"""RecordingControls: toggle-кнопка REC/Stop + таймер автостопа + label под hotkey."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QWidget,
)

from plasma_dog.const import DEFAULT_HOTKEY, DEFAULT_TIMER_SECONDS

# Диапазон значений спинбокса таймера в секундах
_TIMER_MIN_SECONDS = 1
_TIMER_MAX_SECONDS = 60 * 60 * 8  # 8 часов

# Метки кнопки REC/Stop в двух состояниях
_REC_LABEL_IDLE = "● REC"
_REC_LABEL_RECORDING = "■ Stop"
# Значения dynamic property "role" для QSS-стилизации в двух состояниях
_ROLE_IDLE = "rec"
_ROLE_RECORDING = "stop"


class RecordingControls(QWidget):
    """Панель управления записью: toggle REC/Stop + автостоп по таймеру.

    Сигналы:
        start_requested: пользователь запросил старт без таймера.
        stop_requested: пользователь запросил остановку.
        start_with_timer_requested: старт + автостоп через seconds секунд.
    """

    start_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    start_with_timer_requested = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rec_button = QPushButton(_REC_LABEL_IDLE)
        self._rec_button.setProperty("role", _ROLE_IDLE)
        self._rec_button.setCheckable(True)

        self._timer_spinbox = QSpinBox()
        self._timer_spinbox.setRange(_TIMER_MIN_SECONDS, _TIMER_MAX_SECONDS)
        self._timer_spinbox.setValue(DEFAULT_TIMER_SECONDS)
        self._timer_spinbox.setSuffix(" с")

        self._timer_button = QPushButton("Старт с таймером")

        # Подсказка про hotkey (реализация в Stage 5)
        self._hotkey_label = QLabel(f"Hotkey: {DEFAULT_HOTKEY}")
        self._hotkey_label.setProperty("role", "muted")

        self._build_layout()
        self._connect_signals()

    def _build_layout(self) -> None:
        """Сборка горизонтального layout кнопок и таймера."""
        layout = QHBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.addWidget(self._rec_button)
        layout.addSpacing(16)
        layout.addWidget(QLabel("Таймер:"))
        layout.addWidget(self._timer_spinbox)
        layout.addWidget(self._timer_button)
        layout.addStretch(1)
        layout.addWidget(self._hotkey_label)
        self.setLayout(layout)

    def _connect_signals(self) -> None:
        """Подключение клик-сигналов к публичным pyqtSignal."""
        self._rec_button.toggled.connect(self._on_rec_toggled)
        self._timer_button.clicked.connect(self._on_timer_clicked)

    def set_recording(self, is_recording: bool) -> None:
        """Программное переключение состояния toggle-кнопки и связанных контролов.

        Используется внешним кодом (MainWindow) после старта/остановки сессии.
        Сигналы кнопки блокируются, чтобы не зациклить эмит start/stop_requested.

        Args:
            is_recording: True, если запись в процессе.
        """
        self._rec_button.blockSignals(True)
        self._rec_button.setChecked(is_recording)
        self._apply_rec_visual_state(is_recording)
        self._rec_button.blockSignals(False)
        self._timer_button.setEnabled(not is_recording)
        self._timer_spinbox.setEnabled(not is_recording)

    def set_timer_default(self, seconds: int) -> None:
        """Установка значения по умолчанию для спинбокса таймера.

        Args:
            seconds: длительность таймера в секундах.
        """
        clamped = max(_TIMER_MIN_SECONDS, min(_TIMER_MAX_SECONDS, seconds))
        self._timer_spinbox.blockSignals(True)
        self._timer_spinbox.setValue(clamped)
        self._timer_spinbox.blockSignals(False)

    def set_hotkey_text(self, hotkey: str) -> None:
        """Обновление текста подсказки о hotkey.

        Args:
            hotkey: строковое представление комбинации клавиш.
        """
        display = hotkey if hotkey else "—"
        self._hotkey_label.setText(f"Hotkey: {display}")

    def timer_value(self) -> int:
        """Текущее значение спинбокса таймера в секундах."""
        return int(self._timer_spinbox.value())

    def _on_rec_toggled(self, checked: bool) -> None:
        """Обработка переключения toggle-кнопки REC/Stop.

        Args:
            checked: новое состояние кнопки (True = "запись началась").
        """
        self._apply_rec_visual_state(checked)
        if checked:
            self.start_requested.emit()
        else:
            self.stop_requested.emit()

    def _on_timer_clicked(self) -> None:
        """Обработка нажатия 'Старт с таймером': эмит сигнала с секундами."""
        self.start_with_timer_requested.emit(int(self._timer_spinbox.value()))

    def _apply_rec_visual_state(self, is_recording: bool) -> None:
        """Обновление текста, dynamic property и refresh стиля кнопки REC/Stop.

        После смены dynamic property требуется reset стиля через unpolish/polish,
        иначе QSS-селектор [role="..."] не пересчитывается.

        Args:
            is_recording: True, если запись активна.
        """
        if is_recording:
            self._rec_button.setText(_REC_LABEL_RECORDING)
            self._rec_button.setProperty("role", _ROLE_RECORDING)
        else:
            self._rec_button.setText(_REC_LABEL_IDLE)
            self._rec_button.setProperty("role", _ROLE_IDLE)
        style = self._rec_button.style()
        if style is not None:
            style.unpolish(self._rec_button)
            style.polish(self._rec_button)
