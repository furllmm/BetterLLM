"""Persistent custom generation presets."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from .paths import get_base_dir

PRESETS_FILE = get_base_dir() / "presets" / "generation_presets.json"


def _ensure_dir() -> None:
    PRESETS_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_custom_presets() -> Dict[str, Dict]:
    _ensure_dir()
    if not PRESETS_FILE.exists():
        return {}
    try:
        data = json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        clean = {}
        for name, p in data.items():
            if isinstance(name, str) and isinstance(p, dict):
                clean[name] = p
        return clean
    except Exception:
        return {}


def save_custom_preset(name: str, params: Dict) -> None:
    name = (name or "").strip()
    if not name:
        raise ValueError("Preset name cannot be empty")
    presets = load_custom_presets()
    presets[name] = dict(params)
    _ensure_dir()
    PRESETS_FILE.write_text(json.dumps(presets, indent=2, ensure_ascii=False), encoding="utf-8")


def delete_custom_preset(name: str) -> bool:
    presets = load_custom_presets()
    if name not in presets:
        return False
    presets.pop(name)
    _ensure_dir()
    PRESETS_FILE.write_text(json.dumps(presets, indent=2, ensure_ascii=False), encoding="utf-8")
    return True
