# -*- coding: utf-8 -*-
"""Thông báo tạm (_show_message) phải hiện ở nơi người dùng đang nhìn.

Bối cảnh lỗi thật: mọi hộp thoại (Danh sách bài, Sửa bài, Thiết lập) mở bằng
exec() — cửa sổ modal đè lên dashboard. Toast vẽ lên dashboard thì nằm khuất
sau hộp thoại: người dùng bấm Lưu, thấy im lìm, tưởng app không làm gì.
"""
import pytest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QFrame

from frontend_qt import MainDashboard


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def host(qapp, qtbot):
    """Cửa sổ đóng vai dashboard — _show_message chỉ cần một QWidget."""
    w = QWidget()
    w.resize(900, 600)
    qtbot.addWidget(w)
    return w


def _labels(w):
    return [c for c in w.findChildren(QLabel)]


def test_khong_co_modal_thi_toast_nam_tren_dashboard(host):
    with patch("frontend_qt.QApplication.activeModalWidget", return_value=None):
        MainDashboard._show_message(host, "Đã lưu thiết lập")
    lbls = _labels(host)
    assert len(lbls) == 1
    assert lbls[0].parent() is host
    assert lbls[0].text() == "Đã lưu thiết lập"


def test_dang_mo_hop_thoai_thi_toast_nam_tren_hop_thoai(host, qtbot):
    dlg = QWidget()
    dlg.resize(500, 400)
    qtbot.addWidget(dlg)
    with patch("frontend_qt.QApplication.activeModalWidget", return_value=dlg):
        MainDashboard._show_message(host, "Đã lưu 5 mốc thời gian")
    assert not _labels(host), "toast bị vẽ sau lưng hộp thoại"
    lbls = _labels(dlg)
    assert len(lbls) == 1 and lbls[0].parent() is dlg


def test_cau_dai_thi_xuong_dong_va_o_lau_hon(host):
    ngan = "Đã lưu"
    dai = "Chưa ai trong mạng lưới dò 12 bài này, bạn dò một lần là cả mạng lưới dùng được"
    with patch("frontend_qt.QApplication.activeModalWidget", return_value=None):
        MainDashboard._show_message(host, ngan)
        MainDashboard._show_message(host, dai)
    lbl_ngan = [l for l in _labels(host) if l.text() == ngan][0]
    lbl_dai = [l for l in _labels(host) if l.text() == dai][0]

    assert lbl_dai.wordWrap(), "câu dài phải xuống dòng thay vì tràn ngang"
    assert lbl_dai.width() <= int(host.width() * 0.8) + 1

    def _interval(lbl):
        from PySide6.QtCore import QTimer
        timers = lbl.findChildren(QTimer)
        assert timers, "thiếu timer tự đóng"
        return timers[0].interval()

    assert _interval(lbl_dai) > _interval(lbl_ngan)
    assert _interval(lbl_dai) <= 5000


def test_toast_loi_cung_bam_theo_hop_thoai(host, qtbot):
    dlg = QWidget()
    dlg.resize(500, 400)
    qtbot.addWidget(dlg)
    with patch("frontend_qt.QApplication.activeModalWidget", return_value=dlg):
        MainDashboard._show_message(host, "Không lưu được thiết lập", is_error=True)
    def _panels(w):
        # QLabel cũng là QFrame — lọc theo tên trợ năng của panel lỗi.
        return [f for f in w.findChildren(QFrame)
                if f.accessibleName() == "Thông báo lỗi"]

    assert not _panels(host), "panel lỗi bị vẽ sau lưng hộp thoại"
    assert len(_panels(dlg)) == 1
