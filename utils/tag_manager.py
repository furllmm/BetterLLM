"""
Tag Manager
Manages tags for chats. Tags stored in chats/tags.json.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

from .paths import get_chats_dir

logger = logging.getLogger(__name__)


def _tags_file() -> Path:
    return get_chats_dir() / "tags.json"


def _load() -> Dict[str, List[str]]:
    """Load {chat_path_str: [tag, ...]} mapping."""
    f = _tags_file()
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Tag load error: %s", e)
    return {}


def _save(data: Dict[str, List[str]]) -> None:
    try:
        _tags_file().write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.error("Tag save error: %s", e)


def get_tags(chat_path: str) -> List[str]:
    return _load().get(str(chat_path), [])


def set_tags(chat_path: str, tags: List[str]) -> None:
    data = _load()
    data[str(chat_path)] = sorted(set(tags))
    _save(data)


def add_tag(chat_path: str, tag: str) -> None:
    tags = get_tags(chat_path)
    if tag not in tags:
        tags.append(tag)
    set_tags(chat_path, tags)


def remove_tag(chat_path: str, tag: str) -> None:
    tags = get_tags(chat_path)
    if tag in tags:
        tags.remove(tag)
    set_tags(chat_path, tags)


def get_all_tags() -> List[str]:
    """Return all unique tags across all chats."""
    data = _load()
    seen: Set[str] = set()
    for tags in data.values():
        seen.update(tags)
    return sorted(seen)


def get_chats_with_tag(tag: str) -> List[str]:
    """Return chat paths that have a given tag."""
    return [path for path, tags in _load().items() if tag in tags]


def clear_chat_tags(chat_path: str) -> None:
    data = _load()
    data.pop(str(chat_path), None)
    _save(data)
