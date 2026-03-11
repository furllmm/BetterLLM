from __future__ import annotations

import logging
import subprocess
import os
import sys
import platform
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

class TerminalExecutor:
    """
    Handles safe execution of system commands (Windows/Linux).
    """
    def __init__(self):
        self.os_name = platform.system() # 'Windows', 'Linux', 'Darwin'

    def is_safe(self, command: str) -> bool:
        """Basic blacklist filter for dangerous commands."""
        blacklist = [
            "rm -rf /", "format ", "mkfs", "dd if=", ":(){ :|:& };:", 
            "del /s", "rd /s", "taskkill /f /im explorer.exe",
            "> /dev/sda", "chmod 777 /"
        ]
        cmd_lower = command.lower()
        return not any(b in cmd_lower for b in blacklist)

    def run_command(self, command: str) -> Tuple[bool, str]:
        """Executes a command and returns (success, output)."""
        if not self.is_safe(command):
            return False, "[Security Alert] Dangerous command blocked by BetterLLM."

        try:
            # Use shell=True for complex commands/pipes, but handle with care
            # On Windows, we prefer cmd.exe or powershell.exe depending on context
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="ignore"
            )
            stdout, stderr = process.communicate(timeout=30) # 30s timeout

            if process.returncode == 0:
                return True, stdout if stdout else "[Success: No output]"
            else:
                return False, stderr if stderr else f"[Error: Exit Code {process.returncode}]"
                
        except subprocess.TimeoutExpired:
            process.kill()
            return False, "[Error] Command timed out (30s limit)."
        except Exception as e:
            logger.exception(f"Command execution error: {command}")
            return False, f"[System Error] {str(e)}"

    def get_shell_name(self) -> str:
        if self.os_name == "Windows":
            return "CMD/PowerShell"
        return "Bash/Shell"
