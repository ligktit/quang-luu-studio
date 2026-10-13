"""main.py: Velopack phải xử lý hook --veloapp-* trước mọi import nặng; không còn bộ cập nhật cũ."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _main():
    with open(os.path.join(ROOT, "main.py"), encoding="utf-8") as f:
        return f.read()


def test_velopack_chay_truoc_import_nang():
    src = _main()
    i = src.index("velopack.App().run()")
    for heavy in ("from PySide6", "import backend", "from core.logger", "import frontend_qt"):
        assert i < src.index(heavy), heavy


def test_co_lenh_chuyen_cau_hinh_cu_truoc_qt():
    src = _main()
    assert src.index('"--chuyen-cau-hinh-cu"') < src.index("import backend")
    assert "migrate_cli" in src


def test_ap_dung_ban_cho_truoc_khi_thoat():
    src = _main()
    tail = src[src.index('if __name__ == "__main__":'):]
    assert tail.index("apply_pending_on_exit()") < tail.index("os._exit(0)")


def test_khong_con_bo_cap_nhat_cu():
    src = _main()
    for old in ("UpdateDialog", "check_and_notify_update", "_schedule_update_check", "last_check_timestamp"):
        assert old not in src, old
    for f in ("_downloader.py", "_installer.py", "_verifier.py", "_version_check.py"):
        assert not os.path.exists(os.path.join(ROOT, "core", "updater", f)), f
    assert not os.path.exists(os.path.join(ROOT, "ui", "dialogs", "update_dialog.py"))


def test_requirements_ghim_velopack_cung_so_voi_vpk():
    with open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8") as f:
        assert "velopack==1.2.161" in f.read()


def _khoi_velopack():
    src = _main()
    return src[src.index("import velopack"):src.index("# ── PyInstaller _MEI cleanup")]


def test_velopack_chi_tu_ap_dung_khi_la_ban_duy_nhat():
    # App().run() mặc định tự áp dụng bản chờ ở BẤT KỲ lần mở nào và Update.exe tắt
    # mọi tiến trình trong thư mục cài — kể cả app đang chạy.
    blk = _khoi_velopack()
    assert 'getattr(sys, "frozen", False)' in blk
    assert "set_auto_apply_on_startup(False)" in blk
    assert "auto_apply_on_startup_allowed(sys.argv, other_instances_running())" in blk
    assert blk.index("set_auto_apply_on_startup") < blk.index(".run()")


def test_cho_update_exe_truoc_khi_chay_velopack_nhung_khong_o_hook():
    blk = _khoi_velopack()
    assert "wait_for_update_exe(os.path.dirname(sys.executable))" in blk
    assert blk.index("wait_for_update_exe") < blk.index(".run()")
    # Hook --veloapp-* do chính Update.exe gọi: chờ nó là tự chờ mình (hook chỉ có 30 s).
    assert "--veloapp-" in blk


def test_khoi_velopack_chi_dung_stdlib_va_instance_guard():
    blk = _khoi_velopack()
    for heavy in ("PySide6", "import backend", "core.logger", "numba", "frontend_qt"):
        assert heavy not in blk, heavy
    assert "from core.instance_guard import" in blk


def test_ban_cai_roi_thu_muc_cai_truoc_khi_mo_tien_trinh_con():
    """Velopack mở app với CWD = thư mục cài; con cháu (loopMIDI, trình duyệt, DAW) thừa
    hưởng CWD đó và chặn Update.exe đổi tên thư mục khi áp dụng bản chờ."""
    src = _main()
    frozen = src[src.index('if getattr(sys, "frozen", False):'):src.index("except Exception:")]
    assert "leave_install_dir(" in frozen
    assert src.index("leave_install_dir(") < src.index("import backend")
