from __future__ import annotations

import logging

from core.chat_session import ChatSession
from core.memory_manager import MemoryManager
from core.model_manager import ModelManager
from core.resource_monitor import ResourceMonitor
from core.router import TopicRouter
from utils.config_loader import load_config
from utils.logging_config import setup_logging


logger = logging.getLogger(__name__)


def run_cli() -> None:
    try:
        config = load_config()
        setup_logging(config)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        return

    resource_monitor = ResourceMonitor(config.resources.ram_threshold_percent)
    model_manager = ModelManager(config, resource_monitor)
    memory_manager = MemoryManager(config)
    router = TopicRouter(config)
    chat_session = ChatSession(model_manager, memory_manager, router)

    print("BetterLLM CLI Mode. Type 'exit' to quit.")
    while True:
        try:
            query = input("> ")
            if query.lower() == "exit":
                break
            response = chat_session.send_message(query)
            print(f"\n{response}\n")
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.exception("An error occurred in CLI loop")
            print(f"[ERROR] {e}")

    model_manager.stop()
    print("Exiting...")
