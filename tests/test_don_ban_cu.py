# tests/test_don_ban_cu.py
"""tools/don_ban_cu.ps1 xoá bản Inno cũ: thư mục cài, khoá gỡ cài đặt, đúng 5
shortcut cũ trong thư mục dùng chung — và KHÔNG gì khác."""
import os
import subprocess
import uuid
import winreg

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "tools", "don_ban_cu.ps1")
OLD_LNKS = ["Quang Luu Studio.lnk", "Gỡ cài đặt Quang Luu Studio.lnk",
            "Quang Luu Studio - Cấu hình YouTube Cookies.lnk",
            "Quang Luu Studio - Kiểm tra dò tone.lnk", "Quang Luu Studio Recordings.lnk"]


@pytest.fixture
def ctx(tmp_path):
    legacy = tmp_path / "Program Files" / "QuangLuuStudio"
    (legacy / "sfx").mkdir(parents=True)
    (legacy / "QuangLuuStudio.exe").write_bytes(b"MZ")
    (legacy / "sfx" / "a.wav").write_bytes(b"RIFF")
    sc = tmp_path / "Public Desktop"
    sc.mkdir()
    for n in OLD_LNKS + ["Trình duyệt khác.lnk"]:
        (sc / n).write_bytes(b"L")
    sub = f"Software\\QLSTest_DonBanCu\\{uuid.uuid4().hex}"
    winreg.CreateKey(winreg.HKEY_CURRENT_USER, sub).Close()
    yield {"legacy": legacy, "sc": sc, "key": "HKCU:\\" + sub, "sub": sub}
    for path in (sub, "Software\\QLSTest_DonBanCu"):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except OSError:
            pass


def _run(legacy, key, sc, protected=None):
    extra = ["-ProtectedDirs", str(protected)] if protected else []
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", SCRIPT,
         "-LegacyDir", str(legacy), "-UninstallKey", key, "-ShortcutDirs", str(sc)] + extra,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60)


def _key_exists(sub):
    try:
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub).Close()
        return True
    except OSError:
        return False


def test_xoa_thu_muc_khoa_va_shortcut_cu(ctx):
    r = _run(ctx["legacy"], ctx["key"], ctx["sc"])
    assert r.returncode == 0, r.stdout + r.stderr
    assert not ctx["legacy"].exists()
    assert not _key_exists(ctx["sub"])
    assert sorted(os.listdir(ctx["sc"])) == ["Trình duyệt khác.lnk"]


def test_giu_shortcut_khac(ctx):
    _run(ctx["legacy"], ctx["key"], ctx["sc"])
    assert (ctx["sc"] / "Trình duyệt khác.lnk").exists()


def test_khong_xoa_thu_muc_la(ctx, tmp_path):
    la = tmp_path / "ThuMucLa"
    la.mkdir()
    (la / "quan_trong.txt").write_text("x", encoding="utf-8")
    r = _run(la, ctx["key"], ctx["sc"])
    assert r.returncode == 0, r.stdout + r.stderr
    assert (la / "quan_trong.txt").exists()


def test_chay_lai_khi_da_sach_van_ma_0(ctx):
    _run(ctx["legacy"], ctx["key"], ctx["sc"])
    r = _run(ctx["legacy"], ctx["key"], ctx["sc"])
    assert r.returncode == 0, r.stdout + r.stderr


def test_khong_xoa_goc_o_dia(ctx):
    """Thư mục nằm trong danh sách bảo vệ (đại diện gốc ổ / thư mục hệ thống) thì
    không bị xoá dù có QuangLuuStudio.exe bên trong. Không đụng ổ thật."""
    r = _run(ctx["legacy"], ctx["key"], ctx["sc"], protected=ctx["legacy"])
    assert r.returncode == 0, r.stdout + r.stderr
    assert (ctx["legacy"] / "QuangLuuStudio.exe").exists()
    assert (ctx["legacy"] / "sfx" / "a.wav").exists()
    assert "BO QUA" in r.stdout


def test_xoa_chua_het_giu_khoa_va_ma_2(ctx):
    """File đang bị khoá → thư mục còn lại → giữ khoá gỡ cài đặt, mã thoát 2."""
    with open(ctx["legacy"] / "sfx" / "a.wav", "rb"):
        r = _run(ctx["legacy"], ctx["key"], ctx["sc"])
    assert r.returncode == 2, r.stdout + r.stderr
    assert ctx["legacy"].exists()
    assert _key_exists(ctx["sub"])
