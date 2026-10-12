"""Nối AudioDoctorService với MainDashboard: thao tác trên app + dựng DoctorContext."""
import os

import backend
from core import daw
from core.audio_doctor import default_checks
from core.audio_doctor.context import DoctorContext
from core.audio_doctor.service import AudioDoctorService
from core.audio_doctor.system import SystemProbe
from core.audio_doctor.win_audio import WinAudio
from core.config import DATA_DIR, MIDI_FEEDBACK_PORT_NAME, MIDI_PORT_NAME
from ui.ui_invoker import UiInvoker

MIC_KEY = "mix_mic"
MUSIC_KEY = "mix_music"
MUSIC_MIN_PCT = 5
MUSIC_RESTORE_PCT = 80


class DashboardDoctorActions:
    def __init__(self, dashboard, invoker):
        self._d = dashboard
        self._inv = invoker

    # ── DAW / MIDI ──────────────────────────────────────────────────────────
    def launch_daw(self):
        path = (self._d.settings or {}).get("studio_one_path", "")
        if not path or not os.path.exists(path):
            return False
        self._d.engine.launch_app(path)
        return True

    def reconnect_midi(self):
        eng = self._d.engine
        eng.midi_handler.stop_listening()
        ok = bool(eng.connect_midi())
        eng.midi_handler.ensure_listening()
        return ok

    def sync_midi(self):
        self._inv.call(self._d._sync_midi_states)

    def close_daw(self):
        res = self._d.engine.close_studio_one_safely(save=True) or {}
        return res.get("status") in ("closed", "not_running")

    # ── kênh trên app ───────────────────────────────────────────────────────
    def _slider(self, key):
        return (getattr(self._d, "_mixer_sliders", None) or {}).get(key)

    def app_mic_state(self):
        def read():
            sl = self._slider(MIC_KEY)
            if sl is None:
                return None
            # Thanh Mic -10..+10 dB, nấc dưới cùng là -∞ (tắt hẳn).
            level = float("-inf") if sl.value() <= sl.minimum() else float(sl.value())
            return bool(self._d.mute_states.get(MIC_KEY, False)), level
        return self._inv.call(read)

    def ensure_app_mic_on(self):
        def do():
            sl = self._slider(MIC_KEY)
            setter = (getattr(self._d, "_mixer_mute_setters", None) or {}).get(MIC_KEY)
            if sl is None:
                return
            if setter is not None and self._d.mute_states.get(MIC_KEY, False):
                setter(False)
            if sl.value() <= sl.minimum():
                sl.setValue(0)              # valueChanged → gửi CC mức Mic (0 dB)
            else:
                send = (getattr(self._d, "_mixer_senders", None) or {}).get(MIC_KEY)
                if send:
                    send(sl.value())        # DAW có thể đang lệch mức với app
        self._inv.call(do)

    def app_music_state(self):
        def read():
            ch = (getattr(self._d, "_mixer_channels", None) or {}).get(MUSIC_KEY)
            sl = self._slider(MUSIC_KEY)
            if ch is None or sl is None or not ch.is_available():
                return None
            return bool(self._d.mute_states.get(MUSIC_KEY, False)), int(sl.value())
        return self._inv.call(read)

    def ensure_app_music_on(self):
        def do():
            sl = self._slider(MUSIC_KEY)
            setter = (getattr(self._d, "_mixer_mute_setters", None) or {}).get(MUSIC_KEY)
            if sl is None:
                return
            if setter is not None and self._d.mute_states.get(MUSIC_KEY, False):
                setter(False)
            if sl.value() < MUSIC_MIN_PCT:
                sl.setValue(MUSIC_RESTORE_PCT)
        self._inv.call(do)

    # ── player YouTube ──────────────────────────────────────────────────────
    def player_state(self):
        eng = self._d.engine
        cdp = getattr(eng, "cdp_monitor", None)
        if cdp is not None and getattr(cdp, "is_connected", False) is True:
            return cdp.get_player_state() or {"muted": None, "volume": None}
        if getattr(eng, "embedded_volume_callback", None) is not None:
            return {"muted": None, "volume": None}
        return None

    def unmute_player(self):
        cdp = getattr(self._d.engine, "cdp_monitor", None)
        if cdp is not None and getattr(cdp, "is_connected", False) is True:
            return bool(cdp.unmute_player())
        return False

    # ── settings ────────────────────────────────────────────────────────────
    def save_setting(self, key, value):
        def do():
            self._d.settings[key] = value
            backend.ConfigManager.save_settings(self._d.settings)
        self._inv.call(do)


def build_service(dashboard):
    invoker = UiInvoker(dashboard)
    actions = DashboardDoctorActions(dashboard, invoker)
    system, win = SystemProbe(), WinAudio()

    def ctx_factory(ask=None):
        eng = dashboard.engine
        return DoctorContext(
            settings=dashboard.settings,
            daw=daw.active(),
            system=system,
            win=win,
            actions=actions,
            feedback=getattr(eng, "daw_feedback", None),
            send_cc=lambda cc, v: bool(eng.send_midi(int(cc), int(v))),
            midi_cc=dict(dashboard.MIDI_CC),
            midi_port=MIDI_PORT_NAME,
            feedback_port=MIDI_FEEDBACK_PORT_NAME,
            ask=ask or (lambda q: False),
        )

    return AudioDoctorService(ctx_factory, default_checks(),
                              log_path=os.path.join(DATA_DIR, "logs", "audio_doctor.log"))
