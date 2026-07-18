"""Тесты CalibrationDialog: живое превью/индикатор и сбор выборок в add_frame."""

from __future__ import annotations

import numpy as np

from plasma_dog.ui.calibration_dialog import _STATE_FLAME, CalibrationDialog

# Размер синтетического кадра: заметно больше ядра размытия 31x31, чтобы
# blob_fraction по крупному белому блоку возвращал устойчиво высокую долю.
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


def test_add_frame_during_flame_capture_appends_sample_and_updates_label(qapp) -> None:  # type: ignore[no-untyped-def]
    """При активном захвате "пламя" add_frame копит выборку и обновляет индикатор.

    Два кадра с разницей timestamp больше троттла _DISPLAY_INTERVAL_S оба
    попадают в выборку пламени, а текст индикатора получает процент.
    """
    del qapp  # требуется для инициализации QApplication
    dialog = CalibrationDialog()
    dialog._collecting = _STATE_FLAME

    frame = _frame_with_white_block(_FRAME_SIZE, 360)
    dialog.add_frame(frame, 0.0)
    dialog.add_frame(frame, 1.0)

    assert len(dialog._flame) == 2
    assert dialog._pogaslo == []
    assert "%" in dialog._current_label.text()


def test_add_frame_without_capture_updates_label_but_skips_samples(qapp) -> None:  # type: ignore[no-untyped-def]
    """Без активного захвата add_frame не копит выборки, но обновляет индикатор.

    Превью и индикатор текущей доли кляксы работают вне захвата, поэтому текст
    индикатора всё равно получает процент, а обе выборки остаются пустыми.
    """
    del qapp  # требуется для инициализации QApplication
    dialog = CalibrationDialog()
    assert dialog._collecting is None

    frame = _frame_with_white_block(_FRAME_SIZE, 360)
    dialog.add_frame(frame, 0.0)
    dialog.add_frame(frame, 1.0)

    assert dialog._flame == []
    assert dialog._pogaslo == []
    assert "%" in dialog._current_label.text()
