"""
Quang Luu Studio — Layout Test (Concept A)
4 side-by-side panels: MIXER | TONE | MODE | TOOLS
Record button inside Waveform Hero transport bar.
"""
import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QGridLayout, QLabel, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette

# ── Import widgets ──
from ui.design_tokens import C, SP, FONT
from ui.components.painter_fader import PainterFader
from ui.components.painter_button import PainterButton
from ui.components.painter_knob import PainterKnob
from ui.components.painter_panel import GlassPanel
from ui.components.painter_record import PainterRecordButton
from ui.components.painter_header import PaintedHeaderBar, PaintedMidiDot
from ui.components.marquee import SmoothMarqueeLabel
from ui.components.waveform_hero import WaveformHeroPanel
from ui.components.painter_hslider import PainterHSlider
from ui.components.hmixer_channel import HMixerChannel

DARK_BG = "#0A0E1E"


class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Concept A — Quang Lưu Studio")
        self.setMinimumSize(1100, 680)
        self.resize(1100, 680)

        central = QWidget()
        self.setCentralWidget(central)
        central.setStyleSheet(f"background-color: {DARK_BG};")

        ml = QVBoxLayout(central)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)

        # ── Header ──
        header = PaintedHeaderBar(height=52)
        hl = header.layout()

        midi_dot = PaintedMidiDot()
        midi_dot.set_connected(True, True)
        hl.addWidget(midi_dot)
        hl.addSpacing(8)

        marquee = SmoothMarqueeLabel(
            "♪ Quang Lưu Studio — Performance Stage ♪",
            color="#fc8403"
        )
        marquee.setFixedHeight(38)
        hl.addWidget(marquee, 1)
        hl.addStretch()

        autokey_dot = PaintedMidiDot()
        autokey_dot.set_connected(True, False)
        hl.addWidget(autokey_dot)

        ml.addWidget(header)

        # ── Body ──
        body = QWidget()
        body.setStyleSheet(f"background-color: {DARK_BG};")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(SP.SM, SP.XS, SP.SM, SP.XS)
        bl.setSpacing(SP.XS)

        # 1. WAVEFORM HERO (60%)
        self.waveform = WaveformHeroPanel()
        self.waveform.set_song_info("Tình Yêu Màu Nắng", "Am", "Minor", 120)
        self.waveform.set_score(85)
        self.waveform.set_midi_status(True)
        self.waveform.record_clicked.connect(self._toggle_record)
        self.waveform.autotune_toggled.connect(
            lambda on: print(f"  Auto-Tune: {'ON' if on else 'OFF'}")
        )
        bl.addWidget(self.waveform, 60)

        # 2. FOUR PANELS (40%)
        panels = QHBoxLayout()
        panels.setSpacing(SP.XS)

        # Panel: MIXER
        mixer = GlassPanel("MIXER")
        for icon, label, color, default in [
            ("♪", "Nhạc",    C["teal"],         70),
            ("☉", "Mic",     C["orange"],       50),
            ("≡", "Vang",    C["accent"],       30),
            ("☖", "B.Track", C["light_purple"], 70),
        ]:
            ch = HMixerChannel(icon=icon, label=label, color=color,
                               cc_key=f"mix_{label}", default=default)
            ch.slider.valueChanged.connect(
                lambda v, n=label, c=color: print(f"  {n}: {v}")
            )
            mixer.body_layout.addWidget(ch)
        mixer.body_layout.addStretch()
        panels.addWidget(mixer, 25)

        # Panel: TONE
        tone = GlassPanel("TONE")
        tone_row = QHBoxLayout()
        tone_row.setSpacing(SP.SM)
        for name, color in [("Tone Nhạc", C["teal"]), ("Tone Giọng", C["accent"])]:
            kw = QWidget()
            kvl = QVBoxLayout(kw)
            kvl.setContentsMargins(0, 2, 0, 2)
            kvl.setAlignment(Qt.AlignCenter)
            knob = PainterKnob(label=name, minimum=-12, maximum=12,
                               value=0, color=color, size=56)
            kvl.addWidget(knob, 0, Qt.AlignCenter)
            lbl = QLabel(name)
            lbl.setStyleSheet(f"font-size:10px; color:{C['text_muted']}; font-weight:600; background:transparent;")
            lbl.setAlignment(Qt.AlignCenter)
            kvl.addWidget(lbl)
            val = QLabel("+0")
            val.setStyleSheet(f"font-size:11px; font-weight:700; color:{color}; background:transparent;")
            val.setAlignment(Qt.AlignCenter)
            kvl.addWidget(val)
            knob.valueChanged.connect(lambda v, l=val: l.setText(f"{v:+d}"))
            tone_row.addWidget(kw)
        tone.body_layout.addLayout(tone_row)
        tone.body_layout.addStretch()
        panels.addWidget(tone, 25)

        # Panel: MODE
        mode = GlassPanel("MODE")
        mode_lbl = QLabel("Mode")
        mode_lbl.setStyleSheet(f"font-size:10px; font-weight:700; color:{C['text_muted']}; background:transparent;")
        mode_lbl.setAlignment(Qt.AlignCenter)
        mode.body_layout.addWidget(mode_lbl)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(3)
        for name, color in [("Dân Ca", C["accent"]), ("Lofi", C["light_purple"]),
                             ("Remix", C["blue"]), ("Đa Thể", C["teal"])]:
            btn = PainterButton(name, color=color, height=26, radius=8, font_size=9)
            btn.clicked.connect(lambda n=name: print(f"  Mode: {n}"))
            mode_row.addWidget(btn)
        mode.body_layout.addLayout(mode_row)

        sfx_lbl = QLabel("SFX")
        sfx_lbl.setStyleSheet(f"font-size:10px; font-weight:700; color:{C['text_muted']}; background:transparent;")
        sfx_lbl.setAlignment(Qt.AlignCenter)
        mode.body_layout.addWidget(sfx_lbl)

        sfx_row = QHBoxLayout()
        sfx_row.setSpacing(3)
        for icon, color in [("😂", C["orange"]), ("👏", C["teal"]), ("🎉", C["pink"])]:
            btn = PainterButton(icon, color=color, height=26, radius=8, font_size=14)
            sfx_row.addWidget(btn)
        mode.body_layout.addLayout(sfx_row)
        mode.body_layout.addStretch()
        panels.addWidget(mode, 25)

        # Panel: TOOLS
        tools = GlassPanel("TOOLS")
        tgrid = QGridLayout()
        tgrid.setSpacing(3)
        tool_items = [
            ("Dò Nhanh", C["orange"]), ("Dò Full", C["teal"]),
            ("Auto-Tune", C["pink"]),  ("Fix Méo", C["deep_purple"]),
            ("Chấm điểm", C["light_purple"]), ("💾 Lưu", C["teal"]),
            ("Danh sách", C["orange"]), ("Thư Mục", C["light_purple"]),
        ]
        for i, (name, color) in enumerate(tool_items):
            btn = PainterButton(name, color=color, height=26, radius=8, font_size=9)
            btn.clicked.connect(lambda n=name: print(f"  Tool: {n}"))
            tgrid.addWidget(btn, i // 2, i % 2)
        tools.body_layout.addLayout(tgrid)
        tools.body_layout.addStretch()
        panels.addWidget(tools, 25)

        bl.addLayout(panels, 40)
        ml.addWidget(body, 1)

    def _toggle_record(self):
        rec = not self.waveform._recording
        # waveform already toggled internally — just log
        print(f"  Recording: {'ON' if rec else 'OFF'}")

    def closeEvent(self, event):
        self.waveform.stop()
        super().closeEvent(event)


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
