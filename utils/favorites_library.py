"""Favorites Library
Stores user workflow preferences for AI personalization.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

from .paths import get_base_dir

logger = logging.getLogger(__name__)

FAVORITES_FILE = get_base_dir() / "favorites" / "library.json"

_DEFAULT_PROFILE = {
    "preferences": [],
    "favorite_software": [],
    "installed_tools": [],
    "environments": [],
    "favorite_languages": [],
    "interests_hobbies": [],
    "notes": "",
}


def _ensure_dir() -> None:
    FAVORITES_FILE.parent.mkdir(parents=True, exist_ok=True)


def _normalize_list(values: Optional[List[str]]) -> List[str]:
    out: List[str] = []
    seen = set()
    for v in values or []:
        s = (str(v) if v is not None else "").strip()
        k = s.casefold()
        if s and k not in seen:
            out.append(s)
            seen.add(k)
    return out


def _normalize_profile(profile: Optional[Dict]) -> Dict:
    p = dict(_DEFAULT_PROFILE)
    p.update(profile or {})
    for key in [
        "preferences",
        "favorite_software",
        "installed_tools",
        "environments",
        "favorite_languages",
        "interests_hobbies",
    ]:
        p[key] = _normalize_list(p.get(key))
    p["notes"] = (p.get("notes") or "").strip()
    return p


def load_profile() -> Dict:
    _ensure_dir()
    if FAVORITES_FILE.exists():
        try:
            raw = json.loads(FAVORITES_FILE.read_text(encoding="utf-8"))
            return _normalize_profile(raw)
        except Exception as e:
            logger.warning("Favorites profile load failed: %s", e)
    return dict(_DEFAULT_PROFILE)


def save_profile(profile: Dict) -> Dict:
    _ensure_dir()
    normalized = _normalize_profile(profile)
    FAVORITES_FILE.write_text(json.dumps(normalized, indent=2, ensure_ascii=False), encoding="utf-8")
    return normalized


def update_profile(**kwargs) -> Dict:
    profile = load_profile()
    profile.update(kwargs)
    return save_profile(profile)


def build_personalization_context(profile: Optional[Dict] = None) -> str:
    p = _normalize_profile(profile or load_profile())
    lines: List[str] = []

    def _add(label: str, values: List[str]) -> None:
        if values:
            lines.append(f"- {label}: {', '.join(values)}")

    _add("User preferences", p["preferences"])
    _add("Favorite software", p["favorite_software"])
    _add("Installed tools", p["installed_tools"])
    _add("Environment", p["environments"])
    _add("Favorite programming languages", p["favorite_languages"])
    _add("Interests / hobbies", p["interests_hobbies"])
    if p["notes"]:
        lines.append(f"- Notes: {p['notes']}")

    if not lines:
        return ""

    return (
        "User Workflow Profile:\n"
        + "\n".join(lines)
        + "\n- Personalization rule: prefer suggestions and examples compatible with installed tools/environments; "
          "adapt tone and examples to user interests when relevant."
    )


def personalize_suggestions(suggestions: List[str], profile: Optional[Dict] = None, limit: int = 4) -> List[str]:
    """Prioritize suggestions that match user workflow profile fields."""
    p = _normalize_profile(profile or load_profile())

    weighted_terms: List[tuple] = []
    for key, weight in [
        ("installed_tools", 4),
        ("environments", 4),
        ("favorite_languages", 3),
        ("preferences", 3),
        ("favorite_software", 2),
        ("interests_hobbies", 1),
    ]:
        for term in _normalize_list(p.get(key, [])):
            normalized = term.casefold()
            if len(normalized) >= 2:
                weighted_terms.append((normalized, weight))

    scored = []
    for i, suggestion in enumerate(suggestions or []):
        text = (suggestion or "").strip()
        if not text:
            continue
        low = text.casefold()
        token_score = 0
        hit_count = 0
        for term, weight in weighted_terms:
            if not term:
                continue
            # Prefer token-like matches to reduce accidental substring hits.
            pattern = rf"(?<!\w){re.escape(term)}(?!\w)"
            if re.search(pattern, low):
                token_score += weight
                hit_count += 1
            elif term in low:
                token_score += max(1, weight - 1)
                hit_count += 1
        scored.append((token_score, hit_count, i, text))

    scored.sort(key=lambda x: (-x[0], -x[1], x[2]))

    out: List[str] = []
    seen = set()
    for _, _, _, text in scored:
        k = text.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(text)
        if len(out) >= max(1, int(limit)):
            break
    return out
