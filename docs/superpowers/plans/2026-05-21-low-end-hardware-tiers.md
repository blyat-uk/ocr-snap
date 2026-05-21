# Low-End Hardware Tiers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a hardware-tier system (Performance / Balanced / Quality) that auto-detects RAM on first run and picks safe defaults for OCR model variant, device (CPU/GPU), inference downscale, processing animation, and CPU threading — fixing the GTX 1650 + 6 GB RAM crash and giving users override controls in the settings dialog.

**Architecture:** Mirror `sub-label-pos`'s layout. Two new pure-Python modules (`hardware_profile.py`, `perf_settings.py`). Extend the existing `config.py` to load/save a richer `AppSettings` blob (JSON in the same `~/.config/ocr-snap/config.json`). Parameterize `OCREngine` to take an `OCRPerfSettings` and remove its hardcoded model names. Rebuild the single-purpose DeepL dialog into a multi-group settings dialog. Wire `MainWindow` to pass settings and handle live/restart-only changes.

**Tech Stack:** Python 3.12, PyQt6, PaddleOCR 3.x, pytest (newly introduced).

**Spec:** `docs/superpowers/specs/2026-05-21-low-end-hardware-tiers-design.md`

---

## File map

| Path | Created / Modified | Responsibility |
|---|---|---|
| `tests/__init__.py` | Create | Make `tests` a package |
| `tests/conftest.py` | Create | Pytest fixtures (Qt app for UI tests) |
| `tests/test_hardware_profile.py` | Create | Cover `_pick_tier`, `detect` |
| `tests/test_perf_settings.py` | Create | Cover tier defaults, `apply_tier`, `from_profile`, CPU cap |
| `tests/test_config.py` | Create | Cover `AppSettings` JSON round-trip, first-run detection, DeepL preservation |
| `src/ocr_snap/hardware_profile.py` | Create | RAM/CPU detection → tier mapping |
| `src/ocr_snap/perf_settings.py` | Create | Dataclasses, tier defaults, `apply_tier`, `from_profile` |
| `src/ocr_snap/config.py` | Modify | Extend with `load_app_settings`, `save_app_settings`; preserve existing API |
| `src/ocr_snap/ocr_engine.py` | Modify | Constructor takes `OCRPerfSettings`; `_resolve_device`; new `model_load_failed` signal; remove hardcoded models |
| `src/ocr_snap/models.py` | Modify | `ImageState.array: np.ndarray \| None`; add `array_from_pixmap` helper |
| `src/ocr_snap/canvas.py` | Modify | `set_animation_mode()`; conditional scan/sparks; remove duplicate QImage→ndarray code (use helper from models) |
| `src/ocr_snap/settings_dialog.py` | Replace | Multi-group dialog (Translation / OCR engine / Hardware profile) |
| `src/ocr_snap/main_window.py` | Modify | Load settings → engine; animation mode init; drop-array after OCR; re-OCR rebuild; settings-dialog signal handling; model-load-failed slot |
| `pyproject.toml` | Modify | Add `pytest` + `pytest-qt` to a new `dev` optional-dependencies extra |

---

## Task 1: Test infrastructure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add pytest extras to pyproject.toml**

Modify `pyproject.toml`. Inside the existing `[project.optional-dependencies]` table (which today has only `gpu`), add a `dev` line:

```toml
[project.optional-dependencies]
gpu = ["paddlepaddle-gpu>=3.3"]
dev = ["pytest>=8.0", "pytest-qt>=4.4"]
```

Add a `[tool.pytest.ini_options]` block at the bottom of the file:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"
```

- [ ] **Step 2: Create empty package marker**

Create `tests/__init__.py` with no content (empty file).

- [ ] **Step 3: Create conftest with a Qt app fixture**

Create `tests/conftest.py`:

```python
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Session-scoped QApplication. PyQt6 demands exactly one per process."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app  # type: ignore[return-value]
```

- [ ] **Step 4: Install dev deps and confirm pytest runs**

Run:
```bash
pip install -e '.[dev]'
pytest -q
```

Expected: pytest discovers zero tests, exits 0 ("no tests ran").

- [ ] **Step 5: Commit**

```bash
git add tests/__init__.py tests/conftest.py pyproject.toml
git commit -m "Bootstrap pytest with Qt app fixture"
```

---

## Task 2: hardware_profile module

**Files:**
- Create: `src/ocr_snap/hardware_profile.py`
- Create: `tests/test_hardware_profile.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_hardware_profile.py`:

```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

Run:
```bash
pytest tests/test_hardware_profile.py -v
```

Expected: `ModuleNotFoundError: No module named 'ocr_snap.hardware_profile'`.

- [ ] **Step 3: Implement the module**

Create `src/ocr_snap/hardware_profile.py`:

```python
"""Hardware detection for tier selection on first run.

Pure detection — no PyQt imports, no I/O outside reading OS-level
memory/CPU info. Ported from sub-label-pos's services/hardware_profile.py.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Literal

log = logging.getLogger(__name__)

Tier = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class HardwareProfile:
    total_ram_gb: float
    cpu_cores: int
    tier: Tier


def _total_ram_bytes() -> int | None:
    """Best-effort total RAM. Returns None if it can't be determined."""
    # /proc/meminfo on Linux
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return kb * 1024
    except FileNotFoundError:
        pass
    # sysctl on macOS
    try:
        import subprocess
        out = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True, text=True, timeout=2, check=True,
        ).stdout.strip()
        return int(out)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
        pass
    # GlobalMemoryStatusEx on Windows
    try:
        import ctypes
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_uint32),
                ("dwMemoryLoad", ctypes.c_uint32),
                ("ullTotalPhys", ctypes.c_uint64),
                ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64),
                ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64),
                ("ullAvailVirtual", ctypes.c_uint64),
                ("sullAvailExtendedVirtual", ctypes.c_uint64),
            ]
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return stat.ullTotalPhys
    except (AttributeError, OSError):
        pass
    return None


def _pick_tier(ram_gb: float) -> Tier:
    if ram_gb <= 6.0:
        return "low"
    if ram_gb <= 16.0:
        return "medium"
    return "high"


def detect() -> HardwareProfile:
    """Detect current machine's hardware and pick a tier.

    Defensive: if RAM detection fails, assume low tier so we don't risk
    pushing an under-resourced machine into the heavier presets.
    """
    ram_bytes = _total_ram_bytes()
    if ram_bytes is None:
        log.warning("Could not detect RAM; assuming low tier")
        ram_gb = 4.0
    else:
        ram_gb = ram_bytes / (1024 ** 3)
    cores = os.cpu_count() or 1
    tier = _pick_tier(ram_gb)
    return HardwareProfile(total_ram_gb=ram_gb, cpu_cores=cores, tier=tier)
```

- [ ] **Step 4: Run tests to confirm they pass**

Run:
```bash
pytest tests/test_hardware_profile.py -v
```

Expected: all 9 tests PASS (8 parametrized + 1 smoke).

- [ ] **Step 5: Commit**

```bash
git add src/ocr_snap/hardware_profile.py tests/test_hardware_profile.py
git commit -m "Add hardware_profile module for tier detection"
```

---

## Task 3: perf_settings module

**Files:**
- Create: `src/ocr_snap/perf_settings.py`
- Create: `tests/test_perf_settings.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_perf_settings.py`:

```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

Run:
```bash
pytest tests/test_perf_settings.py -v
```

Expected: `ModuleNotFoundError: No module named 'ocr_snap.perf_settings'`.

- [ ] **Step 3: Implement the module**

Create `src/ocr_snap/perf_settings.py`:

```python
"""Typed performance settings + hardware-tier presets.

Tier names (low/medium/high) match the on-disk representation and the
sibling project sub-label-pos. User-facing labels live in TIER_LABELS.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

from ocr_snap.hardware_profile import HardwareProfile


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


def apply_tier(settings: AppSettings, tier: str) -> AppSettings:
    """Overwrite ``settings.perf`` with the named tier's defaults.

    Returns the same settings instance for chaining.
    """
    if tier not in _TIER_DEFAULTS:
        raise ValueError(f"unknown tier: {tier!r}")
    settings.hardware_tier = tier
    settings.perf = OCRPerfSettings(**asdict(_TIER_DEFAULTS[tier]))
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
```

- [ ] **Step 4: Run tests to confirm they pass**

Run:
```bash
pytest tests/test_perf_settings.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ocr_snap/perf_settings.py tests/test_perf_settings.py
git commit -m "Add perf_settings module with tier presets"
```

---

## Task 4: Extend config.py with AppSettings load/save

**Files:**
- Modify: `src/ocr_snap/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Read the existing config.py to confirm baseline**

Read `src/ocr_snap/config.py` so you know `load_config`, `save_config`, `resolve_deepl_key`, `set_deepl_key` exist and reference `CONFIG_PATH = Path.home() / ".config" / "ocr-snap" / "config.json"`. The existing helpers must keep working.

- [ ] **Step 2: Write failing tests**

Create `tests/test_config.py`:

```python
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
```

- [ ] **Step 3: Run tests to confirm they fail**

Run:
```bash
pytest tests/test_config.py -v
```

Expected: failures because `load_app_settings`, `save_app_settings`, and the `detect` import don't exist yet in `config.py`.

- [ ] **Step 4: Extend config.py**

Replace the contents of `src/ocr_snap/config.py` with:

```python
from __future__ import annotations

import json
import os
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

from ocr_snap.hardware_profile import detect
from ocr_snap.perf_settings import (
    AppSettings,
    OCRPerfSettings,
    from_profile,
)

CONFIG_DIR = Path.home() / ".config" / "ocr-snap"
CONFIG_PATH = CONFIG_DIR / "config.json"


# ── Low-level JSON helpers (unchanged behavior) ─────────────────────

def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(CONFIG_PATH.read_text())
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(data: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(CONFIG_PATH)


# ── DeepL key helpers (preserved API) ──────────────────────────────

def resolve_deepl_key() -> str:
    cfg = load_config()
    key = cfg.get("deepl_api_key")
    if isinstance(key, str) and key:
        return key
    env_key = os.environ.get("DEEPL_API_KEY", "") or os.environ.get("DEEPL_AUTH_KEY", "")
    if env_key:
        cfg["deepl_api_key"] = env_key
        try:
            save_config(cfg)
        except OSError:
            pass
    return env_key


def set_deepl_key(key: str) -> None:
    cfg = load_config()
    cfg["deepl_api_key"] = key
    save_config(cfg)


# ── AppSettings load/save ──────────────────────────────────────────

def load_app_settings() -> AppSettings:
    """Load the full AppSettings document.

    On first run (file missing or no ``perf`` section), runs hardware
    detection, builds defaults via ``from_profile``, preserves any
    existing ``deepl_api_key``, and writes the result back to disk.
    """
    raw = load_config()
    if not raw or "perf" not in raw:
        existing_key = raw.get("deepl_api_key", "") if isinstance(raw, dict) else ""
        if not isinstance(existing_key, str):
            existing_key = ""
        settings = from_profile(detect(), deepl_key=existing_key)
        save_app_settings(settings)
        return settings
    return _from_dict(raw)


def save_app_settings(settings: AppSettings) -> None:
    save_config(_to_dict(settings))


def _to_dict(s: AppSettings) -> dict[str, Any]:
    return {
        "version": s.version,
        "deepl_api_key": s.deepl_api_key,
        "hardware_tier": s.hardware_tier,
        "detected_ram_gb": s.detected_ram_gb,
        "detected_cpu_cores": s.detected_cpu_cores,
        "perf": asdict(s.perf),
    }


def _from_dict(data: dict[str, Any]) -> AppSettings:
    perf_data = data.get("perf", {}) or {}
    perf_fields = {f.name for f in fields(OCRPerfSettings)}
    perf = OCRPerfSettings(
        **{k: v for k, v in perf_data.items() if k in perf_fields}
    )
    return AppSettings(
        deepl_api_key=str(data.get("deepl_api_key", "") or ""),
        perf=perf,
        hardware_tier=str(data.get("hardware_tier", "medium")),
        detected_ram_gb=float(data.get("detected_ram_gb", 0.0)),
        detected_cpu_cores=int(data.get("detected_cpu_cores", 0)),
        version=int(data.get("version", 1)),
    )
```

- [ ] **Step 5: Run tests to confirm they pass**

Run:
```bash
pytest tests/test_config.py -v
```

Expected: all 6 tests PASS.

Also re-run the prior suites to make sure nothing regressed:
```bash
pytest -q
```

Expected: all prior tests still pass.

- [ ] **Step 6: Commit**

```bash
git add src/ocr_snap/config.py tests/test_config.py
git commit -m "Extend config with AppSettings load/save"
```

---

## Task 5: Parameterize OCREngine

**Files:**
- Modify: `src/ocr_snap/ocr_engine.py`
- Modify: `src/ocr_snap/main_window.py` (constructor wiring only — animation/drop-array come later)
- Modify: `src/ocr_snap/app.py` (load full settings, pass DeepL key from there)

This task removes the hardcoded server models so the crash fix is in place even if later tasks aren't merged.

- [ ] **Step 1: Rewrite ocr_engine.py**

Replace the contents of `src/ocr_snap/ocr_engine.py` with:

```python
from __future__ import annotations

import collections
import concurrent.futures
import threading

import cv2
import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

from ocr_snap.models import OCRResultItem, OCRResults
from ocr_snap.perf_settings import OCRPerfSettings

_PREDICT_TIMEOUT = 30  # seconds
_PRELOAD_TIMEOUT = 60  # seconds


class OCREngine(QObject):
    result_ready = pyqtSignal(str, OCRResults)  # (image_id, results)
    error_occurred = pyqtSignal(str)
    model_load_failed = pyqtSignal(str)

    def __init__(
        self, perf: OCRPerfSettings, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._perf = perf
        self._max_long_side = perf.ocr_max_long_side
        self._ocr: object | None = None
        self._queue: collections.deque[tuple[str, np.ndarray, float]] = collections.deque()
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._preload_done = threading.Event()
        self._preload_error: str | None = None
        self._predict_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    def preload(self) -> None:
        thread = threading.Thread(target=self._preload_worker, daemon=True)
        thread.start()

    def _preload_worker(self) -> None:
        try:
            self._init_ocr()
        except Exception as e:  # surface init failures up to the UI
            self._preload_error = str(e)
            self.model_load_failed.emit(str(e))
        finally:
            self._preload_done.set()

    def run(self, image_id: str, image: np.ndarray, *, min_confidence: float = 0.5) -> None:
        with self._lock:
            self._queue.append((image_id, image, min_confidence))
            if self._worker is not None and self._worker.is_alive():
                return
        self._start_worker()

    def _start_worker(self) -> None:
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def _resolve_device(self) -> str:
        """Return 'gpu' or 'cpu' for PaddleOCR's device kwarg."""
        if self._perf.device == "cpu":
            return "cpu"
        # auto
        try:
            import paddle  # type: ignore[import-not-found]
            if paddle.is_compiled_with_cuda():
                return "gpu"
        except Exception:
            pass
        return "cpu"

    def _init_ocr(self) -> None:
        if self._ocr is not None:
            return
        from paddleocr import PaddleOCR

        if self._perf.model_variant == "server":
            det = "PP-OCRv5_server_det"
            rec = "PP-OCRv5_server_rec"
        else:
            det = "PP-OCRv5_mobile_det"
            rec = "PP-OCRv5_mobile_rec"

        device = self._resolve_device()
        kwargs: dict[str, object] = dict(
            text_detection_model_name=det,
            text_recognition_model_name=rec,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device=device,
        )
        if device == "cpu" and self._perf.paddle_cpu_threads > 0:
            kwargs["cpu_threads"] = self._perf.paddle_cpu_threads
        self._ocr = PaddleOCR(**kwargs)

    def _worker_loop(self) -> None:
        while True:
            with self._lock:
                if not self._queue:
                    return
                image_id, image, min_confidence = self._queue.popleft()
            self._process_one(image_id, image, min_confidence)

    def _process_one(self, image_id: str, image: np.ndarray, min_confidence: float) -> None:
        try:
            if not self._preload_done.wait(timeout=_PRELOAD_TIMEOUT):
                self.error_occurred.emit("OCR model loading timed out")
                return
            if self._preload_error is not None:
                self.error_occurred.emit(f"OCR model failed to load: {self._preload_error}")
                return
            self._init_ocr()  # fallback if preload() was never called

            h, w = image.shape[:2]
            scale = 1.0
            if max(h, w) > self._max_long_side:
                scale = self._max_long_side / max(h, w)
                new_w = int(w * scale)
                new_h = int(h * scale)
                image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)

            future = self._predict_pool.submit(self._ocr.predict, image)  # type: ignore[union-attr]
            try:
                result = future.result(timeout=_PREDICT_TIMEOUT)
            except concurrent.futures.TimeoutError:
                self.error_occurred.emit("OCR timed out")
                return

            if not result or result[0] is None:
                self.result_ready.emit(image_id, OCRResults([], w, h))
                return

            page = result[0]
            texts = page["rec_texts"]
            scores = page["rec_scores"]
            polys = page["rec_polys"]
            boxes = page["rec_boxes"]

            inv_scale = 1.0 / scale

            items = []
            idx = 0
            for text, score, poly, box in zip(texts, scores, polys, boxes):
                if float(score) < min_confidence:
                    continue
                items.append(
                    OCRResultItem(
                        index=idx,
                        text=text,
                        confidence=float(score),
                        polygon=np.array(poly) * inv_scale,
                        bbox=(
                            float(box[0]) * inv_scale,
                            float(box[1]) * inv_scale,
                            float(box[2]) * inv_scale,
                            float(box[3]) * inv_scale,
                        ),
                    )
                )
                idx += 1

            self.result_ready.emit(image_id, OCRResults(items, w, h))
        except Exception as e:
            self.error_occurred.emit(str(e))

    def shutdown(self) -> None:
        with self._lock:
            self._queue.clear()
        if self._worker is not None:
            self._worker.join(timeout=5)
        self._predict_pool.shutdown(wait=False)
```

- [ ] **Step 2: Update app.py to load settings centrally**

Replace `src/ocr_snap/app.py` with:

```python
import sys

from dotenv import load_dotenv
from PyQt6.QtWidgets import QApplication

from ocr_snap.config import load_app_settings
from ocr_snap.main_window import MainWindow


def main():
    load_dotenv()
    app = QApplication(sys.argv)
    app.setApplicationName("OCR Snap")
    settings = load_app_settings()
    window = MainWindow(settings)
    window.show()
    sys.exit(app.exec())
```

- [ ] **Step 3: Update MainWindow constructor to accept AppSettings**

In `src/ocr_snap/main_window.py`:

Change the import block to add:

```python
from ocr_snap.perf_settings import AppSettings
```

Change the `MainWindow.__init__` signature and body:

```python
def __init__(self, settings: AppSettings) -> None:
    super().__init__()
    self.setWindowTitle("OCR Snap")
    self.resize(1200, 800)
    self.setStyleSheet(_APP_STYLE)

    self._app_settings = settings
    self._ocr_engine = OCREngine(settings.perf, self)
    self._ocr_engine.preload()
    self._translator = TranslationEngine(settings.deepl_api_key, self)
    ...  # rest of __init__ unchanged
```

(Leave the existing translator/widgets/wiring untouched — they'll still work; only the constructor arguments changed.)

- [ ] **Step 4: Manual sanity check**

Start the app:

```bash
python -m ocr_snap
```

Expected:
- App window opens.
- Paste a small screenshot (e.g., from your clipboard).
- OCR completes; results appear in the sidebar.
- First launch creates `~/.config/ocr-snap/config.json` with a `perf` block and `hardware_tier` populated.

Confirm:
```bash
cat ~/.config/ocr-snap/config.json
```

If anything errors, fix before committing. The model variant on this machine should be whatever the auto-detected tier picks (mobile for low/medium, server for high).

- [ ] **Step 5: Commit**

```bash
git add src/ocr_snap/ocr_engine.py src/ocr_snap/app.py src/ocr_snap/main_window.py
git commit -m "Parameterize OCREngine with OCRPerfSettings"
```

---

## Task 6: ImageState.array optional + shared QImage→ndarray helper

**Files:**
- Modify: `src/ocr_snap/models.py`
- Modify: `src/ocr_snap/canvas.py`

- [ ] **Step 1: Add the helper and make array optional**

In `src/ocr_snap/models.py`, add the helper function (place it just below `item_color`):

```python
def array_from_pixmap(pixmap: QPixmap) -> np.ndarray:
    """Convert a QPixmap to an RGB uint8 numpy array (H, W, 3)."""
    qimg = pixmap.toImage().convertToFormat(QImage.Format.Format_RGB888)
    ptr = qimg.bits()
    if ptr is None:
        raise RuntimeError("QImage.bits() returned None")
    h, w = qimg.height(), qimg.width()
    bpl = qimg.bytesPerLine()
    ptr.setsize(bpl * h)
    buf = np.frombuffer(ptr, dtype=np.uint8).reshape(h, bpl)  # type: ignore[call-overload]
    return buf[:, : w * 3].reshape(h, w, 3).copy()
```

Add the matching imports at the top of `models.py`:

```python
from PyQt6.QtGui import QColor, QImage, QPixmap
```

(Already imports `QColor`, `QPixmap`; just add `QImage`.)

Change the `ImageState` class signature:

```python
class ImageState:
    def __init__(self, image_id: str, pixmap: QPixmap, array: np.ndarray | None) -> None:
        self.image_id = image_id
        self.pixmap = pixmap
        self.array: np.ndarray | None = array
        ...  # rest unchanged
```

- [ ] **Step 2: Use the helper from canvas**

In `src/ocr_snap/canvas.py`, replace the inline QImage→ndarray block inside `_load_qimage` (currently `canvas.py:612-620` — the block that does `qimg.convertToFormat(QImage.Format.Format_RGB888)` … `buf[:, : w * 3].reshape(h, w, 3).copy()`) with:

```python
from ocr_snap.models import array_from_pixmap  # at top of file

# inside _load_qimage, after the early-return:
pixmap = QPixmap.fromImage(qimg)
arr = array_from_pixmap(pixmap)
```

Drop the now-unused `qimg_rgb`, `ptr`, `h, w`, `bpl`, `buf` locals from that method. Keep everything else in `_load_qimage` (pixmap addition, scene clearing, `image_loaded.emit(arr, pixmap)`).

- [ ] **Step 3: Run all tests**

```bash
pytest -q
```

Expected: all prior tests still pass (we haven't broken anything; this is a refactor).

- [ ] **Step 4: Manual sanity check**

```bash
python -m ocr_snap
```

Paste an image; confirm OCR still works (this confirms the array still flows correctly).

- [ ] **Step 5: Commit**

```bash
git add src/ocr_snap/models.py src/ocr_snap/canvas.py
git commit -m "Allow ImageState.array to be None; share QImage→ndarray helper"
```

---

## Task 7: OCRCanvas animation mode

**Files:**
- Modify: `src/ocr_snap/canvas.py`

- [ ] **Step 1: Add the setter and gate the animation**

In `src/ocr_snap/canvas.py`:

Add a constant near the other `_SPARKS_PER_TICK` / animation constants at the top:

```python
_SPARKS_PER_TICK_FULL = 3
_SPARKS_PER_TICK_MINIMAL = 0
```

Remove the old `_SPARKS_PER_TICK = 3` constant.

In `OCRCanvas.__init__`, after the other animation state, add:

```python
self._animation_mode: str = "full"  # overridden by set_animation_mode
self._sparks_per_tick = _SPARKS_PER_TICK_FULL
```

Add the public setter:

```python
def set_animation_mode(self, mode: str) -> None:
    """mode is one of 'off', 'minimal', 'full'."""
    self._animation_mode = mode
    if mode == "full":
        self._sparks_per_tick = _SPARKS_PER_TICK_FULL
    else:  # "minimal" or "off"
        self._sparks_per_tick = _SPARKS_PER_TICK_MINIMAL
```

Modify `_start_processing` so the scan line and timer only run in `minimal`/`full` modes:

```python
def _start_processing(self) -> None:
    self._processing = True
    rect = self.sceneRect()

    # Dim overlay (always shown so the user knows something's happening)
    self._overlay = QGraphicsRectItem(rect)
    self._overlay.setBrush(QBrush(QColor(0, 0, 0, 120)))
    self._overlay.setPen(QPen(Qt.PenStyle.NoPen))
    self._overlay.setZValue(50)
    self._scene.addItem(self._overlay)

    if self._animation_mode == "off":
        return  # no scan line, no sparks, no timer

    # Scan line — kept for both minimal and full
    scan_h = rect.height() * 0.012
    self._scan_line = QGraphicsRectItem(rect.x(), rect.y(), rect.width(), scan_h)
    grad = QLinearGradient(0, 0, 0, scan_h)
    grad.setColorAt(0.0, QColor(255, 190, 50, 0))
    grad.setColorAt(0.4, QColor(255, 190, 50, 100))
    grad.setColorAt(0.5, QColor(255, 225, 100, 200))
    grad.setColorAt(0.6, QColor(255, 190, 50, 100))
    grad.setColorAt(1.0, QColor(255, 190, 50, 0))
    self._scan_line.setBrush(QBrush(grad))
    self._scan_line.setPen(QPen(Qt.PenStyle.NoPen))
    self._scan_line.setZValue(51)
    self._scene.addItem(self._scan_line)

    self._scan_pos = 0.0
    self._sparks.clear()
    self._anim_timer.start()
```

Modify `_anim_tick` to use `self._sparks_per_tick` instead of the constant. Find the line `for _ in range(_SPARKS_PER_TICK):` and replace with:

```python
for _ in range(self._sparks_per_tick):
```

- [ ] **Step 2: Smoke test the animation modes**

Create `tests/test_canvas_animation.py`:

```python
from __future__ import annotations

from PyQt6.QtGui import QPixmap

from ocr_snap.canvas import OCRCanvas


def test_set_animation_mode_off_skips_scan_line(qapp) -> None:
    canvas = OCRCanvas()
    # Need a pixmap so _start_processing has something to dim
    pixmap = QPixmap(100, 100)
    pixmap.fill()
    canvas._pixmap_item = canvas._scene.addPixmap(pixmap)
    canvas.setSceneRect(0, 0, 100, 100)

    canvas.set_animation_mode("off")
    canvas._start_processing()
    assert canvas._overlay is not None
    assert canvas._scan_line is None
    assert not canvas._anim_timer.isActive()
    canvas._stop_processing()


def test_set_animation_mode_minimal_runs_scan_no_sparks(qapp) -> None:
    canvas = OCRCanvas()
    pixmap = QPixmap(100, 100)
    pixmap.fill()
    canvas._pixmap_item = canvas._scene.addPixmap(pixmap)
    canvas.setSceneRect(0, 0, 100, 100)

    canvas.set_animation_mode("minimal")
    canvas._start_processing()
    assert canvas._scan_line is not None
    assert canvas._sparks_per_tick == 0
    canvas._anim_tick()
    assert canvas._sparks == []
    canvas._stop_processing()


def test_set_animation_mode_full_spawns_sparks(qapp) -> None:
    canvas = OCRCanvas()
    pixmap = QPixmap(100, 100)
    pixmap.fill()
    canvas._pixmap_item = canvas._scene.addPixmap(pixmap)
    canvas.setSceneRect(0, 0, 100, 100)

    canvas.set_animation_mode("full")
    canvas._start_processing()
    assert canvas._sparks_per_tick == 3
    canvas._anim_tick()
    assert len(canvas._sparks) == 3
    canvas._stop_processing()
```

- [ ] **Step 3: Run the new tests**

```bash
pytest tests/test_canvas_animation.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 4: Run full suite**

```bash
pytest -q
```

Expected: all tests still pass.

- [ ] **Step 5: Commit**

```bash
git add src/ocr_snap/canvas.py tests/test_canvas_animation.py
git commit -m "Add OCRCanvas.set_animation_mode (off/minimal/full)"
```

---

## Task 8: Wire animation mode + drop-array in MainWindow

**Files:**
- Modify: `src/ocr_snap/main_window.py`

- [ ] **Step 1: Apply animation mode at init**

In `MainWindow.__init__`, after `self._canvas = OCRCanvas()` and before the splitter setup, add:

```python
self._canvas.set_animation_mode(self._app_settings.perf.processing_animation)
```

- [ ] **Step 2: Drop the array after OCR completes**

In `MainWindow._on_ocr_results`, after the existing line `state.ocr_results = results` (around `main_window.py:187`), add:

```python
if self._app_settings.perf.drop_array_after_ocr and results.items:
    state.array = None
```

- [ ] **Step 3: Rebuild the array on re-OCR**

Add this import at the top of `main_window.py`:

```python
from ocr_snap.models import array_from_pixmap, ImageState, OCRResultItem, OCRResults
```

(Adjust the existing models import — the line currently reads `from ocr_snap.models import ImageState, OCRResultItem, OCRResults`.)

In `MainWindow._on_reocr_requested`, before the existing `self._ocr_engine.run(...)` call, add the array-rebuild guard:

```python
def _on_reocr_requested(self, threshold: float) -> None:
    if self._active_id is None:
        return
    state = self._images.get(self._active_id)
    if state is None:
        return
    if state.array is None:
        state.array = array_from_pixmap(state.pixmap)
    state.ocr_threshold = threshold
    state.ocr_running = True
    self._canvas.set_processing(True)
    self._gallery.set_processing(self._active_id, True)
    self._ocr_engine.run(self._active_id, state.array, min_confidence=threshold)
    self._status_bar.showMessage("Re-running OCR with lower threshold...")
```

- [ ] **Step 4: Manual sanity check**

```bash
python -m ocr_snap
```

- Paste an image, wait for OCR to finish.
- On a low/medium tier (the default for most machines), verify the animation is dimmer (no sparks).
- Drag the confidence slider down (re-OCR triggers); confirm OCR still runs (the array was rebuilt from the pixmap).
- Open another image, paste it; verify it works too.

If the animation looks wrong or re-OCR crashes, fix before committing.

- [ ] **Step 5: Commit**

```bash
git add src/ocr_snap/main_window.py
git commit -m "Wire animation mode and drop-array-after-ocr in MainWindow"
```

---

## Task 9: Rebuild settings dialog + wire signal handling

**Files:**
- Modify: `src/ocr_snap/settings_dialog.py`
- Modify: `src/ocr_snap/main_window.py`

- [ ] **Step 1: Replace the dialog**

Replace the entire contents of `src/ocr_snap/settings_dialog.py` with:

```python
from __future__ import annotations

import requests
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ocr_snap.hardware_profile import detect
from ocr_snap.perf_settings import (
    AppSettings,
    TIER_LABELS,
    TIER_ORDER,
    apply_tier,
    from_profile,
)

_MODEL_OPTIONS = [
    ("Mobile (smaller, faster, less accurate)", "mobile"),
    ("Server (larger, slower, more accurate)", "server"),
]

_DEVICE_OPTIONS = [
    ("Auto (GPU if available)", "auto"),
    ("CPU only", "cpu"),
]


class SettingsDialog(QDialog):
    """Multi-group settings dialog: Translation / OCR engine / Hardware."""

    tier_overridden = pyqtSignal(str)
    perf_changed = pyqtSignal()

    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(480)
        self._settings = settings
        self._initial_tier = settings.hardware_tier
        self._initial_model = settings.perf.model_variant
        self._initial_device = settings.perf.device
        self._build_ui()

    # ── UI construction ────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(self._build_translation_group())
        layout.addWidget(self._build_ocr_group())
        layout.addWidget(self._build_hardware_group())

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_translation_group(self) -> QGroupBox:
        box = QGroupBox("Translation (DeepL)")
        v = QVBoxLayout(box)

        hint = QLabel(
            "Used to translate OCR results. Free keys end with “:fx”. "
            "Get one at https://www.deepl.com/account/summary."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888; font-size: 12px;")
        v.addWidget(hint)

        row = QHBoxLayout()
        self._key_field = QLineEdit(self._settings.deepl_api_key)
        self._key_field.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_field.setPlaceholderText("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx:fx")
        row.addWidget(self._key_field, stretch=1)

        self._show_box = QCheckBox("Show")
        self._show_box.toggled.connect(self._toggle_visibility)
        row.addWidget(self._show_box)

        self._test_btn = QPushButton("Test key")
        self._test_btn.clicked.connect(self._on_test_key)
        row.addWidget(self._test_btn)
        v.addLayout(row)

        self._key_status = QLabel("")
        self._key_status.setWordWrap(True)
        self._key_status.setStyleSheet("font-size: 12px;")
        v.addWidget(self._key_status)

        return box

    def _build_ocr_group(self) -> QGroupBox:
        box = QGroupBox("OCR engine")
        form = QFormLayout(box)

        self._model_combo = QComboBox()
        for label, value in _MODEL_OPTIONS:
            self._model_combo.addItem(label, value)
        idx = self._model_combo.findData(self._settings.perf.model_variant)
        if idx >= 0:
            self._model_combo.setCurrentIndex(idx)
        form.addRow("Model:", self._model_combo)

        self._device_combo = QComboBox()
        for label, value in _DEVICE_OPTIONS:
            self._device_combo.addItem(label, value)
        idx = self._device_combo.findData(self._settings.perf.device)
        if idx >= 0:
            self._device_combo.setCurrentIndex(idx)
        form.addRow("Device:", self._device_combo)

        note = QLabel(
            "Model or device changes take effect after restarting the app."
        )
        note.setStyleSheet("color: #888; font-size: 11px; font-style: italic;")
        note.setWordWrap(True)
        form.addRow(note)

        return box

    def _build_hardware_group(self) -> QGroupBox:
        box = QGroupBox("Hardware profile")
        v = QVBoxLayout(box)

        row = QHBoxLayout()
        row.addWidget(QLabel("Profile:"))
        self._tier_combo = QComboBox()
        for tier in TIER_ORDER:
            self._tier_combo.addItem(TIER_LABELS[tier], tier)
        idx = (
            TIER_ORDER.index(self._settings.hardware_tier)
            if self._settings.hardware_tier in TIER_ORDER
            else 1
        )
        self._tier_combo.setCurrentIndex(idx)
        row.addWidget(self._tier_combo, 1)

        redetect = QPushButton("Auto-detect")
        redetect.setToolTip(
            "Re-run hardware detection and reset the profile to the recommended tier."
        )
        redetect.clicked.connect(self._on_redetect)
        row.addWidget(redetect)
        v.addLayout(row)

        self._detected_label = QLabel()
        self._detected_label.setStyleSheet("color: #888; font-size: 11px;")
        self._refresh_detected_label()
        v.addWidget(self._detected_label)

        note = QLabel(
            "Profile changes also rewrite Model and Device above. "
            "Restart the app for OCR-engine changes to take effect."
        )
        note.setStyleSheet("color: #888; font-size: 11px; font-style: italic;")
        note.setWordWrap(True)
        v.addWidget(note)

        return box

    def _refresh_detected_label(self) -> None:
        tier_label = TIER_LABELS.get(
            self._settings.hardware_tier, self._settings.hardware_tier
        )
        self._detected_label.setText(
            f"Detected: <b>{self._settings.detected_ram_gb:.1f} GB</b> RAM · "
            f"<b>{self._settings.detected_cpu_cores}</b> cores · "
            f"auto-tier <b>{tier_label}</b>"
        )

    # ── Actions ────────────────────────────────────────────────────

    def _toggle_visibility(self, checked: bool) -> None:
        self._key_field.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    def _set_key_status(self, text: str, color: str) -> None:
        self._key_status.setText(text)
        self._key_status.setStyleSheet(f"font-size: 12px; color: {color};")

    def _on_test_key(self) -> None:
        key = self._key_field.text().strip()
        if not key:
            self._set_key_status("Key is empty.", "#e07a7a")
            return
        url = (
            "https://api-free.deepl.com/v2/usage"
            if key.endswith(":fx")
            else "https://api.deepl.com/v2/usage"
        )
        self._set_key_status("Testing…", "#888")
        self._test_btn.setEnabled(False)
        QApplication.processEvents()
        try:
            resp = requests.get(
                url,
                headers={"Authorization": f"DeepL-Auth-Key {key}"},
                timeout=10,
            )
        except requests.RequestException as e:
            self._test_btn.setEnabled(True)
            self._set_key_status(f"Network error: {e}", "#e07a7a")
            return
        self._test_btn.setEnabled(True)
        if resp.status_code == 200:
            self._set_key_status("Key OK.", "#7ad07a")
        elif resp.status_code in (401, 403):
            self._set_key_status("DeepL rejected the key (unauthorized).", "#e07a7a")
        else:
            self._set_key_status(
                f"Unexpected response from DeepL (HTTP {resp.status_code}).",
                "#e07a7a",
            )

    def _on_redetect(self) -> None:
        # Build fresh settings from detection, but preserve the DeepL key
        fresh = from_profile(detect(), deepl_key=self._key_field.text().strip())
        # Mutate the dialog's settings reference so labels/combos can refresh
        self._settings.perf = fresh.perf
        self._settings.hardware_tier = fresh.hardware_tier
        self._settings.detected_ram_gb = fresh.detected_ram_gb
        self._settings.detected_cpu_cores = fresh.detected_cpu_cores
        # Refresh UI
        idx = TIER_ORDER.index(fresh.hardware_tier)
        self._tier_combo.setCurrentIndex(idx)
        midx = self._model_combo.findData(fresh.perf.model_variant)
        if midx >= 0:
            self._model_combo.setCurrentIndex(midx)
        didx = self._device_combo.findData(fresh.perf.device)
        if didx >= 0:
            self._device_combo.setCurrentIndex(didx)
        self._refresh_detected_label()

    def _on_accept(self) -> None:
        # 1. DeepL key (always saved as entered; testing is advisory)
        self._settings.deepl_api_key = self._key_field.text().strip()

        # 2. Tier change wins over individual combos — apply_tier overwrites perf
        new_tier = self._tier_combo.currentData()
        tier_changed = new_tier != self._initial_tier
        if tier_changed:
            apply_tier(self._settings, new_tier)
        else:
            # 3. Otherwise apply individual model/device overrides
            self._settings.perf.model_variant = self._model_combo.currentData()
            self._settings.perf.device = self._device_combo.currentData()

        # Persist
        from ocr_snap.config import save_app_settings
        save_app_settings(self._settings)

        # Emit signals
        perf_engine_changed = (
            self._settings.perf.model_variant != self._initial_model
            or self._settings.perf.device != self._initial_device
        )
        if tier_changed:
            self.tier_overridden.emit(new_tier)
        if perf_engine_changed:
            self.perf_changed.emit()

        self.accept()
```

- [ ] **Step 2: Smoke-test the dialog**

Create `tests/test_settings_dialog.py`:

```python
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
```

- [ ] **Step 3: Update _on_settings_requested for the new dialog signature**

In `main_window.py`, replace the existing `_on_settings_requested`:

```python
def _on_settings_requested(self) -> None:
    dialog = SettingsDialog(self._app_settings, self)
    needs_restart = {"flag": False}

    def on_tier(_tier: str) -> None:
        needs_restart["flag"] = True

    def on_perf_changed() -> None:
        needs_restart["flag"] = True

    dialog.tier_overridden.connect(on_tier)
    dialog.perf_changed.connect(on_perf_changed)

    if dialog.exec() != SettingsDialog.DialogCode.Accepted:
        return

    # Always apply the live changes
    self._translator.set_api_key(self._app_settings.deepl_api_key)
    self._canvas.set_animation_mode(self._app_settings.perf.processing_animation)
    self._status_bar.showMessage("Settings saved.", 5000)

    if needs_restart["flag"]:
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "Restart required",
            "Model or device changes will take effect after you restart OCR Snap.",
        )
```

Also delete the now-unused `from ocr_snap import config` usage inside `_on_settings_requested` (the dialog now handles saving). Keep the top-level `from ocr_snap import config` import only if it's used elsewhere in the file — search for `config.` to verify.

- [ ] **Step 4: Run new tests**

```bash
pytest tests/test_settings_dialog.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Manual sanity check**

```bash
python -m ocr_snap
```

- Click the gear icon in the sidebar.
- Confirm all three groups render (Translation, OCR engine, Hardware profile).
- Type a DeepL key, click "Test key", confirm status message appears.
- Click "Auto-detect"; confirm the detected line refreshes and combos update.
- Change the Profile combo to Performance; click OK; confirm a "Restart required" message box appears.
- Confirm `~/.config/ocr-snap/config.json` shows `hardware_tier: "low"` and the corresponding perf block.
- Restart the app. Open Settings again. Confirm the profile is still Performance.
- Open Settings, change ONLY the DeepL key, click OK. Confirm NO restart message appears.

- [ ] **Step 6: Commit**

```bash
git add src/ocr_snap/settings_dialog.py src/ocr_snap/main_window.py tests/test_settings_dialog.py
git commit -m "Rebuild SettingsDialog with hardware profile and OCR engine groups"
```

---

## Task 10: Model-load-failed handler

**Files:**
- Modify: `src/ocr_snap/main_window.py`

- [ ] **Step 1: Connect the signal and add the slot**

In `MainWindow.__init__`, after `self._ocr_engine.error_occurred.connect(self._on_ocr_error)`, add:

```python
self._ocr_engine.model_load_failed.connect(self._on_model_load_failed)
self._model_load_failure_shown = False
```

Add the slot next to `_on_ocr_error`:

```python
def _on_model_load_failed(self, message: str) -> None:
    self._status_bar.showMessage(
        f"OCR model failed to load: {message}", 0  # persistent
    )
    if not self._model_load_failure_shown:
        self._model_load_failure_shown = True
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(
            self,
            "OCR engine could not load",
            (
                "The OCR model failed to load:\n\n"
                f"{message}\n\n"
                "Open Settings to try a smaller model (Mobile) or switch the "
                "Device to CPU only, then restart OCR Snap."
            ),
        )
```

- [ ] **Step 2: Run full suite**

```bash
pytest -q
```

Expected: all tests still pass.

- [ ] **Step 3: Commit**

```bash
git add src/ocr_snap/main_window.py
git commit -m "Show critical dialog when OCR model fails to load"
```

---

## Task 11: Final smoke pass + README note

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Mention the new settings in the README**

Find the existing "How to use" section (around `README.md:160-175`). Append a new bullet after the "Multiple images" bullet:

```markdown
8. **Pick a hardware profile** — open Settings (gear icon in the sidebar)
   to choose Performance / Balanced / Quality. On first run the app picks
   one based on detected RAM. Use Performance on low-VRAM GPUs or
   ≤ 6 GB RAM machines.
```

And in the "Note on GPU support" block (around `README.md:118-124`), replace the existing paragraph with:

```markdown
> **Note on GPU support:** OCR Snap auto-detects GPU support at startup and
> chooses CPU or GPU based on your hardware profile. If you're on a low-VRAM
> GPU and the app crashes after pasting, open Settings → OCR engine and set
> Device to "CPU only", or switch Profile to Performance.
```

- [ ] **Step 2: End-to-end manual sanity check**

```bash
python -m ocr_snap
```

Cover these flows:
- Fresh paste → OCR completes → results in sidebar.
- Re-OCR via confidence slider after some time → still works (array rebuild path).
- Open Settings → pick Performance tier → OK → restart prompt → reopen → confirm config.json reflects low tier.
- Open Settings → flip Device to CPU only → OK → restart prompt.
- Paste a second image; confirm gallery works and OCR runs on both.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Document hardware profile in README"
```

---

## Verification checklist (run before declaring done)

- [ ] `pytest -q` reports all green.
- [ ] First-run on a fresh `~/.config/ocr-snap` writes a config.json with `hardware_tier`, `perf`, `detected_ram_gb`, `detected_cpu_cores`.
- [ ] Existing config.json from before this change still loads (first-run path kicks in because there's no `perf` key) and preserves `deepl_api_key`.
- [ ] Pasting an image on a fresh install no longer attempts the server model unless detected tier is high.
- [ ] Switching tier in the dialog persists across restart.
- [ ] Switching only the DeepL key does NOT trigger the restart prompt.
- [ ] Switching Profile, Model, or Device DOES trigger the restart prompt.
- [ ] Re-OCR via the confidence slider works after `drop_array_after_ocr` has nulled `state.array`.
