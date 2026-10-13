"""Bộ cài cầu nối 1.8.x → Velopack: các bảo đảm an toàn đọc được từ script."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _iss():
    with open(os.path.join(ROOT, "QuangLuuStudio_Bridge.iss"), "rb") as f:
        raw = f.read()
    assert raw.startswith(b"\xef\xbb\xbf"), "Inno đọc tiếng Việt cần UTF-8 có BOM"
    return raw.decode("utf-8-sig")


def test_cung_appid_ban_cu_va_khong_tu_ghi_khoa_go_cai():
    iss = _iss()
    assert "AppId={{B8F3E2A1-5D6C-4E7F-9A0B-1C2D3E4F5A6B}" in iss
    assert re.search(r"^Uninstallable=no", iss, re.M)
    assert re.search(r"^PrivilegesRequired=admin", iss, re.M)
    assert "OutputBaseFilename=Setup_QuangLuuStudio_v{#MyAppVersion}" in iss


def test_cai_velopack_duoi_quyen_nguoi_dung_goc():
    iss = _iss()
    assert "ExecAsOriginalUser(CaiDat, '--silent'" in iss
    assert "--chuyen-cau-hinh-cu" in iss


def test_khong_goi_unins000_cu():
    # chỉ được nhắc trong chú thích, không bao giờ được chạy
    assert not re.search(r"Exec\w*\([^;]*unins000", _iss(), re.I)


def test_chi_don_khi_chuyen_cau_hinh_xong():
    iss = _iss()
    code = iss.index("[Code]")
    mig = iss.index("--chuyen-cau-hinh-cu", code)
    don = iss.index("don_ban_cu.ps1", code)
    assert mig < don
    assert "and (Code = 0) then" in iss[mig:don]


def test_chuoi_powershell_nhay_don_duoc_nhan_doi():
    iss = _iss()
    assert "StringChangeEx(S, '''', '''''', True);" in iss


def test_sync_version_cap_nhat_cau_noi():
    with open(os.path.join(ROOT, "sync_version.py"), encoding="utf-8") as f:
        src = f.read()
    assert "QuangLuuStudio_Bridge.iss" in src and "QuangLuuStudio_Setup.iss" not in src


def test_bo_thu_muc_app_rong_chi_khi_don_xong():
    iss = _iss()
    m = re.search(r"procedure CurStepChanged\(CurStep: TSetupStep\);.*?\nend;", iss, re.S)
    assert m, "thiếu CurStepChanged"
    body = m.group(0)
    assert "ssPostInstall" in body and "CleanupCode = 0" in body
    assert "RemoveDir(ExpandConstant('{app}'))" in body
    assert "CleanupCode := -1;" in iss
    assert "CleanupCode := Code;" in iss


def test_cong_don_dung_khi_exitcode_null():
    iss = _iss()
    assert "if ($null -eq $p.ExitCode) { exit 1 }; exit $p.ExitCode" in iss
    assert "if ($null -eq $p) { exit 1 }" in iss


def test_mo_lai_app_cu_o_ca_hai_duong_loi():
    iss = _iss()
    assert "procedure RelaunchOldApp(" in iss
    assert "ExecAsOriginalUser(OldExe" in iss
    code = iss[iss.index("function PrepareToInstall"):]
    fails = re.findall(r"Result := '[^;]*;\s*RelaunchOldApp\(AppDir\);\s*exit;", code)
    assert len(fails) == 2
    assert len(re.findall(r"Result := '[^']", code)) == 2
