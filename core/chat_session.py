from __future__ import annotations

import logging
import os
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Iterator, Tuple

from .memory_manager import MemoryManager
from .model_manager import ModelManager
from .router import TopicRouter
from .terminal_executor import TerminalExecutor
from utils.paths import get_chats_dir
from utils import favorites_library as fav_lib


logger = logging.getLogger(__name__)


@dataclass
class ChatMessage:
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: str
    id: Optional[str] = None
    parent_id: Optional[str] = None

class ChatSession:
    """
    Manages chat history and orchestration.
    Supports streaming, cancellation, forking, and knowledge base integration.
    """
    def __init__(
        self, model_manager: ModelManager, memory_manager: MemoryManager, router: TopicRouter
    ) -> None:
        self._model_manager = model_manager
        self._memory_manager = memory_manager
        self._router = router
        self._executor = TerminalExecutor()
        self._session_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        self._history: List[ChatMessage] = []
        self._active_topic: Optional[str] = None
        self._active_profile: str = "Default"
        self._profile_system_prompt: str = "You are a helpful AI assistant."
        
        from .knowledge_base import KnowledgeBase
        self._kb = KnowledgeBase()
        
        # Tool Registry
        self._tools = {
            "calculator": self._tool_calculator,
            "web_search": self._tool_web_search,
            "file_reader": self._tool_file_reader
        }
        
        # Load plugin tools if available
        try:
            from core.plugin_manager import PluginManager
            pm = PluginManager()
            pm.load_plugins()
            self._tools.update(pm.get_all_tools())
        except Exception:
            pass

    @property
    def session_id(self) -> str:
        return self._session_id

    def fork_conversation(self, message_id: str) -> str:
        """Creates a new session forking from a specific message."""
        new_session = ChatSession(self._model_manager, self._memory_manager, self._router)
        for msg in self._history:
            new_session._history.append(msg)
            if msg.id == message_id:
                break
        return new_session.session_id

    def _tool_calculator(self, expression: str) -> str:
        try:
            # Safe eval for simple expressions
            allowed_chars = "0123456789+-*/(). "
            if all(c in allowed_chars for c in expression):
                return str(eval(expression, {"__builtins__": None}, {}))
            return "Error: Invalid characters in expression"
        except Exception as e:
            return f"Error: {e}"

    def _tool_web_search(self, query: str) -> str:
        # Placeholder for real search (e.g. DuckDuckGo API)
        return f"[Web Search Result for '{query}']: This is a mock search result. In a real scenario, this would call a search engine API."

    def _tool_file_reader(self, file_path: str) -> str:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read(2000) # Limit to 2k chars
        except Exception as e:
            return f"Error: {e}"

    def add_to_knowledge_base(self, file_path: str) -> bool:
        return self._kb.add_document(file_path)

    def _compress_context(self, topic: str) -> None:
        """Summarizes older messages if history is too long."""
        if len(self._history) < 10:
            return
            
        logger.info("Compressing context for topic: %s", topic)
        
        # Keep last 4 messages, summarize the rest
        to_summarize = self._history[:-4]
        summary_prompt = "Please summarize the following conversation history briefly while keeping key information:\n\n"
        for msg in to_summarize:
            summary_prompt += f"{msg.role}: {msg.content}\n"
        
        with self._model_manager.use_model(topic) as backend:
            summary = ""
            for token in backend.generate_stream(summary_prompt, max_tokens=256):
                summary += token
            
            # Replace summarized messages with a single summary message
            summary_msg = ChatMessage(
                role="system",
                content=f"Conversation Summary: {summary.strip()}",
                timestamp=datetime.utcnow().isoformat(),
                id=f"summary_{int(time.time())}"
            )
            self._history = [summary_msg] + self._history[-4:]

    def _build_prompt(self, query: str, topic: str, use_memory: bool, use_kb: bool = True) -> str:
        memories: List[str] = []
        if use_memory:
            relevant_mems = self._memory_manager.get_relevant_memories(topic, query)
            for mem in relevant_mems:
                memories.append(f"- {mem.query} -> {mem.response}")

        kb_context = ""
        if use_kb:
            kb_hits = self._kb.query(query)
            if kb_hits:
                kb_context = "\nKnowledge Base Context:\n"
                for chunk, source in kb_hits:
                    kb_context += f"Source ({source}): {chunk}\n"

        # Limit history
        history_str = "\n".join([f"{m.role}: {m.content}" for m in self._history])

        personalization = fav_lib.build_personalization_context()

        prompt = f"""{self._profile_system_prompt}

<System>
- Current topic: {topic}
- Long-term memories:
{chr(10).join(memories) if memories else 'None.'}
{kb_context}
- User personalization profile:
{personalization if personalization else 'None.'}
- Recent history:
{history_str if history_str else 'Empty.'}
</System>

user: {query}
assistant:"""
        return prompt

    def _get_chat_log_path(self, topic: str) -> Path:
        log_dir = get_chats_dir() / topic
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir / f"{self._session_id}.jsonl"

    def _append_to_log(self, topic: str, message: ChatMessage) -> None:
        path = self._get_chat_log_path(topic)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(message)) + "\n")

    def _process_tools(self, response_text: str) -> Optional[str]:
        """Checks if the response contains a tool call and executes it."""
        import re
        # Look for [TOOL_CALL:tool_name(args)]
        pattern = re.compile(r"\[TOOL_CALL:(\w+)\((.*?)\)\]")
        match = pattern.search(response_text)
        if match:
            tool_name = match.group(1)
            args = match.group(2)
            if tool_name in self._tools:
                logger.info("Executing tool: %s with args: %s", tool_name, args)
                result = self._tools[tool_name](args)
                return f"\n[TOOL_RESULT: {result}]"
        return None

    def send_message_stream(
        self, query: str, use_memory: bool = True, deep_mode: bool = False,
        image_path: Optional[str] = None, gen_params: Optional[Dict] = None
    ) -> Iterator[str]:
        """
        Routes the query and streams tokens from the backend.
        Supports automatic context compression and tool use.
        """
        topic = self._router.get_topic(query)
        self._active_topic = topic
        
        # Auto-compress context if needed
        self._compress_context(topic)

        prompt = self._build_prompt(query, topic, use_memory)
        
        user_content = query
        if image_path:
            user_content = f"[Image: {os.path.basename(image_path)}] {query}"

        msg_id = f"msg_{int(time.time() * 1000)}"
        parent_id = self._history[-1].id if self._history else None
        
        user_msg = ChatMessage(
            role="user", content=user_content, timestamp=datetime.utcnow().isoformat(),
            id=msg_id, parent_id=parent_id
        )
        self._history.append(user_msg)
        self._append_to_log(topic, user_msg)

        params = gen_params or {}
        max_tokens = params.get("max_tokens", 2048 if deep_mode else 512)
        temperature = params.get("temperature", 0.7)
        top_p = params.get("top_p", 0.95)
        top_k = params.get("top_k", 40)
        repeat_penalty = params.get("repeat_penalty", 1.1)
        full_response = []
        
        with self._model_manager.use_model(topic) as backend:
            for token in backend.generate_stream(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                repeat_penalty=repeat_penalty,
                stop=["user:", "\n\n"],
                image_path=image_path
            ):
                full_response.append(token)
                yield token

        response_text = "".join(full_response).strip()
        
        # Check for tool calls
        tool_result = self._process_tools(response_text)
        if tool_result:
            response_text += tool_result
            yield tool_result

        self._handle_generated_images(response_text)

        assistant_msg = ChatMessage(
            role="assistant",
            content=response_text,
            timestamp=datetime.utcnow().isoformat(),
            id=f"msg_{int(time.time() * 1000) + 1}",
            parent_id=msg_id
        )
        self._history.append(assistant_msg)
        self._append_to_log(topic, assistant_msg)

        if use_memory:
            self._memory_manager.add_memory(topic, query, response_text)
            
        self._extract_and_save_code(response_text)

    def _handle_generated_images(self, text: str) -> None:
        """Hook for saving generated images to the generated folder."""
        import re
        import base64
        import shutil
        from utils.paths import get_images_generated_dir
        
        # Look for [IMAGE_GEN:base64data] or [IMAGE_GEN:filepath] pattern
        pattern = re.compile(r"\[IMAGE_GEN:(.*?)\]")
        matches = pattern.findall(text)
        
        if not matches:
            return
            
        gen_dir = get_images_generated_dir()
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        for i, data in enumerate(matches):
            filename = f"gen_{timestamp}_{i}.png"
            file_path = gen_dir / filename
            try:
                # If it's a file path already (some local SD implementations)
                if os.path.exists(data):
                    shutil.copy(data, file_path)
                    logger.info("Copied generated image from %s to %s", data, file_path)
                else:
                    # Basic attempt to decode if it's base64
                    img_data = base64.b64decode(data)
                    with open(file_path, "wb") as f:
                        f.write(img_data)
                    logger.info("Saved decoded base64 image to %s", file_path)
            except Exception as e:
                logger.error("Failed to save generated image: %s", e)

    def _extract_and_save_code(self, text: str) -> None:
        """Extracts code blocks and saves them to the codes folder."""
        import re
        from utils.paths import get_codes_dir
        
        # Matches ```[language]\n[code]```
        pattern = re.compile(r"```(?:\w+)?\n(.*?)\n```", re.DOTALL)
        code_blocks = pattern.findall(text)
        
        if not code_blocks:
            return
            
        codes_dir = get_codes_dir()
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        for i, code in enumerate(code_blocks):
            filename = f"code_{timestamp}_{i}.txt"
            # Try to guess extension if language was provided, but for simplicity we use .txt or .code
            file_path = codes_dir / filename
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(code.strip())
                logger.info("Saved code block to %s", file_path)
            except Exception as e:
                logger.error("Failed to save code block: %s", e)

    def detect_commands(self, text: str) -> List[str]:
        """Detects shell commands in the text."""
        import re
        # Look for code blocks tagged with bash, sh, shell, cmd, powershell, ps1, console, terminal, pwsh
        pattern = re.compile(r"```(?:bash|sh|shell|cmd|powershell|ps1|console|terminal|pwsh)\n(.*?)\n```", re.DOTALL)
        commands = pattern.findall(text)
        
        # Fallback: if no tagged blocks, check for any code block that looks like a command
        if not commands:
            generic_pattern = re.compile(r"```\n(.*?)\n```", re.DOTALL)
            generic_blocks = generic_pattern.findall(text)
            for block in generic_blocks:
                # Basic heuristic: starts with common command-line prefixes or matches common commands
                block_strip = block.strip()
                common_cmds = ("ls ", "dir ", "cd ", "mkdir ", "rm ", "cp ", "mv ", "git ", "pip ", "python ", "npm ", "apt ", "brew ", "sudo ")
                if block_strip.startswith(common_cmds) or block_strip.startswith(("./", ".\\", "cat ", "grep ", "find ", "echo ")):
                    commands.append(block_strip)
                    
        return [cmd.strip() for cmd in commands if cmd.strip()]

    def execute_command(self, command: str) -> Tuple[bool, str]:
        """Safe execution of a command."""
        return self._executor.run_command(command)

    def cancel_generation(self) -> None:
        """Cancels the active backend process."""
        if self._active_topic:
            # This is ad-hoc, ideally ModelManager tracks 'active' backend instance
            # For now we close the active model topic
            self._model_manager.unload_model(self._active_topic)
