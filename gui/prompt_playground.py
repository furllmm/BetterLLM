from __future__ import annotations

from typing import Dict, Any, Optional

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QPushButton,
    QDoubleSpinBox,
    QSpinBox,
    QComboBox,
    QSplitter,
    QMessageBox,
    QWidget,
)

class PlaygroundWorker(QThread):
    token_received = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, backend: Any, prompt: str, params: Dict[str, Any]) -> None:
        super().__init__()
        self.backend = backend
        self.prompt = prompt
        self.params = params

    def run(self) -> None:
        try:
            full_response = ""
            for token in self.backend.generate_stream(
                self.prompt,
                max_tokens=self.params.get("max_tokens", 512),
                temp=self.params.get("temp", 0.7),
                top_p=self.params.get("top_p", 0.9),
                repeat_penalty=self.params.get("repeat_penalty", 1.1)
            ):
                full_response += token
                self.token_received.emit(token)
            self.finished.emit(full_response)
        except Exception as e:
            self.error.emit(str(e))

class PromptPlayground(QDialog):
    """
    UI for testing prompts with adjustable parameters.
    Allows comparing outputs and fine-tuning generation settings.
    """
    def __init__(self, model_manager: Any, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Prompt Playground")
        self.resize(900, 650)
        self.model_manager = model_manager
        self.worker: Optional[PlaygroundWorker] = None
        
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        self.splitter = QSplitter(Qt.Horizontal)
        
        # Left Panel (Parameters)
        params_panel = QWidget()
        params_layout = QVBoxLayout(params_panel)
        
        params_layout.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        # Scan available models
        for m in self.model_manager.get_all_models_status():
            self.model_combo.addItem(m["topic"])
        params_layout.addWidget(self.model_combo)
        
        params_layout.addWidget(QLabel("Temperature:"))
        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0, 2)
        self.temp_spin.setSingleStep(0.1)
        self.temp_spin.setValue(0.7)
        params_layout.addWidget(self.temp_spin)
        
        params_layout.addWidget(QLabel("Top P:"))
        self.top_p_spin = QDoubleSpinBox()
        self.top_p_spin.setRange(0, 1)
        self.top_p_spin.setSingleStep(0.05)
        self.top_p_spin.setValue(0.9)
        params_layout.addWidget(self.top_p_spin)
        
        params_layout.addWidget(QLabel("Repeat Penalty:"))
        self.repeat_spin = QDoubleSpinBox()
        self.repeat_spin.setRange(1, 2)
        self.repeat_spin.setSingleStep(0.1)
        self.repeat_spin.setValue(1.1)
        params_layout.addWidget(self.repeat_spin)
        
        params_layout.addWidget(QLabel("Max Tokens:"))
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(1, 4096)
        self.max_tokens_spin.setValue(512)
        params_layout.addWidget(self.max_tokens_spin)
        
        params_layout.addStretch()
        self.btn_run = QPushButton("Run Prompt")
        params_layout.addWidget(self.btn_run)
        
        # Right Panel (Prompt & Output)
        main_panel = QWidget()
        main_layout = QVBoxLayout(main_panel)
        
        main_layout.addWidget(QLabel("Prompt:"))
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("Enter your prompt here...")
        main_layout.addWidget(self.prompt_edit)
        
        main_layout.addWidget(QLabel("Output:"))
        self.output_edit = QTextEdit()
        self.output_edit.setReadOnly(True)
        main_layout.addWidget(self.output_edit)
        
        self.splitter.addWidget(params_panel)
        self.splitter.addWidget(main_panel)
        self.splitter.setStretchFactor(1, 4)
        layout.addWidget(self.splitter)

    def _connect_signals(self) -> None:
        self.btn_run.clicked.connect(self.run_prompt)

    def run_prompt(self) -> None:
        topic = self.model_combo.currentText()
        if not topic:
            QMessageBox.warning(self, "No Model", "Select a model first")
            return
            
        prompt = self.prompt_edit.toPlainText().strip()
        if not prompt: return
        
        self.output_edit.clear()
        self.btn_run.setEnabled(False)
        
        params = {
            "temp": self.temp_spin.value(),
            "top_p": self.top_p_spin.value(),
            "repeat_penalty": self.repeat_spin.value(),
            "max_tokens": self.max_tokens_spin.value()
        }
        
        try:
            with self.model_manager.use_model(topic) as backend:
                self.worker = PlaygroundWorker(backend, prompt, params)
                self.worker.token_received.connect(lambda t: self.output_edit.insertPlainText(t))
                self.worker.finished.connect(lambda: self.btn_run.setEnabled(True))
                self.worker.error.connect(lambda e: QMessageBox.critical(self, "Error", e))
                self.worker.start()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            self.btn_run.setEnabled(True)
