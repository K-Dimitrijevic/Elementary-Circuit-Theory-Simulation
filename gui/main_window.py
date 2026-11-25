"""Main application window: canvas in the centre, toolbox docked on the left."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QListWidget, QListWidgetItem, QMainWindow

from gui.canvas import CircuitCanvas

TOOLBOX_ITEMS = ("Battery", "Resistor", "Wire")


class MainWindow(QMainWindow):
    """Top-level window of the circuit construction kit."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Circuit Construction Kit")
        self.resize(1100, 700)

        self.canvas = CircuitCanvas(self)
        self.setCentralWidget(self.canvas)
        self.toolbox = self._build_toolbox()

        self.statusBar().showMessage("Milestone 1: DC solver ready. Building circuits arrives in Milestone 2.")

    def _build_toolbox(self) -> QListWidget:
        """Stub toolbox: lists the parts but they cannot be used yet."""
        toolbox = QListWidget()
        for name in TOOLBOX_ITEMS:
            item = QListWidgetItem(name)
            item.setFlags(Qt.ItemFlag.NoItemFlags)  # shown greyed out, not selectable
            item.setToolTip("Not available yet: drag-and-drop comes in Milestone 2")
            toolbox.addItem(item)

        dock = QDockWidget("Toolbox", self)
        dock.setWidget(toolbox)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        return toolbox
