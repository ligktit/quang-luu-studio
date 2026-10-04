"""Scale map: override người dùng > mặc định của DAW > app_config."""
import json
from unittest.mock import patch

import pytest

from core import daw
from core.config import AppConfig
import core.config as cfg


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "CALIBRATION_OVERRIDES_FILE", str(tmp_path / "cal.json"))
    daw.bind(None)
    yield
    daw.bind(None)


def test_studio_one_dung_app_config():
    daw.bind({})
    assert AppConfig.get_scale_midi_map()["Major"] == 13
    assert AppConfig.get_scale_values()["major"] == 13


def test_cubase_dung_mac_dinh_ho_so():
    daw.bind({"daw_kind": "cubase"})
    assert AppConfig.get_scale_midi_map() == {"Major": 43, "Minor": 85}
    assert AppConfig.get_scale_values() == {"major": 43, "minor": 85}


def test_override_nguoi_dung_thang_mac_dinh_daw(tmp_path):
    # Người dùng đã tự cân chỉnh scale_midi_map (file overrides có key này) rồi chuyển sang Cubase.
    (tmp_path / "cal.json").write_text(
        json.dumps({"scale_midi_map": {"Major": 50, "Minor": 90}}), encoding="utf-8")
    daw.bind({"daw_kind": "cubase"})
    with patch.object(AppConfig, "load", return_value={
            "scale_midi_map": {"Major": 50, "Minor": 90},   # như load() đã merge override vào
            "scale_values": {"major": 13, "minor": 18}}):
        assert AppConfig.get_scale_midi_map() == {"Major": 50, "Minor": 90}
        # scale_values không có trong override → vẫn lấy mặc định Cubase
        assert AppConfig.get_scale_values() == {"major": 43, "minor": 85}
