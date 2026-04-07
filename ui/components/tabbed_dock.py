"""
ui.components.tabbed_dock
============================
Custom QPainter tabbed dock — bottom control panel.

Features:
  - 4 tabs with QPainter-drawn tab bar
  - Active tab indicator (glowing bottom border)
  - Glassmorphism background per content area
  - Stacked widget for tab contents
  - Smooth visual transitions
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QSizePolicy, QFrame
)
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import (
    QPainter, QPen, QColor, QFont, QFontMetrics,
    QLinearGradient, QPainterPath
)
from ui.design_tokens import C, SP, FONT, PAINTER


class TabBar(QWidget):
    """
    Custom-painted horizontal tab bar.
    Emits tabChanged(int) when a tab is clicked.
    """
    tabChanged = Signal(int)

    TAB_H = 36          # tab bar height
    INDICATOR_H = 3     # bottom indicator height

    def __init__(self, tabs: list, parent=None):
        super().__init__(parent)
        self._tabs = tabs           # list of (icon, label)
        self._active = 0
        self.setFixedHeight(self.TAB_H)
        self.setCursor(Qt.PointingHandCursor)

    def active_index(self):
        return self._active

    def set_active(self, idx):
        if idx != self._active and 0 <= idx < len(self._tabs):
            self._active = idx
            self.tabChanged.emit(idx)
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        w, h = self.width(), self.height()
        n = len(self._tabs)
        tab_w = w / n

        # ── Background ───────────────────────────────────────
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(15, 20, 38, 220))
        p.drawRoundedRect(QRectF(0, 0, w, h), 8, 8)

        font = QFont()
        font.setFamily("Segoe UI")
        font.setPixelSize(12)
        font.setBold(True)
        p.setFont(font)

        for i, (icon, label) in enumerate(self._tabs):
            x = i * tab_w
            is_active = (i == self._active)
            text = f"{icon} {label}"
            tab_rect = QRectF(x, 0, tab_w, h - self.INDICATOR_H)

            # ── Hover/active background ──────────────────────
            if is_active:
                active_bg = QLinearGradient(x, 0, x, h)
                active_bg.setColorAt(0, QColor(56, 189, 248, 15))
                active_bg.setColorAt(1, QColor(56, 189, 248, 5))
                p.setPen(Qt.NoPen)
                p.setBrush(active_bg)
                p.drawRoundedRect(tab_rect, 6, 6)

            # ── Text ─────────────────────────────────────────
            color = QColor(PAINTER["tab_active"]) if is_active else QColor(PAINTER["tab_inactive"])
            p.setPen(color)
            p.drawText(tab_rect, Qt.AlignCenter, text)

            # ── Active indicator ─────────────────────────────
            if is_active:
                ind_w = min(tab_w * 0.6, 60)
                ind_x = x + (tab_w - ind_w) / 2
                ind_rect = QRectF(ind_x, h - self.INDICATOR_H, ind_w, self.INDICATOR_H)

                # Glow
                glow_rect = QRectF(ind_x - 10, h - self.INDICATOR_H - 3,
                                    ind_w + 20, self.INDICATOR_H + 6)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(56, 189, 248, 25))
                p.drawRoundedRect(glow_rect, 4, 4)

                # Indicator line
                p.setBrush(QColor(PAINTER["tab_indicator"]))
                p.drawRoundedRect(ind_rect, 2, 2)

        # ── Bottom border ────────────────────────────────────
        p.setPen(QPen(QColor(51, 65, 85, 40), 1))
        p.drawLine(QRectF(0, h - 1, w, 1).topLeft(),
                   QRectF(0, h - 1, w, 1).topRight())

        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            n = len(self._tabs)
            tab_w = self.width() / n
            idx = int(e.position().x() / tab_w)
            idx = max(0, min(n - 1, idx))
            self.set_active(idx)


class TabbedDock(QWidget):
    """
    Tabbed control dock with custom tab bar + stacked content.
    Add tab content widgets via add_tab_content(widget).
    """

    def __init__(self, tabs: list, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        # Tab bar
        self.tab_bar = TabBar(tabs)
        vl.addWidget(self.tab_bar)

        # Content wrapper — glass panel background
        self._content_wrapper = QFrame()
        self._content_wrapper.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(20, 25, 45, 180);
                border: 1px solid rgba(51, 65, 85, 0.3);
                border-top: none;
                border-bottom-left-radius: 10px;
                border-bottom-right-radius: 10px;
            }}
        """)
        cw_layout = QVBoxLayout(self._content_wrapper)
        cw_layout.setContentsMargins(SP.MD, SP.SM, SP.MD, SP.SM)

        # Stacked widget
        self.stack = QStackedWidget()
        cw_layout.addWidget(self.stack)

        vl.addWidget(self._content_wrapper, 1)

        # Connect tab bar to stack
        self.tab_bar.tabChanged.connect(self.stack.setCurrentIndex)

    def add_tab_content(self, widget):
        """Add a widget as content for the next tab."""
        self.stack.addWidget(widget)

    def set_active_tab(self, idx):
        self.tab_bar.set_active(idx)
        self.stack.setCurrentIndex(idx)
