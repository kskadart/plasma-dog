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
DEFAULT_CAMERA_MIRROR = True  # горизонтальное зеркалирование кадра по умолчанию

# Параметры записи
DEFAULT_RECORDINGS_DIR = Path.home() / "recordings" / APP_NAME
DEFAULT_TIMER_SECONDS = 60
DEFAULT_HOTKEY = "Ctrl+R"
DEFAULT_RECORDING_MODE = False  # режим записи выключен по умолчанию (кнопки записи скрыты)

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


class FlameState(StrEnum):
    """Состояние горелки, определённое детектором."""

    BURNING = "burning"  # пламя горит (норма)
    EXTINGUISHED = "extinguished"  # погасло (нарушение)
    UNKNOWN = "unknown"


# Параметры CV-детектора горения (гистерезис по доле яркой кляксы в кадре)
DEFAULT_FLAME_BLOB_THR_LOW = 0.27
DEFAULT_FLAME_BLOB_THR_HIGH = 0.34
DEFAULT_FLAME_CONFIRM_FRAMES = 3
DEFAULT_FLAME_INFER_HZ = 2.0
MIN_FLAME_INFER_HZ = 0.1  # нижняя граница частоты прогона (guard от деления на ноль)

# Ключи QSettings детектора горения
KEY_FLAME_BLOB_THR_LOW = "detector/blob_thr_low"
KEY_FLAME_BLOB_THR_HIGH = "detector/blob_thr_high"
KEY_FLAME_CONFIRM_FRAMES = "detector/confirm_frames"
KEY_FLAME_INFER_HZ = "detector/infer_hz"

# Ключ QSettings зеркалирования камеры
KEY_CAMERA_MIRROR = "camera/mirror"

# Ключ QSettings режима записи
KEY_RECORDING_MODE = "recording/mode_enabled"

# Параметры звуковой тревоги при погасшем пламени
DEFAULT_ALARM_ENABLED = True
DEFAULT_ALARM_SOUND_FILE = ""  # пусто -> бандл-дефолт resources/alarm_default.wav
DEFAULT_ALARM_VOLUME = 0.7  # базовая громкость, доля 0..1
DEFAULT_ALARM_HEARTBEAT_S = 5.0  # интервал повтора звука, с
DEFAULT_ALARM_ESCALATE = True  # нарастание громкости до максимума
DEFAULT_ALARM_ESCALATE_SECONDS = 20.0  # время нарастания до максимума, с

# Ключи QSettings звуковой тревоги
KEY_ALARM_ENABLED = "alarm/enabled"
KEY_ALARM_SOUND_FILE = "alarm/sound_file"
KEY_ALARM_VOLUME = "alarm/volume"
KEY_ALARM_HEARTBEAT = "alarm/heartbeat_s"
KEY_ALARM_ESCALATE = "alarm/escalate"
KEY_ALARM_ESCALATE_SECONDS = "alarm/escalate_s"
