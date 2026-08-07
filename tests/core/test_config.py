import pytest
import os
import json
from unittest.mock import patch, mock_open

from core.config import AppConfig, ConfigManager, _DEFAULT_APP_CONFIG

# Ensure tests don't affect real data
@pytest.fixture(autouse=True)
def reset_appconfig():
    AppConfig._data = None
    yield
    AppConfig._data = None

# --- AppConfig Tests ---

def test_appconfig_load_valid(tmp_path):
    # C-01: `load()` đọc file JSON hợp lệ
    config_file = tmp_path / "app_config.json"
    valid_data = {"midi_port_name": "TestPort"}
    config_file.write_text(json.dumps(valid_data), encoding="utf-8")
    
    with patch("core.config.AppConfig._get_config_path", return_value=str(config_file)):
        data = AppConfig.load()
        assert data["midi_port_name"] == "TestPort"
        assert "midi_cc" in data  # merged with default

def test_appconfig_load_not_exists(tmp_path):
    # C-02: `load()` khi file không tồn tại
    config_file = tmp_path / "non_existent.json"
    with patch("core.config.AppConfig._get_config_path", return_value=str(config_file)):
        data = AppConfig.load()
        assert data["midi_port_name"] == _DEFAULT_APP_CONFIG["midi_port_name"]

def test_appconfig_load_malformed(tmp_path):
    # C-03: `load()` file JSON bị hỏng
    config_file = tmp_path / "app_config.json"
    config_file.write_text("NOT A JSON STRING", encoding="utf-8")
    
    with patch("core.config.AppConfig._get_config_path", return_value=str(config_file)):
        data = AppConfig.load()
        assert data["midi_port_name"] == _DEFAULT_APP_CONFIG["midi_port_name"]

def test_appconfig_get_existing(tmp_path):
    # C-04: `get(key)` với key tồn tại
    with patch("core.config.AppConfig._get_config_path", return_value="dummy"):
        assert AppConfig.get("midi_port_name") == _DEFAULT_APP_CONFIG["midi_port_name"]

def test_appconfig_get_non_existing(tmp_path):
    # C-05: `get(key, default)` với key không tồn tại
    with patch("core.config.AppConfig._get_config_path", return_value="dummy"):
        assert AppConfig.get("non_existent_key", "default_val") == "default_val"

def test_appconfig_get_midi_cc():
    # C-06: `get_midi_cc()`
    with patch("core.config.AppConfig._get_config_path", return_value="dummy"):
        cc = AppConfig.get_midi_cc()
        assert "tone_music" in cc

def test_appconfig_get_scale_values():
    # C-07: `get_scale_values()`
    with patch("core.config.AppConfig._get_config_path", return_value="dummy"):
        sv = AppConfig.get_scale_values()
        assert "major" in sv and "minor" in sv

def test_appconfig_get_key_midi_map():
    # C-08: `get_key_midi_map()`
    with patch("core.config.AppConfig._get_config_path", return_value="dummy"):
        km = AppConfig.get_key_midi_map()
        assert "C" in km and km["C"] == 0

def test_appconfig_get_scale_midi_map():
    # C-09: `get_scale_midi_map()`
    with patch("core.config.AppConfig._get_config_path", return_value="dummy"):
        sm = AppConfig.get_scale_midi_map()
        assert "Major" in sm and sm["Major"] == 13

def test_appconfig_get_mode_midi_map():
    # C-10: `get_mode_midi_map()`
    with patch("core.config.AppConfig._get_config_path", return_value="dummy"):
        mm = AppConfig.get_mode_midi_map()
        assert "Fix Méo" in mm

def test_appconfig_update_and_save(tmp_path):
    # C-11: `update(key, value)` + `save()`
    config_file = tmp_path / "app_config.json"
    with patch("core.config.AppConfig._get_config_path", return_value=str(config_file)):
        AppConfig.update("midi_port_name", "NewPort")
        AppConfig.save()
        
        saved_data = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved_data["midi_port_name"] == "NewPort"

def test_appconfig_reload(tmp_path):
    # C-12: `reload()`
    config_file = tmp_path / "app_config.json"
    with patch("core.config.AppConfig._get_config_path", return_value=str(config_file)):
        config_file.write_text(json.dumps({"midi_port_name": "Port1"}), encoding="utf-8")
        AppConfig.load()
        
        # Sửa file ngoài
        config_file.write_text(json.dumps({"midi_port_name": "Port2"}), encoding="utf-8")
        AppConfig.reload()
        
        assert AppConfig.get("midi_port_name") == "Port2"

def test_appconfig_singleton():
    # C-13: Singleton: gọi 2 lần
    with patch("core.config.AppConfig._get_config_path", return_value="dummy"):
        data1 = AppConfig.load()
        data2 = AppConfig.load()
        assert data1 is data2

# --- ConfigManager Tests ---

def test_configmanager_load_existing(tmp_path):
    # C-14: `load_settings()` file tồn tại
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"auto_close": True}), encoding="utf-8")
    
    with patch("core.config.SETTINGS_FILE", str(settings_file)):
        settings = ConfigManager.load_settings()
        assert settings["auto_close"] is True

def test_configmanager_load_not_existing(tmp_path):
    # C-15: `load_settings()` file không tồn tại
    settings_file = tmp_path / "non_existent.json"
    with patch("core.config.SETTINGS_FILE", str(settings_file)):
        settings = ConfigManager.load_settings()
        assert settings == {}

def test_configmanager_save(tmp_path):
    # C-16: `save_settings(settings)`
    settings_file = tmp_path / "settings.json"
    with patch("core.config.SETTINGS_FILE", str(settings_file)):
        success = ConfigManager.save_settings({"theme": "dark"})
        assert success is True
        assert settings_file.exists()
        saved = json.loads(settings_file.read_text(encoding="utf-8"))
        assert saved["theme"] == "dark"

def test_configmanager_round_trip(tmp_path):
    # C-17: Round-trip: save rồi load
    settings_file = tmp_path / "settings.json"
    with patch("core.config.SETTINGS_FILE", str(settings_file)):
        original = {"volume": 80, "mute": False}
        ConfigManager.save_settings(original)
        loaded = ConfigManager.load_settings()
        assert loaded == original


def test_appconfig_get_mode_config():
    with patch("core.config.AppConfig._get_config_path", return_value="dummy"):
        mode_cfg = AppConfig.get_mode_config()
        assert "Lofi" in mode_cfg
        assert "cc" in mode_cfg["Lofi"]
        assert mode_cfg["Lofi"]["cc"] == 37


# --- UiConfigManager: trộn widget mặc định mới vào file của user ---

def test_ui_config_merges_new_default_widgets(tmp_path):
    # Máy đã dùng app từ trước có ui_config.json THIẾU nút mới thêm ở bản cập
    # nhật. Nếu chỉ đọc nguyên file thì nút đó không bao giờ hiện ra.
    from core.config import UiConfigManager

    ui_file = tmp_path / "ui_config.json"
    old_config = {
        "mixer": [{"id": "mix_music", "type": "slider", "label": "Nhạc"}],
        "tools": [{"id": "btn_be", "type": "button", "label": "Bè"}],
        "mode":  [{"id": "mode_lofi", "type": "button", "label": "Lofi"}],
    }
    ui_file.write_text(json.dumps(old_config), encoding="utf-8")

    with patch("core.config.UI_CONFIG_FILE", str(ui_file)):
        merged = UiConfigManager.load_ui_config()

    tool_ids = [t["id"] for t in merged["tools"]]
    assert "btn_tat_on" in tool_ids, "Nút Tắt Ồn phải được bổ sung cho file cũ"
    # Entry user đã có: giữ nguyên, không nhân bản
    assert tool_ids.count("btn_be") == 1
    # Panel khác cũng được bù cho đủ widget mặc định
    assert "mix_mic" in [m["id"] for m in merged["mixer"]]


def test_ui_config_keeps_user_customisation(tmp_path):
    # Không được ghi đè nhãn/màu user đã sửa, cũng không "bật lại" widget đã ẩn.
    from core.config import UiConfigManager

    ui_file = tmp_path / "ui_config.json"
    ui_file.write_text(json.dumps({
        "tools": [
            {"id": "btn_be", "type": "button", "label": "Bè của tôi", "color": "#123456"},
            {"id": "btn_tat_on", "type": "button", "label": "Tắt Ồn", "hidden": True},
        ],
    }), encoding="utf-8")

    with patch("core.config.UI_CONFIG_FILE", str(ui_file)):
        merged = UiConfigManager.load_ui_config()

    by_id = {t["id"]: t for t in merged["tools"]}
    assert by_id["btn_be"]["label"] == "Bè của tôi"
    assert by_id["btn_be"]["color"] == "#123456"
    assert by_id["btn_tat_on"]["hidden"] is True

