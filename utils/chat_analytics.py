"""
Chat Analytics
Tracks and computes statistics for chat sessions.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def compute_chat_stats(chat_path: Path) -> Dict:
    """Compute statistics for a single chat file."""
    messages = []
    try:
        with open(chat_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        messages.append(json.loads(line))
                    except Exception:
                        pass
    except Exception as e:
        logger.error("Could not read chat for analytics: %s", e)
        return {}

    if not messages:
        return {}

    user_msgs = [m for m in messages if m.get("role") == "user"]
    asst_msgs = [m for m in messages if m.get("role") == "assistant"]

    total_chars = sum(len(m.get("content", "")) for m in messages)
    user_chars = sum(len(m.get("content", "")) for m in user_msgs)
    asst_chars = sum(len(m.get("content", "")) for m in asst_msgs)

    # Estimate tokens (~4 chars per token)
    total_tokens = total_chars // 4
    user_tokens = user_chars // 4
    asst_tokens = asst_chars // 4

    # Response times
    response_times = []
    for i in range(1, len(messages)):
        prev = messages[i - 1]
        curr = messages[i]
        if prev.get("role") == "user" and curr.get("role") == "assistant":
            try:
                t1 = datetime.fromisoformat(prev["timestamp"])
                t2 = datetime.fromisoformat(curr["timestamp"])
                delta = (t2 - t1).total_seconds()
                if 0 < delta < 300:  # max 5 min
                    response_times.append(delta)
            except Exception:
                pass

    avg_resp = sum(response_times) / len(response_times) if response_times else 0

    # Date range
    try:
        first_ts = datetime.fromisoformat(messages[0]["timestamp"])
        last_ts = datetime.fromisoformat(messages[-1]["timestamp"])
        duration_mins = (last_ts - first_ts).total_seconds() / 60
    except Exception:
        first_ts = last_ts = None
        duration_mins = 0

    return {
        "total_messages": len(messages),
        "user_messages": len(user_msgs),
        "assistant_messages": len(asst_msgs),
        "total_tokens": total_tokens,
        "user_tokens": user_tokens,
        "assistant_tokens": asst_tokens,
        "avg_response_time_s": round(avg_resp, 1),
        "duration_minutes": round(duration_mins, 1),
        "first_message": first_ts.strftime("%Y-%m-%d %H:%M") if first_ts else "—",
        "last_message": last_ts.strftime("%Y-%m-%d %H:%M") if last_ts else "—",
    }


def compute_folder_stats(chats_dir: Path) -> Dict:
    """Aggregate stats across all chats."""
    totals = defaultdict(int)
    chat_count = 0
    for topic_dir in chats_dir.iterdir():
        if not topic_dir.is_dir():
            continue
        for chat_file in topic_dir.glob("*.jsonl"):
            stats = compute_chat_stats(chat_file)
            if stats:
                chat_count += 1
                for k, v in stats.items():
                    if isinstance(v, (int, float)):
                        totals[k] += v
    totals["chat_count"] = chat_count
    return dict(totals)
