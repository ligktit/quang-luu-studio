"""Dashboard nối SFX: fader âm lượng (lưu settings), bấm nút → bật/tắt qua
SfxPlayer, đèn nút theo trạng thái phát, giữ đèn khi panel dựng lại (Dev Mode)."""
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QObject, Signal


class FakeVoice(QObject):
    finished = Signal()

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.gain = None
        self.playing = False

    def play(self):
        self.playing = True

    def stop(self):
        self.playing = False

    def set_gain(self, g):
        self.gain = g


def _make_dashboard(qtbot, wav, extra=None):
    from frontend_qt import MainDashboard
    base = {
        "studio_one_path": "", "auto_close_studio_one": False,
        "sfx_buttons": [{"id": "sfx_a", "label": "A", "name": "Alpha",
                         "file_path": wav, "color": "#14B8A6"}],
        **(extra or {}),
    }
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
    voices = []

    def factory(path):
        v = FakeVoice(path)
        voices.append(v)
        return v

    # Thay thiết bị âm thanh thật bằng voice giả.
    dashboard._sfx_player._factory = factory
    return dashboard, voices


@pytest.fixture
def wav(tmp_path):
    p = tmp_path / "a.wav"
    p.write_bytes(b"RIFF")
    return str(p)


def _sfx_btn(dashboard, sfx_id="sfx_a"):
    return next(b for b in dashboard._sfx_area._btn_widgets if b.data["id"] == sfx_id)


def test_fader_lay_gia_tri_da_luu(qapp, qtbot, wav):
    d, voices = _make_dashboard(qtbot, wav, {"sfx_volume": 0})
    assert d._sfx_volume_slider.value() == 0
    d._sfx_area.sfx_toggle.emit("sfx_a", wav)
    assert voices[0].gain == 0.0


def test_fader_mac_dinh_100(qapp, qtbot, wav):
    d, voices = _make_dashboard(qtbot, wav)
    assert d._sfx_volume_slider.value() == 100
    d._sfx_area.sfx_toggle.emit("sfx_a", wav)
    assert voices[0].gain == 1.0


def test_keo_fader_doi_am_luong_sfx_dang_phat(qapp, qtbot, wav):
    d, voices = _make_dashboard(qtbot, wav)
    d._sfx_area.sfx_toggle.emit("sfx_a", wav)
    with patch("frontend_qt.backend.ConfigManager.save_settings"):
        d._sfx_volume_slider.setValue(0)
    assert voices[0].gain == 0.0


def test_keo_fader_luu_settings_mot_lan_sau_khi_dung(qapp, qtbot, wav):
    d, _ = _make_dashboard(qtbot, wav)
    with patch("frontend_qt.backend.ConfigManager.save_settings") as save:
        for v in (90, 70, 40):
            d._sfx_volume_slider.setValue(v)
        assert save.call_count == 0          # đang kéo — chưa ghi file
        qtbot.waitUntil(lambda: save.call_count == 1, timeout=2000)
        qtbot.wait(600)
        assert save.call_count == 1
    assert save.call_args[0][0]["sfx_volume"] == 40
    assert d.settings["sfx_volume"] == 40


def test_bam_nut_bat_roi_tat(qapp, qtbot, wav):
    d, voices = _make_dashboard(qtbot, wav)
    btn = _sfx_btn(d)
    d._sfx_area.sfx_toggle.emit("sfx_a", wav)
    assert voices[0].playing and btn.is_playing()
    d._sfx_area.sfx_toggle.emit("sfx_a", wav)
    assert not btn.is_playing()
    qtbot.waitUntil(lambda: not voices[0].playing, timeout=2000)


def test_het_file_nut_tu_tat_den(qapp, qtbot, wav):
    d, voices = _make_dashboard(qtbot, wav)
    d._sfx_area.sfx_toggle.emit("sfx_a", wav)
    voices[0].finished.emit()
    assert not _sfx_btn(d).is_playing()


def test_file_khong_ton_tai_khong_phat(qapp, qtbot, wav, tmp_path):
    d, voices = _make_dashboard(qtbot, wav)
    d._sfx_area.sfx_toggle.emit("sfx_a", str(tmp_path / "mat.wav"))
    assert voices == []
    assert not _sfx_btn(d).is_playing()


def test_xoa_nut_dang_phat_thi_dung_am(qapp, qtbot, wav):
    d, voices = _make_dashboard(qtbot, wav)
    d._sfx_area.sfx_toggle.emit("sfx_a", wav)
    with patch("frontend_qt.backend.ConfigManager.save_settings"):
        d._sfx_area._on_delete(_sfx_btn(d))
    qtbot.waitUntil(lambda: not voices[0].playing, timeout=2000)
    assert not d._sfx_player.is_playing("sfx_a")


def test_dung_lai_panel_giu_den_va_fader(qapp, qtbot, wav):
    d, voices = _make_dashboard(qtbot, wav)
    d._sfx_area.sfx_toggle.emit("sfx_a", wav)
    with patch("frontend_qt.backend.ConfigManager.save_settings"):
        d._sfx_volume_slider.setValue(30)
    d.refresh_ui()
    assert _sfx_btn(d).is_playing()
    assert d._sfx_volume_slider.value() == 30
    # Panel mới vẫn tắt được SFX đang phát từ trước.
    d._sfx_area.sfx_toggle.emit("sfx_a", wav)
    assert not _sfx_btn(d).is_playing()
