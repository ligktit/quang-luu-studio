"""Tools & Tone panel builder for MainDashboard."""
import backend
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QFrame,
    QLineEdit, QListWidget,
)
from PySide6.QtCore import Qt, QSignalBlocker

from ui.design_tokens import C, SP, FONT, FONT_MONO, lighten
from ui.components.painter_button import PainterButton
from ui.components.painter_panel import GlassPanel


def _build_search_bar(dashboard) -> QWidget:
    """Thanh tìm kiếm YouTube / dán link — chỉ dùng ở chế độ màn hình karaoke nhúng."""
    wrapper = QWidget()
    vl = QVBoxLayout(wrapper)
    vl.setContentsMargins(0, 0, 0, 0)
    vl.setSpacing(4)

    row = QHBoxLayout()
    row.setSpacing(6)
    inp = QLineEdit()
    inp.setPlaceholderText("Tìm bài hát hoặc dán link YouTube…")
    inp.setClearButtonEnabled(True)
    inp.setStyleSheet(
        f"QLineEdit {{ background: rgba(0,0,0,0.30); color: {C['text']}; border: 1px solid {C['border']};"
        f" border-radius: 8px; padding: 6px 10px; font-size: 12px; font-family: {FONT}; }}"
        f" QLineEdit:focus {{ border: 1px solid {C['teal']}; }}"
    )
    btn = QPushButton("🔍")
    btn.setFixedSize(34, 32)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setStyleSheet(
        f"QPushButton {{ background: {C['teal']}; color: #fff; border: none; border-radius: 8px;"
        f" font-size: 14px; font-weight: 800; }}"
        f" QPushButton:hover {{ background: {lighten(C['teal'], 0.15)}; }}"
    )
    row.addWidget(inp, 1)
    row.addWidget(btn)
    vl.addLayout(row)

    results = QListWidget()
    results.setVisible(False)
    results.setMaximumHeight(150)
    results.setStyleSheet(
        f"QListWidget {{ background: rgba(0,0,0,0.35); color: {C['text']}; border: 1px solid {C['border']};"
        f" border-radius: 8px; font-size: 11px; font-family: {FONT}; }}"
        f" QListWidget::item {{ padding: 5px 8px; }}"
        f" QListWidget::item:hover {{ background: rgba(255,255,255,0.08); }}"
        f" QListWidget::item:selected {{ background: {C['teal']}; color: #fff; }}"
    )
    vl.addWidget(results)

    dashboard._search_input = inp
    dashboard._search_results_list = results
    btn.clicked.connect(dashboard._on_search_submit)
    inp.returnPressed.connect(dashboard._on_search_submit)
    results.itemClicked.connect(dashboard._on_search_result_clicked)

    return wrapper


def _build_tone_knob_widget(dashboard, label: str, cc_key: str, color: str) -> QWidget:
    wrapper = QWidget()
    vl = QVBoxLayout(wrapper)
    vl.setContentsMargins(4, 4, 4, 4)
    vl.setSpacing(4)
    vl.setAlignment(Qt.AlignCenter)

    lbl = QLabel(label)
    lbl.setStyleSheet(
        f"font-size:10px; color:{C['text_muted']}; font-weight:700;"
        f" font-family:{FONT}; background:transparent;"
    )
    lbl.setAlignment(Qt.AlignCenter)
    vl.addWidget(lbl)

    stepper_row = QHBoxLayout()
    stepper_row.setSpacing(4)
    stepper_row.setContentsMargins(0, 0, 0, 0)

    _btn_qss = f"""
        QPushButton {{
            background-color: {color};
            color: #fff;
            border: none;
            border-radius: 14px;
            font-size: 16px;
            font-weight: 900;
            font-family: {FONT};
        }}
        QPushButton:hover {{ background-color: {lighten(color, 0.15)}; }}
        QPushButton:pressed {{ background-color: {lighten(color, -0.1)}; }}
    """

    btn_minus = QPushButton("−")
    btn_minus.setFixedSize(28, 28)
    btn_minus.setCursor(Qt.PointingHandCursor)
    btn_minus.setStyleSheet(_btn_qss)
    btn_minus.setToolTip(f"Giảm {label} 1 bán cung")
    btn_minus.setAccessibleName(f"Giảm {label}")
    btn_minus.setAccessibleDescription(f"Giảm {label} một bán cung")

    val_lbl = QLabel(" 0 ")
    val_lbl.setFixedWidth(42)
    val_lbl.setAlignment(Qt.AlignCenter)
    val_lbl.setStyleSheet(
        f"font-size:14px; font-weight:800; color:{color}; font-family:{FONT_MONO};"
        f" background:rgba(0,0,0,0.25); border-radius:6px; padding:2px 4px;"
    )
    val_lbl.setAccessibleName(f"Giá trị {label}")

    btn_plus = QPushButton("+")
    btn_plus.setFixedSize(28, 28)
    btn_plus.setCursor(Qt.PointingHandCursor)
    btn_plus.setStyleSheet(_btn_qss)
    btn_plus.setToolTip(f"Tăng {label} 1 bán cung")
    btn_plus.setAccessibleName(f"Tăng {label}")
    btn_plus.setAccessibleDescription(f"Tăng {label} một bán cung")

    stepper_row.addStretch()
    stepper_row.addWidget(btn_minus)
    stepper_row.addWidget(val_lbl)
    stepper_row.addWidget(btn_plus)
    stepper_row.addStretch()
    vl.addLayout(stepper_row)

    _current = [0]
    _CHROMATIC = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    _ENHARMONIC = {"Bb": "A#", "Eb": "D#", "Ab": "G#", "Db": "C#", "Gb": "F#"}

    def _shift_key_midi(delta):
        base = _ENHARMONIC.get(dashboard.current_tone, dashboard.current_tone)
        try:
            base_idx = _CHROMATIC.index(base)
        except ValueError:
            base_idx = 0
        new_key = _CHROMATIC[(base_idx + delta) % 12]
        if hasattr(dashboard, "tone_combo") and dashboard.tone_combo.findText(new_key) >= 0:
            with QSignalBlocker(dashboard.tone_combo):
                dashboard.tone_combo.setCurrentText(new_key)
        dashboard.current_tone = new_key
        key_midi_map = backend.AppConfig.get_key_midi_map()
        key_midi = key_midi_map.get(new_key, 0)
        dashboard.engine.send_midi(dashboard.MIDI_CC["key_root"], key_midi)
        print(f"[KEY] {label} -> {base} -> {new_key} (MIDI {key_midi})")

    def _apply_value(new_val):
        new_val = max(-12, min(12, new_val))
        old_val = _current[0]
        if new_val == old_val:
            return
        _current[0] = new_val
        sign = "+" if new_val >= 0 else ""
        val_lbl.setText(f"{sign}{new_val}")
        midi_value = int(((new_val + 12) / 24) * 127)
        dashboard.engine.send_midi(dashboard.MIDI_CC[cc_key], midi_value)
        if cc_key == "tone_music":
            delta = new_val - old_val
            dashboard.tone_music_value = new_val
            if delta != 0:
                _shift_key_midi(delta)
        else:
            dashboard.tone_voice_value = new_val

    btn_minus.clicked.connect(lambda: _apply_value(_current[0] - 1))
    btn_plus.clicked.connect(lambda: _apply_value(_current[0] + 1))

    return wrapper


def build_panel_tools(dashboard) -> GlassPanel:
    panel = GlassPanel("TOOLS")
    panel.body_layout.addSpacing(6)

    # Thanh tìm kiếm YouTube — chỉ hiện khi dùng màn hình karaoke nhúng (bản Heavy)
    if hasattr(dashboard, "_embedded_player_enabled") and dashboard._embedded_player_enabled():
        panel.body_layout.addWidget(_build_search_bar(dashboard))
        panel.body_layout.addSpacing(8)

    grid = QGridLayout()
    grid.setSpacing(3)

    ui_config = backend.UiConfigManager.load_ui_config()
    tools_config = ui_config.get("tools", [])

    func_btns = []
    for t_cfg in tools_config:
        if t_cfg.get("hidden", False):
            continue
        
        text = t_cfg.get("label", "Unknown")
        c_val = t_cfg.get("color", "#ffffff")
        if c_val in C:
            c_val = C[c_val]
            
        action_name = t_cfg.get("action", "")
        cc_val = t_cfg.get("cc")
        # Dev-mode override: nếu entry có CC dạng SỐ → gửi thẳng CC đó và bỏ qua
        # action built-in. Cho phép kỹ thuật viên map lại cả nút có sẵn.
        if isinstance(cc_val, int):
            cb = None
        else:
            cb = getattr(dashboard, f"_on_{action_name}", None)
        if not cb:
            # Không có method built-in (hoặc bị CC số override) → gửi CC thô
            on_val = t_cfg.get("on_value", 127)
            off_val = t_cfg.get("off_value", 0)
            is_toggle = t_cfg.get("is_toggle", False)

            # Use default args pattern to avoid late binding issues in loops
            def make_custom_cb(c=cc_val, on=on_val, off=off_val, toggle=is_toggle, text_key=text):
                def _do_action():
                    btn = dashboard._func_buttons.get(text_key)
                    if btn and toggle:
                        # Toggle: đọc/ghi cùng thuộc tính _active mà setActive dùng
                        # (trước đây đọc nhầm "_is_active" → luôn gửi On, không gửi Off)
                        is_active = not getattr(btn, "_active", False)
                        btn.setActive(is_active)
                        val = on if is_active else off
                    else:
                        # Momentary: chỉ gửi On Value
                        val = on
                    dashboard.engine.send_midi(c, val)
                return _do_action

            cb = make_custom_cb()
            
        desc = t_cfg.get("desc", "")
        func_btns.append((text, c_val, cb, desc, t_cfg))
        
    for i, (text, color, cb, desc, t_cfg) in enumerate(func_btns):
        btn = PainterButton(text, color=color, height=26, radius=8, font_size=9)
        btn.setToolTip(desc)
        btn.setAccessibleName(text)
        btn.clicked.connect(cb)
        grid.addWidget(btn, i // 2, i % 2)
        dashboard._func_buttons[text] = btn
        
        # Set initial active state for toggles
        if text == "Auto-Tune":
            btn.setActive(getattr(dashboard, "tune_state", True))
        elif text == "Fix Méo":
            btn.setActive(getattr(dashboard, "fix_meo_state", False))
        elif text == "Bè":
            btn.setActive(getattr(dashboard, "be_state", False))
        elif text == "Tắt Ồn":
            btn.setActive(getattr(dashboard, "tat_on_state", False))
            
        # --- Dev Mode Context Menu ---
        if getattr(dashboard, "is_dev_mode", False):
            # KHÔNG import Qt cục bộ ở đây — sẽ shadow import module-level
            # và gây UnboundLocalError ở mọi chỗ dùng Qt trong hàm này.
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            
            def make_ctx_cb(cfg=t_cfg, b=btn):
                def show_ctx(pos):
                    from PySide6.QtWidgets import QMenu
                    from PySide6.QtGui import QAction
                    menu = QMenu(b)
                    menu.setStyleSheet("QMenu { background: #1e1e1e; color: white; }")
                    
                    edit_act = QAction("Sửa", menu)
                    edit_act.triggered.connect(lambda: dashboard._on_edit_widget("tools", cfg))
                    
                    hide_act = QAction("Ẩn", menu)
                    hide_act.triggered.connect(lambda: dashboard._on_hide_widget("tools", cfg))
                    
                    menu.addAction(edit_act)
                    menu.addAction(hide_act)
                    menu.exec(b.mapToGlobal(pos))
                return show_ctx
                
            btn.customContextMenuRequested.connect(make_ctx_cb())

    panel.body_layout.addLayout(grid)
    
    # --- Dev Mode Add Button ---
    if getattr(dashboard, "is_dev_mode", False):
        from PySide6.QtWidgets import QPushButton
        add_btn = QPushButton("+ Thêm Nút")
        add_btn.setStyleSheet(f"background-color: transparent; border: 1px dashed {C['teal']}; color: {C['teal']};")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(lambda: dashboard._on_add_widget("tools", "button"))
        panel.body_layout.addWidget(add_btn)
        
    panel.body_layout.addSpacing(16)

    hl = QHBoxLayout()
    hl.setContentsMargins(0, 0, 0, 0)
    hl.setSpacing(0)
    hl.addStretch(1)
    hl.addWidget(_build_tone_knob_widget(dashboard, "Tone Nhạc", "tone_music", C["teal"]))
    hl.addSpacing(16)

    div = QFrame()
    div.setFrameShape(QFrame.VLine)
    div.setFixedHeight(28)
    div.setStyleSheet(
        f"color:{C['border']}; background:{C['border']}; border:none; min-width:1px; max-width:1px;"
    )
    hl.addWidget(div, 0, Qt.AlignVCenter)

    hl.addSpacing(16)
    hl.addWidget(_build_tone_knob_widget(dashboard, "Tone Giọng", "tone_voice", C["accent"]))
    hl.addStretch(1)

    panel.body_layout.addLayout(hl)
    panel.body_layout.addStretch()
    return panel
