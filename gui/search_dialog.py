"""
Search Dialog
Global search across all chat files with highlighted results.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer, Signal, QThread
from PySide6.QtGui import QTextCharFormat, QColor, QTextCursor
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QWidget, QFrame, QSplitter, QTextEdit,
    QProgressBar,
)

from utils.chat_indexer import ChatIndexer, SearchResult

logger = logging.getLogger(__name__)

SEARCH_STYLE = """
QDialog, QWidget { background: #1a1a2e; color: #e0e0e0; }
QLineEdit { background: #16213e; border: 2px solid #7c83fd; border-radius: 8px;
            padding: 8px 14px; color: #e0e0e0; font-size: 15px; }
QLineEdit:focus { border-color: #9499ff; }
QListWidget { background: #16213e; border: 1px solid #333; border-radius: 6px; }
QListWidget::item { padding: 10px 12px; border-bottom: 1px solid #1e1e3a; }
QListWidget::item:selected { background: #7c83fd22; border-left: 3px solid #7c83fd; }
QListWidget::item:hover { background: #ffffff08; }
QTextEdit { background: #0f1628; border: 1px solid #333; border-radius: 6px; color: #e0e0e0;
            font-family: 'Segoe UI', sans-serif; font-size: 13px; }
QPushButton { background: #7c83fd; color: white; border: none; border-radius: 6px;
              padding: 7px 16px; font-weight: bold; }
QPushButton:hover { background: #9499ff; }
QLabel { color: #c0c0e0; }
QProgressBar { background: #16213e; border: none; border-radius: 3px; height: 4px; }
QProgressBar::chunk { background: #7c83fd; border-radius: 3px; }
"""


class SearchResultItem(QListWidgetItem):
    def __init__(self, result: SearchResult):
        super().__init__()
        self.result = result
        # Format display text
        role_icon = "👤" if result.role == "user" else "🤖"
        try:
            ts_str = datetime.fromisoformat(result.timestamp).strftime("%m/%d %H:%M")
        except Exception:
            ts_str = ""
        self.setText(f"{role_icon}  {result.chat_name}  ·  {result.folder}  {ts_str}\n{result.snippet}")
        self.setToolTip(result.content[:300])


class SearchDialog(QDialog):
    """
    Global chat search dialog.
    jump_to_message(chat_path, message_index) emitted when user wants to navigate.
    """
    jump_to_message = Signal(str, int)  # chat_path, message_index

    def __init__(self, indexer: ChatIndexer, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Global Chat Search")
        self.setMinimumSize(780, 540)
        self.setStyleSheet(SEARCH_STYLE)
        self._indexer = indexer
        self._results = []
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._do_search)
        self._build_ui()

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(16, 16, 16, 16)
        main.setSpacing(12)

        # Header
        title_row = QHBoxLayout()
        title = QLabel("🔍 Search All Chats")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #7c83fd;")
        title_row.addWidget(title)
        title_row.addStretch()
        indexed_lbl = QLabel(f"  {self._indexer.total_indexed} chats indexed")
        indexed_lbl.setStyleSheet("color: #666; font-size: 11px;")
        self._indexed_lbl = indexed_lbl
        title_row.addWidget(indexed_lbl)
        main.addLayout(title_row)

        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Type to search across all conversations…")
        self.search_box.textChanged.connect(self._on_text_changed)
        main.addWidget(self.search_box)

        # Status/count
        status_row = QHBoxLayout()
        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("color: #666; font-size: 12px;")
        status_row.addWidget(self.status_lbl)
        status_row.addStretch()
        self._reindex_btn = QPushButton("↻ Reindex")
        self._reindex_btn.setStyleSheet("background: #2d2d4e; font-size: 11px; padding: 4px 10px;")
        self._reindex_btn.clicked.connect(self._reindex)
        status_row.addWidget(self._reindex_btn)
        main.addLayout(status_row)

        # Splitter: results | preview
        splitter = QSplitter(Qt.Horizontal)

        # Results list
        self.result_list = QListWidget()
        self.result_list.currentItemChanged.connect(self._on_result_selected)
        self.result_list.itemDoubleClicked.connect(self._on_jump)
        splitter.addWidget(self.result_list)

        # Preview panel
        preview_widget = QWidget()
        pv_layout = QVBoxLayout(preview_widget)
        pv_layout.setContentsMargins(0, 0, 0, 0)
        preview_lbl = QLabel("Preview (double-click result to jump to chat)")
        preview_lbl.setStyleSheet("color: #666; font-size: 11px; margin-bottom: 4px;")
        pv_layout.addWidget(preview_lbl)
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        pv_layout.addWidget(self.preview_text)

        jump_btn = QPushButton("↗ Jump to this Message")
        jump_btn.clicked.connect(self._on_jump)
        pv_layout.addWidget(jump_btn)
        splitter.addWidget(preview_widget)
        splitter.setSizes([360, 420])
        main.addWidget(splitter)

    def _on_text_changed(self, text: str):
        # Debounce 250ms
        self._search_timer.start(250)

    def _do_search(self):
        query = self.search_box.text().strip()
        if not query:
            self.result_list.clear()
            self.status_lbl.setText("")
            return

        self._results = self._indexer.search(query, max_results=200)
        self.result_list.clear()

        for r in self._results:
            item = SearchResultItem(r)
            self.result_list.addItem(item)

        count = len(self._results)
        more = " (showing 200)" if count == 200 else ""
        self.status_lbl.setText(f"{count} result{'s' if count != 1 else ''} found{more}")
        if self.result_list.count() > 0:
            self.result_list.setCurrentRow(0)

    def _on_result_selected(self, current: QListWidgetItem, _):
        if not isinstance(current, SearchResultItem):
            return
        result = current.result
        # Show preview with highlighted match
        content = result.content
        query = self.search_box.text().strip()

        self.preview_text.clear()
        self.preview_text.setPlainText(content)

        # Highlight all occurrences
        if query:
            cursor = self.preview_text.textCursor()
            fmt = QTextCharFormat()
            fmt.setBackground(QColor("#7c83fd55"))
            fmt.setForeground(QColor("#ffffff"))
            cursor.movePosition(QTextCursor.Start)
            q_lower = query.lower()
            content_lower = content.lower()
            pos = 0
            while True:
                pos = content_lower.find(q_lower, pos)
                if pos == -1:
                    break
                cursor.setPosition(pos)
                cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(query))
                cursor.setCharFormat(fmt)
                pos += len(query)
            # Scroll to first match
            first_pos = content_lower.find(q_lower)
            if first_pos >= 0:
                cursor.setPosition(first_pos)
                self.preview_text.setTextCursor(cursor)
                self.preview_text.ensureCursorVisible()

    def _on_jump(self, *args):
        current = self.result_list.currentItem()
        if not isinstance(current, SearchResultItem):
            return
        result = current.result
        self.jump_to_message.emit(str(result.chat_path), result.message_index)
        self.accept()

    def _reindex(self):
        self._indexer.force_reindex()
        self._reindex_btn.setText("↻ Indexing…")
        self._reindex_btn.setEnabled(False)
        QTimer.singleShot(3000, lambda: (
            self._reindex_btn.setText("↻ Reindex"),
            self._reindex_btn.setEnabled(True),
            self._indexed_lbl.setText(f"  {self._indexer.total_indexed} chats indexed"),
        ))

    def show_and_focus(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self.search_box.setFocus()
        self.search_box.selectAll()
