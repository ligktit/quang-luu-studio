"""Ô bị khoá trong Thiết lập phải NHÌN RA là đang khoá.

Vì sao có bài kiểm tra này: QSS đặt `color`/`border` không kèm trạng thái sẽ đè
luôn cả lúc widget bị disable, nên ô khoá vẽ ra y hệt ô dùng được. Khách bấm mãi
không tick được (bản Light không có màn hình nhúng, hoặc chế độ khách đang khoá)
rồi báo "app lỗi". Bài này so ảnh vẽ thật của hai trạng thái — nếu ai đó lỡ xoá
luật `:disabled` thì hai ảnh trùng nhau và test đỏ.
"""
import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox

from ui.dialogs.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _render(widget):
    widget.setStyleSheet(widget.styleSheet())   # ép áp lại QSS trước khi vẽ
    widget.resize(QSize(320, 40))
    pix = QPixmap(widget.size())
    pix.fill()
    widget.render(pix)
    return pix.toImage()


def _khac_nhau(make):
    on, off = make(), make()
    off.setEnabled(False)
    return _render(on) != _render(off)


def test_checkbox_bi_khoa_trong_khac_han_checkbox_dung_duoc(qapp):
    def make():
        cb = QCheckBox("Phát YouTube trong màn hình karaoke nhúng (sạch)")
        cb.setStyleSheet(SettingsDialog._checkbox_qss)
        return cb
    assert _khac_nhau(make), "ô khoá vẽ giống hệt ô thường — khách không thể biết"


def test_checkbox_da_tick_ma_bi_khoa_cung_khac(qapp):
    def make():
        cb = QCheckBox("Ẩn lại cả khi khách tự mở Studio One")
        cb.setStyleSheet(SettingsDialog._checkbox_qss)
        cb.setChecked(True)
        return cb
    assert _khac_nhau(make)


def test_combobox_bi_khoa_cung_phai_nhin_ra(qapp):
    def make():
        cb = QComboBox()
        cb.addItem("Màn 1: chính")
        cb.setStyleSheet(SettingsDialog._combo_qss)
        return cb
    assert _khac_nhau(make)


def test_qss_khong_co_loi_cu_phap(qapp):
    """Qt nuốt QSS sai cú pháp trong im lặng — chỉ mất hiệu lực chứ không báo.
    Kiểm bằng cách: màu chữ đọc ra phải đúng màu đã khai trong QSS."""
    from ui.design_tokens import C

    cb = QCheckBox("x")
    cb.setStyleSheet(SettingsDialog._checkbox_qss)
    cb.ensurePolished()
    got = cb.palette().color(cb.foregroundRole()).name().lower()
    assert got == C["text"].lower(), f"QSS khong duoc ap dung (mau {got})"
