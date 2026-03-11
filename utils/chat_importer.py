"""
Universal Chat Importer
Supports: ChatGPT, Claude.ai, Gemini (Google Takeout), Perplexity, Copilot, Character.AI
"""
from __future__ import annotations

import json
import logging
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ImportedMessage:
    role: str
    content: str
    timestamp: Optional[str] = None


@dataclass
class ImportedChat:
    title: str
    source: str
    messages: List[ImportedMessage]
    created_at: Optional[str] = None
    original_id: Optional[str] = None


class ChatImporter:
    """Detect and parse chat exports from all major AI platforms."""

    @staticmethod
    def detect_and_parse(file_path: str) -> Tuple[str, List[ImportedChat]]:
        path = Path(file_path)
        if not path.exists():
            return "Error", []

        ext = path.suffix.lower()
        if ext == ".zip":
            return ChatImporter._handle_zip(path)
        if ext == ".json":
            return ChatImporter._handle_json(path)
        if ext == ".jsonl":
            return ChatImporter._handle_jsonl(path)
        return "Unknown", []

    # ── ZIP dispatcher ───────────────────────────────────────────────────────
    @staticmethod
    def _handle_zip(path: Path) -> Tuple[str, List[ImportedChat]]:
        try:
            with zipfile.ZipFile(path, "r") as z:
                names = z.namelist()
                name_set = set(n.lower() for n in names)

                # ── ChatGPT ──────────────────────────────────────────────────
                # Official export: conversations.json + user.json + message_feedback.json
                if "conversations.json" in names:
                    with z.open("conversations.json") as f:
                        data = json.load(f)
                    # Differentiate: ChatGPT has "mapping" key per conversation
                    # Claude.ai has "uuid" + "chat_messages"
                    if isinstance(data, list) and data:
                        first = data[0]
                        if "mapping" in first:
                            return "ChatGPT", ChatImporter._parse_chatgpt(data)
                        if "uuid" in first or "chat_messages" in first:
                            return "Claude.ai", ChatImporter._parse_claude(data)

                # ── Gemini / Google Takeout ──────────────────────────────────
                # Structure: Takeout/Gemini/... or My Activity/Gemini/...
                gemini_files = [n for n in names
                                if "gemini" in n.lower() and n.endswith(".json")]
                if gemini_files:
                    all_chats = []
                    for fname in gemini_files:
                        with z.open(fname) as f:
                            data = json.load(f)
                        all_chats.extend(ChatImporter._parse_gemini_takeout(data))
                    if all_chats:
                        return "Gemini", all_chats

                # Older Gemini: single "bard_*" or "conversations.json"
                bard_files = [n for n in names if "bard" in n.lower() and n.endswith(".json")]
                if bard_files:
                    with z.open(bard_files[0]) as f:
                        data = json.load(f)
                    return "Gemini", ChatImporter._parse_gemini_takeout(data)

                # ── Perplexity ───────────────────────────────────────────────
                perplexity_files = [n for n in names if "perplexity" in n.lower()]
                if perplexity_files:
                    for fname in perplexity_files:
                        with z.open(fname) as f:
                            data = json.load(f)
                        result = ChatImporter._parse_perplexity(data)
                        if result:
                            return "Perplexity", result

                # ── Copilot (Microsoft) ──────────────────────────────────────
                copilot_files = [n for n in names
                                 if ("copilot" in n.lower() or "bing" in n.lower())
                                 and n.endswith(".json")]
                if copilot_files:
                    with z.open(copilot_files[0]) as f:
                        data = json.load(f)
                    result = ChatImporter._parse_copilot(data)
                    if result:
                        return "Copilot", result

                # ── Fallback: iterate JSON files and try all parsers ─────────
                json_files = [n for n in names if n.endswith(".json")]
                for fname in json_files[:5]:
                    try:
                        with z.open(fname) as f:
                            data = json.load(f)
                        result = ChatImporter._try_all_parsers(data)
                        if result:
                            source, chats = result
                            return source, chats
                    except Exception:
                        pass

            return "Unknown", []
        except Exception as e:
            logger.error(f"Error reading ZIP: {e}")
            return "Error", []

    # ── JSON file dispatcher ─────────────────────────────────────────────────
    @staticmethod
    def _handle_json(path: Path) -> Tuple[str, List[ImportedChat]]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            result = ChatImporter._try_all_parsers(data)
            return result if result else ("Unknown", [])
        except Exception as e:
            logger.error(f"Error reading JSON: {e}")
            return "Error", []

    @staticmethod
    def _handle_jsonl(path: Path) -> Tuple[str, List[ImportedChat]]:
        """Import a single JSONL file (BetterLLM native or generic)."""
        messages = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        role = obj.get("role", "user")
                        content = obj.get("content", "")
                        ts = obj.get("timestamp")
                        if content:
                            messages.append(ImportedMessage(role=role, content=content, timestamp=ts))
                    except Exception:
                        pass
            if messages:
                title = path.stem.replace("_", " ")
                return "BetterLLM", [ImportedChat(title=title, source="BetterLLM", messages=messages)]
        except Exception as e:
            logger.error(f"Error reading JSONL: {e}")
        return "Unknown", []

    @staticmethod
    def _try_all_parsers(data) -> Optional[Tuple[str, List[ImportedChat]]]:
        """Try all parsers and return the first successful result."""
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                if "mapping" in first:
                    chats = ChatImporter._parse_chatgpt(data)
                    if chats:
                        return "ChatGPT", chats
                if "uuid" in first or "chat_messages" in first:
                    chats = ChatImporter._parse_claude(data)
                    if chats:
                        return "Claude.ai", chats
                if "answer" in first or "query" in first:
                    chats = ChatImporter._parse_perplexity(data)
                    if chats:
                        return "Perplexity", chats

        if isinstance(data, dict):
            if "conversations" in data:
                chats = ChatImporter._parse_gemini_takeout(data["conversations"])
                if chats:
                    return "Gemini", chats
            if "title" in data and "mapping" in data:
                chats = ChatImporter._parse_chatgpt([data])
                if chats:
                    return "ChatGPT", chats
            if "items" in data:
                chats = ChatImporter._parse_copilot(data)
                if chats:
                    return "Copilot", chats

        return None

    # ── ChatGPT parser ───────────────────────────────────────────────────────
    @staticmethod
    def _parse_chatgpt(data: List[Dict]) -> List[ImportedChat]:
        chats = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            title = entry.get("title", "Untitled ChatGPT Chat") or "Untitled ChatGPT Chat"
            mapping = entry.get("mapping", {})
            if not mapping:
                continue

            # Build node list sorted by create_time
            nodes = []
            for node_id, node in mapping.items():
                msg = node.get("message")
                if msg:
                    nodes.append((msg.get("create_time") or 0, node))
            nodes.sort(key=lambda x: x[0])

            messages = []
            for _, node in nodes:
                msg = node.get("message")
                if not msg:
                    continue
                author = msg.get("author", {})
                role_raw = author.get("role", "")
                if role_raw not in ("user", "assistant", "tool"):
                    continue
                role = "user" if role_raw == "user" else "assistant"

                content_obj = msg.get("content", {})
                if not content_obj:
                    continue
                content_type = content_obj.get("content_type", "text")
                content = ""
                if content_type == "text":
                    parts = content_obj.get("parts", [])
                    for part in parts:
                        if isinstance(part, str):
                            content += part
                        elif isinstance(part, dict) and "text" in part:
                            content += part["text"]
                elif content_type == "tether_browsing_display":
                    # Web search results – skip
                    continue

                content = content.strip()
                if not content:
                    continue

                ts = None
                ct = msg.get("create_time")
                if ct:
                    try:
                        ts = datetime.fromtimestamp(ct).isoformat()
                    except Exception:
                        pass

                messages.append(ImportedMessage(role=role, content=content, timestamp=ts))

            if messages:
                created_at = None
                ct = entry.get("create_time")
                if ct:
                    try:
                        created_at = datetime.fromtimestamp(ct).isoformat()
                    except Exception:
                        pass
                chats.append(ImportedChat(
                    title=title,
                    source="ChatGPT",
                    messages=messages,
                    created_at=created_at,
                    original_id=entry.get("id"),
                ))
        return chats

    # ── Claude.ai parser ─────────────────────────────────────────────────────
    @staticmethod
    def _parse_claude(data: List[Dict]) -> List[ImportedChat]:
        chats = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            title = entry.get("name", "Untitled Claude Chat") or "Untitled Claude Chat"
            messages = []
            for m in entry.get("chat_messages", []):
                sender = m.get("sender", "")
                role = "user" if sender == "human" else "assistant"
                # Claude content can be a list of content blocks
                text = m.get("text", "")
                if not text:
                    for block in m.get("content", []):
                        if isinstance(block, dict) and block.get("type") == "text":
                            text += block.get("text", "")
                if text.strip():
                    messages.append(ImportedMessage(
                        role=role,
                        content=text.strip(),
                        timestamp=m.get("created_at"),
                    ))
            if messages:
                chats.append(ImportedChat(
                    title=title,
                    source="Claude.ai",
                    messages=messages,
                    created_at=entry.get("created_at"),
                    original_id=entry.get("uuid"),
                ))
        return chats

    # ── Gemini / Google Takeout parser ───────────────────────────────────────
    @staticmethod
    def _parse_gemini_takeout(data) -> List[ImportedChat]:
        chats = []
        # Google Takeout wraps in {"conversations": [...]}
        if isinstance(data, dict):
            data = data.get("conversations", data.get("items", [data]))

        if not isinstance(data, list):
            data = [data]

        for entry in data:
            if not isinstance(entry, dict):
                continue
            title = entry.get("title", entry.get("name", "Untitled Gemini Chat"))
            messages = []
            # Format 1: {"content": [{"author": "user", "text": "..."}]}
            for turn in entry.get("content", []):
                role = "user" if turn.get("author", "").lower() == "user" else "assistant"
                text = turn.get("text", "") or turn.get("content", "")
                if text.strip():
                    messages.append(ImportedMessage(role=role, content=text.strip()))
            # Format 2: {"turns": [{"role": "user", "parts": [{"text": "..."}]}]}
            if not messages:
                for turn in entry.get("turns", []):
                    role = "user" if turn.get("role", "").lower() == "user" else "assistant"
                    text = ""
                    for part in turn.get("parts", []):
                        text += part.get("text", "")
                    if text.strip():
                        messages.append(ImportedMessage(role=role, content=text.strip()))
            if messages:
                chats.append(ImportedChat(
                    title=title,
                    source="Gemini",
                    messages=messages,
                    original_id=entry.get("id"),
                ))
        return chats

    # ── Perplexity parser ────────────────────────────────────────────────────
    @staticmethod
    def _parse_perplexity(data) -> List[ImportedChat]:
        chats = []
        if isinstance(data, dict):
            data = data.get("threads", data.get("conversations", [data]))
        if not isinstance(data, list):
            return []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            title = entry.get("title", entry.get("query", "Untitled Perplexity Chat"))
            if isinstance(title, dict):
                title = "Untitled Perplexity Chat"
            messages = []
            # Format: {"query": "...", "answer": "...", "follow_up": [...]}
            q = entry.get("query", entry.get("user_query", ""))
            a = entry.get("answer", entry.get("response", ""))
            if q:
                messages.append(ImportedMessage(role="user", content=q))
            if a:
                messages.append(ImportedMessage(role="assistant", content=a))
            # Follow-up exchanges
            for fu in entry.get("follow_up", entry.get("exchanges", [])):
                fq = fu.get("query", fu.get("user_query", ""))
                fa = fu.get("answer", fu.get("response", ""))
                if fq:
                    messages.append(ImportedMessage(role="user", content=fq))
                if fa:
                    messages.append(ImportedMessage(role="assistant", content=fa))
            if messages:
                chats.append(ImportedChat(
                    title=str(title)[:100],
                    source="Perplexity",
                    messages=messages,
                    original_id=entry.get("id"),
                ))
        return chats

    # ── Copilot / Microsoft Bing parser ─────────────────────────────────────
    @staticmethod
    def _parse_copilot(data) -> List[ImportedChat]:
        chats = []
        if isinstance(data, dict):
            data = data.get("items", data.get("conversations", []))
        if not isinstance(data, list):
            return []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            title = entry.get("title", "Untitled Copilot Chat")
            messages = []
            for msg in entry.get("messages", entry.get("turns", [])):
                role_raw = msg.get("role", msg.get("author", "")).lower()
                role = "user" if role_raw in ("user", "human") else "assistant"
                text = msg.get("text", msg.get("content", msg.get("message", "")))
                if isinstance(text, list):
                    text = " ".join(str(t) for t in text)
                if str(text).strip():
                    messages.append(ImportedMessage(role=role, content=str(text).strip()))
            if messages:
                chats.append(ImportedChat(
                    title=title,
                    source="Copilot",
                    messages=messages,
                    original_id=entry.get("id"),
                ))
        return chats

    # ── Save to BetterLLM format ─────────────────────────────────────────────
    @staticmethod
    def save_to_betterllm(chat: ImportedChat, target_dir: Path,
                          subfolder: str = "imported") -> str:
        dest_dir = target_dir / subfolder
        dest_dir.mkdir(parents=True, exist_ok=True)

        clean_title = re.sub(r'[\\/*?:"<>|]', "", chat.title)
        clean_title = clean_title.replace(" ", "_")[:60]
        if not clean_title:
            clean_title = "chat"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{clean_title}_{timestamp}.jsonl"
        file_path = dest_dir / filename

        counter = 1
        while file_path.exists():
            file_path = dest_dir / f"{clean_title}_{timestamp}_{counter}.jsonl"
            counter += 1

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                for msg in chat.messages:
                    line = {
                        "role": msg.role,
                        "content": msg.content,
                        "timestamp": msg.timestamp or datetime.now().isoformat(),
                    }
                    f.write(json.dumps(line, ensure_ascii=False) + "\n")
            return str(file_path)
        except Exception as e:
            logger.error(f"Failed to save chat: {e}")
            return ""
