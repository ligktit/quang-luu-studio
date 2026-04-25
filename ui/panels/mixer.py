"""Mixer panel builder for MainDashboard."""
import backend
from ui.design_tokens import C
from ui.components.painter_panel import GlassPanel
from ui.components.hmixer_channel import HMixerChannel


def _make_mute_callback(dashboard, cc_key, mute_cc_map):
    def toggle(is_muted):
        dashboard.mute_states[cc_key] = is_muted
        mute_cc = mute_cc_map[cc_key]
        dashboard.engine.send_midi(dashboard.MIDI_CC[mute_cc], 127 if is_muted else 0)
        
        # Mute browser volume if it's the music channel
        if cc_key == "mix_music":
            if is_muted:
                dashboard.engine.set_browser_volume(0)
            else:
                val = dashboard._mixer_sliders["mix_music"].value()
                dashboard.engine.set_browser_volume(int(val))

        try:
            multi_cc_map = backend.AppConfig.get_mute_multi_cc()
            for entry in multi_cc_map.get(cc_key, []):
                cc_num = int(entry["cc"])
                val = int(entry["on_value"]) if is_muted else int(entry["off_value"])
                dashboard.engine.send_midi(cc_num, val)
                print(f"[MUTE MULTI] {cc_key} -> CC {cc_num} = {val} ({'mute' if is_muted else 'unmute'})")
        except Exception as e:
            print(f"[MUTE MULTI] Lỗi gửi CC phụ cho {cc_key}: {e}")
    return toggle


def _make_value_changed_callback(dashboard, cc_key, range_tuple, unit):
    min_v, max_v = range_tuple
    def cb(raw_value):
        if unit == " dB":
            db = min_v + ((max_v - min_v) * (raw_value / 100.0))
            # Preserve original -60 to +10 dB mapping for MIDI CC
            orig_min, orig_max = -60.0, 10.0
            midi = int(((db - orig_min) / (orig_max - orig_min)) * 127)
            midi = max(0, min(127, midi))
        else:
            midi = int((raw_value / 100.0) * 127)
        dashboard.engine.send_midi(dashboard.MIDI_CC[cc_key], midi)
        if cc_key == "mix_music":
            dashboard.engine.set_browser_volume(int(raw_value))
    return cb


def build_panel_mixer(dashboard) -> GlassPanel:
    panel = GlassPanel("MIXER")
    vl = panel.body_layout
    vl.setSpacing(2)

    mute_cc_map = {
        "mix_music":   "mute_music",
        "mix_mic":     "mute_mic",
        "mix_reverb":  "mute_reverb",
        "mix_backing": "mute_backing",
    }
    saved_levels = dashboard.settings.get("mixer_levels", {}) if dashboard.settings else {}
    channels = [
        {"label": "Nhạc", "icon": "♪", "color": C["teal"],   "cc": "mix_music",  "range": (0, 100),  "default": saved_levels.get("mix_music", 70), "unit": ""},
        {"label": "Mic",  "icon": "☉", "color": C["orange"], "cc": "mix_mic",    "range": (-12, 12), "default": saved_levels.get("mix_mic", 50), "unit": " dB"},
        {"label": "Vang", "icon": "≡", "color": C["accent"], "cc": "mix_reverb", "range": (-12, 12), "default": saved_levels.get("mix_reverb", 50), "unit": " dB"},
    ]

    dashboard._mixer_sliders = {}
    dashboard._mixer_val_labels = {}
    dashboard._mixer_icon_btns = {}
    dashboard._mixer_channels = {}

    for ch in channels:
        ch_view = HMixerChannel(
            icon=ch["icon"],
            label=ch["label"],
            color=ch["color"],
            cc_key=ch["cc"],
            val_range=ch["range"],
            default=ch["default"],
            unit=ch["unit"],
        )

        def _bind_mute(channel_view, cc_key=ch["cc"]):
            def _do_toggle():
                is_muted = channel_view.toggle_mute()
                _make_mute_callback(dashboard, cc_key, mute_cc_map)(is_muted)
            return _do_toggle

        ch_view.mute_btn.clicked.connect(_bind_mute(ch_view))
        ch_view.slider.valueChanged.connect(
            _make_value_changed_callback(dashboard, ch["cc"], ch["range"], ch["unit"])
        )

        vl.addWidget(ch_view)
        dashboard._mixer_sliders[ch["cc"]] = ch_view.slider
        dashboard._mixer_val_labels[ch["cc"]] = ch_view.val_label
        dashboard._mixer_icon_btns[ch["cc"]] = ch_view.mute_btn
        dashboard._mixer_channels[ch["cc"]] = ch_view

    vl.addStretch()
    return panel
