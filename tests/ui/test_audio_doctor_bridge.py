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


# ── hai mic (Studio One) ────────────────────────────────────────────────────
def _dashboard_2mic(qtbot, mic_count=2):
    with patch("frontend_qt.backend.ConfigManager.save_settings"):
        with patch("frontend_qt.backend.SongManager.load_songs", return_value=[]), \
             patch("frontend_qt.backend.ActivationManager.is_activated", return_value=True), \
             patch("frontend_qt.backend.ActivationManager.needs_activation", return_value=False), \
             patch("frontend_qt.QTimer.start"):
            d = MainDashboard({"studio_one_path": "", "auto_close_studio_one": False,
                               "mic_count": mic_count})
            qtbot.addWidget(d)
            if d._so_ready_watcher is not None:
                d._so_ready_watcher.stop()
        return d


def test_mic_check_ok_when_one_mic_on(qapp, mock_engine, qtbot):
    d = _dashboard_2mic(qtbot)
    acts = _actions(d)
    d._mixer_mute_setters["mix_mic"](True)
    d._mixer_mute_setters["mix_mic_2"](False)
    d._mixer_sliders["mix_mic_2"].setValue(0)
    assert acts.app_mic_state() == (False, 0.0)


def test_mic_check_all_off(qapp, mock_engine, qtbot):
    d = _dashboard_2mic(qtbot)
    acts = _actions(d)
    d._mixer_mute_setters["mix_mic"](True)
    d._mixer_mute_setters["mix_mic_2"](True)
    muted, _level = acts.app_mic_state()
    assert muted is True


def test_mic_check_level_is_max_of_unmuted(qapp, mock_engine, qtbot):
    d = _dashboard_2mic(qtbot)
    acts = _actions(d)
    d._mixer_mute_setters["mix_mic"](False)
    d._mixer_mute_setters["mix_mic_2"](False)
    d._mixer_sliders["mix_mic"].setValue(-3)
    d._mixer_sliders["mix_mic_2"].setValue(2)
    assert acts.app_mic_state() == (False, 2.0)


def test_ensure_mic_on_opens_both(qapp, mock_engine, qtbot):
    d = _dashboard_2mic(qtbot)
    acts = _actions(d)
    for k in ("mix_mic", "mix_mic_2"):
        d._mixer_mute_setters[k](True)
        d._mixer_sliders[k].setValue(d._mixer_sliders[k].minimum())
    acts.ensure_app_mic_on()
    for k in ("mix_mic", "mix_mic_2"):
        assert d._mixer_channels[k].is_muted() is False
        assert d._mixer_sliders[k].value() == 0


def test_hai_mic_chua_bat_thi_nhu_mot_mic(qapp, mock_engine, qtbot):
    d = _dashboard_2mic(qtbot, mic_count=1)
    assert "mix_mic_2" not in d._mixer_sliders
    acts = _actions(d)
    d._mixer_mute_setters["mix_mic"](True)
    assert acts.app_mic_state()[0] is True
