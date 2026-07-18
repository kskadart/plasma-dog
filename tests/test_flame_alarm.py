"""Тесты FlameAlarm: чистая логика громкости, старт/стоп, дефолтный звук.

Реальные QMediaPlayer/QAudioOutput в тестах НЕ создаются: их уничтожение с
FFmpeg-бэкендом подвешивает pytest (join фонового потока плеера при GC объекта в
конце теста). В самом приложении это не проблема (процесс завершается, ОС
зачищает ресурсы). Тесты подменяют эти классы лёгкими фейками через monkeypatch —
логика FlameAlarm проверяется без обращения к аудио-устройству.
"""

from __future__ import annotations

import wave

import pytest
from PyQt6.QtCore import QUrl

from plasma_dog.alarm import flame_alarm
from plasma_dog.alarm.flame_alarm import FlameAlarm, default_alarm_sound_path


class _FakeAudioOutput:
    """Заглушка QAudioOutput: хранит громкость, без обращения к устройству."""

    def __init__(self, parent: object = None) -> None:
        self.volume = 1.0

    def setVolume(self, value: float) -> None:
        self.volume = value


class _FakePlayer:
    """Заглушка QMediaPlayer: хранит источник, без реального воспроизведения."""

    def __init__(self, parent: object = None) -> None:
        self._source = QUrl()

    def setAudioOutput(self, audio: object) -> None:
        pass

    def setSource(self, url: QUrl) -> None:
        self._source = url

    def source(self) -> QUrl:
        return self._source

    def play(self) -> None:
        pass

    def stop(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _fake_audio(qapp, monkeypatch):  # type: ignore[no-untyped-def]
    """Подмена QMediaPlayer/QAudioOutput фейками на время теста (без аудио)."""
    del qapp  # требуется, чтобы QApplication существовал для QObject/QTimer
    monkeypatch.setattr(flame_alarm, "QMediaPlayer", _FakePlayer)
    monkeypatch.setattr(flame_alarm, "QAudioOutput", _FakeAudioOutput)


def _configured_alarm(
    *,
    volume: float = 0.7,
    heartbeat: float = 2.0,
    escalate: bool = True,
    escalate_seconds: float = 20.0,
    sound_file: str = "",
) -> FlameAlarm:
    """Создание FlameAlarm с применённой конфигурацией.

    Args:
        volume: базовая громкость 0..1.
        heartbeat: интервал повтора звука, с.
        escalate: включать ли нарастание громкости.
        escalate_seconds: время нарастания до максимума, с.
        sound_file: путь к аудиофайлу (пусто -> дефолт).

    Returns:
        Готовый к использованию экземпляр FlameAlarm.
    """
    alarm = FlameAlarm()
    alarm.configure(
        sound_file=sound_file,
        volume=volume,
        heartbeat_interval=heartbeat,
        escalate=escalate,
        escalate_seconds=escalate_seconds,
    )
    return alarm


def test_default_alarm_sound_path_points_to_existing_wav() -> None:
    """Дефолтный звук существует и является валидным непустым WAV."""
    path = default_alarm_sound_path()
    assert path.exists()
    with wave.open(str(path), "rb") as wav:
        assert wav.getnframes() > 0


def test_volume_for_elapsed_no_escalate_always_base() -> None:
    """Без эскалации громкость всегда равна базовой независимо от времени."""
    alarm = _configured_alarm(volume=0.5, escalate=False, escalate_seconds=20.0)
    assert alarm._volume_for_elapsed(0.0) == pytest.approx(0.5)
    assert alarm._volume_for_elapsed(10.0) == pytest.approx(0.5)
    assert alarm._volume_for_elapsed(1000.0) == pytest.approx(0.5)


def test_volume_for_elapsed_escalate_grows_from_base_to_max() -> None:
    """С эскалацией громкость растёт от базовой к 1.0 и не превышает 1.0."""
    alarm = _configured_alarm(volume=0.7, escalate=True, escalate_seconds=20.0)
    assert alarm._volume_for_elapsed(0.0) == pytest.approx(0.7)
    assert alarm._volume_for_elapsed(10.0) == pytest.approx(0.85)
    assert alarm._volume_for_elapsed(20.0) == pytest.approx(1.0)
    assert alarm._volume_for_elapsed(100.0) == pytest.approx(1.0)


def test_volume_for_elapsed_escalate_is_monotonic() -> None:
    """Громкость при эскалации монотонно не убывает с ростом времени."""
    alarm = _configured_alarm(volume=0.3, escalate=True, escalate_seconds=20.0)
    values = [alarm._volume_for_elapsed(t) for t in (0.0, 5.0, 10.0, 15.0, 20.0, 25.0)]
    assert values == sorted(values)
    assert values[-1] == pytest.approx(1.0)


def test_start_then_stop_toggles_is_active() -> None:
    """start()/stop() переключают is_active() без падений."""
    alarm = _configured_alarm()
    assert alarm.is_active() is False
    alarm.start()
    assert alarm.is_active() is True
    alarm.stop()
    assert alarm.is_active() is False


def test_start_is_idempotent_while_active() -> None:
    """Повторный start() во время активной тревоги оставляет её активной."""
    alarm = _configured_alarm()
    alarm.start()
    alarm.start()
    assert alarm.is_active() is True
    alarm.stop()


def test_stop_is_idempotent_when_inactive() -> None:
    """stop() на неактивной тревоге не падает и оставляет её неактивной."""
    alarm = _configured_alarm()
    alarm.stop()
    assert alarm.is_active() is False


def test_configure_empty_file_uses_default_sound() -> None:
    """Пустой путь звука -> используется дефолтный WAV из пакета."""
    alarm = _configured_alarm(sound_file="")
    assert alarm._player.source().toLocalFile() == str(default_alarm_sound_path())


def test_configure_missing_file_falls_back_to_default() -> None:
    """Несуществующий путь звука -> откат к дефолтному WAV из пакета."""
    alarm = _configured_alarm(sound_file="/nonexistent/path/to/sound.wav")
    assert alarm._player.source().toLocalFile() == str(default_alarm_sound_path())
