"""Точка входа: создаёт QApplication, ставит stylesheet и поднимает MainWindow."""

import logging
import sys

from PyQt6.QtWidgets import QApplication

from plasma_eye.common.logging import setup_logging
from plasma_eye.const import APP_NAME, ORG_NAME
from plasma_eye.ui.main_window import MainWindow
from plasma_eye.ui.style import build_stylesheet


def main() -> None:
    """Инициализация логирования, создание QApplication, применение QSS, event loop."""
    log_path = setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Лог-файл: %s", log_path)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setStyleSheet(build_stylesheet())
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
