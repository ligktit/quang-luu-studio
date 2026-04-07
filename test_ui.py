"""
Quang Luu Studio — QPainter Widget Test Harness
Test all custom-painted components in isolation.
"""
import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QGridLayout, QLabel, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette

# ── Import all QPainter widgets ──
from ui.design_tokens import C, SP, FONT
from ui.components.painter_fader import PainterFader
from ui.components.painter_button import PainterButton
from ui.components.painter_knob import PainterKnob
from ui.components.painter_panel import GlassPanel
from ui.components.painter_record import PainterRecordButton
from ui.components.painter_header import PaintedHeaderBar, PaintedMidiDot
from ui.components.marquee import SmoothMarqueeLabel

DARK_BG = "#0F1729"


class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QPainter Widget Test — Quang Lưu Studio")
        self.setMinimumSize(940, 520)
        self.resize(940, 520)

        central = QWidget()
        self.setCentralWidget(central)
        central.setStyleSheet(f"background-color: {DARK_BG};")

        ml = QVBoxLayout(central)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)

        # ── Header ──
        header = PaintedHeaderBar(height=55)
        hl = header.layout()

        midi_dot = PaintedMidiDot()
        midi_dot.set_connected(True, True)
        hl.addWidget(midi_dot)
        hl.addSpacing(8)

        marquee = SmoothMarqueeLabel(
            "♪ Quang Lưu Studio — QPainter Premium Edition ♪",
            color="#fc8403"
        )
        marquee.setFixedHeight(30)
        hl.addWidget(marquee, 1)
        hl.addStretch()

        autokey_dot = PaintedMidiDot()
        autokey_dot.set_connected(True, False)
        hl.addWidget(autokey_dot)

        ml.addWidget(header)

        # ── Body ──
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(12, 8, 12, 8)
        body_layout.setSpacing(12)

        # ── Left: Buttons + Knobs ──
        left = GlassPanel("🎙️ CHỨC NĂNG")
        grid = QGridLayout()
        grid.setSpacing(6)

        colors = [C["orange"], C["teal"], C["pink"],
                  C["deep_purple"], C["green"], C["light_purple"]]
        labels = ["Dò Tone", "Lấy Tone", "Tone Auto",
                  "Fix Méo", "Major", "Chấm điểm"]

        for i, (text, color) in enumerate(zip(labels, colors)):
            btn = PainterButton(text, color=color, height=30, radius=8, font_size=11)
            btn.clicked.connect(lambda t=text: print(f"Clicked: {t}"))
            grid.addWidget(btn, i // 2, i % 2)

        left.body_layout.addLayout(grid)

        # Knobs
        tone_panel = GlassPanel("🎛️ SET TONE")

        for lbl_text, color in [("Tone Nhạc", C["teal"]), ("Tone Giọng", C["accent"])]:
            row_w = QWidget()
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 4, 0, 4)
            lbl = QLabel(lbl_text)
            lbl.setStyleSheet(f"font-size:12px; color:{C['text_muted']}; font-weight:600;")
            lbl.setFixedWidth(75)
            row_l.addWidget(lbl)
            row_l.addStretch()
            knob = PainterKnob(label=lbl_text, minimum=-12, maximum=12,
                               value=0, color=color, size=56)
            knob.valueChanged.connect(lambda v, k=lbl_text: print(f"{k}: {v:+d}"))
            row_l.addWidget(knob)
            row_l.addStretch()
            tone_panel.body_layout.addWidget(row_w)

        left_w = QWidget()
        left_l = QVBoxLayout(left_w)
        left_l.setContentsMargins(0, 0, 0, 0)
        left_l.setSpacing(10)
        left_l.addWidget(left)
        left_l.addWidget(tone_panel)
        left_l.addStretch()

        body_layout.addWidget(left_w, 30)

        # ── Center: Mixer Faders ──
        center = GlassPanel("🎚️ MIXER")
        fader_row = QHBoxLayout()
        fader_row.setSpacing(16)

        fader_configs = [
            ("Nhạc", C["teal"], 70),
            ("Mic", C["orange"], 50),
            ("Vang", C["accent"], 30),
            ("B.Track", C["light_purple"], 70),
        ]

        for name, color, default in fader_configs:
            wrap = QWidget()
            wl = QVBoxLayout(wrap)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.setSpacing(2)
            wl.setAlignment(Qt.AlignHCenter)

            val_lbl = QLabel(str(default))
            val_lbl.setStyleSheet(f"font-size:13px; font-weight:600; color:{color};")
            val_lbl.setAlignment(Qt.AlignCenter)
            wl.addWidget(val_lbl)

            fader = PainterFader(minimum=0, maximum=100,
                                 value=default, color=color)
            fader.setMinimumHeight(140)
            fader.setFixedWidth(50)
            fader.valueChanged.connect(
                lambda v, l=val_lbl: l.setText(str(v))
            )
            wl.addWidget(fader, 1, Qt.AlignHCenter)

            name_lbl = QLabel(name)
            name_lbl.setStyleSheet(f"font-size:10px; color:{C['text_muted']};")
            name_lbl.setAlignment(Qt.AlignCenter)
            wl.addWidget(name_lbl)

            fader_row.addWidget(wrap, 1)

        center.body_layout.addLayout(fader_row)

        center_w = QWidget()
        center_l = QVBoxLayout(center_w)
        center_l.setContentsMargins(0, 0, 0, 0)
        center_l.addWidget(center)
        center_l.addStretch()

        body_layout.addWidget(center_w, 40)

        # ── Right: Mode & SFX ──
        right = GlassPanel("🎹 CHẾ ĐỘ & HIỆU ỨNG")
        rgrid = QGridLayout()
        rgrid.setSpacing(6)

        mode_sfx = [
            ("Dân Ca", C["accent"], "😂 Cười", C["orange"]),
            ("Lofi", C["light_purple"], "👏 Vỗ tay", C["teal"]),
            ("Remix", C["blue"], "🎉 Hò reo", C["pink"]),
        ]
        for row, (mode, mc, sfx, sc) in enumerate(mode_sfx):
            mbtn = PainterButton(mode, color=mc, height=32, radius=8, font_size=11)
            rgrid.addWidget(mbtn, row, 0)
            sbtn = PainterButton(sfx, color=sc, height=32, radius=8, font_size=11)
            rgrid.addWidget(sbtn, row, 1)

        right.body_layout.addLayout(rgrid)

        right_w = QWidget()
        right_l = QVBoxLayout(right_w)
        right_l.setContentsMargins(0, 0, 0, 0)
        right_l.addWidget(right)
        right_l.addStretch()

        body_layout.addWidget(right_w, 30)

        ml.addWidget(body, 1)

        # ── Bottom Bar ──
        bottom = QWidget()
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(20, 6, 20, 12)

        bar = QFrame()
        bar.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(30, 41, 59, 230);
                border-radius: 26px;
                border: 1px solid rgba(51, 65, 85, 0.4);
            }}
        """)
        bar_l = QHBoxLayout(bar)
        bar_l.setContentsMargins(12, 5, 12, 5)

        save_btn = PainterButton("💾 Lưu", color=C["teal"], height=36, radius=18, font_size=12)
        list_btn = PainterButton("📋 Danh sách", color=C["orange"], height=36, radius=18, font_size=12)
        bar_l.addWidget(save_btn)
        bar_l.addWidget(list_btn)
        bar_l.addStretch()

        rec_btn = PainterRecordButton()
        rec_btn.clicked.connect(lambda: (
            rec_btn.set_recording(not rec_btn._recording),
            print(f"Recording: {rec_btn._recording}")
        ))
        bar_l.addWidget(rec_btn)

        bar_l.addStretch()

        toggle_btn = PainterButton("Ẩn/Hiện SO", color=C["pink"], height=36, radius=18, font_size=12)
        folder_btn = PainterButton("Thư Mục", color=C["light_purple"], height=36, radius=18, font_size=12)
        bar_l.addWidget(toggle_btn)
        bar_l.addWidget(folder_btn)

        bl.addWidget(bar)
        ml.addWidget(bottom)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(DARK_BG))
    pal.setColor(QPalette.WindowText, QColor("#E2E8F0"))
    pal.setColor(QPalette.Base, QColor("#1E293B"))
    pal.setColor(QPalette.Button, QColor("#334155"))
    pal.setColor(QPalette.ButtonText, QColor("#E2E8F0"))
    pal.setColor(QPalette.Highlight, QColor("#38BDF8"))
    app.setPalette(pal)

    win = TestWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()