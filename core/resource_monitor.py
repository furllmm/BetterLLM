from __future__ import annotations

import logging
import os
import psutil
from dataclasses import dataclass
from typing import Dict, Optional


logger = logging.getLogger(__name__)


@dataclass
class RamStats:
    total: int
    used: int
    percent: float


class ResourceMonitor:
    def __init__(self, ram_threshold_percent: float = 75.0) -> None:
        self.ram_threshold_percent = ram_threshold_percent
        self._nvml_initialized = False
        self._init_nvml()

    def _init_nvml(self) -> None:
        try:
            import pynvml
            pynvml.nvmlInit()
            self._nvml_initialized = True
        except Exception:
            # NVML initialization can fail if no NVIDIA GPU is present or drivers are missing
            pass

    def get_system_ram(self) -> RamStats:
        mem = psutil.virtual_memory()
        return RamStats(total=mem.total, used=mem.used, percent=mem.percent)

    def get_gpu_stats(self) -> Optional[Dict[str, any]]:
        if not self._nvml_initialized:
            return None

        try:
            import pynvml
            device_count = pynvml.nvmlDeviceGetCount()
            if device_count == 0:
                return None

            # For simplicity, we take the first GPU
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            name = pynvml.nvmlDeviceGetName(handle)
            # On some systems, name might be bytes
            if isinstance(name, bytes):
                name = name.decode("utf-8")

            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            return {
                "name": name,
                "vram_total": info.total,
                "vram_used": info.used,
                "vram_free": info.free,
            }
        except Exception:
            return None

    def is_ram_safe(self) -> bool:
        return self.get_system_ram().percent < self.ram_threshold_percent

    def __del__(self) -> None:
        if self._nvml_initialized:
            try:
                import pynvml
                pynvml.nvmlShutdown()
            except Exception:
                pass
