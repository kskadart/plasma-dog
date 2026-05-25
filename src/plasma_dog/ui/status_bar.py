"""RecordingStatusBar: панель статистики записи (elapsed, fps, frames, size, dropped)."""

from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from plasma_dog.common.format import human_duration, human_size
from plasma_dog.ui.style import ACCENT_WARNING, FONT_MONO, TEXT_MUTED, TEXT_SECONDARY

# Шаблоны лейблов: prefix + значение моноширинным шрифтом
_LABEL_NAMES = ("Время:", "FPS:", "Кадры:", "Размер:", "Дропы:")


def _value_style(color: str) -> str:
    """QSS-стиль для моноширинного значения с заданным цветом."""
    return f"font-family: {FONT_MONO}; color: {color};"


class RecordingStatusBar(QWidget):
    """Виджет статуса записи: время, fps, кадры, размер на диске, дропы.

    Значения обновляются методом update_stats(). При наличии дропов их
    лейбл подсвечивается жёлто-оранжевым (ACCENT_WARNING).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._elapsed_value = QLabel()
        self._fps_value = QLabel()
        self._frames_value = QLabel()
        self._size_value = QLabel()
        self._dropped_value = QLabel()
        self._build_layout()
        self.reset()

    def _build_layout(self) -> None:
        """Сборка горизонтального layout с парами prefix+value."""
        layout = QHBoxLayout()
        layout.setSpacing(16)
        layout.setContentsMargins(8, 4, 8, 4)
        values = (
            self._elapsed_value,
            self._fps_value,
            self._frames_value,
            self._size_value,
            self._dropped_value,
        )
        for name, value_label in zip(_LABEL_NAMES, values, strict=True):
            prefix = QLabel(name)
            prefix.setProperty("role", "muted")
            layout.addWidget(prefix)
            layout.addWidget(value_label)
        layout.addStretch(1)
        self.setLayout(layout)

    def update_stats(
        self,
        elapsed: float,
        fps: float,
        frames_written: int,
        bytes_on_disk: int,
        dropped: int,
    ) -> None:
        """Обновление значений в виджете.

        Args:
            elapsed: длительность записи в секундах.
            fps: измеренный fps.
            frames_written: число записанных кадров.
            bytes_on_disk: суммарный размер session-папки на диске.
            dropped: число сброшенных кадров.
        """
        self._elapsed_value.setText(human_duration(elapsed))
        self._elapsed_value.setStyleSheet(_value_style(TEXT_SECONDARY))
        self._fps_value.setText(f"{fps:.1f}")
        self._fps_value.setStyleSheet(_value_style(TEXT_SECONDARY))
        self._frames_value.setText(str(frames_written))
        self._frames_value.setStyleSheet(_value_style(TEXT_SECONDARY))
        self._size_value.setText(human_size(bytes_on_disk))
        self._size_value.setStyleSheet(_value_style(TEXT_SECONDARY))
        self._dropped_value.setText(str(dropped))
        color = ACCENT_WARNING if dropped > 0 else TEXT_SECONDARY
        self._dropped_value.setStyleSheet(_value_style(color))

    def reset(self) -> None:
        """Сброс всех значений к нулевым с приглушённым цветом."""
        muted = _value_style(TEXT_MUTED)
        self._elapsed_value.setText("00:00")
        self._elapsed_value.setStyleSheet(muted)
        self._fps_value.setText("0.0")
        self._fps_value.setStyleSheet(muted)
        self._frames_value.setText("0")
        self._frames_value.setStyleSheet(muted)
        self._size_value.setText("0 B")
        self._size_value.setStyleSheet(muted)
        self._dropped_value.setText("0")
        self._dropped_value.setStyleSheet(muted)
