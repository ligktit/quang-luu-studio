from core.audio_doctor.model import Check, loi
from core.audio_doctor.context import DoctorContext
from core.audio_doctor.startup import StartupGate
from core.audio_doctor.service import AudioDoctorService


def test_cho_daw_san_sang_cong_10s():
    g = StartupGate(wait_s=180, settle_s=10, start=0)
    assert g.update(5, False) is None
    assert g.update(30, True) is None      # vừa thấy cửa sổ chính
    assert g.update(39, True) is None
    assert g.update(40, True) == "run"
    assert g.done


def test_het_180s_van_chay_roi_chay_lai_mot_lan_khi_daw_xong():
    g = StartupGate(wait_s=180, settle_s=10, start=0)
    assert g.update(179, False) is None
    assert g.update(180, False) == "run"
    assert not g.done
    assert g.update(200, True) is None
    assert g.update(210, True) == "rerun"
    assert g.update(300, True) is None
    assert g.done


def test_cua_so_chinh_bien_mat_thi_dem_lai():
    g = StartupGate(wait_s=180, settle_s=10, start=0)
    g.update(10, True)
    g.update(15, False)                     # hộp thoại che / đóng project
    assert g.update(21, True) is None
    assert g.update(31, True) == "run"


class _C(Check):
    id, group, title = "a", "bridge", "A"

    def detect(self, ctx):
        return loi("hỏng")


def _svc(tmp_path):
    ctx = lambda ask=None: DoctorContext(settings={}, daw=None, system=None, win=None, actions=None)
    return AudioDoctorService(ctx, [_C()], log_path=tmp_path / "audio_doctor.log")


def test_startup_loop_chay_check_va_bao_ket_qua(tmp_path):
    svc = _svc(tmp_path)
    t = [0.0]
    got = []
    ready = iter([False, True, True, True, True, True])
    svc.startup_loop(
        on_report=lambda rep, act: got.append((act, rep.mode, rep.source)),
        is_daw_ready=lambda: next(ready, True),
        wait_s=180, poll_s=5, now=lambda: t[0],
        sleep=lambda s: t.__setitem__(0, t[0] + s),
    )
    assert got == [("run", "check", "startup")]
    assert (tmp_path / "audio_doctor.log").exists()


def test_startup_loop_dung_khi_stop(tmp_path):
    svc = _svc(tmp_path)
    t = [0.0]
    got = []

    def sleep(s):
        t[0] += s
        if t[0] > 20:
            svc.stop()

    svc.startup_loop(on_report=lambda r, a: got.append(a), is_daw_ready=lambda: False,
                     wait_s=180, poll_s=5, now=lambda: t[0], sleep=sleep)
    assert got == []


def test_run_luu_last_report(tmp_path):
    svc = _svc(tmp_path)
    rep = svc.run("check", "button")
    assert svc.last_report is rep
