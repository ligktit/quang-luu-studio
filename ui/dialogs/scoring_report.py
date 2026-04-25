from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QScrollArea, QWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QLinearGradient, QColor

from ui.design_tokens import C, FONT
from frontend_qt import pill_btn_qss, add_shadow, _lighten


class _GradientBar(QFrame):
    """Custom painted gradient progress bar."""
    def __init__(self, value, color_start, color_end, parent=None):
        super().__init__(parent)
        self._value = value
        self._c0 = color_start
        self._c1 = color_end
        self.setFixedHeight(12)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(C["card"]))
        p.drawRoundedRect(0, 0, w, h, h / 2, h / 2)
        fill_w = w * (self._value / 100.0)
        if fill_w > 0:
            grad = QLinearGradient(0, 0, w, 0)
            grad.setColorAt(0.0, QColor(self._c0))
            grad.setColorAt(1.0, QColor(self._c1))
            p.setBrush(grad)
            p.drawRoundedRect(0, 0, fill_w, h, h / 2, h / 2)


class ScoringReportDialog(QDialog):
    """Dialog hien thi ket qua cham diem Star Score."""

    def __init__(self, parent, result: dict):
        super().__init__(parent)
        self.setWindowTitle("Ket qua Star Score")
        self.setMinimumSize(520, 640)
        self.resize(540, 720)
        self.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")
        self._build_ui(result)

    # ── UI ────────────────────────────────────────────────────

    def _build_ui(self, result: dict):
        score = result.get("total_score", 0)
        feed  = result.get("feedback", {})
        rank     = feed.get("rank", "Ca Si")
        icon     = feed.get("icon", "🎵")
        main_fb  = feed.get("main", "")
        tips     = feed.get("tips", [])

        if score >= 90:
            theme = C["primary"]
        elif score >= 80:
            theme = C["green"]
        elif score >= 70:
            theme = C["orange"]
        else:
            theme = C["pink"]

        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        outer.addWidget(self._build_header(score, rank, icon, theme))
        outer.addWidget(self._build_scroll(result, main_fb, tips, theme), 1)
        outer.addWidget(self._build_footer(theme))

    def _build_header(self, score, rank, icon, theme):
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(30,41,59,255), stop:1 {C['bg']});
                border-bottom: 1px solid rgba(56,189,248,0.2);
            }}
        """)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(4)

        rank_lbl = QLabel(f"{icon} {rank.upper()} {icon}")
        rank_lbl.setStyleSheet(
            f"font-size: 22px; font-weight: bold; color: {theme};"
            f" font-family: {FONT}; background: transparent;"
        )
        rank_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(rank_lbl)

        score_lbl = QLabel(f"{score:.1f}")
        score_lbl.setStyleSheet(
            f"font-size: 80px; font-weight: 900; color: {theme};"
            f" font-family: {FONT}; background: transparent; letter-spacing: -4px;"
        )
        score_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(score_lbl)

        stars_cnt = 5 if score >= 95 else 4 if score >= 85 else 3 if score >= 75 else 2 if score >= 60 else 1
        stars_html = (
            "".join(["<span style='color: #F59E0B;'>★</span>"] * stars_cnt)
            + "".join(["<span style='color: #334155;'>★</span>"] * (5 - stars_cnt))
        )
        star_lbl = QLabel(stars_html)
        star_lbl.setStyleSheet("font-size: 30px; background: transparent;")
        star_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(star_lbl)

        return frame

    def _build_scroll(self, result, main_fb, tips, theme):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background-color: {C['bg']}; }}
            QScrollBar:vertical {{ background: {C['card']}; width: 5px; border-radius: 2px; }}
            QScrollBar::handle:vertical {{ background: {C['border']}; border-radius: 2px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        content = QWidget()
        content.setStyleSheet(f"background-color: {C['bg']};")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(14)

        lay.addWidget(self._build_stats(result))
        lay.addWidget(self._build_feedback(main_fb, tips))
        lay.addStretch()

        scroll.setWidget(content)
        return scroll

    def _build_stats(self, result):
        panel = QFrame()
        panel.setStyleSheet(f"""
            QFrame {{
                background-color: {C['card']};
                border-radius: 14px;
                border: 1px solid {C['border']};
            }}
        """)
        add_shadow(panel)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(14)

        title = QLabel("Chi tiet ket qua")
        title.setStyleSheet(
            f"color: {C['text_muted']}; font-size: 11px; font-weight: 700;"
            f" font-family: {FONT}; background: transparent; border: none; letter-spacing: 1px;"
        )
        lay.addWidget(title)

        # Only show metrics that have real values (> 0)
        metrics = [
            ("Chinh xac cao do", result.get("pitch_intonation", 0), C["blue"], C["primary"]),
            ("Do on dinh giong", result.get("pitch_stability", 0), C["creative"], C["pink"]),
            ("Nhat quan am luong", result.get("volume_consistency", 0), C["accent"], C["pink"]),
            ("Nhip dieu", result.get("rhythm_score", 0), C["green"], C["teal"]),
            ("Dung tong", result.get("key_conformity", 0), C["orange"], C["accent"]),
        ]

        for name, val, clr1, clr2 in metrics:
            if val > 0:
                self._add_metric(lay, name, val, clr1, clr2)

        # Always show voiced ratio as info
        voiced = result.get("voiced_ratio", 0)
        if voiced > 0:
            self._add_metric(lay, "Giong ro rang", voiced, C["teal"], C["green"])

        return panel

    def _add_metric(self, parent_layout, name, val, clr1, clr2):
        row = QHBoxLayout()
        row.setSpacing(10)

        name_lbl = QLabel(name)
        name_lbl.setFixedWidth(155)
        name_lbl.setStyleSheet(
            f"color: {C['text']}; font-size: 13px; font-weight: 600;"
            f" background: transparent; border: none;"
        )
        row.addWidget(name_lbl)
        row.addWidget(_GradientBar(val, clr1, clr2))

        val_lbl = QLabel(f"{val:.0f}%")
        val_lbl.setFixedWidth(42)
        val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        val_lbl.setStyleSheet(
            f"color: {clr1}; font-size: 13px; font-weight: 700;"
            f" background: transparent; border: none;"
        )
        row.addWidget(val_lbl)
        parent_layout.addLayout(row)

    def _build_feedback(self, main_fb, tips):
        panel = QFrame()
        panel.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(56, 189, 248, 0.06);
                border-radius: 14px;
                border: 1px solid rgba(56, 189, 248, 0.25);
            }}
        """)
        add_shadow(panel)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        title = QLabel("Nhan xet")
        title.setStyleSheet(
            f"color: {C['primary']}; font-size: 11px; font-weight: 700;"
            f" font-family: {FONT}; background: transparent; border: none; letter-spacing: 1px;"
        )
        lay.addWidget(title)

        main_lbl = QLabel(main_fb)
        main_lbl.setStyleSheet(
            f"color: {C['text']}; font-size: 14px; font-weight: 500;"
            f" font-family: {FONT}; background: transparent; border: none;"
        )
        main_lbl.setWordWrap(True)
        lay.addWidget(main_lbl)

        for tip in tips:
            tip_lbl = QLabel(f"• {tip}")
            tip_lbl.setStyleSheet(
                f"color: {C['text_muted']}; font-size: 13px;"
                f" font-family: {FONT}; background: transparent; border: none;"
            )
            tip_lbl.setWordWrap(True)
            lay.addWidget(tip_lbl)

        return panel

    def _build_footer(self, theme):
        footer = QFrame()
        footer.setStyleSheet(f"background-color: {C['card']}; border-top: 1px solid {C['border']};")
        lay = QHBoxLayout(footer)
        lay.setContentsMargins(20, 12, 20, 12)

        btn = QPushButton("Tiep Tuc Dam Me")
        btn.setStyleSheet(pill_btn_qss(theme, _lighten(theme, 0.1), 15, 18))
        btn.setFixedHeight(46)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self.accept)
        add_shadow(btn, theme, 12, (0, 3))
        lay.addWidget(btn)

        return footer
