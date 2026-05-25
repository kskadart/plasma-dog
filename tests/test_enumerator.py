"""Тесты enumerator: общий хелпер _try_open и публичная list_cameras.

Тесты избегают зависимости от реальной камеры: проверяется только то, что
функции не падают и возвращают корректные типы.
"""

from __future__ import annotations

from plasma_eye.camera.enumerator import CameraInfo, _try_open, list_cameras
from plasma_eye.camera.properties import default_backend


def test_try_open_returns_bool_without_camera() -> None:
    """_try_open на заведомо отсутствующем индексе возвращает False без исключения."""
    result = _try_open(99, default_backend())
    assert isinstance(result, bool)
    assert result is False


def test_list_cameras_returns_list() -> None:
    """list_cameras() возвращает list (возможно пустой) без исключений.

    Содержимое зависит от железа, поэтому проверяется только тип и форма.
    """
    cameras = list_cameras()
    assert isinstance(cameras, list)
    for cam in cameras:
        assert isinstance(cam, CameraInfo)
        assert cam.index >= 0
        assert cam.name
