from __future__ import annotations

import logging
from typing import List

from utils.config_loader import AppConfig


logger = logging.getLogger(__name__)


class TopicRouter:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._rules: List[tuple[str, List[str]]] = []
        for topic, topic_cfg in config.models.topics.items():
            if topic_cfg.rules:
                self._rules.append((topic, [r.lower() for r in topic_cfg.rules]))

    def get_topic(self, text: str) -> str:
        text_lower = text.lower()
        for topic, config in self._config.models.topics.items():
            if any(rule in text_lower for rule in config.rules):
                return topic
        return self._config.models.default_topic

    def get_topic_icon(self, topic: str) -> str:
        icons = {
            "coder": "🐍",
            "instruct": "💡",
            "roleplay": "🎭",
            "vision": "🖼️",
            "general": "💬"
        }
        return icons.get(topic, "📄")

    def generate_title(self, text: str) -> str:
        """Generates a short title from the first message."""
        words = text.split()
        title = " ".join(words[:5])
        if len(words) > 5:
            title += "..."
        return title
