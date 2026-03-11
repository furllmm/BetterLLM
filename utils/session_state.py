"""
Session State Manager
Saves and restores complete app state between sessions.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from .paths import get_base_dir

logger = logging.getLogger(__name__)

SESSION_FILE = get_base_dir() / "session.json"


def _default_state() -> Dict[str, Any]:
    return {
        "last_chat_path": None,
        "last_model_topic": None,
        "theme": "dark",
        "sidebar_width": 240,
        "mem_checked": True,
        "deep_checked": False,
        "kb_checked": True,
        "window_geometry": None,   # hex string from saveGeometry
        "scroll_position": 0,
        "generation_params": {
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 40,
            "repeat_penalty": 1.1,
            "max_tokens": 512,
        },
        "active_preset": "Balanced",
    }


def load_session() -> Dict[str, Any]:
    """Load session state from disk (returns defaults on failure)."""
    state = _default_state()
    try:
        if SESSION_FILE.exists():
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            # Merge saved into defaults (so new keys always exist)
            state.update(saved)
            # Ensure generation_params sub-keys all exist
            state["generation_params"] = {
                **_default_state()["generation_params"],
                **state.get("generation_params", {}),
            }
    except Exception as e:
        logger.warning("Could not load session state: %s", e)
    return state


def save_session(state: Dict[str, Any]) -> None:
    """Persist session state to disk."""
    try:
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.error("Could not save session state: %s", e)
