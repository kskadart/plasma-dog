"""MainWindow: топбар + превью + панель настроек + controls + status bar записи."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QAction, QCloseEvent, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from plasma_dog.alarm.flame_alarm import FlameAlarm
from plasma_dog.camera.capture import CaptureThread
from plasma_dog.camera.enumerator import CameraInfo, list_cameras
from plasma_dog.camera.properties import CameraProperty
from plasma_dog.const import (
    APP_NAME,
    DEFAULT_FOURCC,
    DEFAULT_FPS,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    MIN_FLAME_INFER_HZ,
    FlameState,
)
from plasma_dog.detection.flame_detector import FlameDetector
from plasma_dog.recording.session import RecordingConfig, RecordingSession
from plasma_dog.settings import AppSettings
from plasma_dog.ui.calibration_dialog import CalibrationDialog
from plasma_dog.ui.camera_panel import CameraSettingsPanel
from plasma_dog.ui.controls import RecordingControls
from plasma_dog.ui.flame_indicator import FlameIndicator
from plasma_dog.ui.preview import PreviewWidget
from plasma_dog.ui.settings_dialog import SettingsDialog
from plasma_dog.ui.status_bar import RecordingStatusBar
from plasma_dog.ui.style import ACCENT_READY, ACCENT_WARNING, FONT_MONO, TEXT_SECONDARY

# Стартовая ширина правой панели настроек (только при первом запуске)
_SETTINGS_PANEL_DEFAULT_WIDTH = 460
# Стартовый размер окна
_WINDOW_WIDTH = 1280
_WINDOW_HEIGHT = 800
# Фиксированная ширина кнопки выбора папки записей
_FOLDER_PICKER_BUTTON_WIDTH = 40
# Кнопка-тумблер правой UVC-панели: компактная иконка + тултип по состоянию
# (иконка не меняется, чтобы визуально не путаться с текстовой кнопкой "Настройки").
_TOGGLE_PANEL_ICON = "🎛"
_TOGGLE_PANEL_BUTTON_WIDTH = 44
_TOGGLE_PANEL_TOOLTIP_HIDE = "Скрыть настройки камеры"
_TOGGLE_PANEL_TOOLTIP_SHOW = "Показать настройки камеры"


class MainWindow(QMainWindow):
    """Главное окно: выбор камеры + live превью + контролы записи + статистика."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(_WINDOW_WIDTH, _WINDOW_HEIGHT)

        self._settings = AppSettings()
        self._capture: CaptureThread | None = None
        self._cameras: list[CameraInfo] = []
        self._auto_stop_timer: QTimer | None = None
        self._recording_started_at: float | None = None
        # Снимок камеры из settings, который применяется один раз
        # после первой интроспекции UVC параметров.
        self._pending_camera_snapshot: dict[str, float] | None = None

        # CV-детектор горения и троттлинг его прогона по кадрам превью.
        self._flame_detector = FlameDetector(
            thr_low=self._settings.flame_blob_thr_low,
            thr_high=self._settings.flame_blob_thr_high,
            confirm_frames=self._settings.flame_confirm_frames,
        )
        self._last_infer_at: float | None = None
        self._infer_interval = 1.0 / max(MIN_FLAME_INFER_HZ, self._settings.flame_infer_hz)

        # Звуковая тревога при погасшем пламени; начальная конфигурация из settings.
        self._flame_alarm = FlameAlarm(self)
        self._reconfigure_flame_alarm()

        self._preview = PreviewWidget()
        self._camera_selector = QComboBox()
        self._refresh_button = QPushButton("Обновить")
        self._toggle_panel_button = QPushButton(_TOGGLE_PANEL_ICON)
        self._toggle_panel_button.setFixedWidth(_TOGGLE_PANEL_BUTTON_WIDTH)
        self._recordings_dir_edit = QLineEdit()
        self._recordings_dir_edit.setReadOnly(True)
        self._recordings_dir_pick_button = QPushButton("...")
        self._recordings_dir_pick_button.setFixedWidth(_FOLDER_PICKER_BUTTON_WIDTH)
        self._controls = RecordingControls()
        self._status_bar = RecordingStatusBar()
        self._camera_panel = CameraSettingsPanel()
        # Splitter для resizable панели — пользователь тянет разделитель между
        # превью и UVC-панелью. Видимость и размеры панели сохраняются в QSettings.
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._preview)
        self._splitter.addWidget(self._camera_panel)
        self._splitter.setCollapsible(0, False)
        self._splitter.setCollapsible(1, True)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 0)
        self._splitter.setHandleWidth(8)

        self._session = RecordingSession(self._build_recording_config(), parent=self)

        self._hotkey_shortcut: QShortcut | None = None

        self._build_menu()
        self._build_layout()
        self._apply_recording_mode()
        self._apply_settings_to_widgets()
        self._connect_signals()
        self._install_hotkey()
        self._refresh_cameras()

    def _build_recording_config(self) -> RecordingConfig:
        """Сборка RecordingConfig с актуальными значениями из AppSettings."""
        return RecordingConfig(
            recordings_root=self._settings.recordings_dir,
            width=DEFAULT_WIDTH,
            height=DEFAULT_HEIGHT,
            fps=self._settings.recording_fps,
            fourcc=DEFAULT_FOURCC,
            frame_format=self._settings.frame_format,
            frame_quality=self._settings.frame_quality,
            video_codec=self._settings.video_codec,
        )

    def _build_menu(self) -> None:
        """Создание меню 'Файл' с пунктом 'Настройки...'."""
        menubar = self.menuBar()
        if menubar is None:
            return
        file_menu = menubar.addMenu("Файл")
        if file_menu is None:
            return
        settings_action = QAction("Настройки...", self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self._open_settings_dialog)
        file_menu.addAction(settings_action)
        file_menu.addSeparator()
        quit_action = QAction("Выход", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    def _build_layout(self) -> None:
        """Сборка топбара, секции папки записей, превью, controls и status bar."""
        self._flame_indicator = FlameIndicator()
        self._brightness_label = QLabel("Яркость: —")
        self._brightness_label.setStyleSheet(f"font-family: {FONT_MONO}; color: {TEXT_SECONDARY};")
        self._alarm_toggle_button = QPushButton()
        self._alarm_toggle_button.setCheckable(True)
        self._alarm_toggle_button.setChecked(self._settings.alarm_enabled)
        self._calibrate_button = QPushButton("Калибровать")
        self._calibrate_button.setEnabled(False)
        self._settings_button = QPushButton("Настройки")

        topbar = QHBoxLayout()
        topbar.setSpacing(8)
        topbar.addWidget(QLabel("Камера:"))
        topbar.addWidget(self._camera_selector, stretch=1)
        topbar.addWidget(self._flame_indicator)
        topbar.addWidget(self._brightness_label)
        topbar.addWidget(self._alarm_toggle_button)
        topbar.addWidget(self._calibrate_button)
        topbar.addWidget(self._refresh_button)
        topbar.addWidget(self._settings_button)
        topbar.addWidget(self._toggle_panel_button)

        folder_row = QHBoxLayout()
        folder_row.setSpacing(8)
        folder_row.addWidget(QLabel("Папка записей:"))
        folder_row.addWidget(self._recordings_dir_edit, stretch=1)
        folder_row.addWidget(self._recordings_dir_pick_button)

        # Восстановление размеров splitter из настроек или дефолт.
        saved_sizes = self._settings.splitter_sizes
        if saved_sizes:
            self._splitter.setSizes(saved_sizes)
        else:
            preview_width = max(_WINDOW_WIDTH - _SETTINGS_PANEL_DEFAULT_WIDTH - 24, 400)
            self._splitter.setSizes([preview_width, _SETTINGS_PANEL_DEFAULT_WIDTH])

        root = QVBoxLayout()
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)
        root.addLayout(topbar)
        root.addLayout(folder_row)
        root.addWidget(self._splitter, stretch=1)
        root.addWidget(self._controls)
        root.addWidget(self._status_bar)

        container = QWidget()
        container.setLayout(root)
        self.setCentralWidget(container)

        # Восстановление видимости панели и тултипа кнопки-тумблера.
        visible = self._settings.camera_panel_visible
        self._camera_panel.setVisible(visible)
        self._toggle_panel_button.setToolTip(
            _TOGGLE_PANEL_TOOLTIP_HIDE if visible else _TOGGLE_PANEL_TOOLTIP_SHOW
        )
        self._update_alarm_button()

    def _connect_signals(self) -> None:
        """Подключение сигналов виджетов и сессии записи."""
        self._refresh_button.clicked.connect(self._refresh_cameras)
        self._calibrate_button.clicked.connect(self._open_calibration)
        self._settings_button.clicked.connect(self._open_settings_dialog)
        self._toggle_panel_button.clicked.connect(self._toggle_camera_panel)
        self._alarm_toggle_button.toggled.connect(self._on_alarm_toggled)
        self._splitter.splitterMoved.connect(self._on_splitter_moved)
        self._camera_selector.currentIndexChanged.connect(self._on_camera_selected)
        self._recordings_dir_pick_button.clicked.connect(self._pick_recordings_dir)
        self._controls.start_requested.connect(self._start_recording)
        self._controls.stop_requested.connect(self._stop_recording)
        self._controls.start_with_timer_requested.connect(self._start_recording_with_timer)
        self._session.stats_updated.connect(self._on_stats_updated)
        self._session.error_occurred.connect(self._on_recording_error)
        self._session.warning_emitted.connect(self._on_recording_warning)

    def _toggle_camera_panel(self) -> None:
        """Toggle видимости правой UVC-панели с сохранением состояния в settings."""
        visible = not self._camera_panel.isVisible()
        self._camera_panel.setVisible(visible)
        self._toggle_panel_button.setToolTip(
            _TOGGLE_PANEL_TOOLTIP_HIDE if visible else _TOGGLE_PANEL_TOOLTIP_SHOW
        )
        self._settings.camera_panel_visible = visible

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        """Сохранение размеров splitter при ручном изменении пользователем."""
        self._settings.splitter_sizes = self._splitter.sizes()

    def _update_alarm_button(self) -> None:
        """Синхронизация текста и цвета кнопки тревоги с её состоянием.

        Включено -> зелёный текст "Тревога: ВКЛ", выключено -> янтарный
        "Тревога: ВЫКЛ" (моно-шрифт по образцу индикатора яркости).
        """
        enabled = self._alarm_toggle_button.isChecked()
        text = "Тревога: ВКЛ" if enabled else "Тревога: ВЫКЛ"
        color = ACCENT_READY if enabled else ACCENT_WARNING
        self._alarm_toggle_button.setText(text)
        self._alarm_toggle_button.setStyleSheet(f"font-family: {FONT_MONO}; color: {color};")

    def _on_alarm_toggled(self, checked: bool) -> None:
        """Тумблер тревоги: запись настройки, заглушение при выключении и
        повторный подъём тревоги при включении, если пламя уже погасло.

        Args:
            checked: новое состояние кнопки (True -> тревога включена).
        """
        self._settings.alarm_enabled = checked
        if not checked:
            self._flame_alarm.stop()
        elif self._flame_detector.state is FlameState.EXTINGUISHED:
            # повторное включение при уже погасшем пламени -> сразу поднять тревогу:
            # старт по смене состояния не сработает, т.к. состояние не менялось
            self._flame_alarm.start()
        self._update_alarm_button()

    def _apply_settings_to_widgets(self) -> None:
        """Синхронизация виджетов с актуальными настройками."""
        self._controls.set_timer_default(self._settings.timer_default_seconds)
        self._controls.set_hotkey_text(self._settings.hotkey_start_stop)
        self._recordings_dir_edit.setText(str(self._settings.recordings_dir))

    def _install_hotkey(self) -> None:
        """Создание/пересоздание QShortcut под hotkey из settings."""
        if self._hotkey_shortcut is not None:
            self._hotkey_shortcut.activated.disconnect(self._toggle_recording)
            self._hotkey_shortcut.deleteLater()
            self._hotkey_shortcut = None
        sequence = QKeySequence(self._settings.hotkey_start_stop)
        if sequence.isEmpty():
            return
        self._hotkey_shortcut = QShortcut(sequence, self)
        self._hotkey_shortcut.activated.connect(self._toggle_recording)

    def _toggle_recording(self) -> None:
        """Хоткей: старт записи если простой, иначе остановка."""
        if self._session.is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _pick_recordings_dir(self) -> None:
        """Выбор новой папки для записей через QFileDialog.

        Во время активной записи смена папки игнорируется с предупреждением,
        иначе пересоздаётся RecordingSession с новым RecordingConfig и
        обновляется отображаемый путь.
        """
        if self._session.is_recording:
            QMessageBox.warning(
                self,
                APP_NAME,
                "Невозможно сменить папку во время записи. Остановите запись и попробуйте снова.",
            )
            return
        current = str(self._settings.recordings_dir)
        chosen = QFileDialog.getExistingDirectory(self, "Выберите папку для записей", current)
        if not chosen:
            return
        new_path = Path(chosen)
        if new_path == self._settings.recordings_dir:
            return
        self._settings.recordings_dir = new_path
        self._rebuild_session_config()
        self._recordings_dir_edit.setText(str(new_path))

    def _rebuild_session_config(self) -> None:
        """Пересборка RecordingSession с актуальным RecordingConfig.

        Вызывается после смены настроек, влияющих на конфиг записи. Не
        вызывается во время активной записи (вызывающая сторона проверяет).
        """
        self._session = RecordingSession(self._build_recording_config(), parent=self)
        self._session.stats_updated.connect(self._on_stats_updated)
        self._session.error_occurred.connect(self._on_recording_error)
        self._session.warning_emitted.connect(self._on_recording_warning)

    def _open_settings_dialog(self) -> None:
        """Открытие модального диалога настроек.

        При принятии диалога перечитывает все производные конфиги: RecordingConfig
        сессии, hotkey, дефолтный таймер, а также параметры CV-детектора горения.
        """
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec() != SettingsDialog.DialogCode.Accepted:
            return
        # Обновить RecordingSession config (если сессия активна — заменим
        # на следующем старте, прерывать активную запись нельзя).
        if not self._session.is_recording:
            self._rebuild_session_config()
        self._apply_settings_to_widgets()
        self._install_hotkey()
        self._reconfigure_flame_detector()
        self._reconfigure_flame_alarm()
        # Синхронизация кнопки тревоги с возможно изменённой настройкой без
        # повторного применения (blockSignals -> toggled-слот не сработает).
        self._alarm_toggle_button.blockSignals(True)
        self._alarm_toggle_button.setChecked(self._settings.alarm_enabled)
        self._alarm_toggle_button.blockSignals(False)
        self._update_alarm_button()
        if self._capture is not None:
            self._capture.set_mirror(self._settings.camera_mirror)
        self._apply_recording_mode()

    def _apply_recording_mode(self) -> None:
        """Показ/скрытие UI записи по настройке recording_mode_enabled.

        При выключенном режиме кнопки записи и панель статистики скрываются. Если
        в момент выключения идёт запись, она сначала останавливается, чтобы не
        осталась скрытая активная сессия.
        """
        enabled = self._settings.recording_mode_enabled
        if not enabled and self._session.is_recording:
            self._stop_recording()
        self._controls.setVisible(enabled)
        self._status_bar.setVisible(enabled)

    def _refresh_cameras(self) -> None:
        """Перечитывание списка камер и обновление combobox."""
        self._stop_capture()
        self._cameras = list_cameras()
        self._camera_selector.blockSignals(True)
        self._camera_selector.clear()
        if not self._cameras:
            self._camera_selector.addItem("Камеры не найдены")
            self._camera_selector.setEnabled(False)
        else:
            for cam in self._cameras:
                self._camera_selector.addItem(cam.name, userData=cam.index)
            self._camera_selector.setEnabled(True)
        self._camera_selector.blockSignals(False)
        if not self._cameras:
            return
        # Восстановление последней выбранной камеры, если индекс ещё доступен.
        last_idx = self._settings.last_camera_index
        target_pos = 0
        if last_idx is not None:
            for pos, cam in enumerate(self._cameras):
                if cam.index == last_idx:
                    target_pos = pos
                    break
        # Сохранённый snapshot применится после первой интроспекции UVC.
        stored = self._settings.camera_properties
        self._pending_camera_snapshot = stored if stored else None
        if target_pos == self._camera_selector.currentIndex():
            self._on_camera_selected(target_pos)
        else:
            self._camera_selector.setCurrentIndex(target_pos)

    def _on_camera_selected(self, idx: int) -> None:
        """Старт CaptureThread для выбранной камеры."""
        if idx < 0 or idx >= len(self._cameras):
            return
        self._stop_capture()
        cam = self._cameras[idx]
        # Камера крутится на родной частоте (DEFAULT_FPS как hint для cap.set);
        # пользовательский recording_fps применяется ТОЛЬКО к записи через
        # throttling в RecordingSession. Иначе preview дёргается при низком fps
        # (например 0.5 fps = один кадр в 2 секунды).
        self._capture = CaptureThread(
            camera_index=cam.index,
            width=DEFAULT_WIDTH,
            height=DEFAULT_HEIGHT,
            fps=DEFAULT_FPS,
            fourcc=DEFAULT_FOURCC,
            mirror=self._settings.camera_mirror,
            parent=self,
        )
        self._capture.frame_ready.connect(self._preview.update_frame)
        self._capture.frame_ready.connect(self._on_frame_for_detection)
        self._capture.error_occurred.connect(self._on_capture_error)
        self._capture.properties_introspected.connect(self._camera_panel.on_properties_introspected)
        self._capture.properties_introspected.connect(self._apply_pending_snapshot)
        self._camera_panel.property_changed.connect(self._capture.set_property)
        self._camera_panel.set_capture(self._capture)
        # Интроспекцию запрашиваем после того как run() стартует и откроет cap.
        self._capture.started_capture.connect(self._on_capture_started)
        self._capture.start()
        self._calibrate_button.setEnabled(True)

    def _on_capture_started(self) -> None:
        """Слот started_capture: запрос интроспекции UVC у текущего capture."""
        if self._capture is not None:
            self._capture.request_introspection()

    def _apply_pending_snapshot(self, _snapshot: dict[CameraProperty, float]) -> None:
        """Применение сохранённого snapshot слайдеров после интроспекции.

        Snapshot из AppSettings содержит значения слайдеров пользователя из
        прошлой сессии. Их нельзя применить до интроспекции, иначе слайдеры
        могут быть ещё скрыты как unsupported.
        """
        if self._pending_camera_snapshot is None:
            return
        snapshot = self._pending_camera_snapshot
        self._pending_camera_snapshot = None
        self._camera_panel.restore_snapshot(snapshot)
        # Распространить значения в capture (восстановленные слайдеры с blockSignals
        # сами в capture их не отправляют).
        if self._capture is None:
            return
        for prop_value, value in snapshot.items():
            try:
                prop = CameraProperty(prop_value)
            except ValueError:
                continue
            self._capture.set_property(prop, value)

    def _on_capture_error(self, message: str) -> None:
        """Обработка ошибки захвата: показ текста на превью."""
        self._preview.setPixmap(QPixmap())
        self._preview.setText(message)

    @pyqtSlot(object, float)
    def _on_frame_for_detection(self, frame: np.ndarray, timestamp: float) -> None:
        """Прогон CV-детектора горения по кадру с троттлингом под infer_hz.

        Кадры от камеры приходят на её родной частоте; детектор запускается не
        чаще infer_hz. Индикатор обновляется только при смене состояния.

        Args:
            frame: numpy BGR кадр от CaptureThread.
            timestamp: время кадра (time.monotonic()), используется для троттлинга.
        """
        if (
            self._last_infer_at is not None
            and timestamp - self._last_infer_at < self._infer_interval
        ):
            return
        self._last_infer_at = timestamp
        previous = self._flame_detector.state
        state = self._flame_detector.update(frame)
        self._brightness_label.setText(
            f"Яркость: {self._flame_detector.last_fraction * 100.0:.1f} %"
        )
        if state != previous:
            self._flame_indicator.set_state(state)
            # Звуковая тревога: старт только при погасшем пламени и включённой
            # тревоге, иначе (горит/неизвестно/тревога выключена) — стоп.
            if state is FlameState.EXTINGUISHED and self._settings.alarm_enabled:
                self._flame_alarm.start()
            else:
                self._flame_alarm.stop()

    def _reconfigure_flame_detector(self) -> None:
        """Пересоздание детектора горения и троттла из текущих настроек.

        Применяет актуальные значения AppSettings (пороги, кадры подтверждения,
        частота прогона) к живому потоку кадров без перезапуска приложения.
        Вызывается после сохранения параметров детектора вручную в диалоге
        настроек или после калибровки. Индикатор сбрасывается в UNKNOWN.
        """
        self._flame_detector = FlameDetector(
            thr_low=self._settings.flame_blob_thr_low,
            thr_high=self._settings.flame_blob_thr_high,
            confirm_frames=self._settings.flame_confirm_frames,
        )
        self._infer_interval = 1.0 / max(MIN_FLAME_INFER_HZ, self._settings.flame_infer_hz)
        self._flame_indicator.set_state(FlameState.UNKNOWN)

    def _reconfigure_flame_alarm(self) -> None:
        """Переконфигурация звуковой тревоги из текущих настроек.

        Применяет актуальные параметры AppSettings (звук, громкость, интервал
        повтора, эскалацию) к тревоге без перезапуска приложения. Если тревога
        выключена в настройках, она принудительно останавливается. Вызывается при
        инициализации окна и после сохранения настроек в диалоге.
        """
        self._flame_alarm.configure(
            sound_file=self._settings.alarm_sound_file,
            volume=self._settings.alarm_volume,
            heartbeat_interval=self._settings.alarm_heartbeat_s,
            escalate=self._settings.alarm_escalate,
            escalate_seconds=self._settings.alarm_escalate_s,
        )
        if not self._settings.alarm_enabled:
            self._flame_alarm.stop()

    def _open_calibration(self) -> None:
        """Открытие модального диалога калибровки порогов CV-детектора горения.

        Диалог получает живые кадры камеры через сигнал frame_ready, собирает
        выборки долей кляксы для состояний "пламя"/"погасло" и вычисляет пороги.
        При принятии диалога пороги сохраняются в settings, детектор
        пересоздаётся, а индикатор сбрасывается в UNKNOWN.
        """
        if self._capture is None:
            return
        dialog = CalibrationDialog(self)
        self._capture.frame_ready.connect(dialog.add_frame)
        dialog.exec()
        if self._capture is not None:
            try:
                self._capture.frame_ready.disconnect(dialog.add_frame)
            except TypeError:
                # камера могла исчезнуть/переоткрыться во время диалога — допустимо
                pass
        if dialog.result() != QDialog.DialogCode.Accepted:
            return
        thresholds = dialog.result_thresholds()
        if thresholds is None:
            return
        thr_low, thr_high = thresholds
        self._settings.flame_blob_thr_low = thr_low
        self._settings.flame_blob_thr_high = thr_high
        self._reconfigure_flame_detector()

    def _stop_capture(self) -> None:
        """Корректная остановка текущего CaptureThread, если он есть."""
        if self._capture is None:
            return
        if self._session.is_recording:
            self._stop_recording()
        try:
            self._capture.frame_ready.disconnect(self._preview.update_frame)
            self._capture.frame_ready.disconnect(self._on_frame_for_detection)
            self._capture.error_occurred.disconnect(self._on_capture_error)
            self._capture.properties_introspected.disconnect(
                self._camera_panel.on_properties_introspected
            )
            self._capture.properties_introspected.disconnect(self._apply_pending_snapshot)
            self._camera_panel.property_changed.disconnect(self._capture.set_property)
            self._capture.started_capture.disconnect(self._on_capture_started)
        except TypeError:
            # отдельные сигналы могли не быть подключены — допустимо
            pass
        self._camera_panel.set_capture(None)
        self._flame_detector.reset()
        self._flame_alarm.stop()
        self._flame_indicator.set_state(FlameState.UNKNOWN)
        self._brightness_label.setText("Яркость: —")
        self._calibrate_button.setEnabled(False)
        self._capture.stop()
        self._capture.deleteLater()
        self._capture = None

    def _current_camera_index(self) -> int | None:
        """Текущий индекс выбранной камеры или None."""
        idx = self._camera_selector.currentIndex()
        if idx < 0 or idx >= len(self._cameras):
            return None
        return self._cameras[idx].index

    def _start_recording(self) -> None:
        """Старт записи (без автостопа)."""
        self._start_session()

    def _start_recording_with_timer(self, seconds: int) -> None:
        """Старт записи + автостоп через seconds секунд."""
        if not self._start_session():
            return
        self._auto_stop_timer = QTimer(self)
        self._auto_stop_timer.setSingleShot(True)
        self._auto_stop_timer.timeout.connect(self._stop_recording)
        self._auto_stop_timer.start(seconds * 1000)

    def _start_session(self) -> bool:
        """Внутренний старт сессии: проверки + session.start() + подключение слота.

        Returns:
            True, если запись успешно начата.
        """
        if not self._settings.recording_mode_enabled:
            return False
        if self._session.is_recording:
            return False
        if self._capture is None:
            QMessageBox.warning(self, APP_NAME, "Камера не запущена.")
            return False
        camera_index = self._current_camera_index()
        if camera_index is None:
            QMessageBox.warning(self, APP_NAME, "Камера не выбрана.")
            return False
        session_path = self._session.start(
            camera_index=camera_index,
            camera_props_snapshot=self._camera_panel.current_snapshot(),
        )
        if session_path is None:
            # session.start() сам эмитнул error_occurred (нет места, нет прав и т.п.)
            return False
        self._capture.frame_ready.connect(self._session.on_frame)
        self._recording_started_at = time.monotonic()
        self._controls.set_recording(True)
        return True

    def _stop_recording(self) -> None:
        """Остановка записи: отвязка слота, stop(), сброс UI."""
        if self._auto_stop_timer is not None:
            self._auto_stop_timer.stop()
            self._auto_stop_timer.deleteLater()
            self._auto_stop_timer = None
        if not self._session.is_recording:
            return
        if self._capture is not None:
            try:
                self._capture.frame_ready.disconnect(self._session.on_frame)
            except TypeError:
                # сигнал уже отвязан — допустимо при ошибочных переходах состояний
                pass
        self._session.stop()
        self._recording_started_at = None
        self._controls.set_recording(False)
        self._status_bar.reset()

    def _on_stats_updated(
        self,
        frames_written: int,
        frames_dropped: int,
        bytes_on_disk: int,
        actual_fps: float,
    ) -> None:
        """Передача статистики из RecordingSession в status bar."""
        elapsed = (
            time.monotonic() - self._recording_started_at
            if self._recording_started_at is not None
            else 0.0
        )
        self._status_bar.update_stats(
            elapsed=elapsed,
            fps=actual_fps,
            frames_written=frames_written,
            bytes_on_disk=bytes_on_disk,
            dropped=frames_dropped,
        )

    def _on_recording_error(self, message: str) -> None:
        """Показ ошибки записи и принудительная остановка."""
        QMessageBox.critical(self, APP_NAME, message)
        if self._session.is_recording:
            self._stop_recording()

    def _on_recording_warning(self, message: str) -> None:
        """Показ предупреждения о записи (низкое место и т.п.) без остановки."""
        QMessageBox.warning(self, APP_NAME, message)

    def _persist_state(self) -> None:
        """Сохранение последнего snapshot камеры и выбранного индекса в settings."""
        snapshot = self._camera_panel.current_snapshot()
        if snapshot:
            self._settings.camera_properties = snapshot
        self._settings.last_camera_index = self._current_camera_index()
        self._settings.timer_default_seconds = self._controls.timer_value()

    def closeEvent(self, event: QCloseEvent | None) -> None:
        """Завершение записи и CaptureThread перед закрытием окна."""
        if self._session.is_recording:
            self._stop_recording()
        self._persist_state()
        self._stop_capture()
        super().closeEvent(event)
