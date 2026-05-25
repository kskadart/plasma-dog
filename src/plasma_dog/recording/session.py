"""RecordingSession: фасад над VideoWriter + FrameSaver + metadata + статистика."""

from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from plasma_dog.common.path import ensure_dir, session_dir_name
from plasma_dog.const import (
    DEFAULT_VIDEO_CODEC,
    FrameFormat,
    VideoCodec,
    codec_extension,
    codec_fourcc,
)
from plasma_dog.recording.frame_saver import FrameSaverPool
from plasma_dog.recording.metadata import RecordingMetadata, write_metadata
from plasma_dog.recording.video_writer import VideoWriterThread

logger = logging.getLogger(__name__)

# Базовое имя файла видео в session-папке (расширение определяется кодеком)
_VIDEO_BASENAME = "video"
# Имя подпапки с отдельными кадрами
_FRAMES_DIRNAME = "frames"
# Интервал обновления статистики UI, миллисекунды
_STATS_INTERVAL_MS = 500
# Пороги свободного места на диске (байты): warning и hard fail
_DISK_WARNING_BYTES = 500 * 1024 * 1024
_DISK_FATAL_BYTES = 100 * 1024 * 1024


@dataclass
class RecordingConfig:
    """Параметры сессии записи.

    Attributes:
        recordings_root: родительская папка для всех session-папок.
        width: ширина кадра.
        height: высота кадра.
        fps: целевой fps записи. Поддерживает дробные значения (0.5, 1, 24, ...);
            кадры от камеры throttle-ятся под этот интервал.
        fourcc: FOURCC захвата (cv2.VideoCapture).
        frame_format: формат сохранения отдельных кадров.
        frame_quality: качество для frame_saver (PNG: 0..9, JPG: 1..100).
        video_codec: кодек видео-файла (H264/MP4V/MJPG/VP9).
    """

    recordings_root: Path
    width: int
    height: int
    fps: float
    fourcc: str
    frame_format: FrameFormat
    frame_quality: int
    video_codec: VideoCodec = DEFAULT_VIDEO_CODEC


class RecordingSession(QObject):
    """Управление одной сессией записи: видео + кадры + metadata.

    На start() создаётся session-папка, запускаются VideoWriterThread и
    FrameSaverPool, стартует QTimer для периодической эмиссии статистики.
    Кадры приходят через слот on_frame(). На stop() — корректное завершение
    writer/saver и запись metadata.json с измеренным fps.
    """

    # frames_written, frames_dropped, bytes_on_disk, actual_fps
    stats_updated = pyqtSignal(int, int, int, float)
    # сообщение об ошибке от video_writer / создания папок / нехватки места
    error_occurred = pyqtSignal(str)
    # предупреждение (низкое свободное место и т.п.); запись продолжается
    warning_emitted = pyqtSignal(str)

    def __init__(self, config: RecordingConfig, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._session_path: Path | None = None
        self._video_writer: VideoWriterThread | None = None
        self._frame_saver: FrameSaverPool | None = None
        self._metadata: RecordingMetadata | None = None
        self._started_at: float | None = None
        # Путь видео-файла, ждущий ленивой инициализации writer'а при первом
        # кадре. None означает что writer уже создан или сессия не запущена.
        self._pending_video_path: Path | None = None
        # Throttling: интервал между сохраняемыми кадрами в секундах и
        # timestamp последнего сохранённого кадра. Кадры от камеры приходят на
        # её родной частоте (~25-30 fps на UVC), а пользователь может хотеть
        # 10 fps или 0.5 fps (time-lapse) — лишние кадры пропускаем.
        self._target_frame_interval: float = 0.0
        self._last_written_at: float | None = None
        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(_STATS_INTERVAL_MS)
        self._stats_timer.timeout.connect(self._emit_stats)

    @property
    def is_recording(self) -> bool:
        """True, если сессия активна (между start() и stop())."""
        return self._session_path is not None

    def start(self, camera_index: int, camera_props_snapshot: dict[str, float]) -> Path | None:
        """Старт записи: создание папок, инициализация writer/saver, metadata.

        Перед стартом проверяется свободное место на диске. При нехватке менее
        100 MB запись отменяется (error_occurred), при менее 500 MB пишется
        предупреждение (warning_emitted) и запись продолжается.

        Args:
            camera_index: индекс камеры для записи в metadata.
            camera_props_snapshot: снимок UVC-параметров на момент старта.

        Returns:
            Путь к созданной session-папке, либо None при ошибке инициализации.
        """
        try:
            ensure_dir(self._config.recordings_root)
        except (PermissionError, OSError) as exc:
            message = f"Не удалось создать корневую папку записей: {exc}"
            logger.error(message)
            self.error_occurred.emit(message)
            return None

        free_bytes = _free_disk_bytes(self._config.recordings_root)
        if free_bytes is not None and free_bytes < _DISK_FATAL_BYTES:
            message = (
                f"Недостаточно свободного места: {free_bytes // (1024 * 1024)} MB "
                f"(минимум {_DISK_FATAL_BYTES // (1024 * 1024)} MB)"
            )
            logger.error(message)
            self.error_occurred.emit(message)
            return None
        if free_bytes is not None and free_bytes < _DISK_WARNING_BYTES:
            warn = (
                f"Мало свободного места: {free_bytes // (1024 * 1024)} MB. "
                "Запись может быть прервана."
            )
            logger.warning(warn)
            self.warning_emitted.emit(warn)

        try:
            session_path = ensure_dir(self._config.recordings_root / session_dir_name())
            frames_dir = ensure_dir(session_path / _FRAMES_DIRNAME)
        except (PermissionError, OSError) as exc:
            message = f"Не удалось создать папку записи: {exc}"
            logger.error(message)
            self.error_occurred.emit(message)
            return None

        # VideoWriter создаётся ЛЕНИВО при первом кадре: камера может выдать
        # не запрошенный размер (на macOS FaceTime игнорирует 1920x1080 и шлёт
        # свой родной размер), а writer должен совпадать с реальной shape кадра.
        self._pending_video_path = (
            session_path / f"{_VIDEO_BASENAME}.{codec_extension(self._config.video_codec)}"
        )
        self._video_writer = None

        self._frame_saver = FrameSaverPool(
            output_dir=frames_dir,
            fmt=self._config.frame_format,
            quality=self._config.frame_quality,
        )

        self._metadata = RecordingMetadata(
            session_path=session_path,
            started_at=datetime.now(),
            camera_index=camera_index,
            width=self._config.width,
            height=self._config.height,
            target_fps=self._config.fps,
            fourcc=self._config.fourcc,
            frame_format=self._config.frame_format,
            camera_properties=dict(camera_props_snapshot),
        )

        self._session_path = session_path
        self._started_at = time.monotonic()
        # Интервал throttling: 1/fps секунд. Защита от деления на ноль.
        self._target_frame_interval = 1.0 / self._config.fps if self._config.fps > 0 else 0.0
        self._last_written_at = None
        self._stats_timer.start()
        logger.info(
            "Запись начата: %s (target_fps=%g, interval=%.3f s)",
            session_path,
            self._config.fps,
            self._target_frame_interval,
        )
        return session_path

    @pyqtSlot(object, float)
    def on_frame(self, frame: np.ndarray, timestamp: float) -> None:
        """Слот для подключения к CaptureThread.frame_ready с throttling под target fps.

        На первом кадре лениво создаёт VideoWriter с реальной shape кадра —
        камера может отдать не запрошенный размер. Дальше throttle: сохраняем
        только те кадры, что не ближе чем target_frame_interval к предыдущему.

        Args:
            frame: numpy BGR кадр.
            timestamp: время кадра (time.monotonic()), используется для throttling.
        """
        if self._session_path is None:
            return
        if self._video_writer is None and self._pending_video_path is not None:
            self._init_video_writer_from_frame(frame)
        if self._last_written_at is not None:
            elapsed = timestamp - self._last_written_at
            if elapsed < self._target_frame_interval:
                return
        self._last_written_at = timestamp
        if self._video_writer is not None:
            self._video_writer.submit(frame)
        if self._frame_saver is not None:
            self._frame_saver.submit(frame)

    def _init_video_writer_from_frame(self, frame: np.ndarray) -> None:
        """Создание VideoWriter под фактический размер первого кадра.

        Также обновляет metadata реальными dimensions: они могут отличаться от
        запрошенных в RecordingConfig (макбук-камера на macOS часто игнорирует
        cap.set FRAME_WIDTH/HEIGHT и отдаёт свой родной размер).

        Args:
            frame: первый numpy BGR кадр сессии.
        """
        if self._pending_video_path is None:
            return
        height, width = int(frame.shape[0]), int(frame.shape[1])
        if self._metadata is not None and (
            self._metadata.width != width or self._metadata.height != height
        ):
            logger.info(
                "Фактический размер кадра %dx%d отличается от запрошенного %dx%d. "
                "Обновляем metadata и инициализируем VideoWriter под реальные dimensions.",
                width,
                height,
                self._metadata.width,
                self._metadata.height,
            )
            self._metadata.width = width
            self._metadata.height = height
        self._video_writer = VideoWriterThread(
            output_path=self._pending_video_path,
            width=width,
            height=height,
            fps=self._config.fps,
            fourcc=codec_fourcc(self._config.video_codec),
            parent=self,
        )
        self._video_writer.error_occurred.connect(self._on_video_writer_error)
        self._video_writer.start()
        self._pending_video_path = None

    def stop(self) -> Path | None:
        """Остановка записи, завершение потоков, запись metadata.json.

        Returns:
            Путь к session-папке или None, если запись не была начата.
        """
        if self._session_path is None or self._metadata is None:
            return None

        self._stats_timer.stop()
        session_path = self._session_path

        if self._video_writer is not None:
            self._video_writer.stop()
        if self._frame_saver is not None:
            self._frame_saver.shutdown(wait=True)

        elapsed = time.monotonic() - self._started_at if self._started_at is not None else 0.0
        frames_written = self._video_writer.written if self._video_writer is not None else 0
        frames_dropped = (self._video_writer.dropped if self._video_writer is not None else 0) + (
            self._frame_saver.dropped if self._frame_saver is not None else 0
        )
        actual_fps = frames_written / elapsed if elapsed > 0 else 0.0

        self._metadata.stopped_at = datetime.now()
        self._metadata.frames_written = frames_written
        self._metadata.frames_dropped = frames_dropped
        self._metadata.actual_fps = round(actual_fps, 3)
        write_metadata(self._metadata, session_path)

        logger.info(
            "Запись остановлена: %s, frames=%d, dropped=%d, fps=%.2f",
            session_path,
            frames_written,
            frames_dropped,
            actual_fps,
        )

        self._video_writer = None
        self._frame_saver = None
        self._metadata = None
        self._session_path = None
        self._started_at = None
        self._pending_video_path = None
        return session_path

    @pyqtSlot(str)
    def _on_video_writer_error(self, message: str) -> None:
        """Обработчик фатальной ошибки video_writer: отмена сессии.

        VideoWriter эмитит error_occurred при провале открытия (все кодеки
        отказали) или при критической ошибке записи. Дальше держать сессию
        бессмысленно — frame_saver продолжит писать кадры, но видео и
        metadata будут отсутствовать, артефакт неполный.

        Args:
            message: текст ошибки от video_writer.
        """
        if self._session_path is None:
            return
        logger.error("VideoWriter упал, отмена сессии: %s", message)
        self._abort_session(message)

    def _abort_session(self, message: str) -> None:
        """Прерывание сессии: остановка пула, удаление частичных артефактов.

        Args:
            message: текст ошибки для проброса в UI через error_occurred.
        """
        session_path = self._session_path
        if session_path is None:
            return
        # обнуление session_path первым делом: дальнейшие on_frame() становятся no-op
        self._session_path = None
        self._stats_timer.stop()
        if self._frame_saver is not None:
            self._frame_saver.shutdown(wait=False)
            self._frame_saver = None
        if self._video_writer is not None:
            self._video_writer.stop()
            self._video_writer = None
        self._pending_video_path = None
        self._metadata = None
        self._started_at = None
        # удаление частично записанной папки сессии
        try:
            if session_path.exists():
                shutil.rmtree(session_path)
                logger.info("Удалена прерванная сессия: %s", session_path)
        except OSError as exc:
            logger.warning("Не удалось удалить прерванную сессию %s: %s", session_path, exc)
        self.error_occurred.emit(message)

    def _emit_stats(self) -> None:
        """Периодическая эмиссия статистики записи в UI."""
        if self._session_path is None or self._started_at is None:
            return
        elapsed = time.monotonic() - self._started_at
        frames_written = self._video_writer.written if self._video_writer is not None else 0
        frames_dropped = (self._video_writer.dropped if self._video_writer is not None else 0) + (
            self._frame_saver.dropped if self._frame_saver is not None else 0
        )
        bytes_on_disk = _dir_size(self._session_path)
        actual_fps = frames_written / elapsed if elapsed > 0 else 0.0
        self.stats_updated.emit(frames_written, frames_dropped, bytes_on_disk, actual_fps)


def _dir_size(path: Path) -> int:
    """Суммарный размер файлов в директории рекурсивно.

    Args:
        path: корневая директория.

    Returns:
        Сумма размеров регулярных файлов в байтах.
    """
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except OSError:
                continue
    return total


def _free_disk_bytes(path: Path) -> int | None:
    """Свободное место на разделе, содержащем path.

    Если путь ещё не существует, проверяется ближайший существующий предок.

    Args:
        path: путь, для которого нужно узнать свободное место.

    Returns:
        Свободные байты или None, если измерение невозможно.
    """
    probe = path
    while probe != probe.parent and not probe.exists():
        probe = probe.parent
    try:
        usage = shutil.disk_usage(probe)
    except OSError:
        return None
    return usage.free
