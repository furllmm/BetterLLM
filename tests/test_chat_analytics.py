import json
from pathlib import Path

from utils.chat_analytics import compute_usage_dashboard


def _write_chat(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_compute_usage_dashboard_groups_by_topic_and_day(tmp_path: Path):
    _write_chat(tmp_path / "coding" / "c1.jsonl", [
        {"role": "user", "content": "hello", "timestamp": "2024-01-01T10:00:00"},
        {"role": "assistant", "content": "world", "timestamp": "2024-01-01T10:00:02"},
    ])
    _write_chat(tmp_path / "writing" / "w1.jsonl", [
        {"role": "user", "content": "draft", "timestamp": "2024-01-02T10:00:00"},
    ])

    dash = compute_usage_dashboard(tmp_path)
    assert "coding" in dash["by_topic"]
    assert dash["by_topic"]["coding"]["chats"] == 1
    assert dash["by_topic"]["coding"]["messages"] == 2
    assert "2024-01-01" in dash["by_day"]
    assert dash["by_day"]["2024-01-01"]["messages"] == 2
