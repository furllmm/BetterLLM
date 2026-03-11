from __future__ import annotations

import os
import threading
import urllib.request
from pathlib import Path
from typing import Optional, List, Dict, Any

from PySide6.QtCore import QTimer, Qt, Signal, QObject
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QVBoxLayout,
    QWidget,
    QFileDialog,
)

from utils.paths import get_models_dir
from core.resource_monitor import ResourceMonitor
from core.model_manager import ModelManager


class ModelBrowser(QDialog):
    """
    GUI for managing models with Load/Unload support and size/quant info.
    """
    model_loaded_signal = Signal(str)

    def __init__(self, model_manager: ModelManager, resource_monitor: ResourceMonitor, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Model Browser")
        self.resize(800, 500)

        self.model_manager = model_manager
        self.monitor = resource_monitor
        self.models_dir = get_models_dir()

        self._setup_ui()
        self._connect_signals()
        
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_stats)
        self.status_timer.start(1000)
        
        self.load_models()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Header: Stats
        stats_layout = QHBoxLayout()
        self.ram_label = QLabel("RAM: -")
        self.gpu_label = QLabel("GPU: -")
        stats_layout.addWidget(self.ram_label)
        stats_layout.addWidget(self.gpu_label)
        layout.addLayout(stats_layout)

        # Path info
        layout.addWidget(QLabel(f"Models folder: {self.models_dir}"))

        # URL Download section
        download_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Paste GGUF download URL...")
        self.btn_download = QPushButton("Download")
        download_layout.addWidget(self.url_input)
        download_layout.addWidget(self.btn_download)
        layout.addLayout(download_layout)

        self.progress = QProgressBar()
        self.progress.setFormat("%p% - %v KB/s")
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # Models List
        self.models_list = QListWidget()
        self.models_list.setSpacing(2)
        layout.addWidget(self.models_list)

        # Actions
        btn_layout = QHBoxLayout()
        self.btn_load = QPushButton("Load Selected")
        self.btn_unload = QPushButton("Unload Selected")
        self.btn_add_file = QPushButton("Add Local File")
        self.btn_delete = QPushButton("Delete Selected")
        self.btn_refresh = QPushButton("Refresh")
        
        btn_layout.addWidget(self.btn_load)
        btn_layout.addWidget(self.btn_unload)
        btn_layout.addWidget(self.btn_add_file)
        btn_layout.addWidget(self.btn_delete)
        btn_layout.addWidget(self.btn_refresh)
        layout.addLayout(btn_layout)

    def _connect_signals(self) -> None:
        self.btn_download.clicked.connect(self.start_download)
        self.btn_add_file.clicked.connect(self.add_local_file)
        self.btn_delete.clicked.connect(self.delete_model)
        self.btn_refresh.clicked.connect(self.load_models)
        self.btn_load.clicked.connect(self.load_selected)
        self.btn_unload.clicked.connect(self.unload_selected)
        self.models_list.itemDoubleClicked.connect(self.load_selected)

    def load_models(self) -> None:
        self.models_list.clear()
        if not self.models_dir.exists():
            return

        # Get status from model manager
        manager_status = {s["path"]: s for s in self.model_manager.get_all_models_status()}

        for f in self.models_dir.glob("*.gguf"):
            size_gb = f.stat().st_size / (1024**3)
            status_info = manager_status.get(str(f))
            is_loaded = status_info["loaded"] if status_info else False
            
            status_text = "[LOADED]" if is_loaded else "[IDLE]"
            item_text = f"{f.name} ({size_gb:.2f} GB)  {status_text}"
            
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, str(f))
            if is_loaded:
                item.setForeground(Qt.darkGreen)
            self.models_list.addItem(item)

    def load_selected(self) -> None:
        item = self.models_list.currentItem()
        if not item: return
        
        path = item.data(Qt.UserRole)
        # We treat the path as the topic for ad-hoc loading
        if self.model_manager.load_model(path):
            self.model_loaded_signal.emit(path)
            self.load_models()
        else:
            QMessageBox.critical(self, "Load Error", f"Failed to load {path}")

    def unload_selected(self) -> None:
        item = self.models_list.currentItem()
        if not item: return
        path = item.data(Qt.UserRole)
        self.model_manager.unload_model(path)
        self.load_models()

    def add_local_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select GGUF", "", "Models (*.gguf)")
        if path:
            src = Path(path)
            dest = self.models_dir / src.name
            if dest.exists():
                QMessageBox.warning(self, "Exists", "Model already in folder.")
                return
            import shutil
            try:
                shutil.copy(src, dest)
                self.load_models()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def delete_model(self) -> None:
        item = self.models_list.currentItem()
        if not item: return
        path = Path(item.data(Qt.UserRole))
        
        reply = QMessageBox.question(self, "Confirm", f"Delete {path.name}?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.model_manager.unload_model(str(path))
            try:
                path.unlink()
                self.load_models()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def start_download(self) -> None:
        url = self.url_input.text().strip()
        if not url: return
        
        name = url.split("/")[-1]
        if not name.endswith(".gguf"):
            name += ".gguf"
            
        dest = self.models_dir / name
        self.progress.setVisible(True)
        self.btn_download.setEnabled(False)

        def _worker():
            try:
                def _report(blocks, block_size, total):
                    if total > 0:
                        p = int(blocks * block_size * 100 / total)
                        self.progress.setValue(min(p, 100))
                
                urllib.request.urlretrieve(url, str(dest), _report)
                self.load_models()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))
            finally:
                self.progress.setVisible(False)
                self.btn_download.setEnabled(True)

        threading.Thread(target=_worker, daemon=True).start()

    def update_stats(self) -> None:
        ram = self.monitor.get_system_ram()
        self.ram_label.setText(f"RAM: {ram.used/(1024**3):.1f}/{ram.total/(1024**3):.1f} GB ({ram.percent}%)")
        
        gpu = self.monitor.get_gpu_stats()
        if gpu:
            self.gpu_label.setText(f"GPU: {gpu['name']} {gpu['vram_used']/(1024**3):.1f}/{gpu['vram_total']/(1024**3):.1f} GB")
        else:
            self.gpu_label.setText("GPU: -")

def run_model_browser(model_manager: ModelManager, resource_monitor: ResourceMonitor) -> None:
    app = QApplication.instance() or QApplication([])
    dlg = ModelBrowser(model_manager, resource_monitor)
    dlg.show()
    app.exec()
