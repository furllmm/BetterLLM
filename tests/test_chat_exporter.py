import json
from pathlib import Path

from utils.chat_exporter import export_chat, export_folder, export_folder_detailed
from utils.chat_exporter import export_chat, export_folder


def _write_chat(path: Path, messages: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for m in messages:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")


def test_export_chat_markdown_preserves_code_blocks(tmp_path: Path):
    chat = tmp_path / "chat.jsonl"
    _write_chat(chat, [
        {"role": "user", "content": "show code", "timestamp": "2024-01-01T00:00:00"},
        {"role": "assistant", "content": "```python\nprint('ok')\n```", "timestamp": "2024-01-01T00:00:01"},
    ])

    out = export_chat(chat, tmp_path / "out", fmt="markdown")
    assert out is not None
    text = out.read_text(encoding="utf-8")
    assert "```python" in text
    assert "print('ok')" in text


def test_export_chat_html_supports_plus_language_tags(tmp_path: Path):
    chat = tmp_path / "cpp_chat.jsonl"
    _write_chat(chat, [
        {"role": "assistant", "content": "```c++\nint main(){}\n```", "timestamp": "2024-01-01T00:00:00"},
    ])

    out = export_chat(chat, tmp_path / "out", fmt="html")
    assert out is not None
    html = out.read_text(encoding="utf-8")
    assert "c++" in html
    assert "int" in html and "main" in html


def test_export_folder_exports_all_jsonl(tmp_path: Path):
    folder = tmp_path / "topic"
    folder.mkdir()
    _write_chat(folder / "a.jsonl", [{"role": "user", "content": "A", "timestamp": "2024-01-01T00:00:00"}])
    _write_chat(folder / "b.jsonl", [{"role": "user", "content": "B", "timestamp": "2024-01-01T00:00:00"}])

    outs = export_folder(folder, tmp_path / "exports", fmt="txt")
    assert len(outs) == 2
    assert all(p.exists() for p in outs)


def test_export_chat_html_does_not_nest_pre_wrappers(tmp_path: Path):
    chat = tmp_path / "py_chat.jsonl"
    _write_chat(chat, [
        {"role": "assistant", "content": "```python\nprint(1)\n```", "timestamp": "2024-01-01T00:00:00"},
    ])

    out = export_chat(chat, tmp_path / "out", fmt="html")
    assert out is not None
    html = out.read_text(encoding="utf-8")
    assert '<pre><div class="highlight"' not in html



def test_export_folder_detailed_counts_failures(tmp_path: Path):
    folder = tmp_path / "topic2"
    folder.mkdir()
    _write_chat(folder / "ok.jsonl", [{"role": "user", "content": "A", "timestamp": "2024-01-01T00:00:00"}])
    # invalid json lines file (will parse as empty but still exportable). Force failure by invalid format call below

    summary = export_folder_detailed(folder, tmp_path / "exports", fmt="txt")
    assert summary["total"] == 1
    assert summary["success"] == 1
    assert summary["failed"] == 0


def test_export_folder_detailed_invalid_format_reports_failures(tmp_path: Path):
    folder = tmp_path / "topic3"
    folder.mkdir()
    _write_chat(folder / "a.jsonl", [{"role": "user", "content": "A", "timestamp": "2024-01-01T00:00:00"}])

    summary = export_folder_detailed(folder, tmp_path / "exports", fmt="invalid")
    assert summary["total"] == 1
    assert summary["success"] == 0
    assert summary["failed"] == 1
    assert "a.jsonl" in summary["errors"]
