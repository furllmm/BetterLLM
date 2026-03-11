from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import queue
from pathlib import Path
from typing import Any, Dict, List, Optional, Iterator, Callable


class LlamaBackend:
    """
    Subprocess-based llama.cpp backend to prevent GUI freezing.
    Supports token streaming and cancellation.
    """

    def __init__(
        self,
        model_path: Path,
        n_ctx: int = 4096,
        n_threads: int = 4,
        n_gpu_layers: int = 0,
        **llama_kwargs: Any,
    ) -> None:
        self._model_path = Path(model_path)
        self._n_ctx = n_ctx
        self._n_threads = n_threads
        self._n_gpu_layers = n_gpu_layers
        self._llama_kwargs = llama_kwargs
        
        self._process: Optional[subprocess.Popen] = None
        self._stop_event = threading.Event()

    def _project_root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    def _llamacpp_dir(self) -> Path:
        return self._project_root() / "llamacpp"

    def _get_cli_executable(self) -> str:
        exe = "llama-cli.exe" if sys.platform == "win32" else "llama-cli"
        path = self._llamacpp_dir() / exe
        if not path.exists():
            raise RuntimeError(f"llama-cli not found at {path}")
        return str(path)

    def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
        top_p: float = 0.9,
        top_k: int = 40,
        repeat_penalty: float = 1.1,
        stop: Optional[List[str]] = None,
        image_path: Optional[str] = None,
    ) -> Iterator[str]:
        """
        Streams tokens from llama-cli using subprocess pipes with speed optimizations.
        """
        self._stop_event.clear()
        
        # Optimization Flags:
        # --mlock: Force model to stay in RAM (prevents swapping)
        # --mmap: Use memory mapping for faster loading
        # -b 512: Optimized batch size for prompt processing
        # -ub 512: Optimized physical batch size
        # --flash-attn: Use Flash Attention (if supported)
        args = [
            self._get_cli_executable(),
            "-m", str(self._model_path),
            "-p", prompt,
            "-n", str(max_tokens),
            "-t", str(self._n_threads),
            "-c", str(self._n_ctx),
            "-b", "512",
            "-ub", "512",
            "--temp", str(temperature),
            "--top-p", str(top_p),
            "--top-k", str(top_k),
            "--repeat-penalty", str(repeat_penalty),
            "--simple-io",
            "--display-prompt", "false",
            "--mlock",
            "--mmap",
            "--flash-attn"
        ]
        
        if image_path:
            # llama-cli uses --image for multimodal models (like LLaVA)
            args += ["--image", image_path]
        
        if self._n_gpu_layers > 0:
            args += ["-ngl", str(self._n_gpu_layers)]
        
        if stop:
            for s in stop:
                args += ["-r", s]

        # Process isolation: Run in a separate process
        try:
            self._process = subprocess.Popen(
                args,
                cwd=str(self._llamacpp_dir()),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="ignore",
                bufsize=1, # Line buffered
                creationflags=subprocess.CREATE_NO_WINDOW | 0x00000080 if sys.platform == "win32" else 0
            )
            
            # Read stdout token by token
            if self._process.stdout:
                while True:
                    if self._stop_event.is_set():
                        self.cancel()
                        break
                        
                    char = self._process.stdout.read(1)
                    if not char:
                        break
                    yield char
                    
            self._process.wait()
        except Exception as e:
            yield f"\n[Backend Error] {e}"
        finally:
            self._process = None

    def cancel(self) -> None:
        """Interrupts the current generation."""
        self._stop_event.set()
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

    def close(self) -> None:
        self.cancel()
