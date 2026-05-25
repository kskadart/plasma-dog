"""CaptureThread: чтение кадров с UVC в отдельном QThread + thread-safe UVC controls."""

from __future__ import annotations

import logging
import time

import cv2
from PyQt6.QtCore import QMutex, QMutexLocker, QObject, QThread, pyqtSignal

from plasma_dog.camera.properties import (
    CameraProperty,
    apply_property,
    default_backend,
    read_property,
    supported_properties,
)

logger = logging.getLogger(__name__)

# Допустимый порог подряд идущих неудачных cap.read() перед остановкой
_MAX_CONSECUTIVE_READ_FAILURES = 5


def _fourcc_to_int(fourcc: str) -> int:
    """Конвертация 4-символьного FOURCC в int для cv2.VideoCapture.set().

    Args:
        fourcc: 4-символьная строка (например 'MJPG').

    Returns:
        Целочисленное представление FOURCC.
    """
    return int(cv2.VideoWriter.fourcc(*fourcc))


class CaptureThread(QThread):
    """Поток захвата кадров с UVC-камеры.

    Открывает cv2.VideoCapture в run(), эмитит сигнал frame_ready на каждый кадр.
    Применение UVC-параметров отложено в очередь и выполняется между кадрами,
    чтобы не нарушать ритм cap.read().
    """

    # numpy BGR-кадр + timestamp в секундах (time.monotonic())
    frame_ready = pyqtSignal(object, float)
    # текст ошибки при сбое открытия или чтения
    error_occurred = pyqtSignal(str)
    # успешное открытие камеры
    started_capture = pyqtSignal()
    # результат интроспекции UVC: dict[CameraProperty, float] для поддерживаемых
    properties_introspected = pyqtSignal(dict)

    def __init__(
        self,
        camera_index: int,
        width: int,
        height: int,
        fps: float,
        fourcc: str = "MJPG",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._camera_index = camera_index
        self._width = width
        self._height = height
        self._fps = fps
        self._fourcc = fourcc
        self._running = False
        self._mutex = QMutex()
        # очередь отложенных применений UVC-параметров (применяются между кадрами)
        self._pending_props: list[tuple[CameraProperty, float]] = []
        # флаг запроса интроспекции (выполняется единожды в run())
        self._should_introspect = False

    def run(self) -> None:
        """Открытие камеры и цикл чтения кадров."""
        cap = cv2.VideoCapture(self._camera_index, default_backend())
        if not cap.isOpened():
            message = f"Не удалось открыть камеру {self._camera_index}"
            logger.error(message)
            self.error_occurred.emit(message)
            return

        cap.set(cv2.CAP_PROP_FOURCC, _fourcc_to_int(self._fourcc))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        cap.set(cv2.CAP_PROP_FPS, self._fps)

        with QMutexLocker(self._mutex):
            self._running = True
        self.started_capture.emit()
        logger.info(
            "Камера %d открыта: %dx%d @ %g fps, fourcc=%s",
            self._camera_index,
            self._width,
            self._height,
            self._fps,
            self._fourcc,
        )

        consecutive_failures = 0
        try:
            while self._is_running():
                self._drain_pending_props(cap)
                self._maybe_introspect(cap)
                ret, frame = cap.read()
                if not ret or frame is None:
                    consecutive_failures += 1
                    if consecutive_failures >= _MAX_CONSECUTIVE_READ_FAILURES:
                        message = "Камера отключилась"
                        logger.error(
                            "%s после %d подряд неудачных cap.read()",
                            message,
                            consecutive_failures,
                        )
                        self.error_occurred.emit(message)
                        return
                    continue
                consecutive_failures = 0
                self.frame_ready.emit(frame, time.monotonic())
        finally:
            cap.release()
            logger.info("Камера %d закрыта", self._camera_index)

    def stop(self) -> None:
        """Остановка цикла захвата и ожидание завершения потока."""
        with QMutexLocker(self._mutex):
            self._running = False
        self.wait()

    def set_property(self, prop: CameraProperty, value: float) -> None:
        """Постановка UVC-параметра в очередь применения (thread-safe).

        Применение произойдёт в run() между чтениями кадров.

        Args:
            prop: идентификатор параметра.
            value: целевое значение.
        """
        with QMutexLocker(self._mutex):
            self._pending_props.append((prop, value))

    def request_introspection(self) -> None:
        """Запрос разовой интроспекции UVC-параметров (thread-safe).

        Поднимает флаг; в ближайшей итерации run() будет вычислен набор
        поддерживаемых параметров и их текущие значения, после чего эмитнется
        сигнал properties_introspected с dict[CameraProperty, float].
        """
        with QMutexLocker(self._mutex):
            self._should_introspect = True

    def _is_running(self) -> bool:
        """Чтение флага _running под мьютексом."""
        with QMutexLocker(self._mutex):
            return self._running

    def _drain_pending_props(self, cap: cv2.VideoCapture) -> None:
        """Применение всех отложенных UVC-параметров к открытому capture.

        Забирает накопленные пары (prop, value) из очереди и применяет к cap.
        """
        with QMutexLocker(self._mutex):
            pending = self._pending_props
            self._pending_props = []
        for prop, value in pending:
            apply_property(cap, prop, value)

    def _maybe_introspect(self, cap: cv2.VideoCapture) -> None:
        """Разовая интроспекция supported + read для всех параметров.

        Если флаг _should_introspect взведён, собирает значения
        поддерживаемых параметров и эмитит properties_introspected.
        Флаг сбрасывается в любом случае, чтобы не зацикливаться.
        """
        with QMutexLocker(self._mutex):
            if not self._should_introspect:
                return
            self._should_introspect = False
        supported = supported_properties(cap)
        snapshot: dict[CameraProperty, float] = {
            prop: read_property(cap, prop) for prop in supported
        }
        self.properties_introspected.emit(snapshot)
