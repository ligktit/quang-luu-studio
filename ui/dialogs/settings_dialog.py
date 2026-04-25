import backend
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox,
    QLineEdit, QFileDialog, QWidget, QFrame, QTabWidget,
)
from PySide6.QtCore import Qt, QSize, QByteArray
from PySide6.QtGui import QIcon, QPixmap, QPainter

from ui.design_tokens import C, FONT
from ui.components.svg_icons import (
    SVG_CANCEL,
    SVG_FOLDER,
    SVG_GLOBE,
    SVG_MIC,
    SVG_POWER,
    SVG_SAVE,
    SVG_SEARCH,
    SVG_SETTINGS,
    SVG_UPLOAD,
    SVG_WRENCH,
)
from frontend_qt import pill_btn_qss, add_shadow, _lighten


class SettingsDialog(QDialog):
    """Dialog thiết lập đường dẫn, tự động khởi động và thiết bị ghi âm."""

    def __init__(self, parent):
        super().__init__(parent)
        self._dashboard = parent
        self.setWindowTitle("Thiết lập")
        self.setMinimumSize(760, 680)
        self.resize(800, 720)
        self.setModal(True)
        self.setStyleSheet(self._dialog_qss())
        self._build_ui()

    # ── Helpers ───────────────────────────────────────────────

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

    @classmethod
    def _icon_button(cls, svg_content, color, size=44, icon_size=18):
        btn = QPushButton("")
        btn.setIcon(cls._svg_icon(svg_content, "white", icon_size))
        btn.setIconSize(QSize(icon_size, icon_size))
        btn.setFixedSize(size, size)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(pill_btn_qss(color, _lighten(color, 0.1), 14, 10))
        return btn

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
            QScrollBar:vertical {{
                background: rgba(15, 23, 42, 110);
                width: 7px;
                border-radius: 3px;
                margin: 4px 0;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(56, 189, 248, 115);
                border-radius: 3px;
                min-height: 28px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QFrame#settingsHeader {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(14, 165, 233, 56),
                    stop:0.48 rgba(30, 41, 59, 245),
                    stop:1 rgba(168, 85, 247, 42));
                border-bottom: 1px solid rgba(148, 163, 184, 45);
            }}
            QFrame#settingsFooter {{
                background-color: rgba(15, 23, 42, 242);
                border-top: 1px solid rgba(148, 163, 184, 45);
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
                padding: 8px 20px;
                margin: 8px 4px 4px 0;
                border: 1px solid rgba(51, 65, 85, 150);
                border-radius: 12px;
                font-size: 14px;
                font-weight: 700;
                min-height: 28px;
            }}
            QTabBar::tab:first {{
                margin-left: 18px;
            }}
            QTabBar::tab:selected {{
                color: {C['text']};
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(56, 189, 248, 210),
                    stop:1 rgba(59, 130, 246, 188));
                border: 1px solid rgba(125, 211, 252, 170);
            }}
            QTabBar::tab:hover:!selected {{
                color: {C['text']};
                background-color: rgba(51, 65, 85, 210);
                border-color: rgba(148, 163, 184, 80);
            }}
        """

    @classmethod
    def _section_header(cls, svg_content, text):
        frame = QFrame()
        frame.setObjectName("settingsSectionHeader")
        frame.setStyleSheet(f"""
            QFrame#settingsSectionHeader {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(56, 189, 248, 55),
                    stop:0.62 rgba(30, 41, 59, 135),
                    stop:1 rgba(30, 41, 59, 0));
                border: 1px solid rgba(56, 189, 248, 70);
                border-left: 4px solid {C['teal']};
                border-radius: 12px;
            }}
        """)
        row = QHBoxLayout(frame)
        row.setContentsMargins(10, 7, 10, 7)
        row.setSpacing(8)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(cls._svg_icon(svg_content, C["teal"], 16).pixmap(QSize(16, 16)))
        icon_lbl.setFixedSize(18, 18)
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {C['text']}; font-size: 13px; font-weight: 800; line-height: 18px;"
            f" font-family: {FONT}; background: transparent; border: none;"
        )
        row.addWidget(icon_lbl)
        row.addWidget(lbl)
        row.addStretch()
        return frame

    @staticmethod
    def _section_card(fn):
        card = QFrame()
        card.setObjectName("settingsCard")
        card.setStyleSheet(f"""
            QFrame#settingsCard {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(30, 41, 59, 238),
                    stop:1 rgba(15, 23, 42, 226));
                border-radius: 16px;
                border: 1px solid rgba(148, 163, 184, 42);
            }}
        """)
        vl = QVBoxLayout(card)
        vl.setContentsMargins(16, 14, 16, 14)
        vl.setSpacing(10)
        fn(vl)
        return card

    _input_qss = f"""
        QLineEdit {{
            background-color: rgba(15, 23, 42, 225);
            color: {C['text']};
            border: 1px solid rgba(148, 163, 184, 55);
            border-radius: 11px;
            padding: 8px 12px;
            font-size: 14px;
            font-weight: 600;
            font-family: {FONT};
            selection-background-color: {C['teal']};
        }}
        QLineEdit:hover {{
            border-color: rgba(148, 163, 184, 100);
        }}
        QLineEdit:focus {{
            border-color: {C['teal']};
            background-color: rgba(2, 6, 23, 235);
        }}
    """

    _checkbox_qss = f"""
        QCheckBox {{
            spacing: 12px; font-size: 14px; font-family: {FONT};
            color: {C['text']}; padding: 4px 6px; background: transparent;
            font-weight: 600;
        }}
        QCheckBox::indicator {{
            width: 24px; height: 24px; border-radius: 8px;
            border: 2px solid rgba(148, 163, 184, 82);
            background-color: rgba(15, 23, 42, 230);
        }}
        QCheckBox::indicator:hover {{
            border-color: {C['teal']};
        }}
        QCheckBox::indicator:checked {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {C['teal']}, stop:1 {C['blue']});
            border-color: rgba(125, 211, 252, 230);
        }}
    """

    _combo_qss = f"""
        QComboBox {{
            background-color: rgba(15, 23, 42, 225);
            color: {C['text']};
            border: 1px solid rgba(148, 163, 184, 55);
            border-radius: 11px;
            padding: 6px 10px;
            font-size: 12px;
            font-weight: 700;
            font-family: {FONT};
            min-height: 20px;
        }}
        QComboBox:hover {{
            border-color: rgba(148, 163, 184, 100);
        }}
        QComboBox:focus {{
            border-color: {C['teal']};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 26px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {C['card']};
            color: {C['text']};
            selection-background-color: {C['teal']};
            selection-color: {C['bg']};
            border: 1px solid rgba(148, 163, 184, 65);
            outline: none;
            font-size: 12px;
            font-family: {FONT};
        }}
    """

    @staticmethod
    def _field_label_qss(size=11, color=None, weight=800, italic=False):
        italic_qss = "font-style: italic;" if italic else ""
        return (
            f"color: {color or C['text_muted']}; font-size: {size}px;"
            f" font-weight: {weight}; font-family: {FONT};"
            f" background: transparent; border: none; {italic_qss}"
        )

    # ── Build ─────────────────────────────────────────────────

    def _build_ui(self):
        settings = self._dashboard.settings
        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # Header
        hdr = QFrame()
        hdr.setObjectName("settingsHeader")
        hdr_lay = QVBoxLayout(hdr)
        hdr_lay.setContentsMargins(24, 16, 24, 14)
        hdr_lay.setSpacing(4)
        title = QLabel("Thiết lập hệ thống")
        title.setStyleSheet(
            f"font-size: 22px; font-weight: 900; color: {C['text']};"
            f" font-family: {FONT}; background: transparent; border: none;"
        )
        title.setAlignment(Qt.AlignCenter)
        subtitle = QLabel("Tinh chỉnh đường dẫn, thiết bị âm thanh và công cụ YouTube/CDP")
        subtitle.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {C['text_muted']};"
            f" font-family: {FONT}; background: transparent; border: none;"
        )
        subtitle.setAlignment(Qt.AlignCenter)
        hdr_lay.addWidget(title)
        hdr_lay.addWidget(subtitle)
        outer.addWidget(hdr)

        # Tab Widget
        self._tabs = QTabWidget()
        self._tabs.setIconSize(QSize(16, 16))

        # Tab 1: System
        self._tabs.addTab(
            self._build_system_tab(settings),
            self._svg_icon(SVG_SETTINGS, "white", 16),
            "Hệ thống",
        )
        # Tab 2: Audio
        self._tabs.addTab(
            self._build_audio_tab(settings),
            self._svg_icon(SVG_MIC, "white", 16),
            "Âm thanh",
        )
        # Tab 3: Tools
        self._tabs.addTab(
            self._build_tools_tab(),
            self._svg_icon(SVG_WRENCH, "white", 16),
            "Công cụ",
        )

        outer.addWidget(self._tabs, 1)
        outer.addWidget(self._build_footer())

    def _build_system_tab(self, settings):
        tab = QWidget()
        tab.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)

        # Paths
        lay.addWidget(self._section_header(SVG_FOLDER, "Đường dẫn ứng dụng"))
        self._inp_so = QLineEdit(settings.get("studio_one_path", ""))
        self._inp_so.setPlaceholderText("VD: D:/Songs/BaiHat.song hoặc C:/.../Studio One 7.exe")
        self._inp_br = QLineEdit(settings.get("browser_path", ""))
        self._inp_br.setPlaceholderText("VD: C:/Program Files/Google/Chrome/chrome.exe")
        lay.addWidget(self._section_card(self._build_paths))

        # Launch options
        lay.addWidget(self._section_header(SVG_POWER, "Khởi động / Tắt tự động"))
        self._cb_launch_so = QCheckBox("Mở Studio One khi khởi động")
        self._cb_launch_so.setStyleSheet(self._checkbox_qss)
        self._cb_launch_so.setChecked(settings.get("auto_launch_studio_one", False))
        self._cb_launch_br = QCheckBox("Mở YouTube (trình duyệt) khi khởi động")
        self._cb_launch_br.setStyleSheet(self._checkbox_qss)
        self._cb_launch_br.setChecked(settings.get("auto_launch_browser", False))
        self._cb_close_so = QCheckBox("Đóng Studio One khi thoát")
        self._cb_close_so.setStyleSheet(self._checkbox_qss)
        self._cb_close_so.setChecked(settings.get("auto_close_studio_one", False))
        self._cb_close_br = QCheckBox("Đóng trình duyệt khi thoát")
        self._cb_close_br.setStyleSheet(self._checkbox_qss)
        self._cb_close_br.setChecked(settings.get("auto_close_browser", False))
        lay.addWidget(self._section_card(self._build_autolaunch))
        
        lay.addStretch()
        return tab

    def _build_audio_tab(self, settings):
        tab = QWidget()
        tab.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)

        lay.addWidget(self._section_header(SVG_MIC, "Thiết bị ghi âm"))
        self._combo_lb, self._combo_mic = self._create_audio_combos(settings)
        lay.addWidget(self._section_card(self._build_audio))

        lay.addWidget(self._section_header(SVG_SETTINGS, "Calibration"))
        cal_btn = QPushButton("Mở Calibration Auto-Tune")
        cal_btn.setIcon(self._svg_icon(SVG_SETTINGS, "white", 17))
        cal_btn.setIconSize(QSize(17, 17))
        cal_btn.setCursor(Qt.PointingHandCursor)
        cal_btn.setFixedHeight(40)
        cal_btn.setStyleSheet(pill_btn_qss(C["orange"], _lighten(C["orange"], 0.1), 14, 18))
        cal_btn.clicked.connect(self._open_calibration)
        add_shadow(cal_btn, C["orange"], 8, (0, 2))
        lay.addWidget(cal_btn)

        lay.addStretch()
        return tab

    def _build_tools_tab(self):
        tab = QWidget()
        tab.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)

        lay.addWidget(self._section_header(SVG_GLOBE, "YouTube Cookie"))
        lay.addWidget(self._section_card(self._build_cookie_tools))

        lay.addWidget(self._section_header(SVG_WRENCH, "Sửa lỗi đồng bộ (CDP)"))
        lay.addWidget(self._section_card(self._build_cdp_tools))

        lay.addStretch()
        return tab

    def _build_paths(self, vl):
        so_lbl = QLabel("Studio One (.song hoặc .exe):")
        so_lbl.setStyleSheet(self._field_label_qss())
        vl.addWidget(so_lbl)
        row_so = QHBoxLayout()
        row_so.setSpacing(8)
        self._inp_so.setStyleSheet(self._input_qss)
        self._inp_so.setMinimumHeight(42)
        row_so.addWidget(self._inp_so)
        browse_so = self._icon_button(SVG_FOLDER, C["teal"], size=42, icon_size=17)
        browse_so.clicked.connect(self._browse_so)
        row_so.addWidget(browse_so)
        vl.addLayout(row_so)

        br_lbl = QLabel("Trình duyệt (YouTube):")
        br_lbl.setStyleSheet(self._field_label_qss())
        vl.addWidget(br_lbl)
        row_br = QHBoxLayout()
        row_br.setSpacing(8)
        self._inp_br.setStyleSheet(self._input_qss)
        self._inp_br.setMinimumHeight(42)
        row_br.addWidget(self._inp_br)
        browse_br = self._icon_button(SVG_FOLDER, C["teal"], size=42, icon_size=17)
        browse_br.clicked.connect(self._browse_br)
        row_br.addWidget(browse_br)
        vl.addLayout(row_br)

    def _build_autolaunch(self, vl):
        vl.setSpacing(8)
        for cb in (self._cb_launch_so, self._cb_launch_br, self._cb_close_so, self._cb_close_br):
            cb.setMinimumHeight(34)
        vl.addWidget(self._cb_launch_so)
        vl.addWidget(self._cb_launch_br)
        vl.addWidget(self._cb_close_so)
        vl.addWidget(self._cb_close_br)

    def _create_audio_combos(self, settings):
        from PySide6.QtWidgets import QComboBox
        combo_lb  = QComboBox()
        combo_mic = QComboBox()
        combo_lb.setStyleSheet(self._combo_qss)
        combo_mic.setStyleSheet(self._combo_qss)

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
            print(f"[SETTINGS] Cannot enumerate audio devices: {e}")

        combo_lb.addItem("Tự động (WASAPI Loopback của loa mặc định)", -1)
        lb_sel = 0
        for idx, (label, dev_idx) in enumerate(audio_devices):
            combo_lb.addItem(label, dev_idx)
            if dev_idx == saved_lb_idx:
                lb_sel = idx + 1
        combo_lb.setCurrentIndex(lb_sel)

        combo_mic.addItem("Tắt (Studio One đã mix giọng vào Loopback)", -2)
        combo_mic.addItem("Bật Mic (chỉ dùng khi KHÔNG qua Studio One)", -1)
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
        lb_lbl.setStyleSheet(self._field_label_qss())
        vl.addWidget(lb_lbl)
        vl.addWidget(self._combo_lb)
        hint = QLabel("Gợi ý: nếu dùng ASIOVADPRO, chọn thiết bị có tên 'ASIOVAD' hoặc 'VB-Cable'")
        hint.setStyleSheet(self._field_label_qss(size=11, color=C["orange"], weight=600, italic=True))
        hint.setWordWrap(True)
        vl.addWidget(hint)
        mic_lbl = QLabel("Microphone:")
        mic_lbl.setStyleSheet(self._field_label_qss())
        vl.addWidget(mic_lbl)
        vl.addWidget(self._combo_mic)
        mic_hint = QLabel(
            "Lưu ý: Khi dùng Studio One, Loopback đã chứa giọng hát đã xử lý (Auto-Tune + Reverb).\n"
            "Bật thêm Mic sẽ khiến giọng bị lặp đôi. Chỉ bật khi ghi âm thô không qua DAW."
        )
        mic_hint.setStyleSheet(self._field_label_qss(size=10, color=C["orange"], weight=600, italic=True))
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
            self._field_label_qss(size=12, weight=500)
        )
        vl.addWidget(desc)

        # Browser selector
        browser_row = QHBoxLayout()
        browser_lbl = QLabel("Nguồn cookie:")
        browser_lbl.setStyleSheet(
            self._field_label_qss(size=12, weight=800) + " min-width: 100px;"
        )
        self._combo_cookie_browser = QComboBox()
        self._combo_cookie_browser.setStyleSheet(self._combo_qss)
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
        export_btn = QPushButton("Xuất Cookie ra File")
        export_btn.setIcon(self._svg_icon(SVG_UPLOAD, "white", 16))
        export_btn.setIconSize(QSize(16, 16))
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.setFixedHeight(38)
        export_btn.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.1), 12, 12))
        add_shadow(export_btn, C["teal"], 8, (0, 2))
        export_btn.setToolTip(
            "Xuất cookie từ browser đang chọn ra file.\n"
            "Chrome/Edge/Brave phải đóng hoàn toàn trước khi xuất.\n"
            "Firefox có thể xuất khi đang mở."
        )

        from core.ytdlp_support import _AUTO_COOKIE_FILE
        file_exists = os.path.exists(_AUTO_COOKIE_FILE)
        self._cookie_status_lbl = QLabel("Có file cookie" if file_exists else "Chưa có file cookie")
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
            self._field_label_qss(size=10, weight=500, italic=True)
        )
        hint.setWordWrap(True)
        vl.addWidget(hint)

    def _build_cdp_tools(self, vl):
        from PySide6.QtWidgets import QLabel, QPushButton, QHBoxLayout
        desc = QLabel(
            "Gợi ý: nếu ứng dụng không thể nhảy theo lời bài hát (hiện thông báo CDP chưa kết nối), "
            "có thể do trình duyệt bị chạy ngầm hoặc thiếu flag. Bạn hãy làm 2 bước:"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(self._field_label_qss(size=12, weight=500))
        vl.addWidget(desc)

        row = QHBoxLayout()
        row.setSpacing(10)
        kill_btn = QPushButton("1. Force Kill Trình Duyệt Ngầm")
        kill_btn.setIcon(self._svg_icon(SVG_CANCEL, "white", 16))
        kill_btn.setIconSize(QSize(16, 16))
        kill_btn.setCursor(Qt.PointingHandCursor)
        kill_btn.setFixedHeight(42)
        kill_btn.setStyleSheet(pill_btn_qss(C["accent"], _lighten(C["accent"], 0.1), 13, 10))
        add_shadow(kill_btn, C["accent"], 8, (0, 2))
        kill_btn.clicked.connect(self._action_kill_browsers)

        fix_btn = QPushButton("2. Thêm Flag vào Shortcut")
        fix_btn.setIcon(self._svg_icon(SVG_WRENCH, "white", 16))
        fix_btn.setIconSize(QSize(16, 16))
        fix_btn.setCursor(Qt.PointingHandCursor)
        fix_btn.setFixedHeight(42)
        fix_btn.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.1), 13, 10))
        add_shadow(fix_btn, C["teal"], 8, (0, 2))
        fix_btn.clicked.connect(self._action_fix_shortcuts)
        
        check_btn = QPushButton("Kiểm tra")
        check_btn.setIcon(self._svg_icon(SVG_SEARCH, "white", 16))
        check_btn.setIconSize(QSize(16, 16))
        check_btn.setCursor(Qt.PointingHandCursor)
        check_btn.setFixedHeight(42)
        check_btn.setFixedWidth(108)
        check_btn.setStyleSheet(pill_btn_qss(C["blue"], _lighten(C["blue"], 0.1), 13, 10))
        check_btn.clicked.connect(self._action_check_cdp)

        row.addWidget(kill_btn)
        row.addWidget(fix_btn)
        row.addWidget(check_btn)
        vl.addLayout(row)

    def _build_footer(self):
        footer = QFrame()
        footer.setObjectName("settingsFooter")
        lay = QHBoxLayout(footer)
        lay.setContentsMargins(20, 12, 20, 12)
        lay.setSpacing(10)

        save_btn = QPushButton("Lưu thiết lập")
        save_btn.setIcon(self._svg_icon(SVG_SAVE, "white", 17))
        save_btn.setIconSize(QSize(17, 17))
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setFixedSize(176, 40)
        save_btn.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.14), 13, 18))
        save_btn.clicked.connect(self._save)
        add_shadow(save_btn, C["green"], 8, (0, 2))

        cancel_btn = QPushButton("Hủy")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setFixedSize(96, 40)
        cancel_btn.setStyleSheet(pill_btn_qss(C["card_hover"], _lighten(C["card_hover"], 0.12), 13, 18))
        cancel_btn.clicked.connect(self.close)

        lay.addStretch()
        lay.addWidget(cancel_btn)
        lay.addWidget(save_btn)
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

        self._dashboard._show_message("Đã lưu thiết lập")
        self.close()

    def _action_export_cookies(self):
        import threading
        browser = self._combo_cookie_browser.currentData() or "chrome"
        if browser in ("none", "auto"):
            browser = "chrome"
        self._cookie_status_lbl.setText("Đang xuất cookie...")
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
                    self._cookie_status_lbl.setText("Xuất cookie thành công!")
                    self._cookie_status_lbl.setStyleSheet(
                        f"color: {C['green']}; font-size: 11px; font-family: {FONT};"
                        " background:transparent; border:none;"
                    )
                    self._dashboard._show_message("Đã lưu cookie")
                    # Auto-switch config to use the cookie file
                    backend.AppConfig.update("youtube_cookie_browser", "none")
                    backend.AppConfig.update("youtube_cookie_file", result)
                    backend.AppConfig.save()
                else:
                    self._cookie_status_lbl.setText("Xuất thất bại (đóng browser trước?)")
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
        self._dashboard._show_message("Đã tắt trình duyệt ngầm")

    def _action_fix_shortcuts(self):
        import os, ctypes
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tools", "_apply_cdp.ps1"))
        if not os.path.exists(script_path):
            self._dashboard._show_message("Không tìm thấy công cụ _apply_cdp.ps1", is_error=True)
            return
            
        cmd = f'-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{script_path}"'
        try:
            # Dùng ShellExecute với 'runas' để tự động hỏi quyền Admin bằng UAC popup
            result = ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe", cmd, None, 1)
            if result > 32:
                self._dashboard._show_message("Đã sửa shortcut")
            else:
                self._dashboard._show_message("Bạn đã từ chối cấp quyền Admin.", is_error=True)
        except Exception as e:
            self._dashboard._show_message(f"Lỗi: {e}", is_error=True)

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
            self._dashboard._show_message("CDP: Đã kết nối")
        elif is_winrt:
            self._dashboard._show_message("Đang dùng WinRT Fallback.\n(Không nhảy lời chính xác, hãy sửa bước 1 & 2)")
        else:
            self._dashboard._show_message("Chưa kết nối trình duyệt.\nHãy mở YouTube trên Edge/Chrome/Brave.", is_error=True)
