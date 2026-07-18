"""FlameIndicator: цветной текстовый индикатор состояния горелки в топбаре."""

from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QWidget

from plasma_dog.const import FlameState
from plasma_dog.ui.style import ACCENT_READY, ACCENT_REC, ACCENT_WARNING, FONT_MONO

# Текст индикатора для каждого состояния горелки
_STATE_TEXT: dict[FlameState, str] = {
    FlameState.BURNING: "ПЛАМЯ ГОРИТ",
    FlameState.EXTINGUISHED: "ПОГАСЛО",
    FlameState.UNKNOWN: "—",
}

# Цвет индикатора для каждого состояния горелки
_STATE_COLOR: dict[FlameState, str] = {
    FlameState.BURNING: ACCENT_READY,
    FlameState.EXTINGUISHED: ACCENT_REC,
    FlameState.UNKNOWN: ACCENT_WARNING,
}


def _value_style(color: str) -> str:
    """QSS-стиль для моноширинного значения с заданным цветом."""
    return f"font-family: {FONT_MONO}; color: {color};"


class FlameIndicator(QLabel):
    """Индикатор состояния горелки: текст и цвет по FlameState.

    Начальное состояние — UNKNOWN. Обновляется методом set_state().
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.set_state(FlameState.UNKNOWN)

    def set_state(self, state: FlameState) -> None:
        """Установка текста и цвета индикатора по состоянию горелки.

        Args:
            state: состояние горелки, определённое детектором.
        """
        self.setText(_STATE_TEXT[state])
        self.setStyleSheet(_value_style(_STATE_COLOR[state]))
