"""Quy đổi giá trị Studio One ↔ MIDI cho Dev Mode (core/so_values.py)."""
import pytest

from core import so_values as sv


def test_switch_thuong_va_bypass():
    assert sv.midi_pair({"type": "switch", "bypass": False}) == (127, 0)
    # Bypass On = plugin TẮT → nút app BẬT phải gửi 0.
    assert sv.midi_pair({"type": "switch", "bypass": True}) == (0, 127)


def test_phan_tram():
    assert sv.percent_to_midi(0) == 0
    assert sv.percent_to_midi(100) == 127
    assert sv.percent_to_midi(50) == 64
    assert sv.percent_to_midi(150) == 127   # kẹp dải
    assert sv.midi_pair({"type": "percent", "on": 75, "off": 10}) == (95, 13)


def test_khoang_so():
    spec = {"type": "range", "min": -12, "max": 12, "on": 5, "off": 0}
    on, off = sv.midi_pair(spec)
    assert (on, off) == (90, 64)
    # Studio One đọc ngược lại gần đúng giá trị đã nhập (sai số ≤ nửa nấc MIDI).
    assert abs(sv.midi_to_range(on, -12, 12) - 5) <= 24 / 127 / 2
    # Dải đảo (max < min) vẫn tuyến tính theo đúng chiều.
    assert sv.range_to_midi(10, 10, 0) == 0
    assert sv.range_to_midi(0, 10, 0) == 127
    assert sv.range_to_midi(3, 5, 5) == 0


@pytest.mark.parametrize("count", [2, 3, 4, 5, 7, 12, 24])
def test_danh_sach_moi_muc_doc_nguoc_dung(count):
    for idx in range(count):
        midi = sv.list_to_midi(idx, count)
        x = midi / 127
        # Cả hai cách plugin hay dùng để đổi ngược đều phải ra đúng mục.
        assert round(x * (count - 1)) == idx
        assert min(count - 1, int(x * count)) == idx
        assert sv.midi_to_list(midi, count) == idx


def test_midi_tho_kep_dai():
    assert sv.midi_pair({"type": "midi", "on": 200, "off": -5}) == (127, 0)


def test_suy_ra_tu_cap_midi_cu():
    assert sv.infer_spec(127, 0) == {"type": "switch", "bypass": False}
    assert sv.infer_spec(0, 127) == {"type": "switch", "bypass": True}
    assert sv.infer_spec(100, 20) == {"type": "midi", "on": 100, "off": 20}


def test_resolve_giu_spec_khop_va_bo_spec_lech():
    spec = {"type": "percent", "on": 75, "off": 0}
    assert sv.resolve_spec(spec, 95, 0) == spec
    # Ai đó sửa tay on_value → spec cũ không còn nói đúng MIDI đang gửi.
    assert sv.resolve_spec(spec, 50, 0) == {"type": "midi", "on": 50, "off": 0}
    assert sv.resolve_spec(None, 0, 127) == {"type": "switch", "bypass": True}
    assert sv.resolve_spec({"type": "la"}, 127, 0)["type"] == "switch"


def test_describe():
    assert sv.describe({"type": "switch"}, "on") == "On"
    assert "Bypass Off" in sv.describe({"type": "switch", "bypass": True}, "on")
    assert sv.describe({"type": "list", "options": ["A", "B", "C"], "on": 2}, "on") == "C"
    assert sv.describe({"type": "range", "min": 0, "max": 10, "unit": "dB", "on": 5}, "on").endswith("dB")
