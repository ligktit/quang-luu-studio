"""core/instance_guard: không để Velopack tắt ngang app đang chạy (bản chờ chỉ áp dụng khi không còn tiến trình nào)."""
import os
from types import SimpleNamespace

from core import instance_guard as ig

EXE = r"C:\Users\Ca Si\AppData\Local\QuangLuuStudio\current\QuangLuuStudio.exe"
UPDATE_EXE = r"C:\Users\Ca Si\AppData\Local\QuangLuuStudio\Update.exe"
APP_DIR = os.path.dirname(EXE)


def _proc(pid, exe):
    return SimpleNamespace(info={"pid": pid, "exe": exe})


def _iter(*procs):
    return lambda attrs=None: list(procs)


# ── other_instances_running ──
def test_cung_duong_dan_khac_pid_la_ban_khac():
    it = _iter(_proc(10, EXE), _proc(20, EXE))
    assert ig.other_instances_running(exe_path=EXE, own_pid=10, process_iter=it) is True


def test_chi_co_chinh_minh_thi_khong_co_ban_khac():
    it = _iter(_proc(10, EXE), _proc(30, r"C:\Windows\notepad.exe"))
    assert ig.other_instances_running(exe_path=EXE, own_pid=10, process_iter=it) is False


def test_exe_khac_thu_muc_khong_tinh():
    it = _iter(_proc(10, EXE), _proc(20, r"D:\Khac\current\QuangLuuStudio.exe"))
    assert ig.other_instances_running(exe_path=EXE, own_pid=10, process_iter=it) is False


def test_so_sanh_khong_phan_biet_hoa_thuong_va_dau_gach():
    it = _iter(_proc(20, EXE.upper().replace("\\", "/")))
    assert ig.other_instances_running(exe_path=EXE, own_pid=10, process_iter=it) is True


def test_tien_trinh_khong_doc_duoc_exe_bi_bo_qua():
    it = _iter(_proc(10, EXE), _proc(20, None))
    assert ig.other_instances_running(exe_path=EXE, own_pid=10, process_iter=it) is False


def test_loi_khi_liet_ke_tien_trinh_thi_coi_la_co_ban_khac():
    def boom(attrs=None):
        raise OSError("psutil hỏng")
    assert ig.other_instances_running(exe_path=EXE, own_pid=10, process_iter=boom) is True


def test_loi_khi_lap_qua_tien_trinh_thi_coi_la_co_ban_khac():
    def gen(attrs=None):
        yield _proc(10, EXE)
        raise RuntimeError("giữa chừng")
    assert ig.other_instances_running(exe_path=EXE, own_pid=10, process_iter=gen) is True


def test_mac_dinh_dung_psutil_that_va_khong_nem():
    assert ig.other_instances_running() in (True, False)


# ── auto_apply_on_startup_allowed ──
def test_co_lenh_cong_cu_thi_khong_tu_ap_dung():
    for flag in ig.TOOL_FLAGS:
        assert ig.auto_apply_on_startup_allowed(["QuangLuuStudio.exe", flag], False) is False


def test_co_ban_khac_dang_chay_thi_khong_tu_ap_dung():
    assert ig.auto_apply_on_startup_allowed(["QuangLuuStudio.exe"], True) is False


def test_mo_binh_thuong_duoc_tu_ap_dung():
    assert ig.auto_apply_on_startup_allowed(["QuangLuuStudio.exe"], False) is True


def test_tool_flags_day_du():
    assert ig.TOOL_FLAGS == ("--tu-kiem-tra", "--thu-tai", "--chuyen-cau-hinh-cu")


# ── wait_for_update_exe ──
class _Clock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


def test_cho_den_khi_update_exe_thoat():
    clk = _Clock()
    lan = {"n": 0}

    def it(attrs=None):
        lan["n"] += 1
        return [_proc(99, UPDATE_EXE)] if lan["n"] <= 3 else []
    assert ig.wait_for_update_exe(APP_DIR, timeout=300, poll=1.0, process_iter=it,
                                  sleep=clk.sleep, clock=clk.now) is True
    assert clk.t == 3.0


def test_khong_co_update_exe_thi_khong_cho():
    clk = _Clock()
    assert ig.wait_for_update_exe(APP_DIR, process_iter=_iter(_proc(1, EXE)),
                                  sleep=clk.sleep, clock=clk.now) is False
    assert clk.t == 0.0


def test_update_exe_cua_thu_muc_khac_bi_bo_qua():
    clk = _Clock()
    it = _iter(_proc(99, r"D:\Khac\Update.exe"))
    assert ig.wait_for_update_exe(APP_DIR, process_iter=it, sleep=clk.sleep, clock=clk.now) is False
    assert clk.t == 0.0


def test_het_thoi_gian_cho_thi_thoi():
    clk = _Clock()
    it = _iter(_proc(99, UPDATE_EXE))
    assert ig.wait_for_update_exe(APP_DIR, timeout=5, poll=1.0, process_iter=it,
                                  sleep=clk.sleep, clock=clk.now) is True
    assert 5 <= clk.t <= 6


def test_loi_liet_ke_khi_cho_thi_khong_treo():
    def boom(attrs=None):
        raise OSError("x")
    clk = _Clock()
    assert ig.wait_for_update_exe(APP_DIR, process_iter=boom, sleep=clk.sleep, clock=clk.now) is False


# ── leave_install_dir ──
# Update.exe phải đổi tên thư mục cài khi áp dụng bản chờ. Tiến trình nào còn lấy nó
# làm thư mục làm việc (CWD) — kể cả con cháu của app thừa hưởng CWD: loopMIDI, trình
# duyệt, DAW — làm việc áp dụng hỏng "os error 32" mà Velopack không dò ra.
def test_cwd_trong_thu_muc_cai_thi_chuyen_ra_ngoai(tmp_path, monkeypatch):
    app_dir = tmp_path / "QuangLuuStudio" / "current"
    (app_dir / "_internal").mkdir(parents=True)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.chdir(app_dir / "_internal")
    assert ig.leave_install_dir(str(app_dir), str(home)) is True
    assert os.path.samefile(os.getcwd(), home)


def test_cwd_ngoai_thu_muc_cai_thi_giu_nguyen(tmp_path, monkeypatch):
    app_dir = tmp_path / "QuangLuuStudio" / "current"
    app_dir.mkdir(parents=True)
    other = tmp_path / "khac"
    other.mkdir()
    monkeypatch.chdir(other)
    assert ig.leave_install_dir(str(app_dir), str(tmp_path / "home")) is False
    assert os.path.samefile(os.getcwd(), other)


def test_thu_muc_dich_khong_ton_tai_thi_khong_loi(tmp_path, monkeypatch):
    app_dir = tmp_path / "current"
    app_dir.mkdir()
    monkeypatch.chdir(app_dir)
    assert ig.leave_install_dir(str(app_dir), str(tmp_path / "khong_co")) is False
    assert os.path.samefile(os.getcwd(), app_dir)
