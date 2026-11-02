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


def _fix_btn(dashboard):
    return dashboard._func_buttons["Tự sửa âm thanh"]


def test_loi_luc_mo_app_bat_cua_so_canh_bao(qapp, mock_engine, qtbot, tmp_path):
    dashboard = _make_dashboard(qtbot)
    rep = _svc(tmp_path).run("check", "startup")
    with patch.object(dashboard, "_a11y_speak") as speak:
        dashboard._on_audio_doctor_report(rep, "run")
    dlg = dashboard._audio_alert_dialog
    qtbot.addWidget(dlg)
    assert dlg.isVisible()
    assert "Kênh Mic đang tắt" in dlg.accessibleDescription()
    assert "1 vấn đề" in dlg.title_label.text()
    speak.assert_called_once()
    assert not hasattr(dashboard, "_audio_warn_btn")
    assert _fix_btn(dashboard)._active is True


def test_rerun_cap_nhat_khong_mo_cua_so_thu_hai(qapp, mock_engine, qtbot, tmp_path):
    dashboard = _make_dashboard(qtbot)
    rep = _svc(tmp_path).run("check", "startup")
    dashboard._on_audio_doctor_report(rep, "run")
    first = dashboard._audio_alert_dialog
    qtbot.addWidget(first)
    dashboard._on_audio_doctor_report(rep, "rerun")
    assert dashboard._audio_alert_dialog is first
    assert first.isVisible()


def test_bao_cao_sach_dong_cua_so_va_tat_vien(qapp, mock_engine, qtbot, tmp_path):
    dashboard = _make_dashboard(qtbot)
    svc = _svc(tmp_path)
    dashboard._on_audio_doctor_report(svc.run("check", "startup"), "run")
    qtbot.addWidget(dashboard._audio_alert_dialog)
    _Mic.fixed = True
    dashboard._on_audio_doctor_report(svc.run("check", "startup"), "rerun")
    assert not dashboard._audio_alert_dialog.isVisible()
    assert _fix_btn(dashboard)._active is False


def test_ket_qua_tu_hop_thoai_khong_bat_canh_bao(qapp, mock_engine, qtbot, tmp_path):
    dashboard = _make_dashboard(qtbot)
    rep = _svc(tmp_path).run("check", "startup")
    dashboard._on_audio_doctor_report(rep, "button")
    dlg = getattr(dashboard, "_audio_alert_dialog", None)
    assert dlg is None or not dlg.isVisible()
    assert _fix_btn(dashboard)._active is True


def test_bam_tu_sua_dong_canh_bao_va_mo_hop_thoai(qapp, mock_engine, qtbot, tmp_path):
    dashboard = _make_dashboard(qtbot)
    dashboard._on_audio_doctor_report(_svc(tmp_path).run("check", "startup"), "run")
    dlg = dashboard._audio_alert_dialog
    qtbot.addWidget(dlg)
    with patch.object(dashboard, "_open_audio_doctor") as op:
        dlg.fix_btn.click()
    op.assert_called_once()
    assert not dlg.isVisible()


def test_bam_de_sau_chi_dong_cua_so(qapp, mock_engine, qtbot, tmp_path):
    dashboard = _make_dashboard(qtbot)
    dashboard._on_audio_doctor_report(_svc(tmp_path).run("check", "startup"), "run")
    dlg = dashboard._audio_alert_dialog
    qtbot.addWidget(dlg)
    with patch.object(dashboard, "_open_audio_doctor") as op:
        dlg.later_btn.click()
    op.assert_not_called()
    assert not dlg.isVisible()
    assert _fix_btn(dashboard)._active is True      # vẫn còn chỗ bấm thứ hai


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


def test_header_khong_con_nut_mat_va_ho_tro_luon_hien(qapp, mock_engine, qtbot):
    d = _make_dashboard(qtbot)
    assert getattr(d, "_eye_btn", None) is None
    assert getattr(d, "_tech_badge", None) is None
    assert d._support_btn.isVisibleTo(d)
