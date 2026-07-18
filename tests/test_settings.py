"""Тесты для AppSettings: round-trip всех свойств + дефолты."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import QSettings

from plasma_dog.const import (
    APP_NAME,
    DEFAULT_ALARM_ENABLED,
    DEFAULT_ALARM_ESCALATE,
    DEFAULT_ALARM_ESCALATE_SECONDS,
    DEFAULT_ALARM_HEARTBEAT_S,
    DEFAULT_ALARM_SOUND_FILE,
    DEFAULT_ALARM_VOLUME,
    DEFAULT_CAMERA_MIRROR,
    DEFAULT_FPS,
    DEFAULT_HOTKEY,
    DEFAULT_PNG_COMPRESSION,
    DEFAULT_RECORDING_MODE,
    DEFAULT_RECORDINGS_DIR,
    DEFAULT_TIMER_SECONDS,
    ORG_NAME,
    FrameFormat,
    VideoCodec,
)
from plasma_dog.settings import AppSettings


@pytest.fixture(autouse=True)
def _isolate_qsettings(qapp, tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """Изоляция QSettings на тестовый каталог через INI-формат и кастомный путь.

    Без изоляции тесты бы писали в реальный реестр/конфиг пользователя.
    QSettings.setPath() с UserScope перенаправит запись в tmp_path.
    """
    del qapp  # требуется для инициализации QApplication, иначе QSettings падает
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        str(tmp_path),
    )
    # Гарантия чистого состояния
    qs = QSettings(ORG_NAME, APP_NAME)
    qs.clear()
    qs.sync()
    yield
    qs2 = QSettings(ORG_NAME, APP_NAME)
    qs2.clear()
    qs2.sync()


def test_settings_defaults(qapp) -> None:  # type: ignore[no-untyped-def]
    """До любых записей AppSettings возвращает дефолты из const.py."""
    del qapp
    settings = AppSettings()
    assert settings.recordings_dir == DEFAULT_RECORDINGS_DIR
    assert settings.frame_format is FrameFormat.PNG
    assert settings.frame_quality == DEFAULT_PNG_COMPRESSION
    assert settings.hotkey_start_stop == DEFAULT_HOTKEY
    assert settings.timer_default_seconds == DEFAULT_TIMER_SECONDS
    assert settings.camera_properties == {}
    assert settings.last_camera_index is None


def test_settings_round_trip(qapp, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Установленные значения возвращаются новым экземпляром AppSettings."""
    del qapp
    custom_dir = tmp_path / "my_recordings"
    snapshot = {"brightness": 25.0, "contrast": -10.0, "auto_exposure": 1.0}

    writer = AppSettings()
    writer.recordings_dir = custom_dir
    writer.frame_format = FrameFormat.JPG
    writer.frame_quality = 80
    writer.hotkey_start_stop = "Ctrl+Shift+R"
    writer.timer_default_seconds = 120
    writer.camera_properties = snapshot
    writer.last_camera_index = 2

    reader = AppSettings()
    assert reader.recordings_dir == custom_dir
    assert reader.frame_format is FrameFormat.JPG
    assert reader.frame_quality == 80
    assert reader.hotkey_start_stop == "Ctrl+Shift+R"
    assert reader.timer_default_seconds == 120
    assert reader.camera_properties == snapshot
    assert reader.last_camera_index == 2


def test_settings_last_camera_index_can_be_cleared(qapp) -> None:  # type: ignore[no-untyped-def]
    """Установка last_camera_index = None удаляет ключ."""
    del qapp
    settings = AppSettings()
    settings.last_camera_index = 5
    assert settings.last_camera_index == 5
    settings.last_camera_index = None
    assert settings.last_camera_index is None


def test_settings_clear_restores_defaults(qapp) -> None:  # type: ignore[no-untyped-def]
    """После clear() читаются дефолтные значения."""
    del qapp
    settings = AppSettings()
    settings.recordings_dir = Path("/tmp/foo")
    settings.frame_format = FrameFormat.BMP
    settings.clear()
    assert settings.recordings_dir == DEFAULT_RECORDINGS_DIR
    assert settings.frame_format is FrameFormat.PNG


def test_settings_camera_properties_invalid_json(qapp) -> None:  # type: ignore[no-untyped-def]
    """Битый JSON в camera_properties не ломает доступ — возвращается пустой dict."""
    del qapp
    settings = AppSettings()
    # Подменяем raw value через QSettings напрямую
    qs = QSettings(ORG_NAME, APP_NAME)
    qs.setValue("camera/properties_json", "not a json {")
    qs.sync()
    assert settings.camera_properties == {}


def test_settings_frame_quality_default_depends_on_format(qapp) -> None:  # type: ignore[no-untyped-def]
    """Если frame_quality не сохранён, дефолт зависит от текущего frame_format."""
    del qapp
    settings = AppSettings()
    # PNG по умолчанию -> DEFAULT_PNG_COMPRESSION
    assert settings.frame_quality == DEFAULT_PNG_COMPRESSION
    settings.frame_format = FrameFormat.JPG
    # frame_quality всё ещё не сохранён — должен переключиться на JPG-дефолт
    assert settings.frame_quality == 95


def test_settings_video_codec_default_is_h264(qapp) -> None:  # type: ignore[no-untyped-def]
    """До любых записей video_codec возвращает H264 (DEFAULT_VIDEO_CODEC)."""
    del qapp
    settings = AppSettings()
    assert settings.video_codec is VideoCodec.H264


def test_settings_video_codec_round_trip(qapp) -> None:  # type: ignore[no-untyped-def]
    """Установка VP9 -> чтение возвращает VP9 в новом экземпляре."""
    del qapp
    writer = AppSettings()
    writer.video_codec = VideoCodec.VP9
    reader = AppSettings()
    assert reader.video_codec is VideoCodec.VP9


def test_settings_recording_fps_default(qapp) -> None:  # type: ignore[no-untyped-def]
    """До любых записей recording_fps возвращает DEFAULT_FPS (30.0) как float."""
    del qapp
    settings = AppSettings()
    assert settings.recording_fps == float(DEFAULT_FPS)
    assert isinstance(settings.recording_fps, float)


def test_settings_recording_fps_round_trip(qapp) -> None:  # type: ignore[no-untyped-def]
    """Установка 60.0 -> чтение возвращает 60.0 в новом экземпляре."""
    del qapp
    writer = AppSettings()
    writer.recording_fps = 60.0
    reader = AppSettings()
    assert reader.recording_fps == 60.0


def test_settings_recording_fps_fractional(qapp) -> None:  # type: ignore[no-untyped-def]
    """Дробный fps (0.5 для time-lapse) корректно сохраняется и читается."""
    del qapp
    writer = AppSettings()
    writer.recording_fps = 0.5
    reader = AppSettings()
    assert reader.recording_fps == 0.5


def test_settings_camera_mirror_default_is_true(qapp) -> None:  # type: ignore[no-untyped-def]
    """До любых записей camera_mirror возвращает DEFAULT_CAMERA_MIRROR (True)."""
    del qapp
    settings = AppSettings()
    assert settings.camera_mirror is DEFAULT_CAMERA_MIRROR
    assert settings.camera_mirror is True


def test_settings_camera_mirror_round_trip(qapp) -> None:  # type: ignore[no-untyped-def]
    """camera_mirror сохраняется и читается новым экземпляром: False -> False, True -> True."""
    del qapp
    writer = AppSettings()
    writer.camera_mirror = False
    assert AppSettings().camera_mirror is False
    writer.camera_mirror = True
    assert AppSettings().camera_mirror is True


def test_settings_recording_mode_default_is_false(qapp) -> None:  # type: ignore[no-untyped-def]
    """До любых записей recording_mode_enabled возвращает DEFAULT_RECORDING_MODE (False)."""
    del qapp
    settings = AppSettings()
    assert settings.recording_mode_enabled is DEFAULT_RECORDING_MODE
    assert settings.recording_mode_enabled is False


def test_settings_recording_mode_round_trip(qapp) -> None:  # type: ignore[no-untyped-def]
    """recording_mode_enabled сохраняется и читается новым экземпляром: False -> False, True -> True."""
    del qapp
    writer = AppSettings()
    writer.recording_mode_enabled = False
    assert AppSettings().recording_mode_enabled is False
    writer.recording_mode_enabled = True
    assert AppSettings().recording_mode_enabled is True


def test_settings_alarm_defaults(qapp) -> None:  # type: ignore[no-untyped-def]
    """До любых записей alarm-настройки возвращают дефолты из const.py."""
    del qapp
    settings = AppSettings()
    assert settings.alarm_enabled is DEFAULT_ALARM_ENABLED
    assert settings.alarm_sound_file == DEFAULT_ALARM_SOUND_FILE
    assert settings.alarm_volume == pytest.approx(DEFAULT_ALARM_VOLUME)
    assert settings.alarm_heartbeat_s == pytest.approx(DEFAULT_ALARM_HEARTBEAT_S)
    assert settings.alarm_escalate is DEFAULT_ALARM_ESCALATE
    assert settings.alarm_escalate_s == pytest.approx(DEFAULT_ALARM_ESCALATE_SECONDS)


def test_settings_alarm_round_trip(qapp) -> None:  # type: ignore[no-untyped-def]
    """Установленные alarm-настройки возвращаются новым экземпляром AppSettings."""
    del qapp
    writer = AppSettings()
    writer.alarm_enabled = False
    writer.alarm_sound_file = "/tmp/custom_alarm.wav"
    writer.alarm_volume = 0.42
    writer.alarm_heartbeat_s = 3.5
    writer.alarm_escalate = False
    writer.alarm_escalate_s = 45.0

    reader = AppSettings()
    assert reader.alarm_enabled is False
    assert reader.alarm_sound_file == "/tmp/custom_alarm.wav"
    assert reader.alarm_volume == pytest.approx(0.42)
    assert reader.alarm_heartbeat_s == pytest.approx(3.5)
    assert reader.alarm_escalate is False
    assert reader.alarm_escalate_s == pytest.approx(45.0)
