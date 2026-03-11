"""
Assistant Profiles Dialog
Create, edit, and switch between assistant personalities.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QTextEdit, QLineEdit,
    QDialogButtonBox, QWidget, QSplitter, QMessageBox, QInputDialog,
)
from PySide6.QtGui import QFont, QColor

from utils.assistant_profiles import load_profiles, save_profiles, DEFAULT_PROFILES

STYLE = """
QDialog, QWidget { background: #1a1a2e; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
QListWidget { background: #16213e; border: 1px solid #333; border-radius: 8px; }
QListWidget::item { padding: 12px 14px; border-bottom: 1px solid #1e1e3a; }
QListWidget::item:selected { background: #7c83fd22; color: #7c83fd; border-left: 3px solid #7c83fd; }
QListWidget::item:hover { background: #ffffff08; }
QTextEdit, QLineEdit { background: #16213e; border: 1px solid #444; border-radius: 6px;
                        color: #e0e0e0; padding: 8px; font-size: 13px; }
QPushButton { background: #7c83fd; color: white; border: none; border-radius: 6px;
              padding: 7px 16px; font-weight: bold; }
QPushButton:hover { background: #9499ff; }
QPushButton#secondary { background: #2d2d4e; }
QPushButton#secondary:hover { background: #3d3d6e; }
QPushButton#danger { background: #4a1a1a; color: #f85149; }
QPushButton#danger:hover { background: #6a2020; }
QLabel { color: #c0c0e0; }
QLabel#title { font-size: 18px; font-weight: bold; color: #7c83fd; }
QLabel#field_label { color: #8b949e; font-size: 11px; margin-top: 6px; }
"""


class ProfilesDialog(QDialog):
    profile_selected = Signal(str)  # profile name

    def __init__(self, current_profile: str = "Default", parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎭 Assistant Profiles")
        self.setMinimumSize(720, 520)
        self.setStyleSheet(STYLE)
        self._profiles = load_profiles()
        self._current = current_profile
        self._selected = current_profile
        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setSpacing(12)
        main.setContentsMargins(16, 16, 16, 16)

        title = QLabel("🎭 Assistant Profiles")
        title.setObjectName("title")
        main.addWidget(title)

        splitter = QSplitter(Qt.Horizontal)

        # Left: profile list
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.profile_list = QListWidget()
        self.profile_list.currentRowChanged.connect(self._on_select)
        ll.addWidget(self.profile_list)

        btn_row = QHBoxLayout()
        self.btn_new = QPushButton("+ New")
        self.btn_new.setObjectName("secondary")
        self.btn_new.clicked.connect(self._new_profile)
        self.btn_del = QPushButton("🗑")
        self.btn_del.setObjectName("danger")
        self.btn_del.setFixedWidth(36)
        self.btn_del.clicked.connect(self._delete_profile)
        btn_row.addWidget(self.btn_new)
        btn_row.addWidget(self.btn_del)
        ll.addLayout(btn_row)
        splitter.addWidget(left)

        # Right: editor
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        rl.setSpacing(4)

        rl.addWidget(QLabel("Name"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Profile name…")
        rl.addWidget(self.name_edit)

        rl.addWidget(QLabel("Icon (emoji)"))
        self.icon_edit = QLineEdit()
        self.icon_edit.setPlaceholderText("🤖")
        self.icon_edit.setMaximumWidth(70)
        rl.addWidget(self.icon_edit)

        rl.addWidget(QLabel("Description"))
        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("Short description…")
        rl.addWidget(self.desc_edit)

        rl.addWidget(QLabel("System Prompt"))
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("Enter the system prompt for this assistant…")
        self.prompt_edit.setMinimumHeight(160)
        rl.addWidget(self.prompt_edit, 1)

        save_row = QHBoxLayout()
        self.btn_save_profile = QPushButton("💾 Save Changes")
        self.btn_save_profile.clicked.connect(self._save_profile)
        save_row.addWidget(self.btn_save_profile)
        rl.addLayout(save_row)

        splitter.addWidget(right)
        splitter.setSizes([220, 480])
        main.addWidget(splitter, 1)

        # Bottom buttons
        btn_box = QHBoxLayout()
        self.btn_use = QPushButton("✅ Use This Profile")
        self.btn_use.clicked.connect(self._use_profile)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondary")
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_use)
        btn_box.addWidget(cancel_btn)
        main.addLayout(btn_box)

    def _refresh_list(self):
        self.profile_list.clear()
        for name, p in self._profiles.items():
            icon = p.get("icon", "🤖")
            item = QListWidgetItem(f"{icon}  {name}")
            item.setData(Qt.UserRole, name)
            if name == self._current:
                item.setForeground(QColor("#7c83fd"))
            self.profile_list.addItem(item)
        # Select current
        for i in range(self.profile_list.count()):
            if self.profile_list.item(i).data(Qt.UserRole) == self._selected:
                self.profile_list.setCurrentRow(i)
                break

    def _on_select(self, row: int):
        if row < 0:
            return
        name = self.profile_list.item(row).data(Qt.UserRole)
        self._selected = name
        p = self._profiles.get(name, {})
        self.name_edit.setText(name)
        self.icon_edit.setText(p.get("icon", "🤖"))
        self.desc_edit.setText(p.get("description", ""))
        self.prompt_edit.setPlainText(p.get("system_prompt", ""))

    def _save_profile(self):
        old_name = self._selected
        new_name = self.name_edit.text().strip()
        if not new_name:
            return
        p = {
            "icon": self.icon_edit.text().strip() or "🤖",
            "description": self.desc_edit.text().strip(),
            "system_prompt": self.prompt_edit.toPlainText().strip(),
            "color": self._profiles.get(old_name, {}).get("color", "#7c83fd"),
        }
        if old_name and old_name != new_name:
            self._profiles.pop(old_name, None)
        self._profiles[new_name] = p
        self._selected = new_name
        save_profiles(self._profiles)
        self._refresh_list()

    def _new_profile(self):
        name, ok = QInputDialog.getText(self, "New Profile", "Profile name:")
        if ok and name.strip():
            self._profiles[name.strip()] = {
                "icon": "🤖", "description": "", "system_prompt": "", "color": "#7c83fd"
            }
            self._selected = name.strip()
            self._refresh_list()

    def _delete_profile(self):
        if self._selected in DEFAULT_PROFILES:
            QMessageBox.warning(self, "Cannot Delete", "Built-in profiles cannot be deleted.")
            return
        reply = QMessageBox.question(self, "Delete Profile", f"Delete '{self._selected}'?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self._profiles.pop(self._selected, None)
            save_profiles(self._profiles)
            self._selected = "Default"
            self._refresh_list()

    def _use_profile(self):
        self.profile_selected.emit(self._selected)
        self.accept()
