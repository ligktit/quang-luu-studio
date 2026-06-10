"""
Quang Lưu Studio — PySide6 Frontend V4.0
QPainter Premium Edition — Custom-painted UI
"""
import sys, os, threading
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox,
    QFrame, QDialog, QLineEdit, QFileDialog, QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, QTimer, Signal, QSignalBlocker
from PySide6.QtGui import QColor, QIcon, QFontDatabase, QKeySequence
import backend

# ─── Design System (Single Source of Truth) ───
from ui.design_tokens import C, SP, FONT, FONT_MONO, load_qss, lighten, darken
import ui.panels as panels
from ui.components.button import _make_pill_qss, _make_circle_qss
from ui.components.waveform_hero import WaveformHeroPanel
from ui.components.painter_button import PainterButton
from core.ytdlp_support import extract_info_with_auth, make_ydl_opts

# ─── Accessibility (TTS, theme, shortcuts) ───
from core.accessibility import Speaker, Announcer, ThemeManager, register_shortcuts
from core.accessibility.speaker import get_speaker

# ─── MIDI CC MAPPING (đọc từ app_config.json) ───
try:
    MIDI_CC = backend.AppConfig.get_midi_cc()
    SCALE_VALUES = backend.AppConfig.get_scale_values()
except Exception as e:
    print(f"[CONFIG] Khong doc duoc app_config.json, dung gia tri mac dinh: {e}")
    MIDI_CC = {}
    SCALE_VALUES = {}

# ─── GLOBAL QSS (loaded from ui/styles/main.qss) ───
APP_QSS = load_qss()

# ─── Backward-compat aliases (used heavily in dialogs/callbacks below) ───
_lighten = lighten
_darken = darken

def pill_btn_qss(color, hover=None, size=13, radius=12):
    return _make_pill_qss(color, hover, size, radius)

def circle_btn_qss(color, sz=24):
    return _make_circle_qss(color, sz)

_fonts_loaded = False

def _load_fonts():
    """Register Be Vietnam Pro TTF files with Qt. Idempotent — safe to call multiple times."""
    global _fonts_loaded
    if _fonts_loaded:
        return
    _fonts_loaded = True
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    font_dir = os.path.join(base, 'Be_Vietnam_Pro')
    if not os.path.isdir(font_dir):
        return
    for fname in os.listdir(font_dir):
        if fname.lower().endswith('.ttf'):
            QFontDatabase.addApplicationFont(os.path.join(font_dir, fname))


def add_shadow(widget, color="#000000", blur=20, offset=(0, 4)):
    """Thêm drop-shadow cho widget — bỏ qua nếu GPU không hỗ trợ"""
    try:
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(blur)
        shadow.setColor(QColor(color))
        shadow.setOffset(*offset)
        widget.setGraphicsEffect(shadow)
    except Exception:
        pass






# ══════════════════════════════════════════════════════
#  MAIN DASHBOARD
# ══════════════════════════════════════════════════════
class MainDashboard(QMainWindow):
    """Cửa sổ chính Quang Lưu Studio — PySide6"""

    # Signal cho thread-safe UI updates
    _autokey_signal = Signal(dict)
    _tone_result_signal = Signal(dict)
    _midi_cc_signal = Signal(int, int)
    
    _midi_status_signal = Signal()
    _browser_status_signal = Signal()
    _message_signal = Signal(str, bool)
    _score_report_signal = Signal(dict)
    _score_btn_reset_signal = Signal()

    @property
    def _marquee_text(self):
        return self._marquee_text_value

    @_marquee_text.setter
    def _marquee_text(self, value):
        self._marquee_text_value = value
        if self._marquee_widget is not None:
            self._marquee_widget.setText(value)

    def __init__(self, settings=None):
        self._ensure_app()
        super().__init__()
        # Backend
        self.engine = backend.SystemEngine(settings)
        self.settings = settings or {}

        # State
        self.tone_music_value = 0
        self.tone_voice_value = 0
        self.current_mode = "Đa Thể Loại"
        self.is_recording = False
        self.current_tone = "C"
        self.current_score = None
        self.be_state = False
        self.vang_state = False
        self.fix_meo_state = False
        self.mute_states = {
            "mix_music": False, "mix_mic": False,
            "mix_reverb": False, "mix_backing": False
        }
        self.autokey_active = False
        self.tune_state = True
        self.fix_meo_state = False
        self.current_scale = "Major"
        self.is_dev_mode = False

        self._mixer_channels = {}

        # Widgets / timers populated by _build_* — init to None so hot paths can
        # do `is None` checks instead of `hasattr` probes.
        self._marquee_widget = None
        self._marquee_timer = None
        self._waveform = None
        self._func_buttons = {}
        self._mode_buttons = {}
        self._mode_colors = {}
        self._marquee_text_value = ""

        # Expose module-level config to panels (avoids circular imports in ui/panels/*)
        self.MIDI_CC = MIDI_CC
        self.SCALE_VALUES = SCALE_VALUES

        # Window — Performance Stage: 1100×650
        self.setWindowTitle("Quang Lưu Studio")
        self.setWindowIcon(QIcon("app_icon.ico"))
        self.setMinimumWidth(780)
        self._autotune_on = False
        self.setStyleSheet(APP_QSS)

        # Central widget
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Marquee text (used by SmoothMarqueeLabel component)
        self._marquee_text = "Bản quyền Quang Lưu Studio"

        # Build UI — V5.0: Performance Stage (waveform hero + tabbed dock)
        root.addWidget(self._build_header())
        
        self._body_wrapper = QWidget()
        self._body_layout = QVBoxLayout(self._body_wrapper)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.addWidget(self._build_body())
        root.addWidget(self._body_wrapper, 1)
        
        root.addWidget(self._build_bottom_bar())

        compact_min_h = max(200, self.minimumSizeHint().height())
        self.setMinimumHeight(compact_min_h)
        self.setMinimumWidth(780)
        
        # Restore window geometry or use default
        geom = self.settings.get("window_geometry")
        if geom:
            self.resize(geom.get("width", 850), geom.get("height", max(compact_min_h + 20, 280)))
            self.move(geom.get("x", 100), geom.get("y", 100))
        else:
            self.resize(850, max(compact_min_h + 20, 280))

        # MIDI
        self.engine.register_midi_callback(self.on_midi_status_changed)
        self._update_midi_status()

        # Signal connections (for thread-safe UI updates)
        self._autokey_signal.connect(self._update_autokey_ui)
        self._tone_result_signal.connect(self._handle_tone_result)
        
        self.engine.on_midi_cc_callback = lambda cc, v: self._midi_cc_signal.emit(cc, v)
        self._midi_cc_signal.connect(self._on_midi_cc_received)
        
        self._midi_status_signal.connect(self._update_midi_status)
        self._browser_status_signal.connect(self._update_browser_status)
        self._message_signal.connect(self._show_message)
        self._score_report_signal.connect(self._show_scoring_report)
        self._score_btn_reset_signal.connect(self._reset_score_btn)

        # Status check timer (5s MIDI, 2s Browser)
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_midi_status)
        self._status_timer.timeout.connect(self._update_browser_status)
        self._status_timer.start(2500)

        # Auto launch (Studio One + Browser theo settings)
        self._auto_launch_apps()

        # YouTube URL Watcher — tự động dò tone khi mở YouTube
        self._start_youtube_watcher()

        # Accessibility — TTS, theme, shortcuts (sau khi UI đã build xong)
        self._init_accessibility()

        # Đồng bộ chế độ mặc định lúc khởi động
        self._on_mode_selected(self.current_mode, toggle=False)
        
        # Dev Mode Shortcut
        from PySide6.QtGui import QShortcut, QKeySequence
        self._dev_mode_shortcut = QShortcut(QKeySequence("Ctrl+Shift+D"), self)
        self._dev_mode_shortcut.activated.connect(self._toggle_dev_mode)

    def _toggle_dev_mode(self):
        self.is_dev_mode = not self.is_dev_mode
        self._show_message(f"Dev Mode: {'ON' if self.is_dev_mode else 'OFF'}")
        self.refresh_ui()

    def refresh_ui(self):
        # Clear body layout
        for i in reversed(range(self._body_layout.count())):
            widget = self._body_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        
        # Rebuild body
        self._body_layout.addWidget(self._build_body())

    def _on_add_widget(self, panel_name, widget_type):
        from ui.dialogs.widget_builder import WidgetBuilderDialog
        dialog = WidgetBuilderDialog(self, panel_name=panel_name, widget_type=widget_type)
        if dialog.exec() == QDialog.Accepted and dialog.result_data:
            ui_config = backend.UiConfigManager.load_ui_config()
            panel_list = ui_config.get(panel_name, [])
            panel_list.append(dialog.result_data)
            ui_config[panel_name] = panel_list
            backend.UiConfigManager.save_ui_config(ui_config)
            self.refresh_ui()

    def _on_edit_widget(self, panel_name, widget_data):
        from ui.dialogs.widget_builder import WidgetBuilderDialog
        dialog = WidgetBuilderDialog(self, panel_name=panel_name, widget_type=widget_data.get("type", "slider"), existing_data=widget_data)
        if dialog.exec() == QDialog.Accepted and dialog.result_data:
            ui_config = backend.UiConfigManager.load_ui_config()
            panel_list = ui_config.get(panel_name, [])
            for i, item in enumerate(panel_list):
                if item.get("id") == widget_data.get("id"):
                    panel_list[i] = dialog.result_data
                    break
            ui_config[panel_name] = panel_list
            backend.UiConfigManager.save_ui_config(ui_config)
            self.refresh_ui()
            
    def _on_hide_widget(self, panel_name, widget_data):
        ui_config = backend.UiConfigManager.load_ui_config()
        panel_list = ui_config.get(panel_name, [])
        for i, item in enumerate(panel_list):
            if item.get("id") == widget_data.get("id"):
                panel_list[i]["hidden"] = True
                break
        ui_config[panel_name] = panel_list
        backend.UiConfigManager.save_ui_config(ui_config)
        self.refresh_ui()

    # ─────────────────────────────────────────
    #  HEADER (55px — Golden Ratio compact)
    # ─────────────────────────────────────────
    def _build_header(self):
        return panels.build_header(self)

    # ─────────────────────────────────────────
    #  BODY — Performance Stage (Waveform Hero + 4-Panel Dock)
    # ─────────────────────────────────────────
    def _build_body(self):
        wrapper = QWidget()
        wrapper.setStyleSheet(f"background-color: {C['bg']};")
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(SP.SM, 2, SP.SM, 2)
        wl.setSpacing(4)

        # ── Hàng 1: Mixer + Mode + Tools ──
        top_dock = QHBoxLayout()
        top_dock.setSpacing(6)
        top_dock.addWidget(self._build_panel_mixer(), 35)
        top_dock.addWidget(self._build_panel_mode(), 35)
        top_dock.addWidget(self._build_panel_tools(), 30)
        wl.addLayout(top_dock)

        return wrapper


    # ── Panel 1: MIXER ────────────────────────────────────
    def _build_panel_mixer(self):
        return panels.build_panel_mixer(self)

    # ── Panel 4: TOOLS & TONE ────────────────────────────────────
    def _build_panel_tools(self):
        return panels.build_panel_tools(self)

    # ── Panel 3: MODE & SFX ───────────────────────────────
    def _build_panel_mode(self):
        return panels.build_panel_mode(self)

    # ─────────────────────────────────────────
    #  BOTTOM BAR — Record button
    # ─────────────────────────────────────────
    def _build_bottom_bar(self):
        return panels.build_bottom_bar(self)

    # ══════════════════════════════════════════
    #  CALLBACKS (giữ nguyên logic từ CTk frontend)
    # ══════════════════════════════════════════

    def _sync_scale_button(self, is_major):
        """Cập nhật nút Major/Minor toggle theo trạng thái scale hiện tại."""
        scale_btn = self._func_buttons.get("Major") or self._func_buttons.get("Minor")
        if not scale_btn:
            return
        if is_major:
            scale_btn.setText("Major")
            scale_btn.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.12), 11, 14))
        else:
            scale_btn.setText("Minor")
            scale_btn.setStyleSheet(pill_btn_qss(C["orange"], _lighten(C["orange"], 0.12), 11, 14))

    def _on_tone_selected(self, value):
        self.current_tone = value
        key_midi_map = backend.AppConfig.get_key_midi_map()
        key_midi = key_midi_map.get(value, 0)
        self.engine.send_midi(MIDI_CC["key_root"], key_midi)

    def _on_scale_selected(self, value):
        self.current_scale = value
        self.scale_is_major = (value == "Major")
        scale_midi_map = backend.AppConfig.get_scale_midi_map()
        # Dùng "scale_type" — CC key thống nhất toàn bộ code
        scale_midi = scale_midi_map.get(value, 13)
        self.engine.send_midi(MIDI_CC.get("scale_type", MIDI_CC.get("key_scale", 35)), scale_midi)
        self._sync_scale_button(self.scale_is_major)

    def _update_midi_status(self):
        try:
            connected = self.engine.is_midi_connected()
        except Exception:
            connected = False
        if connected:
            try:
                name = self.engine.get_midi_port_name()
                if "QuangLuuMIDI" not in name:
                    self._midi_dot.setStyleSheet(f"color: {C['accent']}; font-size: 10px;")
                else:
                    self._midi_dot.setStyleSheet(f"color: {C['teal']}; font-size: 10px;")
            except Exception:
                pass
        else:
            self._midi_dot.setStyleSheet(f"color: {C['accent']}; font-size: 10px;")
        # Sync waveform hero MIDI status
        if self._waveform is not None:
            self._waveform.set_midi_status(connected)

    def _update_browser_status(self):
        """Cập nhật đèn báo trạng thái trình duyệt (CDP/WinRT)."""
        cdp_connected = getattr(self.engine.cdp_monitor, 'is_connected', False)
        
        # Check WinRT fallback logic
        win_media = getattr(self.engine, 'media_monitor', None)
        winrt_active = False
        if win_media and not cdp_connected:
            winrt_active = (win_media.current_title != "") or win_media.is_playing

        if cdp_connected:
            # CDP Kết nối thành công (Xanh lá - Chế độ cao nhất)
            self._browser_dot.setStyleSheet(f"color: {C['green']}; font-size: 10px;")
        elif winrt_active:
            # WinRT Kết nối (Vàng/Cam - Chế độ fallback)
            self._browser_dot.setStyleSheet(f"color: {C['orange']}; font-size: 10px;")
        else:
            # Không có kết nối (Đỏ/Accent)
            self._browser_dot.setStyleSheet(f"color: {C['accent']}; font-size: 10px;")

    def _on_midi_cc_received(self, cc, value):
        # Khi MIDI CC đến → cập nhật UI combobox mà KHÔNG re-emit send_midi.
        # Dùng QSignalBlocker (RAII) thay vì flag toàn cục — đúng idiom Qt.
        try:
            if cc == int(MIDI_CC.get("key_root", 34)):
                # Reverse-lookup: tìm key có MIDI value gần nhất trong KEY_MIDI_MAP
                keys = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
                best_key = "C"
                best_diff = 999
                for k in keys:
                    midi_val = backend.AppConfig.get_key_midi_map().get(k, 0)
                    diff = abs(midi_val - value)
                    if diff < best_diff:
                        best_diff = diff
                        best_key = k
                if self.tone_combo.currentText() != best_key:
                    with QSignalBlocker(self.tone_combo):
                        self.tone_combo.setCurrentText(best_key)
                self.current_tone = best_key
            elif cc == int(MIDI_CC.get("scale_type", MIDI_CC.get("key_scale", 35))):
                # Reverse-lookup: tìm scale có MIDI value gần nhất
                _smap = backend.AppConfig.get_scale_midi_map()
                major_val = _smap.get("Major", 13)
                minor_val = _smap.get("Minor", 18)
                scale_str = "Minor" if abs(value - minor_val) < abs(value - major_val) else "Major"
                self.current_scale = scale_str
                self.scale_is_major = (scale_str == "Major")
                if hasattr(self, 'scale_combo') and self.scale_combo.currentText() != scale_str:
                    with QSignalBlocker(self.scale_combo):
                        self.scale_combo.setCurrentText(scale_str)
                self._sync_scale_button(self.scale_is_major)
            
            # --- Xử lý phản hồi Mute từ MIDI ---
            mute_cc_to_key = {
                int(MIDI_CC.get("mute_music", 50)): "mix_music",
                int(MIDI_CC.get("mute_mic", 51)): "mix_mic",
                int(MIDI_CC.get("mute_reverb", 52)): "mix_reverb",
                int(MIDI_CC.get("mute_backing", 53)): "mix_backing",
            }
            if cc in mute_cc_to_key:
                key = mute_cc_to_key[cc]
                is_muted = (value >= 64)
                self.mute_states[key] = is_muted
                if key in self._mixer_channels:
                    self._mixer_channels[key].set_muted(is_muted)
                    print(f"[MIDI SYNC] {key} -> {'MUTED' if is_muted else 'ACTIVE'} (Value {value})")

            # --- Xử lý phản hồi Toggles khác ---
            if cc == int(MIDI_CC.get("tone_auto", 31)):
                self.tune_state = (value >= 64)
                btn = self._func_buttons.get("Auto-Tune")
                if btn: btn.setActive(self.tune_state)
            
            if cc == int(MIDI_CC.get("fix_meo", 36)):
                self.fix_meo_state = (value >= 64)
                btn = self._func_buttons.get("Fix Méo")
                if btn: btn.setActive(self.fix_meo_state)

            # --- Xử lý phản hồi Chế độ (Mode) từ MIDI ---
            try:
                mode_config = backend.AppConfig.get_mode_config()
            except Exception:
                mode_config = {
                    "Dân Ca": {"cc": 30, "on_value": 127, "off_value": 0},
                    "Lofi": {"cc": 37, "on_value": 127, "off_value": 0},
                    "Remix": {"cc": 38, "on_value": 127, "off_value": 0},
                    "Đa Thể Loại": {"cc": 39, "on_value": 127, "off_value": 0}
                }

            mode_changed = False
            for m_name, cfg in mode_config.items():
                m_cc = int(cfg.get("cc", 30))
                if cc == m_cc:
                    on_val = int(cfg.get("on_value", 127))
                    off_val = int(cfg.get("off_value", 0))

                    if value == on_val:
                        self.current_mode = m_name
                        mode_changed = True
                        break
                    elif value == off_val and self.current_mode == m_name:
                        self.current_mode = None
                        mode_changed = True
                        break

            if mode_changed:
                for m, btn in self._mode_buttons.items():
                    base = self._mode_colors.get(m, C["card_hover"])
                    if m == self.current_mode:
                        btn.setStyleSheet(f"""
                            QPushButton {{
                                background-color: {_lighten(base, 0.25)};
                                color: white; border: 2px solid white;
                                border-radius: 10px; font-size: 10px; font-weight: 700;
                                font-family: {FONT};
                            }}
                            QPushButton:hover {{ background-color: {_lighten(base, 0.3)}; }}
                        """)
                    else:
                        btn.setStyleSheet(pill_btn_qss(base, _lighten(base, 0.15), 10, 10))
                print(f"[MIDI SYNC] Cập nhật Mode thành: {self.current_mode}")

        except Exception as e:
            print(f"[MIDI SYNC] UI MIDI Sync Error: {e}")

    def on_midi_status_changed(self, connected, port_name=None):
        self._midi_status_signal.emit()

    def _auto_launch_apps(self):
        """Tự động mở Studio One và/hoặc YouTube browser khi khởi động (theo settings)."""
        # Studio One
        if self.settings.get("auto_launch_studio_one", False):
            studio_one_path = self.settings.get("studio_one_path", "")
            if studio_one_path and os.path.exists(studio_one_path):
                try:
                    self.engine.launch_app(studio_one_path)
                except Exception:
                    pass
        # Browser YouTube
        if self.settings.get("auto_launch_browser", False):
            browser_path = self.settings.get("browser_path", "")
            if browser_path:
                # Extract exe path (may have extra args like PWA --app-id=...)
                _exe = backend.SystemEngine._parse_browser_path(browser_path)[0]
                if os.path.exists(_exe):
                    try:
                        self.engine.launch_app(browser_path, is_web=True)
                    except Exception:
                        pass

    def _show_settings_dialog(self):
        from ui.dialogs.settings_dialog import SettingsDialog
        SettingsDialog(self).exec()

    def _show_calibration_wizard(self):
        from ui.dialogs.calibration import CalibrationWizardDialog
        CalibrationWizardDialog(self).exec()
        global SCALE_VALUES
        SCALE_VALUES = backend.AppConfig.get_scale_values()

    def _start_youtube_watcher(self):
        """Khởi động YouTube URL Watcher với callbacks thread-safe."""
        def _auto_on_complete(result):
            self._tone_result_signal.emit(result)

        def _auto_on_error(msg):
            # Route error qua signal để UI reset marquee + button state
            print(f"[YT WATCHER] Auto-detect loi: {msg}")
            self._tone_result_signal.emit({'error': msg, 'auto_detected': True})

        def _auto_on_progress(text):
            # Chỉ hiện "Đang dò..." trên marquee, không hiện chi tiết
            if not getattr(self, '_do_tone_running', False):
                self._marquee_text = "♪ Đang dò... ♪"
        
        self.engine.on_auto_tone_complete = _auto_on_complete
        self.engine.on_tone_detected_callback = _auto_on_complete
        self.engine.on_auto_tone_error = _auto_on_error
        self.engine.on_auto_tone_progress = _auto_on_progress
        self.engine.start_youtube_watcher()

    # ── Menu Button Callbacks ──
    def _on_toggle_scan_mode(self):
        btn = self._func_buttons.get("Chế độ: Nhanh") or self._func_buttons.get("Chế độ: Full")
        current_mode = getattr(self.engine, 'tone_scan_mode', 'fast')
        if current_mode == 'fast':
            self.engine.tone_scan_mode = 'full'
            if btn:
                old_key = btn.text()
                btn.setText("Chế độ: Full")
                btn.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.12), 11, 14))
                if old_key in self._func_buttons:
                    self._func_buttons["Chế độ: Full"] = self._func_buttons.pop(old_key)
            self._show_message("Chế độ: Dò Full")
        else:
            self.engine.tone_scan_mode = 'fast'
            if btn:
                old_key = btn.text()
                btn.setText("Chế độ: Nhanh")
                btn.setStyleSheet(pill_btn_qss(C["orange"], _lighten(C["orange"], 0.12), 11, 14))
                if old_key in self._func_buttons:
                    self._func_buttons["Chế độ: Nhanh"] = self._func_buttons.pop(old_key)
            self._show_message("Chế độ: Dò Nhanh")

    def _set_rescan_button_state(self, state: str):
        """Centralized button state: 'idle' | 'running' | 'cancel'.
        Avoids duplicating button-style logic across 3 code paths."""
        btn = (self._func_buttons.get("Dò Lại")
               or self._func_buttons.get("⏳ Đang dò...")
               or self._func_buttons.get("❌ Huỷ"))
        if not btn:
            return
        old_key = btn.text()
        if state == "idle":
            btn.setEnabled(True)
            btn.setText("Dò Lại")
            btn.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.12), 11, 14))
        elif state == "running":
            btn.setEnabled(True)
            btn.setText("❌ Huỷ")
            btn.setStyleSheet(pill_btn_qss(C["accent"], _lighten(C["accent"], 0.12), 11, 14))
        # Update _func_buttons key to match the new text
        if old_key != btn.text() and old_key in self._func_buttons:
            self._func_buttons[btn.text()] = self._func_buttons.pop(old_key)

    def _on_cancel_rescan(self):
        """Cancel a running rescan — called from button click on main thread."""
        self.engine._tone_session.stop()
        self._do_tone_running = False
        self._set_rescan_button_state("idle")
        self.autokey_dot.setStyleSheet(f"color: {C['card_hover']}; font-size: 16px;")
        self._marquee_text = "♪ Quang Lưu Studio — Karaoke Pro ♪"
        self._show_message("Đã huỷ dò tone")

    def _on_force_rescan(self):
        # If already running → treat as cancel
        if getattr(self, '_do_tone_running', False):
            self._on_cancel_rescan()
            return
        self._do_tone_running = True
        
        self._set_rescan_button_state("running")
        self.autokey_dot.setStyleSheet(f"color: {C['orange']}; font-size: 16px;")
        self._marquee_text = "♪ Đang dò lại... ♪"

        import weakref
        url = getattr(self.engine, 'current_youtube_url', None)
        # Single stop() — Tier 1.3: pulled before if/else to avoid double call
        self.engine._tone_session.stop()
        if url:
            self._show_message("Đang dò lại...")
            self.engine._dispatch_auto_detect(url, weakref.ref(self.engine), skip_resolve=True)
        else:
            self._show_message("Đang quét trình duyệt...")
            
            def _on_complete(result):
                self._tone_result_signal.emit(result)
            def _on_error(msg):
                self._tone_result_signal.emit({'error': msg})
                
            self.engine.detect_tone_from_browser(
                on_complete=_on_complete,
                on_error=_on_error,
                on_progress=lambda x: None,
                skip_resolve=True
            )


    def _update_autokey_ui(self, result):
        """Cập nhật UI khi AutoKey phát hiện tone mới (nếu dùng AutoKey ở nơi khác)"""
        key = result.get("key", "")
        scale = result.get("scale", "")
        if key and self.tone_combo.currentText() != key:
            self.tone_combo.setCurrentText(key)
            self.current_tone = key
        if scale:
            if self.scale_combo.currentText() != scale:
                self.scale_combo.setCurrentText(scale)
            self.current_scale = scale
            self.scale_is_major = (scale == "Major")
            # Đồng bộ nút Major/Minor toggle button
            scale_btn = self._func_buttons.get("Major") or self._func_buttons.get("Minor")
            if scale_btn:
                if self.scale_is_major:
                    scale_btn.setText("Major")
                    scale_btn.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.12), 11, 14))
                else:
                    scale_btn.setText("Minor")
                    scale_btn.setStyleSheet(pill_btn_qss(C["orange"], _lighten(C["orange"], 0.12), 11, 14))

    def _handle_tone_result(self, result):
        """Slot xử lý kết quả dò tone trên main thread (thread-safe via Signal)"""
        
        # === Trường hợp LỖI ===
        if 'error' in result:
            msg = result['error']
            self._do_tone_running = False
            self._do_tone_done = False
            self._set_rescan_button_state("idle")
            self.autokey_dot.setStyleSheet(f"color: {C['card_hover']}; font-size: 16px;")
            self._marquee_text = "♪ Quang Lưu Studio — Karaoke Pro ♪"
            self._show_message(f"❌ {msg}", is_error=True)
            return
        
        # === Trường hợp THÀNH CÔNG ===
        self._do_tone_running = False
        
        # Nếu là auto-detect → cập nhật trạng thái nút mà không cần user nhấn trước
        is_auto = result.get('auto_detected', False)
        
        # === 1. Cập nhật Key/Scale lên UI chính ===
        key_display = result.get('key_display', 'C')
        # Trích xuất key root chính xác: "C#m" → "C#", "Am" → "A", "D" → "D"
        if key_display.endswith('#m'):
            key_root = key_display[:-1]  # "C#m" → "C#"
        elif key_display.endswith('m') and len(key_display) >= 2:
            key_root = key_display[:-1]   # "Am" → "A", "Cm" → "C"
        else:
            key_root = key_display         # "D" → "D", "F#" → "F#"
        key_root = result.get('key', key_root)
        scale = result.get('scale', 'Major')
        title = result.get('title', '')
        
        # Tránh gửi MIDI trùng lặp khi set combo (backend đã gửi rồi)
        self.current_tone = key_root
        self.current_scale = scale
        with QSignalBlocker(self.tone_combo):
            self.tone_combo.setCurrentText(key_root)
        with QSignalBlocker(self.scale_combo):
            self.scale_combo.setCurrentText(scale)
        
        # Đổi style combobox → nền trong suốt, text xanh lá, viền trắng
        detected_combo_qss = f"""
            QComboBox {{
                background-color: transparent;
                color: {C['green']};
                border: 2px solid rgba(255, 255, 255, 0.85);
                border-radius: 8px;
                padding: 4px 10px;
                font-size: 13px;
                font-weight: 700;
                font-family: {FONT};
            }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background-color: {C['card']};
                color: {C['text']};
                selection-background-color: {C['green']};
                border: 1px solid rgba(255, 255, 255, 0.5);
                font-size: 13px;
                font-family: {FONT};
            }}
        """
        self.tone_combo.setStyleSheet(detected_combo_qss)
        self.scale_combo.setStyleSheet(detected_combo_qss)
        
        bpm = result.get('bpm', 0)
        camelot = result.get('camelot', '?')
        confidence = result.get('confidence', 0)
        
        # === 2. Reset nút "Dò Lại" về trạng thái ban đầu ===
        self._set_rescan_button_state("idle")
        
        # === 3. Cập nhật dot → xanh (đã phát hiện) ===
        self.autokey_dot.setStyleSheet(f"color: {C['green']}; font-size: 16px;")
        
        # === Sync waveform hero ===
        if self._waveform is not None:
            self._waveform.set_song_info(title, key_root, scale, bpm)
        
        # === 4. Đồng bộ nút Major/Minor toggle ===
        self.scale_is_major = (scale == "Major")
        scale_btn = self._func_buttons.get("Major") or self._func_buttons.get("Minor")
        if scale_btn:
            if self.scale_is_major:
                scale_btn.setText("Major")
                scale_btn.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.12), 11, 14))
            else:
                scale_btn.setText("Minor")
                scale_btn.setStyleSheet(pill_btn_qss(C["orange"], _lighten(C["orange"], 0.12), 11, 14))
        
        # === 5. Hiển thị tên bài hát + kết quả lên Marquee (giữ nguyên Window Title) ===
        # Chỉ cập nhật nội dung marquee nếu đây là kết quả dò toàn bài (không phải sự kiện chuyển timeline)
        if 'time' not in result:
            timeline = result.get('timeline', [])
            if timeline and len(timeline) > 1:
                # Có nhiều đoạn chuyển tone → hiển thị chuỗi tone
                tone_chain = " → ".join(e.get('key_display', '?') for e in timeline)
                if title:
                    self._marquee_text = f"🎵 {title}   ★   {tone_chain}"
                else:
                    self._marquee_text = f"🎵 {tone_chain}"
            elif title:
                self._marquee_text = f"🎵 {title}   ★   {key_display} {scale}"
            else:
                self._marquee_text = f"🎵 {key_display} {scale}"
        
        # === 6. Auto-save vào Danh sách bài hát ===
        url = result.get('url', '')
        if url and title and key_root:
            import backend
            def _auto_save():
                backend.SongManager.add_song(title, url, key_root)
            threading.Thread(target=_auto_save, daemon=True).start()

    def _on_tone_auto(self):
        self.tune_state = not getattr(self, 'tune_state', True)
        val = 127 if self.tune_state else 0
        self.engine.send_midi(MIDI_CC["tone_auto"], val)
        btn = self._func_buttons.get("Auto-Tune")
        if btn:
            btn.setActive(self.tune_state)
        print(f"[TONE AUTO] -> {'ON' if self.tune_state else 'OFF'} (Value {val})")

    def _on_fix_meo(self):
        self.fix_meo_state = not getattr(self, 'fix_meo_state', False)
        val = 127 if self.fix_meo_state else 0
        
        # Ưu tiên dùng giá trị cân chỉnh trong mode_midi_map nếu có
        mode_map = backend.AppConfig.get_mode_midi_map()
        cc_num = int(MIDI_CC.get("fix_meo", 36))
        if "Fix Méo" in mode_map:
            # Nếu dùng mode_map thì thường là giá trị cố định, nhưng ta vẫn dùng toggle logic
            midi_val = mode_map["Fix Méo"] if self.fix_meo_state else 0
            self.engine.send_midi(cc_num, midi_val)
        else:
            # Fallback dùng giá trị mặc định 127/0
            self.engine.send_midi(cc_num, val)
        
        btn = self._func_buttons.get("Fix Méo")
        if btn:
            btn.setActive(self.fix_meo_state)
        print(f"[FIX MEO] -> {'ON' if self.fix_meo_state else 'OFF'} (Value {val})")

    def _on_scale_toggle(self):
        """Toggle Major ↔ Minor"""
        self.scale_is_major = not getattr(self, 'scale_is_major', True)
        if self.scale_is_major:
            self.engine.send_midi(MIDI_CC["scale_type"], SCALE_VALUES.get("major", 13))
            if hasattr(self, 'scale_combo'):
                self.scale_combo.setCurrentText("Major")
        else:
            self.engine.send_midi(MIDI_CC["scale_type"], SCALE_VALUES.get("minor", 18))
            if hasattr(self, 'scale_combo'):
                self.scale_combo.setCurrentText("Minor")
        btn = self._func_buttons.get("Major")
        if btn:
            if self.scale_is_major:
                color = C["green"]
                btn.setText("Major")
            else:
                color = C["orange"]
                btn.setText("Minor")
            btn.setStyleSheet(pill_btn_qss(color, _lighten(color, 0.12), 11, 14))

    def _on_score(self):
        btn = self._func_buttons.get("Chấm điểm")
        
        if self.engine.quick_score_active:
            # Tắt chấm điểm bằng tay nếu đang chạy
            self.engine.stop_quick_score(cancel=True)
            if btn:
                btn.setText("") # Về lại icon mode
                btn.setStyleSheet(pill_btn_qss(C["light_purple"], _lighten(C["light_purple"], 0.12), 11, 14))
            self._show_message("Đã huỷ chấm điểm")
        else:
            # Bật chấm điểm
            def on_score_ready(result):
                # Reset UI
                self._score_btn_reset_signal.emit()
                
                if "error" in result:
                    self._message_signal.emit(f"Lỗi chấm điểm: {result['error']}", True)
                else:
                    self._score_report_signal.emit(result)
                    
            lb_idx = self.settings.get("record_loopback_device", -1)
            mic_idx = self.settings.get("record_mic_device", -1)
            
            # Pass current key for key conformity analysis
            key_ref = getattr(self, 'current_tone', None)
            
            self._show_message("Đang chấm điểm...")
            if btn:
                btn.setText("Đang ghi (chờ kết thúc)")
                btn.setStyleSheet(pill_btn_qss(C["accent"], _darken(C["accent"], 0.2), 11, 14))
                
            self.engine.start_quick_score(lb_idx, mic_idx, on_ready=on_score_ready, on_error=lambda err: self._message_signal.emit(err, True), key_reference=key_ref)

    def _reset_score_btn(self):
        btn = self._func_buttons.get("Chấm điểm") or self._func_buttons.get("Đang ghi (chờ kết thúc)")
        if btn:
            btn.setText("")
            btn.setStyleSheet(pill_btn_qss(C["light_purple"], _lighten(C["light_purple"], 0.12), 11, 14))
            if "Đang ghi (chờ kết thúc)" in self._func_buttons:
                self._func_buttons["Chấm điểm"] = self._func_buttons.pop("Đang ghi (chờ kết thúc)")

    def _show_scoring_report(self, result: dict):
        from ui.dialogs.scoring_report import ScoringReportDialog
        ScoringReportDialog(self, result).exec()

    def _show_message(self, text, is_error=False):
        """Show temporary message box in center of dashboard"""
        lbl = QLabel(text, self)
        color = C["accent"] if is_error else C["green"]
        font_size = 14 if is_error else 11
        padding = "10px 20px" if is_error else "6px 12px"
        lbl.setStyleSheet(f"background-color: {C['card']}; color: {color}; border: 1px solid {color}; border-radius: 8px; padding: {padding}; font-size: {font_size}px; font-weight: bold; font-family: {FONT};")
        lbl.adjustSize()
        lbl.move(self.width()//2 - lbl.width()//2, self.height()//2 - lbl.height()//2)
        lbl.show()
        QTimer.singleShot(2000 if not is_error else 4000, lbl.deleteLater)

    def _on_save(self):
        """Lưu bài hát thông minh (Quick Save)"""
        auto_url = getattr(self.engine, 'current_youtube_url', '') or ''
        auto_tone = getattr(self, 'current_tone', 'C')
        
        # Nếu có URL đang phát → lưu thẳng
        if auto_url:
            self._process_quick_save(auto_url, auto_tone)
            return
            
        # Không có URL → mở popup
        from PySide6.QtWidgets import QDialog, QLineEdit, QVBoxLayout, QHBoxLayout, QFrame as _QF
        dlg = QDialog(self)
        dlg.setWindowTitle("💾 Lưu bài hát")
        dlg.setFixedSize(520, 210)
        dlg.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")

        outer = QVBoxLayout(dlg)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # Header
        hdr = _QF()
        hdr.setStyleSheet(f"background-color: {C['card']}; border-bottom: 1px solid {C['border']};")
        hdr_lay = QVBoxLayout(hdr)
        hdr_lay.setContentsMargins(20, 14, 20, 12)
        title = QLabel("💾 Nhập URL bài hát cần lưu")
        title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {C['teal']}; font-family: {FONT}; background: transparent; border: none;")
        title.setAlignment(Qt.AlignCenter)
        hdr_lay.addWidget(title)
        outer.addWidget(hdr)

        body = QVBoxLayout()
        body.setContentsMargins(20, 14, 20, 14)
        body.setSpacing(10)

        url_input = QLineEdit()
        url_input.setPlaceholderText("https://www.youtube.com/watch?v=...")
        url_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {C['card']};
                color: {C['text']};
                border: 1px solid {C['border']};
                border-radius: 10px;
                padding: 10px 14px;
                font-size: 13px;
                font-family: {FONT};
            }}
            QLineEdit:focus {{ border-color: {C['teal']}; border-width: 2px; }}
        """)
        body.addWidget(url_input)

        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)
        save_btn = QPushButton("💾 Lưu")
        save_btn.setFixedHeight(38)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.1), 13, 12))
        cancel_btn = QPushButton("Hủy")
        cancel_btn.setFixedHeight(38)
        cancel_btn.setFixedWidth(80)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(pill_btn_qss(C["card_hover"], _lighten(C["card_hover"], 0.1), 13, 12))

        def save_from_url():
            url = url_input.text().strip()
            if not url or ("youtube.com" not in url and "youtu.be" not in url):
                self._show_message("⚠️ Vui lòng nhập URL YouTube hợp lệ", is_error=True)
                return
            dlg.accept()
            self._process_quick_save(url, auto_tone)
            
        save_btn.clicked.connect(save_from_url)
        cancel_btn.clicked.connect(dlg.reject)

        btn_box.addWidget(save_btn, 1)
        btn_box.addWidget(cancel_btn)
        body.addLayout(btn_box)

        body_widget = _QF()
        body_widget.setStyleSheet(f"background: {C['bg']}; border: none;")
        body_widget.setLayout(body)
        outer.addWidget(body_widget)
        dlg.exec()


    def _process_quick_save(self, url, tone):
        def _task():
            title = 'Bài hát không tên'
            save_tone = tone
            # Thử lấy từ timeline manual
            timeline_data = backend.ManualToneTimeline.load_timeline(url)
            if timeline_data:
                title = timeline_data.get('title', title)
                tl = timeline_data.get('timeline', [])
                if tl:
                    save_tone = tl[0].get('key_display', save_tone)
            else:
                try:
                    info = extract_info_with_auth(
                        url,
                        make_ydl_opts(skip_download=True),
                        download=False,
                        log_prefix="[QUICK SAVE]"
                    )
                    title = info.get('title', title)
                except Exception:
                    pass
            
            if backend.SongManager.add_song(title, url, save_tone):
                self._message_signal.emit(f"✅ Đã lưu: {title[:40]}", False)
            else:
                self._message_signal.emit("❌ Lỗi khi lưu bài hát", True)
                
        threading.Thread(target=_task, daemon=True).start()

    def _on_eye_toggle_studio_one(self):
        """Nút mắt: Ẩn/Hiện Studio One + cập nhật icon mắt nhắm/mở."""
        from ui.components.svg_icons import SVG_EYE_OPEN, SVG_EYE_CLOSED
        # Gọi logic ẩn/hiện PID-based
        self._on_toggle_studio_one()
        # Đảo trạng thái và cập nhật icon qua setSvg()
        self._studio_one_visible = not getattr(self, '_studio_one_visible', True)
        if hasattr(self, '_eye_btn'):
            new_svg = SVG_EYE_OPEN if self._studio_one_visible else SVG_EYE_CLOSED
            self._eye_btn.setSvg(new_svg)

    def _on_toggle_studio_one(self):
        """Ẩn/Hiện Studio One + tất cả plugin windows (theo PID, không theo title)."""
        try:
            import win32gui
            import win32con
            import win32process
            import psutil
        except ImportError:
            self._show_message("⚠️ pywin32 / psutil chưa được cài đặt", is_error=True)
            return

        # Bước 1: Thu thập PID của tất cả process Studio One
        STUDIO_ONE_EXE_KEYWORDS = ["studio one"]
        studio_pids = set()
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                name = (proc.info['name'] or '').lower()
                if any(kw in name for kw in STUDIO_ONE_EXE_KEYWORDS):
                    studio_pids.add(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if not studio_pids:
            self._show_message("⚠️ Không tìm thấy Studio One đang chạy", is_error=True)
            return

        # Bước 2: Tìm TẤT CẢ top-level windows thuộc các PID đó
        # (bao gồm plugin, mixer, instrument, effect windows)
        hwnd_list = []

        def _enum_cb(hwnd, _):
            if not win32gui.IsWindow(hwnd):
                return True
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid in studio_pids:
                    hwnd_list.append(hwnd)
            except Exception:
                pass
            return True

        win32gui.EnumWindows(_enum_cb, None)

        if not hwnd_list:
            self._show_message("⚠️ Studio One đang chạy nhưng không có cửa sổ nào", is_error=True)
            return

        # Bước 3: Xác định trạng thái hiện tại (visible nếu có ÍT NHẤT 1 cửa sổ đang hiện)
        any_visible = any(win32gui.IsWindowVisible(h) for h in hwnd_list)

        main_hwnd = None
        if any_visible:
            # Ẩn tất cả
            for h in hwnd_list:
                try:
                    win32gui.ShowWindow(h, win32con.SW_HIDE)
                except Exception:
                    pass
            self._show_message("Đã ẩn Studio One")
        else:
            # Hiện tất cả
            for h in hwnd_list:
                try:
                    win32gui.ShowWindow(h, win32con.SW_SHOW)
                    # Ghi nhớ cửa sổ chính (có "Studio One" trong title) để focus sau
                    title = win32gui.GetWindowText(h)
                    if "Studio One" in title and main_hwnd is None:
                        main_hwnd = h
                except Exception:
                    pass
            if main_hwnd:
                try:
                    win32gui.SetForegroundWindow(main_hwnd)
                except Exception:
                    pass
            self._show_message("Đã hiện Studio One")

    def _on_toggle_asiolink(self):
        """Ẩn/Hiện cửa sổ ASIOLINK (ASIO4ALL, ASIOVADPRO, ASIOLink Pro, v.v.)"""
        try:
            import win32gui
            import win32con
            import win32process
        except ImportError:
            self._show_message("⚠️ pywin32 chưa được cài đặt", is_error=True)
            return

        # Danh sách process name phổ biến của ASIO link/driver tools
        ASIO_PROCESS_NAMES = [
            "asiolink.exe", "asio link pro.exe", "asio link tool.exe",
            "asio4all.exe", "asio4allv2.exe", "asiovadpro.exe",
            "ASIOLink2.exe", "ASIOLinkTool.exe",
        ]
        ASIO_TITLE_KEYWORDS = [
            "ASIO Link", "ASIO4ALL", "ASIOVADPRO", "ASIO Pro",
        ]

        found_hwnds = []

        def _enum_cb(hwnd, _):
            if not win32gui.IsWindow(hwnd):
                return True
            # Kiểm tra theo process name (đáng tin hơn title)
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                import psutil
                proc_name = psutil.Process(pid).name().lower()
                if any(p.lower() in proc_name for p in ASIO_PROCESS_NAMES):
                    found_hwnds.append(hwnd)
                    return True
            except Exception:
                pass
            # Fallback: kiểm tra title
            title = win32gui.GetWindowText(hwnd)
            if any(kw in title for kw in ASIO_TITLE_KEYWORDS):
                if hwnd not in found_hwnds:
                    found_hwnds.append(hwnd)
            return True

        try:
            win32gui.EnumWindows(_enum_cb, None)
        except Exception as e:
            self._show_message(f"⚠️ Lỗi tìm ASIOLINK: {e}", is_error=True)
            return

        if not found_hwnds:
            self._show_message("⚠️ Không tìm thấy ASIOLINK đang chạy", is_error=True)
            # Reset state để lần sau tìm lại từ đầu
            self._asiolink_hidden = False
            return

        # Dùng state variable (_asiolink_hidden) — NOT IsWindowVisible()
        # IsWindowVisible trả về sai khi có child window chain hoặc đang loading
        is_hidden = getattr(self, '_asiolink_hidden', False)

        if not is_hidden:
            for h in found_hwnds:
                try:
                    win32gui.ShowWindow(h, win32con.SW_HIDE)
                except Exception:
                    pass
            self._asiolink_hidden = True
            # Cập nhật nút
            btn = self._func_buttons.get("🔊 ASIOLINK")
            if btn:
                btn.setText("🔊 ASIO [ẩn]")
            self._show_message("🙈 Đã ẩn ASIOLINK")
        else:
            for h in found_hwnds:
                try:
                    win32gui.ShowWindow(h, win32con.SW_SHOWNOACTIVATE)
                except Exception:
                    pass
            try:
                win32gui.SetForegroundWindow(found_hwnds[0])
            except Exception:
                pass
            self._asiolink_hidden = False
            # Khôi phục label nút
            btn = self._func_buttons.get("🔊 ASIO [ẩn]")
            if btn:
                btn.setText("🔊 ASIOLINK")
                self._func_buttons["🔊 ASIOLINK"] = self._func_buttons.pop("🔊 ASIO [ẩn]", btn)
            self._show_message("👁️ Đã hiện ASIOLINK")

    def _on_open_recordings_folder(self):
        """Mở thư mục lưu trữ file ghi âm"""
        recordings_dir = backend.RECORDINGS_DIR
        os.makedirs(recordings_dir, exist_ok=True)
        os.startfile(recordings_dir)

    def _on_record(self):
        import time, os
        from PySide6.QtWidgets import QFileDialog
         
        if self.is_recording:
            self.is_recording = False
            self.record_button.set_recording(False)
            self.engine.send_midi(MIDI_CC["score_trigger"], 0)
            
            # Dừng ghi âm và lưu file (không blocking UI)
            def handle_save():
                # Hiện dialog chọn nơi lưu trước
                recordings_dir = backend.RECORDINGS_DIR
                os.makedirs(recordings_dir, exist_ok=True)
                default_name = os.path.join(recordings_dir, f"QuangLuuStudio_Rec_{time.strftime('%Y%m%d_%H%M%S')}.wav")
                save_path, _ = QFileDialog.getSaveFileName(
                    self, "Lưu bản thu âm", default_name, "Audio Files (*.wav)",
                    options=QFileDialog.Option.DontUseNativeDialog
                )
                # stop_recording sẽ tự xử lý: dừng subprocess → lưu file
                if save_path:
                    if self.engine.recorder.stop_recording(save_path=save_path):
                        self._show_message(f"💾 Đã lưu bản thu: {os.path.basename(save_path)}")
                    else:
                        err = getattr(self.engine.recorder, 'last_error', None) or "File ghi âm rỗng hoặc không hợp lệ"
                        self._show_message(f"⚠️ Lưu thất bại: {err[:80]}", is_error=True)
                else:
                    self.engine.recorder.stop_recording(save_path=None)
                    self._show_message("⚠️ Đã hủy lưu bản thu.")
            
            QTimer.singleShot(100, handle_save)
        else:
            self.is_recording = True
            self.record_button.set_recording(True)
            self.engine.send_midi(MIDI_CC["score_trigger"], 127)
            
            # Bắt đầu ghi soundcard (loopback)
            lb_idx = self.settings.get("record_loopback_device", -1)
            # Mặc định tắt mic (-2) vì Studio One output đã chứa giọng hát.
            # Bật mic chỉ gây lặp tiếng khi dùng DAW.
            mic_idx = self.settings.get("record_mic_device", -2)
            ok = self.engine.recorder.start_recording(
                loopback_device_index=lb_idx,
                mic_device_index=mic_idx
            )
            if not ok:
                # Rollback UI
                self.is_recording = False
                self.record_button.set_recording(False)
                self.engine.send_midi(MIDI_CC["score_trigger"], 0)
                err = getattr(self.engine.recorder, 'last_error', None) or "Không tìm thấy thiết bị WASAPI Loopback"
                self._show_message(f"❌ Không thể ghi âm: {err[:80]}", is_error=True)

    def _on_mode_selected(self, mode, toggle=False):
        old_mode = self.current_mode
        if toggle and old_mode == mode:
            self.current_mode = None
        else:
            self.current_mode = mode

        # Load mode config từ AppConfig
        try:
            mode_config = backend.AppConfig.get_mode_config()
        except Exception:
            mode_config = {
                "Dân Ca": {"cc": 30, "on_value": 127, "off_value": 0},
                "Lofi": {"cc": 37, "on_value": 127, "off_value": 0},
                "Remix": {"cc": 38, "on_value": 127, "off_value": 0},
                "Đa Thể Loại": {"cc": 39, "on_value": 127, "off_value": 0}
            }

        # Gửi DUY NHẤT 1 tin nhắn MIDI CC tương ứng với sự thay đổi của nút vừa bấm
        if toggle and old_mode == mode:
            # Tắt chế độ đang chọn
            cfg = mode_config.get(mode)
            if cfg:
                cc_num = int(cfg.get("cc", 30))
                off_val = int(cfg.get("off_value", 0))
                self.engine.send_midi(cc_num, off_val)
                print(f"🎭 [MODE] Tắt {mode} -> MIDI CC {cc_num} Value {off_val}")
        else:
            # Bật chế độ mới
            cfg = mode_config.get(mode)
            if cfg:
                cc_num = int(cfg.get("cc", 30))
                on_val = int(cfg.get("on_value", 127))
                self.engine.send_midi(cc_num, on_val)
                print(f"🎭 [MODE] Bật {mode} -> MIDI CC {cc_num} Value {on_val}")

        # Cập nhật style trên UI cho tất cả các nút
        for m, btn in self._mode_buttons.items():
            base = self._mode_colors.get(m, C["card_hover"])
            if m == self.current_mode:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {_lighten(base, 0.25)};
                        color: white; border: 2px solid white;
                        border-radius: 10px; font-size: 10px; font-weight: 700;
                        font-family: {FONT};
                    }}
                    QPushButton:hover {{ background-color: {_lighten(base, 0.3)}; }}
                """)
            else:
                btn.setStyleSheet(pill_btn_qss(base, _lighten(base, 0.15), 10, 10))



    def _on_sfx_play(self, file_path: str):
        """Phát sound effect theo đường dẫn file (hỗ trợ wav, mp3, ogg, flac...)."""
        if not file_path:
            return
        if not os.path.exists(file_path):
            print(f"[SFX] Khong tim thay file SFX: {file_path}")
            return
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            from PySide6.QtCore import QUrl

            # Tạo player mới mỗi lần (cho phép chồng tiếng)
            player = QMediaPlayer(self)
            audio_out = QAudioOutput(self)
            player.setAudioOutput(audio_out)
            audio_out.setVolume(1.0)
            player.setSource(QUrl.fromLocalFile(file_path))
            player.play()

            # Dọn dẹp khi phát xong
            def _cleanup(status):
                if status == QMediaPlayer.EndOfMedia:
                    player.deleteLater()
                    audio_out.deleteLater()
            player.mediaStatusChanged.connect(_cleanup)

            print(f"[SFX] Playing: {os.path.basename(file_path)}")
        except Exception as e:
            print(f"[SFX] Loi phat SFX: {e}")
            # Fallback: winsound cho file .wav
            if file_path.lower().endswith(".wav"):
                def _play_fallback():
                    try:
                        import winsound
                        winsound.PlaySound(file_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                    except Exception:
                        pass
                threading.Thread(target=_play_fallback, daemon=True).start()

    def _on_sfx_config_changed(self, sfx_list: list):
        """Lưu danh sách SFX buttons vào settings.json khi thay đổi."""
        self.settings["sfx_buttons"] = sfx_list
        try:
            backend.ConfigManager.save_settings(self.settings)
        except Exception as e:
            print(f"[SFX] Khong luu duoc SFX settings: {e}")

    def _show_songs_list(self):
        from ui.dialogs.songs_list import SongsListDialog
        SongsListDialog(self).exec()

    def _show_edit_song_dialog(self, song: dict):
        from ui.dialogs.edit_song import EditSongDialog
        EditSongDialog(self, song).exec()

    def update_score_display(self, score):
        self.current_score = score
        # Sync waveform hero score ring
        if self._waveform is not None:
            self._waveform.set_score(score)

    # ══════════════════════════════════════════
    #  ACCESSIBILITY (TTS, theme, voice, shortcuts)
    # ══════════════════════════════════════════

    def _init_accessibility(self):
        """Khởi tạo Speaker/Announcer/ThemeManager + đăng ký shortcuts.

        Mọi lỗi đều bị nuốt và log — accessibility là tính năng phụ, không
        được phép crash app khi pyttsx3/vosk thiếu.
        """
        try:
            cfg = backend.AppConfig.get_accessibility()
        except Exception:
            cfg = {}

        # Theme
        try:
            self._a11y_theme = ThemeManager()
            self._a11y_theme.set_high_contrast(bool(cfg.get("high_contrast", False)))
            self._a11y_theme.set_font_scale(float(cfg.get("font_scale", 1.0)))
            self._a11y_theme.set_focus_ring_thick(bool(cfg.get("focus_ring_thick", False)))
            self._a11y_theme.apply()
        except Exception as e:
            print(f"[A11Y] Theme init lỗi: {e}")
            self._a11y_theme = None

        # Speaker
        try:
            self._a11y_speaker = get_speaker(
                rate=int(cfg.get("tts_rate", 180)),
                voice_id=cfg.get("tts_voice", "") or "",
                enabled=bool(cfg.get("tts_enabled", False)),
            )
            self._a11y_speaker.set_enabled(bool(cfg.get("tts_enabled", False)))
            if self._a11y_speaker.enabled:
                self._a11y_speaker.start()
        except Exception as e:
            print(f"[A11Y] Speaker init lỗi: {e}")
            self._a11y_speaker = None

        # Announcer
        try:
            self._a11y_announcer = Announcer(
                speaker=self._a11y_speaker,
                dashboard=self,
                announce_focus=bool(cfg.get("announce_focus", True)),
                announce_state=bool(cfg.get("announce_state", True)),
            )
            self._a11y_announcer.attach_focus_filter()
            self._a11y_announcer.hook_dashboard_signals()
        except Exception as e:
            print(f"[A11Y] Announcer init lỗi: {e}")
            self._a11y_announcer = None

        # Voice command (lazy — chỉ tạo khi user kích hoạt vì cần Vosk model)
        self._a11y_voice = None
        if cfg.get("voice_command_enabled", False):
            self._a11y_init_voice()

        # Tab order — chạy theo Header → Mixer → Mode → Tools → Bottom
        try:
            self._setup_tab_order()
        except Exception as e:
            print(f"[A11Y] Tab order lỗi: {e}")

        # Shortcuts
        try:
            register_shortcuts(self)
        except Exception as e:
            print(f"[A11Y] Shortcuts lỗi: {e}")

    def _setup_tab_order(self):
        """Thiết lập Tab order rõ ràng cho điều hướng bằng bàn phím."""
        # Header → Tools → Mixer → Mode → Bottom
        chain = []
        for attr in ("tone_combo", "scale_combo", "_settings_btn", "_eye_btn"):
            w = getattr(self, attr, None)
            if w is not None:
                chain.append(w)
        # Mixer sliders
        for cc in ("mix_music", "mix_mic", "mix_reverb", "tone_music"):
            sl = self._mixer_sliders.get(cc) if hasattr(self, "_mixer_sliders") else None
            if sl is not None:
                chain.append(sl)
            mb = self._mixer_icon_btns.get(cc) if hasattr(self, "_mixer_icon_btns") else None
            if mb is not None and mb.isVisible():
                chain.append(mb)
        # Mode + Tools buttons
        for btn in (self._mode_buttons or {}).values():
            chain.append(btn)
        for key in ("Chế độ: Nhanh", "Chế độ: Full", "Dò Lại", "Auto-Tune", "Fix Méo"):
            b = self._func_buttons.get(key)
            if b is not None:
                chain.append(b)
        # Bottom bar
        for key in ("💾 Lưu", "Danh sách", "Chấm điểm", "Thư Mục"):
            b = self._func_buttons.get(key)
            if b is not None:
                chain.append(b)
        if hasattr(self, "record_button") and self.record_button is not None:
            chain.append(self.record_button)

        # Đảm bảo focusable
        from PySide6.QtCore import Qt
        for w in chain:
            try:
                w.setFocusPolicy(Qt.StrongFocus)
            except Exception:
                pass

        # Set Tab order theo cặp liên tiếp
        for prev, nxt in zip(chain, chain[1:]):
            try:
                self.setTabOrder(prev, nxt)
            except Exception:
                pass

    def _a11y_init_voice(self):
        """Tạo VoiceInput service (chỉ gọi khi user enable + có model)."""
        try:
            from core.accessibility.voice_input import VoiceInput
            self._a11y_voice = VoiceInput(
                on_intent=self._a11y_on_voice_intent,
                on_error=lambda msg: self._a11y_speak(msg, priority="high"),
            )
            if not self._a11y_voice.available:
                self._a11y_speak("Chưa có model giọng nói. Hãy tải Vosk vi vào thư mục models.")
                self._a11y_voice = None
        except Exception as e:
            print(f"[A11Y] VoiceInput init lỗi: {e}")
            self._a11y_voice = None
        self._a11y_voice_listening = False
        self._a11y_voice_indicator = None

    # ── Voice push-to-talk (Ctrl+Space hold) ──────────────────

    def keyPressEvent(self, event):
        from PySide6.QtCore import Qt
        if (event.key() == Qt.Key_Space
                and event.modifiers() & Qt.ControlModifier
                and not event.isAutoRepeat()
                and getattr(self, "_a11y_voice", None) is not None):
            self._a11y_voice_start()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        from PySide6.QtCore import Qt
        if (event.key() == Qt.Key_Space
                and not event.isAutoRepeat()
                and getattr(self, "_a11y_voice_listening", False)):
            self._a11y_voice_stop()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def _a11y_voice_start(self):
        if self._a11y_voice is None or self._a11y_voice_listening:
            return
        self._a11y_voice_listening = True
        # Visual indicator — popup đỏ giữa header
        self._a11y_show_voice_indicator(True)
        # Beep ngắn để báo bắt đầu (winsound)
        try:
            import winsound
            winsound.Beep(880, 80)
        except Exception:
            pass
        self._a11y_speak("Đang nghe", priority="high")
        try:
            self._a11y_voice.start_listening()
        except Exception as e:
            self._a11y_speak(f"Lỗi mở mic: {e}", priority="high")
            self._a11y_voice_listening = False
            self._a11y_show_voice_indicator(False)

    def _a11y_voice_stop(self):
        if not self._a11y_voice_listening:
            return
        self._a11y_voice_listening = False
        self._a11y_show_voice_indicator(False)
        try:
            import winsound
            winsound.Beep(440, 60)
        except Exception:
            pass
        try:
            if self._a11y_voice is not None:
                self._a11y_voice.stop_listening()  # sẽ trigger _a11y_on_voice_intent
        except Exception as e:
            print(f"[A11Y] voice stop lỗi: {e}")

    def _a11y_show_voice_indicator(self, show: bool):
        from PySide6.QtWidgets import QLabel
        from PySide6.QtCore import Qt
        if not show:
            if self._a11y_voice_indicator is not None:
                self._a11y_voice_indicator.hide()
                self._a11y_voice_indicator.deleteLater()
                self._a11y_voice_indicator = None
            return
        lbl = QLabel("🎤  ĐANG NGHE...", self)
        lbl.setStyleSheet(
            "background-color: #EF4444; color: white;"
            " border: 2px solid #FFEB3B; border-radius: 10px;"
            " padding: 8px 16px; font-size: 16px; font-weight: 900;"
        )
        lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        lbl.adjustSize()
        # Đặt ở giữa-trên dashboard
        x = self.width() // 2 - lbl.width() // 2
        y = 80
        lbl.move(x, y)
        lbl.show()
        lbl.raise_()
        self._a11y_voice_indicator = lbl

    def _a11y_speak(self, text, priority="normal"):
        if getattr(self, "_a11y_announcer", None) is not None:
            if priority == "high":
                self._a11y_announcer.announce_error(text)
            else:
                self._a11y_announcer.announce_state(text)

    # ── Shortcut callbacks ────────────────────────────────

    def _a11y_speak_help(self):
        lines = getattr(self, "_a11y_help_lines", []) or []
        text = "Bộ phím tắt trợ năng. " + ". ".join(lines[:18]) if lines else "Chưa có phím tắt nào được đăng ký"
        self._a11y_speak(text, priority="high")

    def _a11y_speak_status(self):
        try:
            midi_ok = self.engine.is_midi_connected()
        except Exception:
            midi_ok = False
        tone = getattr(self, "current_tone", "C")
        scale = getattr(self, "current_scale", "Major")
        mode = getattr(self, "current_mode", "")
        from core.accessibility.announcer import key_to_vn
        parts = [
            f"MIDI {'kết nối' if midi_ok else 'mất kết nối'}",
            f"tone {key_to_vn(tone, scale)}",
        ]
        if mode:
            parts.append(f"chế độ {mode}")
        try:
            sl = self._mixer_sliders.get("mix_music")
            if sl is not None:
                parts.append(f"nhạc {int(sl.value())}")
        except Exception:
            pass
        try:
            sl = self._mixer_sliders.get("mix_mic")
            if sl is not None:
                parts.append(f"mic {int(sl.value())}")
        except Exception:
            pass
        self._a11y_speak(", ".join(parts), priority="high")

    def _a11y_toggle_tts(self):
        spk = getattr(self, "_a11y_speaker", None)
        if spk is None:
            return
        new_state = not spk.enabled
        spk.set_enabled(new_state)
        if new_state:
            spk.start()
            backend.AppConfig.set_accessibility(tts_enabled=True)
            spk.speak("Đã bật giọng đọc", priority="high")
        else:
            backend.AppConfig.set_accessibility(tts_enabled=False)
            self._show_message("TTS: tắt")

    def _a11y_toggle_high_contrast(self):
        tm = getattr(self, "_a11y_theme", None)
        if tm is None:
            return
        tm.set_high_contrast(not tm.is_high_contrast())
        tm.apply()
        backend.AppConfig.set_accessibility(high_contrast=tm.is_high_contrast())
        self._a11y_speak("Bật tương phản cao" if tm.is_high_contrast() else "Tắt tương phản cao")

    def _a11y_increase_font(self):
        tm = getattr(self, "_a11y_theme", None)
        if tm is None:
            return
        tm.increase_font()
        tm.apply()
        backend.AppConfig.set_accessibility(font_scale=tm.font_scale())
        self._a11y_speak(f"Cỡ chữ {int(tm.font_scale() * 100)} phần trăm")

    def _a11y_decrease_font(self):
        tm = getattr(self, "_a11y_theme", None)
        if tm is None:
            return
        tm.decrease_font()
        tm.apply()
        backend.AppConfig.set_accessibility(font_scale=tm.font_scale())
        self._a11y_speak(f"Cỡ chữ {int(tm.font_scale() * 100)} phần trăm")

    def _a11y_reset_font(self):
        tm = getattr(self, "_a11y_theme", None)
        if tm is None:
            return
        tm.set_font_scale(1.0)
        tm.apply()
        backend.AppConfig.set_accessibility(font_scale=1.0)
        self._a11y_speak("Khôi phục cỡ chữ mặc định")

    def _a11y_tone_music_up(self):
        self._a11y_step_tone("tone_music", +1)

    def _a11y_tone_music_down(self):
        self._a11y_step_tone("tone_music", -1)

    def _a11y_tone_voice_up(self):
        self._a11y_step_tone("tone_voice", +1)

    def _a11y_tone_voice_down(self):
        self._a11y_step_tone("tone_voice", -1)

    def _a11y_step_tone(self, which: str, delta: int):
        # Reuse existing slider if present (Tone Giọng = "tone_music" slider trong mixer
        # với range -12..+12 đã có sẵn).  Tone "tone_voice" được điều khiển qua knob,
        # nên ta gửi MIDI trực tiếp + cập nhật state.
        try:
            if which == "tone_music":
                sl = self._mixer_sliders.get("tone_music")
                if sl is not None:
                    new = max(sl.minimum(), min(sl.maximum(), sl.value() + delta))
                    sl.setValue(new)
                    self._a11y_speak(f"Tone Giọng {new:+d}")
                    return
            # tone_voice: knob — tự gửi MIDI
            cur = getattr(self, "tone_voice_value", 0)
            new = max(-12, min(12, cur + delta))
            self.tone_voice_value = new
            midi_value = int(((new + 12) / 24) * 127)
            self.engine.send_midi(MIDI_CC.get("tone_voice", 11), midi_value)
            self._a11y_speak(f"Tone Nhạc {new:+d}")
        except Exception as e:
            print(f"[A11Y] step_tone lỗi: {e}")

    def _a11y_toggle_mute_music(self):
        self._a11y_toggle_mute("mix_music", "Nhạc")

    def _a11y_toggle_mute_mic(self):
        self._a11y_toggle_mute("mix_mic", "Mic")

    def _a11y_toggle_mute_reverb(self):
        self._a11y_toggle_mute("mix_reverb", "Vang")

    def _a11y_toggle_mute_backing(self):
        self._a11y_toggle_mute("mix_backing", "Giọng đệm")

    def _a11y_toggle_mute(self, cc_key: str, label: str):
        try:
            ch = self._mixer_channels.get(cc_key) if hasattr(self, "_mixer_channels") else None
            if ch is None or not getattr(ch, "mute_btn", None):
                self._a11y_speak(f"Kênh {label} không có nút tắt âm")
                return
            ch.mute_btn.click()
            is_muted = ch.is_muted()
            self._a11y_speak(f"{label} {'đã tắt âm' if is_muted else 'đã bật lại'}")
        except Exception as e:
            print(f"[A11Y] toggle_mute lỗi: {e}")

    def _a11y_on_voice_intent(self, intent):
        """Xử lý intent từ voice command. intent: voice_input.Intent"""
        name = getattr(intent, "name", "unknown")
        text = getattr(intent, "text", "")
        print(f"[VOICE INTENT] name={name!r} text={text!r}")

        if name == "empty":
            self._a11y_speak("Không nghe rõ. Hãy nói to và rõ hơn.", priority="high")
            self._show_message("🎤 Không nghe được lệnh", is_error=True)
            return

        actions = {
            "autokey":          self._on_force_rescan,
            "record_toggle":    self._on_record,
            "save":             self._on_save,
            "open_songs":       self._show_songs_list,
            "score":            self._on_score,
            "speak_status":     self._a11y_speak_status,
            "stop_tts":         lambda: self._a11y_speaker and self._a11y_speaker.stop(),
            "mute_music":       self._a11y_toggle_mute_music,
            "mute_mic":         self._a11y_toggle_mute_mic,
            "volume_up_music":  lambda: self._a11y_step_volume("mix_music", +5),
            "volume_down_music": lambda: self._a11y_step_volume("mix_music", -5),
            "volume_up_mic":    lambda: self._a11y_step_volume("mix_mic", +1),
            "volume_down_mic":  lambda: self._a11y_step_volume("mix_mic", -1),
            "volume_up_reverb": lambda: self._a11y_step_volume("mix_reverb", +1),
            "volume_down_reverb": lambda: self._a11y_step_volume("mix_reverb", -1),
            "mode_danca":       lambda: self._on_mode_selected("Dân Ca"),
            "mode_lofi":        lambda: self._on_mode_selected("Lofi"),
            "mode_remix":       lambda: self._on_mode_selected("Remix"),
            "mode_datheloai":   lambda: self._on_mode_selected("Đa Thể Loại"),
        }
        action = actions.get(name)
        if action is None:
            print(f"[VOICE INTENT]   -> Không hiểu lệnh: {text!r}")
            self._a11y_speak(f"Không hiểu lệnh: {text}", priority="high")
            self._show_message(f"🎤 Nghe được: \"{text}\" — không hiểu", is_error=True)
            return
        try:
            print(f"[VOICE INTENT]   -> Thực hiện: {name}")
            action()
            self._a11y_speak("Đã thực hiện", priority="high")
            self._show_message(f"🎤 \"{text}\" → {name}")
        except Exception as e:
            print(f"[VOICE INTENT]   -> Lỗi: {e}")
            self._a11y_speak(f"Lỗi: {e}", priority="high")

    def _a11y_step_volume(self, cc_key: str, delta: int):
        try:
            sl = self._mixer_sliders.get(cc_key) if hasattr(self, "_mixer_sliders") else None
            if sl is None:
                return
            new = max(sl.minimum(), min(sl.maximum(), sl.value() + delta))
            sl.setValue(new)
        except Exception as e:
            print(f"[A11Y] step_volume lỗi: {e}")

    def _ensure_app(self):
        if not QApplication.instance():
            self._app = QApplication(sys.argv)
            self._app.setStyleSheet(APP_QSS)
        _load_fonts()

    # mainloop compatibility (CTk → Qt)
    def mainloop(self):
        self.show()
        app = QApplication.instance()
        if app:
            app.exec()

    def closeEvent(self, event):
        """Đóng cửa sổ không block — set flags ngay, cleanup nặng chạy nền."""
        self.hide()

        # ── BƯỚC 1: Set stop flags (instant, thread-safe) ──────────────────────
        # Phải set trước khi accept để các thread thoát loop nhanh nhất có thể.
        self.engine._youtube_watcher_active = False
        self.engine.autokey_active = False
        try:
            self.engine._tone_session.stop()
        except Exception:
            pass
        # Xóa pending URL queue để watcher không dispatch thêm
        try:
            self.engine.current_youtube_url = None
            self.engine._last_watched_url = None
            with self.engine._pending_url_lock:
                self.engine._pending_url_queue.clear()
        except Exception:
            pass

        # ── BƯỚC 2: Qt timers — phải dừng trên main thread ────────────────────
        self._status_timer.stop()
        if self._marquee_timer is not None:
            self._marquee_timer.stop()
        if self._marquee_widget is not None and hasattr(self._marquee_widget, 'timer'):
            self._marquee_widget.timer.stop()

        # Accessibility cleanup
        try:
            spk = getattr(self, "_a11y_speaker", None)
            if spk is not None:
                spk.stop()
        except Exception:
            pass
        try:
            voice = getattr(self, "_a11y_voice", None)
            if voice is not None:
                voice.stop_listening()
        except Exception:
            pass

        # ── BƯỚC 3: Waveform + ghi âm (nhanh, không block) ────────────────────
        if self._waveform is not None:
            try:
                self._waveform.stop()
            except Exception:
                pass
        if self.is_recording:
            try:
                self.engine.recorder.stop_recording(save_path=None)
            except Exception:
                pass
            self.is_recording = False

        # ── BƯỚC 4: Cleanup tức thì (non-blocking COM/MIDI calls) ──────────────
        try:
            self.engine.restore_browser_volume()
        except Exception:
            pass
        try:
            self.engine.disconnect_midi()
        except Exception:
            pass
        try:
            self.engine.media_monitor.stop()
        except Exception:
            pass

        # ── BƯỚC 5: Accept ngay — window đóng, Qt event loop không bị block ───
        try:
            mixer_levels = {}
            for cc_key, slider in getattr(self, '_mixer_sliders', {}).items():
                mixer_levels[cc_key] = slider.value()
            self.settings["mixer_levels"] = mixer_levels
            
            # Save window position and size
            self.settings["window_geometry"] = {
                "x": self.x(),
                "y": self.y(),
                "width": self.width(),
                "height": self.height()
            }
            
            backend.ConfigManager.save_settings(self.settings)
        except Exception as e:
            print(f"Lỗi lưu mixer levels: {e}")

        # ── BƯỚC 5: Đóng ứng dụng liên kết (Đồng bộ, trước khi os._exit) ───────
        if self.settings.get("auto_close_browser", False):
            try:
                self.engine.close_youtube_windows()
            except Exception:
                pass

        if self.settings.get("auto_close_studio_one", False):
            try:
                self.engine.kill_studio_one_gracefully(timeout_sec=5)
            except Exception:
                pass
            
        event.accept()
        super().closeEvent(event)

        # ── BƯỚC 6: Cleanup nặng trong daemon thread (join + Studio One) ───────
        # Daemon thread tự bị kill khi os._exit(0) chạy trong main.py.
        # Không cần join — chỉ cần đảm bảo các tài nguyên hệ thống được giải phóng.
        settings_snap = dict(self.settings)
        engine = self.engine

        def _bg_shutdown():
            # Watcher loop check flag mỗi 0.1s → join xong nhanh (~0.1s)
            try:
                engine.stop_youtube_watcher()
            except Exception:
                pass
            # Autokey: stream.read() block ~23ms/chunk → thoát nhanh sau khi flag set
            try:
                engine.stop_autokey()
            except Exception:
                pass
            try:
                engine.stop_tone_detection()
            except Exception:
                pass
            if hasattr(engine, '_memory_guard'):
                try:
                    engine._memory_guard.stop()
                except Exception:
                    pass
            import gc
            gc.collect()

        threading.Thread(target=_bg_shutdown, daemon=True, name="bg-shutdown").start()


# ══════════════════════════════════════════════════════
#  ACTIVATION DIALOG (simplified for now)
# ══════════════════════════════════════════════════════
class ActivationDialog(QDialog):
    def __init__(self, callback=None, is_expired=False):
        # We need QApplication to exist before creating any QWidget
        self._ensure_app()
        super().__init__()
        self.callback = callback
        self.is_expired = is_expired
        self.activated = False
        self.setWindowTitle("Kích hoạt Quang Lưu Studio")
        self.setWindowIcon(QIcon("app_icon.ico"))
        self.setFixedSize(520, 510)
        self.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")

        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── Premium Header with gradient ──
        from PySide6.QtWidgets import QFrame as _QF2
        header = _QF2()
        header.setFixedHeight(130)
        header.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {C['card']}, stop:0.5 rgba(20,184,166,18), stop:1 {C['card']});
                border-bottom: 1px solid rgba(20,184,166,0.3);
            }}
        """)
        hdr_lay = QVBoxLayout(header)
        hdr_lay.setContentsMargins(24, 20, 24, 16)
        hdr_lay.setSpacing(6)

        title = QLabel("🎤 Quang Lưu Studio")
        title.setStyleSheet(f"font-size: 26px; font-weight: 900; color: {C['teal']}; font-family: {FONT}; background: transparent; border: none; letter-spacing: -1px;")
        title.setAlignment(Qt.AlignCenter)
        hdr_lay.addWidget(title)

        if is_expired:
            msg = QLabel("⚠️ Bản quyền đã hết hạn! Vui lòng nhập mã kích hoạt mới.")
            msg.setStyleSheet(f"color: {C['accent']}; font-size: 14px; font-family: {FONT}; background: transparent; border: none;")
        else:
            msg = QLabel("Vui lòng nhập Activation Code để tiếp tục.")
            msg.setStyleSheet(f"color: {C['text_muted']}; font-size: 14px; font-family: {FONT}; background: transparent; border: none;")
        msg.setAlignment(Qt.AlignCenter)
        hdr_lay.addWidget(msg)
        outer.addWidget(header)

        # ── Body ──
        body_frame = _QF2()
        body_frame.setStyleSheet(f"background-color: {C['bg']}; border: none;")
        layout = QVBoxLayout(body_frame)
        layout.setSpacing(14)
        layout.setContentsMargins(30, 24, 30, 24)

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("Nhập activation code...")
        self.code_input.setFixedHeight(50)
        self.code_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {C['card']};
                color: {C['text']};
                border: 2px solid {C['border']};
                border-radius: 12px;
                padding: 12px 16px;
                font-size: 16px;
                font-family: {FONT};
                letter-spacing: 2px;
            }}
            QLineEdit:focus {{
                border-color: {C['teal']};
                background-color: rgba(20,184,166,0.06);
            }}
        """)
        layout.addWidget(self.code_input)

        activate_btn = QPushButton("✓ Kích hoạt")
        activate_btn.setFixedHeight(48)
        activate_btn.setCursor(Qt.PointingHandCursor)
        activate_btn.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.12), 17, 22))
        activate_btn.clicked.connect(self._activate)
        add_shadow(activate_btn, C["teal"], 10, (0, 3))
        layout.addWidget(activate_btn)

        # ── Separator ──
        sep_row = QHBoxLayout()
        sep_line1 = _QF2()
        sep_line1.setFixedHeight(1)
        sep_line1.setStyleSheet(f"background-color: {C['border']}; border: none;")
        sep_label = QLabel("hoặc")
        sep_label.setAlignment(Qt.AlignCenter)
        sep_label.setFixedWidth(40)
        sep_label.setStyleSheet(f"color: {C['text_muted']}; font-size: 12px; background: transparent; border: none;")
        sep_line2 = _QF2()
        sep_line2.setFixedHeight(1)
        sep_line2.setStyleSheet(f"background-color: {C['border']}; border: none;")
        sep_row.addWidget(sep_line1, 1)
        sep_row.addWidget(sep_label)
        sep_row.addWidget(sep_line2, 1)
        layout.addLayout(sep_row)

        # ── Trial button ──
        trial_expired = backend.ActivationManager.is_trial_expired()
        if trial_expired:
            trial_btn = QPushButton("⏰ Đã hết hạn dùng thử")
            trial_btn.setFixedHeight(44)
            trial_btn.setEnabled(False)
            trial_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {C['card_hover']};
                    color: {C['text_muted']};
                    border: 1px solid {C['border']};
                    border-radius: 14px;
                    font-size: 14px;
                    font-family: {FONT};
                }}
            """)
        else:
            trial_btn = QPushButton("🎁 Dùng thử miễn phí 3 ngày")
            trial_btn.setFixedHeight(44)
            trial_btn.setCursor(Qt.PointingHandCursor)
            trial_btn.setStyleSheet(pill_btn_qss(C["orange"], _lighten(C["orange"], 0.1), 14, 18))
            trial_btn.clicked.connect(self._start_trial)
        layout.addWidget(trial_btn)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(f"font-size: 13px; font-family: {FONT}; background: transparent; border: none;")
        layout.addWidget(self.status_label)
        layout.addStretch()
        outer.addWidget(body_frame, 1)

    def _ensure_app(self):
        if not QApplication.instance():
            self._app = QApplication(sys.argv)
            self._app.setStyleSheet(APP_QSS)
        _load_fonts()

    def _activate(self):
        code = self.code_input.text().strip()
        if not code:
            self.status_label.setText("Vui lòng nhập mã kích hoạt")
            self.status_label.setStyleSheet(f"color: {C['accent']}; font-size:13px;")
            return
        result = backend.ActivationManager.activate(code)
        if result.get("success"):
            self.activated = True
            self.status_label.setText("✅ Kích hoạt thành công!")
            self.status_label.setStyleSheet(f"color: {C['green']}; font-size:13px;")
            QTimer.singleShot(1000, self._close_and_continue)
        else:
            self.status_label.setText(f"❌ {result.get('error', 'Mã không hợp lệ')}")
            self.status_label.setStyleSheet(f"color: {C['accent']}; font-size:13px;")
    
    def _start_trial(self):
        """Bắt đầu dùng thử 3 ngày"""
        result = backend.ActivationManager.start_trial()
        if result.get("success"):
            self.activated = True
            days = result.get("days_remaining", 3)
            self.status_label.setText(f"🎉 Bắt đầu dùng thử! Còn {days:.0f} ngày")
            self.status_label.setStyleSheet(f"color: {C['green']}; font-size:13px;")
            QTimer.singleShot(1200, self._close_and_continue)
        else:
            self.status_label.setText("⚠️ Thời gian dùng thử đã hết. Vui lòng nhập mã kích hoạt.")
            self.status_label.setStyleSheet(f"color: {C['accent']}; font-size:13px;")

    def _close_and_continue(self):
        self.close()
        # Không gọi callback ở đây — callback sẽ được gọi sau khi app.exec() kết thúc
        # trong mainloop() để tránh nested event loop

    def mainloop(self):
        self.show()
        app = QApplication.instance()
        if app:
            app.exec()
        # Sau khi dialog đóng và event loop kết thúc, gọi callback nếu đã kích hoạt
        if self.activated and self.callback:
            self.callback()


# ══════════════════════════════════════════════════════
#  SETUP VIEW
# ══════════════════════════════════════════════════════
class SetupView(QDialog):
    def __init__(self, callback=None):
        self._ensure_app()
        super().__init__()
        self.callback = callback
        self._saved = False
        existing = backend.ConfigManager.load_settings() or {}

        self.setWindowTitle("Cài đặt Quang Lưu Studio")
        self.setWindowIcon(QIcon("app_icon.ico"))
        self.setFixedSize(580, 460)
        self.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")

        from PySide6.QtWidgets import QFrame as _QF3
        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── Header ──
        header = _QF3()
        header.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {C['card']}, stop:1 rgba(20,184,166,14));
                border-bottom: 1px solid rgba(20,184,166,0.3);
            }}
        """)
        hdr_vl = QVBoxLayout(header)
        hdr_vl.setContentsMargins(30, 20, 30, 16)
        hdr_vl.setSpacing(6)

        title = QLabel("⚙️ Cài đặt ban đầu")
        title.setStyleSheet(f"font-size: 24px; font-weight: 900; color: {C['teal']}; font-family: {FONT}; background: transparent; border: none;")
        title.setAlignment(Qt.AlignCenter)
        hdr_vl.addWidget(title)

        subtitle = QLabel("Thiết lập đường dẫn để bắt đầu sử dụng Quang Lưu Studio")
        subtitle.setStyleSheet(f"font-size: 13px; color: {C['text_muted']}; font-family: {FONT}; background: transparent; border: none;")
        subtitle.setAlignment(Qt.AlignCenter)
        hdr_vl.addWidget(subtitle)
        outer.addWidget(header)

        # ── Body ──
        body = _QF3()
        body.setStyleSheet(f"background-color: {C['bg']}; border: none;")
        layout = QVBoxLayout(body)
        layout.setSpacing(16)
        layout.setContentsMargins(30, 24, 30, 20)

        # Step 1: Studio One path
        step1_lbl = QLabel("🔹 Bước 1:  Đường dẫn Studio One")
        step1_lbl.setStyleSheet(f"color: {C['teal']}; font-size: 13px; font-weight: 700; font-family: {FONT}; background: transparent; border: none;")
        layout.addWidget(step1_lbl)

        row1 = QHBoxLayout()
        row1.setSpacing(6)
        self.studio_one_input = QLineEdit(existing.get("studio_one_path", ""))
        self.studio_one_input.setStyleSheet(self._input_qss())
        row1.addWidget(self.studio_one_input)
        browse1 = QPushButton("📂")
        browse1.setFixedSize(40, 38)
        browse1.setCursor(Qt.PointingHandCursor)
        browse1.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.1), 14, 10))
        browse1.clicked.connect(self._browse_studio_one)
        row1.addWidget(browse1)
        layout.addLayout(row1)

        # Step 2: Browser path
        step2_lbl = QLabel("🔹 Bước 2:  Đường dẫn trình duyệt (YouTube)")
        step2_lbl.setStyleSheet(f"color: {C['teal']}; font-size: 13px; font-weight: 700; font-family: {FONT}; background: transparent; border: none;")
        layout.addWidget(step2_lbl)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        self.browser_input = QLineEdit(existing.get("browser_path", ""))
        self.browser_input.setStyleSheet(self._input_qss())
        row2.addWidget(self.browser_input)
        browse2 = QPushButton("📂")
        browse2.setFixedSize(40, 38)
        browse2.setCursor(Qt.PointingHandCursor)
        browse2.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.1), 14, 10))
        browse2.clicked.connect(self._browse_browser)
        row2.addWidget(browse2)
        layout.addLayout(row2)

        layout.addStretch()

        # Save button
        save_btn = QPushButton("Lưu && Tiếp tục →")
        save_btn.setFixedHeight(48)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.1), 17, 22))
        save_btn.clicked.connect(self._save_and_continue)
        add_shadow(save_btn, C["green"], 10, (0, 3))
        layout.addWidget(save_btn)
        outer.addWidget(body, 1)

    def _ensure_app(self):
        if not QApplication.instance():
            self._app = QApplication(sys.argv)
            self._app.setStyleSheet(APP_QSS)
        _load_fonts()

    def _make_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color:{C['text_muted']}; font-size:13px; font-weight:500;")
        return lbl

    def _input_qss(self):
        return f"""
            QLineEdit {{
                background-color: {C['card']};
                color: {C['text']};
                border: 1px solid {C['border']};
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 14px;
            }}
            QLineEdit:focus {{ border-color: {C['teal']}; }}
        """

    def _browse_studio_one(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file Studio One hoặc chương trình", "",
            "Studio One Files (*.song *.exe);;Song Files (*.song);;Executable (*.exe);;All Files (*.*)"
        )
        if path:
            self.studio_one_input.setText(path)

    def _browse_browser(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn trình duyệt", "", "Executable (*.exe)")
        if path:
            self.browser_input.setText(path)

    def _save_and_continue(self):
        settings = {
            "studio_one_path": self.studio_one_input.text().strip(),
            "browser_path": self.browser_input.text().strip(),
        }
        backend.ConfigManager.save_settings(settings)
        self._saved = True
        self.close()

    def mainloop(self):
        self.show()
        app = QApplication.instance()
        if app:
            app.exec()
        # Sau khi dialog đóng, gọi callback nếu đã lưu settings
        if self._saved and self.callback:
            self.callback()


# ─── DEBUG ───
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainDashboard()
    window.show()
    sys.exit(app.exec())
