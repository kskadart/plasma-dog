"""Тесты SettingsDialog: секция параметров CV-детектора горения."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QSettings

from plasma_dog.const import (
    APP_NAME,
    DEFAULT_FLAME_BLOB_THR_HIGH,
    DEFAULT_FLAME_BLOB_THR_LOW,
    ORG_NAME,
)
from plasma_dog.settings import AppSettings
from plasma_dog.ui.settings_dialog import SettingsDialog


@pytest.fixture(autouse=True)
def _isolate_qsettings(qapp, tmp_path):  # type: ignore[no-untyped-def]
    """Изоляция QSettings на тестовый каталог (INI-формат, кастомный путь).

    Без изоляции тесты писали бы в реальный реестр/конфиг пользователя.
    """
    del qapp  # требуется для инициализации QApplication, иначе QSettings падает
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        str(tmp_path),
    )
    qs = QSettings(ORG_NAME, APP_NAME)
    qs.clear()
    qs.sync()
    yield
    qs2 = QSettings(ORG_NAME, APP_NAME)
    qs2.clear()
    qs2.sync()


def test_flame_detector_section_valid_values_persist_to_settings(qapp) -> None:  # type: ignore[no-untyped-def]
    """Валидные значения секции детектора сохраняются в AppSettings при accept.

    Пороги показываются в процентах, а хранятся как доля 0..1 — проверяется
    конверсия /100 в обе стороны.
    """
    del qapp
    settings = AppSettings()
    dialog = SettingsDialog(settings)

    dialog._flame_thr_low_spin.setValue(20.0)
    dialog._flame_thr_high_spin.setValue(40.0)
    dialog._flame_confirm_spin.setValue(5)
    dialog._flame_infer_hz_spin.setValue(3.0)
    dialog._on_accept()

    reader = AppSettings()
    assert reader.flame_blob_thr_low == pytest.approx(0.20)
    assert reader.flame_blob_thr_high == pytest.approx(0.40)
    assert reader.flame_confirm_frames == 5
    assert reader.flame_infer_hz == pytest.approx(3.0)


def test_flame_detector_section_low_above_high_blocks_save(qapp, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Нижний порог выше верхнего -> предупреждение и ни одно значение не пишется."""
    del qapp
    settings = AppSettings()
    dialog = SettingsDialog(settings)

    warnings: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        "plasma_dog.ui.settings_dialog.QMessageBox.warning",
        lambda *args, **kwargs: warnings.append(args),
    )

    dialog._flame_thr_low_spin.setValue(50.0)
    dialog._flame_thr_high_spin.setValue(30.0)
    dialog._on_accept()

    assert warnings  # предупреждение показано
    # Диалог не закрыт (accept не вызван) и настройки не изменены.
    assert dialog.result() != int(SettingsDialog.DialogCode.Accepted)
    reader = AppSettings()
    assert reader.flame_blob_thr_low == pytest.approx(DEFAULT_FLAME_BLOB_THR_LOW)
    assert reader.flame_blob_thr_high == pytest.approx(DEFAULT_FLAME_BLOB_THR_HIGH)


def test_mirror_checkbox_loads_and_saves_value(qapp) -> None:  # type: ignore[no-untyped-def]
    """Чекбокс 'Зеркало камеры' грузит значение из настроек и сохраняет при accept."""
    del qapp
    settings = AppSettings()
    settings.camera_mirror = False

    dialog = SettingsDialog(settings)
    assert dialog._mirror_checkbox.isChecked() is False  # загружено из настроек

    dialog._mirror_checkbox.setChecked(True)
    dialog._on_accept()

    assert AppSettings().camera_mirror is True


def test_recording_mode_checkbox_loads_and_saves_value(qapp) -> None:  # type: ignore[no-untyped-def]
    """Чекбокс 'Режим записи' грузит значение из настроек и сохраняет при accept."""
    del qapp
    settings = AppSettings()
    settings.recording_mode_enabled = False

    dialog = SettingsDialog(settings)
    assert dialog._recording_mode_checkbox.isChecked() is False  # загружено из настроек

    dialog._recording_mode_checkbox.setChecked(True)
    dialog._on_accept()

    assert AppSettings().recording_mode_enabled is True
