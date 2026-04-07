"""
ui.components.button
====================
Standardized button system.

Button types:
    primary   — main CTA (sky blue)
    secondary — secondary action (card_hover)
    danger    — destructive / record (red)
    ghost     — transparent, muted
    circle    — icon-only round button

Usage:
    btn = StudioButton("Dò Tone", btn_type="primary", color=C["orange"])
    circle = CircleButton("−", color=C["teal"])
"""
from PySide6.QtWidgets import QPushButton, QGraphicsDropShadowEffect
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from ui.design_tokens import C, SP, FONT, lighten, darken


def _make_pill_qss(
    color: str,
    hover: str | None = None,
    font_size: int = 13,
    radius: int = 12,
) -> str:
    if hover is None:
        hover = lighten(color, 0.15)
    pressed = lighten(color, 0.25)
    return f"""
    QPushButton {{
        background-color: {color};
        color: white;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: {radius}px;
        padding: 6px 14px;
        font-size: {font_size}px;
        font-weight: 600;
        font-family: {FONT};
    }}
    QPushButton:hover {{
        background-color: {hover};
        border: 1px solid {lighten(color, 0.3)};
    }}
    QPushButton:pressed {{
        background-color: {pressed};
    }}
    QPushButton:disabled {{
        background-color: {C["card_hover"]};
        color: {C["text_muted"]};
        border: none;
    }}
    """


def _make_circle_qss(color: str, size: int = 24) -> str:
    return f"""
    QPushButton {{
        background-color: {color};
        color: white;
        border: none;
        border-radius: {size // 2}px;
        font-size: {size // 2}px;
        font-weight: bold;
        min-width: {size}px; max-width: {size}px;
        min-height: {size}px; max-height: {size}px;
        font-family: {FONT};
    }}
    QPushButton:hover {{
        background-color: {lighten(color, 0.15)};
        border: 1px solid rgba(255, 255, 255, 0.2);
    }}
    QPushButton:pressed {{
        background-color: {lighten(color, 0.25)};
    }}
    """


def _make_ghost_qss(color: str, font_size: int = 13) -> str:
    return f"""
    QPushButton {{
        background-color: transparent;
        color: {color};
        border: 1px solid {color};
        border-radius: 8px;
        padding: 5px 12px;
        font-size: {font_size}px;
        font-weight: 600;
        font-family: {FONT};
    }}
    QPushButton:hover {{
        background-color: rgba(56, 189, 248, 0.1);
    }}
    QPushButton:pressed {{
        background-color: rgba(56, 189, 248, 0.2);
    }}
    """


class StudioButton(QPushButton):
    """
    Standard button with shadow.

    btn_type: "primary" | "secondary" | "danger" | "ghost"
    color: hex override (default derived from btn_type)
    shadow: whether to add drop shadow
    """

    _TYPE_COLORS = {
        "primary":   C["primary"],
        "secondary": C["card_hover"],
        "danger":    C["accent"],
        "ghost":     C["primary"],
    }

    def __init__(
        self,
        text: str = "",
        btn_type: str = "primary",
        color: str | None = None,
        height: int = 28,
        font_size: int = 11,
        radius: int = 8,
        shadow: bool = True,
        parent=None,
    ):
        super().__init__(text, parent)
        self._color = color or self._TYPE_COLORS.get(btn_type, C["primary"])
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(height)

        if btn_type == "ghost":
            self.setStyleSheet(_make_ghost_qss(self._color, font_size))
        else:
            self.setStyleSheet(_make_pill_qss(self._color, None, font_size, radius))

        if shadow and btn_type != "ghost":
            self._add_shadow()

    def _add_shadow(self):
        try:
            eff = QGraphicsDropShadowEffect(self)
            eff.setBlurRadius(6)
            eff.setColor(QColor(self._color))
            eff.setOffset(0, 2)
            self.setGraphicsEffect(eff)
        except Exception:
            pass


class CircleButton(QPushButton):
    """Icon-only round button (± buttons, small icons)."""

    def __init__(self, text: str, color: str, size: int = 22, parent=None):
        super().__init__(text, parent)
        self._color = color
        self.setStyleSheet(_make_circle_qss(color, size))
        self.setCursor(Qt.PointingHandCursor)
        try:
            eff = QGraphicsDropShadowEffect(self)
            eff.setBlurRadius(4)
            eff.setColor(QColor(color))
            eff.setOffset(0, 2)
            self.setGraphicsEffect(eff)
        except Exception:
            pass


class RecordButton(QPushButton):
    """Big pill record button — danger variant with pulse support."""

    def __init__(self, parent=None):
        super().__init__("● THU ÂM", parent)
        self._active = False
        self.setFixedSize(155, 34)
        self.setCursor(Qt.PointingHandCursor)
        self._apply_idle()
        try:
            eff = QGraphicsDropShadowEffect(self)
            eff.setBlurRadius(10)
            eff.setColor(QColor(C["accent"]))
            eff.setOffset(0, 2)
            self.setGraphicsEffect(eff)
        except Exception:
            pass

    def set_recording(self, recording: bool):
        self._active = recording
        if recording:
            self._apply_active()
        else:
            self._apply_idle()

    def _apply_idle(self):
        self.setText("● THU ÂM")
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {C["accent"]}; color: white; border: none;
                border-radius: 17px; font-size: 13px; font-weight: 700;
                font-family: {FONT};
            }}
            QPushButton:hover {{ background-color: {lighten(C["accent"], 0.15)}; }}
            QPushButton:pressed {{ background-color: {lighten(C["accent"], 0.25)}; }}
        """)

    def _apply_active(self):
        self.setText("■ ĐANG GHI")
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {C["green"]}; color: white; border: none;
                border-radius: 17px; font-size: 13px; font-weight: 700;
                font-family: {FONT};
            }}
            QPushButton:hover {{ background-color: {lighten(C["green"], 0.15)}; }}
            QPushButton:pressed {{ background-color: {lighten(C["green"], 0.25)}; }}
        """)
