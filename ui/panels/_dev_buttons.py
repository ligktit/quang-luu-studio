"""Hàng nút Dev Mode cuối mỗi panel: "+ Thêm…" và "⚙ Quản lý"."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton

from ui.design_tokens import C


def build_dev_row(dashboard, panel_name, add_text, widget_type, extra_style=""):
    style = (f"background-color: transparent; border: 1px dashed {C['teal']};"
             f" color: {C['teal']};{extra_style}")
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)

    add_btn = QPushButton(add_text)
    add_btn.setStyleSheet(style)
    add_btn.setCursor(Qt.PointingHandCursor)
    add_btn.clicked.connect(lambda: dashboard._on_add_widget(panel_name, widget_type))

    manage_btn = QPushButton("⚙ Quản lý")
    manage_btn.setStyleSheet(style)
    manage_btn.setCursor(Qt.PointingHandCursor)
    manage_btn.setToolTip("Hiện lại widget đã ẩn, đổi thứ tự, xoá, xuất/nhập cấu hình")
    manage_btn.clicked.connect(lambda: dashboard._on_manage_widgets(panel_name))

    row.addWidget(add_btn, 1)
    row.addWidget(manage_btn)
    return row
