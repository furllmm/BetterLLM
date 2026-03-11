"""
Prompt Versions Dialog
Browse, search, and restore past prompt submissions.
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QTextEdit, QSplitter, QWidget,
    QMessageBox,
)

from utils.prompt_versions import get_history, delete_entry, clear_all, record_prompt

STYLE = """
QDialog, QWidget { background: #1a1a2e; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
QListWidget { background: #16213e; border: 1px solid #333; border-radius: 8px; }
QListWidget::item { padding: 10px 14px; border-bottom: 1px solid #1e1e3a; }
QListWidget::item:selected { background: #7c83fd22; color: #7c83fd; border-left: 3px solid #7c83fd; }
QListWidget::item:hover { background: #ffffff08; }
QLineEdit { background: #16213e; border: 1px solid #444; border-radius: 6px;
            padding: 7px 12px; color: #e0e0e0; font-size: 13px; }
QLineEdit:focus { border-color: #7c83fd; }
QTextEdit { background: #0f1628; border: 1px solid #333; border-radius: 6px;
            color: #e0e0e0; font-size: 13px; padding: 8px; }
QPushButton { background: #7c83fd; color: white; border: none; border-radius: 6px;
              padding: 7px 14px; font-weight: bold; }
QPushButton:hover { background: #9499ff; }
QPushButton#secondary { background: #2d2d4e; }
QPushButton#danger { background: #4a1a1a; color: #f85149; }
"""


class PromptVersionsDialog(QDialog):
    prompt_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🕓 Prompt History")
        self.setMinimumSize(760, 520)
        self.setStyleSheet(STYLE)
        self._entries = []
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._do_search)
        self._build_ui()
        self._do_search()

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(16, 16, 16, 16)
        main.setSpacing(10)

        title = QLabel("🕓 Prompt History")
        title.setStyleSheet("font-size: 17px; font-weight: bold; color: #7c83fd;")
        main.addWidget(title)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search prompt history…")
        self.search_box.textChanged.connect(lambda _: self._search_timer.start(200))
        main.addWidget(self.search_box)

        splitter = QSplitter(Qt.Horizontal)

        # List
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._on_select)
        self.list_widget.itemDoubleClicked.connect(self._use_prompt)
        splitter.addWidget(self.list_widget)

        # Preview
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        rl.addWidget(QLabel("Full Prompt:"))
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        rl.addWidget(self.preview, 1)
        splitter.addWidget(right)
        splitter.setSizes([340, 400])
        main.addWidget(splitter, 1)

        btn_row = QHBoxLayout()
        self.btn_use = QPushButton("✅ Use This Prompt")
        self.btn_use.clicked.connect(self._use_prompt)
        btn_row.addWidget(self.btn_use)

        self.btn_delete = QPushButton("🗑 Delete")
        self.btn_delete.setObjectName("danger")
        self.btn_delete.clicked.connect(self._delete)
        btn_row.addWidget(self.btn_delete)

        self.btn_clear = QPushButton("🗑 Clear All")
        self.btn_clear.setObjectName("danger")
        self.btn_clear.clicked.connect(self._clear_all)
        btn_row.addWidget(self.btn_clear)

        btn_row.addStretch()
        self.count_lbl = QLabel("")
        self.count_lbl.setStyleSheet("color: #666; font-size: 11px;")
        btn_row.addWidget(self.count_lbl)

        close = QPushButton("Close")
        close.setObjectName("secondary")
        close.clicked.connect(self.reject)
        btn_row.addWidget(close)
        main.addLayout(btn_row)

    def _do_search(self):
        q = self.search_box.text().strip()
        self._entries = get_history(search=q, limit=200)
        self.list_widget.clear()
        for e in self._entries:
            try:
                ts = datetime.fromisoformat(e["created_at"]).strftime("%m/%d %H:%M")
            except Exception:
                ts = ""
            preview = e["prompt"][:80].replace("\n", " ")
            item = QListWidgetItem(f"{ts}  {preview}")
            item.setData(Qt.UserRole, e["id"])
            self.list_widget.addItem(item)
        self.count_lbl.setText(f"{len(self._entries)} entries")

    def _on_select(self, row: int):
        if 0 <= row < len(self._entries):
            self.preview.setPlainText(self._entries[row]["prompt"])

    def _use_prompt(self, *_):
        row = self.list_widget.currentRow()
        if 0 <= row < len(self._entries):
            self.prompt_selected.emit(self._entries[row]["prompt"])
            self.accept()

    def _delete(self):
        row = self.list_widget.currentRow()
        if 0 <= row < len(self._entries):
            delete_entry(self._entries[row]["id"])
            self._do_search()

    def _clear_all(self):
        if QMessageBox.question(self, "Clear History", "Delete all prompt history?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            clear_all()
            self._do_search()
