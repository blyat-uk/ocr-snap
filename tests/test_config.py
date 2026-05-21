from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ocr_snap import config
from ocr_snap.hardware_profile import HardwareProfile
from ocr_snap.perf_settings import AppSettings, OCRPerfSettings


@pytest.fixture
def tmp_config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect CONFIG_PATH to a temp file for the duration of the test."""
    target = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_PATH", target)
    return target


def test_first_run_creates_file_via_detection(tmp_config_path: Path) -> None:
    fake_profile = HardwareProfile(total_ram_gb=4.0, cpu_cores=2, tier="low")
    with patch("ocr_snap.config.detect", return_value=fake_profile):
        settings = config.load_app_settings()
    assert settings.hardware_tier == "low"
    assert settings.detected_ram_gb == 4.0
    assert settings.detected_cpu_cores == 2
    assert settings.perf.paddle_cpu_threads == 1  # CPU-cap kicks in
    assert tmp_config_path.exists()
    data = json.loads(tmp_config_path.read_text())
    assert data["hardware_tier"] == "low"
    assert data["perf"]["model_variant"] == "mobile"


def test_first_run_preserves_existing_deepl_key(tmp_config_path: Path) -> None:
    tmp_config_path.write_text(json.dumps({"deepl_api_key": "key-xyz:fx"}))
    fake_profile = HardwareProfile(total_ram_gb=8.0, cpu_cores=8, tier="medium")
    with patch("ocr_snap.config.detect", return_value=fake_profile):
        settings = config.load_app_settings()
    assert settings.deepl_api_key == "key-xyz:fx"
    assert settings.hardware_tier == "medium"


def test_round_trip(tmp_config_path: Path) -> None:
    original = AppSettings(
        deepl_api_key="round-trip:fx",
        perf=OCRPerfSettings(
            model_variant="server",
            device="cpu",
            ocr_max_long_side=1600,
            drop_array_after_ocr=False,
            processing_animation="full",
            paddle_cpu_threads=6,
        ),
        hardware_tier="high",
        detected_ram_gb=32.5,
        detected_cpu_cores=16,
    )
    config.save_app_settings(original)
    loaded = config.load_app_settings()
    assert loaded.deepl_api_key == "round-trip:fx"
    assert loaded.perf.model_variant == "server"
    assert loaded.perf.device == "cpu"
    assert loaded.perf.ocr_max_long_side == 1600
    assert loaded.perf.drop_array_after_ocr is False
    assert loaded.perf.processing_animation == "full"
    assert loaded.perf.paddle_cpu_threads == 6
    assert loaded.hardware_tier == "high"
    assert loaded.detected_ram_gb == 32.5
    assert loaded.detected_cpu_cores == 16


def test_load_drops_unknown_perf_keys(tmp_config_path: Path) -> None:
    tmp_config_path.write_text(json.dumps({
        "deepl_api_key": "",
        "hardware_tier": "medium",
        "detected_ram_gb": 8.0,
        "detected_cpu_cores": 8,
        "perf": {
            "model_variant": "mobile",
            "device": "auto",
            "ocr_max_long_side": 2000,
            "drop_array_after_ocr": True,
            "processing_animation": "minimal",
            "paddle_cpu_threads": 4,
            "future_knob_we_dont_know_about": 42,
        },
        "version": 1,
    }))
    settings = config.load_app_settings()
    assert settings.perf.model_variant == "mobile"
    assert not hasattr(settings.perf, "future_knob_we_dont_know_about")


def test_set_deepl_key_preserves_perf(tmp_config_path: Path) -> None:
    fake_profile = HardwareProfile(total_ram_gb=8.0, cpu_cores=8, tier="medium")
    with patch("ocr_snap.config.detect", return_value=fake_profile):
        config.load_app_settings()  # first run writes perf section
    config.set_deepl_key("new-key:fx")
    settings = config.load_app_settings()
    assert settings.deepl_api_key == "new-key:fx"
    assert settings.perf.model_variant == "mobile"  # medium default
    assert settings.hardware_tier == "medium"


def test_corrupt_file_triggers_first_run(tmp_config_path: Path) -> None:
    tmp_config_path.write_text("not valid json {")
    fake_profile = HardwareProfile(total_ram_gb=8.0, cpu_cores=8, tier="medium")
    with patch("ocr_snap.config.detect", return_value=fake_profile):
        settings = config.load_app_settings()
    assert settings.hardware_tier == "medium"
