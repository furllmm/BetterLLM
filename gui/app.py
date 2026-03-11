from __future__ import annotations

import logging
import sys
import os

# Suppress DirectWrite font warnings for legacy bitmap fonts
os.environ["QT_LOGGING_RULES"] = "qt.qpa.fonts=false"

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from core.chat_session import ChatSession
from core.memory_manager import MemoryManager
from core.model_manager import ModelManager
from core.resource_monitor import ResourceMonitor
from core.router import TopicRouter
from core.profiler import Profiler
from utils.config_loader import load_config, save_config
from utils.logging_config import setup_logging

from .main_window import MainWindow


logger = logging.getLogger(__name__)


def run_gui() -> None:
    config = load_config()
    setup_logging(config)

    app = QApplication.instance() or QApplication(sys.argv)
    
    # Set a modern global font to avoid fallback to legacy bitmap fonts
    app.setFont(QFont("Segoe UI", 9))

    resource_monitor = ResourceMonitor(config.resources.ram_threshold_percent)
    profiler = Profiler(resource_monitor)
    
    # Auto hardware detection on first launch or if profile is missing
    hw_stats = profiler.detect_hardware()
    auto_profile = profiler.select_profile(hw_stats)
    
    if not config.profile or config.profile == "AUTO":
        logger.info("Auto-selecting profile: %s", auto_profile)
        config.profile = auto_profile
        settings = profiler.get_profile_settings(auto_profile)
        config.resources.idle_unload_minutes = settings["idle_unload_minutes"]
        config.resources.ram_threshold_percent = settings["ram_threshold_percent"]
        config.memory.enabled = settings["memory_enabled"]
        save_config(config)

    model_manager = ModelManager(config, resource_monitor)
    memory_manager = MemoryManager(config)
    router = TopicRouter(config)
    chat_session = ChatSession(model_manager, memory_manager, router)

    main_window = MainWindow(chat_session, resource_monitor, model_manager, config)
    main_window.show()

    # Predictive pre-warming: Load default model on launch
    main_window.warm_loader.maybe_start_warm_loading(config.models.default_topic)

    exit_code = app.exec()

    model_manager.stop()
    sys.exit(exit_code)
