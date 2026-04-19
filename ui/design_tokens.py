"""
ui.design_tokens
================
Single source of truth for all design tokens in Quang Lưu Studio.

Usage:
    from ui.design_tokens import C, SP, FONT, load_qss

Spacing scale (Fibonacci-inspired):
    SP.XS  = 4px   (micro)
    SP.SM  = 8px   (tight)
    SP.MD  = 12px  (normal)
    SP.LG  = 16px  (comfortable)
    SP.XL  = 24px  (section)
"""
import os
from dataclasses import dataclass


# ── Color Palette ──────────────────────────────────────────────
C = {
    # Backgrounds
    "bg":           "#0F172A",   # Deep Navy
    "card":         "#1E293B",   # Panel Surface
    "card_hover":   "#334155",   # Panel hover / secondary button

    # Brand / Accent
    "primary":      "#38BDF8",   # Sky Blue (main CTA)
    "creative":     "#A855F7",   # Vivid Purple
    "accent":       "#EF4444",   # Critical Red / danger
    "green":        "#10B981",   # Emerald / success
    "orange":       "#F59E0B",   # Amber / highlight
    "pink":         "#EC4899",   # Pink / mode
    "deep_purple":  "#7C3AED",   # Deep Purple
    "light_purple": "#A855F7",   # Light Purple (alias creative)
    "blue":         "#3B82F6",   # Standard Blue

    # Aliases (backward compat)
    "teal":         "#38BDF8",   # = primary

    # Text
    "text":         "#F8FAFC",   # Off-white
    "text_muted":   "#94A3B8",   # Slate Gray

    # UI
    "border":       "#334155",   # Slate 700
}

# ── QPainter Tokens ────────────────────────────────────────────
PAINTER = {
    # Fader track
    "track_bg":        "#2a2a42",
    "track_groove_l":  "#383858",
    "track_groove_m":  "#4a4a72",
    "track_tick":      "#555575",
    # Fader handle (metallic gradient stops)
    "handle_top":      "#9898c8",
    "handle_mid":      "#7070a8",
    "handle_bot":      "#484870",
    "handle_border":   "#aaaacc",
    "handle_grip":     "#ccccee",
    "handle_grip_sub": "#88889a",
    # Knob
    "knob_outer":      "#3a3a5c",
    "knob_inner_top":  "#8888b8",
    "knob_inner_bot":  "#4a4a72",
    "knob_pointer":    "#e0e0ff",
    "arc_bg":          "#2a2a42",
    # Glass panel
    "glass_bg":        "rgba(25, 30, 52, 180)",
    "glass_border":    "rgba(100, 110, 160, 60)",
    "glass_highlight": "rgba(255, 255, 255, 12)",
    # Glow
    "glow_blue":       "#38BDF8",
    "glow_red":        "#EF4444",
    "glow_green":      "#10B981",
    "glow_orange":     "#F59E0B",
    # Header
    "header_top":      "#12162a",
    "header_bot":      "#0d1020",
    "header_line":     "rgba(56, 189, 248, 40)",
    # Waveform hero
    "waveform_bg":     "rgba(10, 14, 30, 200)",
    "waveform_grad_1": "#38BDF8",   # teal
    "waveform_grad_2": "#A855F7",   # purple
    "waveform_grad_3": "#EC4899",   # pink
    "waveform_grid":   "rgba(56, 189, 248, 12)",
    "waveform_reflect":"rgba(56, 189, 248, 25)",
    # Tab dock
    "tab_active":      "#38BDF8",
    "tab_inactive":    "#64748B",
    "tab_bar_bg":      "rgba(15, 20, 38, 240)",
    "tab_indicator":   "#38BDF8",
    # Transport
    "transport_bg":    "rgba(15, 23, 42, 200)",
    "transport_btn":   "rgba(100, 116, 139, 120)",
}


# ── Spacing Scale ──────────────────────────────────────────────
@dataclass(frozen=True)
class _Spacing:
    XS: int = 4    # micro
    SM: int = 8    # tight
    MD: int = 12   # normal
    LG: int = 16   # comfortable
    XL: int = 24   # section

SP = _Spacing()


# ── Typography ─────────────────────────────────────────────────
FONT = '"Be Vietnam Pro", "Segoe UI", sans-serif'
FONT_MONO = "Consolas"


# ── QSS loader ────────────────────────────────────────────────
def load_qss() -> str:
    """
    Load and return the compiled global QSS string.
    Reads ui/styles/main.qss and substitutes tokens.
    Falls back to an inline version if file not found.
    """
    qss_path = os.path.join(os.path.dirname(__file__), "styles", "main.qss")
    if os.path.exists(qss_path):
        with open(qss_path, encoding="utf-8") as f:
            template = f.read()
        return template % {
            "bg":         C["bg"],
            "card":       C["card"],
            "card_hover": C["card_hover"],
            "primary":    C["primary"],
            "text":       C["text"],
            "text_muted": C["text_muted"],
            "border":     C["border"],
            "font":       FONT,
        }
    # Inline fallback
    return _inline_qss()


def _inline_qss() -> str:
    return f"""
QMainWindow, QWidget#central {{ background-color: {C['bg']}; }}
QLabel {{ color: {C['text']}; font-size: 13px; font-family: {FONT}; background: transparent; }}
QLabel#panelTitle {{ color: {C['text_muted']}; font-weight: 700; font-size: 10px; border: none; background: transparent; }}
QFrame#card {{ background-color: rgba(30, 41, 59, 220); border-radius: 12px; border: 1px solid rgba(51, 65, 85, 0.5); }}
QFrame#panel {{ background-color: rgba(15, 23, 42, 0.55); border-radius: 8px; border: 1px solid rgba(51, 65, 85, 0.4); }}
QFrame#header {{ background-color: {C['bg']}; border-bottom: 1px solid rgba(51, 65, 85, 0.3); }}
QComboBox {{ background-color: {C['card']}; color: {C['text']}; border: 1px solid {C['border']}; border-radius: 8px; padding: 4px 10px; font-size: 13px; font-weight: 600; font-family: {FONT}; }}
QComboBox::drop-down {{ border: none; }}
QComboBox QAbstractItemView {{ background-color: {C['card']}; color: {C['text']}; selection-background-color: {C['primary']}; border: 1px solid {C['border']}; font-size: 13px; }}
QSlider::groove:vertical {{ background: rgba(51, 65, 85, 0.6); width: 6px; border-radius: 3px; }}
QSlider::handle:vertical {{ width: 20px; height: 20px; margin: 0 -7px; border-radius: 10px; border: 2px solid rgba(255, 255, 255, 0.9); }}
QSlider::add-page:vertical {{ border-radius: 3px; }}
QSlider::sub-page:vertical {{ background: rgba(51, 65, 85, 0.4); border-radius: 3px; }}
QToolTip {{ background-color: {C['card']}; color: {C['text']}; border: 1px solid {C['border']}; border-radius: 6px; padding: 4px 8px; font-size: 12px; }}
"""


# ── Color helpers ──────────────────────────────────────────────
from PySide6.QtGui import QColor  # noqa: E402


def lighten(hex_color: str, factor: float = 0.2) -> str:
    """Return a lighter version of hex_color."""
    c = QColor(hex_color)
    r = min(255, int(c.red()   + (255 - c.red())   * factor))
    g = min(255, int(c.green() + (255 - c.green()) * factor))
    b = min(255, int(c.blue()  + (255 - c.blue())  * factor))
    return f"#{r:02x}{g:02x}{b:02x}"


def darken(hex_color: str, factor: float = 0.2) -> str:
    """Return a darker version of hex_color."""
    c = QColor(hex_color)
    r = max(0, int(c.red()   * (1 - factor)))
    g = max(0, int(c.green() * (1 - factor)))
    b = max(0, int(c.blue()  * (1 - factor)))
    return f"#{r:02x}{g:02x}{b:02x}"


# ── QSS helpers ────────────────────────────────────────────────

def card_qss(radius: int = 12, border_left: str = "") -> str:
    left = f"border-left: 3px solid {border_left};" if border_left else ""
    return (
        f"QFrame {{ background-color: {C['card']}; border-radius: {radius}px;"
        f" border: 1px solid {C['border']}; {left} }}"
    )


def scrollarea_qss(width: int = 6) -> str:
    r = width // 2
    return f"""
        QScrollArea {{ border: none; background-color: {C['bg']}; }}
        QScrollBar:vertical {{ background: {C['card']}; width: {width}px; border-radius: {r}px; }}
        QScrollBar::handle:vertical {{ background: {C['border']}; border-radius: {r}px; min-height: 20px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """.strip()


def input_field_qss(focus_color: str = "") -> str:
    focus = focus_color or C["teal"]
    return f"""
        QLineEdit {{
            background-color: {C['bg']}; color: {C['text']};
            border: 1px solid {C['border']}; border-radius: 8px;
            padding: 8px 10px; font-size: 13px; font-family: {FONT};
        }}
        QLineEdit:focus {{ border-color: {focus}; border-width: 2px; }}
    """.strip()


def combo_qss(color: str = "", font_size: int = 13) -> str:
    text_color = color or C["text"]
    return f"""
        QComboBox {{
            background-color: {C['bg']}; color: {text_color};
            border: 1px solid {C['border']}; border-radius: 6px;
            padding: 6px 10px; font-size: {font_size}px; font-weight: bold; font-family: {FONT};
        }}
        QComboBox::drop-down {{ border: none; }}
        QComboBox QAbstractItemView {{
            background-color: {C['card']}; color: {C['text']};
            selection-background-color: {C['primary']};
            border: 1px solid {C['border']}; font-size: {font_size - 1}px; font-family: {FONT};
        }}
    """.strip()


def header_card_qss() -> str:
    return (
        f"QFrame {{ background-color: {C['card']};"
        f" border-bottom: 1px solid {C['border']}; }}"
    )


def footer_card_qss() -> str:
    return (
        f"QFrame {{ background-color: {C['card']};"
        f" border-top: 1px solid {C['border']}; }}"
    )
