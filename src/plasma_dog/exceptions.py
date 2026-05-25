"""Кастомные исключения plasma-dog."""


class PlasmaEyeError(Exception):
    """Базовое исключение приложения."""


class CameraError(PlasmaEyeError):
    """Базовая ошибка работы с камерой."""


class CameraNotFoundError(CameraError):
    """Камера не найдена или не открывается."""


class CameraDisconnectedError(CameraError):
    """Камера отключилась во время работы."""


class RecordingError(PlasmaEyeError):
    """Базовая ошибка записи."""


class VideoWriterError(RecordingError):
    """Не удалось инициализировать или записать видео-файл."""


class FrameSaverError(RecordingError):
    """Не удалось сохранить отдельный кадр."""
