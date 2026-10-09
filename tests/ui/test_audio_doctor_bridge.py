import threading
from unittest.mock import MagicMock, patch

import pytest

from frontend_qt import MainDashboard
from ui.ui_invoker import UiInvoker


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


def test_invoker_chay_tren_main_thread(qapp, qtbot):
    inv = UiInvoker()
    main = threading.get_ident()
    seen = {}

    def worker():
        seen["tid"] = inv.call(threading.get_ident)
        try:
            inv.call(lambda: 1 / 0)
        except ZeroDivisionError:
            seen["raised"] = True

    t = threading.Thread(target=worker)
    t.start()
    qtbot.waitUntil(lambda: not t.is_alive(), timeout=3000)
    assert seen == {"tid": main, "raised": True}
    assert inv.call(lambda: 5) == 5          # gọi ngay trên main thread không treo


def _actions(dashboard):
    from ui.audio_doctor_bridge import DashboardDoctorActions
    return DashboardDoctorActions(dashboard, UiInvoker(dashboard))


def test_bat_mic_tren_app_bo_mute_va_nang_muc(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot)
    acts = _actions(dashboard)
    dashboard._mixer_mute_setters["mix_mic"](True)
    dashboard._mixer_sliders["mix_mic"].setValue(dashboard._mixer_sliders["mix_mic"].minimum())
    assert acts.app_mic_state()[0] is True
    mock_engine.send_midi.reset_mock()
    acts.ensure_app_mic_on()
    muted, level = acts.app_mic_state()
    assert muted is False and level > -40
    assert dashboard._mixer_channels["mix_mic"].is_muted() is False
    assert (51, 0) in [c.args for c in mock_engine.send_midi.call_args_list]


def test_khong_dung_be_va_vang(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot)
    # Bè là nút bấm (không có thanh trượt); Vang là kênh mixer có mute.
    dashboard._mixer_mute_setters["mix_reverb"](True)
    be_before = getattr(dashboard, "be_state", None)
    acts = _actions(dashboard)
    acts.ensure_app_mic_on()
    acts.ensure_app_music_on()
    assert dashboard.mute_states["mix_reverb"] is True
    assert getattr(dashboard, "be_state", None) == be_before


def test_build_service_tao_context(qapp, mock_engine, qtbot):
    from ui.audio_doctor_bridge import build_service
    dashboard = _make_dashboard(qtbot)
    svc = build_service(dashboard)
    ctx = svc._ctx_factory(ask=None)
    assert ctx.feedback is mock_engine.daw_feedback
    assert ctx.daw.kind in ("studio_one", "cubase")
    assert ctx.ask("?") is False
