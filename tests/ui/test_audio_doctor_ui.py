from unittest.mock import MagicMock, patch

import pytest

from frontend_qt import MainDashboard
from core.audio_doctor.model import Check, Status, loi, ok, da_sua
from core.audio_doctor.context import DoctorContext
from core.audio_doctor.service import AudioDoctorService


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


def _make_dashboard(qtbot):
    with patch("frontend_qt.backend.SongManager.load_songs", return_value=[]), \
         patch("frontend_qt.backend.ActivationManager.is_activated", return_value=True), \
         patch("frontend_qt.backend.ActivationManager.needs_activation", return_value=False), \
         patch("frontend_qt.QTimer.start"):
        dashboard = MainDashboard()
        qtbot.addWidget(dashboard)
        if dashboard._so_ready_watcher is not None:
            dashboard._so_ready_watcher.stop()
        return dashboard


class _Mic(Check):
    id, group, title = "ch_mic", "daw", "Kênh Mic"
    fixed = False

    def detect(self, ctx):
        return ok("Kênh Mic đang bật") if _Mic.fixed else loi("Kênh Mic đang tắt trong Cubase")

    def fix(self, ctx):
        _Mic.fixed = True
        return da_sua("Đã bật kênh Mic")


class _Ok(Check):
    id, group, title = "loopmidi", "bridge", "Cổng MIDI"

    def detect(self, ctx):
        return ok("ổn")


def _svc(tmp_path):
    _Mic.fixed = False
    ctx = lambda ask=None: DoctorContext(settings={}, daw=None, system=None, win=None, actions=None)
    return AudioDoctorService(ctx, [_Ok(), _Mic()], log_path=tmp_path / "a.log")


def test_dai_canh_bao_hien_loi_nang_nhat_va_an_khi_on(qapp, mock_engine, qtbot, tmp_path):
    dashboard = _make_dashboard(qtbot)
    svc = _svc(tmp_path)
    rep = svc.run("check", "startup")
    with patch.object(dashboard, "_a11y_speak") as speak:
        dashboard._on_audio_doctor_report(rep, "run")
    assert dashboard._audio_warn_btn.isVisibleTo(dashboard)
    assert "Kênh Mic đang tắt" in dashboard._audio_warn_btn.text()
    speak.assert_called_once()
    _Mic.fixed = True
    dashboard._on_audio_doctor_report(svc.run("check", "startup"), "rerun")
    assert not dashboard._audio_warn_btn.isVisibleTo(dashboard)


def test_hop_thoai_tu_sua_va_hien_trang_thai(qapp, mock_engine, qtbot, tmp_path):
    from ui.dialogs.audio_doctor_dialog import AudioDoctorDialog
    dashboard = _make_dashboard(qtbot)
    dlg = AudioDoctorDialog(dashboard, _svc(tmp_path), auto_fix=False)
    qtbot.addWidget(dlg)
    with qtbot.waitSignal(dlg._finished, timeout=5000):
        dlg.start("fix")
    assert dlg.rows["ch_mic"].status is Status.DA_SUA
    assert "Đã bật kênh Mic" in dlg.rows["ch_mic"].msg_label.text()
    assert dlg.rows["loopmidi"].status is Status.OK
    assert "Đã sửa 1" in dlg.summary_label.text()


def test_hop_thoai_nen_toi_chu_sang_va_du_cao(qapp, mock_engine, qtbot, tmp_path):
    """Chạy thật trên Windows: thiếu nền tối thì chữ sáng của theme nằm trên nền
    sáng mặc định — gần như không đọc được; danh sách bị bóp còn hai dòng."""
    from ui.design_tokens import C
    from ui.dialogs.audio_doctor_dialog import AudioDoctorDialog
    dashboard = _make_dashboard(qtbot)
    dlg = AudioDoctorDialog(dashboard, _svc(tmp_path), auto_fix=False)
    qtbot.addWidget(dlg)
    qss = dlg.styleSheet()
    assert f"background-color: {C['bg']}" in qss
    assert f"color: {C['text']}" in qss
    assert dlg.minimumHeight() >= 420


def test_hop_thoai_noi_len_khi_chay_xong(qapp, mock_engine, qtbot, tmp_path):
    """DAW mở xong giữa chừng sẽ che mất hộp thoại — chạy xong phải nổi lên lại."""
    from ui.dialogs.audio_doctor_dialog import AudioDoctorDialog
    dashboard = _make_dashboard(qtbot)
    dlg = AudioDoctorDialog(dashboard, _svc(tmp_path), auto_fix=False)
    qtbot.addWidget(dlg)
    with patch.object(dlg, "raise_") as raise_, patch.object(dlg, "activateWindow") as act:
        with qtbot.waitSignal(dlg._finished, timeout=5000):
            dlg.start("check")
    raise_.assert_called_once()
    act.assert_called_once()


def test_nut_va_phim_tat_mo_hop_thoai(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot)
    assert "Tự sửa âm thanh" in dashboard._func_buttons["Tự sửa âm thanh"].toolTip()
    from core.accessibility import shortcuts
    assert any(k == "Ctrl+Shift+A" and t == "_open_audio_doctor" for k, t, _ in shortcuts._DEFAULT_BINDINGS)
