"""Тесты CaptureThread: флаг зеркалирования без запуска потока/камеры."""

from __future__ import annotations

from plasma_dog.camera.capture import CaptureThread


def _make_thread(*, mirror: bool) -> CaptureThread:
    """Конструирование CaptureThread без старта потока (камера не открывается).

    Args:
        mirror: начальное значение флага зеркалирования.

    Returns:
        Экземпляр CaptureThread, готовый к проверке флагов (run() не вызывается).
    """
    return CaptureThread(
        camera_index=0,
        width=640,
        height=480,
        fps=30.0,
        mirror=mirror,
    )


def test_capture_thread_mirror_true_reflects_constructor(qapp) -> None:  # type: ignore[no-untyped-def]
    """Конструктор с mirror=True даёт _is_mirror() == True без запуска потока."""
    del qapp
    thread = _make_thread(mirror=True)
    assert thread._is_mirror() is True


def test_capture_thread_set_mirror_false_updates_flag(qapp) -> None:  # type: ignore[no-untyped-def]
    """set_mirror(False) переключает флаг зеркала в False (thread-safe)."""
    del qapp
    thread = _make_thread(mirror=True)
    thread.set_mirror(False)
    assert thread._is_mirror() is False
