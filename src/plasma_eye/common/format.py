"""Форматирование человекочитаемых значений: размер на диске и длительность."""

from __future__ import annotations

# Десятичные множители (SI), а не binary — пользователь ожидает "1.5 MB" для 1_500_000 байт
_SIZE_UNITS = ("B", "KB", "MB", "GB", "TB")
_SIZE_STEP = 1000.0

_SECONDS_PER_MINUTE = 60
_SECONDS_PER_HOUR = 3600


def human_size(bytes_: int) -> str:
    """Перевод количества байт в человекочитаемый размер.

    Args:
        bytes_: число байт (неотрицательное).

    Returns:
        Строка вида "234 KB", "1.5 MB", "1.2 GB".
    """
    value = float(max(0, bytes_))
    unit_index = 0
    while value >= _SIZE_STEP and unit_index < len(_SIZE_UNITS) - 1:
        value /= _SIZE_STEP
        unit_index += 1
    if unit_index == 0:
        return f"{int(value)} {_SIZE_UNITS[unit_index]}"
    return f"{value:.1f} {_SIZE_UNITS[unit_index]}"


def human_duration(seconds: float) -> str:
    """Перевод длительности в секундах в строку MM:SS или HH:MM:SS.

    Args:
        seconds: длительность в секундах (неотрицательная).

    Returns:
        "MM:SS", если меньше часа, иначе "HH:MM:SS".
    """
    total = int(max(0.0, seconds))
    hours = total // _SECONDS_PER_HOUR
    minutes = (total % _SECONDS_PER_HOUR) // _SECONDS_PER_MINUTE
    secs = total % _SECONDS_PER_MINUTE
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
