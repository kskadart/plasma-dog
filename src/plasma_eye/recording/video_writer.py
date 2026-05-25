"""VideoWriterThread: запись BGR кадров в mp4 через отдельный QThread."""

from __future__ import annotations

import logging
import queue
from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from plasma_eye.const import VIDEO_QUEUE_MAXSIZE

logger = logging.getLogger(__name__)

# Sentinel, кладётся в очередь, чтобы попросить поток выйти
_STOP_SENTINEL: None = None
# Fallback кодек по умолчанию
_DEFAULT_FOURCC = "avc1"
# Минимальный fps, который кодеки (особенно H.264/avc1) принимают без C++ exception
# на writer.write(). Sub-1 fps в record_session обрабатывается throttling'ом,
# а video.mp4 пишется с этим минимумом → получается time-lapse эффект.
_MIN_WRITER_FPS = 1.0
# Цепочки fallback по контейнерам. mp4-кодек НЕ пишется в .webm и наоборот:
# несовместимый кодек + контейнер даёт битый файл (даже если writer откроется).
# Поэтому VP9/VP8 имеют только друг друга — никаких mp4 codec в .webm.
_FOURCC_CHAINS: dict[str, tuple[str, ...]] = {
    "avc1": ("avc1", "mp4v", "MJPG"),  # H.264 в .mp4 -> MPEG-4 -> MJPG в .mp4
    "mp4v": ("mp4v", "avc1", "MJPG"),  # MPEG-4 -> H.264 -> MJPG
    "MJPG": ("MJPG",),  # уже MJPG, fallback не нужен
    "VP90": ("VP90", "VP80"),  # WebM only — без mp4 codec, файл уйдёт в мусор
}
# Если кодек не зарегистрирован выше — пробуем как-есть + универсальный MJPG.
_DEFAULT_CHAIN = ("MJPG",)
# Каждые сколько дропов писать предупреждение, чтобы не засорять лог
_DROP_LOG_INTERVAL = 30
# Таймаут чтения из очереди (даёт шанс проверить флаг остановки)
_QUEUE_GET_TIMEOUT = 0.5


class VideoWriterThread(QThread):
    """Поток записи видео: bounded queue + cv2.VideoWriter.

    Кадры кладутся через submit() из любого потока. Если очередь забита —
    кадр сбрасывается и счётчик дропов растёт. На stop() поток завершается
    после дозаписи остатка очереди.
    """

    # счётчик записанных кадров (нарастающий итог)
    frame_written = pyqtSignal(int)
    # счётчик сброшенных кадров (нарастающий итог)
    frame_dropped = pyqtSignal(int)
    # сообщение об ошибке открытия/записи
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        output_path: Path,
        width: int,
        height: int,
        fps: float,
        fourcc: str = _DEFAULT_FOURCC,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._output_path = output_path
        self._width = width
        self._height = height
        # Запрошенный fps записи (логический темп для статистики).
        self._requested_fps = fps
        # Effective fps для cv2.VideoWriter: H.264 (avc1) кидает C++ exception
        # на writer.write() при fps < 1.0. Зажимаем минимум до 1.0.
        # При sub-1 fps пользователь получает time-lapse видео.
        self._fps = max(_MIN_WRITER_FPS, fps)
        self._fourcc = fourcc
        self._queue: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=VIDEO_QUEUE_MAXSIZE)
        self._written = 0
        self._dropped = 0
        if self._fps != fps:
            logger.info(
                "VideoWriter fps зажат с %g до %g (кодек требует >= %g fps). "
                "Видео-файл будет в формате time-lapse.",
                fps,
                self._fps,
                _MIN_WRITER_FPS,
            )

    def submit(self, frame: np.ndarray) -> None:
        """Постановка кадра в очередь записи.

        Args:
            frame: numpy BGR кадр, готовый к записи.
        """
        try:
            self._queue.put_nowait(frame)
        except queue.Full:
            self._dropped += 1
            if self._dropped % _DROP_LOG_INTERVAL == 0:
                logger.warning("VideoWriter: дропов накоплено %d (очередь забита)", self._dropped)
            self.frame_dropped.emit(self._dropped)

    def stop(self) -> None:
        """Сигнал потоку завершиться и ожидание завершения."""
        self._queue.put(_STOP_SENTINEL)
        self.wait()

    @property
    def written(self) -> int:
        """Количество успешно записанных кадров."""
        return self._written

    @property
    def dropped(self) -> int:
        """Количество сброшенных кадров (queue overflow)."""
        return self._dropped

    def run(self) -> None:
        """Открытие writer и цикл записи кадров до sentinel.

        Сначала пробуется основной кодек, затем codec-specific fallbacks (например
        VP90 -> VP80), затем универсальная цепочка fallback. Логирует, какой кодек
        в итоге использован, либо emit error_occurred при полном провале открытия.
        Если итоговый кодек не из codec-specific fallbacks - пишет warning
        (контейнер мог не совпасть с расширением файла).
        """
        chain = self._build_fallback_chain()
        writer: cv2.VideoWriter | None = None
        used_fourcc = self._fourcc
        for fourcc in chain:
            writer = self._open_writer(fourcc)
            if writer is not None:
                used_fourcc = fourcc
                break
        if writer is None:
            message = (
                f"Не удалось открыть видео-файл {self._output_path} ни с одним кодеком "
                f"(перебор: {', '.join(chain)})"
            )
            logger.error(message)
            self.error_occurred.emit(message)
            return
        if used_fourcc != self._fourcc:
            logger.info(
                "VideoWriter: основной кодек %s недоступен, использован fallback %s "
                "(контейнер %s совместим).",
                self._fourcc,
                used_fourcc,
                self._output_path.suffix,
            )
        logger.info(
            "VideoWriter открыт: %s, кодек=%s, %dx%d @ %g fps",
            self._output_path,
            used_fourcc,
            self._width,
            self._height,
            self._fps,
        )
        try:
            self._consume(writer)
        finally:
            writer.release()
            # Верификация: если кадры писались, но файл нулевой/мизерный —
            # кодек молча провалился (типично для macOS AVFoundation + некоторых
            # FOURCC). Сообщаем пользователю чтобы сменил кодек.
            file_size = self._output_path.stat().st_size if self._output_path.exists() else 0
            if self._written > 0 and file_size < 1024:
                message = (
                    f"Видео-файл {self._output_path} получился размером {file_size} байт "
                    f"({self._written} кадров должно было быть записано). Кодек "
                    f"{used_fourcc} не поддерживается на этой системе. Смените кодек "
                    "в настройках (например, на Motion JPEG или VP9/WebM)."
                )
                logger.error(message)
                self.error_occurred.emit(message)
            logger.info(
                "VideoWriter закрыт: %s, записано=%d, дропов=%d, размер=%d B",
                self._output_path,
                self._written,
                self._dropped,
                file_size,
            )

    def _build_fallback_chain(self) -> tuple[str, ...]:
        """Сборка упорядоченной цепочки fourcc-кодов для попыток открытия.

        Цепочка определяется по primary кодеку из _FOURCC_CHAINS. Кодеки в одной
        цепочке используют совместимый контейнер (mp4 / avi / webm) — нельзя
        смешивать VP9-в-mp4 или MJPG-в-webm, файл будет битым.

        Returns:
            Кортеж fourcc-строк для последовательного перебора.
        """
        chain = _FOURCC_CHAINS.get(self._fourcc)
        if chain is None:
            return (self._fourcc, *_DEFAULT_CHAIN)
        return chain

    def _open_writer(self, fourcc: str) -> cv2.VideoWriter | None:
        """Попытка открыть cv2.VideoWriter с указанным кодеком.

        Args:
            fourcc: 4-символьный FOURCC код.

        Returns:
            Открытый VideoWriter или None при неудаче.
        """
        codec = cv2.VideoWriter.fourcc(*fourcc)
        writer = cv2.VideoWriter(
            str(self._output_path),
            codec,
            float(self._fps),
            (self._width, self._height),
        )
        if not writer.isOpened():
            logger.warning("VideoWriter не открылся с кодеком %s", fourcc)
            writer.release()
            return None
        return writer

    def _consume(self, writer: cv2.VideoWriter) -> None:
        """Чтение кадров из очереди до sentinel и запись в writer.

        Ловим cv2.error (C++ exception от кодека) на первом проблемном кадре:
        логируем, эмитим error_occurred и выходим из цикла. Без catch такой
        exception убивает весь процесс через SIGABRT.
        """
        while True:
            try:
                frame = self._queue.get(timeout=_QUEUE_GET_TIMEOUT)
            except queue.Empty:
                continue
            if frame is _STOP_SENTINEL:
                break
            try:
                writer.write(frame)
            except cv2.error as exc:
                message = (
                    f"Кодек {self._fourcc} отверг кадр (cv2.error: {exc}). "
                    f"Параметры: {self._width}x{self._height} @ {self._fps} fps. "
                    "Смените кодек или fps в настройках."
                )
                logger.exception("Ошибка writer.write")
                self.error_occurred.emit(message)
                return
            self._written += 1
            self.frame_written.emit(self._written)
