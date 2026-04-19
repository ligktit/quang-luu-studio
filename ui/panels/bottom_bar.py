"""Bottom bar builder for MainDashboard."""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QFrame, QGraphicsDropShadowEffect
from PySide6.QtGui import QColor

from ui.design_tokens import C, SP
from ui.components.painter_button import PainterButton
from ui.components.painter_record import PainterRecordButton
from ui.components.svg_icons import SVG_STAR, SVG_LIST, SVG_SAVE, SVG_FOLDER


def build_bottom_bar(dashboard) -> QWidget:
    wrapper = QWidget()
    wrapper.setStyleSheet(f"background-color: {C['bg']};")
    wrapper_layout = QHBoxLayout(wrapper)
    wrapper_layout.setContentsMargins(SP.LG, SP.XS, SP.LG, SP.SM)

    bar = QFrame()
    bar.setStyleSheet("""
        background-color: rgba(30, 41, 59, 230);
        border-radius: 22px;
        border: 1px solid rgba(51, 65, 85, 0.4);
    """)
    shadow = QGraphicsDropShadowEffect()
    shadow.setColor(QColor("#000000"))
    shadow.setBlurRadius(15)
    shadow.setOffset(0, -2)
    bar.setGraphicsEffect(shadow)

    bar_layout = QHBoxLayout(bar)
    bar_layout.setContentsMargins(SP.MD, 6, SP.MD, 6)
    bar_layout.setSpacing(10)

    btn_save = PainterButton(
        "", color=C["teal"], height=34, radius=8,
        font_size=10, svg_content=SVG_SAVE, svg_size=18, fixed_width=38,
    )
    btn_save.setToolTip("Lưu")
    btn_save.clicked.connect(dashboard._on_save)
    bar_layout.addWidget(btn_save)
    dashboard._func_buttons["💾 Lưu"] = btn_save

    btn_list = PainterButton(
        "", color=C["orange"], height=34, radius=8,
        font_size=10, svg_content=SVG_LIST, svg_size=18, fixed_width=38,
    )
    btn_list.setToolTip("Danh sách")
    btn_list.clicked.connect(dashboard._show_songs_list)
    bar_layout.addWidget(btn_list)
    dashboard._func_buttons["Danh sách"] = btn_list

    bar_layout.addStretch()

    dashboard.record_button = PainterRecordButton()
    dashboard.record_button.clicked.connect(dashboard._on_record)
    bar_layout.addWidget(dashboard.record_button)

    bar_layout.addStretch()

    btn_score = PainterButton(
        "", color=C["light_purple"], height=34, radius=8,
        font_size=10, svg_content=SVG_STAR, svg_size=18, fixed_width=38,
    )
    btn_score.setToolTip("Chấm điểm")
    btn_score.clicked.connect(dashboard._on_score)
    bar_layout.addWidget(btn_score)
    dashboard._func_buttons["Chấm điểm"] = btn_score

    btn_folder = PainterButton(
        "", color=C["light_purple"], height=34, radius=8,
        font_size=10, svg_content=SVG_FOLDER, svg_size=18, fixed_width=38,
    )
    btn_folder.setToolTip("Thư mục")
    btn_folder.clicked.connect(dashboard._on_open_recordings_folder)
    bar_layout.addWidget(btn_folder)
    dashboard._func_buttons["Thư Mục"] = btn_folder

    wrapper_layout.addWidget(bar)
    return wrapper
