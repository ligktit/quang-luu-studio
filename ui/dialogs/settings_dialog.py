import backend
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox,
    QLineEdit, QFileDialog, QScrollArea, QWidget, QFrame,
)
from PySide6.QtCore import Qt

from ui.design_tokens import C, FONT
from frontend_qt import pill_btn_qss, add_shadow, _lighten


class SettingsDialog(QDialog):
    """Dialog thiết lập đường dẫn, tự động khởi động và thiết bị ghi âm."""

    def __init__(self, parent):
        super().__init__(parent)
        self._dashboard = parent
        self.setWindowTitle("⚙️ Thiết lập")
        self.setMinimumSize(580, 560)
        self.setMaximumSize(620, 820)
        self.resize(580, 680)
        self.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")
        self._build_ui()

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _section_header(icon, text):
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(56,189,248,18), stop:1 rgba(56,189,248,0));
                border-left: 3px solid {C['teal']};
                border-radius: 0px 6px 6px 0px;
                padding: 2px;
            }}
        """)
        row = QHBoxLayout(frame)
        row.setContentsMargins(10, 6, 10, 6)
        lbl = QLabel(f"{icon}  {text}")
        lbl.setStyleSheet(
            f"color: {C['text']}; font-size: 13px; font-weight: 700;"
            f" font-family: {FONT}; background: transparent; border: none;"
        )
        row.addWidget(lbl)
        return frame

    @staticmethod
    def _section_card(fn):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(30,41,59,180);
                border-radius: 10px;
                border: 1px solid rgba(51,65,85,0.6);
            }}
        """)
        vl = QVBoxLayout(card)
        vl.setContentsMargins(14, 12, 14, 12)
        vl.setSpacing(10)
        fn(vl)
        return card

    _input_qss = f"""
        QLineEdit {{
            background-color: {C['bg']};
            color: {C['text']};
            border: 1px solid {C['border']};
            border-radius: 8px;
            padding: 8px 10px;
            font-size: 13px;
            font-family: {FONT};
        }}
        QLineEdit:focus {{ border-color: {C['teal']}; border-width: 2px; }}
    """

    _checkbox_qss = f"""
        QCheckBox {{
            spacing: 10px; font-size: 13px; font-family: {FONT};
            color: {C['text']}; padding: 4px 2px; background: transparent;
        }}
        QCheckBox::indicator {{
            width: 18px; height: 18px; border-radius: 4px;
            border: 2px solid {C['border']}; background-color: {C['bg']};
        }}
        QCheckBox::indicator:checked {{
            background-color: {C['teal']}; border-color: {C['teal']};
        }}
    """

    # ── Build ─────────────────────────────────────────────────

    def _build_ui(self):
        settings = self._dashboard.settings
        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # Header
        hdr = QFrame()
        hdr.setStyleSheet(f"QFrame {{ background-color: {C['card']}; border-bottom: 1px solid {C['border']}; }}")
        hdr_lay = QVBoxLayout(hdr)
        hdr_lay.setContentsMargins(24, 16, 24, 14)
        title = QLabel("⚙️ Thiết lập khởi động")
        title.setStyleSheet(
            f"font-size: 20px; font-weight: bold; color: {C['teal']};"
            f" font-family: {FONT}; background: transparent; border: none;"
        )
        title.setAlignment(Qt.AlignCenter)
        hdr_lay.addWidget(title)
        outer.addWidget(hdr)

        # Scroll
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background-color: {C['bg']}; }}
            QScrollBar:vertical {{ background: {C['card']}; width: 6px; border-radius: 3px; }}
            QScrollBar::handle:vertical {{ background: {C['border']}; border-radius: 3px; min-height: 20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        content = QWidget()
        content.setStyleSheet(f"background-color: {C['bg']};")
        lay = QVBoxLayout(content)
        lay.setSpacing(14)
        lay.setContentsMargins(20, 16, 20, 16)

        # ── Đường dẫn ──
        lay.addWidget(self._section_header("📁", "Đường dẫn ứng dụng"))
        self._inp_so = QLineEdit(settings.get("studio_one_path", ""))
        self._inp_so.setPlaceholderText("VD: D:/Songs/BaiHat.song hoặc C:/.../Studio One 7.exe")
        self._inp_br = QLineEdit(settings.get("browser_path", ""))
        self._inp_br.setPlaceholderText("VD: C:/Program Files/Google/Chrome/chrome.exe")
        lay.addWidget(self._section_card(self._build_paths))

        # ── Khởi động tự động ──
        lay.addWidget(self._section_header("🚀", "Khởi động / Tắt tự động"))
        self._cb_launch_so = QCheckBox("🎹 Mở Studio One khi khởi động")
        self._cb_launch_so.setStyleSheet(self._checkbox_qss)
        self._cb_launch_so.setChecked(settings.get("auto_launch_studio_one", False))
        self._cb_launch_br = QCheckBox("🌐 Mở YouTube (trình duyệt) khi khởi động")
        self._cb_launch_br.setStyleSheet(self._checkbox_qss)
        self._cb_launch_br.setChecked(settings.get("auto_launch_browser", False))
        self._cb_close_so = QCheckBox("🎹 Đóng Studio One khi thoát")
        self._cb_close_so.setStyleSheet(self._checkbox_qss)
        self._cb_close_so.setChecked(settings.get("auto_close_studio_one", False))
        self._cb_close_br = QCheckBox("🌐 Đóng trình duyệt khi thoát")
        self._cb_close_br.setStyleSheet(self._checkbox_qss)
        self._cb_close_br.setChecked(settings.get("auto_close_browser", False))
        lay.addWidget(self._section_card(self._build_autolaunch))

        # ── Thiết bị ghi âm ──
        lay.addWidget(self._section_header("🎙️", "Thiết bị ghi âm"))
        self._combo_lb, self._combo_mic = self._create_audio_combos(settings)
        lay.addWidget(self._section_card(self._build_audio))

        # ── YouTube Cookie ──
        lay.addWidget(self._section_header("🍪", "YouTube Cookie"))
        lay.addWidget(self._section_card(self._build_cookie_tools))

        # ── Sửa lỗi CDP (Đồng bộ trình duyệt) ──
        lay.addWidget(self._section_header("🛠️", "Sửa lỗi đồng bộ (CDP)"))
        lay.addWidget(self._section_card(self._build_cdp_tools))

        # ── Calibrate button ──
        cal_btn = QPushButton("🎛️ Calibrate Auto-Tune")
        cal_btn.setCursor(Qt.PointingHandCursor)
        cal_btn.setFixedHeight(40)
        cal_btn.setStyleSheet(pill_btn_qss(C["orange"], _lighten(C["orange"], 0.1), 14, 18))
        cal_btn.clicked.connect(self._open_calibration)
        add_shadow(cal_btn, C["orange"], 8, (0, 2))
        lay.addWidget(cal_btn)
        lay.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        outer.addWidget(self._build_footer())

    def _build_paths(self, vl):
        so_lbl = QLabel("🎹 Studio One (.song hoặc .exe):")
        so_lbl.setStyleSheet(f"color: {C['text_muted']}; font-size: 11px; font-weight: 600; font-family: {FONT}; background:transparent; border:none;")
        vl.addWidget(so_lbl)
        row_so = QHBoxLayout()
        row_so.setSpacing(6)
        self._inp_so.setStyleSheet(self._input_qss)
        row_so.addWidget(self._inp_so)
        browse_so = QPushButton("📂")
        browse_so.setFixedSize(38, 36)
        browse_so.setCursor(Qt.PointingHandCursor)
        browse_so.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.1), 14, 8))
        browse_so.clicked.connect(self._browse_so)
        row_so.addWidget(browse_so)
        vl.addLayout(row_so)

        br_lbl = QLabel("🌐 Trình duyệt (YouTube):")
        br_lbl.setStyleSheet(f"color: {C['text_muted']}; font-size: 11px; font-weight: 600; font-family: {FONT}; background:transparent; border:none;")
        vl.addWidget(br_lbl)
        row_br = QHBoxLayout()
        row_br.setSpacing(6)
        self._inp_br.setStyleSheet(self._input_qss)
        row_br.addWidget(self._inp_br)
        browse_br = QPushButton("📂")
        browse_br.setFixedSize(38, 36)
        browse_br.setCursor(Qt.PointingHandCursor)
        browse_br.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.1), 14, 8))
        browse_br.clicked.connect(self._browse_br)
        row_br.addWidget(browse_br)
        vl.addLayout(row_br)

    def _build_autolaunch(self, vl):
        vl.addWidget(self._cb_launch_so)
        vl.addWidget(self._cb_launch_br)
        vl.addWidget(self._cb_close_so)
        vl.addWidget(self._cb_close_br)

    def _create_audio_combos(self, settings):
        combo_qss = f"""
            QComboBox {{
                background-color: {C['bg']}; color: {C['text']};
                border: 1px solid {C['border']}; border-radius: 8px;
                padding: 7px 10px; font-size: 12px; font-family: {FONT};
            }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{
                background-color: {C['card']}; color: {C['text']};
                selection-background-color: {C['teal']};
                border: 1px solid {C['border']}; font-size: 12px;
            }}
        """
        from PySide6.QtWidgets import QComboBox
        combo_lb  = QComboBox()
        combo_mic = QComboBox()
        combo_lb.setStyleSheet(combo_qss)
        combo_mic.setStyleSheet(combo_qss)

        saved_lb_idx  = settings.get("record_loopback_device", -1)
        saved_mic_idx = settings.get("record_mic_device",  -1)
        audio_devices, all_input_devices = [], []

        try:
            import pyaudiowpatch as _paw
            _pa = _paw.PyAudio()
            for i in range(_pa.get_device_count()):
                try:
                    d   = _pa.get_device_info_by_index(i)
                    api = _pa.get_host_api_info_by_index(d["hostApi"])
                    is_lb = d.get("isLoopbackDevice", False)
                    if d["maxInputChannels"] > 0:
                        tag   = " [LB]" if is_lb else ""
                        label = f"[{i}] {d['name'][:38]}{tag}  ({api['name'][:8]})"
                        audio_devices.append((label, i))
                        if not is_lb:
                            all_input_devices.append((label, i))
                except Exception:
                    continue
            _pa.terminate()
        except Exception as e:
            print(f"⚠️ [SETTINGS] Cannot enumerate audio devices: {e}")

        combo_lb.addItem("🔄 Tự động (WASAPI Loopback của loa mặc định)", -1)
        lb_sel = 0
        for idx, (label, dev_idx) in enumerate(audio_devices):
            combo_lb.addItem(label, dev_idx)
            if dev_idx == saved_lb_idx:
                lb_sel = idx + 1
        combo_lb.setCurrentIndex(lb_sel)

        combo_mic.addItem("🔇 Tắt (Studio One đã mix giọng vào Loopback)", -2)
        combo_mic.addItem("🔄 Bật Mic (chỉ dùng khi KHÔNG qua Studio One)", -1)
        mic_sel = 0
        for idx, (label, dev_idx) in enumerate(all_input_devices):
            combo_mic.addItem(label, dev_idx)
            if dev_idx == saved_mic_idx:
                mic_sel = idx + 2
        if saved_mic_idx == -1:
            mic_sel = 1
        elif saved_mic_idx == -2:
            mic_sel = 0
        combo_mic.setCurrentIndex(mic_sel)

        return combo_lb, combo_mic

    def _build_audio(self, vl):
        lb_lbl = QLabel("Nguồn nhạc (Loopback / ASIOVADPRO):")
        lb_lbl.setStyleSheet(f"color: {C['text_muted']}; font-size: 11px; font-weight: 600; font-family: {FONT}; background:transparent; border:none;")
        vl.addWidget(lb_lbl)
        vl.addWidget(self._combo_lb)
        hint = QLabel("💡 Nếu dùng ASIOVADPRO: chọn thiết bị có tên 'ASIOVAD' hoặc 'VB-Cable'")
        hint.setStyleSheet(f"color: {C['orange']}; font-size: 11px; font-style: italic; font-family: {FONT}; background:transparent; border:none;")
        hint.setWordWrap(True)
        vl.addWidget(hint)
        mic_lbl = QLabel("🎤 Microphone:")
        mic_lbl.setStyleSheet(f"color: {C['text_muted']}; font-size: 11px; font-weight: 600; font-family: {FONT}; background:transparent; border:none;")
        vl.addWidget(mic_lbl)
        vl.addWidget(self._combo_mic)
        mic_hint = QLabel(
            "⚠️ Khi dùng Studio One, Loopback đã chứa giọng hát đã xử lý (Auto-Tune + Reverb).\n"
            "Bật thêm Mic sẽ khiến giọng bị lặp đôi. Chỉ bật khi ghi âm thô không qua DAW."
        )
        mic_hint.setStyleSheet(f"color: {C['orange']}; font-size: 10px; font-style: italic; font-family: {FONT}; background:transparent; border:none;")
        mic_hint.setWordWrap(True)
        vl.addWidget(mic_hint)

    def _build_cookie_tools(self, vl):
        from PySide6.QtWidgets import QComboBox
        import os

        desc = QLabel(
            "Nếu thấy lỗi \"Could not copy Chrome cookie database\", dùng Firefox hoặc "
            "xuất cookie ra file một lần (Chrome phải đóng hoàn toàn khi xuất)."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"color: {C['text_muted']}; font-size: 12px; font-family: {FONT};"
            " background:transparent; border:none;"
        )
        vl.addWidget(desc)

        # Browser selector
        browser_row = QHBoxLayout()
        browser_lbl = QLabel("Nguồn cookie:")
        browser_lbl.setStyleSheet(
            f"color: {C['text_muted']}; font-size: 12px; font-family: {FONT};"
            " background:transparent; border:none; min-width: 100px;"
        )
        self._combo_cookie_browser = QComboBox()
        self._combo_cookie_browser.setStyleSheet(f"""
            QComboBox {{
                background-color: {C['bg']}; color: {C['text']};
                border: 1px solid {C['border']}; border-radius: 8px;
                padding: 6px 10px; font-size: 12px; font-family: {FONT};
            }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{
                background-color: {C['card']}; color: {C['text']};
                selection-background-color: {C['teal']};
                border: 1px solid {C['border']}; font-size: 12px;
            }}
        """)
        BROWSER_OPTIONS = [
            ("auto",    "Auto (thử lần lượt)"),
            ("firefox", "Firefox (khuyến dùng, không lock)"),
            ("edge",    "Edge"),
            ("chrome",  "Chrome"),
            ("brave",   "Brave"),
            ("none",    "Tắt (dùng cookie file)"),
        ]
        current = (backend.AppConfig.get("youtube_cookie_browser") or "auto").strip().lower()
        for val, label in BROWSER_OPTIONS:
            self._combo_cookie_browser.addItem(label, val)
            if val == current:
                self._combo_cookie_browser.setCurrentIndex(self._combo_cookie_browser.count() - 1)
        browser_row.addWidget(browser_lbl)
        browser_row.addWidget(self._combo_cookie_browser, 1)
        vl.addLayout(browser_row)

        # Export button + status
        export_row = QHBoxLayout()
        export_btn = QPushButton("📤 Xuất Cookie ra File")
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.setFixedHeight(36)
        export_btn.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.1), 12, 12))
        export_btn.setToolTip(
            "Xuất cookie từ browser đang chọn ra file.\n"
            "Chrome/Edge/Brave phải đóng hoàn toàn trước khi xuất.\n"
            "Firefox có thể xuất khi đang mở."
        )

        from core.ytdlp_support import _AUTO_COOKIE_FILE
        file_exists = os.path.exists(_AUTO_COOKIE_FILE)
        self._cookie_status_lbl = QLabel("✅ Có file cookie" if file_exists else "⚠️ Chưa có file cookie")
        self._cookie_status_lbl.setStyleSheet(
            f"color: {C['green'] if file_exists else C['orange']}; font-size: 11px;"
            f" font-family: {FONT}; background:transparent; border:none;"
        )

        export_btn.clicked.connect(self._action_export_cookies)
        export_row.addWidget(export_btn)
        export_row.addWidget(self._cookie_status_lbl, 1)
        vl.addLayout(export_row)

        hint = QLabel(f"File: {_AUTO_COOKIE_FILE}")
        hint.setStyleSheet(
            f"color: {C['text_muted']}; font-size: 10px; font-style: italic;"
            f" font-family: {FONT}; background:transparent; border:none;"
        )
        hint.setWordWrap(True)
        vl.addWidget(hint)

    def _build_cdp_tools(self, vl):
        from PySide6.QtWidgets import QLabel, QPushButton, QHBoxLayout
        desc = QLabel(
            "💡 Nếu ứng dụng không thể nhảy theo lời bài hát (hiện thông báo CDP chưa kết nối), "
            "có thể do trình duyệt bị chạy ngầm hoặc thiếu flag. Bạn hãy làm 2 bước:"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {C['text_muted']}; font-size: 12px; font-family: {FONT}; background:transparent; border:none;")
        vl.addWidget(desc)

        row = QHBoxLayout()
        kill_btn = QPushButton("🛑 1. Force Kill Trình Duyệt Ngầm")
        kill_btn.setCursor(Qt.PointingHandCursor)
        kill_btn.setFixedHeight(40)
        kill_btn.setStyleSheet(pill_btn_qss(C["accent"], _lighten(C["accent"], 0.1), 13, 10))
        kill_btn.clicked.connect(self._action_kill_browsers)

        fix_btn = QPushButton("🛠️ 2. Thêm Flag vào Shortcut")
        fix_btn.setCursor(Qt.PointingHandCursor)
        fix_btn.setFixedHeight(40)
        fix_btn.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.1), 13, 10))
        fix_btn.clicked.connect(self._action_fix_shortcuts)
        
        check_btn = QPushButton("🔍 Kiểm tra")
        check_btn.setCursor(Qt.PointingHandCursor)
        check_btn.setFixedHeight(40)
        check_btn.setFixedWidth(100)
        check_btn.setStyleSheet(pill_btn_qss(C["blue"], _lighten(C["blue"], 0.1), 13, 10))
        check_btn.clicked.connect(self._action_check_cdp)

        row.addWidget(kill_btn)
        row.addWidget(fix_btn)
        row.addWidget(check_btn)
        vl.addLayout(row)

    def _build_footer(self):
        footer = QFrame()
        footer.setStyleSheet(f"QFrame {{ background-color: {C['card']}; border-top: 1px solid {C['border']}; }}")
        lay = QHBoxLayout(footer)
        lay.setContentsMargins(20, 12, 20, 12)
        lay.setSpacing(10)

        save_btn = QPushButton("💾 Lưu thiết lập")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setFixedHeight(40)
        save_btn.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.1), 14, 18))
        save_btn.clicked.connect(self._save)
        add_shadow(save_btn, C["green"], 8, (0, 2))

        cancel_btn = QPushButton("Hủy")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setFixedHeight(40)
        cancel_btn.setFixedWidth(90)
        cancel_btn.setStyleSheet(pill_btn_qss(C["card_hover"], _lighten(C["card_hover"], 0.1), 14, 18))
        cancel_btn.clicked.connect(self.close)

        lay.addWidget(save_btn, 1)
        lay.addWidget(cancel_btn)
        return footer

    # ── Actions ───────────────────────────────────────────────

    def _browse_so(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file Studio One hoặc chương trình", "",
            "Studio One Files (*.song *.exe);;Song Files (*.song);;Executable (*.exe);;All Files (*.*)"
        )
        if path:
            self._inp_so.setText(path)

    def _browse_br(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn trình duyệt", "", "Executable (*.exe);;All Files (*.*)"
        )
        if path:
            self._inp_br.setText(path)

    def _open_calibration(self):
        from ui.dialogs.calibration import CalibrationWizardDialog
        import frontend_qt
        self.close()
        dlg = CalibrationWizardDialog(self._dashboard)
        dlg.exec()
        frontend_qt.SCALE_VALUES = backend.AppConfig.get_scale_values()

    def _save(self):
        s = self._dashboard.settings
        new_so = self._inp_so.text().strip()
        new_br = self._inp_br.text().strip()
        if new_so:
            s["studio_one_path"] = new_so
        if new_br:
            s["browser_path"] = new_br
        s["auto_launch_studio_one"] = self._cb_launch_so.isChecked()
        s["auto_launch_browser"]    = self._cb_launch_br.isChecked()
        s["auto_close_studio_one"]  = self._cb_close_so.isChecked()
        s["auto_close_browser"]     = self._cb_close_br.isChecked()
        s["record_loopback_device"] = self._combo_lb.currentData()
        s["record_mic_device"]      = self._combo_mic.currentData()
        backend.ConfigManager.save_settings(s)

        # Save cookie browser choice to app_config.json
        cookie_browser = self._combo_cookie_browser.currentData() or "auto"
        backend.AppConfig.update("youtube_cookie_browser", cookie_browser)
        if cookie_browser != "none":
            backend.AppConfig.update("youtube_cookie_file", "")
        backend.AppConfig.save()

        self._dashboard._show_message("✅ Đã lưu thiết lập!")
        self.close()

    def _action_export_cookies(self):
        import threading
        browser = self._combo_cookie_browser.currentData() or "chrome"
        if browser in ("none", "auto"):
            browser = "chrome"
        self._cookie_status_lbl.setText("⏳ Đang xuất cookie...")
        self._cookie_status_lbl.setStyleSheet(
            f"color: {C['teal']}; font-size: 11px; font-family: {FONT};"
            " background:transparent; border:none;"
        )

        def _run():
            from core.ytdlp_support import export_cookies_to_file, _AUTO_COOKIE_FILE
            result = export_cookies_to_file(browser=browser, log_prefix="[SETTINGS]")
            from PySide6.QtCore import QTimer
            def _update():
                if result:
                    self._cookie_status_lbl.setText("✅ Xuất cookie thành công!")
                    self._cookie_status_lbl.setStyleSheet(
                        f"color: {C['green']}; font-size: 11px; font-family: {FONT};"
                        " background:transparent; border:none;"
                    )
                    self._dashboard._show_message(f"Cookie đã lưu:\n{result}")
                    # Auto-switch config to use the cookie file
                    backend.AppConfig.update("youtube_cookie_browser", "none")
                    backend.AppConfig.update("youtube_cookie_file", result)
                    backend.AppConfig.save()
                else:
                    self._cookie_status_lbl.setText("❌ Xuất thất bại (đóng browser trước?)")
                    self._cookie_status_lbl.setStyleSheet(
                        f"color: {C['accent']}; font-size: 11px; font-family: {FONT};"
                        " background:transparent; border:none;"
                    )
                    self._dashboard._show_message(
                        f"Không xuất được cookie từ {browser}.\n\n"
                        "Chrome/Edge/Brave phải đóng hoàn toàn.\n"
                        "Hãy thử Firefox (không cần đóng).",
                        is_error=True
                    )
            QTimer.singleShot(0, _update)

        threading.Thread(target=_run, daemon=True).start()

    def _action_kill_browsers(self):
        import subprocess
        for browser in ["msedge.exe", "chrome.exe", "brave.exe", "msedgewebview2.exe"]:
            subprocess.run(f"taskkill /F /IM {browser} /T", shell=True, capture_output=True)
        self._dashboard._show_message("✅ Đã tắt toàn bộ trình duyệt chạy ngầm!")

    def _action_fix_shortcuts(self):
        import os, ctypes
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tools", "_apply_cdp.ps1"))
        if not os.path.exists(script_path):
            self._dashboard._show_message("⚠️ Không tìm thấy công cụ _apply_cdp.ps1", is_error=True)
            return
            
        cmd = f'-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{script_path}"'
        try:
            # Dùng ShellExecute với 'runas' để tự động hỏi quyền Admin bằng UAC popup
            result = ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe", cmd, None, 1)
            if result > 32:
                self._dashboard._show_message("✅ Đã khởi chạy công cụ sửa Shortcut thành công!")
            else:
                self._dashboard._show_message("⚠️ Bạn đã từ chối cấp quyền Admin.", is_error=True)
        except Exception as e:
            self._dashboard._show_message(f"⚠️ Lỗi: {e}", is_error=True)

    def _action_check_cdp(self):
        engine = self._dashboard.engine
        is_cdp = getattr(engine.monitor, 'is_connected', False)
        
        # Fallback check
        win_media = getattr(engine, 'win_media', None)
        is_winrt = False
        if win_media:
            is_winrt = (win_media.current_title != "") or win_media.is_playing
            
        if is_cdp:
            title = getattr(engine.monitor, 'target_url', 'YouTube')
            self._dashboard._show_message(f"✅ CDP: Đã kết nối!\n({title[:40]}...)")
        elif is_winrt:
            self._dashboard._show_message("⚠️ Đang dùng WinRT Fallback.\n(Không nhảy lời chính xác, hãy sửa bước 1 & 2)")
        else:
            self._dashboard._show_message("❌ Chưa kết nối trình duyệt.\nHãy mở YouTube trên Edge/Chrome/Brave.", is_error=True)

