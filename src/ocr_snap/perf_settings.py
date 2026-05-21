"""Typed performance settings + hardware-tier presets.

Tier names (low/medium/high) match the on-disk representation and the
sibling project sub-label-pos. User-facing labels live in TIER_LABELS.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

from ocr_snap.hardware_profile import HardwareProfile

DISPLAY_LONG_SIDE: int = 2400
_CPU_LONG_SIDE_CAP: int = 1600


@dataclass
class OCRPerfSettings:
    """All perf-relevant OCR knobs."""
    model_variant: Literal["mobile", "server"] = "mobile"
    device: Literal["cpu", "auto"] = "auto"
    ocr_max_long_side: int = 2000
    drop_array_after_ocr: bool = True
    processing_animation: Literal["off", "minimal", "full"] = "minimal"
    paddle_cpu_threads: int = 4


@dataclass
class AppSettings:
    """Root settings document (JSON-serializable)."""
    deepl_api_key: str = ""
    perf: OCRPerfSettings = field(default_factory=OCRPerfSettings)
    hardware_tier: str = "medium"
    detected_ram_gb: float = 0.0
    detected_cpu_cores: int = 0
    version: int = 1


TIER_ORDER = ["low", "medium", "high"]
TIER_LABELS = {
    "low": "Performance",
    "medium": "Balanced",
    "high": "Quality",
}

_TIER_DEFAULTS: dict[str, OCRPerfSettings] = {
    "low": OCRPerfSettings(
        model_variant="mobile",
        device="cpu",
        ocr_max_long_side=1280,
        drop_array_after_ocr=True,
        processing_animation="off",
        paddle_cpu_threads=2,
    ),
    "medium": OCRPerfSettings(
        model_variant="mobile",
        device="auto",
        ocr_max_long_side=2000,
        drop_array_after_ocr=True,
        processing_animation="minimal",
        paddle_cpu_threads=4,
    ),
    "high": OCRPerfSettings(
        model_variant="server",
        device="auto",
        ocr_max_long_side=2400,
        drop_array_after_ocr=False,
        processing_animation="full",
        paddle_cpu_threads=0,
    ),
}


def effective_ocr_long_side(perf: OCRPerfSettings, device: str) -> int:
    """OCR-input long-side ceiling for the resolved device.

    Caps the OCR input at ``_CPU_LONG_SIDE_CAP`` on CPU to keep
    PaddleOCR's activation memory bounded. On GPU, returns the
    user's configured ``ocr_max_long_side`` unchanged.
    """
    if device == "cpu":
        return min(perf.ocr_max_long_side, _CPU_LONG_SIDE_CAP)
    return perf.ocr_max_long_side


def apply_tier(settings: AppSettings, tier: str) -> AppSettings:
    """Overwrite ``settings.perf`` with the named tier's defaults.

    Returns the same settings instance for chaining. If the settings
    record detected CPU cores (>0) and that count is <4, caps
    ``paddle_cpu_threads`` to 1 — same rule as ``from_profile``.
    """
    if tier not in _TIER_DEFAULTS:
        raise ValueError(f"unknown tier: {tier!r}")
    settings.hardware_tier = tier
    settings.perf = OCRPerfSettings(**asdict(_TIER_DEFAULTS[tier]))
    if 0 < settings.detected_cpu_cores < 4:
        settings.perf.paddle_cpu_threads = 1
    return settings


def from_profile(profile: HardwareProfile, deepl_key: str = "") -> AppSettings:
    """Build AppSettings from a fresh hardware detection.

    Applies the CPU-core cap: machines with <4 cores get
    ``paddle_cpu_threads = 1`` regardless of tier default.
    """
    perf = OCRPerfSettings(**asdict(_TIER_DEFAULTS[profile.tier]))
    if profile.cpu_cores < 4:
        perf.paddle_cpu_threads = 1
    return AppSettings(
        deepl_api_key=deepl_key,
        perf=perf,
        hardware_tier=profile.tier,
        detected_ram_gb=round(profile.total_ram_gb, 2),
        detected_cpu_cores=profile.cpu_cores,
    )
