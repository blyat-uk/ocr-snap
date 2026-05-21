from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".config" / "ocr-snap"
CONFIG_PATH = CONFIG_DIR / "config.json"


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
