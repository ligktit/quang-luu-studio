"""Xuất/nhập cấu hình Dev Mode (ui_config + calibration_overrides)."""
import json
import os
from datetime import datetime
from unittest.mock import patch

import pytest

import core.config as cfg
from core import devmode_backup as bk


@pytest.fixture
def files(tmp_path, monkeypatch):
    ui = tmp_path / "ui_config.json"
    cal = tmp_path / "calibration_overrides.json"
    monkeypatch.setattr(cfg, "UI_CONFIG_FILE", str(ui))
    monkeypatch.setattr(cfg, "CALIBRATION_OVERRIDES_FILE", str(cal))
    yield ui, cal
    cfg.AppConfig.reload()


def _write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_default_filename():
    assert bk.default_filename(datetime(2026, 10, 9, 14, 5)) == "quangluu-giaodien-20261009-1405.json"


def test_round_trip_giu_key_la_cua_calibration(files, tmp_path):
    ui, cal = files
    layout = cfg.UiConfigManager.load_ui_config()
    layout["tools"][1]["hidden"] = True
    _write(ui, layout)
    _write(cal, {"mode_config": {"Lofi": {"cc": 37}}, "key_la_cua_may_khach": {"x": 1}})

    out = tmp_path / "out" / "sao-luu.json"
    out.parent.mkdir()
    bk.export_backup(str(out))
    data = bk.read_backup(str(out))
    assert data["format"] == "quangluu-devmode-backup"
    assert data["calibration_overrides"]["key_la_cua_may_khach"] == {"x": 1}

    # Đổi máy: xoá cấu hình rồi khôi phục
    os.remove(ui)
    os.remove(cal)
    assert bk.restore_backup(data) == []  # không có file cũ → không có .bak
    assert _read(ui)["tools"][1]["hidden"] is True
    assert _read(cal)["key_la_cua_may_khach"] == {"x": 1}


def test_restore_tao_bak_truoc_khi_ghi(files):
    ui, cal = files
    _write(ui, {"tools": [{"id": "custom_cu"}]})
    _write(cal, {"toggle_invert": {"be": True}})
    backup = {"format": "quangluu-devmode-backup", "format_version": 1,
              "ui_config": {"tools": [{"id": "custom_moi"}]}, "calibration_overrides": {}}
    baks = bk.restore_backup(backup)
    assert len(baks) == 2
    assert all(os.path.dirname(b) == os.path.join(str(ui.parent), "backups") for b in baks)
    names = sorted(os.path.basename(b).split(".")[0] for b in baks)
    assert names == ["calibration_overrides", "ui_config"]
    ui_bak = next(b for b in baks if os.path.basename(b).startswith("ui_config"))
    with open(ui_bak, encoding="utf-8") as f:
        assert json.load(f) == {"tools": [{"id": "custom_cu"}]}
    assert _read(ui) == {"tools": [{"id": "custom_moi"}]}


def test_restore_thieu_panel_van_du_3_panel(files):
    backup = {"format": "quangluu-devmode-backup", "format_version": 1,
              "ui_config": {"tools": [{"id": "custom_1", "label": "X", "cc": 60}]},
              "calibration_overrides": {}}
    bk.restore_backup(backup)
    loaded = cfg.UiConfigManager.load_ui_config()
    assert set(loaded) >= {"mixer", "tools", "mode"}
    assert loaded["mixer"]  # built-in được nối lại
    assert loaded["tools"][0]["id"] == "custom_1"


def test_restore_ghi_loi_tra_lai_nhu_cu(files):
    ui, cal = files
    _write(ui, {"tools": [{"id": "custom_cu"}]})
    _write(cal, {"toggle_invert": {"be": True}})
    backup = {"format": "quangluu-devmode-backup", "format_version": 1,
              "ui_config": {"tools": []}, "calibration_overrides": {"mode_config": {}}}
    real = bk.atomic_write_json
    calls = []

    def flaky(path, data, *a, **k):
        calls.append(path)
        if len(calls) == 2:
            raise OSError("đĩa đầy")
        return real(path, data, *a, **k)

    with patch.object(bk, "atomic_write_json", side_effect=flaky):
        with pytest.raises(bk.BackupError) as ei:
            bk.restore_backup(backup)
    assert "đã trả lại như cũ" in str(ei.value)
    assert _read(ui) == {"tools": [{"id": "custom_cu"}]}
    assert _read(cal) == {"toggle_invert": {"be": True}}


@pytest.mark.parametrize("content, msg", [
    ("{không phải json", "Không đọc được file"),
    (json.dumps({"format": "khac"}), "không phải bản sao lưu"),
    (json.dumps({"format": "quangluu-devmode-backup", "format_version": 2,
                 "ui_config": {"tools": []}}), "bản app mới hơn"),
    (json.dumps({"format": "quangluu-devmode-backup", "format_version": 1,
                 "ui_config": {"khac": []}}), "không có cấu hình giao diện"),
    (json.dumps({"format": "quangluu-devmode-backup", "format_version": 1,
                 "ui_config": {"tools": []}, "calibration_overrides": [1]}), "cân chỉnh MIDI"),
])
def test_read_backup_tu_choi_file_sai(tmp_path, content, msg):
    p = tmp_path / "x.json"
    p.write_text(content, encoding="utf-8")
    with pytest.raises(bk.BackupError) as ei:
        bk.read_backup(str(p))
    assert msg in str(ei.value)


def test_read_backup_chap_nhan_bom(tmp_path):
    p = tmp_path / "x.json"
    data = {"format": "quangluu-devmode-backup", "format_version": 1, "ui_config": {"tools": []}}
    p.write_text(json.dumps(data), encoding="utf-8-sig")
    out = bk.read_backup(str(p))
    assert out["calibration_overrides"] == {}


def test_summarize_dem_widget_an():
    backup = {"app_version": "1.8.0", "exported_at": "2026-10-09T14:30:00",
              "ui_config": {"mixer": [{"id": "a"}, {"id": "b", "hidden": True}],
                            "tools": [{"id": "c"}]},
              "calibration_overrides": {"mode_config": {}, "toggle_invert": {}}}
    text = bk.summarize(backup)
    assert "Mixer: 2 widget (1 ẩn)" in text
    assert "Tools: 1 widget" in text
    assert "Mode" not in text
    assert "2 mục cân chỉnh MIDI" in text
    assert "v1.8.0 lúc 09/10/2026 14:30" in text


def test_read_backup_bo_phan_tu_khong_phai_dict(tmp_path):
    """Phần tử hỏng trong panel làm dựng panel crash → lọc bỏ ngay khi đọc file."""
    p = tmp_path / "x.json"
    data = {"format": "quangluu-devmode-backup", "format_version": 1,
            "ui_config": {"tools": [None, "x", {"id": "custom_1"}], "mixer": "không phải list"}}
    p.write_text(json.dumps(data), encoding="utf-8")
    out = bk.read_backup(str(p))
    assert out["ui_config"]["tools"] == [{"id": "custom_1"}]
