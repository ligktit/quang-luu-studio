"""release.yml: bản Velopack phát hành dạng prerelease, vpk cùng số với pip velopack."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _yml():
    with open(os.path.join(ROOT, ".github", "workflows", "release.yml"), encoding="utf-8") as f:
        return f.read()


def test_prerelease():
    assert re.search(r"^\s+prerelease: true$", _yml(), re.M)


def test_vpk_cung_so_voi_velopack():
    with open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8") as f:
        pip_ver = re.search(r"velopack==([\d.]+)", f.read()).group(1)
    assert f"dotnet tool install -g vpk --version {pip_ver}" in _yml()


def test_dinh_kem_dung_ten_server_doc():
    y = _yml()
    for name in ["releases/releases.win.json", "releases/QuangLuuStudio-*-full.nupkg",
                 "releases/QuangLuuStudio-*-delta.nupkg", "releases/QuangLuuStudio-CaiDat.exe",
                 "installer_output/Setup_QuangLuuStudio_v*.exe"]:
        assert name in y, name


def test_dung_script_build_chung_va_cau_noi():
    y = _yml()
    assert "tools\\build_velopack.ps1" in y and "QuangLuuStudio_Bridge.iss" in y
    assert "QuangLuuStudio_Setup.iss" not in y
