"""
Token Speed Graph Widget
Visualizes tokens-per-second over recent generations.
"""
from __future__ import annotations

from collections import deque
from typing import Deque

from PySide6.QtCore import Qt, QRect, QPointF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QLinearGradient, QFont, QPainterPath
from PySide6.QtWidgets import QWidget


class TpsGraphWidget(QWidget):
    """Small inline TPS sparkline graph."""

    def __init__(self, maxlen: int = 30, parent=None):
        super().__init__(parent)
        self._data: Deque[float] = deque(maxlen=maxlen)
        self.setMinimumSize(120, 40)
        self.setMaximumHeight(48)
        self._accent = QColor("#7c83fd")
        self._bg = QColor("#16213e")
        self._fill = QColor("#7c83fd")
        self._fill.setAlpha(40)

    def add_tps(self, tps: float) -> None:
        self._data.append(tps)
        self.update()

    def set_colors(self, accent: str, bg: str) -> None:
        self._accent = QColor(accent)
        self._bg = QColor(bg)
        self._fill = QColor(accent)
        self._fill.setAlpha(40)
        self.update()

    def paintEvent(self, event):
        if len(self._data) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        pad = 4

        # Background
        p.fillRect(0, 0, w, h, self._bg)

        data = list(self._data)
        max_v = max(data) or 1
        n = len(data)

        def px(i):
            return pad + (i / (n - 1)) * (w - pad * 2)

        def py(v):
            return h - pad - (v / max_v) * (h - pad * 2)

        # Fill area
        path = QPainterPath()
        path.moveTo(QPointF(px(0), h - pad))
        for i, v in enumerate(data):
            path.lineTo(QPointF(px(i), py(v)))
        path.lineTo(QPointF(px(n - 1), h - pad))
        path.closeSubpath()
        p.fillPath(path, QBrush(self._fill))

        # Line
        pen = QPen(self._accent)
        pen.setWidth(2)
        p.setPen(pen)
        for i in range(1, n):
            p.drawLine(QPointF(px(i - 1), py(data[i - 1])),
                       QPointF(px(i), py(data[i])))

        # Current value label
        current = data[-1]
        p.setFont(QFont("Segoe UI", 8, QFont.Bold))
        p.setPen(self._accent)
        p.drawText(QRect(0, 0, w - 2, h), Qt.AlignRight | Qt.AlignTop,
                   f"{current:.1f} T/s")
        p.end()
