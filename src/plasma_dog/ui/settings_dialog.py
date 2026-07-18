"""SettingsDialog: модальный диалог редактирования AppSettings."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QLocale
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from plasma_dog.const import (
    APP_NAME,
    MIN_FLAME_INFER_HZ,
    FrameFormat,
    VideoCodec,
    codec_display_name,
)
from plasma_dog.settings import AppSettings, default_frame_quality

# Диапазоны спинбоксов
_PNG_MIN_QUALITY = 0
_PNG_MAX_QUALITY = 9
_JPG_MIN_QUALITY = 1
_JPG_MAX_QUALITY = 100
_TIMER_MIN_SECONDS = 5
_TIMER_MAX_SECONDS = 3600
# Диапазон fps записи: от 0.1 (один кадр каждые 10 секунд, time-lapse) до 240.
_FPS_MIN = 0.1
_FPS_MAX = 240.0
_FPS_STEP = 0.5
_FPS_DECIMALS = 2

# Жёсткая минимальная высота полей ввода основной формы. QSS задаёт полям
# min-height + padding, но это формирует лишь мягкий minimumSizeHint: при
# нехватке вертикального места QFormLayout сжимает строки ниже отрисовываемой
# высоты полей, и стилизованные фоны наезжают друг на друга. Хард-минимум
# запрещает такое сжатие (контент 24 + padding 2*4 + бордер 2 = 34).
_FIELD_MIN_HEIGHT = 34

# Диапазоны секции детектора горения. Пороги показываем оператору в процентах,
# в QSettings храним как долю 0..1 (конверсия через _PERCENT_SCALE).
_FLAME_THR_MIN_PERCENT = 0.0
_FLAME_THR_MAX_PERCENT = 100.0
_FLAME_THR_DECIMALS = 1
_FLAME_CONFIRM_MIN = 1
_FLAME_CONFIRM_MAX = 30
_FLAME_INFER_HZ_MAX = 30.0
_FLAME_INFER_DECIMALS = 1
_PERCENT_SCALE = 100.0

# Подписи поля качества для каждого формата
_QUALITY_LABEL_PNG = "Уровень сжатия PNG (0=без сжатия, 9=макс):"
_QUALITY_LABEL_JPG = "Качество JPG (1-100):"
_QUALITY_LABEL_BMP = "Сжатие не применяется"

# Тултипы для спинбокса качества
_QUALITY_TOOLTIP_PNG = (
    "0 быстрее но больше размер файла, 9 медленнее но меньше размер. "
    "Качество PNG всегда без потерь."
)
_QUALITY_TOOLTIP_JPG = "Качество сжатия с потерями. 95 — почти без артефактов, 100 — максимум."
_QUALITY_TOOLTIP_BMP = "BMP не использует параметр качества"


class SettingsDialog(QDialog):
    """Диалог настроек: папка записей, формат фреймов, hotkey, таймер.

    Изменения применяются только при OK. Сброс очищает все QSettings и
    закрывает диалог — пользователь увидит дефолтные значения после
    следующего открытия.
    """

    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle(f"{APP_NAME} — настройки")
        # Минимальная/стартовая высота вмещает всю форму без сжатия: контент
        # требует ~664px (minimumSizeHint), при меньшей высоте QFormLayout
        # сжимал бы строки и поля наезжали бы друг на друга.
        self.setMinimumSize(640, 680)
        self.resize(720, 720)
        # Явный resize-grip в правом нижнем углу: даёт пользователю визуальный
        # хват для изменения размера окна на всех платформах (macOS не показывает
        # grip автоматически для QDialog).
        self.setSizeGripEnabled(True)

        self._dir_edit = QLineEdit()
        self._dir_edit.setReadOnly(True)
        self._dir_button = QPushButton("Выбрать...")

        self._format_combo = QComboBox()
        for fmt in FrameFormat:
            self._format_combo.addItem(fmt.value.upper(), userData=fmt)

        self._quality_spin = QSpinBox()
        # Диапазон/подпись выставятся в _apply_quality_range согласно начальному формату.
        self._quality_label = QLabel(_QUALITY_LABEL_PNG)

        self._codec_combo = QComboBox()
        for codec in VideoCodec:
            self._codec_combo.addItem(codec_display_name(codec), userData=codec)

        self._fps_spin = QDoubleSpinBox()
        self._fps_spin.setRange(_FPS_MIN, _FPS_MAX)
        self._fps_spin.setSingleStep(_FPS_STEP)
        self._fps_spin.setDecimals(_FPS_DECIMALS)
        # Без стрелок up/down — пользователь вводит значение с клавиатуры.
        self._fps_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        # Принудительная C-локаль: дробная часть через точку (научный стандарт),
        # без зависимости от системной локали macOS/Windows/Linux (RU использует
        # запятую как разделитель десятичной части).
        self._fps_spin.setLocale(QLocale(QLocale.Language.C))
        self._fps_spin.setToolTip(
            "Кадров в секунду на запись. Камера выдаёт ~25-30 кадров/сек, "
            "лишние пропускаются. Дробные значения работают: 0.5 — один кадр "
            "каждые 2 секунды (time-lapse), 0.1 — раз в 10 секунд."
        )

        self._hotkey_edit = QKeySequenceEdit()

        self._timer_spin = QSpinBox()
        self._timer_spin.setRange(_TIMER_MIN_SECONDS, _TIMER_MAX_SECONDS)
        self._timer_spin.setSuffix(" с")

        self._recording_mode_checkbox = QCheckBox("Режим записи")
        self._mirror_checkbox = QCheckBox("Зеркало камеры")

        # Параметры CV-детектора горения. Пороги в процентах (C-локаль -> точка
        # как десятичный разделитель), в settings уходят как доля 0..1.
        self._flame_thr_low_spin = QDoubleSpinBox()
        self._flame_thr_low_spin.setRange(_FLAME_THR_MIN_PERCENT, _FLAME_THR_MAX_PERCENT)
        self._flame_thr_low_spin.setDecimals(_FLAME_THR_DECIMALS)
        self._flame_thr_low_spin.setSuffix(" %")
        self._flame_thr_low_spin.setLocale(QLocale(QLocale.Language.C))

        self._flame_thr_high_spin = QDoubleSpinBox()
        self._flame_thr_high_spin.setRange(_FLAME_THR_MIN_PERCENT, _FLAME_THR_MAX_PERCENT)
        self._flame_thr_high_spin.setDecimals(_FLAME_THR_DECIMALS)
        self._flame_thr_high_spin.setSuffix(" %")
        self._flame_thr_high_spin.setLocale(QLocale(QLocale.Language.C))

        self._flame_confirm_spin = QSpinBox()
        self._flame_confirm_spin.setRange(_FLAME_CONFIRM_MIN, _FLAME_CONFIRM_MAX)

        self._flame_infer_hz_spin = QDoubleSpinBox()
        self._flame_infer_hz_spin.setRange(MIN_FLAME_INFER_HZ, _FLAME_INFER_HZ_MAX)
        self._flame_infer_hz_spin.setDecimals(_FLAME_INFER_DECIMALS)
        self._flame_infer_hz_spin.setLocale(QLocale(QLocale.Language.C))

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Reset
        )
        ok_btn = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText("OK")
        cancel_btn = self._buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn is not None:
            cancel_btn.setText("Отмена")
        reset_btn = self._buttons.button(QDialogButtonBox.StandardButton.Reset)
        if reset_btn is not None:
            reset_btn.setText("Сбросить")

        self._build_layout()
        self._connect_signals()
        self._load_from_settings()

    def _build_layout(self) -> None:
        """Сборка form layout + кнопок управления."""
        form = QFormLayout()
        form.setSpacing(8)

        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)
        dir_row.addWidget(self._dir_edit, stretch=1)
        dir_row.addWidget(self._dir_button)
        form.addRow("Папка записей:", dir_row)

        form.addRow("Формат фреймов:", self._format_combo)
        form.addRow(self._quality_label, self._quality_spin)
        form.addRow("Кодек видео:", self._codec_combo)
        form.addRow("FPS записи:", self._fps_spin)
        form.addRow("Hotkey:", self._hotkey_edit)
        form.addRow("Таймер (по умолчанию):", self._timer_spin)
        # Тумблеры-переключатели: собственный текст чекбокса, строка на всю ширину.
        form.addRow(self._recording_mode_checkbox)
        form.addRow(self._mirror_checkbox)

        # Хард-минимум высоты полям основной формы (см. _FIELD_MIN_HEIGHT):
        # запрещает QFormLayout сжимать строки так, что фоны полей наезжают.
        for field in (
            self._dir_edit,
            self._format_combo,
            self._quality_spin,
            self._codec_combo,
            self._fps_spin,
            self._hotkey_edit,
            self._timer_spin,
        ):
            field.setMinimumHeight(_FIELD_MIN_HEIGHT)

        flame_group = QGroupBox("Детектор горения")
        flame_form = QFormLayout()
        flame_form.setSpacing(8)
        flame_form.addRow("Нижний порог, %:", self._flame_thr_low_spin)
        flame_form.addRow("Верхний порог, %:", self._flame_thr_high_spin)
        flame_form.addRow("Кадров подтверждения:", self._flame_confirm_spin)
        flame_form.addRow("Частота детектора, Гц:", self._flame_infer_hz_spin)
        flame_group.setLayout(flame_form)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        root.addLayout(form)
        root.addWidget(flame_group)
        root.addWidget(self._buttons)

    def _connect_signals(self) -> None:
        """Подключение слотов к виджетам диалога."""
        self._dir_button.clicked.connect(self._on_choose_dir)
        self._format_combo.currentIndexChanged.connect(self._on_format_changed)
        self._buttons.accepted.connect(self._on_accept)
        self._buttons.rejected.connect(self.reject)
        reset_btn = self._buttons.button(QDialogButtonBox.StandardButton.Reset)
        if reset_btn is not None:
            reset_btn.clicked.connect(self._on_reset)

    def _load_from_settings(self) -> None:
        """Заполнение виджетов значениями из AppSettings."""
        self._dir_edit.setText(str(self._settings.recordings_dir))

        current_format = self._settings.frame_format
        idx = self._format_combo.findData(current_format)
        if idx >= 0:
            self._format_combo.blockSignals(True)
            self._format_combo.setCurrentIndex(idx)
            self._format_combo.blockSignals(False)
        self._apply_quality_range(current_format, initial_value=self._settings.frame_quality)

        codec_idx = self._codec_combo.findData(self._settings.video_codec)
        if codec_idx >= 0:
            self._codec_combo.setCurrentIndex(codec_idx)

        self._fps_spin.setValue(self._settings.recording_fps)
        self._hotkey_edit.setKeySequence(QKeySequence(self._settings.hotkey_start_stop))
        self._timer_spin.setValue(self._settings.timer_default_seconds)
        self._recording_mode_checkbox.setChecked(self._settings.recording_mode_enabled)
        self._mirror_checkbox.setChecked(self._settings.camera_mirror)

        self._flame_thr_low_spin.setValue(self._settings.flame_blob_thr_low * _PERCENT_SCALE)
        self._flame_thr_high_spin.setValue(self._settings.flame_blob_thr_high * _PERCENT_SCALE)
        self._flame_confirm_spin.setValue(self._settings.flame_confirm_frames)
        self._flame_infer_hz_spin.setValue(self._settings.flame_infer_hz)

    def _on_choose_dir(self) -> None:
        """Открытие диалога выбора директории для записей."""
        current = self._dir_edit.text() or str(self._settings.recordings_dir)
        chosen = QFileDialog.getExistingDirectory(self, "Папка записей", current)
        if chosen:
            self._dir_edit.setText(chosen)

    def _on_format_changed(self, _idx: int) -> None:
        """Адаптация диапазона спинбокса качества под выбранный формат."""
        fmt = self._current_format()
        self._apply_quality_range(fmt, initial_value=default_frame_quality(fmt))

    def _apply_quality_range(self, fmt: FrameFormat, initial_value: int) -> None:
        """Установка диапазона, подписи и стартового значения спинбокса качества."""
        if fmt is FrameFormat.JPG:
            self._quality_label.setText(_QUALITY_LABEL_JPG)
            self._quality_spin.setRange(_JPG_MIN_QUALITY, _JPG_MAX_QUALITY)
            self._quality_spin.setEnabled(True)
            self._quality_spin.setVisible(True)
            self._quality_spin.setToolTip(_QUALITY_TOOLTIP_JPG)
            clamped = max(_JPG_MIN_QUALITY, min(_JPG_MAX_QUALITY, initial_value))
        elif fmt is FrameFormat.PNG:
            self._quality_label.setText(_QUALITY_LABEL_PNG)
            self._quality_spin.setRange(_PNG_MIN_QUALITY, _PNG_MAX_QUALITY)
            self._quality_spin.setEnabled(True)
            self._quality_spin.setVisible(True)
            self._quality_spin.setToolTip(_QUALITY_TOOLTIP_PNG)
            clamped = max(_PNG_MIN_QUALITY, min(_PNG_MAX_QUALITY, initial_value))
        else:
            # BMP не использует параметр качества — спинбокс скрыт, подпись информативная
            self._quality_label.setText(_QUALITY_LABEL_BMP)
            self._quality_spin.setRange(0, 0)
            self._quality_spin.setEnabled(False)
            self._quality_spin.setVisible(False)
            self._quality_spin.setToolTip(_QUALITY_TOOLTIP_BMP)
            clamped = 0
        self._quality_spin.setValue(clamped)

    def _current_format(self) -> FrameFormat:
        """Возврат FrameFormat, выбранного в комбобоксе."""
        data = self._format_combo.currentData()
        if isinstance(data, FrameFormat):
            return data
        return FrameFormat.PNG

    def _on_accept(self) -> None:
        """Запись значений виджетов в AppSettings и закрытие с accept.

        Пороги детектора валидируются до записи: нижний порог не может быть выше
        верхнего. При нарушении показывается предупреждение и диалог не
        закрывается (ни одно значение не сохраняется).
        """
        thr_low_percent = self._flame_thr_low_spin.value()
        thr_high_percent = self._flame_thr_high_spin.value()
        if thr_low_percent > thr_high_percent:
            QMessageBox.warning(
                self,
                APP_NAME,
                "Нижний порог не может быть больше верхнего.",
            )
            return
        self._settings.recordings_dir = Path(self._dir_edit.text())
        self._settings.frame_format = self._current_format()
        self._settings.frame_quality = int(self._quality_spin.value())
        self._settings.video_codec = self._current_codec()
        self._settings.recording_fps = float(self._fps_spin.value())
        self._settings.hotkey_start_stop = self._hotkey_edit.keySequence().toString()
        self._settings.timer_default_seconds = int(self._timer_spin.value())
        self._settings.recording_mode_enabled = self._recording_mode_checkbox.isChecked()
        self._settings.camera_mirror = self._mirror_checkbox.isChecked()
        self._settings.flame_blob_thr_low = thr_low_percent / _PERCENT_SCALE
        self._settings.flame_blob_thr_high = thr_high_percent / _PERCENT_SCALE
        self._settings.flame_confirm_frames = int(self._flame_confirm_spin.value())
        self._settings.flame_infer_hz = float(self._flame_infer_hz_spin.value())
        self.accept()

    def _current_codec(self) -> VideoCodec:
        """Возврат VideoCodec, выбранного в комбобоксе кодека."""
        data = self._codec_combo.currentData()
        if isinstance(data, VideoCodec):
            return data
        return VideoCodec.H264

    def _on_reset(self) -> None:
        """Очистка всех настроек и закрытие диалога с accept (применить дефолты)."""
        self._settings.clear()
        # Возвращаем accept чтобы main_window перечитал состояние.
        self.accept()
