"""
Project Workspaces
Group chats, files, and prompts into named projects with separate settings.
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .paths import get_base_dir

logger = logging.getLogger(__name__)
WORKSPACES_FILE = get_base_dir() / "workspaces.json"
WORKSPACES_DATA_DIR = get_base_dir() / "workspaces"


def _load() -> Dict[str, dict]:
    try:
        if WORKSPACES_FILE.exists():
            return json.loads(WORKSPACES_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Could not load workspaces: %s", e)
    return {}


def _save(data: Dict[str, dict]) -> None:
    try:
        WORKSPACES_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as e:
        logger.error("Could not save workspaces: %s", e)


def get_all_workspaces() -> List[dict]:
    return list(_load().values())


def get_workspace(name: str) -> Optional[dict]:
    return _load().get(name)


def create_workspace(name: str, description: str = "", icon: str = "📁",
                     color: str = "#7c83fd") -> dict:
    data = _load()
    ws = {
        "name": name,
        "description": description,
        "icon": icon,
        "color": color,
        "created_at": datetime.utcnow().isoformat(),
        "chat_paths": [],
        "pinned_prompts": [],
        "gen_params": {},
        "profile": "Default",
        "notes": "",
    }
    data[name] = ws
    _save(data)
    # Create dedicated folder
    ws_dir = WORKSPACES_DATA_DIR / name
    ws_dir.mkdir(parents=True, exist_ok=True)
    return ws


def update_workspace(name: str, updates: dict) -> None:
    data = _load()
    if name in data:
        data[name].update(updates)
        _save(data)


def delete_workspace(name: str) -> None:
    data = _load()
    data.pop(name, None)
    _save(data)


def add_chat_to_workspace(workspace_name: str, chat_path: str) -> None:
    data = _load()
    ws = data.get(workspace_name)
    if ws and chat_path not in ws["chat_paths"]:
        ws["chat_paths"].append(chat_path)
        _save(data)


def remove_chat_from_workspace(workspace_name: str, chat_path: str) -> None:
    data = _load()
    ws = data.get(workspace_name)
    if ws and chat_path in ws["chat_paths"]:
        ws["chat_paths"].remove(chat_path)
        _save(data)


def get_workspace_for_chat(chat_path: str) -> Optional[str]:
    for ws in get_all_workspaces():
        if chat_path in ws.get("chat_paths", []):
            return ws["name"]
    return None
