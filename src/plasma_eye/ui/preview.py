"""Виджет live-превью кадров с камеры: numpy BGR -> QImage -> QPixmap."""

from __future__ import annotations

import cv2
import numpy as np
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QLabel, QWidget

# Минимальный размер виджета (640x360 = 16:9)
_MIN_WIDTH = 640
_MIN_HEIGHT = 360


class PreviewWidget(QLabel):
    """QLabel с отрисовкой numpy BGR кадров через QImage + QPixmap.

    При обновлении кадра делается BGR->RGB конверсия, масштабирование
    под текущий размер виджета с сглаживанием. Без кадра показывается
    placeholder-текст.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(_MIN_WIDTH, _MIN_HEIGHT)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setScaledContents(False)
        self.setText("Камера не подключена")
        # последний полученный кадр для перерисовки на resize
        self._last_frame: np.ndarray | None = None

    @pyqtSlot(object, float)
    def update_frame(self, frame: np.ndarray, timestamp: float) -> None:
        """Получение нового кадра от CaptureThread и отрисовка.

        Args:
            frame: numpy BGR кадр (uint8, shape HxWx3).
            timestamp: время кадра в секундах (time.monotonic()).
        """
        del timestamp  # пока не используется, нужен для совместимости сигнала
        self._last_frame = frame
        self._render(frame)

    def resizeEvent(self, event: object) -> None:
        """Перерисовка последнего кадра при изменении размера виджета."""
        super().resizeEvent(event)  # type: ignore[arg-type]
        if self._last_frame is not None:
            self._render(self._last_frame)

    def _render(self, frame: np.ndarray) -> None:
        """Конверсия BGR->RGB, упаковка в QImage/QPixmap, масштабирование."""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, _ = rgb.shape
        stride = int(rgb.strides[0])
        image = QImage(
            bytes(rgb.data),
            width,
            height,
            stride,
            QImage.Format.Format_RGB888,
        )
        pixmap = QPixmap.fromImage(image)
        scaled = pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)
