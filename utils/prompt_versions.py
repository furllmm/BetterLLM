"""
Prompt Versioning
Tracks prompt history so users can restore and compare past prompt versions.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .paths import get_base_dir

logger = logging.getLogger(__name__)
VERSIONS_FILE = get_base_dir() / "prompt_versions.json"
MAX_VERSIONS = 200


def _load() -> List[dict]:
    try:
        if VERSIONS_FILE.exists():
            return json.loads(VERSIONS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Could not load prompt versions: %s", e)
    return []


def _save(data: List[dict]) -> None:
    try:
        VERSIONS_FILE.write_text(
            json.dumps(data[-MAX_VERSIONS:], indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as e:
        logger.error("Could not save prompt versions: %s", e)


def record_prompt(prompt: str, context: str = "", label: str = "") -> None:
    """Record a prompt submission to history."""
    if not prompt.strip():
        return
    data = _load()
    entry = {
        "id": datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f"),
        "prompt": prompt,
        "context": context,
        "label": label,
        "created_at": datetime.utcnow().isoformat(),
    }
    data.append(entry)
    _save(data)


def get_history(search: str = "", limit: int = 100) -> List[dict]:
    """Return prompt history, optionally filtered."""
    data = _load()
    if search:
        s = search.lower()
        data = [d for d in data if s in d["prompt"].lower() or s in d.get("label", "").lower()]
    return list(reversed(data[-limit:]))


def delete_entry(entry_id: str) -> None:
    data = _load()
    data = [d for d in data if d["id"] != entry_id]
    _save(data)


def clear_all() -> None:
    _save([])
