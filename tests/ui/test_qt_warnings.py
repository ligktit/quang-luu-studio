"""Không để Qt in cảnh báo ra console khi dùng UI (QFont / QWindowsWindow).

Hai cảnh báo này chỉ xuất hiện trên Windows với cửa sổ native thật; trên nền
tảng khác test vẫn chạy nhưng không có gì để bắt.
"""
import pytest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QComboBox, QWidget, QVBoxLayout

from core.config import DEFAULT_MODE_CONFIG, DEFAULT_TOGGLE_INVERT


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def app_qss(qapp):
    """Áp QSS toàn app như lúc chạy thật, trả lại như cũ sau test."""
    from ui.design_tokens import load_qss
    old = qapp.styleSheet()
    qapp.setStyleSheet(load_qss())
    yield
    qapp.setStyleSheet(old)


@pytest.fixture
def cfg():
    modes = {k: dict(v) for k, v in DEFAULT_MODE_CONFIG.items()}
    invert = dict(DEFAULT_TOGGLE_INVERT)
    with patch("core.config.AppConfig.get_mode_config", return_value=modes), \
         patch("core.config.AppConfig.get_toggle_invert", return_value=invert):
        yield modes, invert


def _messages(qtlog):
    return [r.message for r in qtlog.records]


def test_combobox_mo_popup_khong_canh_bao_qfont(qapp, qtbot, qtlog, app_qss):
    """Style windows11 của Qt gọi QFont::setPointSize với pointSize của combobox;
    QSS đặt font-size bằng px thì pointSize = -1 → 'Point size <= 0 (-1)'."""
    host = QWidget()
    qtbot.addWidget(host)
    lay = QVBoxLayout(host)
    combo = QComboBox()
    combo.addItems(["Công tắc", "Phần trăm"])
    lay.addWidget(combo)
    host.show()
    qtbot.waitExposed(host)

    combo.showPopup()
    qtbot.wait(250)
    combo.hidePopup()

    bad = [m for m in _messages(qtlog) if "setPointSize" in m]
    assert bad == [], bad


def test_widget_builder_doi_kieu_khong_canh_bao_geometry(qapp, qtbot, qtlog, cfg):
    """Đổi CC / Kiểu tham số làm layout đổi chiều cao tối thiểu; nhãn ghi chú
    xuống dòng (heightForWidth) khiến Qt ép cỡ hai lần lệch nhau →
    'QWindowsWindow::setGeometry: Unable to set geometry'."""
    from ui.dialogs.widget_builder import WidgetBuilderDialog

    dlg = WidgetBuilderDialog(None, panel_name="tools", widget_type="slider")
    qtbot.addWidget(dlg)
    dlg.show()
    qtbot.waitExposed(dlg)

    dlg.type_combo.setCurrentText("button")
    qtbot.wait(150)
    dlg.cc_input.setValue(20)
    qtbot.wait(150)
    for i in range(dlg.so_type_combo.count()):
        dlg.so_type_combo.setCurrentIndex(i)
        qtbot.wait(150)
    dlg.type_combo.setCurrentText("slider")
    qtbot.wait(150)

    bad = [m for m in _messages(qtlog) if "QWindowsWindow::setGeometry" in m]
    assert bad == [], bad
