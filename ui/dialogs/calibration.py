import backend
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTabWidget, QGridLayout, QWidget, QSpinBox, QSlider,
    QComboBox, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer, QSize, QByteArray
from PySide6.QtGui import QIcon, QPixmap, QPainter

from ui.design_tokens import C, FONT
from ui.components.svg_icons import SVG_SAVE, SVG_SETTINGS, SVG_MUSIC, SVG_WRENCH
from frontend_qt import pill_btn_qss, add_shadow, _lighten, MIDI_CC


class CalibrationWizardDialog(QDialog):
    """
    Calibration Wizard cho Auto-Tune.
    Tab 1 — Scale Type (Major / Minor)
    Tab 2 — Key Root (12 keys)
    Tab 3 — Mode (Fix Méo)

    Luồng: một "live tuner" dùng chung (slider 0-127 + nhích nhanh + auto-sweep)
    gửi MIDI trực tiếp; người dùng canh đúng giá trị trên plugin rồi bấm nút
    "bắt giá trị" ở tab tương ứng. Giá trị bắt = đúng số đang gửi (không off-by-one).

    Caller phải reload SCALE_VALUES sau khi exec() trả về:
        dlg = CalibrationWizardDialog(self)
        dlg.exec()
        SCALE_VALUES = backend.AppConfig.get_scale_values()
    """

    ALL_KEYS  = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    ALL_MODES = ["Fix Méo"]
    BLACK_KEYS = {"C#", "D#", "F#", "G#", "A#"}

    # Auto-sweep: nhãn -> chu kỳ (ms). Càng lớn càng chậm, càng dễ canh.
    SWEEP_SPEEDS = {"Chậm": 450, "Vừa": 280, "Nhanh": 140}

    def __init__(self, parent):
        super().__init__(parent)
        self._dashboard = parent
        self.setWindowTitle("Cân chỉnh Auto-Tune")
        self.setMinimumSize(800, 660)
        self.resize(820, 700)
        self.setStyleSheet(self._dialog_qss())

        self._state = {
            "current_value": 0,
            "sweep_timer": None,
            "major_value": None,
            "minor_value": None,
            "key_values": {},
            "mode_values": {},
        }
        self._build_ui()
        self._set_value(0)
        self._refresh_progress()

    @staticmethod
    def _svg_icon(svg_content, color="white", size=18):
        try:
            from PySide6.QtSvg import QSvgRenderer

            svg = svg_content.replace('stroke="white"', f'stroke="{color}"')
            renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
            pix = QPixmap(size, size)
            pix.fill(Qt.transparent)
            painter = QPainter(pix)
            renderer.render(painter)
            painter.end()
            return QIcon(pix)
        except Exception:
            return QIcon()

    @staticmethod
    def _dialog_qss():
        return f"""
            QDialog {{
                background-color: {C['bg']};
                color: {C['text']};
                font-family: {FONT};
            }}
            QWidget {{
                color: {C['text']};
                font-family: {FONT};
            }}
            QFrame#calibrationHeader {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(245, 158, 11, 56),
                    stop:0.55 rgba(30, 41, 59, 245),
                    stop:1 rgba(56, 189, 248, 38));
                border-bottom: 1px solid rgba(148, 163, 184, 45);
            }}
            QFrame#calibrationCard {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(30, 41, 59, 238),
                    stop:1 rgba(15, 23, 42, 226));
                border-radius: 16px;
                border: 1px solid rgba(148, 163, 184, 42);
            }}
            QFrame#calibrationFooter {{
                background-color: rgba(15, 23, 42, 242);
                border-top: 1px solid rgba(148, 163, 184, 45);
            }}
            QLabel#progressChip {{
                background-color: rgba(15, 23, 42, 180);
                border: 1px solid rgba(148, 163, 184, 55);
                border-radius: 11px;
                padding: 3px 12px;
                font-size: 12px;
                font-weight: 700;
            }}
            QTabWidget::pane {{
                border: none;
                background: transparent;
                top: -1px;
            }}
            QTabBar {{
                background: rgba(15, 23, 42, 180);
            }}
            QTabBar::tab {{
                background-color: rgba(30, 41, 59, 165);
                color: {C['text_muted']};
                padding: 8px 22px;
                margin: 8px 4px 4px 0;
                border: 1px solid rgba(51, 65, 85, 150);
                border-radius: 12px;
                font-size: 13px;
                font-weight: 700;
                min-height: 28px;
            }}
            QTabBar::tab:first {{
                margin-left: 18px;
            }}
            QTabBar::tab:selected {{
                color: {C['text']};
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(245, 158, 11, 210),
                    stop:1 rgba(56, 189, 248, 185));
                border: 1px solid rgba(251, 191, 36, 150);
            }}
            QTabBar::tab:hover:!selected {{
                color: {C['text']};
                background-color: rgba(51, 65, 85, 210);
                border-color: rgba(148, 163, 184, 80);
            }}
            QComboBox {{
                background-color: {C['bg']}; color: {C['text']};
                border: 1px solid {C['border']}; border-radius: 8px;
                padding: 4px 10px; font-size: 12px; font-weight: 700; font-family: {FONT};
            }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background-color: {C['card']}; color: {C['text']};
                selection-background-color: {C['primary']};
                border: 1px solid {C['border']}; font-size: 12px;
            }}
        """

    # ── Build UI ──────────────────────────────────────────────

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(0)
        lay.setContentsMargins(0, 0, 0, 0)

        lay.addWidget(self._build_header())

        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(22, 16, 22, 0)
        body_lay.setSpacing(12)
        body_lay.addWidget(self._build_tuner())
        body_lay.addWidget(self._build_tabs(), 1)
        lay.addWidget(body, 1)

        lay.addWidget(self._build_bottom_row())

    def _build_header(self):
        header = QFrame()
        header.setObjectName("calibrationHeader")
        header_lay = QVBoxLayout(header)
        header_lay.setContentsMargins(24, 14, 24, 12)
        header_lay.setSpacing(6)

        title = QLabel("Cân chỉnh Plugin Auto-Tune")
        title.setStyleSheet(
            f"font-size: 22px; font-weight: 900; color: {C['text']};"
            f" font-family: {FONT}; background: transparent; border: none;"
        )
        title.setAlignment(Qt.AlignCenter)
        header_lay.addWidget(title)

        subtitle = QLabel("Kéo thanh trượt tới khi plugin hiển thị đúng giá trị, rồi bấm nút bắt tương ứng")
        subtitle.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {C['text_muted']};"
            f" font-family: {FONT}; background: transparent; border: none;"
        )
        subtitle.setAlignment(Qt.AlignCenter)
        header_lay.addWidget(subtitle)

        # ── Progress chips ──
        chip_row = QHBoxLayout()
        chip_row.setSpacing(8)
        chip_row.addStretch()
        self._chip_scale = self._make_chip("Scale")
        self._chip_key   = self._make_chip("Key")
        self._chip_mode  = self._make_chip("Chế độ")
        chip_row.addWidget(self._chip_scale)
        chip_row.addWidget(self._chip_key)
        chip_row.addWidget(self._chip_mode)
        chip_row.addStretch()
        header_lay.addLayout(chip_row)
        return header

    def _make_chip(self, text):
        chip = QLabel(text)
        chip.setObjectName("progressChip")
        chip.setAlignment(Qt.AlignCenter)
        return chip

    def _build_tuner(self):
        frame = QFrame()
        frame.setObjectName("calibrationCard")
        sf = QVBoxLayout(frame)
        sf.setContentsMargins(18, 14, 18, 14)
        sf.setSpacing(12)

        # Big readout: CC + value
        head = QHBoxLayout()
        head.addStretch()
        self._cc_label = QLabel("CC 35")
        self._cc_label.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {C['text_muted']};"
            " font-family: Consolas; background: transparent; border: none;"
        )
        head.addWidget(self._cc_label, 0, Qt.AlignBottom)
        self._value_label = QLabel("0")
        self._value_label.setStyleSheet(
            f"font-size: 40px; font-weight: 900; color: {C['primary']};"
            " font-family: Consolas; background: transparent; border: none;"
        )
        head.addWidget(self._value_label, 0, Qt.AlignVCenter)
        self._value_max = QLabel("/ 127")
        self._value_max.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {C['text_muted']};"
            " font-family: Consolas; background: transparent; border: none;"
        )
        head.addWidget(self._value_max, 0, Qt.AlignBottom)
        head.addStretch()
        sf.addLayout(head)

        # Slider
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, 127)
        self._slider.setValue(0)
        self._slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 10px; border-radius: 5px;
                background-color: rgba(15, 23, 42, 235);
            }}
            QSlider::sub-page:horizontal {{
                height: 10px; border-radius: 5px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {C['orange']}, stop:1 {C['primary']});
            }}
            QSlider::handle:horizontal {{
                width: 20px; height: 20px; margin: -6px 0; border-radius: 10px;
                background: {C['text']};
                border: 2px solid {C['primary']};
            }}
            QSlider::handle:horizontal:hover {{
                border-color: {_lighten(C['primary'], 0.2)};
            }}
        """)
        self._slider.valueChanged.connect(self._set_value)
        sf.addWidget(self._slider)

        # Nudge row: -10 -1 [spin] +1 +10
        nudge = QHBoxLayout()
        nudge.setSpacing(8)
        nudge.addStretch()
        for delta, label in ((-10, "−10"), (-1, "−1")):
            nudge.addWidget(self._make_nudge_btn(delta, label))

        self._spin = QSpinBox()
        self._spin.setRange(0, 127)
        self._spin.setFixedSize(78, 34)
        self._spin.setAlignment(Qt.AlignCenter)
        self._spin.setStyleSheet(f"""
            QSpinBox {{
                background-color: {C['bg']}; color: {C['text']};
                border: 1px solid {C['border']}; border-radius: 8px;
                padding: 2px 6px; font-size: 15px; font-weight: 700; font-family: Consolas;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                background-color: {C['card_hover']}; border: none; width: 16px;
            }}
        """)
        self._spin.valueChanged.connect(self._set_value)
        nudge.addWidget(self._spin)

        for delta, label in ((1, "+1"), (10, "+10")):
            nudge.addWidget(self._make_nudge_btn(delta, label))
        nudge.addStretch()
        sf.addLayout(nudge)

        # Auto-sweep row
        sweep = QHBoxLayout()
        sweep.setSpacing(8)
        sweep.addStretch()

        sweep_lbl = QLabel("Quét tự động:")
        sweep_lbl.setStyleSheet(f"font-size: 12px; color: {C['text_muted']}; font-family: {FONT};")
        sweep.addWidget(sweep_lbl)

        self._speed_combo = QComboBox()
        self._speed_combo.addItems(list(self.SWEEP_SPEEDS.keys()))
        self._speed_combo.setCurrentText("Vừa")
        self._speed_combo.setFixedWidth(96)
        sweep.addWidget(self._speed_combo)

        self._sweep_btn = QPushButton("▶  Bắt đầu")
        self._sweep_btn.setCursor(Qt.PointingHandCursor)
        self._sweep_btn.setFixedHeight(32)
        self._sweep_btn.setStyleSheet(pill_btn_qss(C["card_hover"], _lighten(C["card_hover"], 0.12), 12, 14))
        self._sweep_btn.clicked.connect(self._toggle_sweep)
        sweep.addWidget(self._sweep_btn)
        sweep.addStretch()
        sf.addLayout(sweep)
        return frame

    def _make_nudge_btn(self, delta, label):
        btn = QPushButton(label)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(48, 34)
        btn.setStyleSheet(pill_btn_qss(C["card_hover"], _lighten(C["card_hover"], 0.12), 13, 10))
        btn.clicked.connect(lambda: self._nudge(delta))
        return btn

    def _build_tabs(self):
        self._tabs = QTabWidget()
        self._tabs.setIconSize(QSize(16, 16))
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._tabs.addTab(self._build_scale_tab(), self._svg_icon(SVG_MUSIC, "white", 16), "Kiểu Scale")
        self._tabs.addTab(self._build_key_tab(), self._svg_icon(SVG_SETTINGS, "white", 16), "Nốt gốc (Key)")
        self._tabs.addTab(self._build_mode_tab(), self._svg_icon(SVG_WRENCH, "white", 16), "Chế độ")
        return self._tabs

    def _build_scale_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setSpacing(12)
        lay.setContentsMargins(16, 16, 16, 16)

        instr = QLabel("Canh giá trị tương ứng từng kiểu scale trên plugin rồi bấm nút bên dưới.")
        instr.setStyleSheet(f"font-size: 12px; color: {C['text_muted']}; font-family: {FONT};")
        instr.setWordWrap(True)
        lay.addWidget(instr)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self._major_btn = QPushButton("Bắt Major")
        self._major_btn.setCursor(Qt.PointingHandCursor)
        self._major_btn.setFixedHeight(48)
        self._major_btn.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.12), 14, 16))
        self._major_btn.clicked.connect(self._capture_major)
        add_shadow(self._major_btn, C["green"], 6, (0, 2))
        btn_row.addWidget(self._major_btn)

        self._minor_btn = QPushButton("Bắt Minor")
        self._minor_btn.setCursor(Qt.PointingHandCursor)
        self._minor_btn.setFixedHeight(48)
        self._minor_btn.setStyleSheet(pill_btn_qss(C["orange"], _lighten(C["orange"], 0.12), 14, 16))
        self._minor_btn.clicked.connect(self._capture_minor)
        add_shadow(self._minor_btn, C["orange"], 6, (0, 2))
        btn_row.addWidget(self._minor_btn)
        lay.addLayout(btn_row)

        result_frame = QFrame()
        result_frame.setStyleSheet(f"background-color: {C['bg']}; border-radius: 10px;")
        rf_lay = QHBoxLayout(result_frame)
        rf_lay.setContentsMargins(14, 12, 14, 12)
        self._major_result = QLabel("Major: ---")
        self._major_result.setStyleSheet(self._scale_result_qss(C["green"], filled=False))
        self._major_result.setAlignment(Qt.AlignCenter)
        rf_lay.addWidget(self._major_result)
        self._minor_result = QLabel("Minor: ---")
        self._minor_result.setStyleSheet(self._scale_result_qss(C["orange"], filled=False))
        self._minor_result.setAlignment(Qt.AlignCenter)
        rf_lay.addWidget(self._minor_result)
        lay.addWidget(result_frame)

        lay.addStretch()
        return tab

    def _build_key_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setSpacing(10)
        lay.setContentsMargins(16, 16, 16, 16)

        instr = QLabel("Canh giá trị từng nốt trên plugin rồi bấm phím tương ứng để bắt.")
        instr.setStyleSheet(f"font-size: 12px; color: {C['text_muted']}; font-family: {FONT};")
        instr.setWordWrap(True)
        lay.addWidget(instr)

        grid = QGridLayout()
        grid.setSpacing(8)
        self._key_buttons = {}

        for idx, key_name in enumerate(self.ALL_KEYS):
            btn_color = C["deep_purple"] if key_name in self.BLACK_KEYS else C["primary"]
            kbtn = QPushButton(f"{key_name}\n—")
            kbtn.setCursor(Qt.PointingHandCursor)
            kbtn.setFixedHeight(54)
            kbtn.setStyleSheet(self._key_btn_qss(btn_color, captured=False))
            kbtn.clicked.connect(self._make_key_capture(key_name))
            grid.addWidget(kbtn, idx // 4, idx % 4)
            self._key_buttons[key_name] = kbtn

        lay.addLayout(grid)
        self._key_counter = QLabel("Đã ghi nhận: 0 / 12 phím")
        self._key_counter.setStyleSheet(f"font-size: 12px; color: {C['text_muted']}; font-family: {FONT};")
        self._key_counter.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._key_counter)
        lay.addStretch()
        return tab

    def _build_mode_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setSpacing(12)
        lay.setContentsMargins(16, 16, 16, 16)

        instr = QLabel("Canh giá trị từng chế độ trên plugin rồi bấm nút tương ứng để bắt.")
        instr.setStyleSheet(f"font-size: 12px; color: {C['text_muted']}; font-family: {FONT};")
        instr.setWordWrap(True)
        lay.addWidget(instr)

        self._mode_buttons = {}
        for m_name in self.ALL_MODES:
            mbtn = QPushButton(f"Bắt: {m_name}  —")
            mbtn.setCursor(Qt.PointingHandCursor)
            mbtn.setFixedHeight(46)
            mbtn.setStyleSheet(pill_btn_qss(C["primary"], _lighten(C["primary"], 0.12), 14, 14))
            mbtn.clicked.connect(self._make_mode_capture(m_name))
            lay.addWidget(mbtn)
            self._mode_buttons[m_name] = mbtn

        lay.addStretch()
        return tab

    def _build_bottom_row(self):
        footer = QFrame()
        footer.setObjectName("calibrationFooter")
        row = QHBoxLayout(footer)
        row.setContentsMargins(20, 12, 20, 12)
        row.setSpacing(10)

        self._save_btn = QPushButton("Lưu tất cả")
        self._save_btn.setIcon(self._svg_icon(SVG_SAVE, "white", 17))
        self._save_btn.setIconSize(QSize(17, 17))
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.setFixedSize(150, 40)
        self._save_btn.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.1), 13, 18))
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save_calibration)
        add_shadow(self._save_btn, C["green"], 8, (0, 2))

        close_btn = QPushButton("Đóng")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedSize(96, 40)
        close_btn.setStyleSheet(pill_btn_qss(C["card_hover"], _lighten(C["card_hover"], 0.1), 13, 18))
        close_btn.clicked.connect(self.close)

        row.addStretch()
        row.addWidget(close_btn)
        row.addWidget(self._save_btn)
        return footer

    # ── Value control (shared live tuner) ─────────────────────

    def _active_cc(self):
        # Đọc CC trực tiếp từ AppConfig (live) thay vì snapshot MIDI_CC lúc import —
        # đảm bảo tab calibration sweep ĐÚNG CC mà runtime thực sự gửi.
        try:
            cc_map = backend.AppConfig.get_midi_cc()
        except Exception:
            cc_map = MIDI_CC
        idx = self._tabs.currentIndex() if hasattr(self, "_tabs") else 0
        if idx == 1:
            return int(cc_map.get("key_root", 33))
        if idx == 2:
            # Tab "Chế độ" chỉ có Fix Méo → phải sweep CC fix_meo (runtime
            # _on_fix_meo gửi cc_map["fix_meo"]), KHÔNG dùng CC "mode" (live-tuner).
            return int(cc_map.get("fix_meo", 41))
        return int(cc_map.get("scale_type", 35))

    def _set_value(self, v):
        """Single source of truth: clamp, sync widgets, push MIDI live."""
        v = max(0, min(127, int(v)))
        self._state["current_value"] = v
        for w in (self._slider, self._spin):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)
        cc = self._active_cc()
        self._cc_label.setText(f"CC {cc}")
        self._value_label.setText(str(v))
        try:
            self._dashboard.engine.send_midi(cc, v)
        except Exception:
            pass

    def _nudge(self, delta):
        self._set_value(self._state["current_value"] + delta)

    # ── Auto-sweep ────────────────────────────────────────────

    def _toggle_sweep(self):
        if self._state["sweep_timer"]:
            self._stop_sweep()
        else:
            self._start_sweep()

    def _start_sweep(self):
        if self._state["current_value"] >= 127:
            self._set_value(0)
        interval = self.SWEEP_SPEEDS.get(self._speed_combo.currentText(), 280)
        timer = QTimer(self)
        timer.timeout.connect(self._sweep_step)
        timer.start(interval)
        self._state["sweep_timer"] = timer
        self._speed_combo.setEnabled(False)
        self._sweep_btn.setText("⏸  Dừng")
        self._sweep_btn.setStyleSheet(pill_btn_qss(C["orange"], _lighten(C["orange"], 0.12), 12, 14))

    def _stop_sweep(self):
        t = self._state["sweep_timer"]
        if t:
            t.stop()
            self._state["sweep_timer"] = None
        self._speed_combo.setEnabled(True)
        self._sweep_btn.setText("▶  Bắt đầu")
        self._sweep_btn.setStyleSheet(pill_btn_qss(C["card_hover"], _lighten(C["card_hover"], 0.12), 12, 14))

    def _sweep_step(self):
        v = self._state["current_value"] + 1
        if v > 127:
            self._set_value(127)
            self._stop_sweep()
            return
        self._set_value(v)

    def _on_tab_changed(self, _index):
        # Push current value on the newly active CC so plugin stays in sync.
        self._set_value(self._state["current_value"])

    def closeEvent(self, event):
        self._stop_sweep()
        event.accept()

    # ── Capture ───────────────────────────────────────────────

    def _check_save_enabled(self):
        s = self._state
        ok = (
            s["major_value"] is not None
            or s["minor_value"] is not None
            or bool(s["key_values"])
            or bool(s["mode_values"])
        )
        self._save_btn.setEnabled(ok)

    def _capture_major(self):
        v = self._state["current_value"]
        self._state["major_value"] = v
        self._major_result.setText(f"Major: {v}")
        self._major_result.setStyleSheet(self._scale_result_qss(C["green"], filled=True))
        self._after_capture()

    def _capture_minor(self):
        v = self._state["current_value"]
        self._state["minor_value"] = v
        self._minor_result.setText(f"Minor: {v}")
        self._minor_result.setStyleSheet(self._scale_result_qss(C["orange"], filled=True))
        self._after_capture()

    def _make_key_capture(self, key_name):
        def _capture():
            v = self._state["current_value"]
            self._state["key_values"][key_name] = v
            self._key_buttons[key_name].setText(f"{key_name}\n{v}")
            self._key_buttons[key_name].setStyleSheet(self._key_btn_qss(C["green"], captured=True))
            n = len(self._state["key_values"])
            self._key_counter.setText(f"Đã ghi nhận: {n} / 12 phím")
            self._key_counter.setStyleSheet(
                f"font-size: 12px; color: {C['green'] if n == 12 else C['text_muted']};"
                f" font-weight: {'bold' if n == 12 else 'normal'}; font-family: {FONT};"
            )
            self._after_capture()
        return _capture

    def _make_mode_capture(self, m_name):
        def _capture():
            v = self._state["current_value"]
            self._state["mode_values"][m_name] = v
            self._mode_buttons[m_name].setText(f"Bắt: {m_name}  →  {v}")
            self._mode_buttons[m_name].setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.12), 14, 14))
            self._after_capture()
        return _capture

    def _after_capture(self):
        self._check_save_enabled()
        self._refresh_progress()

    # ── Progress indicators ───────────────────────────────────

    def _refresh_progress(self):
        s = self._state
        scale_done = (s["major_value"] is not None) + (s["minor_value"] is not None)
        n_key = len(s["key_values"])
        n_mode = len(s["mode_values"])

        self._set_chip(self._chip_scale, "Scale", scale_done, 2)
        self._set_chip(self._chip_key, "Key", n_key, 12)
        self._set_chip(self._chip_mode, "Chế độ", n_mode, len(self.ALL_MODES))

        self._tabs.setTabText(0, self._tab_label("Kiểu Scale", scale_done, 2))
        self._tabs.setTabText(1, self._tab_label("Nốt gốc", n_key, 12))
        self._tabs.setTabText(2, self._tab_label("Chế độ", n_mode, len(self.ALL_MODES)))

    @staticmethod
    def _tab_label(name, done, total):
        if done >= total:
            return f"{name} ✓"
        if done == 0:
            return name
        return f"{name} ({done}/{total})"

    def _set_chip(self, chip, name, done, total):
        complete = done >= total
        chip.setText(f"{name} ✓" if complete else f"{name} {done}/{total}")
        if complete:
            chip.setStyleSheet(
                f"QLabel#progressChip {{ background-color: rgba(16,185,129,0.18);"
                f" border: 1px solid {C['green']}; border-radius: 11px; padding: 3px 12px;"
                f" font-size: 12px; font-weight: 700; color: {C['green']}; }}"
            )
        else:
            color = C["text_muted"] if done == 0 else C["text"]
            chip.setStyleSheet(
                f"QLabel#progressChip {{ background-color: rgba(15,23,42,180);"
                f" border: 1px solid rgba(148,163,184,55); border-radius: 11px; padding: 3px 12px;"
                f" font-size: 12px; font-weight: 700; color: {color}; }}"
            )

    # ── Save ──────────────────────────────────────────────────

    def _validate_before_save(self):
        """Kiểm tra dữ liệu cân chỉnh trước khi lưu.

        Trả về True nếu được phép tiếp tục lưu, False nếu user hủy.
        Một số cảnh báo cho phép user xác nhận tiếp tục (cố ý), một số chặn cứng
        (giá trị ngoài [0,127]).
        """
        s = self._state

        # 1. Validate dải [0,127] — chặn cứng nếu sai (không nên xảy ra vì widget
        #    đã clamp, nhưng vẫn phòng thủ).
        all_vals = []
        if s["major_value"] is not None:
            all_vals.append(("Major", s["major_value"]))
        if s["minor_value"] is not None:
            all_vals.append(("Minor", s["minor_value"]))
        all_vals += list(s["key_values"].items())
        all_vals += list(s["mode_values"].items())
        bad = [name for name, v in all_vals if not (0 <= int(v) <= 127)]
        if bad:
            QMessageBox.critical(
                self, "Giá trị không hợp lệ",
                "Giá trị phải nằm trong khoảng 0–127. Các mục lỗi: "
                + ", ".join(bad),
            )
            return False

        # 2. Cảnh báo nếu thiếu key (chưa bắt đủ 12) — hỏi lưu phần đã bắt không.
        n_key = len(s["key_values"])
        if 0 < n_key < 12:
            missing = [k for k in self.ALL_KEYS if k not in s["key_values"]]
            ret = QMessageBox.question(
                self, "Chưa bắt đủ 12 phím",
                f"Mới bắt {n_key}/12 phím. Các phím chưa bắt sẽ giữ giá trị cũ "
                f"(map có thể nửa cũ nửa mới):\n{', '.join(missing)}\n\n"
                "Vẫn lưu phần đã bắt?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if ret != QMessageBox.Yes:
                return False

        # 3. Cảnh báo nếu major == minor (reverse-lookup scale luôn ra Major).
        if (s["major_value"] is not None and s["minor_value"] is not None
                and s["major_value"] == s["minor_value"]):
            ret = QMessageBox.question(
                self, "Major trùng Minor",
                f"Major và Minor cùng giá trị ({s['major_value']}). Khi hiển thị "
                "ngược lại MIDI→scale sẽ luôn ra Major.\n\nVẫn tiếp tục?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if ret != QMessageBox.Yes:
                return False

        # 4. Cảnh báo nếu key_values không tăng đơn điệu theo cao độ — reverse-lookup
        #    MIDI→key giả định map tăng dần. Chỉ xét các phím đã bắt, theo thứ tự
        #    cao độ ALL_KEYS. Cho phép xác nhận tiếp tục nếu cố ý.
        ordered = [s["key_values"][k] for k in self.ALL_KEYS if k in s["key_values"]]
        non_monotonic = any(b <= a for a, b in zip(ordered, ordered[1:]))
        if non_monotonic:
            ret = QMessageBox.question(
                self, "Giá trị phím không tăng dần",
                "Giá trị các phím không tăng dần theo cao độ. Việc hiển thị ngược "
                "lại MIDI→nốt (giả định map tăng dần) có thể sai.\n\nVẫn lưu?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if ret != QMessageBox.Yes:
                return False

        return True

    def _save_calibration(self):
        self._stop_sweep()
        s = self._state

        if not self._validate_before_save():
            return

        maps = {}

        if s["major_value"] is not None and s["minor_value"] is not None:
            maj, mno = s["major_value"], s["minor_value"]
            maps["scale_values"] = {"major": maj, "minor": mno}
            maps["scale_midi_map"] = {"Major": maj, "Minor": mno}

        if s["key_values"]:
            enharmonics = {
                "C#": "Db", "Db": "C#", "D#": "Eb", "Eb": "D#",
                "F#": "Gb", "Gb": "F#", "G#": "Ab", "Ab": "G#",
                "A#": "Bb", "Bb": "A#",
            }
            current_map = dict(backend.AppConfig.get_key_midi_map())
            for key_name, midi_val in s["key_values"].items():
                current_map[key_name] = midi_val
                if key_name in enharmonics:
                    current_map[enharmonics[key_name]] = midi_val
            maps["key_midi_map"] = current_map

        if s["mode_values"]:
            maps["mode_midi_map"] = s["mode_values"]

        # Ghi vào DATA_DIR (user-writable) qua set_calibration — KHÔNG ghi
        # app_config.json cạnh exe (có thể read-only ở Program Files).
        ok = backend.AppConfig.set_calibration(**maps) if maps else False

        if ok:
            self._dashboard._show_message("Đã lưu cân chỉnh")
            self.close()
        else:
            QMessageBox.critical(
                self, "Lưu thất bại",
                "Không lưu được cân chỉnh — kiểm tra quyền ghi (thư mục dữ liệu "
                "có thể bị khóa hoặc đầy).",
            )

    # ── Style helpers ─────────────────────────────────────────

    @staticmethod
    def _scale_result_qss(color, filled):
        bg = ""
        if filled:
            rgba = {C["green"]: "16,185,129", C["orange"]: "245,158,11"}.get(color, "148,163,184")
            bg = f" background-color: rgba({rgba},0.15); border-radius: 6px; padding: 6px;"
        return (
            f"font-size: 16px; font-weight: bold; color: {color};"
            f" font-family: Consolas;{bg}"
        )

    @staticmethod
    def _key_btn_qss(color, captured):
        return f"""
            QPushButton {{
                background-color: {color};
                color: white; border: none; border-radius: 10px;
                font-size: 13px; font-weight: 800; font-family: {FONT};
            }}
            QPushButton:hover {{ background-color: {_lighten(color, 0.12)}; }}
        """
