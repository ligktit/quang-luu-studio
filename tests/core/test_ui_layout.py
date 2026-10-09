"""Thao tác thuần trên ui_config cho hộp Quản lý giao diện (Dev Mode)."""
import copy

from core import ui_layout
from core.config import UiConfigManager


def _cfg():
    return copy.deepcopy(UiConfigManager._DEFAULT_UI_CONFIG)


def _ids(entries):
    return [e["id"] for e in entries if isinstance(e, dict)]


def test_is_custom_theo_id_mac_dinh():
    assert not ui_layout.is_custom("tools", {"id": "btn_rescan"})
    assert ui_layout.is_custom("tools", {"id": "custom_ab12cd34"})
    # id built-in của panel khác vẫn tính là custom ở panel này
    assert ui_layout.is_custom("mode", {"id": "btn_rescan"})
    assert not ui_layout.is_custom("tools", "hỏng")


def test_move_len_xuong_va_chan_bien():
    entries = _cfg()["tools"]
    first = entries[0]["id"]
    assert ui_layout.move(entries, 0, -1) == 0
    assert entries[0]["id"] == first
    assert ui_layout.move(entries, 0, 1) == 1
    assert entries[1]["id"] == first
    last = len(entries) - 1
    assert ui_layout.move(entries, last, 1) == last
    assert ui_layout.move(entries, 99, 1) == 99  # index ngoài dải: không làm gì


def test_reorder_theo_ids_giu_phan_tu_la_o_cuoi():
    entries = [{"id": "a"}, "hỏng", {"id": "b"}, {"id": "c"}]
    out = ui_layout.reorder(entries, ["c", "a", "b"])
    assert out[:3] == [{"id": "c"}, {"id": "a"}, {"id": "b"}]
    assert out[3] == "hỏng"


def test_set_hidden():
    entries = _cfg()["mixer"]
    assert ui_layout.set_hidden(entries, "mix_reverb", True)
    assert entries[ui_layout.index_of(entries, "mix_reverb")]["hidden"] is True
    assert ui_layout.set_hidden(entries, "mix_reverb", False)
    assert entries[ui_layout.index_of(entries, "mix_reverb")]["hidden"] is False
    assert not ui_layout.set_hidden(entries, "khong_co", True)


def test_delete_custom_tu_choi_built_in():
    entries = _cfg()["tools"] + [{"id": "custom_1", "label": "X", "cc": 60}]
    assert not ui_layout.delete_custom("tools", entries, "btn_rescan")
    assert "btn_rescan" in _ids(entries)
    assert ui_layout.delete_custom("tools", entries, "custom_1")
    assert "custom_1" not in _ids(entries)
    assert not ui_layout.delete_custom("tools", entries, "custom_1")


def test_reset_panel_chi_doi_panel_do():
    cfg = _cfg()
    cfg["tools"] = [{"id": "custom_1"}]
    cfg["mode"][0]["hidden"] = True
    ui_layout.reset_panel(cfg, "tools")
    assert _ids(cfg["tools"]) == _ids(UiConfigManager._DEFAULT_UI_CONFIG["tools"])
    assert cfg["mode"][0]["hidden"] is True
    # bản sao sâu: sửa cfg không làm bẩn mặc định
    cfg["tools"][0]["label"] = "Đổi"
    assert UiConfigManager._DEFAULT_UI_CONFIG["tools"][0]["label"] != "Đổi"


def test_is_valid_color():
    assert ui_layout.is_valid_color("#abc")
    assert ui_layout.is_valid_color("#14B8A6")
    assert ui_layout.is_valid_color(" #14b8a6 ")
    assert not ui_layout.is_valid_color("#14b8a")
    assert not ui_layout.is_valid_color("teal")
    assert ui_layout.is_valid_color("teal", token_names={"teal"})


def test_conflict_custom_va_built_in():
    cfg = _cfg()
    cfg["tools"].append({"id": "custom_1", "label": "Vang HT", "cc": 60})
    midi_cc = {"mix_music": 20, "mode": 30}
    assert ui_layout.find_cc_conflicts(60, cfg, midi_cc) == ["Vang HT (Tools)"]
    # CC built-in dạng tên → hiện nhãn widget, không lặp lại key hệ thống
    assert ui_layout.find_cc_conflicts(20, cfg, midi_cc) == ["Nhạc (Mixer)"]
    assert ui_layout.find_cc_conflicts(30, cfg, midi_cc) == ["CC hệ thống “mode”"]
    assert ui_layout.find_cc_conflicts(99, cfg, midi_cc) == []
    assert ui_layout.find_cc_conflicts(-1, cfg, midi_cc) == []


def test_conflict_loai_chinh_no_va_mode_config():
    cfg = _cfg()
    cfg["tools"].append({"id": "custom_1", "label": "Vang HT", "cc": 60})
    modes = {"Lofi": {"cc": 37, "on_value": 127, "off_value": 0}}
    assert ui_layout.find_cc_conflicts(60, cfg, {}, exclude_id="custom_1") == []
    assert ui_layout.find_cc_conflicts(37, cfg, {}, mode_config=modes) == ["Mode Lofi"]
    # Đang sửa chính nút Lofi → không tự cảnh báo CC mode của nó
    assert ui_layout.find_cc_conflicts(37, cfg, {}, exclude_id="mode_lofi",
                                       mode_config=modes) == []


def test_conflict_midi_cc_dang_chuoi():
    assert ui_layout.find_cc_conflicts(20, {}, {"mix_music": "20"}) == ["CC hệ thống “mix_music”"]


def test_bo_qua_phan_tu_hong():
    cfg = {"mixer": ["hỏng", None, {"id": "custom_1", "label": "A", "cc": True}],
           "tools": "không phải list"}
    assert ui_layout.find_cc_conflicts(1, cfg, {"x": None}) == []
    assert ui_layout.index_of(cfg["mixer"], "custom_1") == 2
    assert not ui_layout.set_hidden(cfg["mixer"], "khong_co", True)


def test_mixer_slider_on_cc():
    cfg = _cfg()
    cfg["mixer"].append({"id": "custom_s", "type": "slider", "label": "Bass", "cc": 70})
    cfg["tools"].append({"id": "custom_b", "type": "button", "label": "Nút", "cc": 71})
    midi_cc = {"mix_music": 20}
    assert ui_layout.mixer_slider_on_cc(70, cfg, midi_cc) == "Bass"
    assert ui_layout.mixer_slider_on_cc(20, cfg, midi_cc) == "Nhạc"   # tên built-in tra midi_cc
    assert ui_layout.mixer_slider_on_cc(70, cfg, midi_cc, exclude_id="custom_s") is None
    assert ui_layout.mixer_slider_on_cc(71, cfg, midi_cc) is None     # nút Tools không tính
    assert ui_layout.mixer_slider_on_cc(-1, cfg, midi_cc) is None
