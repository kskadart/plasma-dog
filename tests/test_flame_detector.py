"""Тесты чистой логики FlameDetector и blob_fraction (без Qt и данных из data/)."""

from __future__ import annotations

import numpy as np
import pytest

from plasma_dog.const import FlameState
from plasma_dog.detection.flame_detector import FlameDetector, blob_fraction

# Размер синтетического кадра: заметно больше ядра размытия 31x31, чтобы
# после GaussianBlur+Otsu контур крупного блока находился надёжно.
_FRAME_SIZE = 400


def _frame_with_white_block(frame_size: int, block_size: int) -> np.ndarray:
    """Чёрный BGR-кадр с центрированным сплошным белым квадратом.

    Args:
        frame_size: сторона квадратного кадра в пикселях.
        block_size: сторона белого квадрата в пикселях (0 -> полностью чёрный кадр).

    Returns:
        numpy BGR-кадр uint8 (frame_size x frame_size x 3).
    """
    frame = np.zeros((frame_size, frame_size, 3), dtype=np.uint8)
    if block_size > 0:
        offset = (frame_size - block_size) // 2
        frame[offset : offset + block_size, offset : offset + block_size] = 255
    return frame


def _feed(detector: FlameDetector, frame: np.ndarray, count: int) -> None:
    """Подача одного и того же кадра в детектор count раз.

    Args:
        detector: экземпляр детектора.
        frame: numpy BGR кадр.
        count: число вызовов update().
    """
    for _ in range(count):
        detector.update(frame)


def test_blob_fraction_black_frame_returns_zero() -> None:
    """Полностью чёрный кадр не содержит ярких клякс -> доля ~= 0."""
    frame = _frame_with_white_block(_FRAME_SIZE, 0)
    assert blob_fraction(frame) < 0.01


def test_blob_fraction_large_block_returns_high() -> None:
    """Крупный белый блок занимает большую долю кадра."""
    frame = _frame_with_white_block(_FRAME_SIZE, 360)
    # 360x360 в 400x400 -> сырая доля ~0.81, после blur+Otsu остаётся высокой.
    assert blob_fraction(frame) > 0.5


def test_update_high_fraction_confirms_burning() -> None:
    """Серия кадров с долей выше thr_high подтверждает состояние BURNING."""
    detector = FlameDetector(thr_low=0.27, thr_high=0.34, confirm_frames=3)
    frame = _frame_with_white_block(_FRAME_SIZE, 360)
    _feed(detector, frame, 3)
    assert detector.state is FlameState.BURNING


def test_update_low_fraction_confirms_extinguished() -> None:
    """Серия кадров с долей ниже thr_low подтверждает состояние EXTINGUISHED."""
    detector = FlameDetector(thr_low=0.27, thr_high=0.34, confirm_frames=3)
    frame = _frame_with_white_block(_FRAME_SIZE, 0)
    _feed(detector, frame, 3)
    assert detector.state is FlameState.EXTINGUISHED


def test_update_gap_fraction_holds_state() -> None:
    """Кадр с долей в зазоре между low и high не меняет подтверждённое состояние."""
    # Широкие пороги делают зону гистерезиса надёжно достижимой синтетикой.
    detector = FlameDetector(thr_low=0.15, thr_high=0.8, confirm_frames=2)
    burning_frame = _frame_with_white_block(_FRAME_SIZE, 385)
    _feed(detector, burning_frame, 2)
    assert detector.state is FlameState.BURNING

    gap_frame = _frame_with_white_block(_FRAME_SIZE, 280)
    fraction = blob_fraction(gap_frame)
    assert 0.15 < fraction < 0.8  # доля действительно в зоне гистерезиса
    _feed(detector, gap_frame, 3)
    assert detector.state is FlameState.BURNING


def test_update_switch_requires_consecutive_frames() -> None:
    """Смена состояния требует confirm_frames подряд; прерывание сбрасывает счётчик."""
    detector = FlameDetector(thr_low=0.27, thr_high=0.34, confirm_frames=3)
    burning_frame = _frame_with_white_block(_FRAME_SIZE, 360)
    black_frame = _frame_with_white_block(_FRAME_SIZE, 0)

    _feed(detector, burning_frame, 3)
    assert detector.state is FlameState.BURNING

    # Один кадр нового состояния не переключает.
    detector.update(black_frame)
    assert detector.state is FlameState.BURNING

    # Прерывание кадром прежнего состояния сбрасывает накопитель подтверждения.
    detector.update(burning_frame)
    assert detector.state is FlameState.BURNING

    # После сброса снова нужны confirm_frames подряд.
    detector.update(black_frame)
    detector.update(black_frame)
    assert detector.state is FlameState.BURNING
    detector.update(black_frame)
    assert detector.state is FlameState.EXTINGUISHED


def test_init_thr_low_greater_than_high_raises_value_error() -> None:
    """thr_low больше thr_high нарушает инвариант порогов -> ValueError."""
    with pytest.raises(ValueError):
        FlameDetector(thr_low=0.5, thr_high=0.3)
