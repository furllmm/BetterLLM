"""
Message Bookmarks
Save and retrieve bookmarked messages for quick access.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .paths import get_base_dir

logger = logging.getLogger(__name__)
BOOKMARKS_FILE = get_base_dir() / "bookmarks.json"


def _load_raw() -> Dict:
    try:
        if BOOKMARKS_FILE.exists():
            with open(BOOKMARKS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning("Could not load bookmarks: %s", e)
    return {}


def _save_raw(data: Dict) -> None:
    try:
        with open(BOOKMARKS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error("Could not save bookmarks: %s", e)


def add_bookmark(chat_path: str, message_index: int, content: str, role: str, note: str = "") -> None:
    data = _load_raw()
    key = f"{chat_path}::{message_index}"
    data[key] = {
        "chat_path": chat_path,
        "message_index": message_index,
        "content": content[:200],
        "role": role,
        "note": note,
        "saved_at": datetime.utcnow().isoformat(),
    }
    _save_raw(data)


def remove_bookmark(chat_path: str, message_index: int) -> None:
    data = _load_raw()
    key = f"{chat_path}::{message_index}"
    data.pop(key, None)
    _save_raw(data)


def is_bookmarked(chat_path: str, message_index: int) -> bool:
    data = _load_raw()
    return f"{chat_path}::{message_index}" in data


def get_all_bookmarks() -> List[Dict]:
    data = _load_raw()
    return sorted(data.values(), key=lambda x: x.get("saved_at", ""), reverse=True)


def clear_all() -> None:
    _save_raw({})
