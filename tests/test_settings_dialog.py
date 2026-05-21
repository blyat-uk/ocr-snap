from __future__ import annotations

from ocr_snap.perf_settings import AppSettings
from ocr_snap.settings_dialog import SettingsDialog


def test_dialog_constructs_without_error(qapp) -> None:
    settings = AppSettings(deepl_api_key="test:fx")
    dialog = SettingsDialog(settings)
    assert dialog.windowTitle() == "Settings"
    assert dialog._key_field.text() == "test:fx"


def test_dialog_initial_combo_values_match_settings(qapp) -> None:
    settings = AppSettings()
    settings.perf.model_variant = "server"
    settings.perf.device = "cpu"
    settings.hardware_tier = "high"
    dialog = SettingsDialog(settings)
    assert dialog._model_combo.currentData() == "server"
    assert dialog._device_combo.currentData() == "cpu"
    assert dialog._tier_combo.currentData() == "high"
