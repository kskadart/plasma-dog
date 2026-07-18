"""CalibrationDialog: сбор выборок долей кляксы и вычисление порогов детектора.

Диалог собирает по ~3 секунды живых кадров для состояний "пламя горит" и
"погасло", считает по каждому кадру blob_fraction и по накопленным выборкам
вычисляет пороги гистерезиса через detection.calibration.compute_thresholds.
Кадры доставляются извне через слот add_frame (сигнал frame_ready камеры);
диалог постоянно показывает живое превью и текущую долю кляксы, а во время
захвата дополнительно копит эту долю в активную выборку.
"""

from __future__ import annotations

import logging

import numpy as np
from PyQt6.QtCore import QTimer, pyqtSlot
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from plasma_dog.const import APP_NAME
from plasma_dog.detection.calibration import compute_thresholds
from plasma_dog.detection.flame_detector import blob_fraction
from plasma_dog.exceptions import CalibrationError
from plasma_dog.ui.preview import PreviewWidget
from plasma_dog.ui.style import (
    BG_SECONDARY,
    FONT_MONO,
    FONT_SIZE_LG,
    RADIUS_MD,
    SPACING_MD,
    SPACING_SM,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)

# Длительность одного захвата выборки, миллисекунды
_CAPTURE_DURATION_MS = 3000
# Единый троттл превью/индикатора/сэмплирования: не чаще ~12.5 Гц (0.08 с между кадрами)
_DISPLAY_INTERVAL_S = 0.08
# Идентификаторы собираемого состояния
_STATE_FLAME = "flame"
_STATE_POGASLO = "pogaslo"


class CalibrationDialog(QDialog):
    """Диалог калибровки порогов CV-детектора горения по живым кадрам.

    Пользователь захватывает две выборки долей кляксы (пламя/погасло), диалог
    вычисляет пороги и при успехе принимается (accept). Результат доступен через
    result_thresholds() после закрытия.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — калибровка детектора")
        # Минимум под ширину превью (640) плюс поля контента (16+16)
        self.setMinimumWidth(660)

        self._flame: list[float] = []
        self._pogaslo: list[float] = []
        self._collecting: str | None = None
        self._last_sample_at: float | None = None
        self._result: tuple[float, float] | None = None

        self._instruction = QLabel(
            "Калибровка под текущий ракурс камеры.\n"
            "1. До розжига (в кадре видны электроды) — нажмите «Захватить ПОГАСЛО».\n"
            "2. Разожгите плазму.\n"
            "3. Когда пламя стабильно — нажмите «Захватить ПЛАМЯ».\n"
            "4. Нажмите «Вычислить и применить».\n"
            "Ориентируйтесь на превью и «Текущую яркость» ниже."
        )
        self._instruction.setWordWrap(True)
        self._instruction.setStyleSheet(f"color: {TEXT_SECONDARY};")

        # Превью занимает свою естественную минимальную высоту (>=360); без
        # setMaximumHeight, чтобы не создавать конфликт min>max в QVBoxLayout.
        self._preview = PreviewWidget()

        # Индикатор — отдельная плашка под превью с плотным фоном, чтобы текст
        # читался поверх любого (в т.ч. яркого) кадра камеры.
        self._current_label = QLabel("Текущая яркость: —")
        self._current_label.setStyleSheet(
            f"font-family: {FONT_MONO}; font-size: {FONT_SIZE_LG}px; "
            f"font-weight: 600; color: {TEXT_PRIMARY}; "
            f"background-color: {BG_SECONDARY}; "
            f"padding: {SPACING_SM}px {SPACING_MD}px; "
            f"border-radius: {RADIUS_MD}px;"
        )

        self._flame_button = QPushButton("Захватить ПЛАМЯ (3с)")
        self._pogaslo_button = QPushButton("Захватить ПОГАСЛО (3с)")
        self._flame_stats = QLabel()
        self._pogaslo_stats = QLabel()
        self._compute_button = QPushButton("Вычислить и применить")
        self._compute_button.setEnabled(False)

        self._buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        cancel_btn = self._buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn is not None:
            cancel_btn.setText("Отмена")

        self._build_layout()
        self._connect_signals()
        self._update_stats()

    def _build_layout(self) -> None:
        """Сборка инструкции, превью, индикатора, строк захвата и кнопок диалога."""
        flame_row = QHBoxLayout()
        flame_row.setSpacing(8)
        flame_row.addWidget(self._flame_button)
        flame_row.addWidget(self._flame_stats, stretch=1)

        pogaslo_row = QHBoxLayout()
        pogaslo_row.setSpacing(8)
        pogaslo_row.addWidget(self._pogaslo_button)
        pogaslo_row.addWidget(self._pogaslo_stats, stretch=1)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        root.addWidget(self._instruction)
        root.addWidget(self._preview)
        root.addWidget(self._current_label)
        root.addLayout(flame_row)
        root.addLayout(pogaslo_row)
        root.addWidget(self._compute_button)
        root.addWidget(self._buttons)

    def _connect_signals(self) -> None:
        """Подключение слотов к кнопкам захвата, вычисления и отмены."""
        self._flame_button.clicked.connect(self._start_flame_capture)
        self._pogaslo_button.clicked.connect(self._start_pogaslo_capture)
        self._compute_button.clicked.connect(self._on_compute)
        self._buttons.rejected.connect(self.reject)

    @pyqtSlot(object, float)
    def add_frame(self, frame: np.ndarray, timestamp: float) -> None:
        """Обновление превью, индикатора и (при захвате) активной выборки.

        Кадры приходят на родной частоте камеры; превью, индикатор текущей доли
        кляксы и сэмплирование выборки объединены единым троттлом
        _DISPLAY_INTERVAL_S (~12.5 Гц). blob_fraction считается один раз и идёт
        и в индикатор, и (если сбор активен) в активную выборку.

        Args:
            frame: numpy BGR кадр от CaptureThread.
            timestamp: время кадра (time.monotonic()), используется для троттлинга.
        """
        if (
            self._last_sample_at is not None
            and timestamp - self._last_sample_at < _DISPLAY_INTERVAL_S
        ):
            return
        self._last_sample_at = timestamp
        self._preview.update_frame(frame, timestamp)
        fraction = blob_fraction(frame)
        self._current_label.setText(f"Текущая яркость: {fraction * 100.0:.1f} %")
        if self._collecting == _STATE_FLAME:
            self._flame.append(fraction)
        elif self._collecting == _STATE_POGASLO:
            self._pogaslo.append(fraction)

    def _start_flame_capture(self) -> None:
        """Старт захвата выборки состояния "пламя горит"."""
        self._begin_collect(_STATE_FLAME)

    def _start_pogaslo_capture(self) -> None:
        """Старт захвата выборки состояния "погасло"."""
        self._begin_collect(_STATE_POGASLO)

    def _begin_collect(self, state: str) -> None:
        """Очистка выборки, старт сбора и автостоп через _CAPTURE_DURATION_MS.

        Args:
            state: собираемое состояние (_STATE_FLAME или _STATE_POGASLO).
        """
        if state == _STATE_FLAME:
            self._flame = []
        else:
            self._pogaslo = []
        self._collecting = state
        self._last_sample_at = None
        self._set_buttons_enabled(False)
        QTimer.singleShot(_CAPTURE_DURATION_MS, self._finish_collect)

    def _finish_collect(self) -> None:
        """Остановка сбора, обновление статистики и разблокировка кнопок."""
        self._collecting = None
        self._update_stats()
        self._set_buttons_enabled(True)
        self._compute_button.setEnabled(bool(self._flame) and bool(self._pogaslo))

    def _set_buttons_enabled(self, enabled: bool) -> None:
        """Включение/выключение кнопок захвата на время активного сбора.

        Args:
            enabled: True — кнопки доступны, False — заблокированы.
        """
        self._flame_button.setEnabled(enabled)
        self._pogaslo_button.setEnabled(enabled)
        if not enabled:
            self._compute_button.setEnabled(False)

    def _update_stats(self) -> None:
        """Обновление лейблов статистики обеих выборок (кол-во, min-max в %)."""
        self._flame_stats.setText(f"Пламя: {self._sample_summary(self._flame)}")
        self._pogaslo_stats.setText(f"Погасло: {self._sample_summary(self._pogaslo)}")

    def _sample_summary(self, fracs: list[float]) -> str:
        """Краткая статистика выборки: число кадров и диапазон долей в процентах.

        Args:
            fracs: выборка долей кляксы (0..1).

        Returns:
            Строка вида "N кадров, lo-hi%" либо "нет выборки" для пустой выборки.
        """
        if not fracs:
            return "нет выборки"
        return f"{len(fracs)} кадров, {min(fracs) * 100.0:.1f}-{max(fracs) * 100.0:.1f}%"

    def _on_compute(self) -> None:
        """Вычисление порогов по выборкам и принятие диалога при успехе."""
        try:
            thr_low, thr_high = compute_thresholds(self._flame, self._pogaslo)
        except CalibrationError as exc:
            QMessageBox.warning(
                self,
                APP_NAME,
                f"Не удалось вычислить пороги: {exc}. Состояния не разделяются — "
                "переснимите выборки.",
            )
            return
        self._result = (thr_low, thr_high)
        QMessageBox.information(
            self,
            APP_NAME,
            f"Пороги вычислены: нижний={thr_low:.3f}, верхний={thr_high:.3f}.",
        )
        self.accept()

    def result_thresholds(self) -> tuple[float, float] | None:
        """Вычисленные пороги (thr_low, thr_high) либо None, если не вычислены.

        Returns:
            Пара порогов при успешной калибровке, иначе None.
        """
        return self._result
