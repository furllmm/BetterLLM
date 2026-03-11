"""
Generation Settings Panel
Per-chat generation parameters with preset support.
"""
from __future__ import annotations

import logging
from typing import Dict

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QSpinBox, QDoubleSpinBox, QGroupBox, QComboBox,
    QDialogButtonBox, QWidget, QGridLayout,
)

logger = logging.getLogger(__name__)

PRESETS = {
    "Precise": {"temperature": 0.2, "top_p": 0.9, "top_k": 20, "repeat_penalty": 1.15, "max_tokens": 512},
    "Balanced": {"temperature": 0.7, "top_p": 0.95, "top_k": 40, "repeat_penalty": 1.1, "max_tokens": 1024},
    "Creative": {"temperature": 1.1, "top_p": 0.99, "top_k": 100, "repeat_penalty": 1.05, "max_tokens": 2048},
    "Fast Draft": {"temperature": 0.6, "top_p": 0.90, "top_k": 30, "repeat_penalty": 1.1, "max_tokens": 256},
}

SETTINGS_STYLE = """
QDialog, QWidget { background: #1a1a2e; color: #e0e0e0; }
QGroupBox { border: 1px solid #333; border-radius: 8px; margin-top: 12px; padding: 10px;
            color: #c0c0e0; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
QSlider::groove:horizontal { background: #16213e; height: 6px; border-radius: 3px; }
QSlider::handle:horizontal { background: #7c83fd; width: 16px; height: 16px;
                              margin: -5px 0; border-radius: 8px; }
QSlider::sub-page:horizontal { background: #7c83fd; border-radius: 3px; }
QSpinBox, QDoubleSpinBox { background: #16213e; border: 1px solid #444; border-radius: 6px;
                            padding: 4px 8px; color: #e0e0e0; }
QComboBox { background: #16213e; border: 1px solid #444; border-radius: 6px;
            padding: 6px 10px; color: #e0e0e0; }
QPushButton { background: #7c83fd; color: white; border: none; border-radius: 6px;
              padding: 7px 16px; font-weight: bold; }
QPushButton:hover { background: #9499ff; }
QPushButton#secondary { background: #2d2d4e; }
QPushButton#secondary:hover { background: #3d3d6e; }
QLabel.value-lbl { color: #7c83fd; font-weight: bold; min-width: 40px; }
"""


def _make_slider_row(parent, label: str, min_val: int, max_val: int,
                     init_val: int, scale: float = 1.0, suffix: str = ""):
    """Helper: returns (row_widget, slider, value_label)."""
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 4, 0, 4)
    lbl = QLabel(label)
    lbl.setMinimumWidth(130)
    lay.addWidget(lbl)
    slider = QSlider(Qt.Horizontal)
    slider.setRange(min_val, max_val)
    slider.setValue(init_val)
    lay.addWidget(slider, 1)
    val_lbl = QLabel(f"{init_val * scale:.2f}{suffix}" if scale != 1.0 else f"{init_val}{suffix}")
    val_lbl.setStyleSheet("color: #7c83fd; font-weight: bold; min-width: 50px;")
    val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    lay.addWidget(val_lbl)

    def _update(v):
        if scale != 1.0:
            val_lbl.setText(f"{v * scale:.2f}{suffix}")
        else:
            val_lbl.setText(f"{v}{suffix}")
    slider.valueChanged.connect(_update)
    return row, slider, val_lbl


class GenerationSettingsDialog(QDialog):
    """
    Dialog for adjusting generation parameters.
    Emits settings_changed({...}) on accept.
    """
    settings_changed = Signal(dict)

    def __init__(self, current_params: Dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙ Generation Settings")
        self.setMinimumWidth(480)
        self.setStyleSheet(SETTINGS_STYLE)
        self._params = dict(current_params)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Preset selector
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Preset:"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(list(PRESETS.keys()))
        self.preset_combo.currentTextChanged.connect(self._apply_preset)
        preset_row.addWidget(self.preset_combo, 1)
        layout.addLayout(preset_row)

        # Parameters group
        grp = QGroupBox("Parameters")
        grp_layout = QVBoxLayout(grp)

        # Temperature (0–200 → 0.00–2.00)
        p = self._params
        temp_100 = int(p.get("temperature", 0.7) * 100)
        row, self.temp_slider, self.temp_lbl = _make_slider_row(
            self, "Temperature", 0, 200, temp_100, scale=0.01)
        grp_layout.addWidget(row)

        # Top-P (0–100 → 0.00–1.00)
        topp_100 = int(p.get("top_p", 0.95) * 100)
        row2, self.topp_slider, self.topp_lbl = _make_slider_row(
            self, "Top-P", 0, 100, topp_100, scale=0.01)
        grp_layout.addWidget(row2)

        # Top-K (1–200)
        row3, self.topk_slider, self.topk_lbl = _make_slider_row(
            self, "Top-K", 1, 200, p.get("top_k", 40))
        grp_layout.addWidget(row3)

        # Repeat Penalty (100–200 → 1.00–2.00)
        rp_100 = int(p.get("repeat_penalty", 1.1) * 100)
        row4, self.rp_slider, self.rp_lbl = _make_slider_row(
            self, "Repeat Penalty", 100, 200, rp_100, scale=0.01)
        grp_layout.addWidget(row4)

        # Max Tokens (spinbox)
        tok_row = QWidget()
        tok_lay = QHBoxLayout(tok_row)
        tok_lay.setContentsMargins(0, 4, 0, 4)
        tok_lay.addWidget(QLabel("Max Tokens"))
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(64, 16384)
        self.max_tokens_spin.setSingleStep(64)
        self.max_tokens_spin.setValue(p.get("max_tokens", 1024))
        tok_lay.addWidget(self.max_tokens_spin)
        grp_layout.addWidget(tok_row)

        layout.addWidget(grp)

        # Info label
        info = QLabel("ℹ️  Changes apply to this chat session.")
        info.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(info)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel)
        apply_btn = buttons.button(QDialogButtonBox.Apply)
        apply_btn.setText("Apply")
        apply_btn.clicked.connect(self._on_apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _apply_preset(self, preset_name: str):
        p = PRESETS.get(preset_name, {})
        if not p:
            return
        self.temp_slider.setValue(int(p["temperature"] * 100))
        self.topp_slider.setValue(int(p["top_p"] * 100))
        self.topk_slider.setValue(p["top_k"])
        self.rp_slider.setValue(int(p["repeat_penalty"] * 100))
        self.max_tokens_spin.setValue(p["max_tokens"])

    def get_params(self) -> Dict:
        return {
            "temperature": self.temp_slider.value() * 0.01,
            "top_p": self.topp_slider.value() * 0.01,
            "top_k": self.topk_slider.value(),
            "repeat_penalty": self.rp_slider.value() * 0.01,
            "max_tokens": self.max_tokens_spin.value(),
            "preset": self.preset_combo.currentText(),
        }

    def _on_apply(self):
        params = self.get_params()
        self.settings_changed.emit(params)
        self.accept()
