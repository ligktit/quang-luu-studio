"""SfxPlayer: bật/tắt từng SFX, tắt có fade ngắn, fader âm lượng chung.

Trước đây mỗi lần bấm tạo một QMediaPlayer "mồ côi" — không ai giữ tham chiếu
nên SFX dài không tắt được. Thiết bị âm thanh được thay bằng voice giả (cùng
giao diện với voice thật trong ui/components/sfx_player.py); phần logic
bật/tắt, fade, âm lượng là code thật.
"""
import pytest
from PySide6.QtCore import QObject, Signal


class FakeVoice(QObject):
    finished = Signal()

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.playing = False
        self.stopped = False
        self.gain = None
        self.gains = []

    def play(self):
        self.playing = True

    def stop(self):
        self.playing = False
        self.stopped = True

    def set_gain(self, g):
        self.gain = g
        self.gains.append(g)


@pytest.fixture
def player(qapp):
    from ui.components.sfx_player import SfxPlayer
    voices = []

    def factory(path):
        v = FakeVoice(path)
        voices.append(v)
        return v

    p = SfxPlayer(voice_factory=factory, fade_ms=60)
    p.voices = voices
    return p


def test_bam_lan_dau_phat_va_bao_started(player, qtbot):
    with qtbot.waitSignal(player.started) as sig:
        player.toggle("sfx_a", "a.wav")
    assert sig.args == ["sfx_a"]
    assert player.voices[0].playing
    assert player.voices[0].path == "a.wav"
    assert player.is_playing("sfx_a")


def test_bam_lan_hai_fade_roi_dung(player, qtbot):
    player.toggle("sfx_a", "a.wav")
    v = player.voices[0]
    # stopped phát ngay (đèn nút tắt liền) nhưng âm chưa cắt — đang fade.
    with qtbot.waitSignal(player.stopped, timeout=100) as sig:
        player.toggle("sfx_a", "a.wav")
    assert sig.args == ["sfx_a"]
    assert not player.is_playing("sfx_a")
    assert not v.stopped
    qtbot.waitUntil(lambda: v.stopped, timeout=2000)
    # Gain giảm dần về 0 trước khi stop, không nhảy thẳng.
    tail = v.gains[v.gains.index(1.0):]
    assert tail[-1] == 0.0
    assert any(0.0 < g < 1.0 for g in tail)
    assert tail == sorted(tail, reverse=True)
    assert len(player.voices) == 1   # tắt không tạo voice mới


def test_bam_lai_trong_luc_fade_thi_phat_lai_tu_dau(player, qtbot):
    player.toggle("sfx_a", "a.wav")
    old = player.voices[0]
    player.toggle("sfx_a", "a.wav")      # bắt đầu fade
    player.toggle("sfx_a", "a.wav")      # bấm lại khi đang fade
    assert len(player.voices) == 2
    new = player.voices[1]
    assert new.playing
    assert player.is_playing("sfx_a")
    qtbot.waitUntil(lambda: old.stopped, timeout=2000)
    # Voice cũ fade xong không được làm tắt đèn của lần phát mới.
    assert player.is_playing("sfx_a")
    assert new.playing


def test_het_file_tu_bao_stopped(player, qtbot):
    player.toggle("sfx_a", "a.wav")
    with qtbot.waitSignal(player.stopped) as sig:
        player.voices[0].finished.emit()
    assert sig.args == ["sfx_a"]
    assert not player.is_playing("sfx_a")
    # Bấm tiếp sau khi hết file → phát lại, không phải "tắt".
    player.toggle("sfx_a", "a.wav")
    assert len(player.voices) == 2 and player.voices[1].playing


def test_cac_sfx_khac_nhau_phat_chong_duoc(player):
    player.toggle("sfx_a", "a.wav")
    player.toggle("sfx_b", "b.wav")
    assert player.is_playing("sfx_a") and player.is_playing("sfx_b")
    assert all(v.playing for v in player.voices)


def test_stop_id_dang_phat_thi_dung(player, qtbot):
    player.toggle("sfx_a", "a.wav")
    with qtbot.waitSignal(player.stopped, timeout=100):
        player.stop("sfx_a")
    qtbot.waitUntil(lambda: player.voices[0].stopped, timeout=2000)


def test_stop_id_khong_phat_khong_lam_gi(player, qtbot):
    with qtbot.assertNotEmitted(player.stopped, wait=100):
        player.stop("sfx_x")


@pytest.mark.parametrize("percent, lo, hi", [
    (100, 1.0, 1.0),
    (0, 0.0, 0.0),
    # Thang cảm nhận (log): giữa hành trình fader nhỏ hơn hẳn 50% tuyến tính.
    (50, 0.05, 0.3),
])
def test_volume_ap_cho_sfx_moi(player, percent, lo, hi):
    player.set_volume(percent)
    player.toggle("sfx_a", "a.wav")
    assert lo <= player.voices[0].gain <= hi


def test_volume_doi_ngay_cho_sfx_dang_phat(player):
    player.toggle("sfx_a", "a.wav")
    player.toggle("sfx_b", "b.wav")
    player.set_volume(0)
    assert [v.gain for v in player.voices] == [0.0, 0.0]


def test_volume_ngoai_khoang_bi_kep(player):
    player.set_volume(150)
    player.toggle("sfx_a", "a.wav")
    assert player.voices[0].gain == 1.0
    player.set_volume(-5)
    assert player.voices[0].gain == 0.0


def test_voice_loi_khi_tao_khong_bao_started(qapp, qtbot):
    from ui.components.sfx_player import SfxPlayer

    def broken(path):
        raise RuntimeError("no audio")

    p = SfxPlayer(voice_factory=broken)
    with qtbot.assertNotEmitted(p.started, wait=50):
        p.toggle("sfx_a", "a.wav")
    assert not p.is_playing("sfx_a")
