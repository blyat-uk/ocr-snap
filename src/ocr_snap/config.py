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
        "ocr_language": s.ocr_language,
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
        ocr_language=str(data.get("ocr_language", "ch") or "ch"),
        perf=perf,
        hardware_tier=str(data.get("hardware_tier", "medium")),
        detected_ram_gb=float(data.get("detected_ram_gb", 0.0)),
        detected_cpu_cores=int(data.get("detected_cpu_cores", 0)),
        version=int(data.get("version", 1)),
    )
