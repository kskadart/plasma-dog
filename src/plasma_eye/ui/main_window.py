"""MainWindow: топбар + превью + панель настроек + controls + status bar записи."""

from __future__ import annotations

import time
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QCloseEvent, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QComboBox,
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

from plasma_eye.camera.capture import CaptureThread
from plasma_eye.camera.enumerator import CameraInfo, list_cameras
from plasma_eye.camera.properties import CameraProperty
from plasma_eye.const import (
    APP_NAME,
    DEFAULT_FOURCC,
    DEFAULT_FPS,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
)
from plasma_eye.recording.session import RecordingConfig, RecordingSession
from plasma_eye.settings import AppSettings
from plasma_eye.ui.camera_panel import CameraSettingsPanel
from plasma_eye.ui.controls import RecordingControls
from plasma_eye.ui.preview import PreviewWidget
from plasma_eye.ui.settings_dialog import SettingsDialog
from plasma_eye.ui.status_bar import RecordingStatusBar

# Стартовая ширина правой панели настроек (только при первом запуске)
_SETTINGS_PANEL_DEFAULT_WIDTH = 460
# Стартовый размер окна
_WINDOW_WIDTH = 1280
_WINDOW_HEIGHT = 800
# Фиксированная ширина кнопки выбора папки записей
_FOLDER_PICKER_BUTTON_WIDTH = 40
# Подписи кнопки toggle правой панели
_TOGGLE_PANEL_HIDE = "Скрыть настройки"
_TOGGLE_PANEL_SHOW = "Показать настройки"


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

        self._preview = PreviewWidget()
        self._camera_selector = QComboBox()
        self._refresh_button = QPushButton("Обновить")
        self._toggle_panel_button = QPushButton(_TOGGLE_PANEL_HIDE)
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
        topbar = QHBoxLayout()
        topbar.setSpacing(8)
        topbar.addWidget(QLabel("Камера:"))
        topbar.addWidget(self._camera_selector, stretch=1)
        topbar.addWidget(self._refresh_button)
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

        # Восстановление видимости панели и подписи кнопки.
        visible = self._settings.camera_panel_visible
        self._camera_panel.setVisible(visible)
        self._toggle_panel_button.setText(_TOGGLE_PANEL_HIDE if visible else _TOGGLE_PANEL_SHOW)

    def _connect_signals(self) -> None:
        """Подключение сигналов виджетов и сессии записи."""
        self._refresh_button.clicked.connect(self._refresh_cameras)
        self._toggle_panel_button.clicked.connect(self._toggle_camera_panel)
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
        self._toggle_panel_button.setText(_TOGGLE_PANEL_HIDE if visible else _TOGGLE_PANEL_SHOW)
        self._settings.camera_panel_visible = visible

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        """Сохранение размеров splitter при ручном изменении пользователем."""
        self._settings.splitter_sizes = self._splitter.sizes()

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
        сессии, hotkey, дефолтный таймер.
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
            parent=self,
        )
        self._capture.frame_ready.connect(self._preview.update_frame)
        self._capture.error_occurred.connect(self._on_capture_error)
        self._capture.properties_introspected.connect(self._camera_panel.on_properties_introspected)
        self._capture.properties_introspected.connect(self._apply_pending_snapshot)
        self._camera_panel.property_changed.connect(self._capture.set_property)
        self._camera_panel.set_capture(self._capture)
        # Интроспекцию запрашиваем после того как run() стартует и откроет cap.
        self._capture.started_capture.connect(self._on_capture_started)
        self._capture.start()

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

    def _stop_capture(self) -> None:
        """Корректная остановка текущего CaptureThread, если он есть."""
        if self._capture is None:
            return
        if self._session.is_recording:
            self._stop_recording()
        try:
            self._capture.frame_ready.disconnect(self._preview.update_frame)
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
