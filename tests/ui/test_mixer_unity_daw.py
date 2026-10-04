"""Quy đổi dB → CC: 0 dB rơi đúng điểm unity của DAW (Studio One 76, Cubase 100)."""
from core import daw
from ui.panels.mixer import db_to_midi


def test_studio_one_0db_la_76():
    assert db_to_midi(0.0, -10.0, daw.STUDIO_ONE.fader_unity_cc) == 76
    assert db_to_midi(-10.0, -10.0, 76) == 0
    assert db_to_midi(10.0, -10.0, 76) == 127
    # Ghim điểm giữa của Studio One — giá trị cũ không được đổi.
    assert db_to_midi(-5.0, -10.0, 76) == 38
    assert db_to_midi(5.0, -10.0, 76) == 102


def test_cubase_0db_la_100():
    assert db_to_midi(0.0, -10.0, daw.CUBASE.fader_unity_cc) == 100
    assert db_to_midi(-10.0, -10.0, 100) == 0
    assert db_to_midi(10.0, -10.0, 100) == 127
    assert db_to_midi(-5.0, -10.0, 100) == 50


def test_khong_vuot_bien():
    assert db_to_midi(99.0, -10.0, 100) == 127
    assert db_to_midi(-99.0, -10.0, 100) == 0
