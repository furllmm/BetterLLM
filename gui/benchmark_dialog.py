"""
Model Benchmark Tool
Measures tokens per second and load time for loaded models.
"""
from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QProgressBar, QWidget, QTableWidget, QTableWidgetItem,
    QHeaderView,
)
from PySide6.QtGui import QFont

STYLE = """
QDialog, QWidget { background: #1a1a2e; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
QTableWidget { background: #16213e; border: 1px solid #333; border-radius: 6px;
               gridline-color: #2d2d4e; }
QTableWidget::item { padding: 8px 12px; }
QTableWidget::item:selected { background: #7c83fd22; color: #7c83fd; }
QHeaderView::section { background: #0f1628; color: #8b949e; padding: 8px;
                        border: none; border-bottom: 1px solid #333; font-weight: bold; }
QProgressBar { background: #16213e; border: none; border-radius: 4px; height: 8px; }
QProgressBar::chunk { background: #7c83fd; border-radius: 4px; }
QTextEdit { background: #0f1628; border: 1px solid #333; border-radius: 6px;
            color: #3fb950; font-family: Consolas, monospace; font-size: 12px; padding: 8px; }
QPushButton { background: #7c83fd; color: white; border: none; border-radius: 6px;
              padding: 8px 18px; font-weight: bold; }
QPushButton:hover { background: #9499ff; }
QPushButton:disabled { background: #333; color: #666; }
QPushButton#secondary { background: #2d2d4e; }
"""

BENCHMARK_PROMPTS = [
    ("Short", "What is 2 + 2?", 50),
    ("Medium", "Explain the concept of recursion in programming.", 200),
    ("Long", "Write a detailed explanation of how neural networks learn, including backpropagation, gradient descent, and optimization strategies.", 400),
]


class BenchmarkWorker(QThread):
    log = Signal(str)
    result = Signal(str, float, float)   # prompt_name, tps, latency_ms
    all_done = Signal()

    def __init__(self, session, gen_params: dict):
        super().__init__()
        self.session = session
        self.gen_params = gen_params
        self._cancelled = False

    def run(self):
        for name, prompt, max_tok in BENCHMARK_PROMPTS:
            if self._cancelled:
                break
            self.log.emit(f"\n▶ Running '{name}' benchmark ({max_tok} tokens)…")
            try:
                params = {**self.gen_params, "max_tokens": max_tok, "temperature": 0.1}
                t0 = time.time()
                first_token_time = None
                token_count = 0

                for token in self.session.send_message_stream(prompt, False, False, None, params):
                    if self._cancelled:
                        break
                    if first_token_time is None:
                        first_token_time = time.time()
                    token_count += 1

                elapsed = time.time() - t0
                latency_ms = (first_token_time - t0) * 1000 if first_token_time else 0
                tps = token_count / elapsed if elapsed > 0 else 0

                self.log.emit(f"  ✓ {token_count} tokens in {elapsed:.2f}s → {tps:.1f} T/s  (first token: {latency_ms:.0f}ms)")
                self.result.emit(name, tps, latency_ms)
            except Exception as e:
                self.log.emit(f"  ✗ Error: {e}")
        self.all_done.emit()

    def cancel(self):
        self._cancelled = True


class BenchmarkDialog(QDialog):
    def __init__(self, session, gen_params: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⏱ Model Benchmark")
        self.setMinimumSize(620, 500)
        self.setStyleSheet(STYLE)
        self._session = session
        self._gen_params = gen_params
        self._worker: Optional[BenchmarkWorker] = None
        self._build_ui()

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(16, 16, 16, 16)
        main.setSpacing(10)

        title = QLabel("⏱ Model Benchmark")
        title.setStyleSheet("font-size: 17px; font-weight: bold; color: #7c83fd;")
        main.addWidget(title)

        info = QLabel("Runs 3 prompts to measure tokens/sec and first-token latency.")
        info.setStyleSheet("color: #666; font-size: 12px;")
        main.addWidget(info)

        # Results table
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Test", "Tokens/sec", "First Token (ms)", "Rating"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setMaximumHeight(160)
        main.addWidget(self.table)

        self.progress = QProgressBar()
        self.progress.setRange(0, len(BENCHMARK_PROMPTS))
        self.progress.setValue(0)
        main.addWidget(self.progress)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("Benchmark output will appear here…")
        main.addWidget(self.log_view, 1)

        btn_row = QHBoxLayout()
        self.btn_run = QPushButton("▶ Run Benchmark")
        self.btn_run.clicked.connect(self._run)
        btn_row.addWidget(self.btn_run)
        self.btn_stop = QPushButton("⏹ Stop")
        self.btn_stop.setObjectName("secondary")
        self.btn_stop.clicked.connect(self._stop)
        self.btn_stop.setEnabled(False)
        btn_row.addWidget(self.btn_stop)
        btn_row.addStretch()
        close = QPushButton("Close")
        close.setObjectName("secondary")
        close.clicked.connect(self.accept)
        btn_row.addWidget(close)
        main.addLayout(btn_row)

    def _run(self):
        self.table.setRowCount(0)
        self.log_view.clear()
        self.progress.setValue(0)
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._result_count = 0

        self._worker = BenchmarkWorker(self._session, self._gen_params)
        self._worker.log.connect(self.log_view.append)
        self._worker.result.connect(self._on_result)
        self._worker.all_done.connect(self._on_done)
        self._worker.start()

    def _on_result(self, name: str, tps: float, latency: float):
        self._result_count += 1
        self.progress.setValue(self._result_count)
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(name))
        self.table.setItem(row, 1, QTableWidgetItem(f"{tps:.1f}"))
        self.table.setItem(row, 2, QTableWidgetItem(f"{latency:.0f}"))
        # Rating
        if tps > 30:
            rating = "🟢 Fast"
        elif tps > 10:
            rating = "🟡 OK"
        else:
            rating = "🔴 Slow"
        self.table.setItem(row, 3, QTableWidgetItem(rating))

    def _on_done(self):
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.log_view.append("\n✅ Benchmark complete!")

    def _stop(self):
        if self._worker:
            self._worker.cancel()
        self.btn_stop.setEnabled(False)
