"""
Quang Lưu Studio — Bảng tiến bộ luyện hát (Premium "progress").

Hiển thị lịch sử chấm điểm: tổng số lần, điểm trung bình, đường biểu đồ điểm
overall theo thời gian, và xu hướng pitch/rhythm/tone.

Biểu đồ: ưu tiên QtCharts nếu import được; nếu không có (ImportError) → fallback
vẽ line chart đơn giản bằng QPainter trên một widget custom.

Style đồng bộ với ui/dialogs/scoring_report.py (dùng design_tokens).
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QScrollArea, QWidget, QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QLinearGradient

from ui.design_tokens import C, FONT, lighten, scrollarea_qss

from core.score_history import ScoreHistory


# ── Helpers (tự chứa, không phụ thuộc frontend_qt) ───────────────

def _pill_btn_qss(color: str, radius: int = 14, size: int = 14) -> str:
    hover = lighten(color, 0.12)
    return f"""
        QPushButton {{
            background-color: {color}; color: #0F172A;
            border: none; border-radius: {radius}px;
            padding: 10px 18px; font-size: {size}px; font-weight: 700;
            font-family: {FONT};
        }}
        QPushButton:hover {{ background-color: {hover}; }}
    """.strip()


def _add_shadow(widget, color="#000000", blur=20, offset=(0, 4)):
    try:
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(blur)
        shadow.setColor(QColor(color))
        shadow.setOffset(*offset)
        widget.setGraphicsEffect(shadow)
    except Exception:
        pass


def _trend_text(trend: str, delta: float) -> tuple:
    """Trả (nhãn, màu) cho xu hướng."""
    if trend == "up":
        return f"▲ Tiến bộ +{abs(delta):.1f} điểm", C["green"]
    if trend == "down":
        return f"▼ Giảm {abs(delta):.1f} điểm", C["accent"]
    return "→ Ổn định", C["text_muted"]


# ── Biểu đồ fallback bằng QPainter ───────────────────────────────

class _LineChart(QFrame):
    """Line chart đơn giản vẽ bằng QPainter (fallback khi không có QtCharts).

    values: list các điểm (0..100). Vẽ trục, lưới mờ, đường nối + chấm.
    """
    def __init__(self, values, color_start, color_end, parent=None):
        super().__init__(parent)
        self._values = [float(v) for v in values]
        self._c0 = color_start
        self._c1 = color_end
        self.setMinimumHeight(220)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        pad_l, pad_r, pad_t, pad_b = 38, 14, 16, 24
        plot_w = max(1, w - pad_l - pad_r)
        plot_h = max(1, h - pad_t - pad_b)

        # nền
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(C["bg"]))
        p.drawRoundedRect(0, 0, w, h, 10, 10)

        # lưới ngang + nhãn 0/50/100
        grid_pen = QPen(QColor(C["border"]))
        grid_pen.setWidth(1)
        p.setPen(grid_pen)
        for frac, lbl in ((0.0, "100"), (0.5, "50"), (1.0, "0")):
            y = pad_t + plot_h * frac
            p.drawLine(int(pad_l), int(y), int(w - pad_r), int(y))
            p.setPen(QColor(C["text_muted"]))
            p.drawText(2, int(y) + 4, lbl)
            p.setPen(grid_pen)

        vals = self._values
        if not vals:
            return

        def _xy(i, v):
            x = pad_l + (plot_w * (i / (len(vals) - 1)) if len(vals) > 1 else plot_w / 2)
            y = pad_t + plot_h * (1.0 - max(0.0, min(100.0, v)) / 100.0)
            return QPointF(x, y)

        # vùng tô gradient dưới đường
        area = QPainterPath()
        area.moveTo(QPointF(pad_l, pad_t + plot_h))
        for i, v in enumerate(vals):
            area.lineTo(_xy(i, v))
        area.lineTo(QPointF(pad_l + plot_w, pad_t + plot_h))
        area.closeSubpath()
        grad = QLinearGradient(0, pad_t, 0, pad_t + plot_h)
        c0 = QColor(self._c0); c0.setAlpha(70)
        c1 = QColor(self._c0); c1.setAlpha(0)
        grad.setColorAt(0.0, c0)
        grad.setColorAt(1.0, c1)
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawPath(area)

        # đường nối
        line_pen = QPen(QColor(self._c0))
        line_pen.setWidth(2)
        line_pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(line_pen)
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(_xy(0, vals[0]))
        for i in range(1, len(vals)):
            path.lineTo(_xy(i, vals[i]))
        p.drawPath(path)

        # chấm điểm
        p.setBrush(QColor(self._c1))
        p.setPen(QPen(QColor(C["text"]), 1))
        for i, v in enumerate(vals):
            pt = _xy(i, v)
            p.drawEllipse(pt, 3.0, 3.0)


class ProgressDialog(QDialog):
    """Bảng tiến bộ luyện hát — biểu đồ điểm theo thời gian + thống kê."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bảng tiến bộ luyện hát")
        self.setMinimumSize(560, 640)
        self.resize(620, 720)
        self.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────

    def _build_ui(self):
        history = ScoreHistory.load()
        summary = ScoreHistory.summary()

        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        outer.addWidget(self._build_header(summary))

        if not history:
            outer.addWidget(self._build_empty(), 1)
        else:
            outer.addWidget(self._build_scroll(history, summary), 1)

        outer.addWidget(self._build_footer())

    def _build_header(self, summary):
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(30,41,59,255), stop:1 {C['bg']});
                border-bottom: 1px solid rgba(56,189,248,0.2);
            }}
        """)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(24, 18, 24, 14)
        lay.setSpacing(4)

        title = QLabel("📈 BẢNG TIẾN BỘ LUYỆN HÁT")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: 800; color: {C['primary']};"
            f" font-family: {FONT}; background: transparent;"
        )
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)

        if summary["count"] > 0:
            sub = QLabel(
                f"{summary['count']} lần chấm • TB {summary['avg_overall']:.1f}"
                f" • Cao nhất {summary['best']:.1f}"
            )
            sub.setStyleSheet(
                f"font-size: 13px; color: {C['text_muted']};"
                f" font-family: {FONT}; background: transparent;"
            )
            sub.setAlignment(Qt.AlignCenter)
            lay.addWidget(sub)

        return frame

    def _build_empty(self):
        frame = QFrame()
        frame.setStyleSheet(f"background-color: {C['bg']};")
        lay = QVBoxLayout(frame)
        lay.addStretch()
        lbl = QLabel("Chưa có dữ liệu chấm điểm")
        lbl.setStyleSheet(
            f"color: {C['text_muted']}; font-size: 16px; font-weight: 600;"
            f" font-family: {FONT}; background: transparent;"
        )
        lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(lbl)
        hint = QLabel("Hãy chấm điểm vài lần để xem biểu đồ tiến bộ của bạn.")
        hint.setStyleSheet(
            f"color: {C['text_muted']}; font-size: 13px;"
            f" font-family: {FONT}; background: transparent;"
        )
        hint.setAlignment(Qt.AlignCenter)
        lay.addWidget(hint)
        lay.addStretch()
        return frame

    def _build_scroll(self, history, summary):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(scrollarea_qss(6))

        content = QWidget()
        content.setStyleSheet(f"background-color: {C['bg']};")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(14)

        lay.addWidget(self._build_summary_cards(summary))
        lay.addWidget(self._build_chart_panel(history))
        lay.addWidget(self._build_trend_panel(summary))
        lay.addStretch()

        scroll.setWidget(content)
        return scroll

    def _build_summary_cards(self, summary):
        panel = QFrame()
        panel.setStyleSheet(self._card_qss())
        _add_shadow(panel)
        row = QHBoxLayout(panel)
        row.setContentsMargins(16, 14, 16, 14)
        row.setSpacing(12)

        cards = [
            ("Lần gần nhất", f"{summary['latest']:.1f}", C["primary"]),
            ("Trung bình", f"{summary['avg_overall']:.1f}", C["green"]),
            ("Cao nhất", f"{summary['best']:.1f}", C["orange"]),
        ]
        for name, val, clr in cards:
            row.addWidget(self._stat_cell(name, val, clr), 1)
        return panel

    def _stat_cell(self, name, val, clr):
        cell = QWidget()
        cell.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(cell)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        v = QLabel(val)
        v.setStyleSheet(
            f"color: {clr}; font-size: 30px; font-weight: 900;"
            f" font-family: {FONT}; background: transparent; border: none;"
        )
        v.setAlignment(Qt.AlignCenter)
        lay.addWidget(v)
        n = QLabel(name)
        n.setStyleSheet(
            f"color: {C['text_muted']}; font-size: 11px; font-weight: 600;"
            f" font-family: {FONT}; background: transparent; border: none;"
        )
        n.setAlignment(Qt.AlignCenter)
        lay.addWidget(n)
        return cell

    def _build_chart_panel(self, history):
        panel = QFrame()
        panel.setStyleSheet(self._card_qss())
        _add_shadow(panel)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        title = QLabel("ĐIỂM THEO THỜI GIAN")
        title.setStyleSheet(
            f"color: {C['text_muted']}; font-size: 11px; font-weight: 700;"
            f" font-family: {FONT}; background: transparent; border: none; letter-spacing: 1px;"
        )
        lay.addWidget(title)

        overalls = [self._num(e.get("overall")) for e in history]
        lay.addWidget(self._make_chart(overalls))
        return panel

    def _make_chart(self, overalls):
        """Tạo widget biểu đồ — QtCharts nếu có, fallback QPainter."""
        try:
            from PySide6.QtCharts import (
                QChart, QChartView, QLineSeries, QValueAxis,
            )
            series = QLineSeries()
            for i, v in enumerate(overalls):
                series.append(i, v)
            series.setColor(QColor(C["primary"]))

            chart = QChart()
            chart.addSeries(series)
            chart.legend().hide()
            chart.setBackgroundBrush(QColor(C["bg"]))
            chart.setMargins(self._chart_margins())

            axis_x = QValueAxis()
            axis_x.setRange(0, max(1, len(overalls) - 1))
            axis_x.setLabelFormat("%d")
            axis_x.setTitleText("Lần chấm")
            axis_y = QValueAxis()
            axis_y.setRange(0, 100)
            for ax in (axis_x, axis_y):
                ax.setLabelsColor(QColor(C["text_muted"]))
                ax.setTitleBrush(QColor(C["text_muted"]))
                ax.setGridLineColor(QColor(C["border"]))
            chart.addAxis(axis_x, Qt.AlignBottom)
            chart.addAxis(axis_y, Qt.AlignLeft)
            series.attachAxis(axis_x)
            series.attachAxis(axis_y)

            view = QChartView(chart)
            view.setRenderHint(QPainter.Antialiasing)
            view.setMinimumHeight(220)
            view.setStyleSheet(f"background-color: {C['bg']}; border: none;")
            return view
        except ImportError:
            return _LineChart(overalls, C["primary"], C["green"])
        except Exception:
            # Bất kỳ lỗi runtime nào của QtCharts → fallback an toàn.
            return _LineChart(overalls, C["primary"], C["green"])

    def _chart_margins(self):
        from PySide6.QtCore import QMargins
        return QMargins(0, 0, 0, 0)

    def _build_trend_panel(self, summary):
        panel = QFrame()
        panel.setStyleSheet(self._card_qss())
        _add_shadow(panel)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        title = QLabel("XU HƯỚNG")
        title.setStyleSheet(
            f"color: {C['text_muted']}; font-size: 11px; font-weight: 700;"
            f" font-family: {FONT}; background: transparent; border: none; letter-spacing: 1px;"
        )
        lay.addWidget(title)

        txt, clr = _trend_text(summary["trend"], summary["trend_delta"])
        trend_lbl = QLabel(txt)
        trend_lbl.setStyleSheet(
            f"color: {clr}; font-size: 15px; font-weight: 700;"
            f" font-family: {FONT}; background: transparent; border: none;"
        )
        lay.addWidget(trend_lbl)

        # các chỉ số thành phần
        for name, val, clr2 in (
            ("Cao độ (pitch)", summary["avg_pitch"], C["blue"]),
            ("Nhịp điệu (rhythm)", summary["avg_rhythm"], C["green"]),
            ("Đúng tông (tone)", summary["avg_tone"], C["orange"]),
        ):
            row = QHBoxLayout()
            row.setSpacing(8)
            n = QLabel(name)
            n.setStyleSheet(
                f"color: {C['text']}; font-size: 13px; font-weight: 600;"
                f" background: transparent; border: none;"
            )
            row.addWidget(n)
            row.addStretch()
            v = QLabel(f"{val:.0f}%")
            v.setStyleSheet(
                f"color: {clr2}; font-size: 13px; font-weight: 700;"
                f" background: transparent; border: none;"
            )
            row.addWidget(v)
            lay.addLayout(row)

        return panel

    def _build_footer(self):
        footer = QFrame()
        footer.setStyleSheet(f"background-color: {C['card']}; border-top: 1px solid {C['border']};")
        lay = QHBoxLayout(footer)
        lay.setContentsMargins(20, 12, 20, 12)

        btn = QPushButton("Đóng")
        btn.setStyleSheet(_pill_btn_qss(C["primary"], 14, 15))
        btn.setFixedHeight(44)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self.accept)
        _add_shadow(btn, C["primary"], 12, (0, 3))
        lay.addWidget(btn)
        return footer

    # ── tiện ích ─────────────────────────────────────────────

    @staticmethod
    def _card_qss():
        return (
            f"QFrame {{ background-color: {C['card']};"
            f" border-radius: 14px; border: 1px solid {C['border']}; }}"
        )

    @staticmethod
    def _num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0
