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




def _normalize_prompt(entry: Dict) -> Dict:
    """Ensure prompt entries always contain extended metadata keys."""
    e = dict(entry)
    e.setdefault("app_name", "")
    e.setdefault("project_name", "")
    e.setdefault("programming_language", "")
    e.setdefault("framework", "")
    e.setdefault("prompt_version", "v1")
    e.setdefault("feature_name", "")
    e.setdefault("tags", [])
    if not isinstance(e.get("tags"), list):
        e["tags"] = []
    return e


def get_all_prompts() -> List[Dict]:
    """Return all prompts sorted by category then name."""
    return sorted([_normalize_prompt(p) for p in _load()], key=lambda p: (p.get("category", ""), p.get("name", "")))


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


def add_prompt(name: str, text: str, category: str = "General", description: str = "",
               app_name: str = "", project_name: str = "", programming_language: str = "",
               framework: str = "", prompt_version: str = "v1", feature_name: str = "",
               tags: Optional[List[str]] = None) -> Dict:
    """Add a new prompt. Returns the created prompt dict."""
    prompts = _load()
    entry = {
        "id": f"p_{int(time.time() * 1000)}",
        "name": name,
        "text": text,
        "category": category,
        "description": description,
        "app_name": app_name,
        "project_name": project_name,
        "programming_language": programming_language,
        "framework": framework,
        "prompt_version": prompt_version or "v1",
        "feature_name": feature_name,
        "tags": tags or [],
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
        or q in p.get("app_name", "").lower()
        or q in p.get("project_name", "").lower()
        or q in p.get("programming_language", "").lower()
        or q in p.get("framework", "").lower()
        or q in p.get("feature_name", "").lower()
        or any(q in str(t).lower() for t in p.get("tags", []))
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


def filter_prompts(app_name: str = "", programming_language: str = "", framework: str = "") -> List[Dict]:
    prompts = [_normalize_prompt(p) for p in _load()]
    if app_name:
        prompts = [p for p in prompts if p.get("app_name", "") == app_name]
    if programming_language:
        prompts = [p for p in prompts if p.get("programming_language", "") == programming_language]
    if framework:
        prompts = [p for p in prompts if p.get("framework", "") == framework]
    return prompts


def get_unique_values(field: str) -> List[str]:
    vals = []
    seen = set()
    for p in [_normalize_prompt(x) for x in _load()]:
        v = (p.get(field) or "").strip()
        if v and v not in seen:
            seen.add(v)
            vals.append(v)
    return sorted(vals)


def export_prompts(path: Path, fmt: str = "json") -> Path:
    """Export prompt library in JSON or Markdown format."""
    prompts = get_all_prompts()
    path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        path.write_text(json.dumps(prompts, indent=2, ensure_ascii=False), encoding="utf-8")
    elif fmt == "markdown":
        lines = ["# Prompt Library\n\n"]
        for p in prompts:
            tags = ", ".join(p.get("tags", []))
            lines.append(f"## {p.get('name','Untitled')}\n")
            lines.append(f"- Category: {p.get('category','')}\n")
            lines.append(f"- App: {p.get('app_name','')}\n")
            lines.append(f"- Project: {p.get('project_name','')}\n")
            lines.append(f"- Language: {p.get('programming_language','')}\n")
            lines.append(f"- Framework: {p.get('framework','')}\n")
            lines.append(f"- Version: {p.get('prompt_version','v1')}\n")
            lines.append(f"- Feature: {p.get('feature_name','')}\n")
            lines.append(f"- Tags: {tags}\n\n")
            lines.append(f"{p.get('description','')}\n\n")
            lines.append("```\n")
            lines.append(p.get("text", "") + "\n")
            lines.append("```\n\n")
        path.write_text("".join(lines), encoding="utf-8")
    else:
        raise ValueError(f"Unsupported export format: {fmt}")

    return path


def import_prompts(path: Path, merge_duplicates: bool = True) -> int:
    """Import prompts from JSON array file. Returns number of imported items."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Prompt import expects a JSON array")

    existing = [_normalize_prompt(p) for p in _load()]
    existing_ids = {p.get("id") for p in existing}
    existing_sig = {
        (
            (p.get("name") or "").strip().lower(),
            (p.get("text") or "").strip(),
            (p.get("app_name") or "").strip().lower(),
            (p.get("project_name") or "").strip().lower(),
            (p.get("prompt_version") or "").strip().lower(),
            (p.get("feature_name") or "").strip().lower(),
        )
        for p in existing
    }
    imported = 0

    for raw in data:
        if not isinstance(raw, dict):
            continue
        p = _normalize_prompt(raw)

        sig = (
            (p.get("name") or "").strip().lower(),
            (p.get("text") or "").strip(),
            (p.get("app_name") or "").strip().lower(),
            (p.get("project_name") or "").strip().lower(),
            (p.get("prompt_version") or "").strip().lower(),
            (p.get("feature_name") or "").strip().lower(),
        )
        if merge_duplicates and sig in existing_sig:
            continue

        if not p.get("id") or p.get("id") in existing_ids:
            p["id"] = f"p_{int(time.time() * 1000)}_{imported}"

        existing.append(p)
        existing_ids.add(p["id"])
        existing_sig.add(sig)
        imported += 1

    _save(existing)
    return imported


def get_app_prompt_timeline(app_name: str) -> List[Dict]:
    """Return prompts for a specific app, ordered chronologically."""
    if not app_name:
        return []
    prompts = [
        _normalize_prompt(p)
        for p in _load()
        if (p.get("app_name") or "") == app_name
    ]
    return sorted(prompts, key=lambda p: (p.get("created_at", ""), p.get("prompt_version", "")))


def get_prompt_feature_map(app_name: str = "") -> Dict[str, List[Dict]]:
    """Return mapping: feature_name -> prompt entries (optionally filtered by app)."""
    prompts = [_normalize_prompt(p) for p in _load()]
    if app_name:
        prompts = [p for p in prompts if (p.get("app_name") or "") == app_name]
    mapping: Dict[str, List[Dict]] = {}
    for p in prompts:
        feature = (p.get("feature_name") or "").strip() or "(unmapped)"
        mapping.setdefault(feature, []).append(p)
    for feature in list(mapping.keys()):
        mapping[feature] = sorted(mapping[feature], key=lambda x: x.get("created_at", ""))
    return mapping
