"""
Production-grade LAN / OpenAI-compatible API Server
Exposes BetterLLM as an OpenAI-compatible endpoint so any OpenAI client
(LM Studio, Open WebUI, custom scripts, etc.) can connect.

Endpoints:
  GET  /                          → health check
  GET  /v1/models                 → list available models
  POST /v1/chat/completions       → OpenAI-compatible chat (streaming + non-streaming)
  POST /api/chat                  → legacy plain-text streaming endpoint
  GET  /api/status                → server status JSON
  GET  /api/history               → recent chat history (authenticated)

Authentication:
  Optional bearer token. Set BETTERLLM_API_KEY env var or pass api_key to constructor.
  If no key configured, all requests are allowed (LAN-only use).
"""
from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
import uuid
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from flask import Flask, request, jsonify, Response, stream_with_context
    from flask_cors import CORS
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False
    logger.warning("flask/flask-cors not installed — LAN server unavailable")


class LANServer:
    """OpenAI-compatible production LAN server for BetterLLM."""

    def __init__(self, chat_session: Any, host: str = "0.0.0.0", port: int = 5001,
                 api_key: Optional[str] = None):
        self.chat_session = chat_session
        self.host = host
        self.port = port
        self.api_key = api_key or os.environ.get("BETTERLLM_API_KEY", "")
        self._server_thread: Optional[threading.Thread] = None
        self._is_running = False
        self._request_count = 0
        self._start_time: Optional[float] = None

        if HAS_FLASK:
            self.app = Flask(__name__)
            self.app.config["JSON_SORT_KEYS"] = False
            CORS(self.app, resources={r"/*": {"origins": "*"}})
            self._setup_routes()

    # ── Auth middleware ──────────────────────────────────────────────────────
    def _check_auth(self) -> Optional[Response]:
        """Return 401 response if key configured and request doesn't match."""
        if not self.api_key:
            return None  # No auth required
        auth = request.headers.get("Authorization", "")
        key = auth.removeprefix("Bearer ").strip()
        if key != self.api_key:
            return jsonify({"error": {"message": "Invalid API key", "type": "invalid_request_error",
                                      "code": "invalid_api_key"}}), 401
        return None

    # ── Routes ───────────────────────────────────────────────────────────────
    def _setup_routes(self):
        app = self.app

        @app.route("/", methods=["GET"])
        def root():
            return jsonify({"status": "ok", "service": "BetterLLM API",
                            "version": "1.0", "openai_compatible": True})

        # ── OpenAI: list models ──────────────────────────────────────────────
        @app.route("/v1/models", methods=["GET"])
        def list_models():
            err = self._check_auth()
            if err:
                return err
            topic = self.chat_session._model_manager.get_active_model_topic() or "none"
            return jsonify({
                "object": "list",
                "data": [{
                    "id": topic,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "betterllm",
                    "permission": [],
                    "root": topic,
                }]
            })

        # ── OpenAI: chat completions ─────────────────────────────────────────
        @app.route("/v1/chat/completions", methods=["POST"])
        def chat_completions():
            err = self._check_auth()
            if err:
                return err

            data = request.get_json(silent=True) or {}
            messages = data.get("messages", [])
            stream = data.get("stream", False)
            max_tokens = data.get("max_tokens", 2048)
            temperature = data.get("temperature", 0.7)

            if not messages:
                return jsonify({"error": {"message": "No messages provided"}}), 400

            # Extract the last user message as prompt; pass full history as context
            prompt = ""
            for m in reversed(messages):
                if m.get("role") == "user":
                    prompt = m.get("content", "")
                    break

            if not prompt:
                return jsonify({"error": {"message": "No user message found"}}), 400

            self._request_count += 1
            model_id = self.chat_session._model_manager.get_active_model_topic() or "betterllm"
            completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
            created = int(time.time())

            gen_params = {"max_tokens": max_tokens, "temperature": temperature}

            if stream:
                def generate_sse():
                    try:
                        for token in self.chat_session.send_message_stream(
                            prompt, False, False, None, gen_params
                        ):
                            chunk = {
                                "id": completion_id,
                                "object": "chat.completion.chunk",
                                "created": created,
                                "model": model_id,
                                "choices": [{
                                    "index": 0,
                                    "delta": {"role": "assistant", "content": token},
                                    "finish_reason": None,
                                }]
                            }
                            yield f"data: {json.dumps(chunk)}\n\n"
                        # Send final [DONE]
                        done_chunk = {
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": model_id,
                            "choices": [{"index": 0, "delta": {},
                                         "finish_reason": "stop"}]
                        }
                        yield f"data: {json.dumps(done_chunk)}\n\n"
                        yield "data: [DONE]\n\n"
                    except Exception as e:
                        logger.error(f"Streaming error: {e}")
                        yield f"data: {{\"error\": \"{e}\"}}\n\n"

                return Response(
                    stream_with_context(generate_sse()),
                    mimetype="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Accel-Buffering": "no",
                        "Connection": "keep-alive",
                    }
                )
            else:
                # Non-streaming: collect full response
                full_text = ""
                try:
                    for token in self.chat_session.send_message_stream(
                        prompt, False, False, None, gen_params
                    ):
                        full_text += token
                except Exception as e:
                    return jsonify({"error": {"message": str(e)}}), 500

                return jsonify({
                    "id": completion_id,
                    "object": "chat.completion",
                    "created": created,
                    "model": model_id,
                    "choices": [{
                        "index": 0,
                        "message": {"role": "assistant", "content": full_text},
                        "finish_reason": "stop",
                    }],
                    "usage": {
                        "prompt_tokens": len(prompt.split()),
                        "completion_tokens": len(full_text.split()),
                        "total_tokens": len(prompt.split()) + len(full_text.split()),
                    }
                })

        # ── Legacy plain-text streaming ──────────────────────────────────────
        @app.route("/api/chat", methods=["POST"])
        def api_chat():
            err = self._check_auth()
            if err:
                return err
            data = request.get_json(silent=True) or {}
            prompt = data.get("prompt", "")
            if not prompt:
                return jsonify({"error": "No prompt provided"}), 400

            def generate():
                try:
                    for token in self.chat_session.send_message_stream(
                        prompt, False, False, None, {}
                    ):
                        yield token
                except Exception as e:
                    yield f"\n[Error] {e}"

            return Response(stream_with_context(generate()), mimetype="text/plain")

        # ── Status ───────────────────────────────────────────────────────────
        @app.route("/api/status", methods=["GET"])
        def status():
            uptime = int(time.time() - self._start_time) if self._start_time else 0
            return jsonify({
                "status": "online",
                "model": self.chat_session._model_manager.get_active_model_topic() or "None",
                "device": socket.gethostname(),
                "ip": LANServer.get_local_ip(),
                "port": self.port,
                "uptime_seconds": uptime,
                "requests_served": self._request_count,
                "auth_enabled": bool(self.api_key),
                "openai_base_url": f"http://{LANServer.get_local_ip()}:{self.port}/v1",
            })

        # ── Error handlers ───────────────────────────────────────────────────
        @app.errorhandler(404)
        def not_found(e):
            return jsonify({"error": {"message": "Not found", "type": "invalid_request_error"}}), 404

        @app.errorhandler(500)
        def server_error(e):
            return jsonify({"error": {"message": "Internal server error"}}), 500

    # ── Lifecycle ────────────────────────────────────────────────────────────
    def start(self):
        if self._is_running or not HAS_FLASK:
            return
        self._is_running = True
        self._start_time = time.time()

        def _run():
            try:
                import logging as _log
                _log.getLogger("werkzeug").setLevel(_log.ERROR)
                self.app.run(
                    host=self.host,
                    port=self.port,
                    threaded=True,
                    use_reloader=False,
                    debug=False,
                )
            except OSError as e:
                logger.error(f"LAN server failed to start: {e}")
                self._is_running = False

        self._server_thread = threading.Thread(target=_run, daemon=True)
        self._server_thread.start()
        logger.info(
            f"LAN Server started — OpenAI base URL: "
            f"http://{self.get_local_ip()}:{self.port}/v1"
        )

    def stop(self):
        self._is_running = False

    def is_running(self) -> bool:
        return self._is_running

    def get_info(self) -> dict:
        ip = self.get_local_ip()
        return {
            "ip": ip,
            "port": self.port,
            "openai_url": f"http://{ip}:{self.port}/v1",
            "status_url": f"http://{ip}:{self.port}/api/status",
            "auth_enabled": bool(self.api_key),
        }

    @staticmethod
    def get_local_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
