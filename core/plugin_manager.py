from __future__ import annotations

import logging
import os
import importlib.util
from pathlib import Path
from typing import List, Dict, Any, Callable, Optional

from utils.paths import get_base_dir

logger = logging.getLogger(__name__)

class Plugin:
    def __init__(self, name: str):
        self.name = name
        self.tools: Dict[str, Callable] = {}
        self.commands: Dict[str, Callable] = {}

    def register_tool(self, name: str, func: Callable):
        self.tools[name] = func

    def register_command(self, name: str, func: Callable):
        self.commands[name] = func

class PluginManager:
    """
    Manages loading and execution of plugins from a folder.
    Plugins can extend BetterLLM with new tools, commands, and UI.
    """
    def __init__(self, plugins_dir: Optional[str] = None):
        if plugins_dir is None:
            self._plugins_dir = get_base_dir() / "plugins"
        else:
            self._plugins_dir = Path(plugins_dir)
            
        self._plugins_dir.mkdir(parents=True, exist_ok=True)
        self._plugins: Dict[str, Plugin] = {}

    def load_plugins(self):
        """Scans and loads all .py files in the plugins folder."""
        for file in self._plugins_dir.glob("*.py"):
            if file.name == "__init__.py": continue
            try:
                spec = importlib.util.spec_from_file_location(file.stem, file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                if hasattr(module, "setup"):
                    plugin = Plugin(file.stem)
                    module.setup(plugin)
                    self._plugins[file.stem] = plugin
                    logger.info("Loaded plugin: %s", file.stem)
            except Exception as e:
                logger.error("Failed to load plugin %s: %s", file.name, e)

    def get_all_tools(self) -> Dict[str, Callable]:
        all_tools = {}
        for p in self._plugins.values():
            all_tools.update(p.tools)
        return all_tools

    def get_all_commands(self) -> Dict[str, Callable]:
        all_cmds = {}
        for p in self._plugins.values():
            all_cmds.update(p.commands)
        return all_cmds
