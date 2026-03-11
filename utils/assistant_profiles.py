"""
Assistant Profiles
Manages different AI personalities with unique system prompts.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from .paths import get_base_dir

logger = logging.getLogger(__name__)

PROFILES_FILE = get_base_dir() / "profiles.json"

DEFAULT_PROFILES = {
    "Default": {
        "icon": "🤖",
        "description": "Helpful general-purpose assistant",
        "system_prompt": "You are a helpful, harmless, and honest AI assistant.",
        "color": "#7c83fd",
    },
    "Coder": {
        "icon": "💻",
        "description": "Expert software engineer",
        "system_prompt": (
            "You are an expert software engineer. Provide clean, efficient, well-documented code. "
            "Always explain your reasoning, suggest best practices, and point out potential issues. "
            "Prefer modern idioms and production-quality solutions."
        ),
        "color": "#3fb950",
    },
    "Researcher": {
        "icon": "🔬",
        "description": "Thorough academic researcher",
        "system_prompt": (
            "You are a thorough academic researcher. Provide detailed, well-structured answers with "
            "clear reasoning. Distinguish facts from speculation, cite limitations, and suggest "
            "further reading directions when relevant."
        ),
        "color": "#58a6ff",
    },
    "Creative Writer": {
        "icon": "✍️",
        "description": "Imaginative creative writing partner",
        "system_prompt": (
            "You are a skilled creative writer. Help craft vivid, engaging narratives with strong "
            "characters, rich descriptions, and compelling dialogue. Embrace imagination, originality, "
            "and emotional resonance in all writing."
        ),
        "color": "#e94560",
    },
    "Teacher": {
        "icon": "📖",
        "description": "Patient and clear educator",
        "system_prompt": (
            "You are a patient and encouraging teacher. Break down complex concepts into simple, "
            "digestible explanations. Use analogies, examples, and step-by-step reasoning. "
            "Always check understanding and encourage questions."
        ),
        "color": "#d29922",
    },
    "Debater": {
        "icon": "⚔️",
        "description": "Sharp critical thinker",
        "system_prompt": (
            "You are a sharp critical thinker and debater. Challenge assumptions, identify logical "
            "fallacies, present multiple perspectives, and stress-test ideas rigorously. "
            "Be intellectually honest and argue in good faith."
        ),
        "color": "#ff7b72",
    },
}


def load_profiles() -> Dict[str, dict]:
    profiles = dict(DEFAULT_PROFILES)
    try:
        if PROFILES_FILE.exists():
            with open(PROFILES_FILE, "r", encoding="utf-8") as f:
                custom = json.load(f)
            profiles.update(custom)
    except Exception as e:
        logger.warning("Could not load profiles: %s", e)
    return profiles


def save_profiles(profiles: Dict[str, dict]) -> None:
    # Only save non-default profiles (user-created/modified)
    custom = {k: v for k, v in profiles.items() if k not in DEFAULT_PROFILES}
    try:
        with open(PROFILES_FILE, "w", encoding="utf-8") as f:
            json.dump(custom, f, indent=2)
    except Exception as e:
        logger.error("Could not save profiles: %s", e)


def get_profile(name: str) -> Optional[dict]:
    return load_profiles().get(name)


def get_profile_names() -> List[str]:
    return list(load_profiles().keys())
