from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from sentence_transformers import SentenceTransformer, util

from utils.config_loader import AppConfig
from utils.paths import get_memory_root


logger = logging.getLogger(__name__)


@dataclass
class MemoryItem:
    timestamp: str
    topic: str
    query: str
    response: str


class MemoryManager:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._lock = threading.RLock()
        self._embed_model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")

    def _get_memory_path(self, topic: str) -> Path:
        path = get_memory_root() / topic
        path.mkdir(parents=True, exist_ok=True)
        return path / "mem.jsonl"

    def add_memory(self, topic: str, query: str, response: str) -> None:
        if not self._config.memory.enabled:
            return

        item = MemoryItem(
            timestamp=datetime.utcnow().isoformat(),
            topic=topic,
            query=query,
            response=response,
        )
        mem_path = self._get_memory_path(topic)
        with self._lock, open(mem_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(item)) + "\n")

    def get_relevant_memories(
        self, topic: str, query: str, n: int = 3
    ) -> List[MemoryItem]:
        if not self._config.memory.enabled:
            return []

        mem_path = self._get_memory_path(topic)
        if not mem_path.exists():
            return []

        with self._lock, open(mem_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if not lines:
            return []

        memories = [MemoryItem(**json.loads(line)) for line in lines]
        queries = [m.query for m in memories]

        query_embedding = self._embed_model.encode(query, convert_to_tensor=True)
        corpus_embeddings = self._embed_model.encode(queries, convert_to_tensor=True)

        hits = util.semantic_search(query_embedding, corpus_embeddings, top_k=n)[0]
        return [memories[hit["corpus_id"]] for hit in hits]

