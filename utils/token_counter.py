"""
Token Counter
Fast heuristic-based token estimation (no model required).
Uses ~4 chars/token approximation, similar to GPT tokenizer behavior.
"""
from __future__ import annotations

import re
from typing import List


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for a given string.
    Heuristic: ~4 characters per token on average for English text.
    Punctuation and code blocks are weighted slightly differently.
    """
    if not text:
        return 0
    # Count code blocks separately (denser)
    code_pattern = re.compile(r"```.*?```", re.DOTALL)
    code_blocks = code_pattern.findall(text)
    code_chars = sum(len(b) for b in code_blocks)
    rest_chars = len(text) - code_chars

    # Code is slightly denser: ~3.5 chars/token
    # Normal prose: ~4 chars/token
    return max(1, int(code_chars / 3.5 + rest_chars / 4.0))


def estimate_messages_tokens(messages: List[dict]) -> int:
    """Total estimated tokens for a list of message dicts."""
    total = 0
    for m in messages:
        total += estimate_tokens(m.get("content", ""))
        total += 4  # role overhead
    return total


def context_usage_percent(used_tokens: int, ctx_size: int) -> float:
    """Return percentage of context used (0–100)."""
    if ctx_size <= 0:
        return 0.0
    return min(100.0, used_tokens / ctx_size * 100.0)


def context_status(used_tokens: int, ctx_size: int) -> str:
    """Return a human-readable status string."""
    pct = context_usage_percent(used_tokens, ctx_size)
    if pct >= 90:
        return "critical"
    elif pct >= 75:
        return "warning"
    elif pct >= 50:
        return "moderate"
    return "ok"
