"""Nút MODE: tắt = viền mỏng trên nền tối, bật = đổ đầy màu mode + phát sáng.

Trước đây nút luôn tô màu đậm dù bật hay tắt, "đang bật" chỉ là một chấm trắng
4px ở góc — nhìn từ xa không phân biệt được. Test lấy mẫu điểm ảnh thật của nút
để giữ đúng tương phản đó.
"""
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QWidget

MODE_COLOR = "#14B8A6"   # teal như nút Lofi
HOST_BG = "#0F172A"


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _make_button(qtbot, active):
    from ui.components.mode_button import ModeToggleButton
    host = QWidget()
    host.setStyleSheet(f"background-color: {HOST_BG};")
    host.setAutoFillBackground(True)
    lay = QHBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    btn = ModeToggleButton("Lofi", color=MODE_COLOR)
    btn.setActive(active)
    lay.addWidget(btn)
    host.resize(140, btn.height())
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)
    return host, btn


def _sample(host, btn, x_frac, y_frac):
    """Màu điểm ảnh của nút (toạ độ tương đối 0..1) sau khi vẽ lên nền tối."""
    img = host.grab().toImage()
    x = btn.x() + int(btn.width() * x_frac)
    y = btn.y() + int(btn.height() * y_frac)
    return QColor(img.pixel(x, y))


def test_nut_bat_do_day_mau_mode(qapp, qtbot):
    host, btn = _make_button(qtbot, active=True)
    px = _sample(host, btn, 0.12, 0.5)     # trong thân nút, trước chữ và LED
    target = QColor(MODE_COLOR)
    assert px.hsvSaturationF() > 0.45, px.name()
    assert abs(px.hsvHue() - target.hsvHue()) < 25, (px.name(), target.name())


def test_nut_tat_nen_toi_chi_con_vien(qapp, qtbot):
    host, btn = _make_button(qtbot, active=False)
    body = _sample(host, btn, 0.12, 0.5)   # giữa thân nút
    assert body.valueF() < 0.35, body.name()     # gần như nền tối, không tô màu
    edge = _sample(host, btn, 0.5, 0.0)    # mép trên: đường viền màu mode
    assert edge.hsvSaturationF() > 0.3, edge.name()


def test_nut_bat_sang_hon_nut_tat_ro_ret(qapp, qtbot):
    """Khoảng cách màu giữa hai trạng thái phải lớn — đây là mục đích của việc đổi."""
    host_on, on = _make_button(qtbot, active=True)
    host_off, off = _make_button(qtbot, active=False)
    a = _sample(host_on, on, 0.12, 0.5)
    b = _sample(host_off, off, 0.12, 0.5)
    dist = abs(a.red() - b.red()) + abs(a.green() - b.green()) + abs(a.blue() - b.blue())
    assert dist > 200, (a.name(), b.name())


def test_mo_ta_tro_nang_doi_theo_trang_thai(qapp, qtbot):
    from ui.components.mode_button import ModeToggleButton
    btn = ModeToggleButton("Remix", color="#F97316")
    qtbot.addWidget(btn)
    btn.setActive(True)
    assert "Đang bật" in btn.accessibleDescription()
    btn.setActive(False)
    assert "Đang tắt" in btn.accessibleDescription()


def test_panel_mode_dung_nut_moi(qapp, qtbot):
    from frontend_qt import MainDashboard
    from ui.components.mode_button import ModeToggleButton
    base = {"studio_one_path": "", "auto_close_studio_one": False}
    with patch("frontend_qt.backend.SystemEngine") as mock_eng, \
         patch("frontend_qt.backend.SongManager.load_songs", return_value=[]), \
         patch("frontend_qt.backend.ActivationManager.is_activated", return_value=True), \
         patch("frontend_qt.backend.ActivationManager.needs_activation", return_value=False), \
         patch("frontend_qt.QTimer.start"):
        eng = mock_eng.return_value
        eng.current_youtube_url = ""
        eng.tone_detection_active = False
        eng.autokey_active = False
        eng._tone_session = MagicMock()
        eng._tone_session.is_active = False
        dashboard = MainDashboard(base)
        qtbot.addWidget(dashboard)
        if dashboard._so_ready_watcher is not None:
            dashboard._so_ready_watcher.stop()
    assert dashboard._mode_buttons
    for label, btn in dashboard._mode_buttons.items():
        assert isinstance(btn, ModeToggleButton), label
