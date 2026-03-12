"""
Chat Indexer
Indexes all chat files once at startup, then watches for file changes.
Re-indexes only when new/modified files are detected.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .paths import get_chats_dir

logger = logging.getLogger(__name__)


class SearchResult:
    __slots__ = ("chat_path", "message_index", "role", "content", "timestamp", "snippet", "match_start", "match_end")

    def __init__(self, chat_path: Path, message_index: int, role: str, content: str,
                 timestamp: str, snippet: str, match_start: int, match_end: int):
        self.chat_path = chat_path
        self.message_index = message_index
        self.role = role
        self.content = content
        self.timestamp = timestamp
        self.snippet = snippet
        self.match_start = match_start
        self.match_end = match_end

    @property
    def chat_name(self) -> str:
        import re
        name = self.chat_path.stem
        return re.sub(r'_\d{8}_\d{6}(?:_\d+)?$', '', name).replace("_", " ")

    @property
    def folder(self) -> str:
        return self.chat_path.parent.name


class ChatIndexer:
    """
    Maintains an in-memory index of all chats.
    Indexes once at startup, then only re-indexes when file mtimes change.
    """

    def __init__(self) -> None:
        self._index: Dict[str, List[Tuple[int, str, str, str]]] = {}
        # key: str(chat_path), value: list of (msg_idx, role, content, timestamp)
        self._mtimes: Dict[str, float] = {}   # track last-seen mtime per file
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._on_indexed: Optional[Callable[[int], None]] = None
        self._thread: Optional[threading.Thread] = None
        self._initial_index_done = False

    def start(self, on_indexed: Optional[Callable[[int], None]] = None) -> None:
        """Start indexing. Indexes once immediately, then only on changes."""
        self._on_indexed = on_indexed
        self._thread = threading.Thread(
            target=self._index_loop, name="ChatIndexer", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _index_loop(self) -> None:
        """Index once fully, then check for changed/new files every 60 seconds."""
        # Full index on first run
        self._reindex_all(full=True)
        self._initial_index_done = True

        # Subsequent runs: only re-index changed files
        while not self._stop.is_set():
            self._stop.wait(60)
            if not self._stop.is_set():
                self._reindex_changed()

    def _reindex_all(self, full: bool = False) -> None:
        """Full re-index of all files."""
        chats_dir = get_chats_dir()
        new_index: Dict[str, List[Tuple[int, str, str, str]]] = {}
        new_mtimes: Dict[str, float] = {}
        count = 0
        try:
            for topic_dir in chats_dir.iterdir():
                if not topic_dir.is_dir():
                    continue
                for chat_file in topic_dir.glob("*.jsonl"):
                    key = str(chat_file)
                    try:
                        mtime = chat_file.stat().st_mtime
                    except OSError:
                        continue
                    messages = self._load_messages(chat_file)
                    new_index[key] = [
                        (i, m.get("role", ""), m.get("content", ""), m.get("timestamp", ""))
                        for i, m in enumerate(messages)
                    ]
                    new_mtimes[key] = mtime
                    count += 1
        except Exception as e:
            logger.error("Indexing error: %s", e)
            return

        with self._lock:
            self._index = new_index
            self._mtimes = new_mtimes

        logger.info("Indexed %d chat files", count)
        if self._on_indexed:
            try:
                self._on_indexed(count)
            except Exception:
                pass

    def _reindex_changed(self) -> None:
        """Only re-index files that are new or have been modified."""
        chats_dir = get_chats_dir()
        changed = []
        deleted = []

        try:
            current_files: Dict[str, float] = {}
            for topic_dir in chats_dir.iterdir():
                if not topic_dir.is_dir():
                    continue
                for chat_file in topic_dir.glob("*.jsonl"):
                    key = str(chat_file)
                    try:
                        current_files[key] = chat_file.stat().st_mtime
                    except OSError:
                        pass

            with self._lock:
                old_mtimes = dict(self._mtimes)

            # Find changed/new files
            for key, mtime in current_files.items():
                if key not in old_mtimes or old_mtimes[key] != mtime:
                    changed.append(key)

            # Find deleted files
            for key in old_mtimes:
                if key not in current_files:
                    deleted.append(key)

        except Exception as e:
            logger.error("Change detection error: %s", e)
            return

        if not changed and not deleted:
            return  # Nothing to do — no log spam

        logger.info("Re-indexing %d changed, %d deleted files", len(changed), len(deleted))

        with self._lock:
            for key in deleted:
                self._index.pop(key, None)
                self._mtimes.pop(key, None)

        for key in changed:
            path = Path(key)
            try:
                mtime = path.stat().st_mtime
                messages = self._load_messages(path)
                entry = [
                    (i, m.get("role", ""), m.get("content", ""), m.get("timestamp", ""))
                    for i, m in enumerate(messages)
                ]
                with self._lock:
                    self._index[key] = entry
                    self._mtimes[key] = mtime
            except Exception as e:
                logger.warning("Could not re-index %s: %s", key, e)

    def _load_messages(self, path: Path) -> List[dict]:
        messages = []
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            messages.append(json.loads(line))
                        except Exception:
                            pass
        except Exception as e:
            logger.warning("Could not read %s: %s", path, e)
        return messages

    def search(self, query: str, max_results: int = 100) -> List[SearchResult]:
        """
        Fast case-insensitive substring search across all indexed chats.
        Returns up to max_results SearchResult objects.
        """
        if not query.strip():
            return []

        q = query.lower()
        results: List[SearchResult] = []

        with self._lock:
            index_snapshot = dict(self._index)
            mtimes_snapshot = dict(self._mtimes)

        # Search more recent chats first to maximize relevance when max_results is hit.
        ordered_paths = sorted(
            index_snapshot.keys(),
            key=lambda p: mtimes_snapshot.get(p, 0.0),
            reverse=True,
        )

        for path_str in ordered_paths:
            messages = index_snapshot.get(path_str, [])
            chat_path = Path(path_str)

            # Scan latest messages first for faster "recent" hits.
            for (msg_idx, role, content, timestamp) in reversed(messages):
                pos = content.lower().find(q)
                if pos == -1:
                    continue

                # Build a snippet (up to 120 chars around the match)
                snippet_start = max(0, pos - 40)
                snippet_end = min(len(content), pos + len(query) + 80)
                snippet = content[snippet_start:snippet_end]
                if snippet_start > 0:
                    snippet = "…" + snippet
                if snippet_end < len(content):
                    snippet = snippet + "…"

                results.append(SearchResult(
                    chat_path=chat_path,
                    message_index=msg_idx,
                    role=role,
                    content=content,
                    timestamp=timestamp,
                    snippet=snippet,
                    match_start=pos - snippet_start + (1 if snippet_start > 0 else 0),
                    match_end=pos - snippet_start + len(query) + (1 if snippet_start > 0 else 0),
                ))
                if len(results) >= max_results:
                    break
            if len(results) >= max_results:
                break

        # Keep stable recency ordering for UI.
        results.sort(key=lambda r: r.timestamp, reverse=True)
        return results

    @property
    def total_indexed(self) -> int:
        with self._lock:
            return len(self._index)

    def force_reindex(self) -> None:
        """Trigger an immediate full re-index (e.g. after import)."""
        threading.Thread(target=self._reindex_all, daemon=True).start()

