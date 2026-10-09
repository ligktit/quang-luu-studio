import json
import threading
import time

import pytest

from core.audio_doctor.model import Check, Status, ok, loi, khong_ro, da_sua, can_lam_tay
from core.audio_doctor.context import DoctorContext
from core.audio_doctor.runner import Runner, append_log


def _ctx(**kw):
    return DoctorContext(settings={}, daw=None, system=None, win=None, actions=None, **kw)


class FakeCheck(Check):
    def __init__(self, id, group="bridge", requires=(), detects=None, fix_result=None,
                 fix_when_unknown=False, applies=True, raise_in=None, sleep=0.0):
        self.id, self.group, self.title = id, group, id.upper()
        self.requires = requires
        self._detects = list(detects or [ok("ổn")])
        self._fix_result = fix_result or da_sua("đã sửa")
        self.fix_when_unknown = fix_when_unknown
        self._applies = applies
        self._raise_in = raise_in
        self._sleep = sleep
        self.fix_calls = 0
        self.timeout_s = 0.5

    def applies(self, ctx):
        return self._applies

    def detect(self, ctx):
        if self._raise_in == "detect":
            raise RuntimeError("hỏng")
        if self._sleep:
            time.sleep(self._sleep)
        return self._detects.pop(0) if len(self._detects) > 1 else self._detects[0]

    def fix(self, ctx):
        self.fix_calls += 1
        return self._fix_result


def test_check_mode_khong_bao_gio_goi_fix():
    c = FakeCheck("a", detects=[loi("hỏng")])
    rep = Runner([c]).run(_ctx(), "check", "startup")
    assert c.fix_calls == 0
    assert rep.results["a"].status is Status.LOI


def test_fix_thanh_cong_thi_ra_DA_SUA():
    c = FakeCheck("a", detects=[loi("hỏng"), ok("ổn rồi")], fix_result=da_sua("Đã bật"))
    rep = Runner([c]).run(_ctx(), "fix", "button")
    assert c.fix_calls == 1
    assert rep.results["a"].status is Status.DA_SUA
    assert rep.results["a"].message == "Đã bật"


def test_fix_xong_van_loi_thi_CAN_LAM_TAY_kem_huong_dan():
    c = FakeCheck("a", detects=[loi("hỏng", guide=("bước 1",))], fix_result=da_sua("x"))
    rep = Runner([c]).run(_ctx(), "fix", "button")
    f = rep.results["a"]
    assert f.status is Status.CAN_LAM_TAY
    assert f.guide == ("bước 1",)


def test_fix_tra_CAN_LAM_TAY_duoc_giu_du_detect_lai_ok():
    c = FakeCheck("a", detects=[loi("cũ"), ok("ổn")], fix_result=can_lam_tay("Khởi động lại DAW"))
    rep = Runner([c]).run(_ctx(), "fix", "button")
    assert rep.results["a"].status is Status.CAN_LAM_TAY
    assert rep.results["a"].message == "Khởi động lại DAW"


def test_loi_khong_sua_duoc_thanh_CAN_LAM_TAY_khi_fix():
    c = FakeCheck("a", detects=[loi("thiếu", fixable=False)])
    rep = Runner([c]).run(_ctx(), "fix", "button")
    assert c.fix_calls == 0
    assert rep.results["a"].status is Status.CAN_LAM_TAY


def test_khong_ro_co_fix_when_unknown_giu_ket_qua_fix():
    # Studio One không báo trạng thái: detect lại vẫn KHONG_RO → giữ "đã gửi lệnh".
    c = FakeCheck("a", detects=[khong_ro("không biết")], fix_when_unknown=True,
                  fix_result=da_sua("Đã gửi lệnh bật"))
    rep = Runner([c]).run(_ctx(), "fix", "button")
    assert rep.results["a"].status is Status.DA_SUA
    assert rep.results["a"].message == "Đã gửi lệnh bật"


def test_phu_thuoc_loi_thi_bo_qua():
    a = FakeCheck("a", detects=[loi("hỏng")])
    b = FakeCheck("b", requires=("a",))
    rep = Runner([a, b]).run(_ctx(), "check", "startup")
    assert rep.results["b"].status is Status.BO_QUA
    assert "A" in rep.results["b"].message


def test_phu_thuoc_khong_ro_khong_chan():
    a = FakeCheck("a", detects=[khong_ro("?")])
    b = FakeCheck("b", requires=("a",))
    rep = Runner([a, b]).run(_ctx(), "check", "startup")
    assert rep.results["b"].status is Status.OK


def test_check_khong_ap_dung_thi_khong_co_trong_ket_qua():
    rep = Runner([FakeCheck("a", applies=False)]).run(_ctx(), "check", "startup")
    assert "a" not in rep.results


def test_exception_va_timeout_thanh_KHONG_RO():
    a = FakeCheck("a", raise_in="detect")
    b = FakeCheck("b", sleep=2.0)
    rep = Runner([a, b]).run(_ctx(), "check", "startup")
    assert rep.results["a"].status is Status.KHONG_RO
    assert "hỏng" in rep.results["a"].detail
    assert rep.results["b"].status is Status.KHONG_RO


def test_thu_tu_theo_nhom_va_bao_tien_do():
    seen = []
    w = FakeCheck("w", group="windows")
    b = FakeCheck("b", group="bridge")
    Runner([w, b]).run(_ctx(), "check", "startup",
                       on_progress=lambda c, f: seen.append((c.id, f is None)))
    assert seen == [("b", True), ("b", False), ("w", True), ("w", False)]


def test_requires_phai_dung_truoc():
    with pytest.raises(ValueError):
        Runner([FakeCheck("b", requires=("a",)), FakeCheck("a", group="windows")])


def test_hai_luot_khong_chay_song_song():
    active = []
    peak = []

    class Slow(FakeCheck):
        def detect(self, ctx):
            active.append(1)
            peak.append(len(active))
            time.sleep(0.2)
            active.pop()
            return ok("ổn")

    r = Runner([Slow("a")])
    t = threading.Thread(target=r.run, args=(_ctx(), "check", "startup"))
    t.start()
    r.run(_ctx(), "fix", "button")
    t.join()
    assert max(peak) == 1


def test_problems_va_log(tmp_path):
    a = FakeCheck("a", detects=[loi("Mic tắt")])
    b = FakeCheck("b")
    rep = Runner([a, b]).run(_ctx(), "check", "startup")
    assert [c.id for c, _ in rep.problems()] == ["a"]
    assert "Mic tắt" in rep.summary()
    p = tmp_path / "logs" / "audio_doctor.log"
    append_log(rep, p)
    row = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert row["source"] == "startup" and row["results"]["a"]["status"] == "loi"
