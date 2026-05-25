"""Идентификаторы UVC-параметров камеры и хелперы доступа через cv2.CAP_PROP_*."""

from __future__ import annotations

import logging
import sys
from enum import StrEnum

import cv2

logger = logging.getLogger(__name__)

# Толерантность сравнения значения параметра с реально применённым.
_APPLY_VALUE_TOLERANCE = 0.5


class CameraProperty(StrEnum):
    """Идентификаторы свойств UVC-камеры, поддерживаемые приложением."""

    BRIGHTNESS = "brightness"
    CONTRAST = "contrast"
    SATURATION = "saturation"
    HUE = "hue"
    GAIN = "gain"
    EXPOSURE = "exposure"
    AUTO_EXPOSURE = "auto_exposure"
    WB_TEMPERATURE = "wb_temperature"
    AUTO_WB = "auto_wb"
    SHARPNESS = "sharpness"
    GAMMA = "gamma"
    BACKLIGHT = "backlight"
    FOCUS = "focus"
    AUTOFOCUS = "autofocus"
    ZOOM = "zoom"
    FRAME_WIDTH = "frame_width"
    FRAME_HEIGHT = "frame_height"
    FPS = "fps"
    FOURCC = "fourcc"


# Диапазоны слайдеров (min, max) для каждого UVC-параметра. Подобраны под
# типичные значения UVC-драйверов: WB в кельвинах, EXPOSURE в log2-stops,
# GAIN/FOCUS — положительные 8-битные значения и так далее. Конкретная камера
# может иметь другой реальный диапазон — OpenCV нормализует значение, но
# слайдер пользователя должен показывать осмысленную шкалу.
_PROPERTY_RANGES: dict[CameraProperty, tuple[int, int]] = {
    CameraProperty.BRIGHTNESS: (-100, 100),
    CameraProperty.CONTRAST: (-100, 100),
    CameraProperty.SATURATION: (-100, 100),
    CameraProperty.HUE: (-180, 180),
    CameraProperty.GAIN: (0, 255),
    CameraProperty.EXPOSURE: (-13, 0),
    CameraProperty.WB_TEMPERATURE: (2800, 6500),
    CameraProperty.SHARPNESS: (0, 100),
    CameraProperty.GAMMA: (50, 300),
    CameraProperty.BACKLIGHT: (0, 10),
    CameraProperty.FOCUS: (0, 255),
    CameraProperty.ZOOM: (100, 400),
}


# Разумные дефолты для слайдеров: применяются как fallback в Reset-кнопке UVC-панели,
# когда initial-значение текущей камеры неизвестно. EXPOSURE в log2-stops, WB в кельвинах,
# GAIN/SHARPNESS/GAMMA/ZOOM — нормализованные значения, см. _PROPERTY_RANGES.
_PROPERTY_DEFAULTS: dict[CameraProperty, float] = {
    CameraProperty.BRIGHTNESS: 0.0,
    CameraProperty.CONTRAST: 0.0,
    CameraProperty.SATURATION: 0.0,
    CameraProperty.HUE: 0.0,
    CameraProperty.GAIN: 0.0,
    CameraProperty.EXPOSURE: -6.0,
    CameraProperty.WB_TEMPERATURE: 4600.0,
    CameraProperty.SHARPNESS: 50.0,
    CameraProperty.GAMMA: 100.0,
    CameraProperty.BACKLIGHT: 0.0,
    CameraProperty.FOCUS: 0.0,
    CameraProperty.ZOOM: 100.0,
}


# Маппинг доменных идентификаторов на cv2.CAP_PROP_*
_CV_PROP_MAP: dict[CameraProperty, int] = {
    CameraProperty.BRIGHTNESS: cv2.CAP_PROP_BRIGHTNESS,
    CameraProperty.CONTRAST: cv2.CAP_PROP_CONTRAST,
    CameraProperty.SATURATION: cv2.CAP_PROP_SATURATION,
    CameraProperty.HUE: cv2.CAP_PROP_HUE,
    CameraProperty.GAIN: cv2.CAP_PROP_GAIN,
    CameraProperty.EXPOSURE: cv2.CAP_PROP_EXPOSURE,
    CameraProperty.AUTO_EXPOSURE: cv2.CAP_PROP_AUTO_EXPOSURE,
    CameraProperty.WB_TEMPERATURE: cv2.CAP_PROP_WB_TEMPERATURE,
    CameraProperty.AUTO_WB: cv2.CAP_PROP_AUTO_WB,
    CameraProperty.SHARPNESS: cv2.CAP_PROP_SHARPNESS,
    CameraProperty.GAMMA: cv2.CAP_PROP_GAMMA,
    CameraProperty.BACKLIGHT: cv2.CAP_PROP_BACKLIGHT,
    CameraProperty.FOCUS: cv2.CAP_PROP_FOCUS,
    CameraProperty.AUTOFOCUS: cv2.CAP_PROP_AUTOFOCUS,
    CameraProperty.ZOOM: cv2.CAP_PROP_ZOOM,
    CameraProperty.FRAME_WIDTH: cv2.CAP_PROP_FRAME_WIDTH,
    CameraProperty.FRAME_HEIGHT: cv2.CAP_PROP_FRAME_HEIGHT,
    CameraProperty.FPS: cv2.CAP_PROP_FPS,
    CameraProperty.FOURCC: cv2.CAP_PROP_FOURCC,
}


def default_backend() -> int:
    """Выбор cv2 backend по платформе.

    Returns:
        Идентификатор cv2.CAP_* backend для текущей ОС.
    """
    platform = sys.platform
    if platform == "win32":
        return cv2.CAP_DSHOW
    if platform == "linux":
        return cv2.CAP_V4L2
    if platform == "darwin":
        return cv2.CAP_AVFOUNDATION
    return cv2.CAP_ANY


def read_property(cap: cv2.VideoCapture, prop: CameraProperty) -> float:
    """Чтение значения UVC-параметра.

    Args:
        cap: открытый объект cv2.VideoCapture.
        prop: идентификатор параметра.

    Returns:
        Текущее значение параметра; -1, если параметр не поддерживается.
    """
    cv_prop = _CV_PROP_MAP[prop]
    return float(cap.get(cv_prop))


def apply_property(cap: cv2.VideoCapture, prop: CameraProperty, value: float) -> bool:
    """Установка значения UVC-параметра + верификация через обратное чтение.

    На macOS AVFoundation backend OpenCV для большинства UVC-параметров
    cap.set() возвращает True, но фактически параметр не меняется. После
    set() читаем обратно cap.get() и сравниваем с tolerance. При расхождении
    пишем warning в лог.

    Args:
        cap: открытый объект cv2.VideoCapture.
        prop: идентификатор параметра.
        value: новое значение.

    Returns:
        True, если cap.set() сообщил об успехе И cap.get() вернул близкое значение.
    """
    cv_prop = _CV_PROP_MAP[prop]
    result = bool(cap.set(cv_prop, value))
    actual = cap.get(cv_prop)
    applied = abs(actual - value) < _APPLY_VALUE_TOLERANCE
    if not applied:
        logger.warning(
            "apply %s=%.3f: cap.set=%s, но cap.get=%.3f — параметр не применён "
            "(возможно ограничение backend или камеры).",
            prop.value,
            value,
            result,
            actual,
        )
    return result and applied


def property_default(prop: CameraProperty) -> float | None:
    """Разумное дефолтное значение слайдера для UVC-параметра.

    Используется как fallback в Reset-кнопке UVC-панели, если initial-значение
    текущей камеры не было сохранено.

    Args:
        prop: идентификатор параметра.

    Returns:
        Дефолтное значение для редактируемых параметров. None для readonly-
        параметров (FPS/FOURCC/FRAME_WIDTH/FRAME_HEIGHT) и auto-чекбоксов.
    """
    return _PROPERTY_DEFAULTS.get(prop)


def property_range(prop: CameraProperty) -> tuple[int, int] | None:
    """Диапазон значений (min, max) слайдера для UVC-параметра.

    Args:
        prop: идентификатор параметра.

    Returns:
        Кортеж (min, max) для редактируемых слайдером параметров. None для
        readonly-параметров (FPS/FOURCC/FRAME_WIDTH/FRAME_HEIGHT) и для
        auto-чекбоксов (AUTO_EXPOSURE/AUTO_WB/AUTOFOCUS).
    """
    return _PROPERTY_RANGES.get(prop)


def auto_property_values(prop: CameraProperty) -> tuple[float, float]:
    """Значения (manual, auto) для auto-toggle параметра камеры.

    Платформозависимо для AUTO_EXPOSURE: V4L2 на Linux использует
    1=V4L2_EXPOSURE_MANUAL, 3=V4L2_EXPOSURE_APERTURE_PRIORITY (auto).
    На DirectShow (Windows) и AVFoundation (macOS) используется 0=manual,
    1=auto. AUTO_WB и AUTOFOCUS — 0/1 на всех платформах.

    Args:
        prop: идентификатор auto-параметра.

    Returns:
        Кортеж (manual_value, auto_value).
    """
    if prop == CameraProperty.AUTO_EXPOSURE and sys.platform == "linux":
        return (1.0, 3.0)
    return (0.0, 1.0)


def supported_properties(cap: cv2.VideoCapture) -> set[CameraProperty]:
    """Определение набора UVC-параметров, реально поддерживаемых камерой.

    Args:
        cap: открытый объект cv2.VideoCapture.

    Returns:
        Множество поддерживаемых параметров (где cap.get() вернул != -1).
    """
    supported: set[CameraProperty] = set()
    for prop, cv_prop in _CV_PROP_MAP.items():
        value = cap.get(cv_prop)
        if value != -1:
            supported.add(prop)
    return supported
