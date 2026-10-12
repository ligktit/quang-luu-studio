# tests/core/test_first_run.py
"""Bước sau-cài chạy trong app (thay [Code] của bộ cài Inno)."""
import json
import subprocess
from unittest.mock import patch

import pytest

import core.config as cfg
from core import first_run


# ── cờ + nhận biết bản cài ──
def test_co_first_run():
    s = {}
    assert not first_run.is_done(s)
    assert first_run.is_done(first_run.mark_done(s))


def test_is_velopack_install(tmp_path):
    cur = tmp_path / "QuangLuuStudio" / "current"
    cur.mkdir(parents=True)
    assert not first_run.is_velopack_install(str(cur))
    (tmp_path / "QuangLuuStudio" / "Update.exe").write_bytes(b"MZ")
    assert first_run.is_velopack_install(str(cur))


# ── DAW mặc định (logic DawMacDinh của .iss) ──
@pytest.mark.parametrize("dirs,expected", [
    ([], "studio_one"),
    (["pf/Steinberg/Cubase 13"], "cubase"),
    (["ad/Steinberg/Cubase 12_64"], "cubase"),
    (["pf/Steinberg/Cubase 13", "ad/PreSonus/Studio One 6"], "studio_one"),
    (["pf/Steinberg/Cubase 13", "pf/PreSonus"], "studio_one"),
])
def test_default_daw(tmp_path, dirs, expected):
    for d in dirs:
        (tmp_path / d).mkdir(parents=True)
    assert first_run.default_daw(str(tmp_path / "pf"), str(tmp_path / "ad")) == expected


# ── file mặc định ──
def test_tao_file_mac_dinh_khong_de_file_co_san(tmp_path):
    (tmp_path / "saved_songs.json").write_text('[{"x": 1}]', encoding="utf-8")
    created = first_run.ensure_default_data_files(str(tmp_path), "cubase")
    assert "saved_songs.json" not in created
    assert json.loads((tmp_path / "saved_songs.json").read_text(encoding="utf-8")) == [{"x": 1}]
    settings = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert settings == {"studio_one_path": "", "browser_path": "",
                        "auto_launch_studio_one": False, "daw_kind": "cubase"}
    for name in ("activation.json", "playlists.json", "tone_cache.json", "manual_timelines.json"):
        assert (tmp_path / name).exists()
    assert not (tmp_path / "settings.json").read_bytes().startswith(b"\xef\xbb\xbf")


# ── setup_all.bat ──
def test_setup_all_thieu_file_tra_am_mot(tmp_path):
    assert first_run.run_setup_all(str(tmp_path)) == first_run.SETUP_ALL_FAILED


def test_setup_all_tra_ma_thoat(tmp_path):
    (tmp_path / "setup_all.bat").write_text("@exit /b 5\r\n", encoding="ascii")
    assert first_run.run_setup_all(str(tmp_path)) == 5


def test_setup_all_timeout_tra_am_mot(tmp_path):
    (tmp_path / "setup_all.bat").write_text("@echo x\r\n", encoding="ascii")
    with patch("core.first_run.subprocess.run",
               side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1)):
        assert first_run.run_setup_all(str(tmp_path), timeout=1) == first_run.SETUP_ALL_FAILED


def test_mo_ta_ma_thoat():
    assert first_run.describe_setup_all_code(0) == []
    msgs = first_run.describe_setup_all_code(1 | 4)
    assert len(msgs) == 2 and "loopMIDI" in msgs[0] and "Reload Scripts" in msgs[1]
    assert "setup_all.bat" in first_run.describe_setup_all_code(first_run.SETUP_ALL_FAILED)[0]


# ── loopMIDI ──
def test_find_loopmidi(tmp_path):
    exe = tmp_path / "pf86" / "Tobias Erichsen" / "loopMIDI" / "loopMIDI.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ")
    env = {"ProgramFiles": str(tmp_path / "pf"), "ProgramFiles(x86)": str(tmp_path / "pf86"),
           "LOCALAPPDATA": str(tmp_path / "lad")}
    assert first_run.find_loopmidi(env) == str(exe)
    assert first_run.find_loopmidi({"ProgramFiles": str(tmp_path / "khong")}) is None


def test_cai_loopmidi_khong_co_winget_tra_false():
    with patch("core.first_run.shutil.which", return_value=None):
        assert first_run.install_loopmidi_elevated() is False


# ── bản cũ ──
def test_find_legacy_install_khong_co_khoa():
    with patch("core.first_run._read_uninstall_location", return_value=None):
        assert first_run.find_legacy_install() is None


def test_find_legacy_install_co_khoa():
    with patch("core.first_run._read_uninstall_location", return_value="C:\\Program Files\\QuangLuuStudio\\"):
        assert first_run.find_legacy_install() == "C:\\Program Files\\QuangLuuStudio"


def test_find_legacy_install_goc_o_giu_gach():
    for loc in ("D:\\", "D:/", "d:\\\\"):
        with patch("core.first_run._read_uninstall_location", return_value=loc):
            assert first_run.find_legacy_install() == loc[0] + ":\\"


def test_cleanup_legacy_nhan_doi_gach_cuoi_goc_o(tmp_path):
    script = tmp_path / "tools" / "don_ban_cu.ps1"
    script.parent.mkdir()
    script.write_text("", encoding="utf-8")
    seen = []
    with patch("core.first_run.find_bundled", return_value=str(script)), \
         patch("core.first_run._run_elevated_ps", side_effect=lambda inner, t: seen.append(inner) or False):
        assert first_run.cleanup_legacy_elevated("D:\\") is False
    assert "'\"D:\\\\\"'" in seen[0]


@pytest.fixture
def _cfg_iso(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled.json"
    bundled.write_text(json.dumps({"midi_cc": {"tone_music": 20, "tone_auto": 21}}), encoding="utf-8")
    monkeypatch.setattr(cfg, "APP_CONFIG_OVERRIDES_FILE", str(tmp_path / "ov.json"))
    monkeypatch.setattr(cfg, "CALIBRATION_OVERRIDES_FILE", str(tmp_path / "cal.json"))
    with patch.object(cfg.AppConfig, "_get_config_path", return_value=str(bundled)):
        yield tmp_path


def test_migrate_cau_hinh_cu_midi_cc_va_calibration(_cfg_iso):
    legacy = _cfg_iso / "legacy"
    legacy.mkdir()
    # BOM như bản do script PowerShell cũ ghi
    (legacy / "app_config.json").write_bytes(b"\xef\xbb\xbf" + json.dumps({
        "midi_cc": {"tone_music": 55, "tone_auto": 21},
        "scale_midi_map": {"Major": 10, "Minor": 18},
    }).encode("utf-8"))
    assert first_run.migrate_legacy_app_config(str(legacy)) is True
    ov = json.loads((_cfg_iso / "ov.json").read_text(encoding="utf-8"))
    assert ov == {"midi_cc": {"tone_music": 55}}
    cal = json.loads((_cfg_iso / "cal.json").read_text(encoding="utf-8"))
    # Minor = 18 trùng mặc định → chỉ phần khác (Major) được chuyển; calibration
    # merge nông nên {"Major": 10} là đủ.
    assert cal == {"scale_midi_map": {"Major": 10}}


def test_migrate_cau_hinh_cu_khong_de_gia_tri_da_co(_cfg_iso):
    legacy = _cfg_iso / "legacy"
    legacy.mkdir()
    (legacy / "app_config.json").write_text(json.dumps({"midi_cc": {"tone_music": 55}}), encoding="utf-8")
    (_cfg_iso / "ov.json").write_text(json.dumps({"midi_cc": {"tone_music": 60}}), encoding="utf-8")
    first_run.migrate_legacy_app_config(str(legacy))
    ov = json.loads((_cfg_iso / "ov.json").read_text(encoding="utf-8"))
    assert ov["midi_cc"]["tone_music"] == 60


def test_migrate_cau_hinh_cu_giong_mac_dinh_thi_khong_ghi(_cfg_iso):
    legacy = _cfg_iso / "legacy"
    legacy.mkdir()
    (legacy / "app_config.json").write_text(json.dumps({"midi_cc": {"tone_music": 20}}), encoding="utf-8")
    assert first_run.migrate_legacy_app_config(str(legacy)) is False
    assert not (_cfg_iso / "ov.json").exists()


def test_migrate_cau_hinh_cu_hong_tra_false(_cfg_iso):
    legacy = _cfg_iso / "legacy"
    legacy.mkdir()
    (legacy / "app_config.json").write_text("{hong", encoding="utf-8")
    assert first_run.migrate_legacy_app_config(str(legacy)) is False


def test_migrate_cau_hinh_cu_accessibility_sang_file_rieng(_cfg_iso, monkeypatch):
    monkeypatch.setattr(cfg, "ACCESSIBILITY_OVERRIDES_FILE", str(_cfg_iso / "acc.json"))
    legacy = _cfg_iso / "legacy"
    legacy.mkdir()
    (legacy / "app_config.json").write_text(json.dumps({
        "accessibility": {"tts_enabled": True, "tts_rate": 200},
    }), encoding="utf-8")
    # giá trị đã có ở file đích được giữ
    (_cfg_iso / "acc.json").write_text(json.dumps({"tts_rate": 150}), encoding="utf-8")
    assert first_run.migrate_legacy_app_config(str(legacy)) is True
    acc = json.loads((_cfg_iso / "acc.json").read_text(encoding="utf-8"))
    assert acc == {"tts_enabled": True, "tts_rate": 150}
    assert not (_cfg_iso / "ov.json").exists()


def test_lenh_nang_quyen_loi_tra_false():
    # Start-Process lỗi (tương tự từ chối UAC) → $p là $null → exit $null = 0 nếu không chặn
    assert first_run._run_elevated_ps(
        "$p = Start-Process 'khong_ton_tai_xyz_qls' -Wait -PassThru; exit $p.ExitCode", 30) is False
    assert first_run._run_elevated_ps("exit 0", 30) is True


def test_setup_all_duong_dan_co_ngoac_va_va(tmp_path):
    d = tmp_path / "thu muc (x86) &t"
    d.mkdir()
    (d / "setup_all.bat").write_text("@exit /b 5\r\n", encoding="ascii")
    assert first_run.run_setup_all(str(d)) == 5
