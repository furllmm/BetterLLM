#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

from cli.app import run_cli
from gui.app import run_gui
from gui.model_browser import run_model_browser


def is_shift_pressed() -> bool:
    """
    Checks if the Shift key is held down during startup (Windows only).
    """
    if sys.platform != "win32":
        return False

    try:
        import ctypes

        # VK_SHIFT is 0x10. GetAsyncKeyState returns a short where the high-order bit
        # is 1 if the key is down since the last call.
        return (ctypes.windll.user32.GetAsyncKeyState(0x10) & 0x8000) != 0
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Local LLM Desktop App")
    parser.add_argument(
        "--cli", action="store_true", help="Run in CLI mode instead of GUI"
    )
    parser.add_argument(
        "--models", action="store_true", help="Open Model Browser"
    )
    args = parser.parse_args()

    if args.models:
        run_model_browser()
        return

    # Shift + double click -> CLI
    # Normal double click -> GUI
    should_run_cli = args.cli or is_shift_pressed()

    if should_run_cli:
        run_cli()
    else:
        run_gui()


if __name__ == "__main__":
    main()
