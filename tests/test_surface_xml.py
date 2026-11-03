"""Giữ template Studio One (QuangLuuMIDI.surface.xml) đồng bộ với config.

Bối cảnh: tone_auto/fix_meo/mode_danca từng được TÁCH sang CC 40/45/46 trong
core/config.py nhưng surface.xml không đổi theo → 3 nút đó không có control nào
bên Studio One, bấm trên app thì DAW không nhận. Lỗi im lặng, không exception.

Các test dưới đây bắt mọi lệch pha giữa hai bên ngay tại CI.
"""
import os
import re
import xml.etree.ElementTree as ET

import pytest

from core.config import AppConfig
from core.mic2 import shared_cc_numbers

SURFACE_XML = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "studio_one", "QuangLuuMIDI.surface.xml",
)


def _declared_addresses(channel="0"):
    """{cc_number: [control_name, ...]} của các control trên kênh MIDI `channel` (0 = kênh 1)."""
    root = ET.parse(SURFACE_XML).getroot()
    out = {}
    for ctrl in root.iter("Control"):
        for msg in ctrl.iter("MidiMessage"):
            addr = msg.get("address")
            if addr is not None and msg.get("channel") == channel:
                out.setdefault(int(addr), []).append(ctrl.get("name"))
    return out


def _app_ccs():
    """{cc_number: [nguồn, ...]} — mọi CC app có thể GỬI hoặc NHẬN."""
    out = {}
    for key, val in AppConfig.get_midi_cc().items():
        out.setdefault(int(val), []).append(key)
    for mode, cfg in AppConfig.get_mode_config().items():
        out.setdefault(int(cfg["cc"]), []).append(f"mode_config[{mode}]")
    for chan, entries in AppConfig.load().get("mute_multi_cc", {}).items():
        for e in entries:
            out.setdefault(int(e["cc"]), []).append(f"mute_multi_cc[{chan}]")
    return out


def test_surface_xml_is_well_formed():
    ET.parse(SURFACE_XML)  # ném ParseError nếu hỏng


def test_every_app_cc_has_a_control():
    # Thiếu control = nút bấm trên app nhưng Studio One không map được.
    declared = _declared_addresses()
    missing = {cc: src for cc, src in _app_ccs().items() if cc not in declared}
    assert not missing, (
        "CC app dùng nhưng surface.xml chưa khai báo: "
        + ", ".join(f"CC {cc} ({'/'.join(s)})" for cc, s in sorted(missing.items()))
    )


def test_no_orphan_controls():
    # Control thừa = kỹ thuật viên map xong nhưng app không bao giờ gửi.
    app = _app_ccs()
    orphans = {cc: names for cc, names in _declared_addresses().items() if cc not in app}
    assert not orphans, (
        "surface.xml khai báo CC mà app không dùng: "
        + ", ".join(f"CC {cc} ({'/'.join(n)})" for cc, n in sorted(orphans.items()))
    )


def test_every_message_names_its_channel():
    # Kiểm trên máy khách Studio One 5.0.2 (2026-11-02): control không ghi `channel`
    # nhận CC đó trên MỌI kênh (lệnh Mic 2 rơi vào link Mic 1), còn status "#B1"
    # không được nhận. Dạng Studio One tự ghi khi learn: status="#B0" channel="N".
    root = ET.parse(SURFACE_XML).getroot()
    bad = [
        c.get("name") for c in root.iter("Control") for m in c.iter("MidiMessage")
        if m.get("status") != "#B0" or m.get("channel") not in ("0", "1")
    ]
    assert not bad, f"MidiMessage phải là status=#B0 + channel 0/1: {bad}"


def test_no_duplicate_control_addresses():
    # Hai control cùng address → Studio One nhận nhập nhằng, đúng kiểu lỗi
    # "shared CC" mà tone_auto/fix_meo từng mắc.
    # Xét theo (kênh, address): cùng CC khác kênh MIDI là hợp lệ (mic 2).
    dupes = {
        (ch, cc): n
        for ch in ("0", "1")
        for cc, n in _declared_addresses(ch).items()
        if len(n) > 1
    }
    assert not dupes, f"Nhiều control trùng (kênh, CC): {dupes}"


def test_no_duplicate_control_names():
    root = ET.parse(SURFACE_XML).getroot()
    names = [c.get("name") for c in root.iter("Control")]
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"Tên control bị trùng: {dupes}"


@pytest.mark.parametrize("key,title", [
    ("tone_auto", "Auto-Tune"),
    ("fix_meo", "Fix Méo"),
    ("mode_danca", "Mode Dân Ca"),
    ("be", "Bè"),
])
def test_key_buttons_mapped_to_expected_control(key, title):
    # Regression cụ thể cho 3 nút từng bị bỏ quên + nút Bè mới.
    cc = int(AppConfig.get_midi_cc()[key])
    root = ET.parse(SURFACE_XML).getroot()
    for ctrl in root.iter("Control"):
        for msg in ctrl.iter("MidiMessage"):
            if msg.get("address") == str(cc):
                assert ctrl.get("title") == title
                return
    pytest.fail(f"Không tìm thấy control cho {key} (CC {cc})")


def test_header_comment_lists_actual_ccs():
    # Bảng CC trong comment đầu file là thứ kỹ thuật viên đọc khi map tay —
    # sai bảng này thì họ map nhầm dù XML đúng.
    raw = open(SURFACE_XML, encoding="utf-8").read()
    header = raw.split("-->", 1)[0]
    documented = {int(m) for m in re.findall(r"CC (\d+)", header)}
    documented |= {
        cc
        for lo, hi in re.findall(r"CC (\d+)-(\d+)", header)
        for cc in range(int(lo), int(hi) + 1)
    }
    undocumented = set(_app_ccs()) - documented
    assert not undocumented, f"Comment đầu file chưa nhắc tới CC: {sorted(undocumented)}"


def test_mic2_controls_match_shared_set():
    # Kênh 2 = đúng tập CC phát đôi (config) + CC riêng từng mic mà kênh Mic 2 /
    # Vang Mic 2 gửi thẳng kênh 2: mức/tắt Mic, mức/tắt Vang, CC phụ của Vang.
    midi_cc = AppConfig.get_midi_cc()
    per_mic = {midi_cc[k] for k in ("mix_mic", "mute_mic", "mix_reverb", "mute_reverb")}
    per_mic |= {e["cc"] for e in AppConfig.get_mute_multi_cc().get("mix_reverb", [])}
    expected = set(shared_cc_numbers(
        midi_cc, AppConfig.get_mic2_shared_cc(),
        AppConfig.get_mode_config(), AppConfig.get_mute_multi_cc(),
    )) | per_mic
    assert set(_declared_addresses("1")) == expected


def test_mic2_controls_receive_only():
    root = ET.parse(SURFACE_XML).getroot()
    bad = [
        c.get("name") for c in root.iter("Control")
        if any(m.get("channel") == "1" for m in c.iter("MidiMessage"))
        and "transmit" in (c.get("options") or "")
    ]
    assert not bad, f"Control kênh 2 không được có transmit: {bad}"
