"""Настройка root logger: stderr + ротация файла в OS-зависимом каталоге."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from plasma_eye.common.path import ensure_dir
from plasma_eye.const import APP_NAME

# Лимиты ротации: 5 MB на файл, 3 архивных файла (итого ~20 MB на диске)
_LOG_FILE_MAX_BYTES = 5 * 1024 * 1024
_LOG_FILE_BACKUP_COUNT = 3
_LOG_FILENAME = "log.txt"
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def log_file_path() -> Path:
    """Путь к лог-файлу в OS-зависимом каталоге пользовательских данных.

    Linux следует XDG Base Directory Specification: $XDG_DATA_HOME либо
    fallback на ~/.local/share. macOS использует ~/Library/Logs. Windows —
    %APPDATA%, с fallback на ~/AppData/Roaming если переменная не задана.

    Returns:
        Абсолютный путь до файла лога (директория ещё может не существовать).
    """
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Logs"
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / APP_NAME / _LOG_FILENAME


def setup_logging(level: int = logging.INFO) -> Path:
    """Конфигурация root logger: вывод в stderr + ротация файла.

    Идемпотентна: повторный вызов не плодит handlers — старые сбрасываются.
    Файловый handler пишет в OS-зависимый каталог пользовательских данных.

    Args:
        level: уровень логирования (по умолчанию INFO).

    Returns:
        Путь к активному лог-файлу.
    """
    path = log_file_path()
    ensure_dir(path.parent)

    formatter = logging.Formatter(_LOG_FORMAT)

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(level)

    file_handler = RotatingFileHandler(
        path,
        maxBytes=_LOG_FILE_MAX_BYTES,
        backupCount=_LOG_FILE_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    root = logging.getLogger()
    # Сброс прежних handlers, чтобы повторный setup_logging не дублировал вывод
    for existing in list(root.handlers):
        root.removeHandler(existing)
        existing.close()
    root.setLevel(level)
    root.addHandler(stream_handler)
    root.addHandler(file_handler)

    return path
