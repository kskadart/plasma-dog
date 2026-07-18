"""Тесты чистой логики compute_thresholds (без Qt и данных из data/)."""

from __future__ import annotations

import numpy as np
import pytest

from plasma_dog.detection.calibration import compute_thresholds
from plasma_dog.exceptions import CalibrationError

# Хорошо разделимые выборки: "погасло" низко, "пламя" высоко, между ними зазор.
_FLAME_FRACS = [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]
_POGASLO_FRACS = [0.15, 0.16, 0.17, 0.18, 0.19, 0.20]


def test_compute_thresholds_clean_gap_orders_within_gap() -> None:
    """Разделимые выборки -> оба порога лежат строго внутри зазора p95..p5."""
    thr_low, thr_high = compute_thresholds(_FLAME_FRACS, _POGASLO_FRACS)
    pog_high = float(np.percentile(_POGASLO_FRACS, 95))
    flame_low = float(np.percentile(_FLAME_FRACS, 5))
    assert pog_high < thr_low < thr_high < flame_low
    assert thr_low < thr_high


def test_compute_thresholds_overlapping_samples_raises() -> None:
    """Пересекающиеся выборки (зазор <= 0) -> CalibrationError."""
    flame_fracs = [0.20, 0.25, 0.30, 0.35]
    pogaslo_fracs = [0.25, 0.30, 0.35, 0.40]
    with pytest.raises(CalibrationError):
        compute_thresholds(flame_fracs, pogaslo_fracs)


def test_compute_thresholds_empty_flame_raises() -> None:
    """Пустая выборка "пламя" -> CalibrationError."""
    with pytest.raises(CalibrationError):
        compute_thresholds([], _POGASLO_FRACS)


def test_compute_thresholds_empty_pogaslo_raises() -> None:
    """Пустая выборка "погасло" -> CalibrationError."""
    with pytest.raises(CalibrationError):
        compute_thresholds(_FLAME_FRACS, [])


def test_compute_thresholds_larger_margin_narrows_band() -> None:
    """Больший margin даёт более узкий диапазон [thr_low, thr_high]."""
    low_wide, high_wide = compute_thresholds(_FLAME_FRACS, _POGASLO_FRACS, margin=0.1)
    low_narrow, high_narrow = compute_thresholds(_FLAME_FRACS, _POGASLO_FRACS, margin=0.4)
    assert (high_narrow - low_narrow) < (high_wide - low_wide)
