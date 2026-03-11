"""
Prompt Library Dialog
Browse, search, manage, and insert prompts from the library.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QTextEdit, QComboBox, QSplitter,
    QWidget, QFrame, QMessageBox, QInputDialog, QDialogButtonBox, QFileDialog,
)
from PySide6.QtGui import QFont

from utils import prompt_library as lib

logger = logging.getLogger(__name__)


class AddPromptDialog(QDialog):
    def __init__(self, parent=None, initial_text: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Save Prompt")
        self.setMinimumSize(520, 400)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit()
        layout.addWidget(self.name_edit)

        layout.addWidget(QLabel("Category:"))
        self.cat_combo = QComboBox()
        self.cat_combo.setEditable(True)
        cats = lib.get_categories() or ["General", "Coding", "Writing", "Creative", "Education"]
        self.cat_combo.addItems(cats)
        layout.addWidget(self.cat_combo)

        layout.addWidget(QLabel("Description (optional):"))
        self.desc_edit = QLineEdit()
        layout.addWidget(self.desc_edit)

        meta_row = QHBoxLayout()
        self.app_edit = QLineEdit(); self.app_edit.setPlaceholderText("App name")
        self.project_edit = QLineEdit(); self.project_edit.setPlaceholderText("Project")
        meta_row.addWidget(self.app_edit)
        meta_row.addWidget(self.project_edit)
        layout.addLayout(meta_row)

        meta_row2 = QHBoxLayout()
        self.lang_edit = QLineEdit(); self.lang_edit.setPlaceholderText("Programming language")
        self.framework_edit = QLineEdit(); self.framework_edit.setPlaceholderText("Framework (optional)")
        meta_row2.addWidget(self.lang_edit)
        meta_row2.addWidget(self.framework_edit)
        layout.addLayout(meta_row2)

        meta_row3 = QHBoxLayout()
        self.version_edit = QLineEdit(); self.version_edit.setPlaceholderText("Prompt version (e.g. v1)")
        self.tags_edit = QLineEdit(); self.tags_edit.setPlaceholderText("Tags (comma-separated)")
        meta_row3.addWidget(self.version_edit)
        meta_row3.addWidget(self.tags_edit)
        layout.addLayout(meta_row3)

        layout.addWidget(QLabel("Prompt Text:"))
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(initial_text)
        self.text_edit.setMinimumHeight(140)
        layout.addWidget(self.text_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Error", "Name cannot be empty.")
            return
        if not self.text_edit.toPlainText().strip():
            QMessageBox.warning(self, "Error", "Prompt text cannot be empty.")
            return
        self.accept()

    def get_data(self):
        tags = [t.strip() for t in self.tags_edit.text().split(",") if t.strip()]
        return {
            "name": self.name_edit.text().strip(),
            "category": self.cat_combo.currentText().strip() or "General",
            "description": self.desc_edit.text().strip(),
            "text": self.text_edit.toPlainText().strip(),
            "app_name": self.app_edit.text().strip(),
            "project_name": self.project_edit.text().strip(),
            "programming_language": self.lang_edit.text().strip(),
            "framework": self.framework_edit.text().strip(),
            "prompt_version": self.version_edit.text().strip() or "v1",
            "tags": tags,
        }


DIALOG_STYLE = """
QDialog, QWidget { background: #1a1a2e; color: #e0e0e0; }
QListWidget { background: #16213e; border: 1px solid #333; border-radius: 6px; }
QListWidget::item { padding: 8px 10px; border-bottom: 1px solid #222; }
QListWidget::item:selected { background: #7c83fd33; color: #7c83fd; border-left: 3px solid #7c83fd; }
QListWidget::item:hover { background: #ffffff0a; }
QLineEdit, QComboBox { background: #16213e; border: 1px solid #444; border-radius: 6px; 
                        padding: 6px 10px; color: #e0e0e0; }
QLineEdit:focus, QComboBox:focus { border-color: #7c83fd; }
QTextEdit { background: #16213e; border: 1px solid #444; border-radius: 6px;
            color: #e0e0e0; font-family: 'Consolas', monospace; font-size: 13px; }
QPushButton { background: #7c83fd; color: white; border: none; border-radius: 6px;
              padding: 7px 16px; font-weight: bold; }
QPushButton:hover { background: #9499ff; }
QPushButton:pressed { background: #5a61e0; }
QPushButton#danger { background: #e94560; }
QPushButton#danger:hover { background: #ff6b80; }
QPushButton#secondary { background: #2d2d4e; }
QPushButton#secondary:hover { background: #3d3d6e; }
QLabel { color: #c0c0e0; }
QLabel#header { font-size: 16px; font-weight: bold; color: #7c83fd; }
QLabel#category-header { font-size: 11px; font-weight: bold; color: #888; }
"""


class PromptLibraryDialog(QDialog):
    """
    Full-featured prompt library browser.
    Emits prompt_selected(text) when user clicks 'Use Prompt'.
    """
    prompt_selected = Signal(str)

    def __init__(self, parent=None, current_input: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Prompt Library")
        self.setMinimumSize(860, 580)
        self.setStyleSheet(DIALOG_STYLE)
        self._current_input = current_input
        self._all_prompts = []
        self._selected_id: Optional[str] = None

        lib.initialize_defaults()
        self._build_ui()
        self._load_prompts()

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setSpacing(0)
        main.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QWidget()
        header.setStyleSheet("background: #0f3460; padding: 12px;")
        hlay = QHBoxLayout(header)
        title = QLabel("📚 Prompt Library")
        title.setObjectName("header")
        hlay.addWidget(title)
        hlay.addStretch()
        btn_new = QPushButton("+ New Prompt")
        btn_new.clicked.connect(self._new_prompt)
        hlay.addWidget(btn_new)
        btn_save = QPushButton("💾 Save Input")
        btn_save.setObjectName("secondary")
        btn_save.clicked.connect(self._save_current_input)
        if not self._current_input:
            btn_save.setEnabled(False)
        hlay.addWidget(btn_save)

        btn_export = QPushButton("⬇ Export")
        btn_export.setObjectName("secondary")
        btn_export.clicked.connect(self._export_prompts)
        hlay.addWidget(btn_export)

        btn_import = QPushButton("⬆ Import")
        btn_import.setObjectName("secondary")
        btn_import.clicked.connect(self._import_prompts)
        hlay.addWidget(btn_import)

        main.addWidget(header)

        # Body
        body = QWidget()
        body.setContentsMargins(12, 12, 12, 12)
        body_layout = QVBoxLayout(body)

        # Search bar
        search_row = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍  Search prompts...")
        self.search_box.textChanged.connect(self._on_search)
        search_row.addWidget(self.search_box)
        self.cat_filter = QComboBox()
        self.cat_filter.setMinimumWidth(150)
        self.cat_filter.addItem("All Categories")
        self.cat_filter.currentTextChanged.connect(self._on_search)
        search_row.addWidget(self.cat_filter)

        self.app_filter = QComboBox()
        self.app_filter.setMinimumWidth(140)
        self.app_filter.addItem("All Apps")
        self.app_filter.currentTextChanged.connect(self._on_search)
        search_row.addWidget(self.app_filter)

        self.lang_filter = QComboBox()
        self.lang_filter.setMinimumWidth(140)
        self.lang_filter.addItem("All Languages")
        self.lang_filter.currentTextChanged.connect(self._on_search)
        search_row.addWidget(self.lang_filter)

        self.framework_filter = QComboBox()
        self.framework_filter.setMinimumWidth(140)
        self.framework_filter.addItem("All Frameworks")
        self.framework_filter.currentTextChanged.connect(self._on_search)
        search_row.addWidget(self.framework_filter)
        body_layout.addLayout(search_row)

        # Splitter: list | detail
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)

        # Left: prompt list
        self.prompt_list = QListWidget()
        self.prompt_list.setMinimumWidth(260)
        self.prompt_list.currentItemChanged.connect(self._on_select)
        splitter.addWidget(self.prompt_list)

        # Right: detail panel
        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(12, 0, 0, 0)

        self.detail_name = QLabel("Select a prompt")
        self.detail_name.setStyleSheet("font-size: 15px; font-weight: bold; color: #e0e0e0;")
        detail_layout.addWidget(self.detail_name)

        self.detail_cat = QLabel("")
        self.detail_cat.setStyleSheet("color: #7c83fd; font-size: 12px;")
        detail_layout.addWidget(self.detail_cat)

        self.detail_desc = QLabel("")
        self.detail_desc.setStyleSheet("color: #888; font-size: 12px; margin-bottom: 8px;")
        self.detail_desc.setWordWrap(True)
        detail_layout.addWidget(self.detail_desc)

        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setMinimumHeight(180)
        detail_layout.addWidget(self.detail_text)

        # Action buttons
        actions = QHBoxLayout()
        self.btn_use = QPushButton("▶ Use Prompt")
        self.btn_use.setEnabled(False)
        self.btn_use.clicked.connect(self._use_prompt)
        actions.addWidget(self.btn_use)

        self.btn_edit = QPushButton("✏ Edit")
        self.btn_edit.setObjectName("secondary")
        self.btn_edit.setEnabled(False)
        self.btn_edit.clicked.connect(self._edit_prompt)
        actions.addWidget(self.btn_edit)

        self.btn_delete = QPushButton("🗑 Delete")
        self.btn_delete.setObjectName("danger")
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._delete_prompt)
        actions.addWidget(self.btn_delete)

        detail_layout.addLayout(actions)
        splitter.addWidget(detail)
        splitter.setSizes([300, 560])
        body_layout.addWidget(splitter)
        main.addWidget(body)

    def _load_prompts(self):
        self._all_prompts = lib.get_all_prompts()
        cats = lib.get_categories()
        self.cat_filter.clear()
        self.cat_filter.addItem("All Categories")
        self.cat_filter.addItems(cats)

        self.app_filter.clear()
        self.app_filter.addItem("All Apps")
        self.app_filter.addItems(lib.get_unique_values("app_name"))

        self.lang_filter.clear()
        self.lang_filter.addItem("All Languages")
        self.lang_filter.addItems(lib.get_unique_values("programming_language"))

        self.framework_filter.clear()
        self.framework_filter.addItem("All Frameworks")
        self.framework_filter.addItems(lib.get_unique_values("framework"))

        self._display_prompts(self._all_prompts)

    def _display_prompts(self, prompts):
        self.prompt_list.clear()
        for p in prompts:
            item = QListWidgetItem(f"{p.get('name', 'Untitled')}")
            item.setData(Qt.UserRole, p["id"])
            tooltip = (f"Category: {p.get('category', '')} | App: {p.get('app_name', '')} | Lang: {p.get('programming_language', '')}\n"                       f"{p.get('description', '')}")
            item.setToolTip(tooltip)
            self.prompt_list.addItem(item)

    def _on_search(self):
        query = self.search_box.text().strip()
        cat = self.cat_filter.currentText()
        app = self.app_filter.currentText()
        lang = self.lang_filter.currentText()
        fw = self.framework_filter.currentText()
        if query:
            prompts = lib.search_prompts(query)
        else:
            prompts = self._all_prompts
        if cat and cat != "All Categories":
            prompts = [p for p in prompts if p.get("category") == cat]
        if app and app != "All Apps":
            prompts = [p for p in prompts if p.get("app_name", "") == app]
        if lang and lang != "All Languages":
            prompts = [p for p in prompts if p.get("programming_language", "") == lang]
        if fw and fw != "All Frameworks":
            prompts = [p for p in prompts if p.get("framework", "") == fw]
        self._display_prompts(prompts)

    def _on_select(self, current: QListWidgetItem, _):
        if not current:
            self._selected_id = None
            self.btn_use.setEnabled(False)
            self.btn_edit.setEnabled(False)
            self.btn_delete.setEnabled(False)
            return
        pid = current.data(Qt.UserRole)
        self._selected_id = pid
        prompt = next((p for p in self._all_prompts if p["id"] == pid), None)
        if prompt:
            self.detail_name.setText(prompt.get("name", ""))
            self.detail_cat.setText(f"📁 {prompt.get('category', 'General')}")
            meta = f"App: {prompt.get('app_name','')} · Project: {prompt.get('project_name','')} · Lang: {prompt.get('programming_language','')} · FW: {prompt.get('framework','')} · Ver: {prompt.get('prompt_version','v1')}"
            self.detail_desc.setText((prompt.get("description", "") + "\n" + meta).strip())
            self.detail_text.setPlainText(prompt.get("text", ""))
            self.btn_use.setEnabled(True)
            self.btn_edit.setEnabled(True)
            self.btn_delete.setEnabled(True)

    def _use_prompt(self):
        if not self._selected_id:
            return
        prompt = next((p for p in self._all_prompts if p["id"] == self._selected_id), None)
        if prompt:
            lib.increment_use_count(self._selected_id)
            self.prompt_selected.emit(prompt["text"])
            self.accept()

    def _new_prompt(self):
        dlg = AddPromptDialog(self)
        if dlg.exec():
            data = dlg.get_data()
            lib.add_prompt(**data)
            self._load_prompts()

    def _save_current_input(self):
        dlg = AddPromptDialog(self, self._current_input)
        if dlg.exec():
            data = dlg.get_data()
            lib.add_prompt(**data)
            self._load_prompts()

    def _edit_prompt(self):
        if not self._selected_id:
            return
        prompt = next((p for p in self._all_prompts if p["id"] == self._selected_id), None)
        if not prompt:
            return
        dlg = AddPromptDialog(self, prompt.get("text", ""))
        dlg.name_edit.setText(prompt.get("name", ""))
        dlg.desc_edit.setText(prompt.get("description", ""))
        dlg.app_edit.setText(prompt.get("app_name", ""))
        dlg.project_edit.setText(prompt.get("project_name", ""))
        dlg.lang_edit.setText(prompt.get("programming_language", ""))
        dlg.framework_edit.setText(prompt.get("framework", ""))
        dlg.version_edit.setText(prompt.get("prompt_version", "v1"))
        dlg.tags_edit.setText(", ".join(prompt.get("tags", [])))
        idx = dlg.cat_combo.findText(prompt.get("category", ""))
        if idx >= 0:
            dlg.cat_combo.setCurrentIndex(idx)
        if dlg.exec():
            data = dlg.get_data()
            lib.update_prompt(self._selected_id, **data)
            self._load_prompts()

    def _export_prompts(self):
        fmt_item, ok = QInputDialog.getItem(
            self, "Export Prompt Library", "Format:", ["JSON", "Markdown"], 0, False
        )
        if not ok:
            return

        ext = "json" if fmt_item == "JSON" else "md"
        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Prompt Library",
            f"prompt_library.{ext}",
            "JSON (*.json);;Markdown (*.md)",
        )
        if not out_path:
            return

        fmt = "json" if fmt_item == "JSON" else "markdown"
        try:
            lib.export_prompts(Path(out_path), fmt)
            QMessageBox.information(self, "Export", f"Exported prompt library to:\n{out_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", str(e))

    def _import_prompts(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Prompts", "", "JSON (*.json)")
        if not path:
            return
        try:
            n = lib.import_prompts(Path(path))
            self._load_prompts()
            QMessageBox.information(self, "Import", f"Imported {n} prompts.")
        except Exception as e:
            QMessageBox.critical(self, "Import Failed", str(e))

    def _delete_prompt(self):
        if not self._selected_id:
            return
        reply = QMessageBox.question(self, "Delete Prompt", "Delete this prompt permanently?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            lib.delete_prompt(self._selected_id)
            self._selected_id = None
            self._load_prompts()
            self.detail_name.setText("Select a prompt")
            self.detail_cat.setText("")
            self.detail_desc.setText("")
            self.detail_text.clear()
            self.btn_use.setEnabled(False)
            self.btn_edit.setEnabled(False)
            self.btn_delete.setEnabled(False)
