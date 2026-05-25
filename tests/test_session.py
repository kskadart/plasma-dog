"""Тесты RecordingSession: создание папок, metadata.json, проверка диска."""

from __future__ import annotations

import collections
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from plasma_dog.const import DEFAULT_VIDEO_CODEC, FrameFormat
from plasma_dog.recording.metadata import METADATA_FILENAME
from plasma_dog.recording.session import RecordingConfig, RecordingSession


def _make_config(tmp_path: Path) -> RecordingConfig:
    """Создание RecordingConfig с минимально-валидными параметрами для теста.

    Args:
        tmp_path: временный каталог фикстуры pytest.

    Returns:
        RecordingConfig с маленьким разрешением, чтобы тест шёл быстро.
    """
    return RecordingConfig(
        recordings_root=tmp_path / "recordings",
        width=64,
        height=48,
        fps=15,
        fourcc="MJPG",
        frame_format=FrameFormat.PNG,
        frame_quality=1,
        video_codec=DEFAULT_VIDEO_CODEC,
    )


def _make_frame(width: int = 64, height: int = 48) -> np.ndarray:
    """Создание numpy BGR-кадра нужного размера."""
    return np.zeros((height, width, 3), dtype=np.uint8)


@pytest.fixture(autouse=True)
def _silence_logging() -> None:
    """Глушение логов в тестах сессии."""
    import logging

    logging.getLogger("plasma_dog.recording").setLevel(logging.CRITICAL)


def test_session_creates_session_directory(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """start() создаёт session-папку и подпапку frames внутри recordings_root."""
    del qtbot  # фикстура нужна для QApplication
    config = _make_config(tmp_path)
    session = RecordingSession(config)

    session_path = session.start(camera_index=0, camera_props_snapshot={})
    assert session_path is not None
    assert session_path.exists()
    assert session_path.is_dir()
    assert (session_path / "frames").exists()
    assert session_path.parent == config.recordings_root

    session.stop()


def test_session_writes_metadata(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """После start->несколько on_frame->stop в metadata.json валидные поля."""
    del qtbot
    config = _make_config(tmp_path)
    session = RecordingSession(config)

    camera_props = {"brightness": 50.0, "exposure": -7.0}
    session_path = session.start(camera_index=2, camera_props_snapshot=camera_props)
    assert session_path is not None
    # Минимальный sleep, чтобы elapsed > 0
    time.sleep(0.05)

    for _ in range(3):
        session.on_frame(_make_frame(), time.monotonic())

    session.stop()

    metadata_file = session_path / METADATA_FILENAME
    assert metadata_file.exists()
    data: dict[str, Any] = json.loads(metadata_file.read_text(encoding="utf-8"))
    assert data["camera_index"] == 2
    assert data["width"] == 64
    assert data["height"] == 48
    assert data["target_fps"] == 15
    assert data["fourcc"] == "MJPG"
    assert data["frame_format"] == FrameFormat.PNG.value
    assert data["camera_properties"] == camera_props
    assert data["stopped_at"] is not None
    assert data["frames_written"] >= 0
    assert data["actual_fps"] >= 0


def test_session_disk_space_warning(
    qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    """При свободном месте < 100 MB start() возвращает None и эмитит error."""
    del qtbot
    config = _make_config(tmp_path)
    session = RecordingSession(config)

    # 50 MB свободно -> ниже фатального порога 100 MB
    FakeUsage = collections.namedtuple("FakeUsage", ["total", "used", "free"])
    monkeypatch.setattr(
        "plasma_dog.recording.session.shutil.disk_usage",
        lambda _path: FakeUsage(total=1_000_000_000, used=950_000_000, free=50 * 1024 * 1024),
    )

    captured_errors: list[str] = []
    session.error_occurred.connect(captured_errors.append)

    result = session.start(camera_index=0, camera_props_snapshot={})
    assert result is None
    assert len(captured_errors) == 1
    assert "Недостаточно свободного места" in captured_errors[0]
    assert not session.is_recording
