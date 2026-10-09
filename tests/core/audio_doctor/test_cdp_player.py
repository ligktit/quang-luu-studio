from unittest.mock import patch

from core.cdp_monitor import CDPYouTubeMonitor


def _mon():
    m = CDPYouTubeMonitor.__new__(CDPYouTubeMonitor)
    m.is_connected = True
    return m


def test_get_player_state():
    m = _mon()
    with patch.object(CDPYouTubeMonitor, "_evaluate_js", return_value={"muted": True, "volume": 30}) as ev:
        assert m.get_player_state() == {"muted": True, "volume": 30}
    assert "isMuted" in ev.call_args.args[0]


def test_khong_ket_noi_thi_none():
    m = _mon()
    m.is_connected = False
    assert m.get_player_state() is None
    assert m.unmute_player() is False


def test_unmute_player():
    m = _mon()
    with patch.object(CDPYouTubeMonitor, "_evaluate_js", return_value=True) as ev:
        assert m.unmute_player() is True
    assert "unMute" in ev.call_args.args[0] and "muted = false" in ev.call_args.args[0]
