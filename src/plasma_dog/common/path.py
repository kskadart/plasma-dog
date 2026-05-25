"""Хелперы для работы с путями: имя session-папки и создание директорий."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

# Формат имени session-папки: YYYY-MM-DD_HH-MM-SS
_SESSION_DIR_FORMAT = "%Y-%m-%d_%H-%M-%S"


def session_dir_name(now: datetime | None = None) -> str:
    """Формирование имени session-папки на основе timestamp.

    Args:
        now: момент времени; если None, берётся datetime.now().

    Returns:
        Строка вида "2026-05-25_14-30-00".
    """
    moment = now if now is not None else datetime.now()
    return moment.strftime(_SESSION_DIR_FORMAT)


def ensure_dir(path: Path) -> Path:
    """Создание директории со всеми родителями, если её ещё нет.

    Args:
        path: целевой путь к директории.

    Returns:
        Тот же path для chaining.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path
