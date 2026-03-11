"""
Chat Export System
Exports chat histories in multiple formats: Markdown, JSON, TXT, HTML.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pygments import highlight
from pygments.lexers import get_lexer_by_name, TextLexer
from pygments.formatters import HtmlFormatter

logger = logging.getLogger(__name__)


def _load_messages(chat_path: Path) -> List[dict]:
    messages = []
    with open(chat_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return messages


def _highlight_code_html(code: str, lang: str) -> str:
    try:
        lexer = get_lexer_by_name(lang, stripall=True)
    except Exception:
        lexer = TextLexer(stripall=True)
    formatter = HtmlFormatter(style="monokai", noclasses=True)
    return highlight(code, lexer, formatter)


def _messages_to_markdown(messages: List[dict], chat_name: str) -> str:
    lines = [f"# Chat: {chat_name}\n", f"*Exported: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n---\n"]
    for m in messages:
        role = "**You**" if m.get("role") == "user" else "**Assistant**"
        ts = m.get("timestamp", "")
        if ts:
            try:
                ts = datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
        lines.append(f"### {role}  _{ts}_\n")
        lines.append(f"{m.get('content', '')}\n\n")
        lines.append("---\n\n")
    return "".join(lines)


def _messages_to_txt(messages: List[dict], chat_name: str) -> str:
    lines = [f"Chat: {chat_name}", f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M')}", "=" * 60, ""]
    for m in messages:
        role = "You" if m.get("role") == "user" else "Assistant"
        lines.append(f"[{role}]")
        lines.append(m.get("content", ""))
        lines.append("-" * 40)
        lines.append("")
    return "\n".join(lines)


def _messages_to_html(messages: List[dict], chat_name: str) -> str:
    pygments_css = HtmlFormatter(style="monokai", noclasses=True).get_style_defs("pre")

    def render_content(content: str) -> str:
        result = []
        # Find code blocks
        pattern = re.compile(r"```(\w*)\n(.*?)\n?```", re.DOTALL)
        last_end = 0
        for m in pattern.finditer(content):
            # Plain text before code block
            plain = content[last_end:m.start()].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            result.append(f"<p>{plain.replace(chr(10), '<br>')}</p>")
            lang = m.group(1) or "text"
            code = m.group(2)
            highlighted = _highlight_code_html(code, lang)
            result.append(f'<div class="code-block"><span class="lang-badge">{lang}</span><pre>{highlighted}</pre></div>')
            last_end = m.end()
        # Remaining text
        plain = content[last_end:].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if plain.strip():
            result.append(f"<p>{plain.replace(chr(10), '<br>')}</p>")
        return "".join(result)

    body_parts = []
    for m in messages:
        role = m.get("role", "user")
        cls = "user-msg" if role == "user" else "assistant-msg"
        role_label = "You" if role == "user" else "Assistant"
        ts = m.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts).strftime("%H:%M")
        except Exception:
            pass
        content_html = render_content(m.get("content", ""))
        body_parts.append(f"""
        <div class="message {cls}">
            <div class="msg-header"><span class="role">{role_label}</span> <span class="ts">{ts}</span></div>
            <div class="msg-body">{content_html}</div>
        </div>""")

    messages_html = "\n".join(body_parts)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{chat_name}</title>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; background: #1a1a2e; color: #e0e0e0; max-width: 900px; margin: 0 auto; padding: 20px; }}
  h1 {{ color: #7c83fd; border-bottom: 2px solid #7c83fd; padding-bottom: 10px; }}
  .subtitle {{ color: #888; font-size: 0.9em; margin-bottom: 30px; }}
  .message {{ margin-bottom: 24px; border-radius: 12px; padding: 16px; }}
  .user-msg {{ background: #16213e; border-left: 4px solid #7c83fd; }}
  .assistant-msg {{ background: #0f3460; border-left: 4px solid #e94560; }}
  .msg-header {{ font-weight: bold; margin-bottom: 8px; }}
  .role {{ font-size: 1em; }}
  .user-msg .role {{ color: #7c83fd; }}
  .assistant-msg .role {{ color: #e94560; }}
  .ts {{ color: #666; font-size: 0.8em; font-weight: normal; margin-left: 8px; }}
  .msg-body {{ line-height: 1.6; }}
  .code-block {{ position: relative; margin: 10px 0; border-radius: 8px; overflow: hidden; }}
  .lang-badge {{ position: absolute; top: 6px; right: 10px; background: #333; color: #aaa; font-size: 0.75em; padding: 2px 8px; border-radius: 4px; }}
  pre {{ margin: 0; padding: 16px; background: #1e1e1e; overflow-x: auto; font-family: 'Consolas', monospace; font-size: 13px; }}
  p {{ margin: 4px 0; }}
  {pygments_css}
</style>
</head>
<body>
<h1>💬 {chat_name}</h1>
<div class="subtitle">Exported from BetterLLM · {datetime.now().strftime("%Y-%m-%d %H:%M")}</div>
{messages_html}
</body>
</html>"""


def export_chat(
    chat_path: Path,
    output_dir: Path,
    fmt: str = "markdown",
) -> Optional[Path]:
    """
    Export a single chat file.
    fmt: 'markdown', 'json', 'txt', 'html'
    Returns the output file path or None on failure.
    """
    try:
        messages = _load_messages(chat_path)
        chat_name = chat_path.stem
        output_dir.mkdir(parents=True, exist_ok=True)

        if fmt == "markdown":
            content = _messages_to_markdown(messages, chat_name)
            out = output_dir / f"{chat_name}.md"
            out.write_text(content, encoding="utf-8")
        elif fmt == "json":
            out = output_dir / f"{chat_name}.json"
            out.write_text(json.dumps(messages, indent=2, ensure_ascii=False), encoding="utf-8")
        elif fmt == "txt":
            content = _messages_to_txt(messages, chat_name)
            out = output_dir / f"{chat_name}.txt"
            out.write_text(content, encoding="utf-8")
        elif fmt == "html":
            content = _messages_to_html(messages, chat_name)
            out = output_dir / f"{chat_name}.html"
            out.write_text(content, encoding="utf-8")
        else:
            raise ValueError(f"Unknown format: {fmt}")

        logger.info("Exported %s → %s", chat_path.name, out)
        return out
    except Exception as e:
        logger.error("Export failed for %s: %s", chat_path, e)
        return None


def export_folder(
    folder_path: Path,
    output_dir: Path,
    fmt: str = "markdown",
) -> List[Path]:
    """Export all chats in a folder directory."""
    results = []
    for chat_file in sorted(folder_path.glob("*.jsonl")):
        out = export_chat(chat_file, output_dir / folder_path.name, fmt)
        if out:
            results.append(out)
    return results
