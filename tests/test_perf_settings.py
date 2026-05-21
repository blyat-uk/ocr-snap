from __future__ import annotations

import pytest

from ocr_snap.hardware_profile import HardwareProfile
from ocr_snap.perf_settings import (
    AppSettings,
    OCRPerfSettings,
    TIER_LABELS,
    TIER_ORDER,
    _TIER_DEFAULTS,
    apply_tier,
    from_profile,
)


def test_tier_order_and_labels() -> None:
    assert TIER_ORDER == ["low", "medium", "high"]
    assert TIER_LABELS == {
        "low": "Performance",
        "medium": "Balanced",
        "high": "Quality",
    }


def test_low_tier_defaults() -> None:
    perf = _TIER_DEFAULTS["low"]
    assert perf.model_variant == "mobile"
    assert perf.device == "cpu"
    assert perf.ocr_max_long_side == 1280
    assert perf.drop_array_after_ocr is True
    assert perf.processing_animation == "off"
    assert perf.paddle_cpu_threads == 2


def test_medium_tier_defaults() -> None:
    perf = _TIER_DEFAULTS["medium"]
    assert perf.model_variant == "mobile"
    assert perf.device == "auto"
    assert perf.ocr_max_long_side == 2000
    assert perf.drop_array_after_ocr is True
    assert perf.processing_animation == "minimal"
    assert perf.paddle_cpu_threads == 4


def test_high_tier_defaults() -> None:
    perf = _TIER_DEFAULTS["high"]
    assert perf.model_variant == "server"
    assert perf.device == "auto"
    assert perf.ocr_max_long_side == 2400
    assert perf.drop_array_after_ocr is False
    assert perf.processing_animation == "full"
    assert perf.paddle_cpu_threads == 0


def test_apply_tier_overwrites_perf() -> None:
    settings = AppSettings()
    settings.perf.model_variant = "server"  # diverges from medium default
    apply_tier(settings, "low")
    assert settings.hardware_tier == "low"
    assert settings.perf.model_variant == "mobile"
    assert settings.perf.ocr_max_long_side == 1280


def test_apply_tier_unknown_raises() -> None:
    with pytest.raises(ValueError, match="unknown tier"):
        apply_tier(AppSettings(), "ultra")


def test_from_profile_records_detection() -> None:
    profile = HardwareProfile(total_ram_gb=8.0, cpu_cores=8, tier="medium")
    settings = from_profile(profile)
    assert settings.hardware_tier == "medium"
    assert settings.detected_ram_gb == 8.0
    assert settings.detected_cpu_cores == 8
    assert settings.perf.paddle_cpu_threads == 4  # medium default


def test_from_profile_caps_cpu_threads_on_low_core_count() -> None:
    profile = HardwareProfile(total_ram_gb=4.0, cpu_cores=2, tier="low")
    settings = from_profile(profile)
    assert settings.perf.paddle_cpu_threads == 1  # forced down from tier default of 2


def test_from_profile_preserves_deepl_key() -> None:
    profile = HardwareProfile(total_ram_gb=8.0, cpu_cores=8, tier="medium")
    settings = from_profile(profile, deepl_key="abc-123:fx")
    assert settings.deepl_api_key == "abc-123:fx"
