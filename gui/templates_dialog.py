"""
Chat Templates Dialog
Quick-start specialized conversations from predefined setups.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QWidget, QTextEdit, QLineEdit,
    QComboBox, QSplitter,
)

from utils.chat_templates import get_all_templates, get_categories

STYLE = """
QDialog, QWidget { background: #1a1a2e; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
QListWidget { background: #16213e; border: 1px solid #333; border-radius: 8px; }
QListWidget::item { padding: 12px 14px; border-bottom: 1px solid #1e1e3a; }
QListWidget::item:selected { background: #7c83fd22; color: #7c83fd; border-left: 3px solid #7c83fd; }
QListWidget::item:hover { background: #ffffff08; }
QTextEdit { background: #0f1628; border: 1px solid #333; border-radius: 6px;
            color: #e0e0e0; font-size: 13px; padding: 8px; }
QComboBox { background: #16213e; border: 1px solid #444; border-radius: 6px;
            padding: 6px 10px; color: #e0e0e0; }
QLabel#desc { color: #8b949e; font-size: 12px; margin: 4px 0; }
QPushButton { background: #7c83fd; color: white; border: none; border-radius: 6px;
              padding: 8px 18px; font-weight: bold; font-size: 13px; }
QPushButton:hover { background: #9499ff; }
QPushButton#secondary { background: #2d2d4e; }
"""


class TemplatesDialog(QDialog):
    template_selected = Signal(str, str, str)   # system_prompt, starter_text, template_name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📋 Chat Templates")
        self.setMinimumSize(800, 560)
        self.setStyleSheet(STYLE)
        self._templates = get_all_templates()
        self._filtered = list(self._templates)
        self._build_ui()
        self._populate()

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(16, 16, 16, 16)
        main.setSpacing(10)

        hdr = QHBoxLayout()
        title = QLabel("📋 Chat Templates")
        title.setStyleSheet("font-size: 17px; font-weight: bold; color: #7c83fd;")
        hdr.addWidget(title)
        hdr.addStretch()

        self.cat_combo = QComboBox()
        self.cat_combo.addItem("All Categories")
        for c in get_categories():
            self.cat_combo.addItem(c)
        self.cat_combo.currentTextChanged.connect(self._filter)
        hdr.addWidget(self.cat_combo)
        main.addLayout(hdr)

        sub = QLabel("Start a new chat with a pre-configured system prompt and opening message.")
        sub.setObjectName("desc")
        main.addWidget(sub)

        splitter = QSplitter(Qt.Horizontal)

        # Left: template list
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._on_select)
        self.list_widget.itemDoubleClicked.connect(self._use)
        splitter.addWidget(self.list_widget)

        # Right: preview
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        rl.setSpacing(6)

        self.name_lbl = QLabel("")
        self.name_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #e0e0e0;")
        rl.addWidget(self.name_lbl)

        self.desc_lbl = QLabel("")
        self.desc_lbl.setObjectName("desc")
        rl.addWidget(self.desc_lbl)

        rl.addWidget(QLabel("System Prompt:"))
        self.sys_view = QTextEdit()
        self.sys_view.setReadOnly(True)
        self.sys_view.setMaximumHeight(140)
        rl.addWidget(self.sys_view)

        rl.addWidget(QLabel("Starter Message:"))
        self.starter_view = QTextEdit()
        self.starter_view.setReadOnly(True)
        self.starter_view.setMaximumHeight(80)
        rl.addWidget(self.starter_view)
        rl.addStretch()

        splitter.addWidget(right)
        splitter.setSizes([280, 500])
        main.addWidget(splitter, 1)

        btn_row = QHBoxLayout()
        self.btn_use = QPushButton("🚀 Start with This Template")
        self.btn_use.clicked.connect(self._use)
        btn_row.addWidget(self.btn_use)
        btn_row.addStretch()
        close = QPushButton("Cancel")
        close.setObjectName("secondary")
        close.clicked.connect(self.reject)
        btn_row.addWidget(close)
        main.addLayout(btn_row)

    def _populate(self):
        self.list_widget.clear()
        for t in self._filtered:
            icon = t.get("icon", "📋")
            item = QListWidgetItem(f"{icon}  {t['name']}\n   {t.get('description','')}")
            item.setData(Qt.UserRole, t["id"])
            self.list_widget.addItem(item)
        if self._filtered:
            self.list_widget.setCurrentRow(0)

    def _filter(self, cat: str):
        if cat == "All Categories":
            self._filtered = list(self._templates)
        else:
            self._filtered = [t for t in self._templates if t.get("category") == cat]
        self._populate()

    def _on_select(self, row: int):
        if 0 <= row < len(self._filtered):
            t = self._filtered[row]
            self.name_lbl.setText(f"{t.get('icon','')}  {t['name']}")
            self.desc_lbl.setText(t.get("description", ""))
            self.sys_view.setPlainText(t.get("system_prompt", ""))
            self.starter_view.setPlainText(t.get("starter", ""))

    def _use(self, *_):
        row = self.list_widget.currentRow()
        if 0 <= row < len(self._filtered):
            t = self._filtered[row]
            self.template_selected.emit(
                t.get("system_prompt", ""),
                t.get("starter", ""),
                t.get("name", "")
            )
            self.accept()
