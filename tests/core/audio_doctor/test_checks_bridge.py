from core.audio_doctor.checks_bridge import LoopMidiCheck, DawRemoteCheck, LOOPMIDI_PORTS_KEY
from core.audio_doctor.model import Status
from core.daw import CUBASE, STUDIO_ONE
from tests.core.audio_doctor.fakes import make_ctx


def test_loopmidi_du_cong_la_ok():
    ctx = make_ctx()
    ctx.system.outs, ctx.system.ins = ["QuangLuuMIDI 1"], ["QLS_PhanHoi 2"]
    assert LoopMidiCheck().detect(ctx).status is Status.OK


def test_loopmidi_chua_cai_khong_sua_duoc():
    ctx = make_ctx()
    ctx.system.loopmidi_exe = None
    f = LoopMidiCheck().detect(ctx)
    assert f.status is Status.LOI and not f.fixable
    assert "setup_all.bat" in " ".join(f.guide)


def test_loopmidi_tat_thi_bat_len_va_noi_lai_midi():
    ctx = make_ctx()
    s = ctx.system
    s.reg[("HKCU", LOOPMIDI_PORTS_KEY, "QuangLuuMIDI")] = "QuangLuuMIDI"
    s.reg[("HKCU", LOOPMIDI_PORTS_KEY, "QLS_PhanHoi")] = "QLS_PhanHoi"

    def started(path):
        s.procs.add("loopmidi.exe")
        s.outs, s.ins = ["QuangLuuMIDI"], ["QLS_PhanHoi"]
    s.on_start = started
    c = LoopMidiCheck()
    assert c.detect(ctx).fixable
    f = c.fix(ctx)
    assert f.status is Status.DA_SUA
    assert s.started == [s.loopmidi_exe] and s.killed == []
    assert "reconnect_midi" in ctx.actions.calls


def test_loopmidi_thieu_cong_thi_ghi_registry_va_khoi_dong_lai():
    ctx = make_ctx()
    s = ctx.system
    s.procs.add("loopmidi.exe")
    s.outs = ["QuangLuuMIDI"]
    s.reg[("HKCU", LOOPMIDI_PORTS_KEY, "QuangLuuMIDI")] = "QuangLuuMIDI"
    s.on_start = lambda p: (s.procs.add("loopmidi.exe"), setattr(s, "ins", ["QLS_PhanHoi"]))
    f = LoopMidiCheck().fix(ctx)
    assert s.reg[("HKCU", LOOPMIDI_PORTS_KEY, "QLS_PhanHoi")] == "QLS_PhanHoi"
    assert s.killed == ["loopMIDI.exe"]
    assert f.status is Status.DA_SUA


def test_loopmidi_khong_len_cong_thi_can_lam_tay():
    ctx = make_ctx()
    f = LoopMidiCheck().fix(ctx)
    assert f.status is Status.CAN_LAM_TAY


SO_DIR = r"C:\U\AppData\Roaming\PreSonus\Studio One 6"
SO_SURF = SO_DIR + r"\User Devices\QuangLuuMIDI\QuangLuuMIDI.surface.xml"
SO_INFO = SO_DIR + r"\User Devices\QuangLuuMIDI\deviceinfo.xml"
CB_JS = (r"C:\U\Documents\Steinberg\Cubase\MIDI Remote\Driver Scripts\Local"
         r"\QuangLuu\QuangLuuMIDI\QuangLuu_QuangLuuMIDI.js")


def _so_bundle(ctx):
    s = ctx.system
    s.bundle = {"studio_one/QuangLuuMIDI.surface.xml": "SRC_SURF", "studio_one/deviceinfo.xml": "SRC_INFO",
                "cubase/QuangLuu_QuangLuuMIDI.js": "SRC_JS"}
    s.files.update({"SRC_SURF": "surf v2", "SRC_INFO": "info", "SRC_JS": "js v2"})
    s.dirs = [SO_DIR]


def test_surface_so_cu_thi_chep_lai_va_nhac_khoi_dong_lai_khi_dang_chay():
    ctx = make_ctx(STUDIO_ONE)
    _so_bundle(ctx)
    ctx.system.files.update({SO_SURF: "surf v1", SO_INFO: "info"})
    ctx.system.running = True
    c = DawRemoteCheck()
    assert c.detect(ctx).status is Status.LOI
    f = c.fix(ctx)
    assert ctx.system.files[SO_SURF] == "surf v2"
    assert f.status is Status.CAN_LAM_TAY and "Khởi động lại Studio One" in f.message
    assert c.detect(ctx).status is Status.OK


def test_script_cubase_thieu_thi_chep_khi_cubase_dang_dong():
    ctx = make_ctx(CUBASE)
    _so_bundle(ctx)
    c = DawRemoteCheck()
    assert c.detect(ctx).status is Status.LOI
    assert c.fix(ctx).status is Status.DA_SUA
    assert ctx.system.files[CB_JS] == "js v2"


def test_so_chua_tung_chay_thi_khong_ro():
    ctx = make_ctx(STUDIO_ONE)
    _so_bundle(ctx)
    ctx.system.dirs = []
    assert DawRemoteCheck().detect(ctx).status is Status.KHONG_RO
