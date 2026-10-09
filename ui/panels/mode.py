"""Mode & SFX panel builder for MainDashboard."""
import os
from PySide6.QtWidgets import QHBoxLayout, QLabel
from PySide6.QtCore import Qt

from ui.design_tokens import C, SP, FONT
from ui.components.mode_button import ModeToggleButton
from ui.components.painter_hslider import PainterHSlider
from ui.components.painter_panel import GlassPanel
from ui.components.sfx_button_area import SfxButtonArea
from ui.panels._dev_buttons import attach_dev_ctx_menu, build_dev_row


def build_panel_mode(dashboard) -> GlassPanel:
    panel = GlassPanel("MODE")
    vl = panel.body_layout
    vl.setSpacing(SP.SM)
    vl.addSpacing(2)

    import backend
    ui_config = backend.UiConfigManager.load_ui_config()
    modes_config = ui_config.get("mode", [])

    mode_config = []
    for m_cfg in modes_config:
        if m_cfg.get("hidden", False):
            continue

        label = m_cfg.get("label", "Unknown")
        c_val = m_cfg.get("color", "#ffffff")
        if c_val in C:
            c_val = C[c_val]

        mode_config.append((label, c_val, m_cfg))

    mode_row = QHBoxLayout()
    mode_row.setSpacing(3)
    for mlabel, mcolor, m_cfg in mode_config:
        # Tắt = viền mỏng, bật = đổ đầy + phát sáng (xem ui/components/mode_button.py).
        mbtn = ModeToggleButton(mlabel, color=mcolor, height=28, radius=8, font_size=9)
        mbtn.setToolTip(f"Bật/tắt chế độ {mlabel} (độc lập với các mode khác)")
        mbtn.setAccessibleName(f"Chế độ {mlabel}")
        # Panel có thể bị dựng lại (Dev Mode) — lấy lại đèn theo trạng thái cũ.
        mbtn.setActive(bool(dashboard.mode_states.get(mlabel, False)))

        # Determine callback: built-in mode or custom?
        action_name = m_cfg.get("action", "")
        cc_val = m_cfg.get("cc")
        # Dev-mode override: CC dạng SỐ → gửi thẳng CC, bỏ qua action built-in.
        if isinstance(cc_val, int):
            cb = None
        else:
            cb = getattr(dashboard, f"_on_{action_name}", None)
            # Mode built-in dùng action "set_mode_*" (vd set_mode_lofi) nhưng
            # handler thật là _on_mode_selected(label) — không có
            # _on_set_mode_lofi. Thiếu nhánh này thì nút rơi xuống path custom
            # với cc=None → send_midi(None, 127) fail, Studio One không đổi mode.
            if not cb and action_name.startswith("set_mode"):
                cb = dashboard._on_mode_selected
        if not cb:
            # Custom action (hoặc built-in bị CC số override)
            on_val = m_cfg.get("on_value", 127)
            off_val = m_cfg.get("off_value", 0)
            
            def make_custom_cb(c=cc_val, on=on_val, off=off_val, m=mlabel):
                def _do_action():
                    # Toggle độc lập y như mode built-in: chỉ chạm CC của
                    # chính nút này, không tắt nút nào khác.
                    new_state = not dashboard.mode_states.get(m, False)
                    dashboard.mode_states[m] = new_state
                    dashboard.engine.send_midi(c, on if new_state else off)
                    dashboard._refresh_mode_button(m)
                return _do_action
            cb = make_custom_cb()
            mbtn.clicked.connect(cb)
        else:
            mbtn.clicked.connect(lambda m=mlabel: dashboard._on_mode_selected(m, toggle=True))
            
        dashboard._mode_buttons[mlabel] = mbtn
        
        # --- Dev Mode Context Menu ---
        if getattr(dashboard, "is_dev_mode", False):
            attach_dev_ctx_menu(dashboard, "mode", mbtn, m_cfg)
            
        mode_row.addWidget(mbtn)
        
    vl.addLayout(mode_row)
    
    # --- Dev Mode: + Thêm Mode / ⚙ Quản lý ---
    if getattr(dashboard, "is_dev_mode", False):
        vl.addLayout(build_dev_row(dashboard, "mode", "+ Thêm Mode", "button", " margin-top: 5px;"))

    sfx_title = QLabel("SFX")
    sfx_title.setStyleSheet(
        f"font-size:10px; font-weight:700; color:{C['text_muted']};"
        f" font-family:{FONT}; background:transparent;"
    )
    sfx_title.setAlignment(Qt.AlignCenter)
    vl.addWidget(sfx_title)

    # Fader âm lượng chung cho mọi SFX (phát trong app, không qua DAW).
    vol_row = QHBoxLayout()
    vol_row.setSpacing(6)
    vol_icon = QLabel("🔊")
    vol_icon.setStyleSheet("font-size:11px; background:transparent;")
    vol_pct = QLabel()
    vol_pct.setFixedWidth(34)
    vol_pct.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    vol_pct.setStyleSheet(
        f"font-size:10px; font-weight:700; color:{C['text_muted']};"
        f" font-family:{FONT}; background:transparent;"
    )
    slider = PainterHSlider(0, 100, dashboard._sfx_volume_setting(), color=C["teal"])
    slider.setToolTip("Âm lượng SFX")
    slider.setAccessibleName("Âm lượng SFX")
    vol_pct.setText(f"{slider.value()}%")
    slider.valueChanged.connect(lambda v: vol_pct.setText(f"{v}%"))
    slider.valueChanged.connect(dashboard._on_sfx_volume_changed)
    dashboard._sfx_volume_slider = slider
    vol_row.addWidget(vol_icon)
    vol_row.addWidget(slider, 1)
    vol_row.addWidget(vol_pct)
    vl.addLayout(vol_row)

    # In frozen (onefile) build, sfx/ is extracted to _MEIPASS.
    # In dev, walk up from ui/panels/ to project root.
    import sys
    if getattr(sys, 'frozen', False):
        app_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    else:
        app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sfx_list = dashboard.settings.get("sfx_buttons", None)
    dashboard._sfx_area = SfxButtonArea(
        sfx_list=sfx_list,
        app_dir=app_dir,
        parent=panel,
    )
    dashboard._sfx_area.sfx_changed.connect(dashboard._on_sfx_config_changed)
    dashboard._sfx_area.sfx_toggle.connect(dashboard._on_sfx_toggle)
    dashboard._sfx_area.sfx_stop.connect(dashboard._sfx_player.stop)
    # Panel có thể bị dựng lại (Dev Mode) — lấy lại đèn SFX đang phát.
    for item in dashboard._sfx_area.get_sfx_list():
        if dashboard._sfx_player.is_playing(item.get("id", "")):
            dashboard._sfx_area.set_playing(item["id"], True)
    vl.addWidget(dashboard._sfx_area)

    vl.addStretch()
    return panel
