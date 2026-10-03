"""Dải "ĐANG BẬT" — điểm danh mode + nút chức năng đang bật.

Dải này KHÔNG đi theo gói Premium: dải visualizer là của Premium và tắt được
trong Thiết lập, còn dải trạng thái thì bản nào cũng phải thấy. Test đầu tiên
giữ đúng điều đó.
"""
from unittest.mock import MagicMock, patch

import pytest

from frontend_qt import MainDashboard


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def mock_engine():
    with patch("frontend_qt.backend.SystemEngine") as mock_eng:
        eng = mock_eng.return_value
        eng.current_youtube_url = "http://yt.com"
        eng.tone_detection_active = False
        eng.autokey_active = False
        eng._tone_session = MagicMock()
        eng._tone_session.is_active = False
        yield eng


def _make_dashboard(qtbot, premium=False):
    base = {"studio_one_path": "", "auto_close_studio_one": False}
    with patch("frontend_qt.backend.SongManager.load_songs", return_value=[]), \
         patch("frontend_qt.backend.ActivationManager.is_activated", return_value=True), \
         patch("frontend_qt.backend.ActivationManager.needs_activation", return_value=False), \
         patch("core.entitlements.is_premium", return_value=premium), \
         patch("frontend_qt.QTimer.start"):
        dashboard = MainDashboard(base)
        qtbot.addWidget(dashboard)
        if dashboard._so_ready_watcher is not None:
            dashboard._so_ready_watcher.stop()
        return dashboard


def _labels(dashboard):
    return [label for label, _ in dashboard._active_bar.items()]


def test_ban_standard_khong_co_visualizer_van_co_dai(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot, premium=False)
    assert dashboard._premium_viz is None      # không phải Premium → không có dải sóng
    assert dashboard._active_bar is not None   # nhưng dải trạng thái vẫn còn


def _tat_het(dashboard):
    """Tắt mọi thứ có thể bật — về đúng trạng thái 'không có gì chạy'."""
    for mode in list(dashboard.mode_states):
        dashboard._set_mode(mode, False)
    if dashboard.tune_state:
        dashboard._on_tone_auto()
    if dashboard.fix_meo_state:
        dashboard._on_fix_meo()
    if dashboard.be_state:
        dashboard._on_be()
    dashboard._set_tat_on(False, speak=False)
    dashboard.mute_states["mix_reverb"] = False
    dashboard._refresh_active_bar()


def test_khong_bat_gi_thi_dai_an_han(qapp, mock_engine, qtbot):
    """Ẩn = biến khỏi bố cục để panel dịch lên, không phải để dải trống."""
    dashboard = _make_dashboard(qtbot)
    _tat_het(dashboard)
    assert dashboard._active_bar.items() == []
    assert dashboard._active_bar.isHidden()


def test_bat_lai_mot_mode_thi_dai_hien_lai(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot)
    _tat_het(dashboard)
    dashboard._set_mode("Lofi", True)
    assert not dashboard._active_bar.isHidden()
    assert _labels(dashboard) == ["Lofi"]


def test_bat_mode_thi_hien_ten(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot)
    dashboard._set_mode("Lofi", True)
    assert "Lofi" in _labels(dashboard)


def test_tat_mode_thi_mat_ten(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot)
    dashboard._set_mode("Lofi", True)
    dashboard._set_mode("Lofi", False)
    assert "Lofi" not in _labels(dashboard)


def test_nhieu_mode_cung_luc_deu_duoc_ke(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot)
    dashboard._set_mode("Lofi", True)
    dashboard._set_mode("Remix", True)
    labels = _labels(dashboard)
    assert "Lofi" in labels and "Remix" in labels


def test_nut_chuc_nang_cung_duoc_diem_danh(qapp, mock_engine, qtbot):
    """Auto-Tune mặc định BẬT nên phải có sẵn; bấm tắt thì phải biến mất."""
    dashboard = _make_dashboard(qtbot)
    assert "Auto-Tune" in _labels(dashboard)
    dashboard._on_tone_auto()
    assert "Auto-Tune" not in _labels(dashboard)


def test_be_va_khu_on(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot)
    dashboard._on_be()
    dashboard._set_tat_on(True, speak=False)
    labels = _labels(dashboard)
    assert "Bè" in labels and "Tắt Ồn" in labels


def test_tat_vang_cung_hien(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot)
    dashboard.mute_states["mix_reverb"] = True
    dashboard._refresh_active_bar()
    assert "Tắt Vang" in _labels(dashboard)


def test_moi_muc_co_mau_rieng(qapp, mock_engine, qtbot):
    """Màu lấy theo đúng màu nút trên panel, không phải màu chung chung."""
    dashboard = _make_dashboard(qtbot)
    dashboard._set_mode("Lofi", True)
    colors = dict(dashboard._active_bar.items())
    assert colors["Lofi"].startswith("#")
