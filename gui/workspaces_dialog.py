"""
Project Workspaces Dialog
Group chats, files, and prompts into named projects.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QWidget, QLineEdit, QTextEdit,
    QSplitter, QMessageBox, QInputDialog, QFrame,
)
from PySide6.QtGui import QColor

from utils.workspaces import (
    get_all_workspaces, create_workspace, update_workspace,
    delete_workspace, add_chat_to_workspace, remove_chat_from_workspace,
)

STYLE = """
QDialog, QWidget { background: #1a1a2e; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
QListWidget { background: #16213e; border: 1px solid #333; border-radius: 8px; }
QListWidget::item { padding: 12px 14px; border-bottom: 1px solid #1e1e3a; }
QListWidget::item:selected { background: #7c83fd22; color: #7c83fd; border-left: 3px solid #7c83fd; }
QListWidget::item:hover { background: #ffffff08; }
QLineEdit, QTextEdit { background: #16213e; border: 1px solid #444; border-radius: 6px;
                        color: #e0e0e0; padding: 7px; font-size: 13px; }
QLineEdit:focus, QTextEdit:focus { border-color: #7c83fd; }
QPushButton { background: #7c83fd; color: white; border: none; border-radius: 6px;
              padding: 7px 14px; font-weight: bold; }
QPushButton:hover { background: #9499ff; }
QPushButton#secondary { background: #2d2d4e; }
QPushButton#danger { background: #4a1a1a; color: #f85149; }
QLabel#field { color: #8b949e; font-size: 11px; margin-top: 6px; }
"""

WORKSPACE_ICONS = ["📁", "🚀", "💻", "🔬", "✍️", "📊", "🎯", "⚡", "🌍", "🎮"]
WORKSPACE_COLORS = ["#7c83fd", "#3fb950", "#e94560", "#58a6ff", "#d29922", "#a371f7"]


class WorkspacesDialog(QDialog):
    workspace_activated = Signal(str)   # workspace name

    def __init__(self, current_chat_path: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("🗂 Project Workspaces")
        self.setMinimumSize(740, 520)
        self.setStyleSheet(STYLE)
        self._current_chat = current_chat_path
        self._selected: str = ""
        self._build_ui()
        self._load()

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(16, 16, 16, 16)
        main.setSpacing(10)

        title = QLabel("🗂 Project Workspaces")
        title.setStyleSheet("font-size: 17px; font-weight: bold; color: #7c83fd;")
        main.addWidget(title)

        splitter = QSplitter(Qt.Horizontal)

        # Left
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(4)
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._on_select)
        self.list_widget.itemDoubleClicked.connect(self._activate)
        ll.addWidget(self.list_widget, 1)

        new_row = QHBoxLayout()
        self.btn_new = QPushButton("+ New Workspace")
        self.btn_new.clicked.connect(self._new_workspace)
        new_row.addWidget(self.btn_new)
        self.btn_del = QPushButton("🗑")
        self.btn_del.setObjectName("danger")
        self.btn_del.setFixedWidth(36)
        self.btn_del.clicked.connect(self._delete_workspace)
        new_row.addWidget(self.btn_del)
        ll.addLayout(new_row)
        splitter.addWidget(left)

        # Right: editor
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        rl.setSpacing(4)

        rl.addWidget(QLabel("Name"))
        self.name_edit = QLineEdit()
        rl.addWidget(self.name_edit)

        rl.addWidget(QLabel("Description"))
        self.desc_edit = QLineEdit()
        rl.addWidget(self.desc_edit)

        rl.addWidget(QLabel("Notes"))
        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(80)
        rl.addWidget(self.notes_edit)

        chat_lbl = QHBoxLayout()
        chat_lbl.addWidget(QLabel("Chats in this workspace:"))
        chat_lbl.addStretch()
        if self._current_chat:
            self.btn_add_chat = QPushButton("+ Add Current Chat")
            self.btn_add_chat.setObjectName("secondary")
            self.btn_add_chat.clicked.connect(self._add_current_chat)
            chat_lbl.addWidget(self.btn_add_chat)
        rl.addLayout(chat_lbl)

        self.chats_list = QListWidget()
        self.chats_list.setMaximumHeight(100)
        rl.addWidget(self.chats_list)

        save_row = QHBoxLayout()
        self.btn_save = QPushButton("💾 Save")
        self.btn_save.clicked.connect(self._save_changes)
        save_row.addWidget(self.btn_save)
        rl.addLayout(save_row)
        rl.addStretch()

        splitter.addWidget(right)
        splitter.setSizes([240, 480])
        main.addWidget(splitter, 1)

        btn_row = QHBoxLayout()
        self.btn_activate = QPushButton("✅ Switch to Workspace")
        self.btn_activate.clicked.connect(self._activate)
        btn_row.addWidget(self.btn_activate)
        btn_row.addStretch()
        close = QPushButton("Close")
        close.setObjectName("secondary")
        close.clicked.connect(self.accept)
        btn_row.addWidget(close)
        main.addLayout(btn_row)

    def _load(self):
        self.list_widget.clear()
        self._workspaces = get_all_workspaces()
        for ws in self._workspaces:
            icon = ws.get("icon", "📁")
            n = len(ws.get("chat_paths", []))
            item = QListWidgetItem(f"{icon}  {ws['name']}\n   {ws.get('description','')}  ({n} chats)")
            item.setData(Qt.UserRole, ws["name"])
            self.list_widget.addItem(item)
        if not self._workspaces:
            self.list_widget.addItem("No workspaces yet. Create one!")

    def _on_select(self, row: int):
        if row < 0 or row >= len(self._workspaces):
            return
        ws = self._workspaces[row]
        self._selected = ws["name"]
        self.name_edit.setText(ws["name"])
        self.desc_edit.setText(ws.get("description", ""))
        self.notes_edit.setPlainText(ws.get("notes", ""))
        self.chats_list.clear()
        for p in ws.get("chat_paths", []):
            import os
            self.chats_list.addItem(os.path.basename(p))

    def _new_workspace(self):
        name, ok = QInputDialog.getText(self, "New Workspace", "Workspace name:")
        if ok and name.strip():
            create_workspace(name.strip())
            self._load()

    def _delete_workspace(self):
        if not self._selected:
            return
        if QMessageBox.question(self, "Delete", f"Delete '{self._selected}'?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            delete_workspace(self._selected)
            self._selected = ""
            self._load()

    def _save_changes(self):
        if not self._selected:
            return
        update_workspace(self._selected, {
            "description": self.desc_edit.text().strip(),
            "notes": self.notes_edit.toPlainText().strip(),
        })
        self._load()

    def _add_current_chat(self):
        if self._selected and self._current_chat:
            add_chat_to_workspace(self._selected, self._current_chat)
            self._load()

    def _activate(self, *_):
        if self._selected:
            self.workspace_activated.emit(self._selected)
            self.accept()
