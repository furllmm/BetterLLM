from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import deque
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional, Dict

from PySide6.QtCore import QThread, QTimer, Signal, Qt, QSize
from PySide6.QtGui import (QTextCursor, QGuiApplication, QFont, QColor, QTextCharFormat,
                            QKeySequence, QShortcut, QIcon)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QPushButton, QTextEdit, QVBoxLayout, QWidget, QFrame, QSplitter,
    QListWidget, QListWidgetItem, QMessageBox, QFileDialog, QMenu,
    QTreeWidget, QTreeWidgetItem, QStatusBar, QProgressBar, QComboBox,
    QInputDialog, QDialog,
)

from core.chat_session import ChatSession
from core.model_manager import ModelManager
from core.resource_monitor import ResourceMonitor
from core.warm_loader import WarmLoader, WarmState
from core.lan_server import LANServer
from core.plugin_manager import PluginManager
from utils.config_loader import AppConfig
from utils.markdown_renderer import MarkdownRenderer
from utils import session_state as ss
from utils import tag_manager
from utils.chat_indexer import ChatIndexer
from utils.token_counter import estimate_messages_tokens, context_usage_percent, context_status
from .prompt_playground import PromptPlayground
from .prompt_library_dialog import PromptLibraryDialog
from .search_dialog import SearchDialog
from .generation_settings import GenerationSettingsDialog, PRESETS
from .tps_graph import TpsGraphWidget
from utils import assistant_profiles
from utils import bookmarks as bm_util
from utils import snapshots as snap_util
from utils import prompt_versions as pv_util
from .timeline_panel import TimelinePanel
from .suggestion_sidebar import SuggestionSidebar

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────
DARK = {
    "bg": "#0d1117",
    "surface": "#161b22",
    "surface2": "#1c2128",
    "sidebar": "#13191f",
    "border": "#30363d",
    "text": "#e6edf3",
    "text_dim": "#8b949e",
    "accent": "#7c83fd",
    "accent2": "#e94560",
    "user_msg": "#1c2952",
    "asst_msg": "#1b2a1b",
    "user_border": "#7c83fd",
    "asst_border": "#3fb950",
    "success": "#3fb950",
    "warning": "#d29922",
    "danger": "#f85149",
}

LIGHT = {
    "bg": "#ffffff",
    "surface": "#f6f8fa",
    "surface2": "#eaeef2",
    "sidebar": "#f1f3f5",
    "border": "#d0d7de",
    "text": "#1f2328",
    "text_dim": "#636c76",
    "accent": "#5965f8",
    "accent2": "#cf222e",
    "user_msg": "#dbeafe",
    "asst_msg": "#dcfce7",
    "user_border": "#5965f8",
    "asst_border": "#22863a",
    "success": "#22863a",
    "warning": "#9a6700",
    "danger": "#cf222e",
}


# ──────────────────────────────────────────────────────────────────────────────
# CHAT WORKER (batched streaming)
# ──────────────────────────────────────────────────────────────────────────────
class ChatWorker(QThread):
    batch_ready = Signal(str)       # buffered token batch
    finished = Signal(str, float)   # full_text, tps
    error_occurred = Signal(str)

    BATCH_MS = 30  # flush every 30 ms

    def __init__(self, session: ChatSession, query: str,
                 use_mem: bool, deep: bool,
                 image_path: Optional[str] = None,
                 gen_params: Optional[Dict] = None) -> None:
        super().__init__()
        self.session = session
        self.query = query
        self.use_memory = use_mem
        self.deep_mode = deep
        self.image_path = image_path
        self.gen_params = gen_params or {}
        self.full_response = ""
        self._buffer: List[str] = []
        self._last_flush = 0.0
        self._cancelled = False

    def run(self) -> None:
        try:
            t0 = time.time()
            token_count = 0
            self._last_flush = t0

            for token in self.session.send_message_stream(
                self.query, self.use_memory, self.deep_mode,
                self.image_path, self.gen_params
            ):
                if self._cancelled:
                    break
                self.full_response += token
                self._buffer.append(token)
                token_count += 1

                now = time.time()
                if (now - self._last_flush) * 1000 >= self.BATCH_MS:
                    self._flush()

            self._flush()  # flush remaining
            dur = time.time() - t0
            tps = token_count / dur if dur > 0 else 0
            self.finished.emit(self.full_response, tps)
        except Exception as e:
            logger.exception("ChatWorker error")
            self.error_occurred.emit(str(e))

    def _flush(self) -> None:
        if self._buffer:
            self.batch_ready.emit("".join(self._buffer))
            self._buffer.clear()
            self._last_flush = time.time()

    def cancel(self) -> None:
        self._cancelled = True


# ──────────────────────────────────────────────────────────────────────────────
# MAIN WINDOW
# ──────────────────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self, session: ChatSession, monitor: ResourceMonitor,
                 model_manager: ModelManager, config: AppConfig) -> None:
        super().__init__()
        self.setWindowTitle("BetterLLM")
        self.resize(1200, 800)

        self.session = session
        self.monitor = monitor
        self.model_manager = model_manager
        self.config = config
        self.chat_worker: Optional[ChatWorker] = None
        self.warm_loader = WarmLoader(self.model_manager, self._on_warm_state_changed)
        self.md_renderer = MarkdownRenderer()
        self.lan_server = LANServer(self.session)
        self.plugin_manager = PluginManager()
        self.plugin_manager.load_plugins()

        # State
        self._current_chat_path: Optional[str] = None
        self._gen_params: Dict = dict(PRESETS["Balanced"])
        self._tps_history: deque = deque(maxlen=20)
        self._attached_image_path: Optional[str] = None
        self._active_tag_filter: Optional[str] = None
        self._current_theme = "dark"
        self._active_profile: str = "Default"
        self._current_messages: List[Dict] = []  # track messages for bookmarking/editing
        self._regen_previous_response: Optional[str] = None
        self._regen_pending_compare: bool = False
        self._last_ctx_status: str = "ok"

        # Chat indexer
        self._indexer = ChatIndexer()
        self._indexer.start(on_indexed=lambda n: logger.info("Indexed %d chats", n))

        # Load session state
        self._state = ss.load_session()
        self._current_theme = self._state.get("theme", "dark")
        self._gen_params = {**self._gen_params, **self._state.get("generation_params", {})}
        self._active_profile = self._state.get("active_profile", "Default")

        self._setup_ui()
        self._connect_signals()
        self._apply_theme(self._current_theme)
        self._restore_session()

        # Timers
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_status)
        self._status_timer.start(1000)

        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start(10_000)   # every 10 s

        self.load_chat_history()
        self._update_status()

    # ── UI Setup ──────────────────────────────────────────────────────────────
    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        self.setAcceptDrops(True)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(1)

        # ── Sidebar ──────────────────────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(220)
        sidebar.setMaximumWidth(320)
        sb_lay = QVBoxLayout(sidebar)
        sb_lay.setContentsMargins(0, 0, 0, 0)
        sb_lay.setSpacing(0)

        # Sidebar header
        sb_header = QWidget()
        sb_header.setObjectName("sb_header")
        sb_header.setFixedHeight(52)
        sb_h_lay = QHBoxLayout(sb_header)
        sb_h_lay.setContentsMargins(12, 8, 12, 8)
        title_lbl = QLabel("BetterLLM")
        title_lbl.setObjectName("app_title")
        title_lbl.setFont(QFont("Segoe UI", 13, QFont.Bold))
        sb_h_lay.addWidget(title_lbl)
        sb_h_lay.addStretch()
        self.btn_theme = QPushButton("☀" if self._current_theme == "dark" else "🌙")
        self.btn_theme.setObjectName("icon_btn")
        self.btn_theme.setFixedSize(30, 30)
        self.btn_theme.setToolTip("Toggle theme")
        sb_h_lay.addWidget(self.btn_theme)
        sb_lay.addWidget(sb_header)

        # New chat + search
        actions_row = QWidget()
        actions_row.setContentsMargins(8, 6, 8, 6)
        ar_lay = QHBoxLayout(actions_row)
        ar_lay.setContentsMargins(0, 0, 0, 0)
        self.btn_new_chat = QPushButton("+ New Chat")
        self.btn_new_chat.setObjectName("primary_btn")
        ar_lay.addWidget(self.btn_new_chat)
        self.btn_search = QPushButton("🔍")
        self.btn_search.setObjectName("icon_btn")
        self.btn_search.setFixedSize(32, 32)
        self.btn_search.setToolTip("Global Search (Ctrl+F)")
        ar_lay.addWidget(self.btn_search)
        sb_lay.addWidget(actions_row)

        # Tag filter bar
        tag_row = QWidget()
        tag_row.setContentsMargins(8, 0, 8, 4)
        tr_lay = QHBoxLayout(tag_row)
        tr_lay.setContentsMargins(0, 0, 0, 0)
        self.tag_combo = QComboBox()
        self.tag_combo.setObjectName("tag_combo")
        self.tag_combo.addItem("All Chats")
        self.tag_combo.currentTextChanged.connect(self._on_tag_filter_change)
        tr_lay.addWidget(self.tag_combo)
        sb_lay.addWidget(tag_row)

        # History tree
        self.history_tree = QTreeWidget()
        self.history_tree.setObjectName("history_tree")
        self.history_tree.setHeaderHidden(True)
        self.history_tree.setIndentation(12)
        self.history_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.history_tree.customContextMenuRequested.connect(self._sidebar_context_menu)
        sb_lay.addWidget(self.history_tree, 1)

        # Sidebar bottom buttons
        sb_bottom = QWidget()
        sb_b_lay = QVBoxLayout(sb_bottom)
        sb_b_lay.setContentsMargins(8, 4, 8, 8)
        sb_b_lay.setSpacing(4)

        for text, attr, tooltip in [
            ("🗂 Model Browser", "btn_model_browser", "Browse and load models"),
            ("📥 Import Chats", "btn_import_chats", "Import chat history"),
            ("🎮 Playground", "btn_playground", "Prompt playground"),
            ("📚 Prompt Library", "btn_prompt_library", "Manage prompt library"),
            ("📄 Import Document", "btn_import_doc", "Import to knowledge base"),
            ("🎭 Profiles", "btn_profiles", "Assistant profiles"),
            ("📊 Analytics", "btn_analytics", "Chat analytics"),
            ("🔖 Bookmarks", "btn_bookmarks", "Bookmarked messages"),
            ("📋 Templates", "btn_templates", "Chat templates"),
            ("🗂 Workspaces", "btn_workspaces", "Project workspaces"),
            ("📸 Snapshots", "btn_snapshots", "Chat snapshots"),
            ("⏱ Benchmark", "btn_benchmark", "Model benchmark"),
        ]:
            btn = QPushButton(text)
            btn.setObjectName("sidebar_btn")
            btn.setToolTip(tooltip)
            setattr(self, attr, btn)
            sb_b_lay.addWidget(btn)

        sb_lay.addWidget(sb_bottom)
        self.splitter.addWidget(sidebar)

        # ── Main Chat Area ────────────────────────────────────────────────────
        chat_container = QWidget()
        chat_container.setObjectName("chat_container")
        chat_layout = QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        # Header bar
        self.header = QFrame()
        self.header.setObjectName("chat_header")
        self.header.setFixedHeight(48)
        h_lay = QHBoxLayout(self.header)
        h_lay.setContentsMargins(14, 6, 14, 6)
        h_lay.setSpacing(8)

        self.profile_label = QLabel("")
        self.profile_label.setObjectName("header_lbl")
        h_lay.addWidget(self.profile_label)

        self.active_model_label = QLabel("No model loaded")
        self.active_model_label.setObjectName("header_model_lbl")
        h_lay.addWidget(self.active_model_label)

        self.warm_status_label = QLabel("")
        self.warm_status_label.setObjectName("header_lbl")
        h_lay.addWidget(self.warm_status_label)

        h_lay.addStretch()

        self.lan_status_label = QLabel("")
        self.lan_status_label.setObjectName("header_lan")
        h_lay.addWidget(self.lan_status_label)

        for text, attr, tip in [
            ("⚙ Settings", "btn_gen_settings", "Generation settings"),
            ("📋 Export", "btn_export", "Export chat"),
            ("🔀 Fork", "btn_fork", "Fork conversation"),
            ("🔄 Regen", "btn_regen", "Regenerate last response (Ctrl+R)"),
            ("📝 Summarize", "btn_summarize", "Summarize conversation"),
            ("🗂 Timeline", "btn_timeline", "Toggle conversation timeline"),
            ("💡 Suggest", "btn_suggest", "Toggle AI suggestions"),
            ("⏹ Stop", "btn_stop", "Stop generation"),
        ]:
            btn = QPushButton(text)
            btn.setObjectName("header_btn")
            btn.setToolTip(tip)
            setattr(self, attr, btn)
            h_lay.addWidget(btn)
        self.btn_stop.setEnabled(False)
        chat_layout.addWidget(self.header)

        # Context bar (token usage)
        ctx_bar_widget = QWidget()
        ctx_bar_widget.setObjectName("ctx_bar_widget")
        ctx_bar_widget.setFixedHeight(24)
        ctx_lay = QHBoxLayout(ctx_bar_widget)
        ctx_lay.setContentsMargins(14, 2, 14, 2)
        ctx_lay.setSpacing(8)
        self.ctx_lbl = QLabel("Context: —")
        self.ctx_lbl.setObjectName("ctx_lbl")
        ctx_lay.addWidget(self.ctx_lbl)
        self.ctx_bar = QProgressBar()
        self.ctx_bar.setObjectName("ctx_bar")
        self.ctx_bar.setRange(0, 100)
        self.ctx_bar.setValue(0)
        self.ctx_bar.setFixedHeight(6)
        self.ctx_bar.setTextVisible(False)
        ctx_lay.addWidget(self.ctx_bar, 1)
        self.tps_lbl = QLabel("")
        self.tps_lbl.setObjectName("tps_lbl")
        ctx_lay.addWidget(self.tps_lbl)
        self.tps_graph = TpsGraphWidget(maxlen=30)
        self.tps_graph.setFixedWidth(100)
        self.tps_graph.setVisible(False)
        ctx_lay.addWidget(self.tps_graph)
        chat_layout.addWidget(ctx_bar_widget)

        # Chat view
        self.chat_history = QTextEdit()
        self.chat_history.setObjectName("chat_view")
        self.chat_history.setReadOnly(True)
        self.chat_history.setContextMenuPolicy(Qt.CustomContextMenu)
        self.chat_history.customContextMenuRequested.connect(self._chat_context_menu)
        chat_layout.addWidget(self.chat_history, 1)

        # Input area
        input_frame = QFrame()
        input_frame.setObjectName("input_frame")
        in_lay = QVBoxLayout(input_frame)
        in_lay.setContentsMargins(12, 8, 12, 12)
        in_lay.setSpacing(6)

        self.attachment_label = QLabel("")
        self.attachment_label.setObjectName("attachment_lbl")
        self.attachment_label.setVisible(False)
        in_lay.addWidget(self.attachment_label)

        msg_row = QHBoxLayout()
        msg_row.setSpacing(6)
        self.btn_upload = QPushButton("📷")
        self.btn_upload.setObjectName("icon_btn")
        self.btn_upload.setFixedSize(40, 40)
        self.btn_upload.setToolTip("Attach image")
        msg_row.addWidget(self.btn_upload)

        self.input_box = QLineEdit()
        self.input_box.setObjectName("input_box")
        self.input_box.setPlaceholderText("Type your message…  (Enter to send)")
        self.input_box.setMinimumHeight(40)
        msg_row.addWidget(self.input_box, 1)

        self.btn_prompt_lib_quick = QPushButton("📚")
        self.btn_prompt_lib_quick.setObjectName("icon_btn")
        self.btn_prompt_lib_quick.setFixedSize(40, 40)
        self.btn_prompt_lib_quick.setToolTip("Insert from Prompt Library")
        msg_row.addWidget(self.btn_prompt_lib_quick)

        self.btn_prompt_hist = QPushButton("🕓")
        self.btn_prompt_hist.setObjectName("icon_btn")
        self.btn_prompt_hist.setFixedSize(40, 40)
        self.btn_prompt_hist.setToolTip("Prompt History (Ctrl+H)")
        msg_row.addWidget(self.btn_prompt_hist)

        self.btn_send = QPushButton("Send ↵")
        self.btn_send.setObjectName("send_btn")
        self.btn_send.setMinimumHeight(40)
        self.btn_send.setMinimumWidth(90)
        msg_row.addWidget(self.btn_send)
        in_lay.addLayout(msg_row)

        opts_row = QHBoxLayout()
        opts_row.setSpacing(10)
        self.mem_checkbox = QCheckBox("Memory")
        self.deep_checkbox = QCheckBox("Deep Mode")
        self.kb_checkbox = QCheckBox("Knowledge Base")
        self.lan_checkbox = QCheckBox("LAN")
        self.mem_checkbox.setChecked(self._state.get("mem_checked", True))
        self.deep_checkbox.setChecked(self._state.get("deep_checked", False))
        self.kb_checkbox.setChecked(self._state.get("kb_checked", True))
        for cb in (self.mem_checkbox, self.deep_checkbox, self.kb_checkbox, self.lan_checkbox):
            opts_row.addWidget(cb)
        opts_row.addStretch()
        self.profile_badge = QPushButton(f"🎭 {self._active_profile}")
        self.profile_badge.setObjectName("icon_btn")
        self.profile_badge.setToolTip("Switch assistant profile")
        self.profile_badge.clicked.connect(self.open_profiles)
        opts_row.addWidget(self.profile_badge)
        self.preset_badge = QLabel(f"⚙ {self._state.get('active_preset','Balanced')}")
        self.preset_badge.setObjectName("preset_badge")
        opts_row.addWidget(self.preset_badge)
        in_lay.addLayout(opts_row)

        chat_layout.addWidget(input_frame)
        self.splitter.addWidget(chat_container)

        # Timeline panel (right side of chat)
        self.timeline_panel = TimelinePanel()
        self.timeline_panel.jump_to_message.connect(self._jump_to_timeline_message)
        self.splitter.addWidget(self.timeline_panel)

        # Suggestion sidebar (far right)
        self.suggestion_sidebar = SuggestionSidebar()
        self.suggestion_sidebar.suggestion_clicked.connect(self._on_suggestion_clicked)
        self.splitter.addWidget(self.suggestion_sidebar)

        self.splitter.setStretchFactor(1, 4)
        self.splitter.setSizes([240, 960, 0, 0])
        root.addWidget(self.splitter)

        # Status bar
        sb = self.statusBar()
        sb.setObjectName("status_bar")
        self.ram_sb = QLabel("RAM: —")
        self.gpu_sb = QLabel("")
        sb.addPermanentWidget(self.ram_sb)
        sb.addPermanentWidget(self.gpu_sb)

    # ── Signals ───────────────────────────────────────────────────────────────
    def _connect_signals(self) -> None:
        self.btn_send.clicked.connect(self.send_message)
        self.input_box.returnPressed.connect(self.send_message)
        self.input_box.textChanged.connect(self._on_typing)
        self.btn_upload.clicked.connect(self.upload_image)
        self.btn_model_browser.clicked.connect(self.open_model_browser)
        self.btn_import_chats.clicked.connect(self.open_import_dialog)
        self.btn_new_chat.clicked.connect(self.new_chat)
        self.btn_stop.clicked.connect(self.stop_generation)
        self.btn_theme.clicked.connect(self.toggle_theme)
        self.btn_fork.clicked.connect(self.fork_chat)
        self.btn_playground.clicked.connect(self.open_playground)
        self.btn_import_doc.clicked.connect(self.import_document)
        self.btn_prompt_library.clicked.connect(self.open_prompt_library)
        self.btn_prompt_lib_quick.clicked.connect(self.open_prompt_library)
        self.btn_prompt_hist.clicked.connect(self.open_prompt_versions)
        self.btn_gen_settings.clicked.connect(self.open_gen_settings)
        self.btn_export.clicked.connect(self.export_current_chat)
        self.btn_regen.clicked.connect(self.regenerate_response)
        self.btn_summarize.clicked.connect(self.summarize_chat)
        self.btn_profiles.clicked.connect(self.open_profiles)
        self.btn_analytics.clicked.connect(self.open_analytics)
        self.btn_bookmarks.clicked.connect(self.open_bookmarks)
        self.btn_templates.clicked.connect(self.open_templates)
        self.btn_workspaces.clicked.connect(self.open_workspaces)
        self.btn_snapshots.clicked.connect(self.open_snapshots)
        self.btn_benchmark.clicked.connect(self.open_benchmark)
        self.btn_timeline.clicked.connect(self.toggle_timeline)
        self.btn_suggest.clicked.connect(self.toggle_suggestions)
        self.lan_checkbox.toggled.connect(self.toggle_lan_mode)
        self.history_tree.itemClicked.connect(self.load_selected_chat)

        # Keyboard shortcuts
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self.open_search)
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self.new_chat)
        QShortcut(QKeySequence("Ctrl+E"), self).activated.connect(self.export_current_chat)
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(self.regenerate_response)
        QShortcut(QKeySequence("Ctrl+B"), self).activated.connect(self.open_bookmarks)
        QShortcut(QKeySequence("Ctrl+Shift+S"), self).activated.connect(self._quick_snapshot)
        QShortcut(QKeySequence("Ctrl+T"), self).activated.connect(self.open_templates)
        QShortcut(QKeySequence("Ctrl+H"), self).activated.connect(self.open_prompt_versions)

    # ── Theme ─────────────────────────────────────────────────────────────────
    def _apply_theme(self, theme: str) -> None:
        self._current_theme = theme
        c = DARK if theme == "dark" else LIGHT
        self.btn_theme.setText("☀" if theme == "dark" else "🌙")

        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background: {c['bg']}; color: {c['text']}; font-family: 'Segoe UI', sans-serif; }}
            QWidget#sidebar {{ background: {c['sidebar']}; border-right: 1px solid {c['border']}; }}
            QWidget#sb_header {{ background: {c['sidebar']}; border-bottom: 1px solid {c['border']}; }}
            QLabel#app_title {{ color: {c['accent']}; }}
            QPushButton#primary_btn {{ background: {c['accent']}; color: white; border: none; border-radius: 6px; padding: 7px 12px; font-weight: 600; }}
            QPushButton#primary_btn:hover {{ background: {c['accent']}cc; }}
            QPushButton#icon_btn {{ background: transparent; color: {c['text_dim']}; border: 1px solid {c['border']}; border-radius: 6px; font-size: 15px; }}
            QPushButton#icon_btn:hover {{ background: {c['surface2']}; color: {c['text']}; }}
            QPushButton#sidebar_btn {{ background: transparent; color: {c['text_dim']}; border: none; border-radius: 4px; padding: 6px 10px; text-align: left; }}
            QPushButton#sidebar_btn:hover {{ background: {c['surface2']}; color: {c['text']}; }}
            QWidget#chat_container {{ background: {c['bg']}; }}
            QFrame#chat_header {{ background: {c['surface']}; border-bottom: 1px solid {c['border']}; }}
            QLabel#header_lbl {{ color: {c['text_dim']}; font-size: 12px; }}
            QLabel#header_model_lbl {{ color: {c['accent']}; font-size: 12px; font-weight: bold; }}
            QLabel#header_lan {{ color: {c['success']}; font-size: 11px; }}
            QPushButton#header_btn {{ background: {c['surface2']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 5px; padding: 4px 10px; font-size: 12px; }}
            QPushButton#header_btn:hover {{ background: {c['accent']}33; border-color: {c['accent']}; }}
            QWidget#ctx_bar_widget {{ background: {c['surface']}; border-bottom: 1px solid {c['border']}; }}
            QLabel#ctx_lbl, QLabel#tps_lbl {{ color: {c['text_dim']}; font-size: 11px; }}
            QProgressBar#ctx_bar {{ background: {c['surface2']}; border: none; border-radius: 3px; }}
            QProgressBar#ctx_bar::chunk {{ background: {c['accent']}; border-radius: 3px; }}
            QTextEdit#chat_view {{ background: {c['bg']}; border: none; color: {c['text']}; font-size: 14px; padding: 8px; }}
            QFrame#input_frame {{ background: {c['surface']}; border-top: 1px solid {c['border']}; }}
            QLineEdit#input_box {{ background: {c['surface2']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 8px 12px; color: {c['text']}; font-size: 14px; }}
            QLineEdit#input_box:focus {{ border-color: {c['accent']}; }}
            QPushButton#send_btn {{ background: {c['accent']}; color: white; border: none; border-radius: 8px; padding: 8px 18px; font-weight: 700; font-size: 13px; }}
            QPushButton#send_btn:hover {{ background: {c['accent']}cc; }}
            QPushButton#send_btn:disabled {{ background: {c['border']}; color: {c['text_dim']}; }}
            QCheckBox {{ color: {c['text_dim']}; spacing: 6px; font-size: 12px; }}
            QCheckBox::indicator {{ width: 14px; height: 14px; border-radius: 3px; border: 1px solid {c['border']}; background: {c['surface2']}; }}
            QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; }}
            QLabel#preset_badge {{ color: {c['accent']}; font-size: 11px; }}
            QLabel#attachment_lbl {{ color: {c['warning']}; font-size: 12px; }}
            QTreeWidget#history_tree {{ background: {c['sidebar']}; border: none; color: {c['text']}; }}
            QTreeWidget#history_tree::item {{ padding: 5px 8px; border-radius: 4px; }}
            QTreeWidget#history_tree::item:selected {{ background: {c['accent']}22; color: {c['accent']}; }}
            QTreeWidget#history_tree::item:hover {{ background: {c['surface2']}; }}
            QComboBox#tag_combo {{ background: {c['surface2']}; border: 1px solid {c['border']}; border-radius: 4px; padding: 3px 8px; color: {c['text_dim']}; font-size: 11px; }}
            QStatusBar {{ background: {c['surface']}; border-top: 1px solid {c['border']}; color: {c['text_dim']}; font-size: 11px; }}
            QScrollBar:vertical {{ background: {c['surface']}; width: 8px; }}
            QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 4px; min-height: 20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)

        self.chat_history.document().setDefaultStyleSheet(f"""
            body {{
                font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
                font-size: 14px;
                color: {c['text']};
                line-height: 1.75;
                margin: 0;
                padding: 0;
                background: {c['bg']};
            }}

            /* ── Message rows ──────────────────────────────────── */
            .msg-row {{
                margin: 0;
                padding: 18px 28px 18px 28px;
                border-bottom: 1px solid {c['border']}22;
            }}
            .msg-row-user {{
                background: {c['bg']};
            }}
            .msg-row-asst {{
                background: {'#161b22' if theme == 'dark' else '#f6f8fa'};
            }}

            /* ── Avatar + name header ──────────────────────────── */
            .msg-header {{
                margin-bottom: 10px;
                display: block;
                user-select: none;
            }}
            .avatar-user {{
                display: inline-block;
                background: {'#3d4aff' if theme == 'dark' else '#5965f8'};
                color: white;
                font-size: 10px;
                font-weight: 800;
                border-radius: 50%;
                width: 28px;
                height: 28px;
                text-align: center;
                line-height: 28px;
                margin-right: 10px;
                vertical-align: middle;
                letter-spacing: 0.5px;
            }}
            .avatar-asst {{
                display: inline-block;
                background: {'#1a3a2a' if theme == 'dark' else '#d1fadf'};
                color: {'#3fb950' if theme == 'dark' else '#1a7f37'};
                font-size: 10px;
                font-weight: 800;
                border-radius: 50%;
                width: 28px;
                height: 28px;
                text-align: center;
                line-height: 28px;
                margin-right: 10px;
                vertical-align: middle;
                border: 1.5px solid {'#3fb950' if theme == 'dark' else '#1a7f37'};
            }}
            .role-user {{
                color: {'#7c83fd' if theme == 'dark' else '#5965f8'};
                font-weight: 700;
                font-size: 13px;
                vertical-align: middle;
                letter-spacing: 0.3px;
            }}
            .role-asst {{
                color: {'#3fb950' if theme == 'dark' else '#1a7f37'};
                font-weight: 700;
                font-size: 13px;
                vertical-align: middle;
                letter-spacing: 0.3px;
            }}
            .ts {{
                color: {c['text_dim']};
                font-size: 11px;
                margin-left: 12px;
                font-weight: 400;
                vertical-align: middle;
                opacity: 0.7;
            }}

            /* ── Message body ──────────────────────────────────── */
            .msg-body {{
                margin-left: 38px;
                color: {c['text']};
                line-height: 1.8;
                font-size: 14px;
            }}

            /* ── Paragraphs ─────────────────────────────────────── */
            p {{ margin: 0 0 12px 0; }}
            p:last-child {{ margin-bottom: 0; }}

            /* ── Headings ───────────────────────────────────────── */
            h1 {{
                font-size: 20px; font-weight: 700;
                color: {c['text']};
                margin: 20px 0 10px 0;
                padding-bottom: 6px;
                border-bottom: 2px solid {c['accent']}55;
            }}
            h2 {{
                font-size: 17px; font-weight: 700;
                color: {c['text']};
                margin: 16px 0 8px 0;
                padding-bottom: 4px;
                border-bottom: 1px solid {c['border']}66;
            }}
            h3 {{
                font-size: 15px; font-weight: 700;
                color: {c['text']};
                margin: 12px 0 6px 0;
            }}
            h4, h5, h6 {{
                font-size: 13px; font-weight: 600;
                color: {c['text_dim']};
                margin: 10px 0 4px 0;
            }}

            strong, b {{ font-weight: 700; color: {c['text']}; }}
            em, i {{ font-style: italic; color: {c['text_dim']}; }}

            /* ── Blockquote ─────────────────────────────────────── */
            blockquote {{
                border-left: 3px solid {c['accent']}88;
                margin: 12px 0;
                padding: 8px 16px;
                color: {c['text_dim']};
                font-style: italic;
                background: {c['surface2']}55;
                border-radius: 0 8px 8px 0;
            }}

            hr {{
                border: none;
                border-top: 1px solid {c['border']};
                margin: 16px 0;
            }}
            a {{
                color: {c['accent']};
                text-decoration: none;
            }}

            /* ── Tables ─────────────────────────────────────────── */
            table {{
                border-collapse: collapse;
                margin: 12px 0;
                width: 100%;
                font-size: 13px;
                border-radius: 8px;
                overflow: hidden;
            }}
            th {{
                background: {c['surface2']};
                border: 1px solid {c['border']};
                padding: 8px 14px;
                font-weight: 700;
                text-align: left;
                color: {c['text']};
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            td {{
                border: 1px solid {c['border']};
                padding: 7px 14px;
                color: {c['text']};
            }}
            tr:nth-child(even) td {{ background: {c['surface2']}44; }}
            tr:hover td {{ background: {c['surface2']}88; }}

            /* ── Inline code ────────────────────────────────────── */
            code {{
                background: {'#2d333b' if theme == 'dark' else '#eaeef2'};
                color: {'#ff7b72' if theme == 'dark' else '#cf222e'};
                padding: 2px 7px;
                border-radius: 5px;
                font-family: 'Consolas', 'JetBrains Mono', 'Courier New', monospace;
                font-size: 12.5px;
                border: 1px solid {c['border']}66;
            }}

            /* ── Code block header ───────────────────────────────── */
            .code-lang-header {{
                background: {'#1c2128' if theme == 'dark' else '#e8edf2'};
                border: 1px solid {c['border']};
                border-bottom: none;
                border-radius: 8px 8px 0 0;
                padding: 5px 14px;
                font-family: 'Consolas', monospace;
                font-size: 11px;
                color: {c['text_dim']};
                display: block;
                margin-top: 12px;
            }}

            /* ── Code blocks ─────────────────────────────────────── */
            pre {{
                background: {'#0d1117' if theme == 'dark' else '#f6f8fa'};
                color: {'#e6edf3' if theme == 'dark' else '#24292e'};
                padding: 16px 18px;
                border-radius: 0 0 8px 8px;
                font-family: 'Consolas', 'JetBrains Mono', 'Courier New', monospace;
                font-size: 13px;
                border: 1px solid {c['border']};
                border-top: none;
                margin: 0 0 12px 0;
                line-height: 1.55;
                overflow-x: auto;
                white-space: pre-wrap;
            }}
            pre code {{
                background: transparent;
                color: inherit;
                padding: 0;
                border: none;
                font-size: inherit;
            }}

            /* ── Token count ─────────────────────────────────────── */
            .tok-count {{
                color: {c['text_dim']};
                font-size: 10px;
                margin-top: 10px;
                display: block;
                opacity: 0.6;
            }}

            /* ── Date separator ──────────────────────────────────── */
            .date-sep {{
                color: {c['text_dim']};
                font-size: 11px;
                text-align: center;
                margin: 20px 0 10px 0;
                padding: 4px 0;
                opacity: 0.7;
            }}

            /* ── Summary block ───────────────────────────────────── */
            .summary-block {{
                background: {'#2d2a1a' if theme == 'dark' else '#fffbeb'};
                border-left: 4px solid {c['warning']};
                border-radius: 0 8px 8px 0;
                padding: 12px 18px;
                margin: 10px 0 16px 0;
                font-style: italic;
                color: {c['text_dim']};
                font-size: 13px;
            }}

            {self.md_renderer.get_css()}
        """)
        self.tps_graph.set_colors(c['accent'], c['surface2'])
        self.refresh_current_view()

    def toggle_theme(self) -> None:
        new = "light" if self._current_theme == "dark" else "dark"
        self._apply_theme(new)

    # ── Session Restore ───────────────────────────────────────────────────────
    def _restore_session(self) -> None:
        geom = self._state.get("window_geometry")
        if geom:
            try:
                self.restoreGeometry(bytes.fromhex(geom))
            except Exception:
                pass

        splitter_sizes = self._state.get("splitter_sizes")
        if isinstance(splitter_sizes, list) and len(splitter_sizes) == 4:
            try:
                self.splitter.setSizes([max(0, int(v)) for v in splitter_sizes])
            except Exception:
                splitter_sizes = None

        if not splitter_sizes:
            sw = self._state.get("sidebar_width", 240)
            total = self.splitter.width() or 1200
            self.splitter.setSizes([sw, max(400, total - sw), 0, 0])

        self.lan_checkbox.setChecked(bool(self._state.get("lan_checked", False)))
        self.timeline_panel.setVisible(bool(self._state.get("timeline_visible", False)))
        self.suggestion_sidebar.setVisible(bool(self._state.get("suggestions_visible", False)))
        draft = self._state.get("input_draft", "")
        if draft:
            self.input_box.setText(draft)

        last_chat = self._state.get("last_chat_path")
        if last_chat and os.path.exists(last_chat):
            self._load_chat_file(Path(last_chat))

            # Restore per-chat scroll position after render is complete.
            scroll_state = self._state.get("chat_scroll_positions", {})
            scroll_pos = scroll_state.get(last_chat, self._state.get("scroll_position", 0))
            sb = self.chat_history.verticalScrollBar()
            QTimer.singleShot(0, lambda: sb.setValue(max(0, min(int(scroll_pos), sb.maximum()))))

        # Restore previously active model in the background.
        active_model_topic = self._state.get("active_model_topic")
        if active_model_topic:
            self.model_manager.start_load_async(
                active_model_topic,
                on_complete=lambda _t: QTimer.singleShot(0, self._update_status),
                on_error=lambda _t, _e: logger.warning("Failed to restore model %s", active_model_topic),
            )

    def _save_session(self) -> None:
        self._state.update({
            "last_chat_path": self._current_chat_path,
            "theme": self._current_theme,
            "sidebar_width": self.splitter.sizes()[0],
            "splitter_sizes": self.splitter.sizes(),
            "mem_checked": self.mem_checkbox.isChecked(),
            "deep_checked": self.deep_checkbox.isChecked(),
            "kb_checked": self.kb_checkbox.isChecked(),
            "lan_checked": self.lan_checkbox.isChecked(),
            "window_geometry": bytes(self.saveGeometry()).hex(),
            "generation_params": self._gen_params,
            "active_preset": self._state.get("active_preset", "Balanced"),
            "active_profile": self._active_profile,
            "active_model_topic": self.model_manager.get_active_model_topic(),
            "scroll_position": self.chat_history.verticalScrollBar().value(),
        })

        scroll_map = self._state.get("chat_scroll_positions", {})
        if not isinstance(scroll_map, dict):
            scroll_map = {}
        if self._current_chat_path:
            scroll_map[self._current_chat_path] = self.chat_history.verticalScrollBar().value()

        # Keep map bounded and discard entries for files that no longer exist.
        existing = {k: v for k, v in scroll_map.items() if isinstance(k, str) and os.path.exists(k)}
        if len(existing) > 500:
            existing_items = list(existing.items())[-500:]
            existing = dict(existing_items)
        self._state["chat_scroll_positions"] = existing

        # Keep lightweight draft/input UI state.
        self._state["input_draft"] = self.input_box.text()
        self._state["timeline_visible"] = self.timeline_panel.isVisible()
        self._state["suggestions_visible"] = self.suggestion_sidebar.isVisible()

        ss.save_session(self._state)

    def _autosave(self) -> None:
        if self._current_chat_path:
            scroll_map = self._state.get("chat_scroll_positions", {})
            if not isinstance(scroll_map, dict):
                scroll_map = {}
            scroll_map[self._current_chat_path] = self.chat_history.verticalScrollBar().value()
            self._state["chat_scroll_positions"] = scroll_map
        self._save_session()

    # ── History Tree ──────────────────────────────────────────────────────────
    @staticmethod
    def _decode_filename(name: str) -> str:
        """Decode #Uxxxx sequences and clean up chat filename for display."""
        # Decode URL-like unicode escapes: #U0130 -> İ
        decoded = re.sub(r'#U([0-9a-fA-F]{4,6})',
                         lambda m: chr(int(m.group(1), 16)), name)
        # Remove timestamp suffix _20260310_212540 or similar
        decoded = re.sub(r'_\d{8}_\d{6}(?:_\d+)?$', '', decoded)
        # Replace underscores with spaces (but keep consecutive ones as-is)
        return decoded.replace("_", " ").strip()

    def load_chat_history(self) -> None:
        from utils.paths import get_chats_dir
        # Remember expanded state
        expanded = set()
        for i in range(self.history_tree.topLevelItemCount()):
            item = self.history_tree.topLevelItem(i)
            if item and item.isExpanded():
                expanded.add(item.text(0))

        self.history_tree.clear()
        chats_dir = get_chats_dir()
        if not chats_dir.exists():
            return

        # Refresh tag combo
        self.tag_combo.blockSignals(True)
        current_tag = self.tag_combo.currentText()
        self.tag_combo.clear()
        self.tag_combo.addItem("Tüm Sohbetler")
        for t in tag_manager.get_all_tags():
            self.tag_combo.addItem(t)
        idx = self.tag_combo.findText(current_tag)
        self.tag_combo.setCurrentIndex(max(0, idx))
        self.tag_combo.blockSignals(False)

        active_filter = self.tag_combo.currentText()
        tagged_paths = (set(tag_manager.get_chats_with_tag(active_filter))
                        if active_filter and active_filter not in ("Tüm Sohbetler", "All Chats")
                        else None)

        c = DARK if self._current_theme == "dark" else LIGHT

        for topic_dir in sorted(chats_dir.iterdir()):
            if not topic_dir.is_dir():
                continue
            if topic_dir.name.startswith("__"):
                continue
            icon = self.session._router.get_topic_icon(topic_dir.name)
            chat_files = list(topic_dir.glob("*.jsonl"))
            chat_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

            visible_files = [f for f in chat_files
                             if tagged_paths is None or str(f) in tagged_paths]
            if not visible_files:
                continue

            # Decode folder name too
            folder_display = self._decode_filename(topic_dir.name).upper()
            folder_item = QTreeWidgetItem(self.history_tree)
            folder_item.setText(0, f"{icon}  {folder_display}")
            folder_item.setFont(0, QFont("Segoe UI", 9, QFont.Bold))
            folder_item.setForeground(0, QColor(c["text_dim"]))
            folder_item.setData(0, Qt.UserRole + 1, "folder")  # mark as folder
            folder_item.setData(0, Qt.UserRole + 2, str(topic_dir))  # folder path

            for chat_file in visible_files:
                display_name = self._decode_filename(chat_file.stem)
                child = QTreeWidgetItem(folder_item)
                tags = tag_manager.get_tags(str(chat_file))
                tag_str = f"  [{', '.join(tags)}]" if tags else ""
                child.setText(0, f"  {display_name}{tag_str}")
                child.setData(0, Qt.UserRole, str(chat_file))
                if str(chat_file) == self._current_chat_path:
                    child.setForeground(0, QColor(c["accent"]))
                    child.setFont(0, QFont("Segoe UI", 9, QFont.Bold))

            # Restore expanded state or default expand
            folder_key = folder_item.text(0)
            folder_item.setExpanded(folder_key in expanded or len(expanded) == 0)

    def _on_tag_filter_change(self, _: str) -> None:
        self.load_chat_history()

    def _sidebar_context_menu(self, pos) -> None:
        item = self.history_tree.itemAt(pos)
        c = DARK if self._current_theme == "dark" else LIGHT
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']}; }}"
            f"QMenu::item {{ padding: 6px 20px; }}"
            f"QMenu::item:selected {{ background: {c['accent']}33; }}"
        )

        is_folder = item and item.data(0, Qt.UserRole + 1) == "folder"
        path = item.data(0, Qt.UserRole) if item else None

        # ── Always available: New Folder ─────────────────────────────────────
        act_new_folder = menu.addAction("📁 Yeni Klasör")

        if is_folder:
            menu.addSeparator()
            act_rename_folder = menu.addAction("✏️ Klasörü Yeniden Adlandır")
            act_export_folder = menu.addAction("📦 Klasörü Dışa Aktar")
            act_delete_folder = menu.addAction("🗑 Klasörü Sil")
        elif path:
            menu.addSeparator()
            act_move = menu.addAction("📂 Klasöre Taşı")
            menu.addSeparator()
            act_tag = menu.addAction("🏷 Etiket Ekle / Düzenle")
            act_rename = menu.addAction("✏️ Sohbeti Yeniden Adlandır")
            menu.addSeparator()
            act_exp_md = menu.addAction("📄 Markdown Olarak Dışa Aktar")
            act_exp_html = menu.addAction("🌐 HTML Olarak Dışa Aktar")
            act_exp_json = menu.addAction("{ } JSON Olarak Dışa Aktar")
            act_exp_txt = menu.addAction("📝 TXT Olarak Dışa Aktar")
            menu.addSeparator()
            act_del = menu.addAction("🗑 Sohbeti Sil")

        act = menu.exec(self.history_tree.mapToGlobal(pos))
        if not act:
            return

        if act == act_new_folder:
            self._create_new_folder()
        elif is_folder:
            folder_path = item.data(0, Qt.UserRole + 2)
            if act == act_rename_folder:
                self._rename_folder(folder_path, item)
            elif act == act_export_folder:
                self._export_folder_path(Path(folder_path))
            elif act == act_delete_folder:
                self._delete_folder(folder_path)
        elif path:
            if act == act_move:
                self._move_chat_to_folder(path)
            elif act == act_tag:
                self._tag_chat(path)
            elif act == act_rename:
                self._rename_chat(path)
            elif act in (act_exp_md, act_exp_html, act_exp_json, act_exp_txt):
                fmt_map = {act_exp_md: "markdown", act_exp_html: "html",
                           act_exp_json: "json", act_exp_txt: "txt"}
                self._export_chat_path(Path(path), fmt_map[act])
            elif act == act_del:
                self._delete_chat(path)

    def _create_new_folder(self) -> None:
        """Create a new folder inside the chats directory."""
        from utils.paths import get_chats_dir
        name, ok = QInputDialog.getText(self, "Yeni Klasör", "Klasör adı:")
        if not ok or not name.strip():
            return
        # Sanitize
        clean = re.sub(r'[\\/*?:"<>|]', "", name.strip()).replace(" ", "_")
        if not clean:
            return
        new_dir = get_chats_dir() / clean
        if new_dir.exists():
            QMessageBox.warning(self, "Klasör Var", f"'{clean}' klasörü zaten mevcut.")
            return
        try:
            new_dir.mkdir(parents=True, exist_ok=True)
            # Add a .keep file so the folder persists
            (new_dir / ".keep").touch()
            self.load_chat_history()
            self.statusBar().showMessage(f"📁 Klasör oluşturuldu: {clean}", 2000)
        except Exception as e:
            QMessageBox.critical(self, "Hata", str(e))

    def _rename_folder(self, folder_path: str, item) -> None:
        fp = Path(folder_path)
        name, ok = QInputDialog.getText(self, "Klasörü Yeniden Adlandır",
                                        "Yeni ad:", text=fp.name)
        if not ok or not name.strip():
            return
        clean = re.sub(r'[\\/*?:"<>|]', "", name.strip()).replace(" ", "_")
        new_path = fp.parent / clean
        if new_path.exists():
            QMessageBox.warning(self, "Klasör Var", "Bu isimde klasör zaten var.")
            return
        try:
            fp.rename(new_path)
            if self._current_chat_path and self._current_chat_path.startswith(folder_path):
                self._current_chat_path = self._current_chat_path.replace(
                    folder_path, str(new_path), 1)
            self.load_chat_history()
        except Exception as e:
            QMessageBox.critical(self, "Hata", str(e))

    def _delete_folder(self, folder_path: str) -> None:
        fp = Path(folder_path)
        n_files = len(list(fp.glob("*.jsonl")))
        msg = (f"'{fp.name}' klasörünü sil?"
               + (f"\n\n{n_files} sohbet dosyası da silinecek!" if n_files else ""))
        reply = QMessageBox.question(self, "Klasörü Sil", msg,
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        import shutil
        try:
            shutil.rmtree(fp)
            if self._current_chat_path and self._current_chat_path.startswith(folder_path):
                self._current_chat_path = None
                self.chat_history.clear()
            self.load_chat_history()
        except Exception as e:
            QMessageBox.critical(self, "Hata", str(e))

    def _move_chat_to_folder(self, path: str) -> None:
        """Move a chat file to another folder."""
        from utils.paths import get_chats_dir
        chats_dir = get_chats_dir()
        # List all available folders
        folders = [d.name for d in chats_dir.iterdir()
                   if d.is_dir() and not d.name.startswith("__")]
        if not folders:
            QMessageBox.information(self, "Klasör Yok",
                                    "Önce bir klasör oluşturun.")
            return
        folder_name, ok = QInputDialog.getItem(
            self, "Klasöre Taşı", "Hedef klasörü seçin:", sorted(folders), 0, False)
        if not ok:
            return
        src = Path(path)
        dest_dir = chats_dir / folder_name
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        # Avoid overwrite
        counter = 1
        while dest.exists():
            dest = dest_dir / f"{src.stem}_{counter}{src.suffix}"
            counter += 1
        try:
            import shutil
            shutil.move(str(src), str(dest))
            if self._current_chat_path == path:
                self._current_chat_path = str(dest)
            self.load_chat_history()
            self.statusBar().showMessage(f"📂 Taşındı → {folder_name}/", 2000)
        except Exception as e:
            QMessageBox.critical(self, "Hata", str(e))

    def _rename_chat(self, path: str) -> None:
        fp = Path(path)
        current_name = self._decode_filename(fp.stem)
        name, ok = QInputDialog.getText(self, "Sohbeti Yeniden Adlandır",
                                        "Yeni ad:", text=current_name)
        if not ok or not name.strip():
            return
        clean = re.sub(r'[\\/*?:"<>|]', "", name.strip()).replace(" ", "_")
        if not clean:
            return
        from datetime import datetime as dt
        ts = dt.now().strftime("%Y%m%d_%H%M%S")
        new_path = fp.parent / f"{clean}_{ts}.jsonl"
        try:
            fp.rename(new_path)
            if self._current_chat_path == path:
                self._current_chat_path = str(new_path)
            self.load_chat_history()
        except Exception as e:
            QMessageBox.critical(self, "Hata", str(e))

    def _tag_chat(self, path: str) -> None:
        current = ", ".join(tag_manager.get_tags(path))
        text, ok = QInputDialog.getText(self, "Etiketler", "Etiketleri girin (virgülle ayırın):", text=current)
        if ok:
            tags = [t.strip() for t in text.split(",") if t.strip()]
            tag_manager.set_tags(path, tags)
            self.load_chat_history()

    def _delete_chat(self, path: str) -> None:
        reply = QMessageBox.question(self, "Sohbeti Sil", "Bu sohbeti kalıcı olarak sil?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                os.remove(path)
                if self._current_chat_path == path:
                    self._current_chat_path = None
                    self.chat_history.clear()
                self.load_chat_history()
            except Exception as e:
                QMessageBox.critical(self, "Hata", str(e))

    # ── Load Chat ─────────────────────────────────────────────────────────────
    def load_selected_chat(self, item: QTreeWidgetItem, _=None) -> None:
        path = item.data(0, Qt.UserRole)
        if not path or not os.path.exists(path):
            return
        self._load_chat_file(Path(path))

    def _load_chat_file(self, path: Path, scroll_to: int = -1) -> None:
        self._current_chat_path = str(path)
        self.chat_history.clear()
        self.chat_history.setExtraSelections([])
        self._current_messages = []
        try:
            messages = []
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            messages.append(json.loads(line))
                        except Exception:
                            pass
            self._current_messages = messages

            prev_date: Optional[date] = None
            for i, m in enumerate(messages):
                # Date separator
                ts_str = m.get("timestamp", "")
                try:
                    msg_date = datetime.fromisoformat(ts_str).date()
                    if prev_date is None or msg_date != prev_date:
                        date_str = msg_date.strftime("%A, %B %d, %Y")
                        self.chat_history.append(f"<div class='date-sep'>— {date_str} —</div>")
                        prev_date = msg_date
                except Exception:
                    pass

                self._append_message_html(m["role"], m["content"],
                                          ts_str, estimate_tokens=True, message_index=i)

            if scroll_to >= 0:
                self.chat_history.scrollToAnchor(f"msg-{max(0, scroll_to)}")
            else:
                # Restore remembered per-chat scroll (fallback to bottom).
                scroll_state = self._state.get("chat_scroll_positions", {})
                saved_scroll = int(scroll_state.get(str(path), self._state.get("scroll_position", -1)))
                sb = self.chat_history.verticalScrollBar()
                if saved_scroll >= 0:
                    QTimer.singleShot(0, lambda: sb.setValue(max(0, min(saved_scroll, sb.maximum()))))
                else:
                    self.chat_history.moveCursor(QTextCursor.End)

            self._update_ctx_bar()
        except Exception as e:
            self.chat_history.append(f"<span style='color:red'>Error loading: {e}</span>")

    def _append_message_html(self, role: str, content: str,
                              timestamp: str = "", estimate_tokens: bool = False,
                              message_index: Optional[int] = None) -> None:
        c = DARK if self._current_theme == "dark" else LIGHT
        is_user = role == "user"

        row_cls = "msg-row-user" if is_user else "msg-row-asst"
        role_cls = "role-user" if is_user else "role-asst"
        avatar_cls = "avatar-user" if is_user else "avatar-asst"
        avatar_letter = "U" if is_user else "AI"
        role_label = "You" if is_user else "Assistant"

        try:
            ts_display = datetime.fromisoformat(timestamp).strftime("%H:%M") if timestamp else ""
        except Exception:
            ts_display = ""

        rendered = self.md_renderer.render(content)

        tok_info = ""
        if estimate_tokens:
            from utils.token_counter import estimate_tokens as et
            tok = et(content)
            tok_info = f"<span class='tok-count'>~{tok} tokens</span>"

        anchor = f"<a name='msg-{message_index}'></a>" if message_index is not None else ""

        html = (
            anchor +
            f"<div class='msg-row {row_cls}'>"
            # Header row: avatar + name + timestamp
            f"<div class='msg-header'>"
            f"<span class='{avatar_cls}'>{avatar_letter}</span>"
            f"<span class='{role_cls}'>{role_label}</span>"
            f"<span class='ts'>{ts_display}</span>"
            f"</div>"
            # Body indented under avatar
            f"<div class='msg-body'>{rendered}{tok_info}</div>"
            f"</div>"
        )
        self.chat_history.append(html)

    # ── New Chat ──────────────────────────────────────────────────────────────
    def new_chat(self) -> None:
        self.session._history.clear()
        self.session._session_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        self._current_chat_path = None
        self.chat_history.clear()
        self.chat_history.setExtraSelections([])
        c = DARK if self._current_theme == "dark" else LIGHT
        bg = c["bg"]
        text_dim = c["text_dim"]
        accent = c["accent"]
        surface2 = c["surface2"]
        border = c["border"]
        profile_name = self._active_profile
        self.chat_history.setHtml(
            f"""<html><body style='background:{bg};font-family:Segoe UI,sans-serif;'>
            <table width='100%' style='height:420px;border:none;border-collapse:collapse;'>
            <tr><td style='text-align:center;vertical-align:middle;padding:40px;'>
                <div style='font-size:40px;margin-bottom:16px;'>✨</div>
                <div style='font-size:22px;font-weight:700;color:{c["text"]};margin-bottom:8px;'>BetterLLM</div>
                <div style='font-size:13px;color:{text_dim};margin-bottom:24px;'>
                    Profile: <span style='color:{accent};font-weight:600;'>{profile_name}</span>
                </div>
                <table style='border:none;border-collapse:collapse;margin:0 auto;'>
                <tr>
                <td style='padding:8px 10px;'>
                    <div style='background:{surface2};border:1px solid {border};border-radius:10px;padding:14px 18px;text-align:left;width:160px;'>
                        <div style='font-size:20px;margin-bottom:6px;'>⌨️</div>
                        <div style='font-size:12px;font-weight:600;color:{c["text"]};'>Start typing</div>
                        <div style='font-size:11px;color:{text_dim};margin-top:2px;'>Ask anything below</div>
                    </div>
                </td>
                <td style='padding:8px 10px;'>
                    <div style='background:{surface2};border:1px solid {border};border-radius:10px;padding:14px 18px;text-align:left;width:160px;'>
                        <div style='font-size:20px;margin-bottom:6px;'>📋</div>
                        <div style='font-size:12px;font-weight:600;color:{c["text"]};'>Templates</div>
                        <div style='font-size:11px;color:{text_dim};margin-top:2px;'>Ctrl+T for quick start</div>
                    </div>
                </td>
                <td style='padding:8px 10px;'>
                    <div style='background:{surface2};border:1px solid {border};border-radius:10px;padding:14px 18px;text-align:left;width:160px;'>
                        <div style='font-size:20px;margin-bottom:6px;'>🔍</div>
                        <div style='font-size:12px;font-weight:600;color:{c["text"]};'>Search chats</div>
                        <div style='font-size:11px;color:{text_dim};margin-top:2px;'>Ctrl+F to find anything</div>
                    </div>
                </td>
                </tr>
                </table>
            </td></tr>
            </table>
            </body></html>"""
        )
        self._update_ctx_bar()

    # ── Send Message ──────────────────────────────────────────────────────────
    def send_message(self) -> None:
        query = self.input_box.text().strip()
        if not query or (self.chat_worker and self.chat_worker.isRunning()):
            return

        self.input_box.clear()
        ts = datetime.utcnow().isoformat()

        display_query = query
        if self._attached_image_path:
            display_query = f"📎 {os.path.basename(self._attached_image_path)}\n{query}"

        self._append_message_html("user", display_query, ts)
        c = DARK if self._current_theme == "dark" else LIGHT
        self.chat_history.append(
            f"<div class='msg-row msg-row-asst'>"
            f"<div class='msg-header'>"
            f"<span class='avatar-asst'>AI</span>"
            f"<span class='role-asst'>Assistant</span>"
            f"</div>"
            f"<div class='msg-body'>"
        )
        self.chat_history.moveCursor(QTextCursor.End)

        self.btn_send.setEnabled(False)
        self.btn_stop.setEnabled(True)

        params = dict(self._gen_params)
        self.chat_worker = ChatWorker(
            self.session, query,
            self.mem_checkbox.isChecked(),
            self.deep_checkbox.isChecked(),
            self._attached_image_path,
            params
        )
        self._attached_image_path = None
        self.attachment_label.setVisible(False)

        self.chat_worker.batch_ready.connect(self._handle_batch)
        self.chat_worker.finished.connect(self._handle_finished)
        self.chat_worker.error_occurred.connect(self._handle_error)
        self.chat_worker.start()

    def _handle_batch(self, text: str) -> None:
        # During streaming: append plain text in small batches for smoother UI.
        sb = self.chat_history.verticalScrollBar()
        keep_bottom = sb.value() >= (sb.maximum() - 4)

        cursor = self.chat_history.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self.chat_history.setTextCursor(cursor)

        if keep_bottom:
            sb.setValue(sb.maximum())

    def _handle_finished(self, full_text: str, tps: float) -> None:
        self._tps_history.append(tps)
        avg_tps = sum(self._tps_history) / len(self._tps_history)
        self.tps_lbl.setText(f"⚡ {avg_tps:.1f} T/s")
        self.tps_graph.add_tps(tps)
        self.tps_graph.setVisible(True)

        commands = self.session.detect_commands(full_text)
        for cmd in commands:
            self.ask_run_command(cmd)

        self.refresh_current_view()
        self._update_ctx_bar()
        self.btn_send.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.input_box.setFocus()
        self.load_chat_history()

        if self._regen_pending_compare and self._regen_previous_response:
            self._show_regen_compare(self._regen_previous_response, full_text)
        self._regen_pending_compare = False
        self._regen_previous_response = None

        # Update timeline
        self._refresh_timeline()

        # Record prompt in version history
        history = self.session._history
        if len(history) >= 2:
            last_user = next((m.content for m in reversed(history) if m.role == "user"), "")
            pv_util.record_prompt(last_user)

        # Generate suggestions if sidebar is visible
        if self.suggestion_sidebar.isVisible():
            exchange = "\n".join(
                f"{m.role}: {m.content[:200]}"
                for m in history[-6:]
            )
            self.suggestion_sidebar.generate_for(self.session, exchange)

    def _handle_error(self, err: str) -> None:
        c = DARK if self._current_theme == "dark" else LIGHT
        danger = c["danger"]
        self.chat_history.append(
            f"<div style='color:{danger};padding:8px;border-left:3px solid {danger}'>"
            f"⚠ Error: {err}</div>"
        )
        self.btn_send.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def stop_generation(self) -> None:
        if self.chat_worker:
            self.chat_worker.cancel()
            self.session.cancel_generation()
            self.btn_stop.setEnabled(False)

    # ── Refresh View ──────────────────────────────────────────────────────────
    def refresh_current_view(self) -> None:
        self.chat_history.clear()
        prev_date: Optional[date] = None
        for i, m in enumerate(self.session._history):
            ts = m.timestamp
            try:
                msg_date = datetime.fromisoformat(ts).date()
                if prev_date is None or msg_date != prev_date:
                    date_str = msg_date.strftime("%A, %B %d, %Y")
                    self.chat_history.append(f"<div class='date-sep'>— {date_str} —</div>")
                    prev_date = msg_date
            except Exception:
                pass
            self._append_message_html(m.role, m.content, ts, estimate_tokens=True, message_index=i)
        self.chat_history.moveCursor(QTextCursor.End)
        self._refresh_timeline()

    # ── Context Bar ───────────────────────────────────────────────────────────
    def _update_ctx_bar(self) -> None:
        history = [{"content": m.content} for m in self.session._history]
        used = estimate_messages_tokens(history)
        ctx_size = 4096
        topic = self.session._active_topic
        if topic and topic in self.config.models.topics:
            ctx_size = self.config.models.topics[topic].ctx_size
        pct = int(context_usage_percent(used, ctx_size))
        status = context_status(used, ctx_size)
        self.ctx_bar.setValue(pct)
        self.ctx_lbl.setText(f"Context: ~{used:,} / {ctx_size:,} tokens  ({pct}%)")
        c = DARK if self._current_theme == "dark" else LIGHT
        color = c["danger"] if status == "critical" else c["warning"] if status == "warning" else c["accent"]
        self.ctx_bar.setStyleSheet(
            f"QProgressBar#ctx_bar {{ background: {c['surface2']}; border: none; border-radius: 3px; }}"
            f"QProgressBar#ctx_bar::chunk {{ background: {color}; border-radius: 3px; }}"
        )
        if status == "critical":
            self.ctx_lbl.setStyleSheet(f"color: {c['danger']}; font-size: 11px; font-weight: bold;")
        elif status == "warning":
            self.ctx_lbl.setStyleSheet(f"color: {c['warning']}; font-size: 11px; font-weight: 600;")
        else:
            self.ctx_lbl.setStyleSheet(f"color: {c['text_dim']}; font-size: 11px;")

        if status != self._last_ctx_status:
            if status == "warning":
                self.statusBar().showMessage("⚠ Context usage is high. Consider summarizing or pruning messages.", 4000)
            elif status == "critical":
                self.statusBar().showMessage("🛑 Context limit is near. Responses may degrade or truncate.", 5000)
            self._last_ctx_status = status

    # ── Generation Settings ───────────────────────────────────────────────────
    def open_gen_settings(self) -> None:
        dlg = GenerationSettingsDialog(self._gen_params, self)
        dlg.settings_changed.connect(self._on_gen_settings_changed)
        dlg.exec()

    def _on_gen_settings_changed(self, params: Dict) -> None:
        self._gen_params = params
        preset = params.get("preset", "Custom")
        self.preset_badge.setText(f"⚙ {preset}")
        self._state["active_preset"] = preset
        self._state["generation_params"] = params

    # ── Prompt Library ────────────────────────────────────────────────────────
    def open_prompt_library(self) -> None:
        current = self.input_box.text()
        dlg = PromptLibraryDialog(self, current_input=current)
        dlg.prompt_selected.connect(self.input_box.setText)
        dlg.exec()

    # ── Global Search ─────────────────────────────────────────────────────────
    def open_search(self) -> None:
        dlg = SearchDialog(self._indexer, self)
        dlg.jump_to_message.connect(self._jump_to_search_result)
        dlg.show_and_focus()

    def _jump_to_search_result(self, chat_path: str, message_index: int, query: str = "") -> None:
        if os.path.exists(chat_path):
            self._load_chat_file(Path(chat_path), scroll_to=message_index)
            if query:
                self._highlight_in_chat(query)
            self.load_chat_history()

    def _highlight_in_chat(self, query: str) -> None:
        if not query:
            self.chat_history.setExtraSelections([])
            return

        text = self.chat_history.toPlainText()
        q = query.lower()
        text_l = text.lower()

        positions = []
        pos = 0
        while True:
            pos = text_l.find(q, pos)
            if pos == -1:
                break
            positions.append(pos)
            pos += len(query)

        if not positions:
            self.chat_history.setExtraSelections([])
            return

        sels = []
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#f59e0b55"))

        for p0 in positions:
            cursor = self.chat_history.textCursor()
            cursor.setPosition(p0)
            cursor.setPosition(p0 + len(query), QTextCursor.KeepAnchor)
            sel = QTextEdit.ExtraSelection()
            sel.cursor = cursor
            sel.format = fmt
            sels.append(sel)

        self.chat_history.setExtraSelections(sels)
        self.chat_history.setTextCursor(sels[0].cursor)
        self.chat_history.ensureCursorVisible()

    # ── Export ────────────────────────────────────────────────────────────────
    def export_current_chat(self) -> None:
        if not self._current_chat_path:
            QMessageBox.information(self, "Export", "No chat is currently open.")
            return

        chat_path = Path(self._current_chat_path)
        folder_path = chat_path.parent
        choice, ok = QInputDialog.getItem(
            self,
            "Export",
            "What would you like to export?",
            ["Current chat", f"Entire folder ({folder_path.name})"],
            0,
            False,
        )
        if not ok:
            return

        if choice.startswith("Entire folder"):
            self._export_folder_path(folder_path)
        else:
            self._export_chat_path(chat_path)

    def _export_chat_path(self, path: Path, fmt: str = None) -> None:
        from utils.chat_exporter import export_chat
        if fmt is None:
            items = ["Markdown (.md)", "HTML (.html)", "JSON (.json)", "Plain Text (.txt)"]
            item, ok = QInputDialog.getItem(self, "Export Format", "Choose format:", items, 0, False)
            if not ok:
                return
            fmt = {"Markdown (.md)": "markdown", "HTML (.html)": "html",
                   "JSON (.json)": "json", "Plain Text (.txt)": "txt"}[item]

        out_dir = QFileDialog.getExistingDirectory(self, "Select Export Folder")
        if not out_dir:
            return

        result = export_chat(path, Path(out_dir), fmt)
        if result:
            QMessageBox.information(self, "Exported", f"Saved to:\n{result}")
            if os.name == "nt":
                os.startfile(Path(out_dir))
        else:
            QMessageBox.critical(self, "Export Failed", "Could not export the chat.")


    def _export_folder_path(self, folder_path: Path, fmt: str = None) -> None:
        from utils.chat_exporter import export_folder
        if fmt is None:
            items = ["Markdown (.md)", "HTML (.html)", "JSON (.json)", "Plain Text (.txt)"]
            item, ok = QInputDialog.getItem(self, "Folder Export Format", "Choose format:", items, 0, False)
            if not ok:
                return
            fmt = {"Markdown (.md)": "markdown", "HTML (.html)": "html",
                   "JSON (.json)": "json", "Plain Text (.txt)": "txt"}[item]

        out_dir = QFileDialog.getExistingDirectory(self, "Select Export Folder")
        if not out_dir:
            return

        results = export_folder(folder_path, Path(out_dir), fmt)
        if results:
            QMessageBox.information(self, "Exported", f"Exported {len(results)} chats to:\n{Path(out_dir) / folder_path.name}")
            if os.name == "nt":
                os.startfile(Path(out_dir))
        else:
            QMessageBox.warning(self, "Export", "No chat files were exported from this folder.")

    # ── Upload / Attach ───────────────────────────────────────────────────────
    def upload_image(self) -> None:
        from utils.paths import get_images_uploaded_dir
        import shutil
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if path:
            src = Path(path)
            dest_dir = get_images_uploaded_dir()
            dest = dest_dir / src.name
            if dest.exists():
                dest = dest_dir / f"{src.stem}_{int(time.time())}{src.suffix}"
            try:
                shutil.copy(src, dest)
                self._attached_image_path = str(dest)
                self.attachment_label.setText(f"📎 {dest.name}  ✕")
                self.attachment_label.setVisible(True)
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    # ── Model Browser / Import / Playground ───────────────────────────────────
    def open_model_browser(self) -> None:
        from .model_browser import ModelBrowser
        browser = ModelBrowser(self.model_manager, self.monitor, self)
        browser.model_loaded_signal.connect(lambda _: self._update_status())
        browser.exec()

    def open_import_dialog(self, file_path: Optional[str] = None) -> None:
        from .import_dialog import ImportDialog
        dialog = ImportDialog(self)
        if file_path:
            dialog._load_file(file_path)
        if dialog.exec():
            self.load_chat_history()

    def open_playground(self) -> None:
        pg = PromptPlayground(self.model_manager, self)
        pg.exec()

    def import_document(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Document", "", "Docs (*.pdf *.txt *.md *.py *.js *.cpp *.h)")
        if path:
            if self.session.add_to_knowledge_base(path):
                QMessageBox.information(self, "Imported", f"Indexed: {os.path.basename(path)}")
            else:
                QMessageBox.critical(self, "Error", f"Failed to index {os.path.basename(path)}")

    def fork_chat(self) -> None:
        if not self.session._history:
            return
        last_id = self.session._history[-1].id
        new_sid = self.session.fork_conversation(last_id)
        QMessageBox.information(self, "Chat Forked",
                                f"New branch created.\nSession: {new_sid}")

    # ── LAN Mode ─────────────────────────────────────────────────────────────
    def toggle_lan_mode(self, checked: bool) -> None:
        if checked:
            self.lan_server.start()
            info = self.lan_server.get_info()
            self.lan_status_label.setText(f"🌐 LAN: {info['ip']}:{info['port']}")
            self.lan_status_label.setToolTip(
                f"OpenAI API: {info['openai_url']}\n"
                f"Status: {info['status_url']}\n"
                f"Auth: {'Etkin' if info['auth_enabled'] else 'Devre dışı'}\n\n"
                f"OpenAI uyumlu istemcilerden bağlanmak için:\n"
                f"base_url = \"{info['openai_url']}\""
            )
        else:
            self.lan_server.stop()
            self.lan_status_label.setText("")
            self.lan_status_label.setToolTip("")

    # ── Drag & Drop ───────────────────────────────────────────────────────────
    def dragEnterEvent(self, event) -> None:
        event.accept() if event.mimeData().hasUrls() else event.ignore()

    def dropEvent(self, event) -> None:
        for u in event.mimeData().urls():
            f = u.toLocalFile()
            if f.lower().endswith(('.zip', '.json')):
                self.open_import_dialog(f)
                break

    # ── Status Updates ────────────────────────────────────────────────────────
    def _update_status(self) -> None:
        ram = self.monitor.get_system_ram()
        self.ram_sb.setText(
            f"RAM {ram.used / (1024**3):.1f} / {ram.total / (1024**3):.1f} GB  ({ram.percent}%)")
        gpu = self.monitor.get_gpu_stats()
        if gpu:
            self.gpu_sb.setText(
                f"VRAM {gpu['vram_used'] / (1024**3):.1f} / {gpu['vram_total'] / (1024**3):.1f} GB")
        active = self.model_manager.get_active_model_topic()
        self.active_model_label.setText(f"Model: {active or 'None'}")
        profile = self.config.profile if self.config.profile else ""
        self.profile_label.setText(profile)

    def _on_typing(self, text: str) -> None:
        if text.strip() and not (self.chat_worker and self.chat_worker.isRunning()):
            topic = self.session._router.get_topic(text)
            self.warm_loader.maybe_start_warm_loading(topic)

    def _on_warm_state_changed(self, topic: str, state: WarmState, progress: float) -> None:
        from PySide6.QtCore import QMetaObject, Qt, Q_ARG
        status_text = self.warm_loader.get_status_text()
        QMetaObject.invokeMethod(self.warm_status_label, "setText",
                                 Qt.QueuedConnection, Q_ARG(str, status_text))
        if state == WarmState.READY:
            QMetaObject.invokeMethod(self, "_update_status", Qt.QueuedConnection)

    # ── Terminal Command ──────────────────────────────────────────────────────
    def ask_run_command(self, command: str) -> None:
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        c = DARK if self._current_theme == "dark" else LIGHT
        dialog = QDialog(self)
        dialog.setWindowTitle("Run Command?")
        dialog.setMinimumWidth(500)
        dialog.setStyleSheet(f"QDialog, QWidget {{ background: {c['surface']}; color: {c['text']}; }}")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("AI suggested this command. Edit before running:"))
        edit = QTextEdit()
        edit.setPlainText(command)
        edit.setStyleSheet(f"background: {c['bg']}; color: {c['text']}; font-family: Consolas; border-radius: 4px;")
        layout.addWidget(edit)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dialog.accept)
        btns.rejected.connect(dialog.reject)
        layout.addWidget(btns)
        if dialog.exec() == QDialog.Accepted:
            cmd = edit.toPlainText().strip()
            if cmd:
                success, output = self.session.execute_command(cmd)
                color = c["success"] if success else c["danger"]
                surf2 = c["surface2"]
                status_label = "OK" if success else "FAIL"
                self.chat_history.append(
                    f"<div style='border-left:4px solid {color};padding:10px;background:{surf2};border-radius:4px;margin:8px 0'>"
                    f"<b>Terminal ({status_label}):</b><pre style='font-family:Consolas;font-size:12px'>{output}</pre></div>"
                )

    # ── Regenerate Response ───────────────────────────────────────────────────
    def regenerate_response(self) -> None:
        """Regenerate the last assistant response while preserving previous output for comparison."""
        if self.chat_worker and self.chat_worker.isRunning():
            return

        history = self.session._history
        if len(history) < 2:
            return

        # Find the last assistant/user pair.
        asst_idx = next((i for i in range(len(history) - 1, -1, -1) if history[i].role == "assistant"), -1)
        if asst_idx <= 0:
            return
        user_idx = next((i for i in range(asst_idx - 1, -1, -1) if history[i].role == "user"), -1)
        if user_idx < 0:
            return

        prev_response = history[asst_idx].content
        prompt = history[user_idx].content

        # Keep everything before the selected user message; new exchange will be appended.
        self.session._history = history[:user_idx]

        self._regen_previous_response = prev_response
        self._regen_pending_compare = True

        self.input_box.setText(prompt)
        self.refresh_current_view()
        self._update_ctx_bar()
        self.send_message()

    def _show_regen_compare(self, previous: str, current: str) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Compare Responses")
        dlg.resize(980, 620)

        lay = QVBoxLayout(dlg)
        split = QSplitter(Qt.Horizontal)

        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.addWidget(QLabel("Previous"))
        prev_box = QTextEdit()
        prev_box.setReadOnly(True)
        prev_box.setPlainText(previous)
        left_l.addWidget(prev_box)

        right = QWidget()
        right_l = QVBoxLayout(right)
        right_l.addWidget(QLabel("Regenerated"))
        cur_box = QTextEdit()
        cur_box.setReadOnly(True)
        cur_box.setPlainText(current)
        right_l.addWidget(cur_box)

        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([490, 490])
        lay.addWidget(split)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn, alignment=Qt.AlignRight)

        dlg.exec()

    # ── Chat Summarization ────────────────────────────────────────────────────
    def summarize_chat(self) -> None:
        """Summarize the current conversation and show at top."""
        if not self.session._history:
            QMessageBox.information(self, "Summarize", "No conversation to summarize.")
            return
        if self.chat_worker and self.chat_worker.isRunning():
            QMessageBox.warning(self, "Busy", "Please wait for generation to finish.")
            return

        c = DARK if self._current_theme == "dark" else LIGHT
        self.statusBar().showMessage("Generating summary…")

        # Build summary prompt
        lines = []
        for m in self.session._history[-20:]:  # last 20 messages
            lines.append(f"{m.role}: {m.content[:300]}")
        summary_query = (
            "Please provide a concise 2-3 sentence summary of the following conversation:\n\n"
            + "\n".join(lines)
        )

        # Use a temporary worker to get summary
        from core.chat_session import ChatSession
        temp_params = {"max_tokens": 256, "temperature": 0.3}
        worker = ChatWorker(self.session, summary_query, False, False, None, temp_params)
        summary_result = []

        def on_batch(text):
            summary_result.append(text)

        def on_done(full, tps):
            summary = "".join(summary_result).strip()
            # Remove the summary exchange from session history
            if self.session._history and self.session._history[-1].role == "assistant":
                self.session._history.pop()
            if self.session._history and self.session._history[-1].role == "user":
                self.session._history.pop()
            # Prepend summary to chat view
            summary_html = (
                f"<div class='summary-block'>"
                f"<b style='color:{c['warning']}'>📋 Conversation Summary</b><br>{summary}"
                f"</div>"
            )
            cursor = self.chat_history.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self.chat_history.setTextCursor(cursor)
            self.chat_history.insertHtml(summary_html)
            self.statusBar().showMessage("Summary generated.", 3000)

        worker.batch_ready.connect(on_batch)
        worker.finished.connect(on_done)
        worker.start()
        self._summary_worker = worker  # keep reference

    # ── Context Menu on Chat ──────────────────────────────────────────────────
    def _chat_context_menu(self, pos) -> None:
        c = DARK if self._current_theme == "dark" else LIGHT
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']}; }}"
            f"QMenu::item:selected {{ background: {c['accent']}33; }}"
        )
        act_copy = menu.addAction("📋 Copy Selected Text")
        act_copy_all = menu.addAction("📄 Copy All Text")
        menu.addSeparator()
        # Find which message index is being right-clicked (rough estimate)
        act_bookmark = menu.addAction("🔖 Bookmark This Message")
        menu.addSeparator()
        act_edit = menu.addAction("✏️ Edit Last User Message")

        act = menu.exec(self.chat_history.mapToGlobal(pos))

        if act == act_copy:
            QGuiApplication.clipboard().setText(self.chat_history.textCursor().selectedText())
        elif act == act_copy_all:
            QGuiApplication.clipboard().setText(self.chat_history.toPlainText())
        elif act == act_bookmark:
            self._bookmark_near_cursor()
        elif act == act_edit:
            self._edit_last_user_message()

    def _bookmark_near_cursor(self) -> None:
        """Bookmark the message nearest to cursor position."""
        if not self._current_chat_path or not self._current_messages:
            return
        # Use last message as a simple bookmark target
        msgs = self._current_messages
        if not msgs:
            return
        # Find last assistant message
        for i in range(len(msgs) - 1, -1, -1):
            m = msgs[i]
            if m.get("role") == "assistant":
                bm_util.add_bookmark(
                    self._current_chat_path, i,
                    m.get("content", ""), m.get("role", "")
                )
                c = DARK if self._current_theme == "dark" else LIGHT
                self.statusBar().showMessage("🔖 Message bookmarked!", 2000)
                return

    def _edit_last_user_message(self) -> None:
        """Put the last user message back into the input box for editing."""
        history = self.session._history
        if not history:
            return
        # Find last user message
        for i in range(len(history) - 1, -1, -1):
            if history[i].role == "user":
                content = history[i].content
                self.input_box.setText(content)
                self.input_box.setFocus()
                # Remove from history so it can be re-sent
                history.pop(i)
                # Also remove any trailing assistant response
                while history and history[-1].role == "assistant":
                    history.pop()
                self.refresh_current_view()
                self._update_ctx_bar()
                return

    # ── Assistant Profiles ────────────────────────────────────────────────────
    def open_profiles(self) -> None:
        from .profiles_dialog import ProfilesDialog
        dlg = ProfilesDialog(self._active_profile, self)
        dlg.profile_selected.connect(self._on_profile_selected)
        dlg.exec()

    def _on_profile_selected(self, name: str) -> None:
        self._active_profile = name
        self.profile_badge.setText(f"🎭 {name}")
        # Update session system prompt based on profile
        profile = assistant_profiles.get_profile(name)
        if profile:
            self.session._active_profile = name
            self.session._profile_system_prompt = profile.get("system_prompt", "")
        c = DARK if self._current_theme == "dark" else LIGHT
        self.statusBar().showMessage(f"Profile switched to: {name}", 2000)

    # ── Analytics ─────────────────────────────────────────────────────────────
    def open_analytics(self) -> None:
        from .analytics_dialog import ChatAnalyticsDialog
        dlg = ChatAnalyticsDialog(self._current_chat_path, self)
        dlg.exec()

    # ── Bookmarks ─────────────────────────────────────────────────────────────
    def open_bookmarks(self) -> None:
        from .bookmarks_dialog import BookmarksDialog
        dlg = BookmarksDialog(self)
        dlg.jump_to.connect(self._jump_to_bookmark)
        dlg.exec()

    def _jump_to_bookmark(self, chat_path: str, message_index: int) -> None:
        import os
        if os.path.exists(chat_path):
            self._load_chat_file(Path(chat_path), scroll_to=message_index)
            self.load_chat_history()

    # ── Timeline ──────────────────────────────────────────────────────────────
    def toggle_timeline(self) -> None:
        visible = self.timeline_panel.isVisible()
        self.timeline_panel.setVisible(not visible)
        if not visible:
            self._refresh_timeline()
            sizes = self.splitter.sizes()
            # Distribute space: sidebar | chat | timeline | suggestions
            total = sum(sizes)
            self.splitter.setSizes([sizes[0], total - sizes[0] - 200, 200, sizes[3] if len(sizes) > 3 else 0])

    def _refresh_timeline(self) -> None:
        if not self.timeline_panel.isVisible():
            return
        msgs = [{"role": m.role, "content": m.content, "timestamp": m.timestamp}
                for m in self.session._history]
        if not msgs and self._current_messages:
            msgs = self._current_messages
        self.timeline_panel.update_messages(msgs)

    def _jump_to_timeline_message(self, index: int) -> None:
        """Scroll chat view to a specific message index."""
        self.chat_history.scrollToAnchor(f"msg-{max(0, index)}")

    # ── AI Suggestions ────────────────────────────────────────────────────────
    def toggle_suggestions(self) -> None:
        visible = self.suggestion_sidebar.isVisible()
        self.suggestion_sidebar.setVisible(not visible)
        if not visible:
            sizes = self.splitter.sizes()
            total = sum(sizes)
            tl_w = 200 if self.timeline_panel.isVisible() else 0
            self.splitter.setSizes([sizes[0], total - sizes[0] - tl_w - 220, tl_w, 220])
            # Generate suggestions for current conversation
            history = self.session._history
            if history:
                exchange = "\n".join(f"{m.role}: {m.content[:200]}" for m in history[-6:])
                self.suggestion_sidebar.generate_for(self.session, exchange)

    def _on_suggestion_clicked(self, text: str) -> None:
        self.input_box.setText(text)
        self.input_box.setFocus()

    # ── Snapshots ─────────────────────────────────────────────────────────────
    def open_snapshots(self) -> None:
        from .snapshots_dialog import SnapshotsDialog
        dlg = SnapshotsDialog(self._current_chat_path, self)
        dlg.restore_snapshot.connect(self._restore_snapshot)
        dlg.exec()

    def _quick_snapshot(self) -> None:
        """Save a quick snapshot with Ctrl+Shift+S."""
        msgs = [{"role": m.role, "content": m.content, "timestamp": m.timestamp}
                for m in self.session._history]
        if not msgs:
            return
        snap_id = snap_util.save_snapshot(
            self._current_chat_path or "unsaved",
            msgs,
            label=f"Quick save ({len(msgs)} messages)"
        )
        self.statusBar().showMessage(f"📸 Snapshot saved ({len(msgs)} messages)", 2000)

    def _restore_snapshot(self, messages: List[Dict]) -> None:
        """Restore conversation history from a snapshot."""
        from core.chat_session import ChatMessage
        self.session._history.clear()
        for m in messages:
            self.session._history.append(ChatMessage(
                role=m.get("role", "user"),
                content=m.get("content", ""),
                timestamp=m.get("timestamp", ""),
                id=m.get("id"),
                parent_id=m.get("parent_id"),
            ))
        self.refresh_current_view()
        self._update_ctx_bar()
        self.statusBar().showMessage("⏪ Snapshot restored", 2000)

    # ── Prompt Versions ───────────────────────────────────────────────────────
    def open_prompt_versions(self) -> None:
        from .prompt_versions_dialog import PromptVersionsDialog
        dlg = PromptVersionsDialog(self)
        dlg.prompt_selected.connect(self.input_box.setText)
        dlg.exec()

    # ── Templates ─────────────────────────────────────────────────────────────
    def open_templates(self) -> None:
        from .templates_dialog import TemplatesDialog
        dlg = TemplatesDialog(self)
        dlg.template_selected.connect(self._apply_template)
        dlg.exec()

    def _apply_template(self, system_prompt: str, starter: str, name: str) -> None:
        """Apply a chat template: start new chat with profile system prompt."""
        self.new_chat()
        # Set the system prompt via profile mechanism
        self.session._profile_system_prompt = system_prompt
        self.session._active_profile = f"Template: {name}"
        self.profile_badge.setText(f"📋 {name}")
        if starter:
            self.input_box.setText(starter)
            self.input_box.setFocus()
        self.statusBar().showMessage(f"📋 Template applied: {name}", 2000)

    # ── Workspaces ────────────────────────────────────────────────────────────
    def open_workspaces(self) -> None:
        from .workspaces_dialog import WorkspacesDialog
        dlg = WorkspacesDialog(self._current_chat_path or "", self)
        dlg.workspace_activated.connect(self._on_workspace_activated)
        dlg.exec()

    def _on_workspace_activated(self, name: str) -> None:
        from utils.workspaces import get_workspace
        ws = get_workspace(name)
        if ws:
            # Apply workspace settings
            if ws.get("gen_params"):
                self._gen_params.update(ws["gen_params"])
            if ws.get("profile"):
                self._on_profile_selected(ws["profile"])
            self.statusBar().showMessage(f"🗂 Workspace: {name}", 2000)
            # Update window title
            self.setWindowTitle(f"BetterLLM — {name}")

    # ── Benchmark ─────────────────────────────────────────────────────────────
    def open_benchmark(self) -> None:
        from .benchmark_dialog import BenchmarkDialog
        dlg = BenchmarkDialog(self.session, self._gen_params, self)
        dlg.exec()

    # ── Close ─────────────────────────────────────────────────────────────────
    def closeEvent(self, event) -> None:
        self._save_session()
        self._indexer.stop()
        self.model_manager.stop()
        super().closeEvent(event)
