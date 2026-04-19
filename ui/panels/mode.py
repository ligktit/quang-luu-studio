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

    mode_config = [
        ("Dân Ca",       C["accent"]),
        ("Lofi",         C["light_purple"]),
        ("Remix",        C["blue"]),
        ("Đa Thể Loại",  C["teal"]),
    ]
    dashboard._mode_colors = {label: color for label, color in mode_config}

    mode_row = QHBoxLayout()
    mode_row.setSpacing(3)
    for mlabel, mcolor in mode_config:
        mbtn = PainterButton(mlabel, color=mcolor, height=26, radius=8, font_size=9)
        mbtn.clicked.connect(lambda m=mlabel: dashboard._on_mode_selected(m))
        mode_row.addWidget(mbtn)
        dashboard._mode_buttons[mlabel] = mbtn
    vl.addLayout(mode_row)

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
