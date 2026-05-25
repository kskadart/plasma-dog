"""Тесты для camera/properties.py: per-property диапазоны и платформозависимые auto-значения."""

from __future__ import annotations

import pytest

from plasma_dog.camera.properties import (
    CameraProperty,
    auto_property_values,
    property_default,
    property_range,
)


def test_property_range_wb_temperature_returns_kelvin() -> None:
    """WB_TEMPERATURE должен иметь диапазон в кельвинах, не -100..100."""
    rng = property_range(CameraProperty.WB_TEMPERATURE)
    assert rng is not None
    min_k, max_k = rng
    assert 2000 <= min_k <= 3500
    assert 5500 <= max_k <= 8000


def test_property_range_brightness_is_symmetric_around_zero() -> None:
    """BRIGHTNESS — симметричный диапазон вокруг нуля (UVC normalized)."""
    rng = property_range(CameraProperty.BRIGHTNESS)
    assert rng is not None
    min_v, max_v = rng
    assert min_v < 0 < max_v
    assert min_v == -max_v


def test_property_range_exposure_returns_uvc_log_stops() -> None:
    """EXPOSURE — UVC log2 stops, отрицательный диапазон."""
    rng = property_range(CameraProperty.EXPOSURE)
    assert rng is not None
    min_v, max_v = rng
    assert min_v < 0
    assert max_v <= 0


def test_property_range_gain_is_positive_only() -> None:
    """GAIN — UVC gain неотрицательный."""
    rng = property_range(CameraProperty.GAIN)
    assert rng is not None
    min_v, _ = rng
    assert min_v >= 0


def test_property_range_focus_is_positive_only() -> None:
    """FOCUS — расстояние фокусировки неотрицательное."""
    rng = property_range(CameraProperty.FOCUS)
    assert rng is not None
    min_v, _ = rng
    assert min_v >= 0


@pytest.mark.parametrize(
    "prop",
    [
        CameraProperty.FRAME_WIDTH,
        CameraProperty.FRAME_HEIGHT,
        CameraProperty.FPS,
        CameraProperty.FOURCC,
        CameraProperty.AUTO_EXPOSURE,
        CameraProperty.AUTO_WB,
        CameraProperty.AUTOFOCUS,
    ],
)
def test_property_range_readonly_and_auto_return_none(prop: CameraProperty) -> None:
    """Readonly-параметры и auto-чекбоксы не имеют слайдер-диапазона."""
    assert property_range(prop) is None


def test_auto_property_values_exposure_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    """На Linux V4L2 AUTO_EXPOSURE использует 1=manual, 3=auto (V4L2 enum)."""
    monkeypatch.setattr("sys.platform", "linux")
    manual, auto = auto_property_values(CameraProperty.AUTO_EXPOSURE)
    assert manual == 1.0
    assert auto == 3.0


def test_auto_property_values_exposure_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """На Windows DirectShow AUTO_EXPOSURE использует 0=manual, 1=auto."""
    monkeypatch.setattr("sys.platform", "win32")
    manual, auto = auto_property_values(CameraProperty.AUTO_EXPOSURE)
    assert manual == 0.0
    assert auto == 1.0


def test_auto_property_values_exposure_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    """На macOS AVFoundation AUTO_EXPOSURE использует 0=manual, 1=auto."""
    monkeypatch.setattr("sys.platform", "darwin")
    manual, auto = auto_property_values(CameraProperty.AUTO_EXPOSURE)
    assert manual == 0.0
    assert auto == 1.0


@pytest.mark.parametrize("prop", [CameraProperty.AUTO_WB, CameraProperty.AUTOFOCUS])
@pytest.mark.parametrize("platform", ["linux", "win32", "darwin"])
def test_auto_property_values_wb_and_focus_universal(
    monkeypatch: pytest.MonkeyPatch,
    prop: CameraProperty,
    platform: str,
) -> None:
    """AUTO_WB и AUTOFOCUS используют 0=manual, 1=auto на всех платформах."""
    monkeypatch.setattr("sys.platform", platform)
    manual, auto = auto_property_values(prop)
    assert manual == 0.0
    assert auto == 1.0


def test_property_default_wb_temperature_is_neutral() -> None:
    """WB_TEMPERATURE default — нейтральный белый около 4500-5000K."""
    value = property_default(CameraProperty.WB_TEMPERATURE)
    assert value is not None
    assert 4500 <= value <= 5000


def test_property_default_brightness_is_zero() -> None:
    """BRIGHTNESS default — нейтральный 0 (симметричный UVC-диапазон)."""
    value = property_default(CameraProperty.BRIGHTNESS)
    assert value == 0.0


def test_property_default_zoom_is_100_percent() -> None:
    """ZOOM default — 100% (без зума)."""
    value = property_default(CameraProperty.ZOOM)
    assert value == 100.0


@pytest.mark.parametrize(
    "prop",
    [
        CameraProperty.FPS,
        CameraProperty.FOURCC,
        CameraProperty.FRAME_WIDTH,
        CameraProperty.FRAME_HEIGHT,
    ],
)
def test_property_default_returns_none_for_readonly(prop: CameraProperty) -> None:
    """Readonly-параметры (FPS/FOURCC/FRAME_*) не имеют дефолта для Reset."""
    assert property_default(prop) is None
