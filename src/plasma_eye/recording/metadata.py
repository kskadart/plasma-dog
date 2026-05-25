"""Метаданные сессии записи: snapshot параметров камеры + статистика."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from plasma_eye.const import FrameFormat

# Имя файла метаданных в session-папке
METADATA_FILENAME = "metadata.json"


@dataclass
class RecordingMetadata:
    """Метаданные сессии записи для научной воспроизводимости.

    Attributes:
        session_path: абсолютный путь к session-папке.
        started_at: момент старта записи.
        stopped_at: момент остановки; None пока запись идёт.
        camera_index: индекс камеры в системе.
        width: ширина кадра в пикселях.
        height: высота кадра в пикселях.
        target_fps: целевой fps, заданный при настройке захвата.
        fourcc: FOURCC код, использованный для cv2.VideoCapture.
        frame_format: формат сохранения отдельных кадров.
        camera_properties: snapshot UVC-параметров на момент старта.
        frames_written: фактическое число записанных кадров в видео.
        frames_dropped: число дропов (video + frame_saver).
        actual_fps: измеренный fps, посчитанный при stop().
    """

    session_path: Path
    started_at: datetime
    camera_index: int
    width: int
    height: int
    target_fps: float
    fourcc: str
    frame_format: FrameFormat
    camera_properties: dict[str, float] = field(default_factory=dict)
    stopped_at: datetime | None = None
    frames_written: int = 0
    frames_dropped: int = 0
    actual_fps: float = 0.0

    def to_json(self) -> str:
        """Сериализация в JSON с человекочитаемым отступом.

        Returns:
            Строка JSON с UTF-8 текстом, без ASCII-эскейпа.
        """
        return json.dumps(asdict(self), default=str, indent=2, ensure_ascii=False)


def write_metadata(metadata: RecordingMetadata, session_path: Path) -> None:
    """Сохранение metadata.json в session-папке.

    Args:
        metadata: объект метаданных для сериализации.
        session_path: путь к session-папке, куда писать файл.
    """
    target = session_path / METADATA_FILENAME
    target.write_text(metadata.to_json(), encoding="utf-8")
