"""
AI Suggestion Sidebar
Shows follow-up questions and next-prompt suggestions after each response.
Uses a background worker to generate suggestions without blocking the UI.
"""
from __future__ import annotations

import json
import re
from typing import List, Optional

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QSizePolicy,
)


class SuggestionWorker(QThread):
    suggestions_ready = Signal(list)

    def __init__(self, session, last_exchange: str):
        super().__init__()
        self._session = session
        self._exchange = last_exchange
        self._cancelled = False

    def run(self):
        try:
            prompt = (
                "Based on this conversation excerpt, generate exactly 4 short follow-up questions "
                "or next prompts the user might want to ask. Return ONLY a JSON array of strings, "
                "nothing else. Example: [\"Question 1?\", \"Question 2?\", ...]\n\n"
                f"Excerpt:\n{self._exchange[-800:]}"
            )
            full = ""
            for token in self._session.send_message_stream(prompt, False, False, None,
                                                            {"max_tokens": 200, "temperature": 0.7}):
                if self._cancelled:
                    return
                full += token

            # Remove the suggestion query from session history
            h = self._session._history
            if h and h[-1].role == "assistant":
                h.pop()
            if h and h[-1].role == "user":
                h.pop()

            # Parse JSON
            match = re.search(r'\[.*?\]', full, re.DOTALL)
            if match:
                suggestions = json.loads(match.group())
                if isinstance(suggestions, list):
                    self.suggestions_ready.emit([str(s) for s in suggestions[:4]])
        except Exception:
            pass

    def cancel(self):
        self._cancelled = True


class SuggestionChip(QPushButton):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("suggestion_chip")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(32)
        self.setStyleSheet("""
            QPushButton#suggestion_chip {
                background: #1c2128;
                color: #8b949e;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 5px 10px;
                text-align: left;
                font-size: 12px;
            }
            QPushButton#suggestion_chip:hover {
                background: #7c83fd22;
                border-color: #7c83fd;
                color: #e6edf3;
            }
        """)
        self.setCursor(Qt.PointingHandCursor)


class SuggestionSidebar(QWidget):
    """Panel that shows AI-generated follow-up suggestions."""
    suggestion_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaximumWidth(240)
        self.setMinimumWidth(200)
        self._worker: Optional[SuggestionWorker] = None
        self._build_ui()
        self.setVisible(False)

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        header = QWidget()
        header.setStyleSheet("background: #13191f; border-left: 1px solid #30363d; border-bottom: 1px solid #30363d;")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(10, 6, 8, 6)
        title = QLabel("💡 Suggestions")
        title.setStyleSheet("color: #7c83fd; font-weight: bold; font-size: 12px;")
        h_lay.addWidget(title, 1)
        self.loading_lbl = QLabel("")
        self.loading_lbl.setStyleSheet("color: #555; font-size: 10px;")
        h_lay.addWidget(self.loading_lbl)
        btn_hide = QPushButton("✕")
        btn_hide.setStyleSheet("background: transparent; color: #555; border: none; font-size: 12px;")
        btn_hide.setFixedSize(20, 20)
        btn_hide.clicked.connect(lambda: self.setVisible(False))
        h_lay.addWidget(btn_hide)
        lay.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background: #0d1117; border: none; border-left: 1px solid #30363d; }"
            "QScrollBar:vertical { background: #13191f; width: 5px; }"
            "QScrollBar::handle:vertical { background: #30363d; border-radius: 2px; }"
        )

        self.content = QWidget()
        self.content.setStyleSheet("background: #0d1117;")
        self.content_lay = QVBoxLayout(self.content)
        self.content_lay.setContentsMargins(8, 8, 8, 8)
        self.content_lay.setSpacing(6)

        self.placeholder = QLabel("Suggestions will appear\nafter a response.")
        self.placeholder.setStyleSheet("color: #444; font-size: 11px; text-align: center;")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.content_lay.addWidget(self.placeholder)
        self.content_lay.addStretch()

        scroll.setWidget(self.content)
        lay.addWidget(scroll, 1)

    def set_loading(self, loading: bool):
        self.loading_lbl.setText("⟳" if loading else "")

    def update_suggestions(self, suggestions: List[str]):
        self.set_loading(False)
        # Clear chips
        while self.content_lay.count() > 1:
            item = self.content_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not suggestions:
            self.placeholder.setVisible(True)
            return

        self.placeholder.setVisible(False)
        for s in suggestions:
            chip = SuggestionChip(s)
            chip.clicked.connect(lambda checked, text=s: self.suggestion_clicked.emit(text))
            self.content_lay.insertWidget(self.content_lay.count() - 1, chip)

    def generate_for(self, session, exchange: str):
        """Start background generation of suggestions."""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
        self.set_loading(True)
        self.setVisible(True)
        self._worker = SuggestionWorker(session, exchange)
        self._worker.suggestions_ready.connect(self.update_suggestions)
        self._worker.start()

    def clear(self):
        self.update_suggestions([])
        self.setVisible(False)
