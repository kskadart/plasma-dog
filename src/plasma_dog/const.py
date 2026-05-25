"""Константы приложения plasma-dog."""

from enum import StrEnum
from pathlib import Path

# Идентификация приложения для QSettings
APP_NAME = "plasma-dog"
ORG_NAME = "plasma-dog"

# Параметры захвата по умолчанию
DEFAULT_FPS = 30
DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
DEFAULT_FOURCC = "MJPG"  # быстрее YUYV на USB UVC

# Параметры записи
DEFAULT_RECORDINGS_DIR = Path.home() / "recordings" / APP_NAME
DEFAULT_TIMER_SECONDS = 60
DEFAULT_HOTKEY = "Ctrl+R"

# PNG compression: 0 (без сжатия, быстро) - 9 (макс. сжатие, медленно)
DEFAULT_PNG_COMPRESSION = 1
DEFAULT_JPG_QUALITY = 95

# Лимиты очередей и пулов
VIDEO_QUEUE_MAXSIZE = 30
FRAME_SAVER_QUEUE_THRESHOLD = 60  # порог дропа фреймов


class FrameFormat(StrEnum):
    """Формат сохранения отдельных кадров на диск."""

    PNG = "png"
    JPG = "jpg"
    BMP = "bmp"


class VideoCodec(StrEnum):
    """Поддерживаемые видео-кодеки для записи сессии."""

    H264 = "h264"  # avc1 в .mp4, рекомендуется для научных задач
    MP4V = "mp4v"  # MPEG-4 Part 2 в .mp4, fallback
    MJPG = "mjpg"  # Motion JPEG в .avi, без межкадрового сжатия
    VP9 = "vp9"  # VP9 в .webm, открытый стандарт


DEFAULT_VIDEO_CODEC = VideoCodec.H264

# Маппинг кодека на fourcc-строку для cv2.VideoWriter
_CODEC_TO_FOURCC: dict[VideoCodec, str] = {
    VideoCodec.H264: "avc1",
    VideoCodec.MP4V: "mp4v",
    VideoCodec.MJPG: "MJPG",
    VideoCodec.VP9: "VP90",
}

# Контейнер для каждого кодека (определяет расширение видео-файла)
_CODEC_TO_EXTENSION: dict[VideoCodec, str] = {
    VideoCodec.H264: "mp4",
    VideoCodec.MP4V: "mp4",
    VideoCodec.MJPG: "avi",
    VideoCodec.VP9: "webm",
}

# Человекочитаемые названия для UI (QComboBox)
_CODEC_DISPLAY_NAMES: dict[VideoCodec, str] = {
    VideoCodec.H264: "H.264 (.mp4) - рекомендуется",
    VideoCodec.MP4V: "MPEG-4 (.mp4)",
    VideoCodec.MJPG: "Motion JPEG (.avi)",
    VideoCodec.VP9: "VP9 / WebM (.webm)",
}


def codec_fourcc(codec: VideoCodec) -> str:
    """FOURCC код для cv2.VideoWriter.

    Args:
        codec: кодек из перечисления VideoCodec.

    Returns:
        4-символьная строка fourcc для cv2.VideoWriter.fourcc.
    """
    return _CODEC_TO_FOURCC[codec]


def codec_extension(codec: VideoCodec) -> str:
    """Расширение видео-файла (без точки).

    Args:
        codec: кодек из перечисления VideoCodec.

    Returns:
        Расширение файла-контейнера (mp4/avi/webm).
    """
    return _CODEC_TO_EXTENSION[codec]


def codec_display_name(codec: VideoCodec) -> str:
    """Человекочитаемое название для QComboBox.

    Args:
        codec: кодек из перечисления VideoCodec.

    Returns:
        Локализованная строка для отображения в UI.
    """
    return _CODEC_DISPLAY_NAMES[codec]
