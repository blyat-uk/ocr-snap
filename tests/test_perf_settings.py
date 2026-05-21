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
    assert perf.processing_animation == "off"
    assert perf.paddle_cpu_threads == 2


def test_medium_tier_defaults() -> None:
    perf = _TIER_DEFAULTS["medium"]
    assert perf.model_variant == "mobile"
    assert perf.device == "auto"
    assert perf.ocr_max_long_side == 2000
    assert perf.processing_animation == "minimal"
    assert perf.paddle_cpu_threads == 4


def test_high_tier_defaults() -> None:
    perf = _TIER_DEFAULTS["high"]
    assert perf.model_variant == "server"
    assert perf.device == "auto"
    assert perf.ocr_max_long_side == 2400
    assert perf.processing_animation == "full"
    assert perf.paddle_cpu_threads == 4


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


def test_apply_tier_respects_cpu_cap() -> None:
    settings = AppSettings(detected_cpu_cores=2)
    apply_tier(settings, "high")
    assert settings.hardware_tier == "high"
    assert settings.perf.paddle_cpu_threads == 1  # <4 cores rule overrides tier default of 4


def test_apply_tier_skips_cap_when_cores_unknown() -> None:
    settings = AppSettings()  # detected_cpu_cores defaults to 0
    apply_tier(settings, "high")
    assert settings.perf.paddle_cpu_threads == 4  # tier default is 4; cap does not apply (cores unknown)


def test_from_profile_preserves_deepl_key() -> None:
    profile = HardwareProfile(total_ram_gb=8.0, cpu_cores=8, tier="medium")
    settings = from_profile(profile, deepl_key="abc-123:fx")
    assert settings.deepl_api_key == "abc-123:fx"


@pytest.mark.parametrize(
    "ocr_max,device,expected",
    [
        (2000, "cpu", 1600),   # capped to _CPU_LONG_SIDE_CAP
        (1280, "cpu", 1280),   # below cap, unchanged
        (1600, "cpu", 1600),   # at cap exactly
        (2400, "cpu", 1600),   # well above, capped
        (2000, "gpu", 2000),   # gpu: no cap
        (2400, "gpu", 2400),
        (1280, "gpu", 1280),
    ],
)
def test_effective_ocr_long_side(ocr_max: int, device: str, expected: int) -> None:
    from ocr_snap.perf_settings import OCRPerfSettings, effective_ocr_long_side

    perf = OCRPerfSettings(ocr_max_long_side=ocr_max)
    assert effective_ocr_long_side(perf, device) == expected


def test_display_long_side_is_2400() -> None:
    from ocr_snap.perf_settings import DISPLAY_LONG_SIDE

    assert DISPLAY_LONG_SIDE == 2400


def test_apply_tier_clamps_threads_above_four() -> None:
    """If a tier default ever exceeded 4 (or someone hand-edits the
    AppSettings.perf.paddle_cpu_threads after apply_tier), we still
    clamp to 4. Defensive."""
    settings = AppSettings(detected_cpu_cores=8)
    apply_tier(settings, "high")
    settings.perf.paddle_cpu_threads = 16  # simulate hand-edit
    apply_tier(settings, "high")            # re-apply
    assert settings.perf.paddle_cpu_threads == 4
