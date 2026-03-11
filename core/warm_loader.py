from __future__ import annotations

import logging
import threading
import time
from enum import Enum, auto
from typing import Optional, Callable, Dict, Any

logger = logging.getLogger(__name__)

class WarmState(Enum):
    IDLE = auto()
    WARMING = auto()
    READY = auto()
    FAILED = auto()
    CANCELED = auto()

class WarmLoader:
    """
    Manages background model warming based on user activity (typing, session opening).
    Tracks state and coordinates with ModelManager.
    """
    def __init__(self, model_manager: Any, on_state_change: Optional[Callable[[str, WarmState, float], None]] = None) -> None:
        self._model_manager = model_manager
        self._on_state_change = on_state_change
        
        self._current_topic: Optional[str] = None
        self._state = WarmState.IDLE
        self._progress = 0.0
        self._lock = threading.Lock()
        
        # To avoid constant re-triggering while typing
        self._last_trigger_time = 0.0
        self._trigger_threshold = 2.0 # seconds

    @property
    def state(self) -> WarmState:
        return self._state

    @property
    def progress(self) -> float:
        return self._progress

    def maybe_start_warm_loading(self, topic: str) -> None:
        """Triggers warming if not already loaded or warming."""
        with self._lock:
            # Avoid duplicate triggers within threshold
            now = time.time()
            if now - self._last_trigger_time < self._trigger_threshold and self._current_topic == topic:
                return
            
            self._last_trigger_time = now

            # If already loading this topic or loaded, skip
            if self._current_topic == topic:
                if self._state in (WarmState.WARMING, WarmState.READY):
                    return
            
            # If warming another topic, cancel it first
            if self._current_topic and self._current_topic != topic:
                self.cancel_warming()

            self._current_topic = topic
            self._update_state(WarmState.WARMING, 0.0)

        # Start async load in ModelManager
        logger.info(f"Warm loading triggered for topic: {topic}")
        self._model_manager.start_load_async(
            topic, 
            on_progress=self._handle_progress,
            on_complete=self._handle_complete,
            on_error=self._handle_error
        )

    def cancel_warming(self) -> None:
        """Cancels any active warming process."""
        with self._lock:
            if self._state == WarmState.WARMING and self._current_topic:
                logger.info(f"Canceling warm loading for: {self._current_topic}")
                self._model_manager.cancel_loading(self._current_topic)
                self._update_state(WarmState.CANCELED, 0.0)
                self._current_topic = None

    def _handle_progress(self, topic: str, progress: float) -> None:
        with self._lock:
            if self._current_topic == topic and self._state == WarmState.WARMING:
                self._progress = progress
                self._notify_state_change()

    def _handle_complete(self, topic: str) -> None:
        with self._lock:
            if self._current_topic == topic:
                self._update_state(WarmState.READY, 1.0)
                logger.info(f"Warm loading complete for: {topic}")

    def _handle_error(self, topic: str, error: str) -> None:
        with self._lock:
            if self._current_topic == topic:
                self._update_state(WarmState.FAILED, 0.0)
                logger.error(f"Warm loading failed for {topic}: {error}")

    def _update_state(self, state: WarmState, progress: float) -> None:
        self._state = state
        self._progress = progress
        self._notify_state_change()

    def _notify_state_change(self) -> None:
        if self._on_state_change and self._current_topic:
            self._on_state_change(self._current_topic, self._state, self._progress)

    def get_status_text(self) -> str:
        if self._state == WarmState.IDLE: return ""
        if self._state == WarmState.WARMING: return f"Warming {self._current_topic}... {int(self._progress * 100)}%"
        if self._state == WarmState.READY: return f"{self._current_topic} Ready"
        if self._state == WarmState.FAILED: return "Loading Failed"
        if self._state == WarmState.CANCELED: return "Loading Canceled"
        return ""
