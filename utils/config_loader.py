from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import yaml

from .paths import get_config_path


logger = logging.getLogger(__name__)


@dataclass
class TopicConfig:
    path: str
    ctx_size: int = 4096
    gpu_layers: int = 0
    threads: int = 4
    rules: List[str] = field(default_factory=list)


@dataclass
class ModelsConfig:
    default_topic: str = "general"
    topics: Dict[str, TopicConfig] = field(default_factory=dict)


@dataclass
class MemoryConfig:
    enabled: bool = True
    prune_interval_seconds: int = 300
    max_tokens_per_topic: int = 2048


@dataclass
class ResourcesConfig:
    ram_threshold_percent: int = 75
    idle_unload_minutes: int = 5
    poll_interval_seconds: int = 10


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "app.log"


@dataclass
class AppConfig:
    models: ModelsConfig
    memory: MemoryConfig
    resources: ResourcesConfig
    logging: LoggingConfig
    profile: str = "BALANCED" # Default


def load_config() -> AppConfig:
    config_path = get_config_path()
    if not config_path.exists():
        # Create a default config if it doesn't exist
        default_config = {
            "models": {
                "default_topic": "general",
                "topics": {
                    "general": {
                        "path": "models/general.gguf",
                        "ctx_size": 4096,
                        "gpu_layers": 0,
                        "threads": 4,
                        "rules": ["hello", "how are you"]
                    }
                }
            },
            "memory": {
                "enabled": True,
                "prune_interval_seconds": 300,
                "max_tokens_per_topic": 2048
            },
            "resources": {
                "ram_threshold_percent": 75,
                "idle_unload_minutes": 5,
                "poll_interval_seconds": 10
            },
            "logging": {
                "level": "INFO",
                "file": "app.log"
            },
            "profile": "BALANCED"
        }
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(default_config, f)
        raw_config = default_config
    else:
        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f) or {}

    return AppConfig(
        models=ModelsConfig(
            default_topic=raw_config.get("models", {}).get("default_topic", "general"),
            topics={k: TopicConfig(**v) for k, v in raw_config.get("models", {}).get("topics", {}).items()},
        ),
        memory=MemoryConfig(**raw_config.get("memory", {})),
        resources=ResourcesConfig(**raw_config.get("resources", {})),
        logging=LoggingConfig(**raw_config.get("logging", {})),
        profile=raw_config.get("profile", "BALANCED")
    )

def save_config(config: AppConfig) -> None:
    config_path = get_config_path()
    
    # Convert AppConfig back to dict for yaml dump
    data = {
        "models": {
            "default_topic": config.models.default_topic,
            "topics": {k: {
                "path": v.path,
                "ctx_size": v.ctx_size,
                "gpu_layers": v.gpu_layers,
                "threads": v.threads,
                "rules": v.rules
            } for k, v in config.models.topics.items()}
        },
        "memory": {
            "enabled": config.memory.enabled,
            "prune_interval_seconds": config.memory.prune_interval_seconds,
            "max_tokens_per_topic": config.memory.max_tokens_per_topic
        },
        "resources": {
            "ram_threshold_percent": config.resources.ram_threshold_percent,
            "idle_unload_minutes": config.resources.idle_unload_minutes,
            "poll_interval_seconds": config.resources.poll_interval_seconds
        },
        "logging": {
            "level": config.logging.level,
            "file": config.logging.file
        },
        "profile": config.profile
    }
    
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)
