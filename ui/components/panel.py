"""
ui.components.panel
===================
Cấp 2 trong hierarchy: Panel with title + content area.

Usage:
    panel = Panel("🎙️ HIỆU ỨNG (MODE)")
    panel.body_layout.addWidget(some_btn)
"""
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel
from PySide6.QtCore import Qt
from ui.design_tokens import C, SP, FONT


class Panel(QFrame):
    """
    Standardized panel container — cấp 2 (section inside card).

    Structure:
        QFrame#panel
          └─ QVBoxLayout
               ├─ QLabel#panelTitle  (header row)
               └─ body_layout        (caller populates this)
    """

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")

        root = QVBoxLayout(self)
        root.setContentsMargins(SP.MD, SP.SM, SP.MD, SP.SM)
        root.setSpacing(SP.SM)

        # Title
        self._title_label = QLabel(title.upper())
        self._title_label.setObjectName("panelTitle")
        root.addWidget(self._title_label)

        # Body — caller adds widgets here
        self.body_layout = QVBoxLayout()
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(SP.SM)
        root.addLayout(self.body_layout)

    def set_title(self, title: str):
        self._title_label.setText(title.upper())
