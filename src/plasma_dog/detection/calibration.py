"""Вычисление порогов гистерезиса CV-детектора горения из калибровочных выборок.

Пользователь собирает две выборки доли яркой кляксы (blob_fraction): в состоянии
"пламя горит" и в состоянии "погасло". По перцентилям этих выборок вычисляется
зазор между состояниями и внутри него — пара порогов гистерезиса детектора.
Модуль не зависит от Qt.
"""

from __future__ import annotations

import logging

import numpy as np

from plasma_dog.exceptions import CalibrationError

logger = logging.getLogger(__name__)


def compute_thresholds(
    flame_fracs: list[float],
    pogaslo_fracs: list[float],
    margin: float = 0.25,
) -> tuple[float, float]:
    """Пороги гистерезиса из калибровочных выборок доли кляксы двух состояний.

    Args:
        flame_fracs: доли яркой кляксы (0..1) в состоянии "пламя горит".
        pogaslo_fracs: доли в состоянии "погасло".
        margin: отступ внутрь зазора с каждой стороны, доля зазора (0 <= margin < 0.5).

    Returns:
        Кортеж (thr_low, thr_high): нижний порог ближе к "погасло", верхний к "горит".

    Raises:
        CalibrationError: если выборки пусты или состояния не разделяются (зазор <= 0).
    """
    if not flame_fracs or not pogaslo_fracs:
        raise CalibrationError("нужны выборки обоих состояний")
    flame_low = float(np.percentile(flame_fracs, 5))
    pog_high = float(np.percentile(pogaslo_fracs, 95))
    gap = flame_low - pog_high
    if gap <= 0:
        raise CalibrationError(
            "состояния не разделяются: p95(погасло)=" f"{pog_high:.3f} >= p5(пламя)={flame_low:.3f}"
        )
    thr_low = pog_high + margin * gap
    thr_high = flame_low - margin * gap
    return (thr_low, thr_high)
