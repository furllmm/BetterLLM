"""
Snapshots Dialog
Save and restore conversation checkpoints.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QWidget, QInputDialog, QMessageBox,
    QTextEdit,
)

import utils.snapshots as snap_util

STYLE = """
QDialog, QWidget { background: #1a1a2e; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
QListWidget { background: #16213e; border: 1px solid #333; border-radius: 8px; }
QListWidget::item { padding: 10px 14px; border-bottom: 1px solid #1e1e3a; }
QListWidget::item:selected { background: #7c83fd22; color: #7c83fd; border-left: 3px solid #7c83fd; }
QListWidget::item:hover { background: #ffffff08; }
QTextEdit { background: #0f1628; border: 1px solid #333; border-radius: 6px;
            color: #e0e0e0; font-size: 12px; padding: 6px; }
QPushButton { background: #7c83fd; color: white; border: none; border-radius: 6px;
              padding: 7px 14px; font-weight: bold; }
QPushButton:hover { background: #9499ff; }
QPushButton#secondary { background: #2d2d4e; }
QPushButton#danger { background: #4a1a1a; color: #f85149; }
"""


class SnapshotsDialog(QDialog):
    restore_snapshot = Signal(list)   # list of message dicts

    def __init__(self, current_chat_path: Optional[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("📸 Chat Snapshots")
        self.setMinimumSize(620, 440)
        self.setStyleSheet(STYLE)
        self._chat_path = current_chat_path
        self._build_ui()
        self._load()

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(16, 16, 16, 16)
        main.setSpacing(10)

        hdr = QHBoxLayout()
        title = QLabel("📸 Chat Snapshots")
        title.setStyleSheet("font-size: 17px; font-weight: bold; color: #7c83fd;")
        hdr.addWidget(title)
        hdr.addStretch()
        info = QLabel("Checkpoints let you rewind to any point in the conversation")
        info.setStyleSheet("color: #666; font-size: 11px;")
        hdr.addWidget(info)
        main.addLayout(hdr)

        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._on_select)
        self.list_widget.itemDoubleClicked.connect(self._restore)
        main.addWidget(self.list_widget, 1)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(100)
        self.preview.setPlaceholderText("Select a snapshot to preview…")
        main.addWidget(self.preview)

        btn_row = QHBoxLayout()
        self.btn_restore = QPushButton("⏪ Restore")
        self.btn_restore.clicked.connect(self._restore)
        btn_row.addWidget(self.btn_restore)

        self.btn_rename = QPushButton("✏️ Rename")
        self.btn_rename.setObjectName("secondary")
        self.btn_rename.clicked.connect(self._rename)
        btn_row.addWidget(self.btn_rename)

        self.btn_delete = QPushButton("🗑 Delete")
        self.btn_delete.setObjectName("danger")
        self.btn_delete.clicked.connect(self._delete)
        btn_row.addWidget(self.btn_delete)

        btn_row.addStretch()
        close = QPushButton("Close")
        close.setObjectName("secondary")
        close.clicked.connect(self.accept)
        btn_row.addWidget(close)
        main.addLayout(btn_row)

    def _load(self):
        self.list_widget.clear()
        self._snaps = snap_util.list_snapshots(self._chat_path)
        if not self._snaps:
            self.list_widget.addItem("No snapshots yet. Use Ctrl+Shift+S to save a checkpoint.")
            return
        for s in self._snaps:
            try:
                ts = datetime.fromisoformat(s["created_at"]).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                ts = s.get("created_at", "")
            n = s.get("message_count", 0)
            item = QListWidgetItem(f"📸  {s['label']}\n   {ts}  ·  {n} messages")
            item.setData(Qt.UserRole, s["id"])
            self.list_widget.addItem(item)

    def _on_select(self, row: int):
        if row < 0 or row >= len(self._snaps):
            return
        s = self._snaps[row]
        msgs = s.get("messages", [])
        lines = []
        for m in msgs[-5:]:
            role = "You" if m.get("role") == "user" else "AI"
            lines.append(f"[{role}] {m.get('content','')[:80]}…")
        self.preview.setPlainText("\n".join(lines))

    def _restore(self, *_):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self._snaps):
            return
        s = self._snaps[row]
        reply = QMessageBox.question(
            self, "Restore Snapshot",
            f"Restore '{s['label']}'?\nThis will replace current conversation history.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.restore_snapshot.emit(s.get("messages", []))
            self.accept()

    def _rename(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self._snaps):
            return
        s = self._snaps[row]
        text, ok = QInputDialog.getText(self, "Rename", "New label:", text=s["label"])
        if ok and text.strip():
            loaded = snap_util.load_snapshot(s["id"])
            if loaded:
                loaded["label"] = text.strip()
                import json
                from utils.paths import get_base_dir
                f = get_base_dir() / "snapshots" / f"{s['id']}.json"
                f.write_text(json.dumps(loaded, indent=2), encoding="utf-8")
            self._load()

    def _delete(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self._snaps):
            return
        s = self._snaps[row]
        snap_util.delete_snapshot(s["id"])
        self._load()
