"""Mixer panel builder for MainDashboard."""
import backend
from PySide6.QtCore import Qt
from core import mic2
from ui.design_tokens import C
from ui.components.painter_panel import GlassPanel
from ui.components.hmixer_channel import HMixerChannel
from ui.panels._dev_buttons import attach_dev_ctx_menu, build_dev_row


def _resolve_cc_number(dashboard, cc_key):
    """cc của kênh có thể là tên built-in (tra MIDI_CC) hoặc số CC thô (slider custom từ Dev Mode)."""
    if isinstance(cc_key, int):
        return cc_key
    return dashboard.MIDI_CC.get(cc_key)


def midi_route(dashboard, cc_key):
    """(khoá gốc, hàm gửi CC) của một kênh mixer.

    Mic 2 dùng chung số CC (mức, tắt, CC phụ mute_multi_cc) với Mic nhưng đi
    kênh MIDI 2 và không phát đôi; mọi kênh khác gửi thẳng engine.send_midi
    như trước.
    """
    if cc_key == mic2.MIC2_KEY:
        engine = dashboard.engine
        return mic2.MIC_KEY, lambda cc, v: engine.send_midi_on_channel(mic2.MIC2_CHANNEL, cc, v)
    return cc_key, dashboard.engine.send_midi


def _remember_mic_mutes(dashboard):
    """Hai mic: ghi NGAY trạng thái tắt/mở cả hai mic — máy hay bị tắt nguồn
    ngang, chờ lúc thoát app mới lưu là mất."""
    settings = dashboard.settings
    if not mic2.is_enabled(settings):
        return
    settings["mic_mutes"] = {k: bool(dashboard.mute_states.get(k, False))
                             for k in (mic2.MIC_KEY, mic2.MIC2_KEY)}
    try:
        backend.ConfigManager.save_settings(settings)
    except Exception as e:
        print(f"[MIC2] Không ghi được trạng thái tắt mic: {e}")


# Cột tên kênh rộng nhất khi bật hai mic (px).
_MIC_NAME_MAX_W = 110


# Kênh chỉ điều khiển player YouTube (nhúng hoặc CDP), không gửi CC nào cho DAW
# — Studio One lẫn Cubase. Không có player thì frontend làm xám kênh.
YOUTUBE_ONLY_KEY = "mix_music"


def _make_mute_callback(dashboard, cc_key, mute_cc_map, val_range=(0, 100)):
    min_v, max_v = val_range
    def toggle(is_muted):
        dashboard.mute_states[cc_key] = is_muted
        if cc_key == YOUTUBE_ONLY_KEY:
            if is_muted:
                dashboard.engine.set_browser_volume(0)
            else:
                dashboard.engine.set_browser_volume(int(dashboard._mixer_sliders[cc_key].value()))
            return
        base_key, send = midi_route(dashboard, cc_key)
        mute_cc = mute_cc_map.get(base_key)
        if mute_cc is not None:
            send(dashboard.MIDI_CC[mute_cc], 127 if is_muted else 0)
        else:
            # Slider custom không có CC mute riêng: gửi 0 khi mute,
            # khôi phục giá trị hiện tại của slider khi bật lại
            cc_num = _resolve_cc_number(dashboard, cc_key)
            if cc_num is not None:
                if is_muted:
                    dashboard.engine.send_midi(cc_num, 0)
                else:
                    slider = dashboard._mixer_sliders.get(cc_key)
                    val = slider.value() if slider is not None else min_v
                    normalized = (val - min_v) / (max_v - min_v) if max_v > min_v else 0
                    dashboard.engine.send_midi(cc_num, max(0, min(127, int(normalized * 127))))

        try:
            multi_cc_map = backend.AppConfig.get_mute_multi_cc()
            for entry in multi_cc_map.get(base_key, []):
                cc_num = int(entry["cc"])
                val = int(entry["on_value"]) if is_muted else int(entry["off_value"])
                send(cc_num, val)
                print(f"[MUTE MULTI] {cc_key} -> CC {cc_num} = {val} ({'mute' if is_muted else 'unmute'})")
        except Exception as e:
            print(f"[MUTE MULTI] Lỗi gửi CC phụ cho {cc_key}: {e}")

        # Ghi đĩa SAU khi đã gửi MIDI — không để việc ghi file làm chậm lệnh tắt.
        if cc_key in (mic2.MIC_KEY, mic2.MIC2_KEY):
            _remember_mic_mutes(dashboard)
    return toggle


def db_to_midi(db, min_v, unity):
    """dB (min_v..0..+10) → CC. 0 dB = `unity` (Studio One 76, Cubase 100), hai đoạn tuyến tính."""
    db = float(db)
    if db <= min_v:
        return 0
    if db <= 0:
        return max(0, min(127, int(round(unity + db * (unity / abs(min_v))))))
    return max(0, min(127, int(round(unity + db * ((127 - unity) / 10.0)))))


def _make_value_changed_callback(dashboard, cc_key, range_tuple, unit):
    min_v, max_v = range_tuple
    def cb(raw_value):
        if cc_key == YOUTUBE_ONLY_KEY:
            dashboard.engine.set_browser_volume(int(raw_value))
            return
        base_key, send = midi_route(dashboard, cc_key)
        cc_num = _resolve_cc_number(dashboard, base_key)
        if cc_num is None:
            return
        if base_key in ["mix_mic", "mix_reverb"]:
            # 0 dB -> fader_unity_cc của DAW: Studio One 76, Cubase 100 (đo 2026-10-04)
            from core import daw
            midi = db_to_midi(raw_value, min_v, daw.active().fader_unity_cc)
        else:
            # voice_fx và slider custom: tuyến tính min..max -> 0..127
            normalized = (raw_value - min_v) / (max_v - min_v) if max_v > min_v else 0
            midi = int(normalized * 127)
            midi = max(0, min(127, midi))

        send(cc_num, midi)
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
        # Thanh "Giọng" đời cũ lưu mức dưới tên "tone_music" (trước khi tách CC 54).
        if key == "voice_fx" and key not in saved_levels:
            val = saved_levels.get("tone_music", fallback)
        else:
            val = saved_levels.get(key, fallback)
        # Nếu giá trị là 50 (mặc định cũ của thang 0-100) và dải hiện tại là âm-dương
        # thì khả năng cao là setting cũ, ta reset về 0.
        if val == 50 and key in ["mix_mic", "mix_reverb", "voice_fx"]:
            return 0
        return val

    ui_config = backend.UiConfigManager.load_ui_config()
    channels_config = ui_config.get("mixer", [])

    def _channel_spec(ch_cfg):
        # Resolve dynamic color if it's a token name
        c_val = ch_cfg.get("color", "#ffffff")
        if c_val in C:
            c_val = C[c_val]

        # Slider custom bỏ CC ("không gán") thì khoá theo id của nó và không gửi
        # MIDI — trước đây rơi về "mix_music", chiếm chỗ kênh Nhạc và chỉnh
        # luôn âm lượng nhạc.
        cc_key = ch_cfg.get("cc", ch_cfg.get("id", "mix_music"))
        return {
            "label": ch_cfg.get("label", ""),
            "icon": ch_cfg.get("icon", ""),
            "color": c_val,
            "cc": cc_key,
            "range": tuple(ch_cfg.get("range", [0, 100])),
            "default": _get_level(cc_key, ch_cfg.get("default", 0)),
            "unit": ch_cfg.get("unit", ""),
            "has_mute": ch_cfg.get("has_mute", False),
            "has_inf_bottom": ch_cfg.get("has_inf_bottom", False),
        }

    dashboard._mixer_sliders = {}
    dashboard._mixer_val_labels = {}
    dashboard._mixer_icon_btns = {}
    dashboard._mixer_channels = {}
    # Hàm gửi MIDI của từng kênh, giữ lại để lượt đồng bộ toàn cục
    # (_sync_midi_states) bắn lại được mức thanh trượt mà không phải chép lại
    # phép quy đổi dB -> MIDI ở chỗ khác.
    dashboard._mixer_senders = {}
    # Đặt mute theo giá trị (không lật) — Tự sửa âm thanh dùng.
    dashboard._mixer_mute_setters = {}

    def _add_channel(ch, ch_cfg):
        """Dựng một kênh; `ch_cfg` là entry mà menu Dev Mode Sửa/Ẩn nhắm tới
        (Mic 2 dùng entry giả id mix_mic_2 — frontend xử lý riêng)."""
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

        # Accessible names cho slider + mute button
        ch_view.setAccessibleName(f"Kênh {ch['label']}")
        try:
            ch_view.slider.setAccessibleName(f"Âm lượng {ch['label']}")
            ch_view.slider.setAccessibleDescription(
                "Mũi tên trái phải để tăng giảm"
            )
            if ch["has_mute"]:
                ch_view.mute_btn.setAccessibleName(f"Tắt âm {ch['label']}")
                ch_view.mute_btn.setAccessibleDescription(
                    f"Tắt hoặc bật lại âm thanh kênh {ch['label']}"
                )
        except Exception:
            pass

        def _bind_mute(channel_view, cc_key=ch["cc"], val_range=ch["range"]):
            def _do_toggle():
                is_muted = channel_view.toggle_mute()
                _make_mute_callback(dashboard, cc_key, mute_cc_map, val_range)(is_muted)
            return _do_toggle

        if ch["has_mute"]:
            ch_view.mute_btn.clicked.connect(_bind_mute(ch_view))

            def _set_muted(muted, channel_view=ch_view, cc_key=ch["cc"], val_range=ch["range"]):
                # Cùng đường gửi CC với nút bấm; chỉ lật hình khi trạng thái khác.
                if channel_view.is_muted() != bool(muted):
                    channel_view.toggle_mute()
                _make_mute_callback(dashboard, cc_key, mute_cc_map, val_range)(bool(muted))
            dashboard._mixer_mute_setters[ch["cc"]] = _set_muted

        _send_value = _make_value_changed_callback(dashboard, ch["cc"], ch["range"], ch["unit"])
        ch_view.slider.valueChanged.connect(_send_value)
        dashboard._mixer_senders[ch["cc"]] = _send_value

        # Announce slider value change qua announcer (debounced).
        def _announce_slider_value(value, cc_key=ch["cc"]):
            announcer = getattr(dashboard, "_a11y_announcer", None)
            if announcer is not None:
                announcer.announce_slider(cc_key, value)
        ch_view.slider.valueChanged.connect(_announce_slider_value)

        # --- Dev Mode Context Menu ---
        if ch_cfg is not None and getattr(dashboard, "is_dev_mode", False):
            attach_dev_ctx_menu(dashboard, "mixer", ch_view, ch_cfg)

        vl.addWidget(ch_view)
        dashboard._mixer_sliders[ch["cc"]] = ch_view.slider
        dashboard._mixer_val_labels[ch["cc"]] = ch_view.val_label
        dashboard._mixer_icon_btns[ch["cc"]] = ch_view.mute_btn
        dashboard._mixer_channels[ch["cc"]] = ch_view
        return ch_view

    # Hai mic (Studio One): kênh Mic 2 là phần mở rộng chỉ có khi bật — không
    # thêm vào ui_config, để _merge_new_defaults không đẩy nó sang máy khác.
    two_mics = mic2.is_enabled(dashboard.settings)
    mic_labels = mic2.labels(dashboard.settings) if two_mics else {}
    mute_states = getattr(dashboard, "mute_states", None) or {}

    # Một vòng duy nhất trên entry cấu hình: `ch_cfg` trong thân vòng luôn là
    # kênh đang dựng. (Trước đây chép sang list trung gian rồi dựng ở vòng thứ
    # hai — `ch_cfg` lọt vào vòng sau là entry cuối, menu Sửa/Ẩn nhắm nhầm Giọng.)
    for ch_cfg in channels_config:
        if ch_cfg.get("hidden", False):
            continue
        ch = _channel_spec(ch_cfg)
        if ch["cc"] in dashboard._mixer_channels:
            # Các bảng _mixer_* (và mixer_levels/mute_states) khoá theo CC — kênh
            # thứ hai cùng CC sẽ đè kênh đầu, không đồng bộ được. Bỏ qua kênh trùng.
            print(f"[MIXER] Bỏ kênh '{ch['label']}': trùng CC {ch['cc']!r} với kênh đã có")
            continue
        if not (two_mics and ch["cc"] == mic2.MIC_KEY):
            _add_channel(ch, ch_cfg)
            continue
        # Mic + Mic 2 liền nhau, cùng kiểu kênh; dựng lại (Cài đặt, Dev Mode)
        # vẫn hiện đúng trạng thái tắt đang giữ trong mute_states.
        # Tên hai kênh lấy từ settings["mic_labels"], không từ ui_config: menu
        # Dev Mode mang tên đang hiện để Sửa thấy đúng tên, và frontend ghi tên
        # mới vào mic_labels (_on_edit_widget). Mic 2 không có entry ui_config —
        # cfg giả id/cc = mix_mic_2 chỉ để menu biết đang bấm kênh nào.
        ch["label"] = mic_labels[mic2.MIC_KEY]
        ch2 = dict(ch, cc=mic2.MIC2_KEY, label=mic_labels[mic2.MIC2_KEY],
                   default=_get_level(mic2.MIC2_KEY, 0))
        cfg1 = dict(ch_cfg, label=ch["label"])
        cfg2 = dict(ch_cfg, id=mic2.MIC2_KEY, cc=mic2.MIC2_KEY, label=ch2["label"])
        for spec, cfg in ((ch, cfg1), (ch2, cfg2)):
            _add_channel(spec, cfg).set_muted(bool(mute_states.get(spec["cc"], False)))

    if two_mics and dashboard._mixer_channels:
        # Tên hai mic ("Mic Không Dây") dài hơn cột tên 52px → nới cột tên mọi
        # kênh cho thẳng hàng; chặn trên để tên quá dài không bóp thanh trượt.
        views = dashboard._mixer_channels.values()
        width = min(_MIC_NAME_MAX_W, max(52, *(v.name_width_hint() for v in views)))
        for v in views:
            v.set_name_width(width)

    # --- Dev Mode: + Thêm / ⚙ Quản lý ---
    if getattr(dashboard, "is_dev_mode", False):
        vl.addLayout(build_dev_row(dashboard, "mixer", "+ Thêm", "slider"))

    vl.addStretch()

    # Kênh mới dựng mặc định sáng — xám ngay nếu chưa có player YouTube, khỏi
    # chờ nhịp kiểm tra trình duyệt 2.5s.
    update_music = getattr(dashboard, "_update_music_channel_availability", None)
    if callable(update_music):
        update_music()
    return panel
