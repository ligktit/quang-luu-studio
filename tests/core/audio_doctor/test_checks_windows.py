from core.audio_doctor.checks_windows import (
    WinPlaybackDefaultCheck, WinPlaybackMuteCheck, WinMicCheck, MIC_CONSENT_KEY,
)
from core.audio_doctor.checks_browser import BrowserSessionCheck, YtPlayerCheck
from core.audio_doctor.model import Status
from core.audio_doctor.win_audio import Device
from tests.core.audio_doctor.fakes import make_ctx

VAD = Device("{vad}", "ASIOVADPRO Out")
SPK = Device("{spk}", "Speakers (Realtek)")


def _ctx(settings=None, answers=None):
    ctx = make_ctx(settings=settings if settings is not None else {}, answers=answers)
    ctx.win.devices = [SPK, VAD]
    return ctx


def test_mac_dinh_dung_thiet_bi_ao():
    ctx = _ctx({"music_playback_device_id": "{vad}"})
    ctx.win.defaults = ("{vad}", "{vad}")
    assert WinPlaybackDefaultCheck().detect(ctx).status is Status.OK


def test_mac_dinh_nhay_sang_loa_thi_dat_lai():
    ctx = _ctx({"music_playback_device_id": "{vad}"})
    ctx.win.defaults = ("{spk}", "{spk}")
    c = WinPlaybackDefaultCheck()
    f = c.detect(ctx)
    assert f.status is Status.LOI and "Speakers (Realtek)" in f.message
    assert c.fix(ctx).status is Status.DA_SUA
    assert ctx.win.set_default_calls == ["{vad}"]


def test_thiet_bi_ao_bien_mat_khong_sua_duoc():
    ctx = _ctx({"music_playback_device_id": "{gone}", "music_playback_device_name": "VB-Cable"})
    ctx.win.defaults = ("{spk}", "{spk}")
    f = WinPlaybackDefaultCheck().detect(ctx)
    assert f.status is Status.LOI and not f.fixable and "VB-Cable" in f.message


def test_chua_chon_thiet_bi_thi_khong_ro_luc_kiem_tra():
    c = WinPlaybackDefaultCheck()
    assert c.fix_when_unknown
    assert c.detect(_ctx()).status is Status.KHONG_RO


def test_chua_chon_thiet_bi_de_xuat_va_hoi_khach():
    ctx = _ctx(answers=[True])
    ctx.win.defaults = ("{spk}", "{spk}")
    f = WinPlaybackDefaultCheck().fix(ctx)
    assert f.status is Status.DA_SUA
    assert "ASIOVADPRO" in ctx.asked[0]
    assert ctx.actions.settings_saved == {"music_playback_device_id": "{vad}",
                                          "music_playback_device_name": "ASIOVADPRO Out"}
    assert ctx.win.set_default_calls == ["{vad}"]


def test_khong_co_thiet_bi_nao_khop_ten_thi_khong_dat_bua():
    ctx = make_ctx(answers=[True])
    ctx.win.devices = [SPK]
    f = WinPlaybackDefaultCheck().fix(ctx)
    assert f.status is Status.CAN_LAM_TAY
    assert ctx.win.set_default_calls == [] and ctx.asked == []
    assert "Cài đặt" in " ".join(f.guide)


def test_khach_tu_choi_de_xuat():
    ctx = _ctx(answers=[False])
    f = WinPlaybackDefaultCheck().fix(ctx)
    assert f.status is Status.CAN_LAM_TAY and ctx.win.set_default_calls == []


def test_pycaw_thieu_thi_khong_ro():
    ctx = _ctx({"music_playback_device_id": "{vad}"})
    ctx.win.ok = False
    assert WinPlaybackDefaultCheck().detect(ctx).status is Status.KHONG_RO


def test_thiet_bi_ao_bi_mute():
    ctx = _ctx({"music_playback_device_id": "{vad}"})
    ctx.win.state["{vad}"] = (True, 100.0)
    c = WinPlaybackMuteCheck()
    assert c.detect(ctx).status is Status.LOI
    c.fix(ctx)
    assert ctx.win.state["{vad}"] == (False, 100.0)


def test_khong_chon_thiet_bi_thi_kiem_loa_mac_dinh():
    ctx = _ctx()
    ctx.win.defaults = ("{spk}", "{spk}")
    ctx.win.state["{spk}"] = (False, 2.0)
    assert WinPlaybackMuteCheck().detect(ctx).status is Status.LOI


def test_mic_bi_chan_trong_quyen_rieng_tu_va_mute():
    ctx = _ctx()
    ctx.system.reg[("HKCU", MIC_CONSENT_KEY + r"\NonPackaged", "Value")] = "Deny"
    ctx.win.capture = "{mic}"
    ctx.win.state["{mic}"] = (True, 80.0)
    c = WinMicCheck()
    f = c.detect(ctx)
    assert f.status is Status.LOI and f.fixable
    assert c.fix(ctx).status is Status.DA_SUA
    assert ctx.system.reg[("HKCU", MIC_CONSENT_KEY + r"\NonPackaged", "Value")] == "Allow"
    assert ctx.win.state["{mic}"][0] is False


def test_mic_bi_chan_toan_may_can_ky_thuat():
    ctx = _ctx()
    ctx.system.reg[("HKLM", MIC_CONSENT_KEY, "Value")] = "Deny"
    f = WinMicCheck().detect(ctx)
    assert f.status is Status.LOI and not f.fixable


def test_trinh_duyet_bi_mute_trong_volume_mixer():
    ctx = _ctx()
    ctx.win.sessions = [("chrome.exe", True, 100.0)]
    c = BrowserSessionCheck()
    assert c.detect(ctx).status is Status.LOI
    c.fix(ctx)
    assert ctx.win.sessions == [("chrome.exe", False, 100.0)]


def test_trinh_duyet_chua_phat_thi_bo_qua():
    assert BrowserSessionCheck().detect(_ctx()).status is Status.BO_QUA


def test_player_youtube():
    ctx = _ctx()
    c = YtPlayerCheck()
    assert c.detect(ctx).status is Status.BO_QUA            # chưa có player
    ctx.actions.player = {"muted": True, "volume": 50}
    assert c.detect(ctx).status is Status.LOI
    c.fix(ctx)
    assert c.detect(ctx).status is Status.OK


def test_thanh_nhac_tren_app_dang_tat():
    ctx = _ctx()
    ctx.actions.player = {"muted": None, "volume": None}   # player nhúng: không đọc được
    ctx.actions.music = (True, 80)
    f = YtPlayerCheck().detect(ctx)
    assert f.status is Status.LOI and "Nhạc" in f.message
