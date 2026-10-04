"""Giữ script MIDI Remote cho Cubase (cubase/QuangLuu_QuangLuuMIDI.js) khớp với config.

Cùng lý do với tests/test_surface_xml.py: số CC đổi trong core/config.py mà file phía
DAW không đổi theo thì nút bấm trên app im lặng không tác dụng.
"""
import os
import re

from core.config import AppConfig

JS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "cubase", "QuangLuu_QuangLuuMIDI.js",
)


def _js_cc_table():
    """{tên_khoá: cc} trong khối `var CC = { ... }` của script."""
    with open(JS_PATH, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"var CC = \{(.*?)\n\}", src, re.S)
    assert m, "không thấy khối `var CC = {` trong script"
    return {k: int(v) for k, v in re.findall(r"(\w+):\s*(\d+)", m.group(1))}


def test_js_cc_keys_match_config():
    cfg = AppConfig.get_midi_cc()
    js = _js_cc_table()
    unknown = sorted(set(js) - set(cfg))
    assert not unknown, f"khoá trong JS không có trong config: {unknown}"
    wrong = {k: (js[k], cfg[k]) for k in js if js[k] != int(cfg[k])}
    assert not wrong, f"CC lệch giữa JS và config (js, config): {wrong}"


def test_js_declares_every_mode_and_mute_cc():
    # Bản thăm dò chỉ cần NHẬN được mọi CC app gửi (log), nên mọi CC phải xuất hiện trong file.
    with open(JS_PATH, encoding="utf-8") as f:
        src = f.read()
    numbers = {int(n) for n in re.findall(r"\b(\d{1,3})\b", src)}
    needed = {int(v) for v in AppConfig.get_midi_cc().values()}
    for cfg in AppConfig.get_mode_config().values():
        needed.add(int(cfg["cc"]))
    for entries in AppConfig.load().get("mute_multi_cc", {}).values():
        for e in entries:
            needed.add(int(e["cc"]))
    missing = sorted(needed - numbers)
    assert not missing, f"CC app dùng nhưng script Cubase không nhắc tới: {missing}"


def test_js_is_es5():
    # Engine JS của Cubase là ES5: let/const/arrow/template làm script không nạp, lỗi im lặng.
    with open(JS_PATH, encoding="utf-8") as f:
        src = f.read()
    assert not re.search(r"^\s*(let|const)\s", src, re.M)
    assert "=>" not in src
    assert "`" not in src


def test_js_gan_cc_app_vao_tham_so_plugin():
    with open(JS_PATH, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"var THAM_SO_PLUGIN = \{(.*?)\}", src, re.S)
    assert m, "thiếu THAM_SO_PLUGIN"
    idx = {k: int(v) for k, v in re.findall(r"(\w+):\s*(\d+)", m.group(1))}
    assert idx == {"key_root": 6, "scale_type": 7, "tone_auto": 3}
    assert "makeValueBinding(kApp.mSurfaceValue, thamSo[" in src
