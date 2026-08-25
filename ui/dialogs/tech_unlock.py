"""
Quang Lưu Studio — Hộp thoại khoá kỹ thuật.

TechUnlockDialog : nhập PIN để mở phiên kỹ thuật (hiện lại Studio One).
SetPinDialog     : đặt / đổi PIN kỹ thuật.

Tự chứa về style (chỉ dùng design_tokens) để không kéo theo frontend_qt — hộp
thoại này phải mở được cả từ header lẫn từ dialog Thiết lập.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFrame,
)
from PySide6.QtCore import Qt, QTimer

from ui.design_tokens import C, FONT, lighten
from core import kiosk


def _pill_btn_qss(color: str, radius: int = 12, size: int = 13) -> str:
    return f"""
        QPushButton {{
            background-color: {color}; color: #0F172A;
            border: none; border-radius: {radius}px;
            padding: 9px 16px; font-size: {size}px; font-weight: 700;
            font-family: {FONT};
        }}
        QPushButton:hover {{ background-color: {lighten(color, 0.12)}; }}
        QPushButton:disabled {{ background-color: {C['card_hover']}; color: {C['text_muted']}; }}
    """.strip()


_PIN_INPUT_QSS = f"""
    QLineEdit {{
        background-color: rgba(15, 23, 42, 225);
        color: {C['text']};
        border: 1px solid rgba(148, 163, 184, 55);
        border-radius: 11px;
        padding: 10px 14px;
        font-size: 20px;
        font-weight: 700;
        letter-spacing: 6px;
        font-family: {FONT};
    }}
    QLineEdit:focus {{ border-color: {C['teal']}; }}
"""


class _BaseTechDialog(QDialog):
    """Khung chung: tiêu đề, mô tả, dòng trạng thái, hàng nút."""

    def __init__(self, parent, title, subtitle):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setFixedWidth(430)
        self.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(24, 20, 24, 18)
        self._root.setSpacing(12)

        head = QLabel(title)
        head.setStyleSheet(
            f"font-size: 18px; font-weight: 900; color: {C['text']};"
            f" font-family: {FONT}; background: transparent;"
        )
        self._root.addWidget(head)

        sub = QLabel(subtitle)
        sub.setWordWrap(True)
        sub.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {C['text_muted']};"
            f" font-family: {FONT}; background: transparent;"
        )
        self._root.addWidget(sub)

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background-color: {C['border']}; border: none;")
        self._root.addWidget(line)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {C['orange']};"
            f" font-family: {FONT}; background: transparent;"
        )
        self._status.setVisible(False)

    def _new_pin_input(self, placeholder):
        inp = QLineEdit()
        inp.setEchoMode(QLineEdit.Password)
        inp.setPlaceholderText(placeholder)
        inp.setStyleSheet(_PIN_INPUT_QSS)
        inp.setMaxLength(32)
        inp.setAlignment(Qt.AlignCenter)
        return inp

    def _show_status(self, text, color=None):
        self._status.setText(text)
        self._status.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {color or C['orange']};"
            f" font-family: {FONT}; background: transparent;"
        )
        self._status.setVisible(True)

    def _button_row(self, ok_text, ok_color, on_ok):
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addStretch()
        cancel = QPushButton("Huỷ")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.setStyleSheet(_pill_btn_qss(C["card_hover"]))
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        ok = QPushButton(ok_text)
        ok.setCursor(Qt.PointingHandCursor)
        ok.setStyleSheet(_pill_btn_qss(ok_color))
        ok.setDefault(True)
        ok.clicked.connect(on_ok)
        row.addWidget(ok)
        return row, ok


class TechUnlockDialog(_BaseTechDialog):
    """Nhập PIN để mở phiên kỹ thuật.

    Nhập sai nhiều lần bị khoá tạm (core.kiosk đếm trong RAM) — bộ đếm sống theo
    tiến trình app nên khách không thể dò bằng cách bấm mãi.
    """

    def __init__(self, parent=None):
        super().__init__(
            parent,
            "Mở khoá kỹ thuật",
            "Nhập mã PIN kỹ thuật để hiện lại Studio One. "
            f"Phiên tự khoá lại sau {kiosk.session_minutes()} phút hoặc khi đóng app.",
        )
        self._pin = self._new_pin_input("Mã PIN")
        self._pin.returnPressed.connect(self._try_unlock)
        self._root.addWidget(self._pin)
        self._root.addWidget(self._status)

        row, self._ok_btn = self._button_row("Mở khoá", C["teal"], self._try_unlock)
        self._root.addLayout(row)

        self._countdown = QTimer(self)
        self._countdown.timeout.connect(self._tick_lockout)
        self._countdown.start(1000)
        self._tick_lockout()

    def _tick_lockout(self):
        remain = kiosk.lockout_remaining()
        if remain > 0:
            self._pin.setEnabled(False)
            self._ok_btn.setEnabled(False)
            self._show_status(f"Nhập sai quá nhiều — thử lại sau {remain} giây", C["accent"])
        else:
            self._pin.setEnabled(True)
            self._ok_btn.setEnabled(True)
            if self._status.text().startswith("Nhập sai quá nhiều"):
                self._status.setVisible(False)
            self._pin.setFocus()

    def _try_unlock(self):
        if kiosk.lockout_remaining() > 0:
            return
        pin = self._pin.text()
        if kiosk.verify_pin(pin):
            kiosk.start_session()
            self.accept()
            return
        self._pin.clear()
        cooldown = kiosk.register_failure()
        if cooldown:
            self._tick_lockout()
        else:
            self._show_status("Mã PIN không đúng", C["accent"])


class SetPinDialog(_BaseTechDialog):
    """Đặt hoặc đổi PIN kỹ thuật. Đã có PIN thì phải nhập PIN cũ trước."""

    def __init__(self, parent=None):
        changing = kiosk.has_pin()
        super().__init__(
            parent,
            "Đổi mã PIN kỹ thuật" if changing else "Đặt mã PIN kỹ thuật",
            "PIN được lưu dạng băm PBKDF2 — không ai đọc lại được từ file cấu hình. "
            "Quên PIN thì phải xoá mục \"tech_lock\" trong settings.json.",
        )
        self._changing = changing

        self._old = None
        if changing:
            self._root.addWidget(self._field_label("Mã PIN hiện tại"))
            self._old = self._new_pin_input("PIN cũ")
            self._root.addWidget(self._old)

        self._root.addWidget(self._field_label("Mã PIN mới (tối thiểu 4 ký tự)"))
        self._pin1 = self._new_pin_input("PIN mới")
        self._root.addWidget(self._pin1)

        self._root.addWidget(self._field_label("Nhập lại mã PIN mới"))
        self._pin2 = self._new_pin_input("Nhập lại")
        self._pin2.returnPressed.connect(self._try_save)
        self._root.addWidget(self._pin2)

        self._root.addWidget(self._status)
        row, _ = self._button_row("Lưu PIN", C["green"], self._try_save)
        self._root.addLayout(row)

    def _field_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-size: 11px; font-weight: 800; color: {C['text_muted']};"
            f" font-family: {FONT}; background: transparent;"
        )
        return lbl

    def _try_save(self):
        if self._changing and not kiosk.verify_pin(self._old.text()):
            self._show_status("Mã PIN hiện tại không đúng", C["accent"])
            return
        if self._pin1.text() != self._pin2.text():
            self._show_status("Hai lần nhập không khớp", C["accent"])
            return
        try:
            kiosk.set_pin(self._pin1.text())
        except ValueError as e:
            self._show_status(str(e), C["accent"])
            return
        self.accept()
