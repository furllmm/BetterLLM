"""
Chat Snapshots
Save and restore conversation checkpoints / branching points.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .paths import get_base_dir

logger = logging.getLogger(__name__)
SNAPSHOTS_DIR = get_base_dir() / "snapshots"


def _ensure_dir() -> Path:
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    return SNAPSHOTS_DIR


def save_snapshot(chat_path: str, messages: List[dict], label: str = "") -> str:
    """Save a snapshot of the current chat state. Returns snapshot ID."""
    snap_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    d = _ensure_dir()
    snap = {
        "id": snap_id,
        "chat_path": chat_path,
        "label": label or f"Snapshot {datetime.utcnow().strftime('%H:%M:%S')}",
        "created_at": datetime.utcnow().isoformat(),
        "messages": messages,
        "message_count": len(messages),
    }
    (d / f"{snap_id}.json").write_text(
        json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("Saved snapshot %s (%d messages)", snap_id, len(messages))
    return snap_id


def list_snapshots(chat_path: Optional[str] = None) -> List[dict]:
    """List all snapshots, optionally filtered by chat path."""
    d = _ensure_dir()
    snaps = []
    for f in sorted(d.glob("*.json"), reverse=True):
        try:
            snap = json.loads(f.read_text(encoding="utf-8"))
            if chat_path is None or snap.get("chat_path") == chat_path:
                snaps.append(snap)
        except Exception:
            pass
    return snaps


def load_snapshot(snap_id: str) -> Optional[dict]:
    d = _ensure_dir()
    f = d / f"{snap_id}.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error("Could not load snapshot %s: %s", snap_id, e)
    return None


def delete_snapshot(snap_id: str) -> None:
    d = _ensure_dir()
    f = d / f"{snap_id}.json"
    if f.exists():
        f.unlink()
