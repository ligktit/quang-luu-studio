"""Dev Mode trên panel: hàng nút "+ Thêm…"/"⚙ Quản lý" và menu chuột phải Sửa/Ẩn."""
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


def attach_dev_ctx_menu(dashboard, panel_name, widget, cfg):
    """Menu chuột phải Sửa/Ẩn cho `widget`, nhắm đúng entry `cfg` của nó.

    Gọi một lần cho mỗi widget lúc dựng panel — `cfg` và `widget` được giữ
    theo lời gọi, không phụ thuộc biến vòng lặp của panel.
    """
    widget.setContextMenuPolicy(Qt.CustomContextMenu)

    def show_ctx(pos):
        # Import lúc chạy (không ở đầu module) để test thay được QMenu.
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction
        menu = QMenu(widget)
        menu.setStyleSheet("QMenu { background: #1e1e1e; color: white; }")

        edit_act = QAction("Sửa", menu)
        edit_act.triggered.connect(lambda: dashboard._on_edit_widget(panel_name, cfg))

        hide_act = QAction("Ẩn", menu)
        hide_act.triggered.connect(lambda: dashboard._on_hide_widget(panel_name, cfg))

        menu.addAction(edit_act)
        menu.addAction(hide_act)
        menu.exec(widget.mapToGlobal(pos))

    widget.customContextMenuRequested.connect(show_ctx)
