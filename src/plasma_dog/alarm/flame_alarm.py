"""FlameAlarm: звуковая тревога при погасшем пламени (QtMultimedia).

Тревога проигрывает короткий звук по кругу с заданным интервалом (heartbeat),
пока состояние горелки остаётся EXTINGUISHED. Опционально громкость нарастает от
базовой до максимума за заданное время, чтобы дольше игнорируемая тревога звучала
всё настойчивее. Всё событийное (QTimer + QMediaPlayer), выполняется в GUI-потоке
без блокирующих вызовов. При отсутствии аудио-устройства (headless) конструирование
и воспроизведение не падают — QMediaPlayer это переносит.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QElapsedTimer, QObject, QTimer, QUrl, pyqtSlot
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer

logger = logging.getLogger(__name__)

# Минимальные разумные границы конфигурации тревоги
_MIN_HEARTBEAT_S = 0.2  # нижняя граница интервала повтора звука, с
_MIN_ESCALATE_S = 0.1  # нижняя граница времени нарастания громкости, с
_MIN_VOLUME = 0.0
_MAX_VOLUME = 1.0
_MS_PER_SECOND = 1000.0


def default_alarm_sound_path() -> Path:
    """Путь к дефолтному звуку тревоги, вложенному в пакет.

    Returns:
        Абсолютный путь к resources/alarm_default.wav относительно пакета.
    """
    return Path(__file__).resolve().parent.parent / "resources" / "alarm_default.wav"


class FlameAlarm(QObject):
    """Циклическая звуковая тревога с опциональным нарастанием громкости.

    Держит QMediaPlayer + QAudioOutput и heartbeat-таймер. По start() запускает
    воспроизведение и перезапускает звук на каждом тике таймера; по stop()
    останавливает. Эскалация громкости считается от момента старта по монотонным
    часам QElapsedTimer, повторный start() во время активной тревоги её не
    сбрасывает.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        """Создание плеера, аудио-выхода и heartbeat-таймера.

        Args:
            parent: родительский QObject для управления временем жизни.
        """
        super().__init__(parent)
        self._audio = QAudioOutput(self)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio)

        self._timer = QTimer(self)
        self._timer.setSingleShot(False)
        self._timer.timeout.connect(self._on_beat)
        self._clock = QElapsedTimer()

        self._active = False
        self._base_volume = 0.7
        self._heartbeat_interval = 2.0
        self._escalate = True
        self._escalate_seconds = 20.0

    def configure(
        self,
        sound_file: str,
        volume: float,
        heartbeat_interval: float,
        escalate: bool,
        escalate_seconds: float,
    ) -> None:
        """Применение параметров тревоги и загрузка источника звука.

        Значения громкости и времени нарастания клампятся в разумные пределы;
        интервал повтора не опускается ниже _MIN_HEARTBEAT_S. Пустой или
        несуществующий sound_file заменяется дефолтным звуком из пакета.
        Воспроизведение здесь не запускается.

        Args:
            sound_file: путь к аудиофайлу; пусто/несуществующий -> дефолт.
            volume: базовая громкость 0.0..1.0.
            heartbeat_interval: интервал повтора звука, с.
            escalate: включать ли нарастание громкости.
            escalate_seconds: время нарастания до максимума, с.
        """
        self._base_volume = min(_MAX_VOLUME, max(_MIN_VOLUME, volume))
        self._heartbeat_interval = max(_MIN_HEARTBEAT_S, heartbeat_interval)
        self._escalate = escalate
        self._escalate_seconds = max(_MIN_ESCALATE_S, escalate_seconds)

        path = Path(sound_file) if sound_file else None
        if path is None or not path.exists():
            path = default_alarm_sound_path()
        self._player.setSource(QUrl.fromLocalFile(str(path)))

    def _volume_for_elapsed(self, elapsed_s: float) -> float:
        """Громкость для заданного времени с момента старта тревоги.

        Без эскалации всегда возвращается базовая громкость. С эскалацией
        громкость линейно растёт от базовой к 1.0 за escalate_seconds и дальше
        не превышает 1.0.

        Args:
            elapsed_s: время с момента старта тревоги, с.

        Returns:
            Громкость в диапазоне 0.0..1.0.
        """
        if not self._escalate:
            return self._base_volume
        ratio = elapsed_s / max(self._escalate_seconds, 0.001)
        return min(_MAX_VOLUME, self._base_volume + (_MAX_VOLUME - self._base_volume) * ratio)

    def start(self) -> None:
        """Запуск тревоги, если она ещё не активна.

        Повторный вызов во время активной тревоги игнорируется, чтобы не
        сбрасывать накопленную эскалацию громкости.
        """
        if self._active:
            return
        self._active = True
        self._clock.start()
        self._audio.setVolume(self._volume_for_elapsed(0.0))
        self._player.play()
        self._timer.start(int(self._heartbeat_interval * _MS_PER_SECOND))

    @pyqtSlot()
    def _on_beat(self) -> None:
        """Тик heartbeat: пересчёт громкости и перезапуск звука с начала."""
        if not self._active:
            self._timer.stop()
            return
        elapsed_s = self._clock.elapsed() / _MS_PER_SECOND
        self._audio.setVolume(self._volume_for_elapsed(elapsed_s))
        self._player.stop()
        self._player.play()

    def stop(self) -> None:
        """Остановка тревоги и сброс громкости к базовой. Идемпотентно."""
        self._active = False
        self._timer.stop()
        self._player.stop()
        self._audio.setVolume(self._base_volume)

    def is_active(self) -> bool:
        """Активна ли тревога сейчас.

        Returns:
            True, если тревога проигрывается.
        """
        return self._active
