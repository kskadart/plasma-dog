"""AppSettings: персистентные настройки приложения поверх QSettings.

Хранение через нативный QSettings — на Linux в ~/.config/plasma-dog/plasma-dog.conf,
на Windows в реестре HKCU\\Software\\plasma-dog, на macOS в plist. Application/
Organization name выставляются в main.py до создания AppSettings.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from PyQt6.QtCore import QSettings

from plasma_dog.const import (
    DEFAULT_FPS,
    DEFAULT_HOTKEY,
    DEFAULT_JPG_QUALITY,
    DEFAULT_PNG_COMPRESSION,
    DEFAULT_RECORDINGS_DIR,
    DEFAULT_TIMER_SECONDS,
    DEFAULT_VIDEO_CODEC,
    FrameFormat,
    VideoCodec,
)

# Ключи QSettings
_KEY_RECORDINGS_DIR = "recording/dir"
_KEY_FRAME_FORMAT = "recording/frame_format"
_KEY_FRAME_QUALITY = "recording/frame_quality"
_KEY_VIDEO_CODEC = "recording/video_codec"
_KEY_RECORDING_FPS = "recording/fps"
_KEY_HOTKEY = "ui/hotkey_start_stop"
_KEY_TIMER_DEFAULT = "ui/timer_default_seconds"
_KEY_CAMERA_PROPS = "camera/properties_json"
_KEY_LAST_CAMERA_INDEX = "camera/last_index"
_KEY_CAMERA_PANEL_VISIBLE = "ui/camera_panel_visible"
_KEY_SPLITTER_SIZES = "ui/splitter_sizes"

T = TypeVar("T")


def default_frame_quality(fmt: FrameFormat) -> int:
    """Качество по умолчанию для заданного формата фрейма.

    PNG использует уровень компрессии 0..9, JPG — качество 1..100, BMP игнорирует.

    Args:
        fmt: формат фрейма.

    Returns:
        Дефолтное значение качества для этого формата.
    """
    if fmt is FrameFormat.JPG:
        return DEFAULT_JPG_QUALITY
    # PNG / BMP — используем PNG compression level
    return DEFAULT_PNG_COMPRESSION


class AppSettings:
    """Типобезопасная обёртка над QSettings со всеми пользовательскими настройками.

    Значения читаются/пишутся через свойства; для составных типов (Path, enum,
    dict) используется явная конверсия. Все ключи сгруппированы по префиксам.
    """

    def __init__(self) -> None:
        """Создание QSettings (использует APP_NAME/ORG_NAME из QApplication)."""
        self._qs = QSettings()

    # ---- recordings_dir ----

    @property
    def recordings_dir(self) -> Path:
        """Корневая папка, в которой создаются session-папки записи."""
        raw = self._qs.value(_KEY_RECORDINGS_DIR, str(DEFAULT_RECORDINGS_DIR))
        return Path(str(raw))

    @recordings_dir.setter
    def recordings_dir(self, value: Path) -> None:
        self._qs.setValue(_KEY_RECORDINGS_DIR, str(value))

    # ---- frame_format ----

    @property
    def frame_format(self) -> FrameFormat:
        """Формат сохранения отдельных кадров (PNG/JPG/BMP)."""
        raw = self._qs.value(_KEY_FRAME_FORMAT, FrameFormat.PNG.value)
        try:
            return FrameFormat(str(raw))
        except ValueError:
            return FrameFormat.PNG

    @frame_format.setter
    def frame_format(self, value: FrameFormat) -> None:
        self._qs.setValue(_KEY_FRAME_FORMAT, value.value)

    # ---- frame_quality ----

    @property
    def frame_quality(self) -> int:
        """Качество/уровень компрессии для фрейма (интерпретация на стороне saver)."""
        raw = self._qs.value(_KEY_FRAME_QUALITY)
        if raw is None:
            return default_frame_quality(self.frame_format)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default_frame_quality(self.frame_format)

    @frame_quality.setter
    def frame_quality(self, value: int) -> None:
        self._qs.setValue(_KEY_FRAME_QUALITY, int(value))

    # ---- video_codec ----

    @property
    def video_codec(self) -> VideoCodec:
        """Кодек видео-файла (H264/MP4V/MJPG/VP9)."""
        raw = self._qs.value(_KEY_VIDEO_CODEC, DEFAULT_VIDEO_CODEC.value)
        try:
            return VideoCodec(str(raw))
        except ValueError:
            return DEFAULT_VIDEO_CODEC

    @video_codec.setter
    def video_codec(self, value: VideoCodec) -> None:
        self._qs.setValue(_KEY_VIDEO_CODEC, value.value)

    # ---- recording_fps ----

    @property
    def recording_fps(self) -> float:
        """Желаемая частота кадров записи (поддерживает дробные значения)."""
        raw = self._qs.value(_KEY_RECORDING_FPS, float(DEFAULT_FPS))
        try:
            return float(raw)
        except (TypeError, ValueError):
            return float(DEFAULT_FPS)

    @recording_fps.setter
    def recording_fps(self, value: float) -> None:
        self._qs.setValue(_KEY_RECORDING_FPS, float(value))

    # ---- hotkey_start_stop ----

    @property
    def hotkey_start_stop(self) -> str:
        """Горячая клавиша запуска/остановки записи (например 'Ctrl+R')."""
        raw = self._qs.value(_KEY_HOTKEY, DEFAULT_HOTKEY)
        return str(raw)

    @hotkey_start_stop.setter
    def hotkey_start_stop(self, value: str) -> None:
        self._qs.setValue(_KEY_HOTKEY, value)

    # ---- timer_default_seconds ----

    @property
    def timer_default_seconds(self) -> int:
        """Значение по умолчанию для спинбокса таймера автостопа, в секундах."""
        raw = self._qs.value(_KEY_TIMER_DEFAULT, DEFAULT_TIMER_SECONDS)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return DEFAULT_TIMER_SECONDS

    @timer_default_seconds.setter
    def timer_default_seconds(self, value: int) -> None:
        self._qs.setValue(_KEY_TIMER_DEFAULT, int(value))

    # ---- camera_properties ----

    @property
    def camera_properties(self) -> dict[str, float]:
        """Последний сохранённый snapshot слайдеров камеры."""
        raw = self._qs.value(_KEY_CAMERA_PROPS)
        if raw is None:
            return {}
        try:
            parsed = json.loads(str(raw))
        except (json.JSONDecodeError, TypeError):
            return {}
        if not isinstance(parsed, dict):
            return {}
        result: dict[str, float] = {}
        for key, value in parsed.items():
            try:
                result[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
        return result

    @camera_properties.setter
    def camera_properties(self, value: dict[str, float]) -> None:
        self._qs.setValue(_KEY_CAMERA_PROPS, json.dumps(value))

    # ---- last_camera_index ----

    @property
    def last_camera_index(self) -> int | None:
        """Индекс последней выбранной камеры либо None, если не сохранён."""
        raw = self._qs.value(_KEY_LAST_CAMERA_INDEX)
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    @last_camera_index.setter
    def last_camera_index(self, value: int | None) -> None:
        if value is None:
            self._qs.remove(_KEY_LAST_CAMERA_INDEX)
            return
        self._qs.setValue(_KEY_LAST_CAMERA_INDEX, int(value))

    # ---- camera_panel_visible ----

    @property
    def camera_panel_visible(self) -> bool:
        """Видимость правой UVC-панели (default True при первом запуске)."""
        raw = self._qs.value(_KEY_CAMERA_PANEL_VISIBLE, True)
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.lower() in ("true", "1", "yes")
        return True

    @camera_panel_visible.setter
    def camera_panel_visible(self, value: bool) -> None:
        self._qs.setValue(_KEY_CAMERA_PANEL_VISIBLE, bool(value))

    # ---- splitter_sizes ----

    @property
    def splitter_sizes(self) -> list[int]:
        """Размеры [preview, panel] для QSplitter; пустой list если не сохранено."""
        raw = self._qs.value(_KEY_SPLITTER_SIZES, "")
        if not isinstance(raw, str) or not raw:
            return []
        try:
            parts = [int(s) for s in raw.split(",")]
        except ValueError:
            return []
        return parts if len(parts) == 2 else []

    @splitter_sizes.setter
    def splitter_sizes(self, value: list[int]) -> None:
        if not value:
            self._qs.setValue(_KEY_SPLITTER_SIZES, "")
            return
        self._qs.setValue(_KEY_SPLITTER_SIZES, ",".join(str(int(s)) for s in value))

    # ---- очистка ----

    def clear(self) -> None:
        """Полная очистка всех сохранённых настроек (возврат к дефолтам)."""
        self._qs.clear()
        self._qs.sync()
