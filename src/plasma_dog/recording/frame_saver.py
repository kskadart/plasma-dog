"""FrameSaverPool: параллельное сохранение PNG/JPG/BMP через ThreadPoolExecutor."""

from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

from plasma_dog.const import FRAME_SAVER_QUEUE_THRESHOLD, FrameFormat

logger = logging.getLogger(__name__)

# Каждые сколько дропов писать предупреждение в лог
_DROP_LOG_INTERVAL = 30


def _encode_params(fmt: FrameFormat, quality: int) -> list[int]:
    """Параметры cv2.imwrite для заданного формата.

    Args:
        fmt: формат сохранения.
        quality: для PNG — уровень компрессии 0..9; для JPG — качество 1..100.

    Returns:
        Список параметров для cv2.imwrite.
    """
    if fmt is FrameFormat.PNG:
        return [cv2.IMWRITE_PNG_COMPRESSION, quality]
    if fmt is FrameFormat.JPG:
        return [cv2.IMWRITE_JPEG_QUALITY, quality]
    return []


class FrameSaverPool:
    """Пул потоков для параллельной записи отдельных кадров.

    PNG-компрессия 1080p CPU-bound (~30-50ms на ядро), поэтому используем пул
    размером с количество CPU. При переполнении backlog кадр дропается, а
    счётчик дропов растёт — это спасает realtime от затыка диска/CPU.
    """

    def __init__(
        self,
        output_dir: Path,
        fmt: FrameFormat,
        quality: int,
        max_workers: int | None = None,
    ) -> None:
        self._dir = output_dir
        self._fmt = fmt
        self._quality = quality
        self._params = _encode_params(fmt, quality)
        workers = max_workers if max_workers is not None else os.cpu_count() or 4
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="frame-saver")
        self._lock = threading.Lock()
        self._counter = 0
        self._inflight = 0
        self._written = 0
        self._dropped = 0

    @property
    def written(self) -> int:
        """Количество успешно записанных кадров."""
        with self._lock:
            return self._written

    @property
    def dropped(self) -> int:
        """Количество сброшенных кадров (backlog overflow или ошибка cv2.imwrite)."""
        with self._lock:
            return self._dropped

    @property
    def counter(self) -> int:
        """Общее число submitted кадров."""
        with self._lock:
            return self._counter

    def submit(self, frame: np.ndarray) -> None:
        """Постановка кадра в пул на запись.

        Args:
            frame: numpy BGR кадр.
        """
        with self._lock:
            self._counter += 1
            idx = self._counter
            if self._inflight > FRAME_SAVER_QUEUE_THRESHOLD:
                self._dropped += 1
                dropped_total = self._dropped
                accepted = False
            else:
                self._inflight += 1
                accepted = True
                dropped_total = 0
        if not accepted:
            if dropped_total % _DROP_LOG_INTERVAL == 0:
                logger.warning(
                    "FrameSaverPool: дропов накоплено %d (backlog > %d)",
                    dropped_total,
                    FRAME_SAVER_QUEUE_THRESHOLD,
                )
            return
        self._pool.submit(self._write, frame, idx)

    def shutdown(self, wait: bool = True) -> None:
        """Завершение работы пула.

        Args:
            wait: если True, ожидать завершения всех задач.
        """
        self._pool.shutdown(wait=wait)

    def _write(self, frame: np.ndarray, idx: int) -> None:
        """Запись одного кадра на диск (выполняется в worker-потоке)."""
        path = self._dir / f"{idx:06d}.{self._fmt.value}"
        try:
            # cv2.imwrite на Windows не открывает пути с не-ASCII символами
            # (узкий fopen внутри). Кодируем кадр в память и пишем байты через
            # numpy.tofile, который поддерживает Unicode-пути на всех ОС.
            ok, buf = cv2.imencode(f".{self._fmt.value}", frame, self._params)
            if not ok:
                logger.error("cv2.imencode вернул False для %s", path)
                with self._lock:
                    self._dropped += 1
                return
            buf.tofile(str(path))
            with self._lock:
                self._written += 1
        except OSError as exc:
            logger.error("Запись кадра %s не удалась: %s", path, exc)
            with self._lock:
                self._dropped += 1
        finally:
            with self._lock:
                self._inflight -= 1
