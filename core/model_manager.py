from __future__ import annotations

import logging
import threading
import time
import psutil
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterator, Optional, List

from .model_backend import LlamaBackend
from .resource_monitor import ResourceMonitor
from utils.config_loader import AppConfig, TopicConfig


logger = logging.getLogger(__name__)


@dataclass
class ModelHandle:
    topic: str
    path: Path
    backend: Optional[LlamaBackend]
    last_used: datetime
    est_ram_bytes: int = 0
    loaded: bool = False


class ModelManager:
    """
    Manages loading, unloading, and auto-optimization of models.
    Supports LRU unloading and RAM safety thresholds.
    """

    def __init__(self, config: AppConfig, resource_monitor: ResourceMonitor) -> None:
        self._config = config
        self._resource_monitor = resource_monitor
        self._lock = threading.RLock()
        self._models: Dict[str, ModelHandle] = {}
        self._lru: "OrderedDict[str, None]" = OrderedDict()
        
        self._idle_unload_minutes = config.resources.idle_unload_minutes
        self._stop_flag = threading.Event()

        # Pre-initialize model handles from config topics
        for topic, topic_cfg in config.models.topics.items():
            self._models[topic] = ModelHandle(
                topic=topic,
                path=Path(topic_cfg.path),
                backend=None,
                last_used=datetime.utcnow(),
                est_ram_bytes=self._estimate_model_ram(topic_cfg),
                loaded=False
            )

        self._idle_thread = threading.Thread(
            target=self._idle_unload_loop, name="ModelIdleUnloader", daemon=True
        )
        self._idle_thread.start()

        # Track loading threads and cancellation flags per topic
        self._loading_threads: Dict[str, threading.Thread] = {}
        self._loading_stops: Dict[str, threading.Event] = {}
        self._loading_progress: Dict[str, float] = {}

    def _estimate_model_ram(self, topic_cfg: TopicConfig) -> int:
        """Estimates RAM usage based on file size and ctx."""
        path = Path(topic_cfg.path)
        if path.exists():
            return int(path.stat().st_size * 1.2) # File size + 20% overhead
        return 2_000_000_000 # Default 2GB

    def _get_optimized_threads(self) -> int:
        """Returns recommended threads based on CPU count."""
        cores = psutil.cpu_count(logical=False) or psutil.cpu_count() or 4
        if cores > 4:
            return cores - 1
        return cores

    def stop(self) -> None:
        self._stop_flag.set()
        with self._lock:
            for handle in self._models.values():
                if handle.backend:
                    handle.backend.close()

    def _idle_unload_loop(self) -> None:
        interval = max(self._config.resources.poll_interval_seconds, 10)
        while not self._stop_flag.is_set():
            now = datetime.utcnow()
            idle_delta = timedelta(minutes=self._idle_unload_minutes)
            
            topics_to_unload = []
            with self._lock:
                for topic, handle in self._models.items():
                    if handle.loaded and (now - handle.last_used > idle_delta):
                        topics_to_unload.append(topic)
            
            for topic in topics_to_unload:
                logger.info("Auto-unloading idle model: %s", topic)
                self.unload_model(topic)
                
            time.sleep(interval)

    def _ensure_ram_safety(self, required_bytes: int) -> bool:
        """Unloads LRU models if RAM threshold is exceeded."""
        while True:
            ram = self._resource_monitor.get_system_ram()
            if ram.percent < self._config.resources.ram_threshold_percent:
                return True
                
            with self._lock:
                if not self._lru:
                    logger.warning("RAM high but no models to unload!")
                    return False
                
                # Unload the oldest model that is currently loaded
                for topic in list(self._lru.keys()):
                    handle = self._models[topic]
                    if handle.loaded:
                        logger.info("RAM pressure (%.1f%%). Unloading LRU: %s", ram.percent, topic)
                        self.unload_model(topic)
                        break
                else:
                    return False

    def start_load_async(
        self, 
        topic: str, 
        on_progress: Optional[Callable[[str, float], None]] = None,
        on_complete: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str, str], None]] = None
    ) -> None:
        """Starts a model load in a background thread."""
        with self._lock:
            # Check if already loaded or loading
            if topic in self._models and self._models[topic].loaded:
                if on_complete: on_complete(topic)
                return
            
            if topic in self._loading_threads:
                return

            # Cancel any previous load for this topic
            self.cancel_loading(topic)
            
            stop_event = threading.Event()
            self._loading_stops[topic] = stop_event
            self._loading_progress[topic] = 0.0
            
            thread = threading.Thread(
                target=self._load_async_worker,
                args=(topic, stop_event, on_progress, on_complete, on_error),
                name=f"Load-{topic}",
                daemon=True
            )
            self._loading_threads[topic] = thread
            thread.start()

    def _load_async_worker(
        self, 
        topic: str, 
        stop_event: threading.Event,
        on_progress: Optional[Callable[[str, float], None]],
        on_complete: Optional[Callable[[str]], None],
        on_error: Optional[Callable[[str, str], None]]
    ) -> None:
        """Worker thread for asynchronous model loading."""
        try:
            # Simulate progress if backend doesn't support it yet
            # In a real llama-cli scenario, we might parse stderr for progress
            # For now, we update progress to 50% after RAM safety check
            
            if stop_event.is_set(): return
            
            handle = self._models.get(topic)
            if not handle:
                # Same path-based fallback as load_model
                if Path(topic).exists():
                    path = Path(topic)
                    handle = ModelHandle(
                        topic=path.name,
                        path=path,
                        backend=None,
                        last_used=datetime.utcnow(),
                        est_ram_bytes=int(path.stat().st_size * 1.2),
                        loaded=False
                    )
                    with self._lock:
                        self._models[topic] = handle
                else:
                    if on_error: on_error(topic, f"Topic '{topic}' not found")
                    return

            # RAM Safety Check
            if not self._ensure_ram_safety(handle.est_ram_bytes):
                if on_error: on_error(topic, "Insufficient RAM for warm loading")
                return

            if stop_event.is_set(): return
            if on_progress: on_progress(topic, 0.5)

            # Actual load call (reuse existing load_model logic but in thread)
            # Since load_model handles locking internally, we just call it
            success = self.load_model(topic)
            
            if stop_event.is_set():
                # If we loaded but then got canceled, unload immediately
                self.unload_model(topic)
                return

            if success:
                if on_progress: on_progress(topic, 1.0)
                if on_complete: on_complete(topic)
            else:
                if on_error: on_error(topic, "Model load failed")

        except Exception as e:
            logger.exception(f"Async load failed for {topic}")
            if on_error: on_error(topic, str(e))
        finally:
            with self._lock:
                self._loading_threads.pop(topic, None)
                self._loading_stops.pop(topic, None)
                self._loading_progress.pop(topic, None)

    def cancel_loading(self, topic: str) -> None:
        """Cancels an active background load."""
        with self._lock:
            if topic in self._loading_stops:
                logger.info(f"Setting stop event for loading topic: {topic}")
                self._loading_stops[topic].set()

    def is_model_loaded(self, topic: str) -> bool:
        with self._lock:
            return topic in self._models and self._models[topic].loaded

    def get_loading_progress(self, topic: str) -> float:
        with self._lock:
            return self._loading_progress.get(topic, 0.0)

    def load_model(self, topic: str) -> bool:
        """Loads a model lazily. Returns True if successful."""
        with self._lock:
            handle = self._models.get(topic)
            if not handle:
                # If topic not in config, try to find it as a direct path
                if Path(topic).exists():
                    path = Path(topic)
                    handle = ModelHandle(
                        topic=path.name,
                        path=path,
                        backend=None,
                        last_used=datetime.utcnow(),
                        est_ram_bytes=int(path.stat().st_size * 1.2),
                        loaded=False
                    )
                    self._models[topic] = handle
                else:
                    return False

            if handle.loaded:
                handle.last_used = datetime.utcnow()
                self._lru.move_to_end(topic)
                return True

            # RAM Safety Check
            self._ensure_ram_safety(handle.est_ram_bytes)

            # Optimization
            topic_cfg = self._config.models.topics.get(topic)
            n_threads = topic_cfg.threads if topic_cfg else self._get_optimized_threads()
            n_ctx = topic_cfg.ctx_size if topic_cfg else 4096
            n_gpu = topic_cfg.gpu_layers if topic_cfg else 0

            try:
                backend = LlamaBackend(
                    model_path=handle.path,
                    n_ctx=n_ctx,
                    n_threads=n_threads,
                    n_gpu_layers=n_gpu
                )
                handle.backend = backend
                handle.loaded = True
                handle.last_used = datetime.utcnow()
                self._lru[topic] = None
                logger.info("Successfully loaded model: %s", topic)
                return True
            except Exception as e:
                logger.error("Failed to load model %s: %s", topic, e)
                return False

    def unload_model(self, topic: str) -> None:
        with self._lock:
            handle = self._models.get(topic)
            if handle and handle.loaded:
                if handle.backend:
                    handle.backend.close()
                handle.backend = None
                handle.loaded = False
                self._lru.pop(topic, None)
                logger.info("Unloaded model: %s", topic)

    def get_active_model_topic(self) -> Optional[str]:
        with self._lock:
            for topic in reversed(self._lru):
                if self._models[topic].loaded:
                    return topic
        return None

    def get_all_models_status(self) -> List[Dict[str, Any]]:
        """Returns list of all models and their status."""
        status = []
        with self._lock:
            for topic, handle in self._models.items():
                status.append({
                    "topic": topic,
                    "path": str(handle.path),
                    "loaded": handle.loaded,
                    "size_gb": handle.path.stat().st_size / (1024**3) if handle.path.exists() else 0,
                    "last_used": handle.last_used.isoformat()
                })
        return status

    @contextmanager
    def use_model(self, topic: str) -> Iterator[LlamaBackend]:
        if not self.load_model(topic):
            raise RuntimeError(f"Could not load model for topic: {topic}")
        
        handle = self._models[topic]
        with self._lock:
            handle.last_used = datetime.utcnow()
            self._lru.move_to_end(topic)
            
        yield handle.backend
