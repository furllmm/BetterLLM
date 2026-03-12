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


def compute_usage_dashboard(chats_dir: Path) -> Dict:
    """Compute usage aggregates by topic and by day."""
    by_topic: Dict[str, Dict[str, int]] = defaultdict(lambda: {"chats": 0, "messages": 0, "tokens": 0})
    by_day: Dict[str, Dict[str, int]] = defaultdict(lambda: {"messages": 0, "tokens": 0})

    if not chats_dir.exists():
        return {"by_topic": {}, "by_day": {}}

    for topic_dir in chats_dir.iterdir():
        if not topic_dir.is_dir():
            continue
        topic = topic_dir.name
        for chat_file in topic_dir.glob("*.jsonl"):
            stats = compute_chat_stats(chat_file)
            if not stats:
                continue
            by_topic[topic]["chats"] += 1
            by_topic[topic]["messages"] += int(stats.get("total_messages", 0))
            by_topic[topic]["tokens"] += int(stats.get("total_tokens", 0))

            try:
                with open(chat_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            m = json.loads(line)
                        except Exception:
                            continue
                        ts = m.get("timestamp", "")
                        day = ts[:10] if len(ts) >= 10 else "unknown"
                        by_day[day]["messages"] += 1
                        by_day[day]["tokens"] += len(m.get("content", "")) // 4
            except Exception:
                pass

    by_topic_sorted = dict(sorted(by_topic.items(), key=lambda kv: kv[1]["tokens"], reverse=True))
    by_day_sorted = dict(sorted(by_day.items(), key=lambda kv: kv[0], reverse=True))
    return {"by_topic": by_topic_sorted, "by_day": by_day_sorted}
