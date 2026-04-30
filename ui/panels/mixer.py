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
        if cc_key in ["mix_mic", "mix_reverb"]:
            # UI -10..+10 là dB thật. Calibrate với Studio One: 0 dB = MIDI 76, +10 dB = MIDI 100
            # (tuyến tính trong dải UI: 2.4 MIDI / dB)
            db = float(raw_value)
            midi = int(round(76 + db * 2.4))
            midi = max(0, min(127, midi))
        elif cc_key == "tone_music":
            # Transpose: -12 to 12
            normalized = (raw_value - min_v) / (max_v - min_v) if max_v > min_v else 0
            midi = int(normalized * 127)
            midi = max(0, min(127, midi))
        else:
            # mix_music: 0 to 100
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
    
    def _get_level(key, fallback):
        val = saved_levels.get(key, fallback)
        # Nếu giá trị là 50 (mặc định cũ của thang 0-100) và dải hiện tại là âm-dương
        # thì khả năng cao là setting cũ, ta reset về 0.
        if val == 50 and key in ["mix_mic", "mix_reverb", "tone_music"]:
            return 0
        return val

    channels = [
        {"label": "Nhạc", "icon": "♪", "color": C["teal"],   "cc": "mix_music",  "range": (0, 100),  "default": _get_level("mix_music", 70), "unit": "", "has_mute": True, "has_inf_bottom": False},
        {"label": "Mic",  "icon": "☉", "color": C["orange"], "cc": "mix_mic",    "range": (-10, 10), "default": _get_level("mix_mic", 0), "unit": "", "has_mute": True, "has_inf_bottom": True},
        {"label": "Vang", "icon": "≡", "color": C["accent"], "cc": "mix_reverb", "range": (-10, 10), "default": _get_level("mix_reverb", 0), "unit": "", "has_mute": True, "has_inf_bottom": True},
        {"label": "Giọng", "icon": "↕", "color": C["deep_purple"], "cc": "tone_music", "range": (-12, 12), "default": _get_level("tone_music", 0), "unit": "", "has_mute": False, "has_inf_bottom": False},
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
            has_mute=ch["has_mute"],
            has_inf_bottom=ch["has_inf_bottom"],
        )

        def _bind_mute(channel_view, cc_key=ch["cc"]):
            def _do_toggle():
                is_muted = channel_view.toggle_mute()
                _make_mute_callback(dashboard, cc_key, mute_cc_map)(is_muted)
            return _do_toggle

        if ch["has_mute"]:
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
