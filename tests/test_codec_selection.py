"""Тесты для маппинга VideoCodec -> fourcc / extension / display name."""

from __future__ import annotations

from plasma_dog.const import (
    VideoCodec,
    codec_display_name,
    codec_extension,
    codec_fourcc,
)


def test_codec_h264_fourcc_is_avc1() -> None:
    """H.264 маппится в fourcc avc1 (нужен на macOS/AVFoundation)."""
    assert codec_fourcc(VideoCodec.H264) == "avc1"


def test_codec_vp9_fourcc_is_vp90() -> None:
    """VP9 маппится в fourcc VP90 (cv2 standard)."""
    assert codec_fourcc(VideoCodec.VP9) == "VP90"


def test_codec_h264_extension_is_mp4() -> None:
    """H.264 пишется в контейнер .mp4."""
    assert codec_extension(VideoCodec.H264) == "mp4"


def test_codec_vp9_extension_is_webm() -> None:
    """VP9 пишется в контейнер .webm."""
    assert codec_extension(VideoCodec.VP9) == "webm"


def test_codec_mjpg_extension_is_avi() -> None:
    """Motion JPEG пишется в контейнер .avi."""
    assert codec_extension(VideoCodec.MJPG) == "avi"


def test_codec_mp4v_extension_is_mp4() -> None:
    """MPEG-4 Part 2 (mp4v) пишется в контейнер .mp4."""
    assert codec_extension(VideoCodec.MP4V) == "mp4"


def test_all_codecs_have_display_name() -> None:
    """Для каждого VideoCodec доступно непустое человекочитаемое название."""
    for codec in VideoCodec:
        name = codec_display_name(codec)
        assert isinstance(name, str)
        assert name.strip()
