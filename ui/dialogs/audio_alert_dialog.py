"""Cửa sổ cảnh báo Tự sửa âm thanh — dành cho KHÁCH HÁT.

Lượt kiểm tra lúc mở app thấy lỗi thì bật cửa sổ này: nói rõ lỗi gì, một nút lớn
"Tự sửa". Thay cho dải cảnh báo cũ chen trong header (chiếm chỗ marquee, câu bị cắt
cụt trên màn 1366×768).

Không chặn app (non-modal) và nổi trên cùng: lượt kiểm tra chạy khi DAW vừa sẵn
sàng, DAW hay giành tiền cảnh đúng lúc đó.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ui import responsive as rp
from ui.design_tokens import C, FONT, lighten


def _btn_qss(color: str, text: str = "#0F172A") -> str:
    return f"""
        QPushButton {{
            background-color: {color}; color: {text};
            border: none; border-radius: 12px;
            padding: 12px 22px; font-size: 18px; font-weight: 800;
            font-family: {FONT};
        }}
        QPushButton:hover {{ background-color: {lighten(color, 0.12)}; }}
    """.strip()


class AudioAlertDialog(QDialog):
    def __init__(self, dashboard):
        super().__init__(dashboard)
        self._dashboard = dashboard
        self.setWindowTitle("Cảnh báo âm thanh")
        self.setModal(False)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setAccessibleName("Cảnh báo âm thanh")
        self.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']}; font-family: {FONT};")
        rp.set_min_width(self, 460)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        self.title_label = QLabel("")
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet(
            f"font-size: 22px; font-weight: 900; color: {C['orange']}; background: transparent;")
        root.addWidget(self.title_label)

        self.list_label = QLabel("")
        self.list_label.setWordWrap(True)
        self.list_label.setTextFormat(Qt.PlainText)
        self.list_label.setStyleSheet(
            f"font-size: 18px; font-weight: 600; color: {C['text']}; background: transparent;")
        root.addWidget(self.list_label)

        btns = QHBoxLayout()
        btns.setSpacing(10)
        self.fix_btn = QPushButton("Tự sửa")
        self.fix_btn.setCursor(Qt.PointingHandCursor)
        self.fix_btn.setStyleSheet(_btn_qss(C["orange"]))
        self.fix_btn.setDefault(True)
        self.later_btn = QPushButton("Để sau")
        self.later_btn.setCursor(Qt.PointingHandCursor)
        self.later_btn.setStyleSheet(_btn_qss(C["card_hover"], C["text"]))
        btns.addWidget(self.fix_btn, 2)
        btns.addWidget(self.later_btn, 1)
        root.addLayout(btns)

        self.fix_btn.clicked.connect(self._on_fix)
        self.later_btn.clicked.connect(self.close)

    def set_report(self, report):
        messages = [f.message for _, f in report.problems()]
        self.title_label.setText(f"Phát hiện {len(messages)} vấn đề âm thanh")
        self.list_label.setText("\n".join(f"• {m}" for m in messages))
        self.setAccessibleDescription(". ".join(messages))
        self.adjustSize()

    def show_on_top(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_fix(self):
        self.close()
        self._dashboard._open_audio_doctor()
