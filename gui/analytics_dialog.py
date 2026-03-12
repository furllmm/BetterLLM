"""
Chat Analytics Dialog
Shows statistics for the current or all chats.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
    QWidget, QGridLayout, QFrame, QTabWidget,
)
from PySide6.QtGui import QFont

from utils.chat_analytics import compute_chat_stats, compute_folder_stats, compute_usage_dashboard
from utils.paths import get_chats_dir

STYLE = """
QDialog, QWidget { background: #1a1a2e; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
QTabWidget::pane { border: 1px solid #333; border-radius: 6px; }
QTabBar::tab { background: #16213e; color: #888; padding: 8px 16px; border-radius: 4px 4px 0 0; margin-right: 2px; }
QTabBar::tab:selected { background: #7c83fd22; color: #7c83fd; border-bottom: 2px solid #7c83fd; }
QFrame#stat_card { background: #16213e; border: 1px solid #2d2d4e; border-radius: 10px; padding: 8px; }
QLabel#stat_value { font-size: 22px; font-weight: bold; color: #7c83fd; }
QLabel#stat_label { font-size: 11px; color: #666; }
QLabel#section_title { font-size: 14px; font-weight: bold; color: #c0c0e0; margin-top: 8px; }
QPushButton { background: #2d2d4e; color: #e0e0e0; border: none; border-radius: 6px; padding: 7px 16px; }
QPushButton:hover { background: #3d3d6e; }
"""


def _stat_card(value: str, label: str, color: str = "#7c83fd") -> QFrame:
    card = QFrame()
    card.setObjectName("stat_card")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(12, 10, 12, 10)
    lay.setSpacing(2)
    v = QLabel(value)
    v.setObjectName("stat_value")
    v.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {color};")
    v.setAlignment(Qt.AlignCenter)
    lay.addWidget(v)
    l = QLabel(label)
    l.setObjectName("stat_label")
    l.setAlignment(Qt.AlignCenter)
    lay.addWidget(l)
    return card


class ChatAnalyticsDialog(QDialog):
    def __init__(self, current_chat_path: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📊 Chat Analytics")
        self.setMinimumSize(620, 460)
        self.setStyleSheet(STYLE)
        self._chat_path = current_chat_path
        self._build_ui()

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(16, 16, 16, 16)
        main.setSpacing(12)

        title = QLabel("📊 Chat Analytics")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #7c83fd;")
        main.addWidget(title)

        tabs = QTabWidget()

        # Tab 1: Current chat
        if self._chat_path:
            tab1 = QWidget()
            self._build_chat_tab(tab1, Path(self._chat_path))
            tabs.addTab(tab1, "Current Chat")

        # Tab 2: All chats
        tab2 = QWidget()
        self._build_global_tab(tab2)
        tabs.addTab(tab2, "All Chats")

        main.addWidget(tabs, 1)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        main.addWidget(close_btn, alignment=Qt.AlignRight)

    def _build_chat_tab(self, tab: QWidget, path: Path):
        stats = compute_chat_stats(path)
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(12, 12, 12, 12)

        if not stats:
            lay.addWidget(QLabel("No data available for this chat."))
            return

        grid = QGridLayout()
        grid.setSpacing(10)

        cards = [
            (str(stats["total_messages"]), "Total Messages", "#7c83fd"),
            (str(stats["user_messages"]), "Your Messages", "#58a6ff"),
            (str(stats["assistant_messages"]), "AI Responses", "#3fb950"),
            (f"{stats['total_tokens']:,}", "Est. Tokens", "#e94560"),
            (f"{stats['avg_response_time_s']}s", "Avg Response Time", "#d29922"),
            (f"{stats['duration_minutes']}m", "Conversation Duration", "#a371f7"),
        ]

        for i, (val, label, color) in enumerate(cards):
            grid.addWidget(_stat_card(val, label, color), i // 3, i % 3)

        lay.addLayout(grid)

        info = QLabel(f"📅 Started: {stats['first_message']}  ·  Last: {stats['last_message']}")
        info.setStyleSheet("color: #666; font-size: 11px; margin-top: 8px;")
        lay.addWidget(info)
        lay.addStretch()

    def _build_global_tab(self, tab: QWidget):
        chats_dir = get_chats_dir()
        stats = compute_folder_stats(chats_dir) if chats_dir.exists() else {}
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(12, 12, 12, 12)

        if not stats:
            lay.addWidget(QLabel("No chat data found."))
            return

        grid = QGridLayout()
        grid.setSpacing(10)

        cards = [
            (str(stats.get("chat_count", 0)), "Total Chats", "#7c83fd"),
            (str(stats.get("total_messages", 0)), "Total Messages", "#58a6ff"),
            (f"{stats.get('total_tokens', 0):,}", "Total Est. Tokens", "#3fb950"),
            (str(stats.get("user_messages", 0)), "User Messages", "#e94560"),
            (str(stats.get("assistant_messages", 0)), "AI Responses", "#d29922"),
            (f"{stats.get('duration_minutes', 0):,.0f}m", "Total Chat Time", "#a371f7"),
        ]

        for i, (val, label, color) in enumerate(cards):
            grid.addWidget(_stat_card(val, label, color), i // 3, i % 3)

        lay.addLayout(grid)

        dashboard = compute_usage_dashboard(chats_dir)
        breakdown = QTextEdit()
        breakdown.setReadOnly(True)
        breakdown.setMinimumHeight(180)

        lines = ["📌 Usage Breakdown", "", "By Topic:"]
        for topic, d in dashboard.get("by_topic", {}).items():
            lines.append(f"- {topic}: {d.get('chats',0)} chats · {d.get('messages',0)} msgs · ~{d.get('tokens',0)} tok")

        lines.append("")
        lines.append("Recent Days:")
        for day, d in list(dashboard.get("by_day", {}).items())[:7]:
            lines.append(f"- {day}: {d.get('messages',0)} msgs · ~{d.get('tokens',0)} tok")

        breakdown.setPlainText("\n".join(lines))
        lay.addWidget(breakdown)
        lay.addStretch()
