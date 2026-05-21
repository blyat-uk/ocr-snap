from __future__ import annotations

import pytest

from ocr_snap.hardware_profile import _pick_tier, detect


@pytest.mark.parametrize(
    "ram_gb,expected",
    [
        (2.0, "low"),
        (4.0, "low"),
        (6.0, "low"),
        (8.0, "medium"),
        (12.0, "medium"),
        (16.0, "medium"),
        (24.0, "high"),
        (64.0, "high"),
    ],
)
def test_pick_tier(ram_gb: float, expected: str) -> None:
    assert _pick_tier(ram_gb) == expected


def test_detect_returns_valid_profile() -> None:
    profile = detect()
    assert profile.total_ram_gb > 0
    assert profile.cpu_cores >= 1
    assert profile.tier in {"low", "medium", "high"}
