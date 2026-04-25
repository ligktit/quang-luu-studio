import backend
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QFrame, QTabWidget, QGridLayout, QWidget,
    QSpinBox,
)
from PySide6.QtCore import Qt, QTimer

from ui.design_tokens import C, FONT
from frontend_qt import pill_btn_qss, add_shadow, _lighten, MIDI_CC


class CalibrationWizardDialog(QDialog):
    """
    Calibration Wizard cho Auto-Tune.
    Tab 1 — Scale Type (Major / Minor)
    Tab 2 — Key Root (12 keys)
    Tab 3 — Mode (Dân Ca, Lofi, Remix, Đa Thể Loại, Fix Méo)

    Caller phải reload SCALE_VALUES sau khi exec() trả về:
        dlg = CalibrationWizardDialog(self)
        dlg.exec()
        SCALE_VALUES = backend.AppConfig.get_scale_values()
    """

    ALL_KEYS  = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    ALL_MODES = ["Dân Ca", "Lofi", "Remix", "Đa Thể Loại", "Fix Méo"]

    def __init__(self, parent):
        super().__init__(parent)
        self._dashboard = parent
        self.setWindowTitle("🎛️ Calibrate Auto-Tune")
        self.setFixedSize(640, 780)
        self.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")

        self._state = {
            "scanning": False,
            "current_value": 0,
            "timer": None,
            "major_value": None,
            "minor_value": None,
            "key_values": {},
            "mode_values": {},
        }
        self._build_ui()

    # ── Build UI ──────────────────────────────────────────────

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(24, 20, 24, 16)

        title = QLabel("🎛️ Calibrate Auto-Tune Plugin")
        title.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {C['orange']}; font-family: {FONT};")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)

        subtitle = QLabel("Quét MIDI CC 0→127, nhấn nút tương ứng khi thấy đúng giá trị trên plugin")
        subtitle.setStyleSheet(f"font-size: 12px; color: {C['text_muted']}; font-family: {FONT};")
        subtitle.setAlignment(Qt.AlignCenter)
        lay.addWidget(subtitle)

        lay.addWidget(self._build_scan_controls())
        lay.addWidget(self._build_tabs(), 1)
        lay.addLayout(self._build_bottom_row())

    def _build_scan_controls(self):
        frame = QFrame()
        frame.setStyleSheet(f"background-color: {C['card']}; border-radius: 12px; border: 1px solid {C['border']};")
        sf = QVBoxLayout(frame)
        sf.setContentsMargins(16, 10, 16, 10)
        sf.setSpacing(8)

        self._value_label = QLabel("CC Value: ---")
        self._value_label.setStyleSheet(f"font-size: 26px; font-weight: bold; color: {C['primary']}; font-family: Consolas;")
        self._value_label.setAlignment(Qt.AlignCenter)
        sf.addWidget(self._value_label)

        self._progress = QProgressBar()
        self._progress.setRange(0, 127)
        self._progress.setValue(0)
        self._progress.setStyleSheet(f"""
            QProgressBar {{
                border: none; background-color: {C['bg']};
                border-radius: 4px; max-height: 8px;
            }}
            QProgressBar::chunk {{ background-color: {C['primary']}; border-radius: 4px; }}
        """)
        sf.addWidget(self._progress)

        row = QHBoxLayout()
        self._start_btn = QPushButton("▶ Bắt đầu quét")
        self._start_btn.setCursor(Qt.PointingHandCursor)
        self._start_btn.setFixedHeight(36)
        self._start_btn.setStyleSheet(pill_btn_qss(C["primary"], _lighten(C["primary"], 0.12), 13, 18))
        add_shadow(self._start_btn, C["primary"], 6, (0, 2))
        self._start_btn.clicked.connect(self._start_scan)
        row.addWidget(self._start_btn)

        self._stop_btn = QPushButton("⏹ Dừng")
        self._stop_btn.setCursor(Qt.PointingHandCursor)
        self._stop_btn.setFixedHeight(36)
        self._stop_btn.setStyleSheet(pill_btn_qss(C["card_hover"], _lighten(C["card_hover"], 0.1), 13, 18))
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop_scan)
        row.addWidget(self._stop_btn)

        reset_btn = QPushButton("↺ Reset 0")
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.setFixedHeight(36)
        reset_btn.setStyleSheet(pill_btn_qss(C["card_hover"], _lighten(C["card_hover"], 0.1), 13, 18))
        reset_btn.clicked.connect(self._reset_scan)
        row.addWidget(reset_btn)

        sf.addLayout(row)
        return frame

    def _build_tabs(self):
        tab_qss = f"""
            QTabWidget::pane {{
                border: 1px solid {C['border']};
                border-radius: 8px;
                background-color: {C['card']};
            }}
            QTabBar::tab {{
                background-color: {C['card_hover']};
                color: {C['text_muted']};
                border: none;
                padding: 8px 20px;
                font-size: 13px; font-weight: 600; font-family: {FONT};
                border-top-left-radius: 8px; border-top-right-radius: 8px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{ background-color: {C['card']}; color: {C['primary']}; border-bottom: 2px solid {C['primary']}; }}
            QTabBar::tab:hover   {{ background-color: {C['card']}; color: {C['text']}; }}
        """
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(tab_qss)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._tabs.addTab(self._build_scale_tab(), "🎵 Scale Type")
        self._tabs.addTab(self._build_key_tab(),   "🎹 Key Root")
        self._tabs.addTab(self._build_mode_tab(),  "🎭 Mode")
        return self._tabs

    def _build_scale_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setSpacing(10)
        lay.setContentsMargins(12, 12, 12, 12)

        instr = QLabel("Quét MIDI hoặc nhập số thủ công (0-127).")
        instr.setStyleSheet(f"font-size: 12px; color: {C['text_muted']}; font-family: {FONT};")
        instr.setWordWrap(True)
        lay.addWidget(instr)

        btn_row = QHBoxLayout()
        self._major_btn = QPushButton("Day la Major")
        self._major_btn.setCursor(Qt.PointingHandCursor)
        self._major_btn.setFixedHeight(44)
        self._major_btn.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.12), 14, 16))
        self._major_btn.setEnabled(False)
        self._major_btn.clicked.connect(self._capture_major)
        add_shadow(self._major_btn, C["green"], 6, (0, 2))
        btn_row.addWidget(self._major_btn)

        self._minor_btn = QPushButton("Day la Minor")
        self._minor_btn.setCursor(Qt.PointingHandCursor)
        self._minor_btn.setFixedHeight(44)
        self._minor_btn.setStyleSheet(pill_btn_qss(C["orange"], _lighten(C["orange"], 0.12), 14, 16))
        self._minor_btn.setEnabled(False)
        self._minor_btn.clicked.connect(self._capture_minor)
        add_shadow(self._minor_btn, C["orange"], 6, (0, 2))
        btn_row.addWidget(self._minor_btn)
        lay.addLayout(btn_row)

        result_frame = QFrame()
        result_frame.setStyleSheet(f"background-color: {C['bg']}; border-radius: 8px; padding: 6px;")
        rf_lay = QHBoxLayout(result_frame)
        rf_lay.setContentsMargins(12, 8, 12, 8)
        self._major_result = QLabel("Major: ---")
        self._major_result.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {C['green']}; font-family: Consolas;")
        self._major_result.setAlignment(Qt.AlignCenter)
        rf_lay.addWidget(self._major_result)
        self._minor_result = QLabel("Minor: ---")
        self._minor_result.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {C['orange']}; font-family: Consolas;")
        self._minor_result.setAlignment(Qt.AlignCenter)
        rf_lay.addWidget(self._minor_result)
        lay.addWidget(result_frame)

        # ── Manual input ──
        manual_lbl = QLabel("Nhap thu cong:")
        manual_lbl.setStyleSheet(f"font-size: 11px; color: {C['text_muted']}; font-family: {FONT};")
        lay.addWidget(manual_lbl)

        mr = QHBoxLayout()
        self._major_spin = self._make_spinbox()
        maj_apply = QPushButton("Set Major")
        maj_apply.setFixedHeight(30)
        maj_apply.setCursor(Qt.PointingHandCursor)
        maj_apply.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.12), 11, 8))
        maj_apply.clicked.connect(lambda: self._manual_set_scale("major"))
        mr.addWidget(self._major_spin)
        mr.addWidget(maj_apply)

        self._minor_spin = self._make_spinbox()
        min_apply = QPushButton("Set Minor")
        min_apply.setFixedHeight(30)
        min_apply.setCursor(Qt.PointingHandCursor)
        min_apply.setStyleSheet(pill_btn_qss(C["orange"], _lighten(C["orange"], 0.12), 11, 8))
        min_apply.clicked.connect(lambda: self._manual_set_scale("minor"))
        mr.addWidget(self._minor_spin)
        mr.addWidget(min_apply)
        lay.addLayout(mr)

        lay.addStretch()
        return tab

    def _build_key_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setSpacing(8)
        lay.setContentsMargins(12, 12, 12, 12)

        instr = QLabel("Quét MIDI hoặc nhập số (0-127) cho từng key.")
        instr.setStyleSheet(f"font-size: 12px; color: {C['text_muted']}; font-family: {FONT};")
        instr.setWordWrap(True)
        lay.addWidget(instr)

        black_keys = {"C#", "D#", "F#", "G#", "A#"}
        grid = QGridLayout()
        grid.setSpacing(4)
        self._key_buttons = {}
        self._key_result_labels = {}
        self._key_spinboxes = {}

        for idx, key_name in enumerate(self.ALL_KEYS):
            btn_color = C["deep_purple"] if key_name in black_keys else C["primary"]
            cell = QWidget()
            cl = QVBoxLayout(cell)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(2)

            kbtn = QPushButton(key_name)
            kbtn.setCursor(Qt.PointingHandCursor)
            kbtn.setFixedHeight(30)
            kbtn.setStyleSheet(pill_btn_qss(btn_color, _lighten(btn_color, 0.12), 12, 6))
            kbtn.setEnabled(False)
            kbtn.clicked.connect(self._make_key_capture(key_name))
            cl.addWidget(kbtn)

            # Manual spinbox row
            spin_row = QHBoxLayout()
            spin_row.setSpacing(2)
            kspin = self._make_spinbox(width=48)
            spin_row.addWidget(kspin)
            kapply = QPushButton("Set")
            kapply.setFixedSize(30, 24)
            kapply.setCursor(Qt.PointingHandCursor)
            kapply.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.12), 9, 2))
            kapply.clicked.connect(self._make_key_manual_set(key_name))
            spin_row.addWidget(kapply)
            cl.addLayout(spin_row)

            klbl = QLabel("---")
            klbl.setStyleSheet(f"font-size: 10px; color: {C['text_muted']}; font-family: Consolas;")
            klbl.setAlignment(Qt.AlignCenter)
            cl.addWidget(klbl)

            grid.addWidget(cell, idx // 4, idx % 4)
            self._key_buttons[key_name] = kbtn
            self._key_result_labels[key_name] = klbl
            self._key_spinboxes[key_name] = kspin

        lay.addLayout(grid)
        self._key_counter = QLabel("Da capture: 0 / 12 keys")
        self._key_counter.setStyleSheet(f"font-size: 12px; color: {C['text_muted']}; font-family: {FONT};")
        self._key_counter.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._key_counter)
        lay.addStretch()
        return tab

    def _build_mode_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setSpacing(10)
        lay.setContentsMargins(12, 12, 12, 12)

        instr = QLabel("Quét MIDI hoặc nhập số (0-127) cho từng mode.")
        instr.setStyleSheet(f"font-size: 12px; color: {C['text_muted']}; font-family: {FONT};")
        instr.setWordWrap(True)
        lay.addWidget(instr)

        grid = QGridLayout()
        grid.setSpacing(6)
        self._mode_buttons = {}
        self._mode_result_labels = {}
        self._mode_spinboxes = {}

        for idx, m_name in enumerate(self.ALL_MODES):
            mbtn = QPushButton(m_name)
            mbtn.setCursor(Qt.PointingHandCursor)
            mbtn.setFixedHeight(38)
            mbtn.setStyleSheet(pill_btn_qss(C["primary"], _lighten(C["primary"], 0.12), 13, 14))
            mbtn.setEnabled(False)
            mbtn.clicked.connect(self._make_mode_capture(m_name))

            # Manual spinbox row
            spin_row = QHBoxLayout()
            mspin = self._make_spinbox(width=60)
            mapply = QPushButton("Set")
            mapply.setFixedSize(36, 26)
            mapply.setCursor(Qt.PointingHandCursor)
            mapply.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.12), 10, 4))
            mapply.clicked.connect(self._make_mode_manual_set(m_name))
            spin_row.addWidget(mspin)
            spin_row.addWidget(mapply)

            mres = QLabel("---")
            mres.setStyleSheet(f"font-size: 12px; color: {C['text_muted']}; font-family: Consolas;")
            mres.setAlignment(Qt.AlignCenter)

            row, col = divmod(idx, 2)
            grid.addWidget(mbtn, row * 3,     col)
            grid.addLayout(spin_row, row * 3 + 1, col)
            grid.addWidget(mres, row * 3 + 2, col)
            self._mode_buttons[m_name] = mbtn
            self._mode_result_labels[m_name] = mres
            self._mode_spinboxes[m_name] = mspin

        lay.addLayout(grid)
        lay.addStretch()
        return tab

    def _build_bottom_row(self):
        row = QHBoxLayout()
        self._save_btn = QPushButton("💾 Lưu tất cả")
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.setFixedHeight(40)
        self._save_btn.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.1), 14, 18))
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save_calibration)
        add_shadow(self._save_btn, C["green"], 8, (0, 2))
        row.addWidget(self._save_btn)

        close_btn = QPushButton("Đóng")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedHeight(40)
        close_btn.setStyleSheet(pill_btn_qss(C["card_hover"], _lighten(C["card_hover"], 0.1), 14, 18))
        close_btn.clicked.connect(self.close)
        row.addWidget(close_btn)
        return row

    # ── Scan logic ────────────────────────────────────────────

    def _get_active_cc(self):
        idx = self._tabs.currentIndex()
        if idx == 0: return int(MIDI_CC.get("scale_type", 35))
        if idx == 1: return int(MIDI_CC.get("key_root", 33))
        return int(MIDI_CC.get("mode", 30))

    def _start_scan(self):
        s = self._state
        s["scanning"] = True
        if s["current_value"] > 127:
            s["current_value"] = 0
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._major_btn.setEnabled(True)
        self._minor_btn.setEnabled(True)
        for b in self._key_buttons.values():
            b.setEnabled(True)
        for b in self._mode_buttons.values():
            b.setEnabled(True)

        timer = QTimer(self)
        timer.timeout.connect(self._step_scan)
        timer.start(300)
        s["timer"] = timer

    def _stop_scan(self):
        s = self._state
        s["scanning"] = False
        if s["timer"]:
            s["timer"].stop()
            s["timer"] = None
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._start_btn.setText("▶ Tiếp tục quét")

    def _reset_scan(self):
        self._stop_scan()
        self._state["current_value"] = 0
        self._value_label.setText("CC Value: ---")
        self._progress.setValue(0)
        self._start_btn.setText("▶ Bắt đầu quét")

    def _step_scan(self):
        s = self._state
        if not s["scanning"]:
            return
        v = s["current_value"]
        if v > 127:
            self._stop_scan()
            self._value_label.setText("✅ Quét xong! (0→127)")
            return
        cc = self._get_active_cc()
        self._dashboard.engine.send_midi(cc, v)
        self._value_label.setText(f"CC {cc}  Value: {v}")
        self._progress.setValue(v)
        s["current_value"] = v + 1

    def _on_tab_changed(self, _index):
        if self._state["scanning"]:
            self._stop_scan()
            self._state["current_value"] = 0
            self._value_label.setText("CC Value: ---")
            self._progress.setValue(0)
            self._start_btn.setText("▶ Bắt đầu quét")

    def closeEvent(self, event):
        self._stop_scan()
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
        v = max(0, self._state["current_value"] - 1)
        self._state["major_value"] = v
        self._major_result.setText(f"Major: {v}")
        self._major_result.setStyleSheet(
            f"font-size: 15px; font-weight: bold; color: {C['green']}; font-family: Consolas;"
            f" background-color: rgba(16,185,129,0.15); border-radius: 6px; padding: 4px;"
        )
        self._check_save_enabled()

    def _capture_minor(self):
        v = max(0, self._state["current_value"] - 1)
        self._state["minor_value"] = v
        self._minor_result.setText(f"Minor: {v}")
        self._minor_result.setStyleSheet(
            f"font-size: 15px; font-weight: bold; color: {C['orange']}; font-family: Consolas;"
            f" background-color: rgba(245,158,11,0.15); border-radius: 6px; padding: 4px;"
        )
        self._check_save_enabled()

    def _make_key_capture(self, key_name):
        def _capture():
            v = max(0, self._state["current_value"] - 1)
            self._state["key_values"][key_name] = v
            self._key_result_labels[key_name].setText(str(v))
            self._key_result_labels[key_name].setStyleSheet(
                f"font-size: 11px; font-weight: bold; color: {C['green']}; font-family: Consolas;"
            )
            self._key_buttons[key_name].setStyleSheet(
                pill_btn_qss(C["green"], _lighten(C["green"], 0.12), 13, 8)
            )
            self._key_buttons[key_name].setText(f"✓ {key_name}")
            n = len(self._state["key_values"])
            self._key_counter.setText(f"Đã capture: {n} / 12 keys")
            if n == 12:
                self._key_counter.setStyleSheet(
                    f"font-size: 12px; color: {C['green']}; font-weight: bold; font-family: {FONT};"
                )
            self._check_save_enabled()
        return _capture

    def _make_mode_capture(self, m_name):
        def _capture():
            v = max(0, self._state["current_value"] - 1)
            self._state["mode_values"][m_name] = v
            self._mode_result_labels[m_name].setText(str(v))
            self._mode_result_labels[m_name].setStyleSheet(
                f"font-size: 14px; font-weight: bold; color: {C['primary']}; font-family: Consolas;"
            )
            self._mode_buttons[m_name].setStyleSheet(
                pill_btn_qss(C["green"], _lighten(C["green"], 0.12), 14, 16)
            )
            self._check_save_enabled()
        return _capture

    # ── Save ──────────────────────────────────────────────────

    def _save_calibration(self):
        self._stop_scan()
        s = self._state

        if s["major_value"] is not None and s["minor_value"] is not None:
            maj, mno = s["major_value"], s["minor_value"]
            backend.AppConfig.update("scale_values",  {"major": maj, "minor": mno})
            backend.AppConfig.update("scale_midi_map", {"Major": maj, "Minor": mno})

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
            backend.AppConfig.update("key_midi_map", current_map)

        if s["mode_values"]:
            backend.AppConfig.update("mode_midi_map", s["mode_values"])

        backend.AppConfig.save()

        parts = []
        if s["major_value"] is not None:
            parts.append(f"Maj={s['major_value']}")
        if s["minor_value"] is not None:
            parts.append(f"Min={s['minor_value']}")
        if s["key_values"]:
            parts.append(f"Keys: {len(s['key_values'])}/12")
        if s["mode_values"]:
            parts.append(f"Modes: {len(s['mode_values'])}/5")

        self._dashboard._show_message("Đã lưu cân chỉnh")
        self.close()

    # ── Helpers ───────────────────────────────────────────────

    def _make_spinbox(self, width=70):
        """Create a styled QSpinBox (0-127) for manual CC input."""
        spin = QSpinBox()
        spin.setRange(0, 127)
        spin.setFixedWidth(width)
        spin.setFixedHeight(28)
        spin.setStyleSheet(f"""
            QSpinBox {{
                background-color: {C['bg']};
                color: {C['text']};
                border: 1px solid {C['border']};
                border-radius: 6px;
                padding: 2px 6px;
                font-size: 13px;
                font-family: Consolas;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                background-color: {C['card_hover']};
                border: none;
                width: 16px;
            }}
        """)
        return spin

    def _manual_set_scale(self, scale_type):
        """Set scale value from manual spinbox input."""
        if scale_type == "major":
            v = self._major_spin.value()
            self._state["major_value"] = v
            self._major_result.setText(f"Major: {v}")
            self._major_result.setStyleSheet(
                f"font-size: 15px; font-weight: bold; color: {C['green']}; font-family: Consolas;"
                f" background-color: rgba(16,185,129,0.15); border-radius: 6px; padding: 4px;"
            )
        else:
            v = self._minor_spin.value()
            self._state["minor_value"] = v
            self._minor_result.setText(f"Minor: {v}")
            self._minor_result.setStyleSheet(
                f"font-size: 15px; font-weight: bold; color: {C['orange']}; font-family: Consolas;"
                f" background-color: rgba(245,158,11,0.15); border-radius: 6px; padding: 4px;"
            )
        self._check_save_enabled()

    def _make_key_manual_set(self, key_name):
        """Return a closure that sets a key value from its spinbox."""
        def _set():
            if key_name not in getattr(self, '_key_spinboxes', {}):
                return
            v = self._key_spinboxes[key_name].value()
            self._state["key_values"][key_name] = v
            self._key_result_labels[key_name].setText(str(v))
            self._key_result_labels[key_name].setStyleSheet(
                f"font-size: 10px; font-weight: bold; color: {C['green']}; font-family: Consolas;"
            )
            self._key_buttons[key_name].setStyleSheet(
                pill_btn_qss(C["green"], _lighten(C["green"], 0.12), 12, 8)
            )
            n = len(self._state["key_values"])
            self._key_counter.setText(f"Da capture: {n} / 12 keys")
            if n == 12:
                self._key_counter.setStyleSheet(
                    f"font-size: 12px; color: {C['green']}; font-weight: bold; font-family: {FONT};"
                )
            self._check_save_enabled()
        return _set

    def _make_mode_manual_set(self, m_name):
        """Return a closure that sets a mode value from its spinbox."""
        def _set():
            if m_name not in getattr(self, '_mode_spinboxes', {}):
                return
            v = self._mode_spinboxes[m_name].value()
            self._state["mode_values"][m_name] = v
            self._mode_result_labels[m_name].setText(str(v))
            self._mode_result_labels[m_name].setStyleSheet(
                f"font-size: 14px; font-weight: bold; color: {C['primary']}; font-family: Consolas;"
            )
            self._mode_buttons[m_name].setStyleSheet(
                pill_btn_qss(C["green"], _lighten(C["green"], 0.12), 13, 16)
            )
            self._check_save_enabled()
        return _set
