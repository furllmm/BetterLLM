"""
Bookmarks Dialog
Quick access panel for saved/bookmarked messages.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QWidget, QTextEdit,
)
from PySide6.QtGui import QColor
from datetime import datetime

import utils.bookmarks as bm

STYLE = """
QDialog, QWidget { background: #1a1a2e; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
QListWidget { background: #16213e; border: 1px solid #333; border-radius: 8px; }
QListWidget::item { padding: 10px 12px; border-bottom: 1px solid #1e1e3a; }
QListWidget::item:selected { background: #7c83fd22; color: #7c83fd; border-left: 3px solid #7c83fd; }
QListWidget::item:hover { background: #ffffff08; }
QTextEdit { background: #0f1628; border: 1px solid #333; border-radius: 6px; color: #e0e0e0; font-size: 13px; }
QPushButton { background: #7c83fd; color: white; border: none; border-radius: 6px; padding: 7px 14px; font-weight: bold; }
QPushButton:hover { background: #9499ff; }
QPushButton#secondary { background: #2d2d4e; }
QPushButton#secondary:hover { background: #3d3d6e; }
QPushButton#danger { background: #4a1a1a; color: #f85149; }
"""


class BookmarksDialog(QDialog):
    jump_to = Signal(str, int)  # chat_path, message_index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔖 Bookmarks")
        self.setMinimumSize(640, 440)
        self.setStyleSheet(STYLE)
        self._build_ui()
        self._load()

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(16, 16, 16, 16)
        main.setSpacing(10)

        title = QLabel("🔖 Bookmarked Messages")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #7c83fd;")
        main.addWidget(title)

        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._on_select)
        self.list_widget.itemDoubleClicked.connect(self._jump)
        main.addWidget(self.list_widget, 1)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(120)
        main.addWidget(self.preview)

        btn_row = QHBoxLayout()
        self.btn_jump = QPushButton("↗ Jump to Message")
        self.btn_jump.clicked.connect(self._jump)
        btn_row.addWidget(self.btn_jump)
        self.btn_remove = QPushButton("🗑 Remove")
        self.btn_remove.setObjectName("danger")
        self.btn_remove.clicked.connect(self._remove)
        btn_row.addWidget(self.btn_remove)
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setObjectName("secondary")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        main.addLayout(btn_row)

    def _load(self):
        self.list_widget.clear()
        self._bookmarks = bm.get_all_bookmarks()
        for b in self._bookmarks:
            role_icon = "👤" if b["role"] == "user" else "🤖"
            try:
                ts = datetime.fromisoformat(b["saved_at"]).strftime("%m/%d %H:%M")
            except Exception:
                ts = ""
            item = QListWidgetItem(
                f"{role_icon}  {b['content'][:80]}…\n"
                f"  🔖 Saved {ts}"
            )
            item.setData(Qt.UserRole, b)
            self.list_widget.addItem(item)
        if not self._bookmarks:
            self.list_widget.addItem("No bookmarks yet. Right-click a message to bookmark it.")

    def _on_select(self, row: int):
        if row < 0 or row >= len(self._bookmarks):
            return
        b = self._bookmarks[row]
        self.preview.setPlainText(b["content"])

    def _jump(self, *args):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self._bookmarks):
            return
        b = self._bookmarks[row]
        self.jump_to.emit(b["chat_path"], b["message_index"])
        self.accept()

    def _remove(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self._bookmarks):
            return
        b = self._bookmarks[row]
        bm.remove_bookmark(b["chat_path"], b["message_index"])
        self._load()
