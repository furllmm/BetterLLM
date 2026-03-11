"""
Universal Chat Import Dialog
Supports: ChatGPT, Claude.ai, Gemini, Perplexity, Copilot, BetterLLM JSONL
"""
from __future__ import annotations

import logging
from typing import List, Optional

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QProgressBar, QTextEdit, QSplitter, QMessageBox,
    QFileDialog, QWidget, QApplication, QFrame, QComboBox,
)

from utils.chat_importer import ChatImporter, ImportedChat
from utils.paths import get_chats_dir

logger = logging.getLogger(__name__)

STYLE = """
QDialog { background: #0d1117; color: #e6edf3; font-family: 'Segoe UI', sans-serif; }
QWidget { background: #0d1117; color: #e6edf3; }
QLabel { color: #e6edf3; }
QLabel#header { font-size: 16px; font-weight: bold; color: #7c83fd; }
QLabel#sub { font-size: 12px; color: #8b949e; }
QLabel#source_badge {
    background: #1c2952; color: #7c83fd; border: 1px solid #7c83fd44;
    border-radius: 4px; padding: 2px 10px; font-size: 12px; font-weight: bold;
}
QListWidget {
    background: #161b22; border: 1px solid #30363d; border-radius: 8px;
    color: #e6edf3; font-size: 13px;
}
QListWidget::item { padding: 8px 12px; border-bottom: 1px solid #1c2128; }
QListWidget::item:selected { background: #7c83fd22; color: #7c83fd; border-left: 3px solid #7c83fd; }
QListWidget::item:hover { background: #1c2128; }
QTextEdit {
    background: #161b22; border: 1px solid #30363d; border-radius: 8px;
    color: #e6edf3; font-size: 13px; padding: 8px;
}
QPushButton {
    background: #7c83fd; color: white; border: none; border-radius: 6px;
    padding: 8px 18px; font-weight: bold; font-size: 13px;
}
QPushButton:hover { background: #9499ff; }
QPushButton:disabled { background: #30363d; color: #8b949e; }
QPushButton#secondary { background: #1c2128; border: 1px solid #30363d; color: #e6edf3; }
QPushButton#secondary:hover { background: #30363d; }
QProgressBar { background: #1c2128; border: none; border-radius: 4px; height: 6px; }
QProgressBar::chunk { background: #7c83fd; border-radius: 4px; }
QComboBox {
    background: #1c2128; border: 1px solid #30363d; border-radius: 6px;
    color: #e6edf3; padding: 5px 10px; font-size: 12px;
}
QSplitter::handle { background: #30363d; }
"""

SOURCE_ICONS = {
    "ChatGPT": "🤖",
    "Claude.ai": "🧠",
    "Gemini": "✨",
    "Perplexity": "🔍",
    "Copilot": "🪁",
    "BetterLLM": "💙",
    "Unknown": "❓",
    "Error": "❌",
}


class ImportWorker(QThread):
    finished = Signal(str, list)
    error = Signal(str)

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            source, chats = ChatImporter.detect_and_parse(self.file_path)
            self.finished.emit(source, chats)
        except Exception as e:
            self.error.emit(str(e))


class ImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📥 Universal Chat Import")
        self.resize(920, 620)
        self.setStyleSheet(STYLE)

        self.source: str = "Unknown"
        self.all_chats: List[ImportedChat] = []
        self._worker: Optional[ImportWorker] = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        # ── Header ───────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        title = QLabel("📥 Import Chats")
        title.setObjectName("header")
        hdr.addWidget(title)
        hdr.addStretch()

        # Source badge
        self.source_badge = QLabel("No file loaded")
        self.source_badge.setObjectName("source_badge")
        self.source_badge.setVisible(False)
        hdr.addWidget(self.source_badge)
        layout.addLayout(hdr)

        sub = QLabel(
            "Import conversations from ChatGPT, Claude.ai, Gemini, Perplexity, Copilot or BetterLLM exports"
        )
        sub.setObjectName("sub")
        layout.addWidget(sub)

        # ── Platform guide ───────────────────────────────────────────────────
        guide = QLabel(
            "  🤖 ChatGPT: Settings → Export → conversations.json (ZIP)   "
            "🧠 Claude: Settings → Export Data (ZIP)   "
            "✨ Gemini: Google Takeout → include Gemini (ZIP)   "
            "🔍 Perplexity: Settings → Export (JSON)"
        )
        guide.setStyleSheet(
            "background: #161b22; border: 1px solid #30363d; border-radius: 6px; "
            "padding: 6px 10px; color: #8b949e; font-size: 11px;"
        )
        guide.setWordWrap(True)
        layout.addWidget(guide)

        # ── File selector ────────────────────────────────────────────────────
        file_row = QHBoxLayout()
        self.btn_select_file = QPushButton("📂  Select File…")
        self.btn_select_file.setFixedHeight(40)
        file_row.addWidget(self.btn_select_file)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(6)
        layout.addWidget(self.progress_bar)

        self.status_lbl = QLabel("Select a ZIP or JSON file to begin")
        self.status_lbl.setObjectName("sub")
        file_row.addWidget(self.status_lbl, 1)
        layout.addLayout(file_row)

        # ── Main splitter ─────────────────────────────────────────────────────
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setVisible(False)

        # Left: chat list
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(6)

        list_hdr = QHBoxLayout()
        list_hdr.addWidget(QLabel("Conversations:"))
        list_hdr.addStretch()
        self.count_lbl = QLabel("")
        self.count_lbl.setObjectName("sub")
        list_hdr.addWidget(self.count_lbl)
        ll.addLayout(list_hdr)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.MultiSelection)
        ll.addWidget(self.list_widget, 1)

        btn_row = QHBoxLayout()
        self.btn_select_all = QPushButton("Select All")
        self.btn_select_all.setObjectName("secondary")
        self.btn_deselect_all = QPushButton("Deselect All")
        self.btn_deselect_all.setObjectName("secondary")
        btn_row.addWidget(self.btn_select_all)
        btn_row.addWidget(self.btn_deselect_all)
        ll.addLayout(btn_row)
        self.splitter.addWidget(left)

        # Right: preview
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        rl.addWidget(QLabel("Preview:"))
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        rl.addWidget(self.preview_text, 1)
        self.splitter.addWidget(right)
        self.splitter.setSizes([340, 560])
        layout.addWidget(self.splitter, 1)

        # ── Footer ────────────────────────────────────────────────────────────
        footer = QHBoxLayout()
        self.stats_label = QLabel("")
        self.stats_label.setObjectName("sub")
        footer.addWidget(self.stats_label)
        footer.addStretch()
        self.btn_import = QPushButton("⬇  Import Selected")
        self.btn_import.setEnabled(False)
        self.btn_import.setFixedHeight(40)
        footer.addWidget(self.btn_import)
        btn_close = QPushButton("Close")
        btn_close.setObjectName("secondary")
        btn_close.clicked.connect(self.close)
        footer.addWidget(btn_close)
        layout.addLayout(footer)

    def _connect_signals(self):
        self.btn_select_file.clicked.connect(self.select_file)
        self.btn_select_all.clicked.connect(self._select_all)
        self.btn_deselect_all.clicked.connect(self._deselect_all)
        self.btn_import.clicked.connect(self.start_import)
        self.list_widget.itemClicked.connect(self._preview_selected)
        self.list_widget.itemSelectionChanged.connect(self._update_stats)

    def select_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Export File", "",
            "Export Files (*.zip *.json *.jsonl);;ZIP Archives (*.zip);;JSON Files (*.json *.jsonl)"
        )
        if path:
            self._load_file(path)

    def _load_file(self, path: str):
        import os
        fname = os.path.basename(path)
        self.status_lbl.setText(f"Parsing {fname}…")
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)
        self.btn_select_file.setEnabled(False)
        self.source_badge.setVisible(False)
        self.splitter.setVisible(False)

        self._worker = ImportWorker(path)
        self._worker.finished.connect(self._on_parsed)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_parsed(self, source: str, chats: List[ImportedChat]):
        self.progress_bar.setVisible(False)
        self.btn_select_file.setEnabled(True)
        self.source = source
        self.all_chats = chats

        icon = SOURCE_ICONS.get(source, "❓")
        self.source_badge.setText(f"{icon} {source}")
        self.source_badge.setVisible(True)

        if not chats:
            self.status_lbl.setText(
                f"No conversations found in {source} export. "
                "Make sure you selected the correct file format."
            )
            return

        self.status_lbl.setText(f"Found {len(chats)} conversations from {source}")
        self.list_widget.clear()
        for chat in chats:
            n_msgs = len(chat.messages)
            item = QListWidgetItem(f"{icon}  {chat.title}  ({n_msgs} messages)")
            item.setData(Qt.UserRole, chat)
            self.list_widget.addItem(item)

        self.splitter.setVisible(True)
        self.btn_import.setEnabled(True)
        self._update_stats()

    def _on_error(self, err: str):
        self.progress_bar.setVisible(False)
        self.btn_select_file.setEnabled(True)
        QMessageBox.critical(self, "Import Error", f"Failed to parse file:\n\n{err}")

    def _select_all(self):
        self.list_widget.selectAll()

    def _deselect_all(self):
        self.list_widget.clearSelection()

    def _update_stats(self):
        sel = len(self.list_widget.selectedItems())
        total = len(self.all_chats)
        self.count_lbl.setText(f"{total} total")
        self.stats_label.setText(f"Selected: {sel} / {total}")

    def _preview_selected(self, item: QListWidgetItem):
        chat: ImportedChat = item.data(Qt.UserRole)
        self.preview_text.clear()
        for msg in chat.messages[:30]:  # limit preview
            if msg.role == "user":
                self.preview_text.append(
                    f"<p><b><span style='color:#7c83fd;'>👤 You:</span></b><br>{msg.content[:400]}</p>"
                )
            else:
                self.preview_text.append(
                    f"<p><b><span style='color:#3fb950;'>🤖 Assistant:</span></b><br>{msg.content[:400]}</p>"
                )
        if len(chat.messages) > 30:
            self.preview_text.append(
                f"<p style='color:#8b949e;'>… and {len(chat.messages)-30} more messages</p>"
            )

    def start_import(self):
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return

        self.progress_bar.setRange(0, len(selected_items))
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.btn_import.setEnabled(False)

        target_dir = get_chats_dir()
        # Use source name as subfolder
        subfolder = self.source.lower().replace(".", "_").replace(" ", "_")
        if subfolder in ("unknown", "error"):
            subfolder = "imported"

        import_count = 0
        for i, item in enumerate(selected_items):
            chat: ImportedChat = item.data(Qt.UserRole)
            path = ChatImporter.save_to_betterllm(chat, target_dir, subfolder=subfolder)
            if path:
                import_count += 1
            self.progress_bar.setValue(i + 1)
            QApplication.processEvents()

        self.progress_bar.setVisible(False)
        self.btn_import.setEnabled(True)
        QMessageBox.information(
            self, "Import Complete",
            f"✅ Successfully imported {import_count} of {len(selected_items)} conversations\n"
            f"Saved to: {subfolder}/"
        )
        self.accept()
