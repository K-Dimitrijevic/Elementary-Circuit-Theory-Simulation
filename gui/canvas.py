"""The drawing area: a QGraphicsView showing a QGraphicsScene with a grid."""

from __future__ import annotations

import math

from PySide6.QtCore import QLineF, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QWidget


class CircuitCanvas(QGraphicsView):
    """Empty canvas for now; components and wires will be added as scene items."""

    GRID = 20  # px between grid lines; parts will snap to this later
    BACKGROUND = QColor("#f4f7fb")
    GRID_COLOR = QColor("#dde3ea")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # The scene owns the items; the view is just a camera onto it.
        self.setScene(QGraphicsScene(QRectF(-2000, -2000, 4000, 4000), self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        """Fill the exposed area and draw grid lines aligned to multiples of GRID."""
        painter.fillRect(rect, self.BACKGROUND)
        g = self.GRID
        left = math.floor(rect.left() / g) * g
        top = math.floor(rect.top() / g) * g
        lines = [QLineF(x, rect.top(), x, rect.bottom()) for x in range(left, int(rect.right()) + 1, g)]
        lines += [QLineF(rect.left(), y, rect.right(), y) for y in range(top, int(rect.bottom()) + 1, g)]
        painter.setPen(QPen(self.GRID_COLOR, 0))  # width 0 = 1 device pixel at any zoom
        painter.drawLines(lines)
