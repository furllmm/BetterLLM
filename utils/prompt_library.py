"""
Prompt Library
Saves, categorizes, searches, and retrieves reusable prompts.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

from .paths import get_base_dir

logger = logging.getLogger(__name__)

LIBRARY_FILE = get_base_dir() / "prompts" / "library.json"


def _ensure_dir() -> None:
    LIBRARY_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load() -> List[Dict]:
    _ensure_dir()
    if LIBRARY_FILE.exists():
        try:
            return json.loads(LIBRARY_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Prompt library load failed: %s", e)
    return []


def _save(prompts: List[Dict]) -> None:
    _ensure_dir()
    LIBRARY_FILE.write_text(json.dumps(prompts, indent=2, ensure_ascii=False), encoding="utf-8")


def get_all_prompts() -> List[Dict]:
    """Return all prompts sorted by category then name."""
    return sorted(_load(), key=lambda p: (p.get("category", ""), p.get("name", "")))


def get_categories() -> List[str]:
    """Return all unique categories."""
    seen = set()
    cats = []
    for p in _load():
        c = p.get("category", "General")
        if c not in seen:
            seen.add(c)
            cats.append(c)
    return sorted(cats)


def add_prompt(name: str, text: str, category: str = "General", description: str = "") -> Dict:
    """Add a new prompt. Returns the created prompt dict."""
    prompts = _load()
    entry = {
        "id": f"p_{int(time.time() * 1000)}",
        "name": name,
        "text": text,
        "category": category,
        "description": description,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "use_count": 0,
    }
    prompts.append(entry)
    _save(prompts)
    return entry


def update_prompt(prompt_id: str, **kwargs) -> bool:
    prompts = _load()
    for p in prompts:
        if p["id"] == prompt_id:
            p.update(kwargs)
            _save(prompts)
            return True
    return False


def delete_prompt(prompt_id: str) -> bool:
    prompts = _load()
    new = [p for p in prompts if p["id"] != prompt_id]
    if len(new) < len(prompts):
        _save(new)
        return True
    return False


def search_prompts(query: str) -> List[Dict]:
    """Case-insensitive search in name, text, description, category."""
    q = query.lower()
    return [
        p for p in _load()
        if q in p.get("name", "").lower()
        or q in p.get("text", "").lower()
        or q in p.get("description", "").lower()
        or q in p.get("category", "").lower()
    ]


def increment_use_count(prompt_id: str) -> None:
    prompts = _load()
    for p in prompts:
        if p["id"] == prompt_id:
            p["use_count"] = p.get("use_count", 0) + 1
    _save(prompts)


# Built-in starter prompts
STARTER_PROMPTS = [
    {"name": "Code Review", "category": "Coding", "description": "Review code for issues", "text": "Please review the following code for bugs, performance issues, and style improvements:\n\n```\n{code}\n```"},
    {"name": "Explain Like I'm 5", "category": "Education", "description": "Simple explanation", "text": "Explain {topic} in simple terms that a 5-year-old could understand."},
    {"name": "Translate to Python", "category": "Coding", "description": "Convert code to Python", "text": "Convert the following code to Python:\n\n```\n{code}\n```"},
    {"name": "Write Unit Tests", "category": "Coding", "description": "Generate unit tests", "text": "Write comprehensive unit tests for the following code:\n\n```\n{code}\n```"},
    {"name": "Summarize Text", "category": "Writing", "description": "Summarize long text", "text": "Summarize the following text in 3-5 bullet points:\n\n{text}"},
    {"name": "Fix Grammar", "category": "Writing", "description": "Fix grammar and style", "text": "Fix the grammar, punctuation, and style of the following text while preserving the original meaning:\n\n{text}"},
    {"name": "Debug Error", "category": "Coding", "description": "Help debug an error", "text": "I'm getting this error:\n\n{error}\n\nHere is my code:\n\n```\n{code}\n```\n\nWhat's wrong and how do I fix it?"},
    {"name": "Brainstorm Ideas", "category": "Creative", "description": "Generate creative ideas", "text": "Give me 10 creative ideas for {topic}. Be specific and original."},
]


def initialize_defaults() -> None:
    """Add starter prompts if library is empty."""
    if not _load():
        for p in STARTER_PROMPTS:
            add_prompt(p["name"], p["text"], p["category"], p.get("description", ""))
