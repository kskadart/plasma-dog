"""Тесты FrameSaverPool: PNG/JPG запись, backpressure, счётчик."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

from plasma_dog.const import FRAME_SAVER_QUEUE_THRESHOLD, FrameFormat
from plasma_dog.recording.frame_saver import FrameSaverPool


def _make_frame(value: int = 0) -> np.ndarray:
    """Создание небольшого numpy BGR-кадра для теста.

    Args:
        value: значение интенсивности для всех пикселей.

    Returns:
        Кадр 100x100x3 uint8.
    """
    return np.full((100, 100, 3), value, dtype=np.uint8)


def _wait_until(predicate, timeout: float = 5.0) -> bool:  # type: ignore[no-untyped-def]
    """Поллинг условия до timeout (для ожидания фоновой записи)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_frame_saver_writes_png(tmp_path: Path) -> None:
    """5 PNG-кадров должны быть сохранены с инкрементными именами 000001..000005."""
    pool = FrameSaverPool(output_dir=tmp_path, fmt=FrameFormat.PNG, quality=1)
    for i in range(5):
        pool.submit(_make_frame(i * 10))
    pool.shutdown(wait=True)

    files = sorted(tmp_path.glob("*.png"))
    assert len(files) == 5
    expected_names = [f"{i:06d}.png" for i in range(1, 6)]
    assert [f.name for f in files] == expected_names
    assert pool.written == 5
    assert pool.dropped == 0


def test_frame_saver_writes_jpg(tmp_path: Path) -> None:
    """5 JPG-кадров с корректным расширением и нумерацией."""
    pool = FrameSaverPool(output_dir=tmp_path, fmt=FrameFormat.JPG, quality=85)
    for i in range(5):
        pool.submit(_make_frame(i * 10))
    pool.shutdown(wait=True)

    files = sorted(tmp_path.glob("*.jpg"))
    assert len(files) == 5
    assert [f.name for f in files] == [f"{i:06d}.jpg" for i in range(1, 6)]
    assert pool.written == 5


def test_frame_saver_writes_to_non_ascii_path(tmp_path: Path) -> None:
    """Кадры пишутся в путь с кириллицей (на Windows cv2.imwrite это не умеет).

    Регрессия на запись через imencode+tofile: файлы должны быть созданы и
    декодироваться обратно в корректное изображение.
    """
    out_dir = tmp_path / "Записи_Тест"
    out_dir.mkdir()
    pool = FrameSaverPool(output_dir=out_dir, fmt=FrameFormat.PNG, quality=1)
    for i in range(3):
        pool.submit(_make_frame(i * 10))
    pool.shutdown(wait=True)

    files = sorted(out_dir.glob("*.png"))
    assert [f.name for f in files] == [f"{i:06d}.png" for i in range(1, 4)]
    assert pool.written == 3
    assert pool.dropped == 0
    # чтение Unicode-safe способом (cv2.imread на Windows тоже не умеет не-ASCII)
    decoded = cv2.imdecode(np.fromfile(files[0], dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None
    assert decoded.shape == (100, 100, 3)


def test_frame_saver_backpressure(tmp_path: Path) -> None:
    """При быстром submit'е большой партии часть кадров должна быть дропнута.

    Используем 1 worker, чтобы гарантированно превысить порог inflight, и
    держим запись внутри _write через monkeypatch на медленную функцию.
    """
    pool = FrameSaverPool(output_dir=tmp_path, fmt=FrameFormat.PNG, quality=1, max_workers=1)

    # Удерживаем первого рабочего, чтобы очередь успела забиться
    block_event = threading.Event()
    release_event = threading.Event()
    original_write = pool._write

    def blocking_write(frame: np.ndarray, idx: int) -> None:
        if idx == 1:
            block_event.set()
            release_event.wait(timeout=10.0)
        original_write(frame, idx)

    pool._write = blocking_write  # type: ignore[method-assign]

    pool.submit(_make_frame(0))
    assert block_event.wait(timeout=2.0), "worker не стартовал"
    # Накидываем существенно больше FRAME_SAVER_QUEUE_THRESHOLD
    for _ in range(FRAME_SAVER_QUEUE_THRESHOLD * 3):
        pool.submit(_make_frame(1))

    release_event.set()
    pool.shutdown(wait=True)

    assert pool.dropped > 0, "ожидался хотя бы один дроп при переполнении"
    # счётчик увеличивается на каждый submit, включая дропы
    assert pool.counter == FRAME_SAVER_QUEUE_THRESHOLD * 3 + 1


def test_frame_saver_counter(tmp_path: Path) -> None:
    """counter инкрементируется на каждый submit (включая дропы)."""
    pool = FrameSaverPool(output_dir=tmp_path, fmt=FrameFormat.PNG, quality=1)
    assert pool.counter == 0
    for _ in range(7):
        pool.submit(_make_frame())
    pool.shutdown(wait=True)
    assert pool.counter == 7
    assert _wait_until(lambda: pool.written == 7)


@pytest.fixture(autouse=True)
def _silence_logging() -> None:
    """Глушение логов в тестах, чтобы dropped warnings не засоряли вывод."""
    import logging

    logging.getLogger("plasma_dog.recording.frame_saver").setLevel(logging.CRITICAL)
