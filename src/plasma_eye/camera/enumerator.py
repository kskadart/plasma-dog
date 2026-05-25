"""Перебор доступных UVC-камер через cv2.VideoCapture."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import cv2.utils.logging as cv2_logging

from plasma_eye.camera.properties import default_backend

# Диапазон сканирования для платформ без явного списка устройств
_DARWIN_MAX_INDEX = 3
_WINDOWS_MAX_INDEX = 10
_GENERIC_MAX_INDEX = 3
# Лимит подряд идущих неудач для early-exit на index-based сканах
_MAX_CONSECUTIVE_FAILURES = 2
# Регулярка извлечения номера устройства из /dev/videoN
_LINUX_VIDEO_DEVICE_RE = re.compile(r"video(\d+)$")
_LINUX_DEV_DIR = Path("/dev")


@dataclass(frozen=True, slots=True)
class CameraInfo:
    """Метаданные доступной камеры.

    Attributes:
        index: системный индекс камеры (cv2.VideoCapture(index)).
        name: человекочитаемое имя (на UVC обычно "Camera N").
        backend: cv2-идентификатор используемого backend.
    """

    index: int
    name: str
    backend: int


def list_cameras() -> list[CameraInfo]:
    """Перечисление UVC-камер платформо-специфично.

    На macOS (AVFoundation) и обобщённой платформе используется короткий
    index scan 0..3 с early-exit. На Windows (DirectShow) — 0..10. На Linux
    список устройств читается из /dev/video* без сканирования индексов.

    Returns:
        Список CameraInfo для каждого доступного устройства.
    """
    platform: str = sys.platform
    if platform == "darwin":
        return _list_cameras_darwin()
    if platform == "linux":
        return _list_cameras_linux()
    if platform == "win32":
        return _list_cameras_windows()
    return _list_cameras_generic()


def _list_cameras_darwin() -> list[CameraInfo]:
    """Enumeration на macOS: index scan 0..3 с early-exit.

    AVFoundation редко выдаёт больше 2-3 камер (built-in + USB).
    """
    return _index_scan(_DARWIN_MAX_INDEX, _MAX_CONSECUTIVE_FAILURES)


def _list_cameras_windows() -> list[CameraInfo]:
    """Enumeration на Windows: index scan 0..10 с early-exit.

    DirectShow не предоставляет удобного API для enumeration.
    """
    return _index_scan(_WINDOWS_MAX_INDEX, _MAX_CONSECUTIVE_FAILURES)


def _list_cameras_generic() -> list[CameraInfo]:
    """Fallback enumeration для неизвестных платформ: короткий index scan."""
    return _index_scan(_GENERIC_MAX_INDEX, _MAX_CONSECUTIVE_FAILURES)


def _list_cameras_linux() -> list[CameraInfo]:
    """Enumeration на Linux: чтение /dev/video* + верификация через cv2.

    Если /dev/ недоступен (контейнер без проброса), fallback на generic scan.

    Returns:
        Список CameraInfo для устройств, которые реально открылись.
    """
    if not _LINUX_DEV_DIR.is_dir():
        return _list_cameras_generic()
    backend = default_backend()
    cameras: list[CameraInfo] = []
    previous_log_level = cv2_logging.getLogLevel()
    cv2_logging.setLogLevel(cv2_logging.LOG_LEVEL_ERROR)
    try:
        for path in sorted(_LINUX_DEV_DIR.glob("video*")):
            match = _LINUX_VIDEO_DEVICE_RE.match(path.name)
            if match is None:
                continue
            index = int(match.group(1))
            if not _try_open(index, backend):
                continue
            cameras.append(CameraInfo(index=index, name=f"Camera {index}", backend=backend))
    finally:
        cv2_logging.setLogLevel(previous_log_level)
    return cameras


def _index_scan(max_index: int, max_consecutive_failures: int) -> list[CameraInfo]:
    """Универсальный index-based scan с early-exit.

    Args:
        max_index: максимальный индекс (включительно), который проверяется.
        max_consecutive_failures: после стольких подряд неудач сканирование
            прекращается (защита от долгого ожидания на хабах).

    Returns:
        Список CameraInfo для каждого индекса, который открылся.
    """
    backend = default_backend()
    cameras: list[CameraInfo] = []
    consecutive_failures = 0
    previous_log_level = cv2_logging.getLogLevel()
    cv2_logging.setLogLevel(cv2_logging.LOG_LEVEL_ERROR)
    try:
        for index in range(max_index + 1):
            if _try_open(index, backend):
                cameras.append(CameraInfo(index=index, name=f"Camera {index}", backend=backend))
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    break
    finally:
        cv2_logging.setLogLevel(previous_log_level)
    return cameras


def _try_open(index: int, backend: int) -> bool:
    """Проверка, что cv2.VideoCapture успешно открывается на заданном индексе.

    Args:
        index: индекс камеры для cv2.VideoCapture.
        backend: backend-идентификатор cv2.

    Returns:
        True, если cap.isOpened() вернул True.
    """
    cap = cv2.VideoCapture(index, backend)
    opened = cap.isOpened()
    cap.release()
    return opened
