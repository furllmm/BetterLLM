"""
Conversation Timeline
Visual navigator for long conversations - shows all messages as a timeline
with jump-to-message functionality.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Dict, Optional

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy,
)
from PySide6.QtGui import QColor, QPalette, QFont


class TimelineNode(QFrame):
    clicked = Signal(int)   # message index

    def __init__(self, index: int, role: str, content: str,
                 timestamp: str, theme: str = "dark", parent=None):
        super().__init__(parent)
        self._index = index
        is_user = role == "user"
        c_accent = "#7c83fd" if is_user else "#3fb950"
        c_bg = "#1c2952" if is_user else "#1b2a1b"
        c_bg_dark = "#16213e"

        self.setObjectName("timeline_node")
        self.setMinimumHeight(44)
        self.setCursor(Qt.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(8)

        # Role dot
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {c_accent}; font-size: 10px;")
        dot.setFixedWidth(12)
        lay.addWidget(dot)

        # Content preview
        preview = content[:60].replace("\n", " ") + ("…" if len(content) > 60 else "")
        text_lbl = QLabel(preview)
        text_lbl.setStyleSheet(f"color: #c0c0c0; font-size: 11px;")
        text_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lay.addWidget(text_lbl, 1)

        # Timestamp
        try:
            ts = datetime.fromisoformat(timestamp).strftime("%H:%M")
        except Exception:
            ts = ""
        ts_lbl = QLabel(ts)
        ts_lbl.setStyleSheet("color: #555; font-size: 10px;")
        lay.addWidget(ts_lbl)

        self.setStyleSheet(f"""
            QFrame#timeline_node {{
                background: {c_bg_dark};
                border-left: 3px solid {c_accent};
                border-radius: 4px;
                margin: 1px 0;
            }}
            QFrame#timeline_node:hover {{
                background: {c_accent}22;
            }}
        """)

    def mousePressEvent(self, event):
        self.clicked.emit(self._index)
        super().mousePressEvent(event)


class TimelinePanel(QWidget):
    """Sidebar panel showing conversation as a scrollable timeline."""
    jump_to_message = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(200)
        self.setMaximumWidth(260)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        header = QWidget()
        header.setStyleSheet("background: #13191f; border-bottom: 1px solid #30363d;")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(10, 6, 10, 6)
        title = QLabel("🗂 Timeline")
        title.setStyleSheet("color: #7c83fd; font-weight: bold; font-size: 12px;")
        h_lay.addWidget(title)
        h_lay.addStretch()
        self.count_lbl = QLabel("")
        self.count_lbl.setStyleSheet("color: #555; font-size: 10px;")
        h_lay.addWidget(self.count_lbl)
        lay.addWidget(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("""
            QScrollArea { background: #0d1117; border: none; }
            QScrollBar:vertical { background: #13191f; width: 6px; }
            QScrollBar::handle:vertical { background: #30363d; border-radius: 3px; }
        """)

        self.container = QWidget()
        self.container.setStyleSheet("background: #0d1117;")
        self.container_lay = QVBoxLayout(self.container)
        self.container_lay.setContentsMargins(6, 6, 6, 6)
        self.container_lay.setSpacing(2)
        self.container_lay.addStretch()

        self.scroll.setWidget(self.container)
        lay.addWidget(self.scroll, 1)

    def update_messages(self, messages: List[Dict]):
        """Rebuild timeline from message list."""
        # Clear existing nodes
        while self.container_lay.count() > 1:
            item = self.container_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        prev_date = None
        for i, m in enumerate(messages):
            role = m.get("role", "user")
            content = m.get("content", "")
            ts = m.get("timestamp", "")

            # Date separator
            try:
                msg_date = datetime.fromisoformat(ts).date()
                if prev_date is None or msg_date != prev_date:
                    date_lbl = QLabel(msg_date.strftime("%b %d"))
                    date_lbl.setStyleSheet(
                        "color: #555; font-size: 10px; text-align: center; "
                        "border-top: 1px solid #1e1e3a; padding-top: 4px; margin: 4px 0;"
                    )
                    self.container_lay.insertWidget(self.container_lay.count() - 1, date_lbl)
                    prev_date = msg_date
            except Exception:
                pass

            node = TimelineNode(i, role, content, ts)
            node.clicked.connect(self.jump_to_message.emit)
            self.container_lay.insertWidget(self.container_lay.count() - 1, node)

        self.count_lbl.setText(f"{len(messages)}")
        # Scroll to bottom
        self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()
        )

    def clear(self):
        while self.container_lay.count() > 1:
            item = self.container_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.count_lbl.setText("")
