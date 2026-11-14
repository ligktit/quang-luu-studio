"""app_config.json cạnh exe chỉ là MẶC ĐỊNH; phần người dùng đổi nằm ở
DATA_DIR/app_config_overrides.json (thư mục cài bị thay mỗi lần cập nhật)."""
import json
from unittest.mock import patch

import pytest

import core.config as cfg
from core.config import AppConfig, config_diff


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    bundled = tmp_path / "app" / "app_config.json"
    bundled.parent.mkdir()
    bundled.write_text(json.dumps({"midi_port_name": "Goc", "midi_cc": {"tone_music": 20}}),
                       encoding="utf-8")
    monkeypatch.setattr(cfg, "APP_CONFIG_OVERRIDES_FILE", str(tmp_path / "ov.json"))
    monkeypatch.setattr(cfg, "ACCESSIBILITY_OVERRIDES_FILE", str(tmp_path / "a11y.json"))
    monkeypatch.setattr(cfg, "CALIBRATION_OVERRIDES_FILE", str(tmp_path / "cal.json"))
    AppConfig._data = None
    with patch.object(AppConfig, "_get_config_path", return_value=str(bundled)):
        yield tmp_path
    AppConfig._data = None


def test_overrides_de_len_ban_dong_goi(_iso):
    (_iso / "ov.json").write_text(json.dumps({"midi_cc": {"tone_music": 55}}), encoding="utf-8")
    data = AppConfig.load()
    assert data["midi_cc"]["tone_music"] == 55
    assert data["midi_port_name"] == "Goc"
    # khoá con khác của midi_cc vẫn lấy từ mặc định
    assert "tone_auto" in data["midi_cc"]


def test_save_chi_ghi_phan_khac_vao_overrides(_iso):
    AppConfig.update("youtube_cookie_browser", "edge")
    AppConfig.update("midi_cc", {"tone_music": 21})
    assert AppConfig.save() is True
    saved = json.loads((_iso / "ov.json").read_text(encoding="utf-8"))
    assert saved == {"youtube_cookie_browser": "edge", "midi_cc": {"tone_music": 21}}
    # bản đóng gói không bị đụng
    bundled = json.loads((_iso / "app" / "app_config.json").read_text(encoding="utf-8"))
    assert bundled == {"midi_port_name": "Goc", "midi_cc": {"tone_music": 20}}


def test_dat_lai_gia_tri_goc_thi_khoa_bien_khoi_overrides(_iso):
    AppConfig.update("youtube_cookie_browser", "edge")
    AppConfig.save()
    AppConfig.update("youtube_cookie_browser", cfg._DEFAULT_APP_CONFIG["youtube_cookie_browser"])
    AppConfig.save()
    saved = json.loads((_iso / "ov.json").read_text(encoding="utf-8"))
    assert "youtube_cookie_browser" not in saved


def test_save_khong_ghi_khoa_calibration(_iso):
    AppConfig.update("scale_midi_map", {"Major": 99})
    AppConfig.save()
    saved = json.loads((_iso / "ov.json").read_text(encoding="utf-8"))
    assert "scale_midi_map" not in saved


def test_overrides_hong_van_chay(_iso):
    (_iso / "ov.json").write_text("{khong phai json", encoding="utf-8")
    data = AppConfig.load()
    assert data["midi_port_name"] == "Goc"
    assert data["midi_cc"]["tone_music"] == 20


def test_overrides_co_bom_van_doc(_iso):
    (_iso / "ov.json").write_bytes(b"\xef\xbb\xbf" + json.dumps({"midi_port_name": "X"}).encode())
    assert AppConfig.load()["midi_port_name"] == "X"


def test_config_diff_dict_long_nhau():
    base = {"a": 1, "d": {"x": 1, "y": 2}, "e": [1]}
    data = {"a": 1, "d": {"x": 1, "y": 3}, "e": [1, 2], "moi": True}
    assert config_diff(base, data) == {"d": {"y": 3}, "e": [1, 2], "moi": True}


def test_save_khong_ghi_accessibility(_iso):
    (_iso / "a11y.json").write_text(json.dumps({"font_scale": 1.5}), encoding="utf-8")
    AppConfig.load()
    assert AppConfig.save() is True
    saved = json.loads((_iso / "ov.json").read_text(encoding="utf-8"))
    assert "accessibility" not in saved
    # reset file accessibility riêng → không bị bản sao cũ trong overrides che
    (_iso / "a11y.json").unlink()
    AppConfig._data = None
    data = AppConfig.load()
    assert data["accessibility"]["font_scale"] == cfg._DEFAULT_APP_CONFIG["accessibility"]["font_scale"]
