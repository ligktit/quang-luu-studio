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
