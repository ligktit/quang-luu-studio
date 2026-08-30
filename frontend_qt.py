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
from ui import responsive as rp
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

# Câu nói về nguồn tone — dùng CHUNG cho tooltip lẫn thông báo, để một ý không
# có hai cách nói khác nhau (xem docs/UI_TEXT_AUDIT.md §3).
TONE_MSG_LOW_CONF = "Tone gợi ý — sai thì bấm Dò Lại"
TONE_MSG_CACHED = "Tone đã lưu — sai thì bấm Dò Lại"
TONE_MSG_FRESH = "Tone vừa dò xong"
TONE_MSG_LOOPBACK = "Đã dò tone qua loa máy"

# ─── GLOBAL QSS (loaded from ui/styles/main.qss) ───
APP_QSS = load_qss()

# ─── Backward-compat aliases (used heavily in dialogs/callbacks below) ───
_lighten = lighten
_darken = darken

# True khi vòng lặp sự kiện của dashboard đang chạy. Các dialog dùng mainloop()
# (show + app.exec) chỉ hợp lệ TRƯỚC khi dashboard mở; gọi lúc vòng lặp đã chạy
# thì Qt từ chối exec lồng nhau và trả về ngay → dialog biến mất trước khi kịp
# vẽ. Cờ này để mainloop() tự chuyển sang exec() modal khi ở giữa phiên.
_APP_LOOP_RUNNING = False

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
    _tone_result_signal = Signal(dict)
    _midi_cc_signal = Signal(int, int)

    _midi_status_signal = Signal()
    _browser_status_signal = Signal()
    _message_signal = Signal(str, bool)
    _score_report_signal = Signal(dict)
    _score_btn_reset_signal = Signal()
    _marquee_signal = Signal(str)
    _voice_intent_signal = Signal(object)
    _embedded_volume_signal = Signal(int)   # set âm lượng player nhúng (thread-safe)
    _search_results_signal = Signal(list)   # kết quả tìm kiếm YouTube (thread-safe)
    _stream_resolved_signal = Signal(str, str, str, str)  # (video_id, url, title, loi)

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

        # Khoá kỹ thuật đọc/ghi trên chính dict settings này — phải gắn TRƯỚC khi
        # dựng header, vì header hỏi kiosk.is_locked() để quyết định hiện nút mắt.
        try:
            from core import kiosk
            kiosk.bind(self.settings)
        except Exception as e:
            print(f"[KIOSK] bind lỗi: {e}")
        self._so_hide_guard = None
        self._so_shutdown_done = False
        self._kiosk_timer = None

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
        self.tat_on_state = False   # nút Tắt Ồn (khử ồn mic) — mọi phiên bản
        self.mute_states = {
            "mix_music": False, "mix_mic": False,
            "mix_reverb": False, "mix_backing": False
        }
        self.autokey_active = False
        self.tune_state = True
        self.fix_meo_state = False
        self.current_scale = "Major"
        self.is_dev_mode = False
        # Cờ khoá replay khi user chỉnh tone/scale tay (xem _lock_replay_for_manual_override)
        self._manual_tone_override = False

        # ── Trạng thái timeline tone (nguồn sự thật của phần HIỂN THỊ) ──────
        # UI tự giữ timeline + vị trí phát, thay vì chỉ ngồi chờ engine bắn sự
        # kiện lên. Nhờ vậy UI biết được "đoạn kế tiếp còn bao lâu" (engine không
        # gửi thông tin đó) và vẫn bám đúng bài kể cả khi vòng replay im tiếng.
        # Ở đây CHỈ hiển thị — MIDI vẫn do engine gửi, tránh hai nguồn bắn trùng.
        self._tone_timeline = []
        self._tone_index = -1
        self._tone_position = 0.0
        self._tone_duration = 0.0
        self._tone_tick_timer = None
        self._embedded_pos = None   # (position, duration) mới nhất từ player nhúng
        self.current_title = ""

        self._mixer_channels = {}

        # Widgets / timers populated by _build_* — init to None so hot paths can
        # do `is None` checks instead of `hasattr` probes.
        self._marquee_widget = None
        self._marquee_timer = None
        self._waveform = None
        self._player_window = None   # KaraokePlayerWindow (chế độ màn hình nhúng)
        self._search_input = None
        self._search_results_list = None
        self._func_buttons = {}
        self._mode_buttons = {}
        self._mode_colors = {}
        self._marquee_text_value = ""

        # Tự động bật/tắt Vang theo nhạc (Premium) — xem _apply_auto_echo_setting
        self._auto_echo_timer = None
        self._auto_echo_playing = None   # trạng thái nhạc đã CHỐT (None = chưa biết)
        self._auto_echo_streak = 0       # số lần lấy mẫu liên tiếp cho trạng thái mới

        # Tự động bật/tắt Khử ồn theo nhạc (Premium) — xem _apply_auto_noise_setting
        self._auto_noise_timer = None
        self._auto_noise_playing = None
        self._auto_noise_streak = 0

        # Expose module-level config to panels (avoids circular imports in ui/panels/*)
        self.MIDI_CC = MIDI_CC
        self.SCALE_VALUES = SCALE_VALUES

        # Window — cỡ đi theo tỉ lệ màn hình (xem ui/responsive.py), không fix cứng
        self.setWindowTitle("Quang Lưu Studio")
        self.setWindowIcon(QIcon("app_icon.ico"))
        rp.set_min_size(self, 780, 200)
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
        self._marquee_text = self._brand_marquee_text("Bản quyền Quang Lưu Studio")

        # Build UI — V5.0: Performance Stage (waveform hero + tabbed dock)
        root.addWidget(self._build_header())
        
        self._body_wrapper = QWidget()
        self._body_layout = QVBoxLayout(self._body_wrapper)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.addWidget(self._build_body())
        root.addWidget(self._body_wrapper, 1)
        
        root.addWidget(self._build_bottom_bar())

        compact_min_h = max(200, self.minimumSizeHint().height())
        # Cỡ tối thiểu vẫn phải vừa vùng làm việc của màn hình đang dùng: trên máy
        # 1280x720 mà ép min theo nội dung thì cửa sổ tràn ra ngoài, thu lại không được.
        rp.set_min_size(self, 780, compact_min_h)

        # Khôi phục vị trí cũ — restore_geometry tự loại bỏ toạ độ đã "lạc" khi user
        # rút màn phụ / đổi độ phân giải. Không dùng được thì dựng cỡ theo TỈ LỆ màn
        # hình, nhờ vậy 1366x768, 1920x1080, 2560x1440 hay 4K đều ra bố cục cân đối.
        if not rp.restore_geometry(self, self.settings.get("window_geometry")):
            rp.apply_window_size(
                self,
                ratio=(0.58, 0.42),
                min_size=(820, rp.px(compact_min_h + 20)),
                max_size=(1500, max(compact_min_h + 20, 900)),
            )

        # MIDI
        self.engine.register_midi_callback(self.on_midi_status_changed)
        self._update_midi_status()

        # Signal connections (for thread-safe UI updates)
        self._tone_result_signal.connect(self._handle_tone_result)
        self._marquee_signal.connect(self._set_marquee_text)
        # Queued: intent handler có thể mở dialog (exec) — không được chạy
        # trực tiếp bên trong key-event handler / callback của voice input.
        self._voice_intent_signal.connect(self._a11y_on_voice_intent, Qt.QueuedConnection)
        
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

        # Nhịp bám timeline tone — 250ms, CHỈ chạy khi đang phát và bài có
        # timeline nhiều đoạn (xem _tone_ticker_sync). Nhàn rỗi thì dừng hẳn.
        self._tone_tick_timer = QTimer(self)
        self._tone_tick_timer.timeout.connect(self._on_tone_tick)
        # Timer 2.5s sẵn có làm nhiệm vụ bật/tắt nhịp trên theo trạng thái phát.
        self._status_timer.timeout.connect(self._tone_ticker_sync)

        # Auto launch (Studio One + Browser theo settings)
        self._auto_launch_apps()

        # Player nhúng (bản Heavy) hoặc YouTube URL Watcher (mặc định).
        # Chế độ nhúng KHÔNG dùng watcher trình duyệt ngoài (tránh dò trùng).
        self._embedded_volume_signal.connect(self._set_embedded_volume)
        self._search_results_signal.connect(self._on_search_results)
        self._stream_resolved_signal.connect(self._on_stream_resolved)
        self._apply_embedded_player_setting()

        # Tự động bật/tắt Vang theo nhạc (Premium) — chỉ chạy nếu bật trong Cài đặt
        self._apply_auto_echo_setting()

        # Tự động bật/tắt Khử ồn theo nhạc (Premium) — cùng điều kiện như trên
        self._apply_auto_noise_setting()

        # Accessibility — TTS, theme, shortcuts (sau khi UI đã build xong)
        self._init_accessibility()

        # Đồng bộ chế độ mặc định lúc khởi động
        self._on_mode_selected(self.current_mode, toggle=False)
        
        # Dev Mode Shortcut
        from PySide6.QtGui import QShortcut, QKeySequence
        self._dev_mode_shortcut = QShortcut(QKeySequence("Ctrl+Shift+D"), self)
        self._dev_mode_shortcut.activated.connect(self._toggle_dev_mode)

        # Khoá kỹ thuật — phím tắt không ghi ở đâu trong giao diện khách.
        self._tech_shortcut = QShortcut(QKeySequence("Ctrl+Alt+Shift+T"), self)
        self._tech_shortcut.activated.connect(self._toggle_tech_session)
        self._apply_kiosk_visibility()

        # Premium: nút lấp lánh theo nhạc (sau khi toàn bộ UI đã dựng).
        self._enable_premium_button_fx()

    def _enable_premium_button_fx(self):
        """Bật hiệu ứng glow/lấp lánh theo beat cho mọi PainterButton — chỉ Premium."""
        try:
            from core import entitlements
            if not entitlements.is_premium():
                return
            self._fx_buttons = self.findChildren(PainterButton)
            for btn in self._fx_buttons:
                btn.set_music_reactive(True)
        except Exception as e:
            print(f"[PREMIUM-FX] enable lỗi: {e}")

    def _toggle_dev_mode(self):
        self.is_dev_mode = not self.is_dev_mode
        self._show_message(f"Dev Mode: {'ON' if self.is_dev_mode else 'OFF'}")
        self.refresh_ui()

    # ── Khoá kỹ thuật (chế độ khách) ─────────────────────────────────────────

    def _apply_kiosk_visibility(self):
        """Đồng bộ giao diện + watchdog với trạng thái khoá hiện tại.

        Gọi mỗi khi trạng thái khoá đổi (mở/đóng phiên kỹ thuật, bật/tắt chế độ
        khách trong Thiết lập) và một lần lúc khởi động.
        """
        from core import kiosk, so_windows

        locked = kiosk.is_locked()
        if self._eye_btn is not None:
            self._eye_btn.setVisible(not locked)
        support_btn = getattr(self, "_support_btn", None)
        if support_btn is not None:
            support_btn.setVisible(not locked)
        if getattr(self, "_tech_badge", None) is not None:
            self._tech_badge.setVisible(kiosk.is_enabled() and kiosk.session_active())

        # Watchdog giữ ẩn (tuỳ chọn) — chỉ chạy khi đang khoá.
        want_guard = locked and kiosk.keep_hidden()
        if want_guard:
            if self._so_hide_guard is None:
                self._so_hide_guard = so_windows.HideGuard(
                    should_hide=lambda: kiosk.is_locked() and kiosk.keep_hidden()
                )
            self._so_hide_guard.start()
        elif self._so_hide_guard is not None:
            self._so_hide_guard.stop()

        # Đồng hồ tự khoá lại khi hết phiên — KTV hay quên bấm khoá.
        timer = getattr(self, "_kiosk_timer", None)
        if kiosk.is_enabled() and kiosk.session_active():
            if timer is None:
                self._kiosk_timer = QTimer(self)
                self._kiosk_timer.timeout.connect(self._kiosk_session_tick)
                self._kiosk_timer.start(5000)
        elif timer is not None:
            timer.stop()
            self._kiosk_timer = None

    def _kiosk_session_tick(self):
        from core import kiosk
        if kiosk.session_active():
            return
        self._lock_studio_one("Hết phiên kỹ thuật — đã khoá lại Studio One")

    def _lock_studio_one(self, message):
        from core import kiosk, so_windows
        kiosk.end_session()
        try:
            so_windows.hide_all()
        except Exception as e:
            print(f"[KIOSK] ẩn Studio One lỗi: {e}")
        self._studio_one_visible = False
        self._apply_kiosk_visibility()
        self._show_message(message)

    def _toggle_tech_session(self):
        """Ctrl+Alt+Shift+T — mở/đóng phiên kỹ thuật."""
        from core import kiosk, so_windows

        if not kiosk.is_enabled():
            self._show_message("Chế độ khách chưa bật (Thiết lập → Hệ thống)")
            return

        if kiosk.session_active():
            self._lock_studio_one("Đã khoá lại — Studio One ẩn khỏi khách")
            return

        if not kiosk.has_pin():
            self._show_message("Chưa đặt mã PIN kỹ thuật", is_error=True)
            return

        from ui.dialogs.tech_unlock import TechUnlockDialog
        if TechUnlockDialog(self).exec() != QDialog.Accepted:
            return

        self._apply_kiosk_visibility()
        try:
            shown = so_windows.show_all()
        except Exception as e:
            shown = 0
            print(f"[KIOSK] hiện Studio One lỗi: {e}")
        self._studio_one_visible = True
        if self._eye_btn is not None:
            from ui.components.svg_icons import SVG_EYE_OPEN
            self._eye_btn.setSvg(SVG_EYE_OPEN)
        if shown or so_windows.is_running():
            self._show_message(f"Mở khoá kỹ thuật {kiosk.session_minutes()} phút")
        else:
            self._show_message(
                f"Mở khoá kỹ thuật {kiosk.session_minutes()} phút — Studio One chưa chạy")

    def refresh_ui(self):
        # Clear body layout
        removed_roots = []
        for i in reversed(range(self._body_layout.count())):
            widget = self._body_layout.itemAt(i).widget()
            if widget:
                removed_roots.append(widget)
                widget.setParent(None)
                widget.deleteLater()

        # Xóa các ref cũ trong registry trỏ tới widget vừa bị xóa — nếu giữ lại
        # sẽ crash "Internal C++ object already deleted" khi _set_rescan_button_state
        # / _reset_score_btn truy cập. Chỉ xóa entry thuộc body (bottom bar giữ nguyên).
        for key, btn in list(self._func_buttons.items()):
            try:
                if any(w is btn or w.isAncestorOf(btn) for w in removed_roots):
                    del self._func_buttons[key]
            except RuntimeError:
                # Wrapped C++ object đã bị xóa → ref chắc chắn stale
                del self._func_buttons[key]
        # Mode buttons nằm hoàn toàn trong body → clear toàn bộ (mode.py sẽ thêm lại)
        self._mode_buttons = {}

        # Rebuild body
        self._body_layout.addWidget(self._build_body())

        # Tab order tham chiếu widget cũ — thiết lập lại sau khi rebuild
        try:
            self._setup_tab_order()
        except Exception as e:
            print(f"[A11Y] Tab order lỗi: {e}")

        # Bật lại lấp lánh theo nhạc cho các nút vừa dựng lại (Premium).
        self._enable_premium_button_fx()

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

        # ── Visualizer Premium (chỉ hiện cho gói Premium) ──
        self._premium_viz = None
        try:
            from core import entitlements
            if entitlements.is_premium():
                from ui.components.premium_visualizer import PremiumVisualizer
                self._premium_viz = PremiumVisualizer()
                wl.addWidget(self._premium_viz)
        except Exception as e:
            print(f"[PREMIUM-VIZ] init lỗi: {e}")

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
            scale_btn.setToolTip("Đang ở thể Major. Bấm để đổi sang Minor.")
        else:
            scale_btn.setText("Minor")
            scale_btn.setStyleSheet(pill_btn_qss(C["orange"], _lighten(C["orange"], 0.12), 11, 14))
            scale_btn.setToolTip("Đang ở thể Minor. Bấm để đổi sang Major.")

    # Tên 12 nốt — dùng cho relative + reverse-lookup
    _CHROMATIC_KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    RELATIVE_MINOR_OFFSET = 9  # Major + 9 semitone = relative Minor (đồng bộ ToneDetector)

    @staticmethod
    def _reverse_lookup_key(value, key_midi_map, keys=None):
        """MIDI value → tên nốt, bền với map calibrate phi tuyến / đảo chiều.

        Chọn nốt có MIDI value GẦN nhất với ``value``. Khi nhiều nốt cách đều
        nhau (tie), ưu tiên nốt KHỚP CHÍNH XÁC nếu có; nếu vẫn hoà thì giữ nốt
        đầu tiên gặp theo thứ tự chromatic (ổn định, không phụ thuộc giá trị
        tuyệt đối của MIDI value như cách "ưu tiên key thấp" cũ).
        """
        if keys is None:
            keys = MainDashboard._CHROMATIC_KEYS
        best_key = keys[0]
        best_diff = None
        best_exact = False
        for k in keys:
            midi_val = key_midi_map.get(k, 0)
            diff = abs(midi_val - value)
            exact = (midi_val == value)
            if best_diff is None or diff < best_diff:
                best_diff, best_key, best_exact = diff, k, exact
            elif diff == best_diff and exact and not best_exact:
                # Tie về khoảng cách → ưu tiên nốt khớp chính xác value
                best_key, best_exact = k, True
        return best_key

    @staticmethod
    def _reverse_lookup_scale(value, scale_midi_map):
        """MIDI value → 'Major'/'Minor' theo value gần nhất, có guard chống chia
        nhầm khi map bất thường (Major == Minor → mặc định 'Major')."""
        major_val = scale_midi_map.get("Major", 13)
        minor_val = scale_midi_map.get("Minor", 18)
        if major_val == minor_val:
            # Map hỏng / hai thể trùng value → không thể phân biệt, giữ Major
            return "Major"
        return "Minor" if abs(value - minor_val) < abs(value - major_val) else "Major"

    def _lock_replay_for_manual_override(self):
        """Khi user chỉnh tone/scale tay → dừng replay timeline để mốc kế tiếp
        không gửi MIDI đè lên lựa chọn của user. Replay sẽ bật lại khi user
        bấm "Dò Lại" hoặc đổi bài (đường đi dò tone mới gọi start_scanning)."""
        try:
            self.engine.stop_tone_detection()
        except Exception as e:
            print(f"[TONE] Không dừng được replay khi override tay: {e}")
        self._manual_tone_override = True
        # Dừng nhịp bám timeline ngay lập tức, nếu không mốc kế tiếp sẽ ghi đè
        # lựa chọn vừa chỉnh tay của user trong vòng 250ms.
        self._tone_ticker_sync()

    def _on_tone_selected(self, value):
        self.current_tone = value
        key_midi_map = backend.AppConfig.get_key_midi_map()
        key_midi = key_midi_map.get(value, 0)
        self.engine.send_midi(MIDI_CC.get("key_root", 33), key_midi)
        self._lock_replay_for_manual_override()

    def _on_scale_selected(self, value):
        self.current_scale = value
        self.scale_is_major = (value == "Major")
        scale_midi_map = backend.AppConfig.get_scale_midi_map()
        # Dùng "scale_type" — CC key thống nhất toàn bộ code
        scale_midi = scale_midi_map.get(value, 13)
        self.engine.send_midi(MIDI_CC.get("scale_type", MIDI_CC.get("key_scale", 35)), scale_midi)
        self._sync_scale_button(self.scale_is_major)
        self._lock_replay_for_manual_override()

    def _on_toggle_relative(self):
        """Đổi tone hiện tại sang tone tương đối (C Trưởng ↔ La Thứ).
        Đổi CẢ nốt gốc LẪN thể trong một chạm, rồi gửi MIDI như khi user chọn tay."""
        cur_key = getattr(self, 'current_tone', 'C') or 'C'
        cur_scale = getattr(self, 'current_scale', 'Major') or 'Major'
        try:
            idx = self._CHROMATIC_KEYS.index(cur_key)
        except ValueError:
            idx = 0
        if cur_scale == "Major":
            # Major → relative Minor: index + 9
            new_idx = (idx + self.RELATIVE_MINOR_OFFSET) % 12
            new_scale = "Minor"
        else:
            # Minor → relative Major: index - 9 (== + 3)
            new_idx = (idx - self.RELATIVE_MINOR_OFFSET) % 12
            new_scale = "Major"
        new_key = self._CHROMATIC_KEYS[new_idx]

        # Cập nhật combo + gửi MIDI (đi qua _on_tone_selected/_on_scale_selected để
        # phát MIDI giống hệt khi user chọn tay; cũng khoá replay luôn).
        with QSignalBlocker(self.tone_combo):
            self.tone_combo.setCurrentText(new_key)
        with QSignalBlocker(self.scale_combo):
            self.scale_combo.setCurrentText(new_scale)
        # Phát MIDI thủ công (đã chặn signal ở trên để tránh gọi 2 lần)
        self._on_tone_selected(new_key)
        self._on_scale_selected(new_scale)
        self._show_message(f"Đổi sang tone tương đối: {new_key} {new_scale}")

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
            if cc == int(MIDI_CC.get("key_root", 33)):
                # Reverse-lookup bền: nốt có MIDI value gần nhất, tie-break ưu
                # tiên khớp chính xác (xem _reverse_lookup_key).
                best_key = self._reverse_lookup_key(value, backend.AppConfig.get_key_midi_map())
                if self.tone_combo.currentText() != best_key:
                    with QSignalBlocker(self.tone_combo):
                        self.tone_combo.setCurrentText(best_key)
                self.current_tone = best_key
            elif cc == int(MIDI_CC.get("scale_type", MIDI_CC.get("key_scale", 35))):
                # Reverse-lookup thể theo value gần nhất, có guard major==minor.
                scale_str = self._reverse_lookup_scale(value, backend.AppConfig.get_scale_midi_map())
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
            if cc == int(MIDI_CC.get("tone_auto", 40)):
                self.tune_state = (value >= 64)
                btn = self._func_buttons.get("Auto-Tune")
                if btn: btn.setActive(self.tune_state)

            if cc == int(MIDI_CC.get("fix_meo", 45)):
                self.fix_meo_state = (value >= 64)
                btn = self._func_buttons.get("Fix Méo")
                if btn: btn.setActive(self.fix_meo_state)

            if cc == int(MIDI_CC.get("be", 47)):
                self.be_state = (value >= 64)
                btn = self._func_buttons.get("Bè")
                if btn: btn.setActive(self.be_state)

            if cc == int(MIDI_CC.get("tat_on", 48)):
                self.tat_on_state = (value >= 64)
                btn = self._func_buttons.get("Tắt Ồn")
                if btn: btn.setActive(self.tat_on_state)

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
        from core import kiosk, so_windows

        studio_one_path = self.settings.get("studio_one_path", "")

        # Phục hồi bản mẫu .song TRƯỚC khi mở Studio One — mọi thứ khách chỉnh
        # buổi trước biến mất, kỹ thuật viên không phải sửa lại tay.
        if kiosk.is_enabled() and kiosk.restore_template_enabled():
            try:
                from core import so_template
                result = so_template.restore(studio_one_path)
                if result["restored"]:
                    print("[KIOSK] Đã phục hồi bản mẫu Studio One")
            except Exception as e:
                print(f"[KIOSK] phục hồi bản mẫu lỗi: {e}")

        # Studio One
        launched = False
        if self.settings.get("auto_launch_studio_one", False):
            if studio_one_path and os.path.exists(studio_one_path):
                try:
                    self.engine.launch_app(studio_one_path)
                    launched = True
                except Exception:
                    pass

        # Chế độ khách: giấu Studio One đi. Vừa khởi chạy thì phải chờ nó dựng
        # xong cửa sổ (nạp bài + quét plugin mất hàng chục giây) rồi mới ẩn được.
        if kiosk.is_locked():
            try:
                if launched:
                    so_windows.hide_when_ready()
                elif so_windows.is_running():
                    so_windows.hide_all()
            except Exception as e:
                print(f"[KIOSK] ẩn Studio One lúc khởi động lỗi: {e}")
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

    def _show_support_dialog(self):
        from ui.dialogs.support_dialog import SupportDialog
        dlg = SupportDialog(self)
        dlg.unread_changed.connect(self._refresh_support_badge)
        dlg.exec()
        self._refresh_support_badge()

    def _on_support_reply(self, unread):
        """Slot main-thread: đội kỹ thuật vừa trả lời (từ luồng check-in nền).

        Toast chỉ là cú hích 2 giây; thứ thật sự giữ thông tin là chấm đỏ trên
        nút Hỗ trợ — nó ở lại tới khi khách mở hộp thư đọc.
        """
        self._refresh_support_badge(unread)
        self._show_message("Đội kỹ thuật đã trả lời — mở nút Hỗ trợ để xem.")

    def _refresh_support_badge(self, count=None):
        """Nút Hỗ trợ đỏ lên khi dev đã trả lời mà khách chưa đọc.

        KHÔNG gọi mạng ở đây — số liệu do core.support cập nhật từ luồng nền
        (main._background_maintenance) hoặc từ chính dialog.
        """
        btn = getattr(self, "_support_btn", None)
        if btn is None:
            return
        try:
            from core import support
            unread = support.unread_count() if count is None else int(count)
        except Exception:
            unread = 0
        btn.setColor(C["accent"] if unread else C["card_hover"])
        btn.setToolTip(
            f"Hỗ trợ kỹ thuật — {unread} trả lời chưa đọc" if unread
            else "Hỗ trợ kỹ thuật"
        )

    def _show_calibration_wizard(self):
        from ui.dialogs.calibration import CalibrationWizardDialog
        CalibrationWizardDialog(self).exec()
        global SCALE_VALUES
        SCALE_VALUES = backend.AppConfig.get_scale_values()

    def _wire_auto_tone_callbacks(self):
        """Nối callback dò tone tự động (thread-safe) vào engine. Dùng cho CẢ chế độ
        watcher trình duyệt ngoài lẫn chế độ player nhúng (dò tone cho bài tìm kiếm)."""
        def _auto_on_complete(result):
            self._tone_result_signal.emit(result)

        def _auto_on_error(msg):
            print(f"[YT WATCHER] Auto-detect loi: {msg}")
            self._tone_result_signal.emit({'error': msg, 'auto_detected': True})

        def _auto_on_progress(text):
            self._marquee_signal.emit(self._scan_marquee_text(text))

        self.engine.on_auto_tone_complete = _auto_on_complete
        self.engine.on_tone_detected_callback = _auto_on_complete
        self.engine.on_auto_tone_error = _auto_on_error
        self.engine.on_auto_tone_progress = _auto_on_progress

    def _start_youtube_watcher(self):
        """Khởi động YouTube URL Watcher với callbacks thread-safe."""
        self._wire_auto_tone_callbacks()
        self.engine.start_youtube_watcher()

    # ── Màn hình karaoke nhúng (bản Heavy) ───────────────────────────────────
    def _embedded_player_enabled(self) -> bool:
        """True nếu user bật player nhúng VÀ build hiện tại hỗ trợ (Heavy)."""
        try:
            from core import capabilities
            return bool(self.settings.get("use_embedded_player", False)) and \
                capabilities.embedded_player_available()
        except Exception:
            return False

    def _embedded_player_active(self) -> bool:
        return self._player_window is not None

    def _apply_embedded_player_setting(self):
        """Tạo/đóng cửa sổ karaoke + bật/tắt watcher theo thiết lập hiện tại.
        Gọi lúc khởi động và mỗi khi lưu Settings."""
        want = self._embedded_player_enabled()
        if want and self._player_window is None:
            self._create_player_window()
            # Chế độ nhúng: dừng watcher trình duyệt ngoài, chỉ nối callback dò tone.
            try:
                self.engine.stop_youtube_watcher()
            except Exception:
                pass
            self._wire_auto_tone_callbacks()
        elif not want:
            if self._player_window is not None:
                self._destroy_player_window()
            # Quay lại chế độ watcher trình duyệt ngoài nếu chưa chạy.
            if not getattr(self.engine, "_youtube_watcher_active", False):
                self._start_youtube_watcher()
        elif want and self._player_window is not None:
            # Đã bật sẵn — chỉ cập nhật màn hình hiển thị.
            self._player_window.move_to_monitor(int(self.settings.get("display_monitor_index", 0)))

    def _create_player_window(self):
        try:
            from ui.karaoke_player import KaraokePlayerWindow
        except ImportError as e:
            print(f"[PLAYER] Không thể tạo player nhúng: {e}")
            self._player_window = None
            return
        idx = int(self.settings.get("display_monitor_index", 0))
        self._player_window = KaraokePlayerWindow(monitor_index=idx)
        self._player_window.video_ended.connect(self._on_embedded_video_ended)
        self._player_window.embed_blocked.connect(self._on_embedded_embed_blocked)
        self._player_window.video_meta.connect(self._on_embedded_meta)
        self._player_window.stream_failed.connect(self._on_stream_failed)
        self._player_window.playback_stalled.connect(self._on_playback_stalled)
        # Bài nào đã thử lại luồng trực tiếp rồi thì lần kẹt sau mở trình duyệt
        # luôn, khỏi quay vòng native <-> IFrame.
        self._embedded_stall_retried = set()
        # Player nhúng phát bằng QMediaPlayer/IFrame nên Windows (WinRT) và CDP đều
        # không thấy vị trí phát. Signal này đã có sẵn từ đầu nhưng chưa ai nghe —
        # đây là nguồn vị trí DUY NHẤT ở chế độ nhúng.
        self._player_window.time_updated.connect(self._on_embedded_time)
        # Định tuyến điều khiển âm lượng sang player nhúng (thread-safe qua signal).
        self.engine.embedded_volume_callback = lambda v: self._embedded_volume_signal.emit(int(v))
        # Nguồn vị trí phát cho engine gửi MIDI theo timeline tone. Vòng lặp replay
        # chạy ở thread nền nên callback chỉ được đọc thuộc tính thuần của cửa sổ
        # player (playback_state), tuyệt đối không gọi API Qt.
        self.engine.embedded_position_callback = self._embedded_playback_state

    def _embedded_playback_state(self):
        """(vị trí giây, có đang phát không) cho engine. Cửa sổ đã đóng → (0, False)
        để vòng lặp replay đứng chờ thay vì bám một con số chết."""
        win = self._player_window
        if win is None:
            return 0.0, False
        return win.playback_state()

    def _destroy_player_window(self):
        try:
            self.engine.embedded_volume_callback = None
            self.engine.embedded_position_callback = None
        except Exception:
            pass
        # Vị trí cũ của player nhúng không còn giá trị — bỏ đi để _tone_current_position
        # rơi về CDP/WinRT thay vì bám một con số chết.
        self._embedded_pos = None
        if self._player_window is not None:
            try:
                self._player_window.close()
            except Exception:
                pass
            self._player_window = None

    def _set_embedded_volume(self, volume: int):
        if self._player_window is not None:
            self._player_window.set_volume(volume)

    def _embedded_video_id(self, url: str):
        clean = self.engine._clean_youtube_url(url) or url
        if "v=" in clean:
            return clean.split("v=")[-1][:11]
        return None

    def _load_embedded_video(self, url: str):
        """play_callback cho engine.open_youtube_url ở chế độ nhúng (Bài đã lưu /
        Setlist). Lấy luồng trực tiếp (không quảng cáo) rồi phát native; fallback
        IFrame nếu không được. Tone do engine.open_youtube_url tự lo — KHÔNG dò lại
        ở đây. An toàn gọi từ thread nền (kết quả marshal về GUI qua signal)."""
        if self._player_window is None:
            return
        self._embedded_current_url = url
        vid = self._embedded_video_id(url)
        import threading
        threading.Thread(
            target=self._resolve_and_play_stream, args=(url, vid or ""), daemon=True
        ).start()

    def play_youtube_in_app(self, url: str, autodetect: bool = True):
        """Phát 1 URL/bài (từ ô tìm kiếm hoặc dán link). Dùng player nhúng nếu bật,
        ngược lại mở trình duyệt ngoài như cũ."""
        if not url:
            return
        # Bài mở bằng link/ô tìm kiếm VẪN có thể là bài đã lưu chuỗi tone thủ
        # công — tra trước khi coi là bài lạ. Không tra thì đường này xoá sạch
        # timeline rồi để engine dò lại từ đầu, đè mất tone khách chỉnh tay.
        manual_tl = self._saved_manual_timeline(url)
        if manual_tl:
            self._set_tone_timeline(manual_tl, 0.0)
        else:
            # Bài lạ: xoá timeline bài cũ kẻo ô "kế tiếp" đếm ngược theo mốc của
            # bài trước đó.
            self._clear_tone_timeline()
        if not self._embedded_player_active():
            self.engine.open_youtube_url(
                url,
                on_video_end_callback=lambda res: None,
                on_tone_detected=lambda result: self._tone_result_signal.emit(result),
                manual_timeline=manual_tl,
            )
            return
        self._embedded_current_url = url
        # Dò tone chạy độc lập (đường yt-dlp riêng) — kích ngay. Có tone đã lưu
        # thì bước resolve trong đó trả về ngay, không tải audio.
        if autodetect:
            self.engine._ensure_tone_for_url(url)
        # Lấy luồng trực tiếp (không quảng cáo) ở nền; xong marshal về GUI để phát.
        vid = self._embedded_video_id(url)
        self._marquee_signal.emit(self._spinner_progress_text("Đang tải video…"))
        import threading
        threading.Thread(
            target=self._resolve_and_play_stream, args=(url, vid or ""), daemon=True
        ).start()

    def _resolve_and_play_stream(self, url: str, video_id: str):
        """Nền: yt-dlp trích luồng progressive (video+audio 1 file, không cần ffmpeg
        để phát trực tiếp). Chọn itag 22 (720p) → 18 (360p) → progressive tốt nhất."""
        stream_url, title, err_msg = "", "", ""
        try:
            from core.ytdlp_support import (
                PURPOSE_VIDEO, extract_info_with_auth, make_ydl_opts,
            )
            # Cần luồng PROGRESSIVE (itag 22/18 — 1 file video+audio, phát thẳng
            # không cần ffmpeg) và URL mở được trong QMediaPlayer; luồng DASH
            # không phát trực tiếp được.
            #
            # KHÔNG ép player_client ở đây nữa: danh sách cũ
            # ["tv_embedded","android","ios"] vừa đã bị yt-dlp 2026.07 bỏ
            # (tv_embedded) vừa chưa bao giờ có hiệu lực (bị _apply_player_clients
            # xoá). Thang client giờ do `purpose=PURPOSE_VIDEO` quyết định — nó
            # ưu tiên bộ client cho nhiều luồng progressive chất lượng cao nhất
            # khi máy đã có PO Token, và tự lùi về android khi chưa có.
            opts = make_ydl_opts(
                skip_download=True,
                format=("22/18/best[vcodec!=none][acodec!=none][ext=mp4]"
                        "/best[vcodec!=none][acodec!=none]"),
            )
            info = extract_info_with_auth(url, opts, download=False, log_prefix="[STREAM]",
                                          purpose=PURPOSE_VIDEO)
            if info:
                title = info.get("title") or ""
                stream_url = info.get("url") or ""
                if not stream_url:
                    # Không có url top-level → quét formats tìm luồng progressive.
                    for f in info.get("formats", []):
                        if (f.get("url") and f.get("acodec") not in (None, "none")
                                and f.get("vcodec") not in (None, "none")):
                            stream_url = f["url"]
        except Exception as e:
            # yt-dlp dựng sẵn thông báo chẩn đoán tiếng Việt cho từng lớp lỗi
            # (thiếu PO Token, 403, trình duyệt khoá file cookie…). Trước đây nó
            # chỉ ra console rồi app lặng lẽ lùi sang IFrame — người dùng nhận
            # đúng một màn hình lỗi khó hiểu của YouTube ("Mã lượt phát: VX-…")
            # thay vì lý do thật kèm cách sửa.
            err_msg = str(e)
            print(f"[STREAM] resolve lỗi: {e}")
        self._stream_resolved_signal.emit(video_id, stream_url, title, err_msg)

    def _on_stream_resolved(self, video_id: str, stream_url: str, title: str,
                            error: str = ""):
        """GUI thread: có luồng → phát native (không QC); không có → fallback IFrame."""
        if self._player_window is None:
            return
        if stream_url:
            # play_stream tự emit video_meta (đã nối tới _on_embedded_meta) nếu có title.
            self._player_window.play_stream(stream_url, title, video_id)
            return
        # Vẫn thử IFrame (nhiều bài phát được), nhưng phải nói rõ vì sao mất
        # luồng trực tiếp — nếu IFrame cũng hỏng thì đây là manh mối duy nhất.
        if error:
            self._show_message(error, is_error=True)
        else:
            self._show_message("Không lấy được luồng trực tiếp")
        if video_id:
            self._player_window.load_video(video_id)

    def _on_stream_failed(self, video_id: str):
        """Luồng native lỗi giữa chừng → lùi sang IFrame YouTube."""
        if self._player_window is not None and video_id:
            self._player_window.load_video(video_id)

    def _on_playback_stalled(self, video_id: str):
        """IFrame YouTube cũng không lên hình — gồm cả lỗi "Mã lượt phát: VX-…"
        mà YouTube tự vẽ trong iframe (không bắn onError, app chỉ biết qua
        watchdog quá hạn chờ).

        Thử lại luồng trực tiếp MỘT lần trước đã: URL googlevideo có hạn dùng và
        rất hay hết hạn giữa chừng, resolve lại thường là phát được ngay. Hết
        cách mới chịu mở trình duyệt ngoài."""
        if self._player_window is None:
            return
        url = getattr(self, "_embedded_current_url", None) or self.engine.current_youtube_url
        retried = getattr(self, "_embedded_stall_retried", None)
        if retried is None:
            retried = self._embedded_stall_retried = set()
        key = video_id or url
        if url and key and key not in retried:
            retried.add(key)
            self._show_message("Đang thử lại luồng trực tiếp…")
            import threading
            threading.Thread(target=self._resolve_and_play_stream,
                             args=(url, video_id or ""), daemon=True).start()
            return
        self._show_message("Mở bằng trình duyệt ngoài")
        if url:
            self.engine.open_youtube_url(
                url,
                on_video_end_callback=lambda res: None,
                on_tone_detected=lambda result: self._tone_result_signal.emit(result),
            )

    def _on_embedded_video_ended(self):
        try:
            self.engine.notify_video_ended()
        except Exception as e:
            print(f"[PLAYER] notify_video_ended lỗi: {e}")

    def _on_embedded_embed_blocked(self):
        """Video chặn nhúng → fallback mở trình duyệt ngoài + báo người dùng."""
        url = getattr(self, "_embedded_current_url", None) or self.engine.current_youtube_url
        self._show_message("Video không cho nhúng — mở trình duyệt")
        if url:
            self.engine.open_youtube_url(
                url,
                on_video_end_callback=lambda res: None,
                on_tone_detected=lambda result: self._tone_result_signal.emit(result),
            )

    def _on_embedded_meta(self, title: str, video_id: str):
        if not title:
            return
        try:
            tone = self.current_tone
            if self._waveform is not None:
                self._waveform.set_song_info(title, tone, self.current_scale, 0)
            self._marquee_text = f"🎵 {title}   ★   {tone}"
        except Exception:
            pass

    # ── Tìm kiếm YouTube trong app (chế độ player nhúng) ──────────────────────
    def _on_search_submit(self):
        """Người dùng nhấn tìm/Enter: nếu là link → phát ngay, nếu là từ khoá → tìm."""
        q = self._search_input.text().strip() if self._search_input is not None else ""
        if not q:
            return
        # Là link YouTube? → phát luôn
        if self._embedded_video_id(q):
            self.play_youtube_in_app(q, autodetect=True)
            self._search_input.clear()
            self._hide_search_results()
            return
        # Từ khoá → tìm nền
        self._marquee_signal.emit(self._spinner_progress_text(f"Đang tìm: {q}"))
        import threading
        threading.Thread(target=self._do_youtube_search, args=(q,), daemon=True).start()

    def _do_youtube_search(self, query: str):
        results = []
        try:
            from core.ytdlp_support import extract_info_with_auth, make_ydl_opts
            info = extract_info_with_auth(
                f"ytsearch6:{query}",
                make_ydl_opts(skip_download=True, default_search='ytsearch', extract_flat=True),
                download=False,
                log_prefix="[SEARCH]",
            )
            for e in (info.get('entries', []) if info else []):
                if not e:
                    continue
                vid = e.get('id', '')
                if not vid:
                    continue
                results.append({
                    'id': vid,
                    'title': e.get('title', '(không tên)'),
                    'uploader': e.get('uploader') or e.get('channel') or '',
                })
        except Exception as ex:
            print(f"[SEARCH] lỗi: {ex}")
        self._search_results_signal.emit(results)

    def _on_search_results(self, results):
        lst = getattr(self, "_search_results_list", None)
        if lst is None:
            return
        lst.clear()
        if not results:
            self._marquee_signal.emit("Không tìm thấy kết quả")
            self._hide_search_results()
            return
        from PySide6.QtWidgets import QListWidgetItem
        for r in results:
            label = r['title']
            if r.get('uploader'):
                label += f"  —  {r['uploader']}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, r['id'])
            lst.addItem(item)
        lst.setVisible(True)
        self._marquee_signal.emit(f"Tìm thấy {len(results)} kết quả — chọn 1 bài")

    def _on_search_result_clicked(self, item):
        vid = item.data(Qt.UserRole)
        if not vid:
            return
        url = f"https://www.youtube.com/watch?v={vid}"
        self.play_youtube_in_app(url, autodetect=True)
        self._hide_search_results()
        if self._search_input is not None:
            self._search_input.clear()

    def _hide_search_results(self):
        lst = getattr(self, "_search_results_list", None)
        if lst is not None:
            lst.setVisible(False)

    _SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def _spinner_progress_text(self, text):
        """Bọc chuỗi tiến trình backend bằng spinner xoay (luân phiên frame mỗi
        lần gọi) để user thấy app đang chạy chứ không treo."""
        idx = getattr(self, '_spinner_idx', 0)
        self._spinner_idx = (idx + 1) % len(self._SPINNER_FRAMES)
        frame = self._SPINNER_FRAMES[idx]
        msg = (text or "").strip() or "Đang dò tone..."
        return f"{frame}  {msg}  {frame}"

    # Marquee lúc dò tone chỉ nói MỘT câu. Các bước bên trong (kiểm tra cache,
    # tải audio, phân tích, lưu kết quả…) là chuyện của máy — người hát chỉ cần
    # biết app đang chạy. Text tiến trình thật vẫn in ra log cho kỹ thuật viên.
    SCAN_MARQUEE_TEXT = "Đang dò..."

    def _scan_marquee_text(self, backend_text=""):
        if backend_text:
            print(f"[TONE] {backend_text}")
        return self._spinner_progress_text(self.SCAN_MARQUEE_TEXT)

    def _brand_marquee_text(self, default: str) -> str:
        """Text thương hiệu/nhàn rỗi cho marquee. Khách VIP (Premium) được chào
        đón riêng; còn lại giữ text mặc định."""
        try:
            from core import entitlements
            if entitlements.is_premium():
                return "👑  Chào mừng Quý khách VIP đến với Quang Lưu Studio  👑"
        except Exception:
            pass
        return default

    def _set_marquee_text(self, text):
        """Slot main-thread cho _marquee_signal — cập nhật marquee an toàn."""
        self._marquee_text = text

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
            self._show_message("Dò Full: quét cả bài, bám đổi tone")
        else:
            self.engine.tone_scan_mode = 'fast'
            if btn:
                old_key = btn.text()
                btn.setText("Chế độ: Nhanh")
                btn.setStyleSheet(pill_btn_qss(C["orange"], _lighten(C["orange"], 0.12), 11, 14))
                if old_key in self._func_buttons:
                    self._func_buttons["Chế độ: Nhanh"] = self._func_buttons.pop(old_key)
            self._show_message("Dò Nhanh: nghe 45 giây đầu")

    def _set_rescan_button_state(self, state: str):
        """Centralized button state: 'idle' | 'running' | 'cancel'.
        Avoids duplicating button-style logic across 3 code paths."""
        btn = (self._func_buttons.get("Dò Lại")
               or self._func_buttons.get("⏳ Đang dò...")
               or self._func_buttons.get("Huỷ"))
        if not btn:
            return
        old_key = btn.text()
        if state == "idle":
            btn.setEnabled(True)
            btn.setText("Dò Lại")
            btn.setStyleSheet(pill_btn_qss(C["teal"], _lighten(C["teal"], 0.12), 11, 14))
        elif state == "running":
            btn.setEnabled(True)
            btn.setText("Huỷ")
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
        self._marquee_text = self._brand_marquee_text("♪ Quang Lưu Studio — Karaoke Pro ♪")
        self._show_message("Đã huỷ dò tone")

    def _on_force_rescan(self):
        # If already running → treat as cancel
        if getattr(self, '_do_tone_running', False):
            self._on_cancel_rescan()
            return
        self._do_tone_running = True
        # User chủ động dò lại → bỏ khoá override tay (cho phép kết quả mới ghi đè).
        self._manual_tone_override = False

        self._set_rescan_button_state("running")
        self.autokey_dot.setStyleSheet(f"color: {C['orange']}; font-size: 16px;")
        self._marquee_text = self._scan_marquee_text()

        import weakref
        url = getattr(self.engine, 'current_youtube_url', None)
        # Backend vẫn bắn tiến trình từng bước; marquee chỉ nhận một câu,
        # bước thật đi vào log (xem _scan_marquee_text).
        def _on_progress(text):
            self._marquee_signal.emit(self._scan_marquee_text(text))
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
                on_progress=_on_progress,
                skip_resolve=True
            )

    # ── Hướng dẫn khi nghe loa (loopback) thất bại ──────────────────────────
    # Các cụm từ này xuất hiện trong message lỗi do core trả về (core/tone_detector.py,
    # core/engine/_tone.py) khi phương án dự phòng "nghe từ loa" không có âm thanh —
    # thường vì loa/tai nghe đang nghe KHÁC thiết bị mặc định của Windows.
    _SPEAKER_ERR_HINTS = (
        "không phát ra âm thanh",
        "nghe loa cũng thất bại",
        "nghe từ loa",
        "nghe được âm thanh từ loa",
        "lỗi khi nghe âm thanh từ loa",
        "loa mặc định",
    )

    @classmethod
    def _is_speaker_loopback_error(cls, msg):
        """True nếu message lỗi nói về việc nghe loa/loopback thất bại."""
        low = (msg or "").lower()
        return any(h in low for h in cls._SPEAKER_ERR_HINTS)

    def _open_sound_settings(self):
        """Mở trang Cài đặt âm thanh của Windows (ms-settings:sound)."""
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        if not QDesktopServices.openUrl(QUrl("ms-settings:sound")):
            # Dự phòng nếu ms-settings bị chặn: mở Control Panel âm thanh cổ điển
            try:
                os.startfile("mmsys.cpl")
            except Exception:
                self._show_message(
                    "Không mở được Cài đặt âm thanh. Hãy chuột phải biểu tượng "
                    "loa ở khay hệ thống.", is_error=True)

    def _show_speaker_help(self, msg):
        """Thông báo lỗi nghe loa kèm hướng dẫn từng bước + nút mở Cài đặt âm thanh.

        Người dùng phổ thông thường cắm tai nghe nhưng Windows vẫn để loa cũ làm
        mặc định → app nghe nhầm thiết bị im lặng. Hướng dẫn họ đặt đúng thiết bị
        đang nghe làm Output mặc định."""
        guide = (
            f"{msg}\n\n"
            "👉 Cách sửa: app chỉ nghe được THIẾT BỊ ÂM THANH MẶC ĐỊNH của Windows.\n"
            "1. Chuột phải biểu tượng loa 🔈 ở khay hệ thống (góc dưới phải).\n"
            "2. Chọn 'Open Sound settings' (Mở cài đặt âm thanh).\n"
            "3. Ở mục Output / Đầu ra, chọn ĐÚNG thiết bị bạn đang nghe (tai nghe "
            "hoặc loa) làm mặc định.\n"
            "4. Phát lại bài hát rồi bấm 'Dò Lại'."
        )
        # Dùng panel lỗi (ở lâu, không cắt cụt) nhưng gắn thêm nút mở Cài đặt.
        self._show_message(guide, is_error=True, action_text="Mở Cài đặt âm thanh",
                           action_cb=self._open_sound_settings)

    # ── Timeline tone: nguồn sự thật cho phần HIỂN THỊ ───────────────────────
    # Engine vẫn là bên gửi MIDI và vẫn bắn callback mỗi lần đổi tone. Phần dưới
    # đây chỉ lo hiển thị, và tự tính lấy vị trí phát vì engine không hề gửi
    # thông tin "đoạn kế tiếp còn bao lâu" — thứ người chỉnh cần nhất.

    @staticmethod
    def _save_single_tone_timeline(url, title, key_display):
        """Ghi chuỗi tone thủ công 1 mốc (0:00) cho bài — tone khách tự chọn.

        Bỏ qua khi bài đã có chuỗi NHIỀU mốc: chuỗi đó chi tiết hơn và cũng do
        khách tạo, ghi đè bằng một tone duy nhất là làm mất công sức của khách.
        Trả True nếu có ghi.
        """
        if not url or not key_display:
            return False
        try:
            from core.tone_cache import ManualToneTimeline, make_timeline_entry
            existing = ManualToneTimeline.load_timeline(url)
            if existing and len(existing.get("timeline") or []) > 1:
                return False
            return bool(ManualToneTimeline.save_timeline(
                url, title or "", [make_timeline_entry(key_display)], source="human"))
        except Exception as e:
            print(f"[TONE UI] Không lưu được tone thủ công: {e}")
            return False

    @staticmethod
    def _saved_manual_timeline(url):
        """Chuỗi tone khách đã lưu cho URL này (thủ công → tone đơn của bài), hoặc None.

        Mọi đường mở bài (Danh sách bài hát, dán link / tìm kiếm, Setlist) đều đi
        qua đây để không đường nào bỏ sót tone đã lưu rồi để engine dò lại.
        """
        try:
            from core.tone_cache import saved_tone_timeline
            return saved_tone_timeline(url)
        except Exception as e:
            print(f"[TONE UI] Không đọc được chuỗi tone đã lưu: {e}")
            return None

    def _set_tone_timeline(self, timeline, duration=0.0):
        """Nạp timeline cho phần hiển thị (3 chỗ gọi: phát bài đã lưu ở dashboard,
        phát từ Danh sách bài hát, và khi dò xong toàn bài)."""
        entries = []
        for e in (timeline or []):
            if not isinstance(e, dict):
                continue
            try:
                entries.append({**e, "time": float(e.get("time", 0) or 0)})
            except (TypeError, ValueError):
                continue
        entries.sort(key=lambda x: x["time"])
        self._tone_timeline = entries
        self._tone_index = -1
        self._tone_position = 0.0
        self._tone_duration = float(duration or 0.0)
        self._embedded_pos = None
        self._tone_ticker_sync()

    def _clear_tone_timeline(self):
        """Đổi bài / bài không có timeline → xoá sạch, tránh timeline bài cũ rò
        sang bài mới."""
        self._set_tone_timeline([], 0.0)

    def _on_embedded_time(self, position: float, duration: float):
        """Player nhúng báo vị trí phát (signal có sẵn từ trước, chưa ai nghe)."""
        self._embedded_pos = (float(position), float(duration))
        if duration and not self._tone_duration:
            self._tone_duration = float(duration)

    def _tone_current_position(self):
        """Vị trí đang phát (giây). Thứ tự ưu tiên giống hệt _music_is_playing:
        player nhúng → CDP → WinRT. None = không nguồn nào biết."""
        try:
            if self._player_window is not None and self._embedded_pos is not None:
                return self._embedded_pos[0]
            cdp = getattr(self.engine, "cdp_monitor", None)
            if cdp is not None and getattr(cdp, "is_connected", False):
                return float(cdp.current_position)
            win_media = getattr(self.engine, "media_monitor", None)
            if win_media is not None:
                return float(win_media.current_position)
        except Exception as e:
            print(f"[TONE UI] Đọc vị trí phát lỗi: {e}")
        return None

    def _tone_ticker_sync(self):
        """Bật/tắt nhịp 250ms theo trạng thái thật. Gọi từ timer 2.5s sẵn có nên
        không tốn thêm timer nào để canh."""
        if self._tone_tick_timer is None:
            return
        pill = getattr(self, "_next_tone_pill", None)
        has_timeline = len(self._tone_timeline) > 1

        if not has_timeline:
            self._tone_tick_timer.stop()
            if pill is not None:
                pill.setVisible(False)
            return

        if self._manual_tone_override:
            # User đã chỉnh tay → engine đã dừng replay, timeline không còn là
            # thẩm quyền. Không ghi đè lựa chọn của user, chỉ nói rõ đang ở chế độ nào.
            self._tone_tick_timer.stop()
            if pill is not None:
                pill.setVisible(True)
                pill.set_message("chỉnh tay")
            return

        if pill is not None:
            pill.setVisible(True)
        if self._music_is_playing():
            if not self._tone_tick_timer.isActive():
                self._tone_tick_timer.start(250)
        else:
            self._tone_tick_timer.stop()

    def _tone_segment_at(self, position):
        """Trả (chỉ số đoạn, giây còn lại, phần còn lại 1→0, entry kế tiếp).

        Đoạn cuối kết thúc ở _tone_duration; không biết độ dài bài thì không có
        đếm ngược cho đoạn cuối (trả None) chứ không bịa số.
        """
        tl = self._tone_timeline
        if not tl:
            return -1, None, None, None
        idx = 0
        for i, entry in enumerate(tl):
            if position >= entry["time"] - 0.05:
                idx = i
            else:
                break
        start = tl[idx]["time"]
        nxt = tl[idx + 1] if idx + 1 < len(tl) else None
        end = nxt["time"] if nxt else (self._tone_duration or None)
        if not end or end <= start:
            return idx, None, None, nxt
        remaining = max(0.0, end - position)
        return idx, remaining, remaining / (end - start), nxt

    def _on_tone_tick(self):
        """Nhịp 250ms: bám vị trí phát → cập nhật ô tone + ô 'kế tiếp'."""
        # Chốt lại ngay đầu vòng: _tone_ticker_sync() đã stop() timer khi user
        # chỉnh tay, nhưng một timeout ĐÃ nằm sẵn trong hàng đợi Qt vẫn nổ thêm
        # một nhịp nữa — đủ để ghi đè lựa chọn vừa chỉnh tay.
        if self._manual_tone_override or len(self._tone_timeline) < 2:
            return
        position = self._tone_current_position()
        if position is None:
            return
        self._tone_position = position
        idx, remaining, fraction, nxt = self._tone_segment_at(position)
        if idx < 0:
            return

        if idx != self._tone_index:
            self._tone_index = idx
            entry = self._tone_timeline[idx]
            key_root = self._key_root_of(entry)
            changed = self._sync_tone_widgets(
                key_root, entry.get("scale", "Major"), flash=True,
            )
            if changed:
                # Chỉ dựng lại marquee khi tone THỰC SỰ đổi — đặt text mới sẽ
                # reset vòng chạy chữ, làm mỗi 250ms thì chữ đứng im tại chỗ.
                self._refresh_tone_marquee()

        pill = getattr(self, "_next_tone_pill", None)
        if pill is None:
            return
        if nxt is not None and remaining is not None:
            pill.set_next(nxt.get("key_display", "?"), remaining, fraction)
        elif nxt is not None:
            pill.set_next(nxt.get("key_display", "?"), 0.0, None)
        else:
            pill.set_message("đoạn cuối")

    @staticmethod
    def _key_root_of(entry):
        """Nốt gốc từ 1 entry timeline: ưu tiên 'key', không có thì bỏ hậu tố 'm'."""
        key = entry.get("key")
        if key:
            return key
        return (entry.get("key_display", "C") or "C").rstrip("m") or "C"

    def _sync_tone_widgets(self, key_root, scale, accent=None, flash=False):
        """Đặt tone/thể lên header. Trả True nếu giá trị THỰC SỰ đổi.

        Dùng chung cho cả hai đường vào (callback của engine và nhịp 250ms) để
        hai bên không đá nhau — bên đến sau thấy 'không đổi' thì không chớp lần hai.
        """
        changed = (key_root != self.tone_combo.currentText()
                   or scale != self.scale_combo.currentText())
        self.current_tone = key_root
        self.current_scale = scale
        with QSignalBlocker(self.tone_combo):
            self.tone_combo.setCurrentText(key_root)
        with QSignalBlocker(self.scale_combo):
            self.scale_combo.setCurrentText(scale)
        # Các API riêng của widget mới — dùng getattr để test/bản cũ dựng UI bằng
        # QComboBox thuần vẫn chạy được.
        set_scale_text = getattr(self.tone_combo, "set_scale_text", None)
        if set_scale_text is not None:
            set_scale_text(scale)
        if accent is not None:
            set_accent = getattr(self.tone_combo, "set_accent", None)
            if set_accent is not None:
                set_accent(accent)
        if flash and changed:
            do_flash = getattr(self.tone_combo, "flash", None)
            if do_flash is not None:
                do_flash()
        return changed

    def _compose_tone_marquee(self, badge=""):
        """Chữ chạy: tên bài ★ tone hiện tại ▸ kế tiếp.

        Cố ý KHÔNG in cả chuỗi 20 đoạn — người hát chỉ cần biết đang ở đâu và
        sắp tới đâu. Cũng không kèm số giây vì marquee chỉ dựng lại khi đổi tone,
        số giây nằm ở ô 'kế tiếp' (cập nhật 4 lần/giây).
        """
        title = getattr(self, "current_title", "") or ""
        key = self.current_tone or "C"
        scale = self.current_scale or "Major"
        display = key + ("m" if scale == "Minor" else "")

        core = display
        idx = self._tone_index
        # idx < 0 = chưa bám được đoạn nào (vừa dò xong, chưa phát). Lúc đó chưa
        # biết "kế tiếp" là gì — timeline[0] là đoạn ĐẦU chứ không phải đoạn sau.
        if idx >= 0 and idx + 1 < len(self._tone_timeline):
            core += f"  ▸ kế: {self._tone_timeline[idx + 1].get('key_display', '?')}"
        if len(self._tone_timeline) > 1 and idx >= 0:
            core += f"  ({idx + 1}/{len(self._tone_timeline)})"

        if title:
            return f"🎵 {title}   ★   {core}{badge}"
        return f"🎵 {core}{badge}"

    def _refresh_tone_marquee(self, badge=""):
        self._marquee_text = self._compose_tone_marquee(badge)

    def _handle_tone_result(self, result):
        """Slot xử lý kết quả dò tone trên main thread (thread-safe via Signal)"""

        # === Lọc các trạng thái KHÔNG phải kết quả tone ===
        # Callback on_key_update gửi {'status':'listening'/'stopped'} khi im lặng /
        # dừng — KHÔNG được set combo (key_display có thể là '...' không hợp lệ →
        # nhấp nháy/rỗng). Chỉ early-return, không chạm UI tone.
        status = result.get('status')
        if status in ('listening', 'stopped'):
            return
        # Phòng hờ: nếu CÓ key/key_display nhưng KHÔNG thuộc 12 nốt (vd '...',
        # 'Silence', 'Unknown') → bỏ qua để combo không bị set giá trị lạ. Khi cả
        # hai đều vắng mặt thì để nhánh thành công dùng default 'C' như cũ.
        if 'error' not in result:
            raw_key = result.get('key')
            raw_disp = result.get('key_display')
            if raw_key is not None or raw_disp is not None:
                kd_root = (raw_key or '').rstrip('m')
                kd_disp = (raw_disp or '').rstrip('m')
                valid_keys = self._CHROMATIC_KEYS
                if (kd_root not in valid_keys) and (kd_disp not in valid_keys):
                    return

        # === Trường hợp LỖI ===
        if 'error' in result:
            msg = result['error']
            self._do_tone_running = False
            self._do_tone_done = False
            self._set_rescan_button_state("idle")
            self.autokey_dot.setStyleSheet(f"color: {C['card_hover']}; font-size: 16px;")
            self._marquee_text = self._brand_marquee_text("♪ Quang Lưu Studio — Karaoke Pro ♪")
            # Lỗi liên quan tới việc NGHE LOA (loopback) thường do tai nghe / loa
            # đang nghe KHÁC với thiết bị mặc định Windows → kèm hướng dẫn cụ thể
            # + nút mở "Cài đặt âm thanh" thay vì chỉ báo lỗi cụt.
            if self._is_speaker_loopback_error(msg):
                self._show_speaker_help(msg)
            else:
                self._show_message(f"{msg}", is_error=True)
            return
        
        # === Trường hợp THÀNH CÔNG ===
        self._do_tone_running = False
        # Kết quả dò mới từ backend → bỏ khoá manual override (replay/auto được
        # phép gửi MIDI lại bình thường).
        self._manual_tone_override = False

        # Nếu là auto-detect → cập nhật trạng thái nút mà không cần user nhấn trước
        is_auto = result.get('auto_detected', False)

        # Cờ nguồn + độ tin cậy (backend mới cung cấp)
        from_cache = result.get('from_cache', False)
        from_manual = result.get('from_manual', False)
        uncertain = result.get('uncertain', False)
        confidence_level = result.get('confidence_level', '')
        
        # === 1. Cập nhật Key/Scale lên UI chính ===
        key_display = result.get('key_display', 'C')
        # Engine luôn trả 'key' = root note (đã strip 'm' suffix)
        key_root = result.get('key', 'C')
        scale = result.get('scale', 'Major')
        # Sự kiện CHUYỂN TONE lúc đang phát không kèm title. Lấy title cũ thay vì
        # chuỗi rỗng — nếu không, mỗi lần đổi tone là một lần xoá trắng tên bài
        # trên waveform hero và trên chữ chạy.
        title = result.get('title') or getattr(self, 'current_title', '') or ''
        if title:
            self.current_title = title

        # Kết quả dò toàn bài mang theo cả timeline → nạp cho phần hiển thị bám
        # theo. Sự kiện chuyển tone lẻ (có 'time') thì không đụng tới timeline
        # đang có.
        if result.get('timeline'):
            self._set_tone_timeline(result['timeline'], result.get('total_duration', 0))
        elif 'time' not in result and not result.get('from_cache') and not result.get('from_manual'):
            # Dò ra đúng MỘT tone cho cả bài → không còn timeline nào hợp lệ.
            self._clear_tone_timeline()

        # Tránh gửi MIDI trùng lặp khi set combo (backend đã gửi rồi)
        is_low_conf_pre = bool(uncertain) or (confidence_level == 'low')
        self._sync_tone_widgets(
            key_root, scale,
            accent=C['orange'] if is_low_conf_pre else C['green'],
            flash=True,
        )

        # Đổi style combobox theo độ tin cậy:
        #  - chắc chắn  → text xanh lá (green)
        #  - chưa chắc (uncertain / confidence thấp) → text cam cảnh báo
        is_low_conf = bool(uncertain) or (confidence_level == 'low')
        combo_color = C['orange'] if is_low_conf else C['green']
        detected_combo_qss = f"""
            QComboBox {{
                background-color: transparent;
                color: {combo_color};
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
                selection-background-color: {combo_color};
                border: 1px solid rgba(255, 255, 255, 0.5);
                font-size: 13px;
                font-family: {FONT};
            }}
        """
        # Widget tự tạo dáng (SELF_STYLED) thì bỏ qua: ô tone đã đổi màu qua
        # set_accent() ở _sync_tone_widgets, còn nút Major/Minor là PainterButton
        # tự vẽ. Áp QSS này vào sẽ ghi đè cỡ chữ 18px của ô tone.
        for _w in (self.tone_combo, self.scale_combo):
            if not getattr(_w, 'SELF_STYLED', False):
                _w.setStyleSheet(detected_combo_qss)

        # Tooltip giải thích nguồn/độ tin cậy của tone đang hiển thị
        if is_low_conf:
            _tip = TONE_MSG_LOW_CONF
        elif from_cache or from_manual:
            _tip = TONE_MSG_CACHED
        else:
            _tip = TONE_MSG_FRESH
        self.tone_combo.setToolTip(_tip)
        self.scale_combo.setToolTip(_tip)
        
        bpm = result.get('bpm', 0)
        camelot = result.get('camelot', '?')
        confidence = result.get('confidence', 0)
        
        # === 2. Reset nút "Dò Lại" về trạng thái ban đầu ===
        self._set_rescan_button_state("idle")
        
        # === 3. Cập nhật dot → xanh (đã phát hiện) / cam (chưa chắc) ===
        _dot_color = C['orange'] if is_low_conf else C['green']
        self.autokey_dot.setStyleSheet(f"color: {_dot_color}; font-size: 16px;")
        
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
        
        # Nhãn (badge) phụ cho marquee: nguồn lưu sẵn / mức tin cậy
        if is_low_conf:
            badge = "  tone gợi ý — chưa chắc"
        elif from_cache or from_manual:
            badge = "  (đã lưu — sai? bấm Dò Lại)"
        else:
            badge = ""

        # === 5. Hiển thị tên bài hát + kết quả lên Marquee (giữ nguyên Window Title) ===
        # TRƯỚC ĐÂY: chặn `if 'time' not in result` khiến marquee đứng im suốt bài,
        # vì MỌI sự kiện chuyển tone lúc đang phát đều có 'time'. Nay cập nhật cả
        # hai loại: dò xong bài, và mỗi lần đổi tone.
        #
        # Marquee chỉ dựng lại khi tone ĐỔI (không phải mỗi nhịp 250ms) — đặt text
        # mới sẽ reset vòng chạy chữ, làm liên tục thì chữ đứng im tại chỗ. Số giây
        # đếm ngược nằm ở ô "kế tiếp" bên phải, nơi vẽ lại được 4 lần/giây mà không
        # ảnh hưởng gì.
        self._refresh_tone_marquee(badge)

        # Báo cho người dùng biết tone được dò từ loa (yt-dlp tải thất bại)
        if result.get('from_loopback'):
            self._show_message(TONE_MSG_LOOPBACK)
        elif is_low_conf:
            self._show_message(TONE_MSG_LOW_CONF)
        elif from_cache or from_manual:
            self._show_message(TONE_MSG_CACHED)

        # === 6. Auto-save vào Danh sách bài hát ===
        # Bảo thủ: KHÔNG tự lưu khi tone chưa chắc (uncertain/low) để tránh lưu tone
        # đoán sai. Cũng không cần lưu lại nếu tone vốn lấy từ cache/manual.
        url = result.get('url', '')
        if url and title and key_root and not is_low_conf and not from_cache and not from_manual:
            def _auto_save():
                # Lưu key_display ('Am') chứ không phải nốt gốc ('A'): mất chữ
                # 'm' là mất luôn thể thứ, mở lại bài sẽ gửi sang Studio One một
                # tone TRƯỞNG dù bài là thứ.
                backend.SongManager.add_song(title, url, key_display)
            threading.Thread(target=_auto_save, daemon=True).start()

    def _on_tone_auto(self):
        self.tune_state = not getattr(self, 'tune_state', True)
        val = 127 if self.tune_state else 0
        self.engine.send_midi(MIDI_CC.get("tone_auto", 40), val)
        btn = self._func_buttons.get("Auto-Tune")
        if btn:
            btn.setActive(self.tune_state)
        print(f"[TONE AUTO] -> {'ON' if self.tune_state else 'OFF'} (Value {val})")

    def _on_fix_meo(self):
        self.fix_meo_state = not getattr(self, 'fix_meo_state', False)
        val = 127 if self.fix_meo_state else 0
        
        # Ưu tiên dùng giá trị cân chỉnh trong mode_midi_map nếu có
        mode_map = backend.AppConfig.get_mode_midi_map()
        cc_num = int(MIDI_CC.get("fix_meo", 45))
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

    def _on_be(self):
        """Toggle hiệu ứng bè giọng (CC "be") trên Studio One.

        KHÁC mix_backing (âm lượng bè) và mute_backing (tắt tiếng bè) — nút này
        bật/tắt bản thân hiệu ứng bè.
        """
        self.be_state = not getattr(self, 'be_state', False)
        val = 127 if self.be_state else 0
        self.engine.send_midi(int(MIDI_CC.get("be", 47)), val)
        btn = self._func_buttons.get("Bè")
        if btn:
            btn.setActive(self.be_state)
        print(f"[BE] -> {'ON' if self.be_state else 'OFF'} (Value {val})")

    def _on_tat_on(self):
        """Toggle bộ khử tiếng ồn nền cho mic (CC "tat_on") — có ở MỌI phiên bản.

        KHÁC mute_mic (tắt hẳn kênh mic): nút này chỉ đóng/mở noise gate bên
        Studio One nên người hát vẫn nghe giọng mình, chỉ bớt tiếng ồn phòng.
        """
        self._set_tat_on(not getattr(self, 'tat_on_state', False))

    def _set_tat_on(self, on: bool, speak: bool = True):
        """Đặt trạng thái Khử ồn — đường DUY NHẤT gửi CC "tat_on".

        Cả nút bấm tay lẫn Tắt ồn tự động đều đi qua đây, nên cờ `tat_on_state`,
        nút trên panel Công cụ và MIDI không bao giờ lệch nhau.

        `speak=False` cho đường tự động: máy tự lật thì đã có toast báo, đọc
        thêm bằng TTS mỗi lần vào/ra bài sẽ thành ồn ào.
        """
        self.tat_on_state = bool(on)
        val = 127 if self.tat_on_state else 0
        self.engine.send_midi(int(MIDI_CC.get("tat_on", 48)), val)
        btn = self._func_buttons.get("Tắt Ồn")
        if btn:
            btn.setActive(self.tat_on_state)
        if speak:
            self._a11y_speak(f"Tắt ồn {'bật' if self.tat_on_state else 'tắt'}")
        print(f"[TAT ON] -> {'ON' if self.tat_on_state else 'OFF'} (Value {val})")

    # ── Tự động bật/tắt Vang theo nhạc (Premium) ────────────────────────────
    # Chu kỳ lấy mẫu + số mẫu liên tiếp cần có trước khi CHỐT trạng thái mới.
    # Bật nhanh (nhạc vào là có vang ngay), tắt chậm hơn để không rớt vang khi
    # nhạc khựng 1 nhịp / chuyển bài / tua.
    _AUTO_ECHO_TICK_MS = 500
    _AUTO_ECHO_ON_TICKS = 1    # ~0.5s
    _AUTO_ECHO_OFF_TICKS = 6   # ~3s

    def _music_is_playing(self) -> bool:
        """Có nhạc đang phát không — gom cả 3 nguồn app biết được.

        Ưu tiên giống _update_browser_status: CDP (chính xác nhất) → WinRT.
        Riêng màn hình karaoke nhúng phát bằng QMediaPlayer thì Windows không
        thấy, nên phải hỏi thẳng cửa sổ player.
        """
        try:
            player = self._player_window
            if player is not None and player.is_playing():
                return True
            cdp = getattr(self.engine, 'cdp_monitor', None)
            if cdp is not None and getattr(cdp, 'is_connected', False):
                return bool(cdp.is_playing)
            win_media = getattr(self.engine, 'media_monitor', None)
            if win_media is not None:
                return bool(win_media.is_playing)
        except Exception as e:
            print(f"[AUTO ECHO] đọc trạng thái nhạc lỗi: {e}")
        return False

    def _auto_echo_enabled(self) -> bool:
        """Tính năng đang bật trong Cài đặt VÀ license còn quyền Premium."""
        if not self.settings.get("auto_echo_enabled", False):
            return False
        try:
            from core import entitlements
            return entitlements.has_feature("auto_echo")
        except Exception:
            return False

    def _apply_auto_echo_setting(self):
        """Bật/tắt vòng lặp theo dõi nhạc theo thiết lập hiện tại.

        Gọi lúc khởi động và mỗi lần user lưu Cài đặt. Khi tắt tính năng thì
        KHÔNG tự đụng vào Vang — giữ nguyên trạng thái user đang nghe.
        """
        want = self._auto_echo_enabled()
        if want and self._auto_echo_timer is None:
            self._auto_echo_timer = QTimer(self)
            self._auto_echo_timer.timeout.connect(self._auto_echo_tick)
            self._auto_echo_timer.start(self._AUTO_ECHO_TICK_MS)
            # Chốt theo hiện trạng để không lật Vang ngay khi vừa bật tính năng
            self._auto_echo_playing = self._music_is_playing()
            self._auto_echo_streak = 0
            print("[AUTO ECHO] Bật theo dõi nhạc")
        elif not want and self._auto_echo_timer is not None:
            self._auto_echo_timer.stop()
            self._auto_echo_timer.deleteLater()
            self._auto_echo_timer = None
            self._auto_echo_playing = None
            self._auto_echo_streak = 0
            print("[AUTO ECHO] Tắt theo dõi nhạc")

    def _auto_echo_tick(self):
        """Một nhịp lấy mẫu: đủ số mẫu liên tiếp thì mới lật Vang."""
        # License có thể hết hạn / bị thu hồi giữa phiên → dừng luôn.
        if not self._auto_echo_enabled():
            self._apply_auto_echo_setting()
            return

        playing = self._music_is_playing()
        if playing == self._auto_echo_playing:
            self._auto_echo_streak = 0
            return

        self._auto_echo_streak += 1
        needed = self._AUTO_ECHO_ON_TICKS if playing else self._AUTO_ECHO_OFF_TICKS
        if self._auto_echo_streak < needed:
            return

        self._auto_echo_playing = playing
        self._auto_echo_streak = 0
        # Có nhạc → mở Vang; hết nhạc → tắt Vang (mute kênh Vang).
        self._set_reverb_muted(not playing)
        self._show_message("Tự động bật Vang" if playing else "Tự động tắt Vang")

    def _set_reverb_muted(self, muted: bool):
        """Đặt trạng thái mute kênh Vang, đi ĐÚNG đường như user tự bấm.

        Bấm mute_btn thay vì gửi CC thẳng để nút mute trong Mixer, mute_states
        và các CC phụ (mute_multi_cc) đều đồng bộ — chỉ một nguồn logic duy nhất.
        """
        try:
            ch = self._mixer_channels.get("mix_reverb")
            if ch is None or not getattr(ch, "mute_btn", None):
                return
            if ch.is_muted() != muted:
                ch.mute_btn.click()
        except Exception as e:
            print(f"[AUTO ECHO] đặt mute Vang lỗi: {e}")

    # ── Tự động bật/tắt Khử ồn theo nhạc (Premium) ──────────────────────────
    # Cùng khuôn và cùng chiều với Vang tự động: nhạc vào là bật khử ồn để
    # tiếng ồn phòng (quạt, điều hoà, bàn tán) không lẫn vào bài hát; hết nhạc
    # thì trả mic về tự nhiên để MC/khách nói chuyện không bị noise gate cắt lời.
    # Bật nhanh, tắt chậm — y như Vang — để không lật qua lật lại lúc tua bài.
    _AUTO_NOISE_TICK_MS = 500
    _AUTO_NOISE_ON_TICKS = 1    # ~0.5s
    _AUTO_NOISE_OFF_TICKS = 6   # ~3s

    def _auto_noise_enabled(self) -> bool:
        """Tính năng đang bật trong Cài đặt VÀ license còn quyền Premium."""
        if not self.settings.get("auto_noise_enabled", False):
            return False
        try:
            from core import entitlements
            return entitlements.has_feature("auto_noise")
        except Exception:
            return False

    def _apply_auto_noise_setting(self):
        """Bật/tắt vòng lặp theo dõi nhạc theo thiết lập hiện tại.

        Gọi lúc khởi động và mỗi lần user lưu Cài đặt. Khi tắt tính năng thì
        KHÔNG tự đụng vào Khử ồn — giữ nguyên trạng thái user đang nghe.
        """
        want = self._auto_noise_enabled()
        if want and self._auto_noise_timer is None:
            self._auto_noise_timer = QTimer(self)
            self._auto_noise_timer.timeout.connect(self._auto_noise_tick)
            self._auto_noise_timer.start(self._AUTO_NOISE_TICK_MS)
            # Chốt theo hiện trạng để không lật Khử ồn ngay khi vừa bật tính năng
            self._auto_noise_playing = self._music_is_playing()
            self._auto_noise_streak = 0
            print("[AUTO NOISE] Bật theo dõi nhạc")
        elif not want and self._auto_noise_timer is not None:
            self._auto_noise_timer.stop()
            self._auto_noise_timer.deleteLater()
            self._auto_noise_timer = None
            self._auto_noise_playing = None
            self._auto_noise_streak = 0
            print("[AUTO NOISE] Tắt theo dõi nhạc")

    def _auto_noise_tick(self):
        """Một nhịp lấy mẫu: đủ số mẫu liên tiếp thì mới lật Khử ồn."""
        # License có thể hết hạn / bị thu hồi giữa phiên → dừng luôn.
        if not self._auto_noise_enabled():
            self._apply_auto_noise_setting()
            return

        playing = self._music_is_playing()
        if playing == self._auto_noise_playing:
            self._auto_noise_streak = 0
            return

        self._auto_noise_streak += 1
        needed = self._AUTO_NOISE_ON_TICKS if playing else self._AUTO_NOISE_OFF_TICKS
        if self._auto_noise_streak < needed:
            return

        self._auto_noise_playing = playing
        self._auto_noise_streak = 0
        # Có nhạc → bật khử ồn; hết nhạc → tắt khử ồn.
        # Đi qua _set_tat_on để nút Tắt Ồn trên panel sáng/tắt theo, không phải
        # gửi CC thẳng rồi để nút hiển thị một đằng máy chạy một nẻo.
        if self.tat_on_state != playing:
            self._set_tat_on(playing, speak=False)
            self._show_message("Tự động bật khử ồn" if playing else "Tự động tắt khử ồn")

    def _on_scale_toggle(self):
        """Toggle Major ↔ Minor"""
        self.scale_is_major = not getattr(self, 'scale_is_major', True)
        if self.scale_is_major:
            self.engine.send_midi(MIDI_CC.get("scale_type", 35), SCALE_VALUES.get("major", 13))
            if hasattr(self, 'scale_combo'):
                self.scale_combo.setCurrentText("Major")
        else:
            self.engine.send_midi(MIDI_CC.get("scale_type", 35), SCALE_VALUES.get("minor", 18))
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
        # User chỉnh thể tay → khoá replay timeline (không để mốc kế tiếp đè MIDI)
        self._lock_replay_for_manual_override()

    def _on_score(self):
        # Premium-only: chặn trước khi bắt đầu (cho phép tắt nếu đang chạy).
        if not self.engine.quick_score_active and not self._require_premium("scoring", "Chấm Điểm"):
            return

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
                    # Phase 3 — lưu lịch sử chấm điểm (Premium "progress").
                    # Score đã gate premium ở đầu _on_score nên chỉ chạy cho Premium.
                    # Fail-soft: ScoreHistory.add nuốt mọi lỗi, không làm vỡ luồng.
                    try:
                        from core.score_history import ScoreHistory
                        ScoreHistory.add(
                            result,
                            song_title=getattr(self, "current_title", "") or "",
                            url=getattr(self.engine, "current_youtube_url", "") or "",
                        )
                    except Exception as e:
                        print(f"[PROGRESS] save history error: {e}")
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

    # ── Phase 3: Bảng tiến bộ luyện hát (Premium) ──
    def _show_progress_dialog(self):
        if not self._require_premium("progress", "Bảng tiến bộ luyện hát"):
            return
        from ui.dialogs.progress_dialog import ProgressDialog
        ProgressDialog(self).exec()

    # ── Phase 2: Smart Recall (Premium) ──
    def _apply_song_preset(self, song):
        """Khôi phục tone/scale/mixer/mode đã lưu của bài (Smart Recall).

        Dùng has_feature im lặng (KHÔNG upsell) ở luồng mở bài: Standard mở bài
        bình thường, chỉ bỏ qua việc auto-apply. Fail-soft toàn bộ."""
        if not song:
            return
        try:
            from core import entitlements
            if not entitlements.has_feature("smart_recall"):
                return
            preset = backend.SongManager.get_preset(song.get("id"))
        except Exception:
            return
        if not preset:
            return  # Bài chưa có preset → tương thích ngược

        from PySide6.QtCore import QSignalBlocker
        try:
            tone = preset.get("tone")
            if tone:
                with QSignalBlocker(self.tone_combo):
                    self.tone_combo.setCurrentText(tone)
                self._on_tone_selected(tone)

            scale = preset.get("scale")
            if scale and hasattr(self, "scale_combo"):
                with QSignalBlocker(self.scale_combo):
                    self.scale_combo.setCurrentText(scale)
                self._on_scale_selected(scale)

            mixer = preset.get("mixer") or {}
            key_map = {"music": "mix_music", "mic": "mix_mic",
                       "reverb": "mix_reverb", "backing": "mix_backing"}
            sliders = getattr(self, "_mixer_sliders", {})
            for pkey, cc_key in key_map.items():
                if pkey not in mixer:
                    continue
                slider = sliders.get(cc_key)
                if slider is not None:
                    slider.setValue(int(mixer[pkey]))

            mode = preset.get("mode")
            if mode:
                self._on_mode_selected(mode, toggle=False)

            self._show_message(f"Đã khôi phục thiết lập: {song.get('title','')}")
        except Exception as e:
            print(f"[SMART_RECALL] apply preset error: {e}")

    def _capture_current_preset(self) -> dict:
        """Chụp trạng thái UI hiện tại thành preset dict (tone/scale/mixer/mode)."""
        preset = {
            "tone":  self.tone_combo.currentText() if hasattr(self, "tone_combo") else None,
            "scale": self.scale_combo.currentText() if hasattr(self, "scale_combo") else None,
            "mode":  getattr(self, "current_mode", None),
            "mixer": {},
        }
        key_map = {"mix_music": "music", "mix_mic": "mic",
                   "mix_reverb": "reverb", "mix_backing": "backing"}
        sliders = getattr(self, "_mixer_sliders", {})
        for cc_key, pkey in key_map.items():
            slider = sliders.get(cc_key)
            if slider is not None:
                preset["mixer"][pkey] = slider.value()
        return preset

    # ── Phase 5: Live Setlist / Auto-Pilot (Premium) ──
    def _show_setlist(self):
        if not self._require_premium("setlist", "Live Setlist / Auto-Pilot"):
            return
        from ui.dialogs.setlist_dialog import SetlistDialog
        SetlistDialog(
            self,
            on_play=self._setlist_play_song,
            make_controller=self.engine.make_setlist,
        ).exec()

    def _setlist_play_song(self, song):
        """Mở URL bài + áp preset khi Auto-Pilot chuyển bài."""
        if not song:
            return
        url   = song.get("url")
        tone  = song.get("tone", "C")
        if not url:
            return
        try:
            manual_tl = self._saved_manual_timeline(url)
            # Timeline đã lưu chính là thứ engine sắp replay — nạp luôn cho phần
            # hiển thị để ô "kế tiếp" đếm ngược được ngay từ giây đầu.
            self._set_tone_timeline(manual_tl or [], song.get("duration", 0) or 0)
            play_cb   = self._load_embedded_video if self._embedded_player_active() else None
            if play_cb is not None:
                self._embedded_current_url = url
            self.engine.open_youtube_url(
                url,
                on_video_end_callback=lambda res: None,
                on_tone_detected=lambda result: self._tone_result_signal.emit(result),
                manual_timeline=manual_tl,
                play_callback=play_cb,
            )
            from core.tone_cache import make_timeline_entry
            from PySide6.QtCore import QSignalBlocker
            with QSignalBlocker(self.tone_combo):
                # Ô tone chỉ có 12 nốt gốc — "Am" phải tách thành "A" mới hiện được.
                self.tone_combo.setCurrentText(
                    make_timeline_entry(tone)["key_display"].rstrip("m"))
            self._apply_song_preset(song)
        except Exception as e:
            print(f"[SETLIST] play song error: {e}")

    # ── Entitlement gate (Premium) ──
    def _require_premium(self, feature: str, label: str) -> bool:
        """Trả True nếu được phép dùng `feature`. Nếu không → mở dialog upsell
        và (tuỳ chọn) mở lại ActivationDialog để nhập mã Premium. Trả False."""
        from core import entitlements
        if entitlements.has_feature(feature):
            return True
        try:
            from ui.dialogs.premium_dialog import PremiumUpsellDialog
            dlg = PremiumUpsellDialog(feature, label, self)
            if dlg.exec() == QDialog.Accepted:
                self._open_activation_upgrade()
                # Sau khi nhập mã thành công, kiểm tra lại quyền ngay.
                allowed = entitlements.has_feature(feature)
                if allowed:
                    # Header, nền Premium và visualizer dựng một lần lúc khởi
                    # động → phải mở lại app mới thấy giao diện Premium.
                    self._show_message("Đã bật Premium — khởi động lại app")
                return allowed
        except Exception as e:
            print(f"[PREMIUM] upsell dialog error: {e}")
        return False

    def _open_activation_upgrade(self):
        """Mở ActivationDialog để người dùng nhập mã Premium giữa phiên.

        KHÔNG dùng mainloop(): hàm đó gọi app.exec(), mà vòng lặp sự kiện của
        dashboard đang chạy sẵn — Qt từ chối exec lồng nhau và trả về NGAY, nên
        dialog bị thu hồi trước khi kịp vẽ (người dùng bấm "Nâng cấp" xong không
        thấy gì hiện lên). Giữa phiên phải dùng exec() của chính dialog: đó là
        vòng lặp modal lồng hợp lệ của Qt.
        """
        try:
            dlg = ActivationDialog(parent=self)
            dlg.setWindowModality(Qt.ApplicationModal)
            dlg.exec()
        except Exception as e:
            print(f"[PREMIUM] activation dialog error: {e}")

    def _show_message(self, text, is_error=False, action_text=None, action_cb=None):
        """Hiện thông báo tạm ở giữa cửa sổ đang đứng trước mặt người dùng.

        Thông báo lỗi: ở lâu hơn (8s), không cắt cụt câu dài (word-wrap, rộng
        tối đa theo cửa sổ) và có nút ✕ để user tự đóng ngay khi đã đọc xong.
        Thông báo info: xuống dòng khi câu dài, sống 2s và cộng thêm theo độ
        dài câu (tối đa 5s) để người đọc kịp.

        action_text/action_cb: nếu có, hiện thêm một nút hành động (vd "Mở Cài
        đặt âm thanh") dưới nội dung lỗi — chỉ áp dụng cho panel lỗi."""
        color = C["accent"] if is_error else C["green"]
        font_size = 14 if is_error else 11

        # Toast là widget CON của cửa sổ nhận nó. Các hộp thoại (Danh sách bài,
        # Sửa bài, Thiết lập…) mở bằng exec() nên là cửa sổ modal ĐÈ LÊN
        # dashboard — vẽ toast lên dashboard thì nó nằm khuất phía sau, người
        # dùng bấm Lưu mà tưởng không có gì xảy ra. Có modal thì vẽ lên modal.
        host = QApplication.activeModalWidget() or self

        if not is_error:
            lbl = QLabel(text, host)
            lbl.setWordWrap(True)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                f"background-color: {C['card']}; color: {color}; border: 1px solid {color};"
                f" border-radius: 8px; padding: 6px 12px; font-size: {font_size}px;"
                f" font-weight: bold; font-family: {FONT};"
            )
            lbl.setMaximumWidth(max(280, int(host.width() * 0.8)))
            lbl.adjustSize()
            lbl.move(host.width() // 2 - lbl.width() // 2, host.height() // 2 - lbl.height() // 2)
            lbl.show()
            lbl.raise_()
            # Timer làm CON của nhãn: hộp thoại đóng trước hạn thì timer chết
            # theo, không còn callback gọi vào widget đã bị xoá.
            timer = QTimer(lbl)
            timer.setSingleShot(True)
            timer.timeout.connect(lbl.deleteLater)
            timer.start(min(5000, 2000 + 40 * len(text)))
            return

        # ── Thông báo LỖI: panel có nút đóng, ở lâu, không cắt cụt ──
        panel = QFrame(host)
        panel.setStyleSheet(
            f"background-color: {C['card']}; color: {color}; border: 1px solid {color};"
            f" border-radius: 8px;"
        )
        panel.setAccessibleName("Thông báo lỗi")
        panel.setAccessibleDescription(text)
        outer_v = QVBoxLayout(panel)
        outer_v.setContentsMargins(0, 0, 0, 0)
        outer_v.setSpacing(6)
        top_row = QWidget(panel)
        lay = QHBoxLayout(top_row)
        lay.setContentsMargins(16, 12, 10, 12)
        lay.setSpacing(8)
        outer_v.addWidget(top_row)

        lbl = QLabel(text, panel)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f"color: {color}; background: transparent; border: none;"
            f" font-size: {font_size}px; font-weight: bold; font-family: {FONT};"
        )
        lay.addWidget(lbl, 1)

        close_btn = QPushButton("✕", panel)
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setToolTip("Đóng thông báo")
        close_btn.setAccessibleName("Đóng thông báo")
        close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {color}; border: none;"
            f" font-size: 15px; font-weight: 900; font-family: {FONT}; }}"
            f"QPushButton:hover {{ color: {_lighten(color, 0.3)}; }}"
        )
        lay.addWidget(close_btn, 0, Qt.AlignTop)

        def _close():
            try:
                panel.deleteLater()
            except RuntimeError:
                pass

        # Nút hành động phụ (vd "Mở Cài đặt âm thanh") — đặt dưới nội dung lỗi.
        if action_text and action_cb is not None:
            act_row = QWidget(panel)
            act_lay = QHBoxLayout(act_row)
            act_lay.setContentsMargins(16, 0, 10, 12)
            act_lay.addStretch()
            act_btn = QPushButton(action_text, act_row)
            act_btn.setCursor(Qt.PointingHandCursor)
            act_btn.setAccessibleName(action_text)
            act_btn.setAccessibleDescription(
                "Chọn thiết bị đang nghe làm mặc định của Windows")
            act_btn.setStyleSheet(
                f"QPushButton {{ background: {color}; color: {C['bg']}; border: none;"
                f" border-radius: 8px; padding: 6px 14px; font-size: 13px;"
                f" font-weight: 700; font-family: {FONT}; }}"
                f"QPushButton:hover {{ background: {_lighten(color, 0.15)}; }}"
            )
            def _do_action():
                try:
                    action_cb()
                finally:
                    _close()
            act_btn.clicked.connect(_do_action)
            act_lay.addWidget(act_btn)
            outer_v.addWidget(act_row)

        # Rộng tối đa ~80% cửa sổ để câu dài xuống dòng thay vì bị cắt
        max_w = max(320, int(host.width() * 0.8))
        panel.setMaximumWidth(max_w)
        panel.adjustSize()
        panel.move(host.width() // 2 - panel.width() // 2,
                   host.height() // 2 - panel.height() // 2)
        panel.show()
        panel.raise_()

        close_btn.clicked.connect(_close)
        # Có nút hành động → để lâu hơn (12s) cho user kịp đọc & bấm
        QTimer.singleShot(12000 if action_text else 8000, _close)

    _SAVE_KEYS = [
        "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B",
        "Cm", "C#m", "Dm", "D#m", "Em", "Fm", "F#m", "Gm", "G#m", "Am", "A#m", "Bm",
    ]

    def _on_save(self):
        """Lưu bài hát — popup nhập đầy đủ Tên + Tone + URL (điền sẵn nếu đang phát)."""
        auto_url   = getattr(self.engine, 'current_youtube_url', '') or ''
        auto_tone  = getattr(self, 'current_tone', 'C') or 'C'
        auto_title = getattr(self, 'current_title', '') or ''

        from PySide6.QtWidgets import QDialog, QLineEdit, QVBoxLayout, QHBoxLayout, QFrame as _QF
        dlg = QDialog(self)
        dlg.setWindowTitle("💾 Lưu bài hát")
        rp.apply_dialog_size(dlg, 520, 330, fixed=True, max_scale=1.25)
        dlg.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")

        outer = QVBoxLayout(dlg)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # Header
        hdr = _QF()
        hdr.setStyleSheet(f"background-color: {C['card']}; border-bottom: 1px solid {C['border']};")
        hdr_lay = QVBoxLayout(hdr)
        hdr_lay.setContentsMargins(20, 14, 20, 12)
        title = QLabel("💾 Lưu bài hát")
        title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {C['teal']}; font-family: {FONT}; background: transparent; border: none;")
        title.setAlignment(Qt.AlignCenter)
        hdr_lay.addWidget(title)
        outer.addWidget(hdr)

        body = QVBoxLayout()
        body.setContentsMargins(20, 14, 20, 14)
        body.setSpacing(8)

        _field_qss = f"""
            QLineEdit {{
                background-color: {C['card']}; color: {C['text']};
                border: 1px solid {C['border']}; border-radius: 10px;
                padding: 9px 14px; font-size: 13px; font-family: {FONT};
            }}
            QLineEdit:focus {{ border-color: {C['teal']}; border-width: 2px; }}
        """

        def _lbl(text):
            l = QLabel(text)
            l.setStyleSheet(f"font-size: 12px; color: {C['text_muted']}; font-family: {FONT}; background: transparent; border: none;")
            return l

        body.addWidget(_lbl("Tên bài hát"))
        title_input = QLineEdit(auto_title)
        title_input.setPlaceholderText("Tự động lấy từ YouTube nếu để trống")
        title_input.setStyleSheet(_field_qss)
        body.addWidget(title_input)

        body.addWidget(_lbl("Tone"))
        tone_combo = QComboBox()
        tone_combo.addItems(self._SAVE_KEYS)
        if auto_tone in self._SAVE_KEYS:
            tone_combo.setCurrentText(auto_tone)
        tone_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {C['card']}; color: {C['green']};
                border: 1px solid {C['border']}; border-radius: 10px;
                padding: 8px 14px; font-size: 13px; font-weight: 700; font-family: {FONT};
            }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background-color: {C['card']}; color: {C['text']};
                selection-background-color: {C['green']};
            }}
        """)
        body.addWidget(tone_combo)

        body.addWidget(_lbl("URL YouTube"))
        url_input = QLineEdit(auto_url)
        url_input.setPlaceholderText("https://www.youtube.com/watch?v=...")
        url_input.setStyleSheet(_field_qss)
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

        def save_from_form():
            url = url_input.text().strip()
            if not url or ("youtube.com" not in url and "youtu.be" not in url):
                self._show_message("Cần link YouTube hợp lệ", is_error=True)
                return
            dlg.accept()
            # Tone khách TỰ CHỌN (đổi khác tone điền sẵn, hoặc vừa chỉnh tay ở
            # màn hình chính) là ý muốn rõ ràng → lưu thành chuỗi tone thủ công
            # để lần sau mở bài là chạy đúng tone đó, không dò lại.
            chosen_tone = tone_combo.currentText()
            tone_is_human = (chosen_tone != auto_tone
                             or bool(getattr(self, "_manual_tone_override", False)))
            self._process_quick_save(url, chosen_tone, title_input.text().strip(),
                                     tone_is_human=tone_is_human)

        save_btn.clicked.connect(save_from_form)
        cancel_btn.clicked.connect(dlg.reject)

        btn_box.addWidget(save_btn, 1)
        btn_box.addWidget(cancel_btn)
        body.addLayout(btn_box)

        body_widget = _QF()
        body_widget.setStyleSheet(f"background: {C['bg']}; border: none;")
        body_widget.setLayout(body)
        outer.addWidget(body_widget)
        dlg.exec()


    def _process_quick_save(self, url, tone, title=None, tone_is_human=False):
        """Lưu bài. Nếu title rỗng → tự lấy từ timeline manual / yt-dlp (chạy nền).

        tone_is_human=True (khách tự chọn tone ở ô Tone) → ghi thêm chuỗi tone
        thủ công 1 mốc để chuỗi resolve dùng được. KHÔNG bao giờ đè lên chuỗi
        nhiều mốc đã có: chuỗi đó chi tiết hơn và cũng do khách tạo.
        """
        def _task():
            save_title = (title or '').strip()
            save_tone = tone
            if not save_title:
                # Thử lấy tên + tone từ timeline manual
                timeline_data = backend.ManualToneTimeline.load_timeline(url)
                if timeline_data:
                    save_title = timeline_data.get('title', '') or save_title
                    tl = timeline_data.get('timeline', [])
                    if tl and not tone:
                        save_tone = tl[0].get('key_display', save_tone)
                if not save_title:
                    try:
                        info = extract_info_with_auth(
                            url,
                            make_ydl_opts(skip_download=True),
                            download=False,
                            log_prefix="[QUICK SAVE]"
                        )
                        save_title = info.get('title', '') or save_title
                    except Exception:
                        pass
            if not save_title:
                save_title = 'Bài hát không tên'

            if backend.SongManager.add_song(save_title, url, save_tone):
                if tone_is_human and save_tone:
                    self._save_single_tone_timeline(url, save_title, save_tone)
                self._message_signal.emit(f"✅ Đã lưu: {save_title[:40]}", False)
            else:
                self._message_signal.emit("Lỗi khi lưu bài hát", True)

        threading.Thread(target=_task, daemon=True).start()

    def _on_eye_toggle_studio_one(self):
        """Nút mắt: Ẩn/Hiện Studio One + cập nhật icon mắt nhắm/mở."""
        from ui.components.svg_icons import SVG_EYE_OPEN, SVG_EYE_CLOSED
        # Gọi logic ẩn/hiện PID-based
        self._on_toggle_studio_one()
        # Đọc lại trạng thái thật thay vì đảo cờ: lệnh trên có thể đã bỏ qua
        # (đang khoá, Studio One chưa chạy) — đảo mù sẽ làm icon lệch thực tế.
        from core import so_windows
        self._studio_one_visible = so_windows.any_visible()
        if self._eye_btn is not None:
            new_svg = SVG_EYE_OPEN if self._studio_one_visible else SVG_EYE_CLOSED
            self._eye_btn.setSvg(new_svg)

    def _on_toggle_studio_one(self):
        """Ẩn/Hiện Studio One + tất cả plugin windows (theo PID, không theo title)."""
        from core import kiosk, so_windows

        # Chốt chặn cuối: nút mắt đã bị ẩn khi khoá, nhưng lệnh này còn tới được
        # từ MIDI/giọng nói/nút custom nên phải chặn ngay tại đây.
        if kiosk.is_locked():
            self._show_message("Studio One đang khoá — cần mở khoá kỹ thuật", is_error=True)
            return

        if so_windows.win32_modules() is None:
            self._show_message("Thiếu thành phần hệ thống — báo kỹ thuật", is_error=True)
            return

        if not so_windows.studio_one_pids():
            self._show_message("Không tìm thấy Studio One đang chạy", is_error=True)
            return

        if not so_windows.all_windows():
            self._show_message("Studio One đang chạy nhưng không có cửa sổ nào", is_error=True)
            return

        if so_windows.any_visible():
            so_windows.hide_all()
            self._show_message("Đã ẩn Studio One")
        else:
            so_windows.show_all()
            self._show_message("Đã hiện Studio One")

    def _on_toggle_asiolink(self):
        """Ẩn/Hiện cửa sổ ASIOLINK (ASIO4ALL, ASIOVADPRO, ASIOLink Pro, v.v.)"""
        try:
            import win32gui
            import win32con
            import win32process
        except ImportError:
            self._show_message("Thiếu thành phần hệ thống — báo kỹ thuật", is_error=True)
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
            self._show_message(f"Lỗi tìm bảng điều khiển âm thanh: {e}", is_error=True)
            return

        if not found_hwnds:
            self._show_message("Không tìm thấy bảng điều khiển âm thanh", is_error=True)
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
            self._show_message("Đã ẩn bảng điều khiển âm thanh")
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
            self._show_message("Đã hiện bảng điều khiển âm thanh")

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
            self.engine.send_midi(MIDI_CC.get("score_trigger", 32), 0)
            
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
                        self._show_message(f"Đã lưu bản thu: {os.path.basename(save_path)}")
                        # Bản thu bị rè thì nói thẳng nguyên nhân, đừng để khách
                        # tự đoán. Chờ 3s cho thông báo lưu hiện xong đã.
                        try:
                            warn = self.engine.recorder.quality_warning()
                        except Exception:
                            warn = None
                        if warn:
                            QTimer.singleShot(
                                3000, lambda: self._show_message(f"{warn}", is_error=True)
                            )
                    else:
                        err = getattr(self.engine.recorder, 'last_error', None) or "File ghi âm rỗng hoặc không hợp lệ"
                        self._show_message(f"Lưu thất bại: {err[:80]}", is_error=True)
                else:
                    self.engine.recorder.stop_recording(save_path=None)
                    self._show_message("Đã huỷ lưu bản thu")
            
            QTimer.singleShot(100, handle_save)
        else:
            self.is_recording = True
            self.record_button.set_recording(True)
            self.engine.send_midi(MIDI_CC.get("score_trigger", 32), 127)
            
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
                self.engine.send_midi(MIDI_CC.get("score_trigger", 32), 0)
                err = getattr(self.engine.recorder, 'last_error', None) or "Không tìm thấy thiết bị WASAPI Loopback"
                self._show_message(f"Không thể ghi âm: {err[:80]}", is_error=True)

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

            # Dọn dẹp khi phát xong HOẶC khi media lỗi — nếu chỉ dọn ở
            # EndOfMedia thì file hỏng/decode lỗi sẽ leak player tích lũy dần.
            _disposed = {"done": False}

            def _dispose():
                if _disposed["done"]:
                    return
                _disposed["done"] = True
                player.deleteLater()
                audio_out.deleteLater()

            def _cleanup(status):
                if status in (QMediaPlayer.EndOfMedia, QMediaPlayer.InvalidMedia):
                    _dispose()

            def _on_media_error(error, error_string=""):
                print(f"[SFX] Loi media: {error_string or error}")
                _dispose()

            player.mediaStatusChanged.connect(_cleanup)
            player.errorOccurred.connect(_on_media_error)

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
                engine=cfg.get("tts_engine", "piper") or "piper",
            )
            # Áp engine kể cả khi singleton đã tồn tại (đổi trong Cài đặt).
            self._a11y_speaker.set_engine(
                cfg.get("tts_engine", "piper") or "piper",
                cfg.get("tts_piper_voice", "") or "",
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
        self._a11y_voice_listening = False
        self._a11y_voice_indicator = None
        if cfg.get("voice_command_enabled", False):
            self._a11y_init_voice()

        # Event filter toàn app cho push-to-talk — child widget có StrongFocus
        # sẽ nuốt phím Space nếu chỉ dùng keyPressEvent của QMainWindow.
        try:
            app = QApplication.instance()
            if app is not None:
                app.installEventFilter(self)
        except Exception as e:
            print(f"[A11Y] Event filter lỗi: {e}")

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
        for attr in ("tone_combo", "scale_combo", "_support_btn", "_settings_btn", "_eye_btn"):
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
            # Intent route qua signal (QueuedConnection) — handler có thể mở
            # dialog, không được chạy trực tiếp trong callback/key handler.
            try:
                _vcfg = backend.AppConfig.get_accessibility() or {}
            except Exception:
                _vcfg = {}
            self._a11y_voice = VoiceInput(
                on_intent=lambda it: self._voice_intent_signal.emit(it),
                on_error=lambda msg: self._a11y_speak(msg, priority="high"),
                variant=_vcfg.get("voice_model", "small") or "small",
            )
            if not self._a11y_voice.available:
                self._a11y_speak("Chưa có model giọng nói. Hãy tải Vosk vi vào thư mục models.")
                self._a11y_voice = None
            else:
                # Tải model Vosk trong thread nền NGAY từ đầu — load sync trong
                # key handler lần nhấn PTT đầu tiên sẽ freeze UI nhiều giây.
                self._a11y_voice.preload_async()
        except Exception as e:
            print(f"[A11Y] VoiceInput init lỗi: {e}")
            self._a11y_voice = None
        self._a11y_voice_listening = False
        self._a11y_voice_indicator = None

    # ── Voice push-to-talk (Ctrl+Space hold) ──────────────────

    def eventFilter(self, obj, event):
        """App-level filter cho push-to-talk — bắt Ctrl+Space bất kể widget nào
        đang focus (child StrongFocus nuốt Space nếu dùng keyPressEvent thường).
        """
        from PySide6.QtCore import QEvent
        t = event.type()
        if t == QEvent.KeyPress:
            if (event.key() == Qt.Key_Space
                    and event.modifiers() & Qt.ControlModifier
                    and not event.isAutoRepeat()
                    and getattr(self, "_a11y_voice", None) is not None):
                self._a11y_voice_start()
                return True
        elif t == QEvent.KeyRelease:
            # Thả Space HOẶC Ctrl đều dừng nghe — tránh kẹt mic khi user
            # thả Ctrl trước Space.
            if (event.key() in (Qt.Key_Space, Qt.Key_Control)
                    and not event.isAutoRepeat()
                    and getattr(self, "_a11y_voice_listening", False)):
                self._a11y_voice_stop()
                if event.key() == Qt.Key_Space:
                    return True
        elif t in (QEvent.WindowDeactivate, QEvent.ApplicationDeactivate):
            # Safety net: mất focus cửa sổ → không bao giờ để mic kẹt "ĐANG NGHE"
            if getattr(self, "_a11y_voice_listening", False):
                self._a11y_voice_stop()
        return super().eventFilter(obj, event)

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
            self._show_message("Không nghe được lệnh", is_error=True)
            return

        actions = {
            "autokey":          self._on_force_rescan,
            "record_toggle":    self._on_record,
            "save":             self._on_save,
            "open_songs":       self._show_songs_list,
            "open_setlist":     self._show_setlist,
            "score":            self._on_score,
            "speak_status":     self._a11y_speak_status,
            # interrupt() chỉ ngắt câu đang đọc + xoá queue — KHÔNG kill worker
            # thread (stop() sẽ làm các announce sau bị kẹt vĩnh viễn).
            "stop_tts":         lambda: self._a11y_speaker and self._a11y_speaker.interrupt(),
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
            self._show_message(f"Nghe được: \"{text}\" — không hiểu", is_error=True)
            return
        try:
            print(f"[VOICE INTENT]   -> Thực hiện: {name}")
            action()
            if name != "stop_tts":
                # "im lặng" mà còn đọc "Đã thực hiện" thì phản tác dụng
                self._a11y_speak("Đã thực hiện", priority="high")
            self._show_message(f"Đã thực hiện: \"{text}\"")
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
        global _APP_LOOP_RUNNING
        self.show()
        app = QApplication.instance()
        if app:
            _APP_LOOP_RUNNING = True
            try:
                app.exec()
            finally:
                _APP_LOOP_RUNNING = False

    def _needs_studio_one_shutdown(self) -> bool:
        if not self.settings.get("auto_close_studio_one", False):
            return False
        try:
            from core import so_windows
            return so_windows.is_running()
        except Exception:
            return False

    def _run_studio_one_shutdown(self):
        """Chờ Studio One lưu bài và thoát, có hộp thoại tiến trình trước mặt."""
        from ui.dialogs.shutdown_dialog import StudioOneShutdownDialog
        try:
            dlg = StudioOneShutdownDialog(
                self.engine,
                timeout_sec=float(self.settings.get("studio_one_close_timeout", 45)),
                force_kill=bool(self.settings.get("force_kill_studio_one", False)),
                parent=self,
            )
            dlg.exec()
            status = (dlg.result_data or {}).get("status")
            if status not in ("closed", "not_running"):
                print(f"[STUDIO ONE] Thoát app khi chưa đóng xong ({status})")
                # Bước lưu đã phải hiện cửa sổ Studio One lên để gõ Ctrl+S. Nếu
                # nó không đóng được thì phải giấu lại, kẻo app thoát xong khách
                # ngồi trước một cửa sổ Studio One đang mở.
                from core import kiosk, so_windows
                if kiosk.is_locked():
                    so_windows.hide_all()
        except Exception as e:
            print(f"[STUDIO ONE] Đóng an toàn lỗi: {e}")
        # Đóng lại sau khi closeEvent hiện tại đã trả về — gọi self.close() ngay
        # trong handler là đệ quy closeEvent.
        QTimer.singleShot(0, self.close)

    def closeEvent(self, event):
        """Đóng cửa sổ không block — set flags ngay, cleanup nặng chạy nền."""
        # ── BƯỚC 0: đóng Studio One an toàn ───────────────────────────────────
        # Phải xong TRƯỚC khi app tắt: chuỗi lưu-rồi-đóng mất vài chục giây, mà
        # main.py chỉ chờ thread nền 4 giây rồi os._exit(0) — chạy nền là chắc
        # chắn bị cắt ngang, đúng cái đã khiến Studio One đòi phục hồi phiên.
        if not self._so_shutdown_done and self._needs_studio_one_shutdown():
            self._so_shutdown_done = True
            event.ignore()
            self._run_studio_one_shutdown()
            return

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

        # Đóng cửa sổ màn hình karaoke nhúng (nếu có)
        if self._player_window is not None:
            try:
                self._player_window.close()
            except Exception:
                pass
            self._player_window = None

        # ── BƯỚC 2: Qt timers — phải dừng trên main thread ────────────────────
        self._status_timer.stop()
        if self._auto_echo_timer is not None:
            self._auto_echo_timer.stop()
            self._auto_echo_timer = None
        if self._auto_noise_timer is not None:
            self._auto_noise_timer.stop()
            self._auto_noise_timer = None
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
        if getattr(self, "_premium_viz", None) is not None:
            try:
                self._premium_viz.stop()
            except Exception:
                pass
        if getattr(self, "_premium_tag", None) is not None:
            try:
                self._premium_tag.stop()
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

        # ── BƯỚC 5: Accept ngay — window đóng, UI không bị block ──────────────
        event.accept()
        super().closeEvent(event)

        # ── BƯỚC 6: Cleanup nặng trong daemon thread ──────────────────────────
        # Bao gồm cả đóng browser. main.py join thread này (timeout ngắn) trước
        # khi os._exit(0) để ffmpeg/yt-dlp con không bị orphan giữa chừng.
        # (Studio One không nằm ở đây — xem BƯỚC 0.)
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
            # Đóng ứng dụng liên kết — chuyển từ closeEvent xuống đây để UI
            # thread không bị treo 5s+ khi thoát.
            if settings_snap.get("auto_close_browser", False):
                try:
                    engine.close_youtube_windows()
                except Exception:
                    pass
            # Studio One đã được đóng ở BƯỚC 0 (có hộp thoại tiến trình) — không
            # đụng vào nữa, tránh giết nhầm process đang lưu dở.
            import gc
            gc.collect()

        self._bg_shutdown_thread = threading.Thread(
            target=_bg_shutdown, daemon=True, name="bg-shutdown")
        self._bg_shutdown_thread.start()


# ══════════════════════════════════════════════════════
#  ACTIVATION DIALOG (simplified for now)
# ══════════════════════════════════════════════════════
class ActivationDialog(QDialog):
    def __init__(self, callback=None, is_expired=False, needs_renewal=False,
                 parent=None):
        # We need QApplication to exist before creating any QWidget
        self._ensure_app()
        # parent chỉ dùng khi mở giữa phiên (nâng cấp Premium) — để dialog nằm
        # trên dashboard và canh giữa theo nó. Lúc khởi động vẫn là None.
        super().__init__(parent)
        self.callback = callback
        self.is_expired = is_expired
        self.needs_renewal = needs_renewal
        self.activated = False
        self.setWindowTitle("Kích hoạt Quang Lưu Studio")
        self.setWindowIcon(QIcon("app_icon.ico"))
        # Khối gia hạn thêm một đoạn chữ + nút Thử lại nên cần cao hơn.
        rp.apply_dialog_size(self, 520, 640 if needs_renewal else 510,
                             fixed=True, max_scale=1.25)
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

        if needs_renewal:
            # Giấy phép còn hạn, chỉ là lâu chưa gọi được máy chủ. Nói đúng như
            # vậy — đừng bắt khách đi mua mã mới khi họ chỉ mất mạng.
            msg = QLabel("Cần kết nối internet để gia hạn giấy phép")
            msg.setStyleSheet(f"color: {C['orange']}; font-size: 14px; font-family: {FONT}; background: transparent; border: none;")
        elif is_expired:
            msg = QLabel("Bản quyền đã hết hạn! Vui lòng nhập mã kích hoạt mới.")
            msg.setStyleSheet(f"color: {C['accent']}; font-size: 14px; font-family: {FONT}; background: transparent; border: none;")
        else:
            msg = QLabel("Vui lòng nhập Activation Code để tiếp tục.")
            msg.setStyleSheet(f"color: {C['text_muted']}; font-size: 14px; font-family: {FONT}; background: transparent; border: none;")
        msg.setAlignment(Qt.AlignCenter)
        msg.setWordWrap(True)
        hdr_lay.addWidget(msg)
        outer.addWidget(header)

        # ── Body ──
        body_frame = _QF2()
        body_frame.setStyleSheet(f"background-color: {C['bg']}; border: none;")
        layout = QVBoxLayout(body_frame)
        layout.setSpacing(14)
        layout.setContentsMargins(30, 24, 30, 24)

        # ── Khối gia hạn (chỉ khi giấy phép còn hạn mà app chưa check-in được) ──
        if needs_renewal:
            days_off = backend.ActivationManager.days_since_verify()
            days_left = backend.ActivationManager.get_days_remaining()
            detail = QLabel(
                f"Giấy phép của bạn vẫn còn {int(days_left)} ngày, nhưng app đã "
                f"{int(days_off)} ngày chưa kết nối được máy chủ.\n"
                "Bật mạng rồi bấm Thử lại — không cần nhập lại mã."
            )
            detail.setWordWrap(True)
            detail.setAlignment(Qt.AlignCenter)
            detail.setStyleSheet(
                f"color: {C['text_muted']}; font-size: 13px; font-family: {FONT}; "
                f"background: transparent; border: none;")
            layout.addWidget(detail)

            self.retry_btn = QPushButton("🔄 Thử lại")
            self.retry_btn.setFixedHeight(48)
            self.retry_btn.setCursor(Qt.PointingHandCursor)
            self.retry_btn.setStyleSheet(pill_btn_qss(C["green"], _lighten(C["green"], 0.12), 17, 22))
            self.retry_btn.clicked.connect(self._retry_renew)
            add_shadow(self.retry_btn, C["green"], 10, (0, 3))
            layout.addWidget(self.retry_btn)

            sep_or = QLabel("hoặc nhập mã kích hoạt khác")
            sep_or.setAlignment(Qt.AlignCenter)
            sep_or.setStyleSheet(
                f"color: {C['text_muted']}; font-size: 12px; background: transparent; border: none;")
            layout.addWidget(sep_or)

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("Nhập activation code...")
        # Điền sẵn mã cũ nếu còn: khách bị đá ra thường không nhớ mã để đâu.
        try:
            self.code_input.setText(backend.ActivationManager.cached_code())
        except Exception:
            pass
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
            self.status_label.setText(f"{result.get('error', 'Mã không hợp lệ')}")
            self.status_label.setStyleSheet(f"color: {C['accent']}; font-size:13px;")
    
    def _retry_renew(self):
        """Nút 'Thử lại': xin gia hạn bằng giấy phép đang có, không cần nhập mã."""
        self.retry_btn.setEnabled(False)
        self.status_label.setText("Đang kết nối máy chủ...")
        self.status_label.setStyleSheet(f"color: {C['text_muted']}; font-size:13px;")
        # Cho Qt vẽ xong dòng trạng thái rồi mới gọi mạng (gọi thẳng sẽ đơ 10 giây
        # mà người dùng không thấy gì).
        QTimer.singleShot(50, self._do_renew)

    def _do_renew(self):
        result = backend.ActivationManager.try_renew_online()
        if result.get("success"):
            self.activated = True
            self.status_label.setText("✅ Đã gia hạn! Đang mở app...")
            self.status_label.setStyleSheet(f"color: {C['green']}; font-size:13px;")
            QTimer.singleShot(900, self._close_and_continue)
            return
        self.retry_btn.setEnabled(True)
        self.status_label.setText(f"❌ {result.get('error', 'Chưa gia hạn được.')}")
        self.status_label.setStyleSheet(f"color: {C['accent']}; font-size:13px;")

    def _start_trial(self):
        """Bắt đầu dùng thử 3 ngày (server neo theo máy nên không xin lại được)"""
        result = backend.ActivationManager.start_trial()
        if result.get("success"):
            self.activated = True
            days = result.get("days_remaining", 3)
            self.status_label.setText(f"🎉 Bắt đầu dùng thử! Còn {days:.0f} ngày")
            self.status_label.setStyleSheet(f"color: {C['green']}; font-size:13px;")
            QTimer.singleShot(1200, self._close_and_continue)
        else:
            self.status_label.setText(
                f"{result.get('error') or 'Thời gian dùng thử đã hết.'}"
            )
            self.status_label.setStyleSheet(f"color: {C['accent']}; font-size:13px;")

    def _close_and_continue(self):
        self.close()
        # Không gọi callback ở đây — callback sẽ được gọi sau khi app.exec() kết thúc
        # trong mainloop() để tránh nested event loop

    def mainloop(self):
        if _APP_LOOP_RUNNING:
            # Giữa phiên: vòng lặp của dashboard đang chạy → app.exec() sẽ bị Qt
            # từ chối và trả về ngay, dialog chưa kịp hiện đã bị thu hồi.
            self.exec()
        else:
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
        rp.apply_dialog_size(self, 580, 460, fixed=True, max_scale=1.25)
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
        if _APP_LOOP_RUNNING:
            self.exec()
        else:
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
