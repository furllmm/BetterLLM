from __future__ import annotations

import logging
import psutil
import platform
from dataclasses import dataclass
from typing import Dict, Optional


logger = logging.getLogger(__name__)


@dataclass
class HardwareStats:
    total_ram_gb: float
    cpu_cores: int
    has_gpu: bool
    vram_gb: float
    os_name: str
    machine: str


class Profiler:
    """
    Detects hardware and selects a performance profile (LITE, BALANCED, POWER).
    """

    def __init__(self, resource_monitor) -> None:
        self.monitor = resource_monitor

    def detect_hardware(self) -> HardwareStats:
        mem = psutil.virtual_memory()
        total_ram_gb = mem.total / (1024**3)
        cpu_cores = psutil.cpu_count(logical=False) or psutil.cpu_count() or 1

        gpu_stats = self.monitor.get_gpu_stats()
        has_gpu = gpu_stats is not None
        vram_gb = (gpu_stats["vram_total"] / (1024**3)) if has_gpu else 0.0

        stats = HardwareStats(
            total_ram_gb=total_ram_gb,
            cpu_cores=cpu_cores,
            has_gpu=has_gpu,
            vram_gb=vram_gb,
            os_name=platform.system(),
            machine=platform.machine(),
        )
        logger.info("Detected hardware: %s", stats)
        return stats

    def select_profile(self, stats: HardwareStats) -> str:
        # POWER: 32GB+ RAM or GPU with 8GB+ VRAM
        if stats.total_ram_gb >= 31 or (stats.has_gpu and stats.vram_gb >= 7.5):
            return "POWER"
        
        # BALANCED: 15GB+ RAM
        if stats.total_ram_gb >= 15:
            return "BALANCED"
        
        # LITE: Default fallback
        return "LITE"

    def get_profile_settings(self, profile_name: str) -> Dict[str, any]:
        if profile_name == "POWER":
            return {
                "idle_unload_minutes": 20,
                "ram_threshold_percent": 85,
                "default_ctx": 8192,
                "memory_enabled": True
            }
        elif profile_name == "BALANCED":
            return {
                "idle_unload_minutes": 10,
                "ram_threshold_percent": 75,
                "default_ctx": 4096,
                "memory_enabled": True
            }
        else: # LITE
            return {
                "idle_unload_minutes": 5,
                "ram_threshold_percent": 65,
                "default_ctx": 2048,
                "memory_enabled": False
            }
