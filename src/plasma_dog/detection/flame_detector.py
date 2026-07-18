"""FlameDetector: классический CV-детектор горения плазмы (opencv + numpy).

Детектор оценивает долю кадра, занятую крупнейшей яркой кляксой (Otsu-порог по
размытой яркости), и по этой доле определяет состояние горелки. Смена состояния
защищена гистерезисом (две границы порога) и сглаживанием (подтверждение по
нескольким подряд идущим кадрам), чтобы одиночные выбросы не переключали статус.
Модуль не зависит от Qt и от папки ml/.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

from plasma_dog.const import (
    DEFAULT_FLAME_BLOB_THR_HIGH,
    DEFAULT_FLAME_BLOB_THR_LOW,
    DEFAULT_FLAME_CONFIRM_FRAMES,
    FlameState,
)

logger = logging.getLogger(__name__)

# Ядро размытия перед Otsu: гасит шум и мелкие блики, оставляя крупную кляксу.
# Пороги откалиброваны под full-res кадр с этим ядром, кадр НЕ даунскейлить.
_BLUR_KERNEL = (31, 31)


def blob_fraction(bgr: np.ndarray) -> float:
    """Доля кадра, занятая крупнейшей яркой кляксой (Otsu).

    Кадр переводится в grayscale, размывается и бинаризуется порогом Otsu.
    Возвращается отношение площади крупнейшего внешнего контура к площади кадра.

    Args:
        bgr: numpy BGR-кадр (H x W x 3, uint8).

    Returns:
        Доля площади кадра в диапазоне 0.0..1.0; 0.0 если ярких клякс нет.
    """
    gray = cv2.GaussianBlur(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), _BLUR_KERNEL, 0)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return 0.0
    largest = max(cv2.contourArea(c) for c in cnts)
    return float(largest / (bgr.shape[0] * bgr.shape[1]))


class FlameDetector:
    """Детектор состояния горелки по доле яркой кляксы с гистерезисом.

    Держит текущее подтверждённое состояние и переключает его только когда
    доля кляксы уверенно пересекает одну из границ (thr_high -> BURNING,
    thr_low -> EXTINGUISHED) в течение confirm_frames подряд идущих кадров.
    Зона между thr_low и thr_high удерживает прежнее состояние (гистерезис).
    """

    def __init__(
        self,
        thr_low: float = DEFAULT_FLAME_BLOB_THR_LOW,
        thr_high: float = DEFAULT_FLAME_BLOB_THR_HIGH,
        confirm_frames: int = DEFAULT_FLAME_CONFIRM_FRAMES,
    ) -> None:
        """Инициализация детектора с проверкой порогов.

        Args:
            thr_low: нижняя граница доли для перехода в EXTINGUISHED.
            thr_high: верхняя граница доли для перехода в BURNING.
            confirm_frames: число подряд идущих кадров для подтверждения смены
                состояния; приводится к минимуму 1.

        Raises:
            ValueError: если не выполнено 0 <= thr_low <= thr_high <= 1.
        """
        if not 0.0 <= thr_low <= thr_high <= 1.0:
            raise ValueError(
                "Пороги детектора должны удовлетворять 0 <= thr_low <= thr_high <= 1, "
                f"получено thr_low={thr_low}, thr_high={thr_high}"
            )
        self._thr_low = thr_low
        self._thr_high = thr_high
        self._confirm_frames = max(1, confirm_frames)
        self._state: FlameState = FlameState.UNKNOWN
        self._pending: FlameState | None = None
        self._pending_count = 0
        self._last_fraction = 0.0

    @property
    def state(self) -> FlameState:
        """Текущее подтверждённое состояние горелки."""
        return self._state

    @property
    def last_fraction(self) -> float:
        """Доля кляксы, вычисленная на последнем вызове update()."""
        return self._last_fraction

    def reset(self) -> None:
        """Сброс состояния и накопителей подтверждения в начальное (UNKNOWN)."""
        self._state = FlameState.UNKNOWN
        self._pending = None
        self._pending_count = 0
        self._last_fraction = 0.0

    def update(self, bgr: np.ndarray) -> FlameState:
        """Обработка очередного кадра и возврат актуального состояния.

        Args:
            bgr: numpy BGR-кадр (H x W x 3, uint8).

        Returns:
            Текущее подтверждённое состояние горелки после обработки кадра.
        """
        frac = blob_fraction(bgr)
        self._last_fraction = frac
        if frac >= self._thr_high:
            candidate = FlameState.BURNING
        elif frac <= self._thr_low:
            candidate = FlameState.EXTINGUISHED
        else:
            candidate = self._state  # зона гистерезиса -> держим прежнее
        if candidate == self._state or candidate == FlameState.UNKNOWN:
            self._pending = None
            self._pending_count = 0
            return self._state
        if candidate == self._pending:
            self._pending_count += 1
        else:
            self._pending = candidate
            self._pending_count = 1
        if self._pending_count >= self._confirm_frames:  # подтверждение по N кадрам
            self._state = candidate
            self._pending = None
            self._pending_count = 0
        return self._state
