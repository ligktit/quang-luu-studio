"""Mode & SFX panel builder for MainDashboard."""
import os
from PySide6.QtWidgets import QHBoxLayout, QLabel
from PySide6.QtCore import Qt

from ui.design_tokens import C, SP, FONT
from ui.components.painter_button import PainterButton
from ui.components.painter_panel import GlassPanel
from ui.components.sfx_button_area import SfxButtonArea


def build_panel_mode(dashboard) -> GlassPanel:
    panel = GlassPanel("MODE")
    vl = panel.body_layout
    vl.setSpacing(SP.SM)
    vl.addSpacing(2)

    import backend
    ui_config = backend.UiConfigManager.load_ui_config()
    modes_config = ui_config.get("mode", [])

    mode_config = []
    dashboard._mode_colors = {}
    
    for m_cfg in modes_config:
        if m_cfg.get("hidden", False):
            continue
        
        label = m_cfg.get("label", "Unknown")
        c_val = m_cfg.get("color", "#ffffff")
        if c_val in C:
            c_val = C[c_val]
            
        mode_config.append((label, c_val, m_cfg))
        dashboard._mode_colors[label] = c_val

    mode_row = QHBoxLayout()
    mode_row.setSpacing(3)
    for mlabel, mcolor, m_cfg in mode_config:
        mbtn = PainterButton(mlabel, color=mcolor, height=26, radius=8, font_size=9)
        mbtn.setAccessibleName(f"Chế độ {mlabel}")
        mbtn.setAccessibleDescription(f"Chuyển sang chế độ {mlabel}")
        
        # Determine callback: built-in mode or custom?
        action_name = m_cfg.get("action", "")
        cb = getattr(dashboard, f"_on_{action_name}", None)
        if not cb:
            # Custom action
            cc_val = m_cfg.get("cc")
            on_val = m_cfg.get("on_value", 127)
            off_val = m_cfg.get("off_value", 0)
            
            def make_custom_cb(c=cc_val, on=on_val, off=off_val, m=mlabel):
                def _do_action():
                    if dashboard.current_mode == m:
                        dashboard.engine.send_midi(c, off)
                        dashboard.current_mode = None
                    else:
                        dashboard.engine.send_midi(c, on)
                        dashboard.current_mode = m
                    
                    # Visual update
                    for mx, btn in dashboard._mode_buttons.items():
                        base = dashboard._mode_colors.get(mx, C["card_hover"])
                        if mx == dashboard.current_mode:
                            btn.setStyleSheet(f"""
                                QPushButton {{
                                    background-color: {lighten(base, 0.25)};
                                    color: white; border: 2px solid white;
                                    border-radius: 10px; font-size: 10px; font-weight: 700;
                                    font-family: {FONT};
                                }}
                                QPushButton:hover {{ background-color: {lighten(base, 0.3)}; }}
                            """)
                        else:
                            from ui.components.button import _make_pill_qss
                            btn.setStyleSheet(_make_pill_qss(base, lighten(base, 0.15), 10, 10))
                return _do_action
            cb = make_custom_cb()
            mbtn.clicked.connect(cb)
        else:
            mbtn.clicked.connect(lambda m=mlabel: dashboard._on_mode_selected(m, toggle=True))
            
        dashboard._mode_buttons[mlabel] = mbtn
        
        # --- Dev Mode Context Menu ---
        if getattr(dashboard, "is_dev_mode", False):
            from PySide6.QtCore import Qt
            mbtn.setContextMenuPolicy(Qt.CustomContextMenu)
            
            def make_ctx_cb(cfg=m_cfg, b=mbtn):
                def show_ctx(pos):
                    from PySide6.QtWidgets import QMenu
                    from PySide6.QtGui import QAction
                    menu = QMenu(b)
                    menu.setStyleSheet("QMenu { background: #1e1e1e; color: white; }")
                    
                    edit_act = QAction("Sửa", menu)
                    edit_act.triggered.connect(lambda: dashboard._on_edit_widget("mode", cfg))
                    
                    hide_act = QAction("Ẩn", menu)
                    hide_act.triggered.connect(lambda: dashboard._on_hide_widget("mode", cfg))
                    
                    menu.addAction(edit_act)
                    menu.addAction(hide_act)
                    menu.exec(b.mapToGlobal(pos))
                return show_ctx
                
            mbtn.customContextMenuRequested.connect(make_ctx_cb())
            
        mode_row.addWidget(mbtn)
        
    vl.addLayout(mode_row)
    
    # --- Dev Mode Add Button ---
    if getattr(dashboard, "is_dev_mode", False):
        from PySide6.QtWidgets import QPushButton
        from PySide6.QtCore import Qt
        add_btn = QPushButton("+ Thêm Mode")
        add_btn.setStyleSheet(f"background-color: transparent; border: 1px dashed {C['teal']}; color: {C['teal']}; margin-top: 5px;")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(lambda: dashboard._on_add_widget("mode", "button"))
        vl.addWidget(add_btn)

    sfx_title = QLabel("SFX")
    sfx_title.setStyleSheet(
        f"font-size:10px; font-weight:700; color:{C['text_muted']};"
        f" font-family:{FONT}; background:transparent;"
    )
    sfx_title.setAlignment(Qt.AlignCenter)
    vl.addWidget(sfx_title)

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
    dashboard._sfx_area.sfx_play.connect(dashboard._on_sfx_play)
    vl.addWidget(dashboard._sfx_area)

    vl.addStretch()
    return panel
