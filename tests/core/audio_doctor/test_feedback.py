import threading
import time

from core.audio_doctor.feedback import DawFeedback

CC = {"mix_music": 20, "mix_mic": 21, "mix_reverb": 22, "mix_backing": 23,
      "mute_music": 50, "mute_mic": 51, "mute_reverb": 52, "mute_backing": 53}


def test_mute_va_fader_theo_nhom():
    fb = DawFeedback(CC, clock=lambda: 7.0)
    assert fb.get("mic") is None
    assert fb.on_cc(51, 127) is True
    assert fb.on_cc(21, 100) is True
    st = fb.get("mic")
    assert st.muted is True and st.fader == 100 and st.ts == 7.0
    fb.on_cc(51, 0)
    assert fb.get("mic").muted is False


def test_cc_khong_lien_quan_bi_bo_qua():
    fb = DawFeedback(CC)
    assert fb.on_cc(49, 5) is False     # echo ping
    assert fb.on_cc(60, 3) is False     # độ dài tên kênh
    assert fb.get("nhac") is None


def test_wait_for_tra_true_khi_trang_thai_toi():
    fb = DawFeedback(CC)
    fb.on_cc(50, 127)
    threading.Timer(0.05, lambda: fb.on_cc(50, 0)).start()
    assert fb.wait_for("nhac", lambda s: s.muted is False, timeout=1.0) is True


def test_wait_for_het_gio():
    fb = DawFeedback(CC)
    t0 = time.monotonic()
    assert fb.wait_for("mic", lambda s: s.muted is False, timeout=0.1) is False
    assert time.monotonic() - t0 < 1.0
