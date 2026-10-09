from core.audio_doctor.checks_daw import (
    DawRunningCheck, DawDialogCheck, CubaseReleaseDriverCheck, MicChannelCheck, MusicChannelCheck,
)
from core.audio_doctor.model import Status
from core.daw import CUBASE, STUDIO_ONE
from tests.core.audio_doctor.fakes import make_ctx

SONG = r"D:\QLS\mau.song"


def test_daw_dang_chay_co_cua_so_chinh():
    ctx = make_ctx(settings={"studio_one_path": SONG})
    ctx.system.running = ctx.system.main_window = True
    assert DawRunningCheck().detect(ctx).status is Status.OK


def test_chua_dat_duong_dan_thi_khong_sua_duoc():
    ctx = make_ctx(settings={})
    f = DawRunningCheck().detect(ctx)
    assert f.status is Status.LOI and not f.fixable
    assert "Cài đặt" in " ".join(f.guide)


def test_mo_daw_roi_dong_bo_midi():
    ctx = make_ctx(settings={"studio_one_path": SONG})
    ctx.system.files[SONG] = ""
    ctx.actions.on_launch = lambda: (setattr(ctx.system, "running", True),
                                     setattr(ctx.system, "main_window", True))
    c = DawRunningCheck()
    assert c.detect(ctx).fixable
    f = c.fix(ctx)
    assert f.status is Status.DA_SUA
    assert ctx.actions.calls == ["launch_daw", "sync_midi"]


def test_daw_mo_khong_xong_thi_can_lam_tay():
    ctx = make_ctx(settings={"studio_one_path": SONG})
    ctx.system.files[SONG] = ""
    ctx.actions.on_launch = lambda: setattr(ctx.system, "running", True)
    assert DawRunningCheck().fix(ctx).status is Status.CAN_LAM_TAY


def test_hop_thoai_chan_thi_dua_len_truoc_khong_bam_ho():
    ctx = make_ctx()
    ctx.system.running = True
    ctx.system.dialogs = [(42, "Audio Device Setup")]
    c = DawDialogCheck()
    f = c.detect(ctx)
    assert f.status is Status.LOI and "Audio Device Setup" in f.message
    g = c.fix(ctx)
    assert g.status is Status.CAN_LAM_TAY and ctx.system.focused == [42]


def test_khong_co_hop_thoai():
    ctx = make_ctx()
    ctx.system.running = ctx.system.main_window = True
    assert DawDialogCheck().detect(ctx).status is Status.OK


DEF = r"C:\U\AppData\Roaming\Steinberg\Cubase 13_64\Defaults.xml"


def _cubase_prefs(ctx, value):
    ctx.system.dirs = [r"C:\U\AppData\Roaming\Steinberg\Cubase 13_64"]
    ctx.system.files[DEF] = f'<a><int name="ReleaseHardware" value="{value}"/></a>'


def test_release_driver_chi_ap_dung_cubase():
    assert not CubaseReleaseDriverCheck().applies(make_ctx(STUDIO_ONE))
    assert CubaseReleaseDriverCheck().applies(make_ctx(CUBASE))


def test_release_driver_bat_khi_cubase_dong_thi_sua_va_sao_luu():
    ctx = make_ctx(CUBASE)
    _cubase_prefs(ctx, 1)
    c = CubaseReleaseDriverCheck()
    assert c.detect(ctx).status is Status.LOI
    f = c.fix(ctx)
    assert f.status is Status.DA_SUA
    assert 'value="0"' in ctx.system.files[DEF]
    assert ctx.system.backups == [DEF]
    assert ctx.actions.calls == []


def test_release_driver_khach_tu_choi_dong_cubase():
    ctx = make_ctx(CUBASE, answers=[False])
    _cubase_prefs(ctx, 1)
    ctx.system.running = True
    f = CubaseReleaseDriverCheck().fix(ctx)
    assert f.status is Status.CAN_LAM_TAY
    assert 'value="1"' in ctx.system.files[DEF]
    assert "close_daw" not in ctx.actions.calls
    assert ctx.asked and "Cubase" in ctx.asked[0]


def test_release_driver_khach_dong_y_thi_dong_sua_mo_lai():
    ctx = make_ctx(CUBASE, answers=[True])
    _cubase_prefs(ctx, 1)
    ctx.system.running = True
    ctx.actions.close_ok = True
    f = CubaseReleaseDriverCheck().fix(ctx)
    assert f.status is Status.DA_SUA
    assert ctx.actions.calls == ["close_daw", "launch_daw"]


def test_release_driver_tat_la_ok():
    ctx = make_ctx(CUBASE)
    _cubase_prefs(ctx, 0)
    assert CubaseReleaseDriverCheck().detect(ctx).status is Status.OK


def test_kenh_mic_studio_one_khong_ro_nhung_van_gui_lenh():
    ctx = make_ctx(STUDIO_ONE)
    c = MicChannelCheck()
    assert c.fix_when_unknown
    assert c.detect(ctx).status is Status.KHONG_RO
    f = c.fix(ctx)
    assert f.status is Status.DA_SUA and "gửi lệnh" in f.message
    assert "ensure_app_mic_on" in ctx.actions.calls
    assert (51, 0) in ctx.sent


def test_kenh_mic_app_dang_tat_la_loi_ca_voi_studio_one():
    ctx = make_ctx(STUDIO_ONE)
    ctx.actions.mic = (True, 0.0)
    assert MicChannelCheck().detect(ctx).status is Status.LOI


def test_kenh_mic_cubase_bao_mute():
    ctx = make_ctx(CUBASE)
    ctx.feedback.on_cc(51, 127)
    ctx.feedback.on_cc(21, 100)
    f = MicChannelCheck().detect(ctx)
    assert f.status is Status.LOI and "Cubase" in f.message


def test_kenh_mic_cubase_xac_nhan_sau_khi_sua():
    ctx = make_ctx(CUBASE)
    ctx.feedback.on_cc(51, 127)
    ctx.send_cc = lambda cc, v: (ctx.sent.append((cc, v)), ctx.feedback.on_cc(cc, v))[1] or True
    f = MicChannelCheck().fix(ctx)
    assert f.status is Status.DA_SUA
    assert MicChannelCheck().detect(ctx).status is Status.OK


def test_kenh_mic_cubase_khong_xac_nhan_thi_can_lam_tay():
    ctx = make_ctx(CUBASE)
    ctx.feedback.on_cc(51, 127)
    f = MicChannelCheck().fix(ctx)
    assert f.status is Status.CAN_LAM_TAY


def test_kenh_nhac_fader_qua_thap_cubase():
    ctx = make_ctx(CUBASE)
    ctx.feedback.on_cc(50, 0)
    ctx.feedback.on_cc(20, 1)
    assert MusicChannelCheck().detect(ctx).status is Status.LOI


def test_kenh_nhac_sua_gui_bo_mute_va_fader_0db():
    ctx = make_ctx(CUBASE)
    MusicChannelCheck().fix(ctx)
    assert (50, 0) in ctx.sent and (20, CUBASE.fader_unity_cc) in ctx.sent


def test_kenh_khong_dung_be_va_vang():
    ctx = make_ctx(CUBASE)
    MicChannelCheck().fix(ctx)
    MusicChannelCheck().fix(ctx)
    assert not [cc for cc, _ in ctx.sent if cc in (22, 23, 52, 53)]


# ── Sửa sau review cuối ──
def test_mic_cubase_fader_thap_co_chu_y_khong_bi_coi_la_tat():
    # Mic -9 dB trên app = CC 10 ở Cubase: khách cố ý để nhỏ, không phải lỗi.
    ctx = make_ctx(CUBASE)
    ctx.feedback.on_cc(51, 0)
    ctx.feedback.on_cc(21, 10)
    assert MicChannelCheck().detect(ctx).status is Status.OK


def test_release_driver_mo_lai_cubase_thi_cho_xong_dong_bo_va_xoa_phan_hoi_cu():
    ctx = make_ctx(CUBASE, answers=[True])
    _cubase_prefs(ctx, 1)
    ctx.system.running = True
    ctx.system.main_window = True
    ctx.feedback.on_cc(51, 0)                    # trạng thái của Cubase TRƯỚC khi đóng
    f = CubaseReleaseDriverCheck().fix(ctx)
    assert f.status is Status.DA_SUA
    assert ctx.actions.calls == ["close_daw", "launch_daw", "sync_midi"]
    assert ctx.feedback.get("mic") is None


def test_mo_daw_xoa_phan_hoi_cu():
    ctx = make_ctx(CUBASE, settings={"studio_one_path": SONG})
    ctx.system.files[SONG] = ""
    ctx.feedback.on_cc(51, 0)
    ctx.actions.on_launch = lambda: (setattr(ctx.system, "running", True),
                                     setattr(ctx.system, "main_window", True))
    DawRunningCheck().fix(ctx)
    assert ctx.feedback.get("mic") is None
