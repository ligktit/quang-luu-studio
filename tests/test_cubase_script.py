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


def _js_ho_so_plugin():
    with open(JS_PATH, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"var HO_SO_PLUGIN = \[(.*?)\n\]", src, re.S)
    assert m, "thiếu HO_SO_PLUGIN"
    ho_so = {}
    for ten, body in re.findall(r"\{\s*ten:\s*'([^']+)'(.*?)\}", m.group(1), re.S):
        ho_so[ten] = {k: int(v) for k, v in re.findall(r"(\w+):\s*(-?\d+)", body)}
    return ho_so


def test_js_gan_cc_app_vao_tham_so_plugin():
    # Chỉ số đo trên máy thật: Pitch Correct (Cubase 13.0.10, 2026-10-04),
    # Auto-Tune Pro 11 VST3 (máy khách, 2026-10-06). tone_auto = -1: nút On của insert slot.
    ho_so = _js_ho_so_plugin()
    assert list(ho_so) == ["Pitch Correct", "Auto-Tune Pro"], "hồ sơ đầu tiên là mặc định khi plugin lạ"
    assert ho_so["Pitch Correct"] == {"key_root": 6, "scale_type": 7, "tone_auto": 3}
    # Auto-Tune Pro: tham số 162 "Modern Scale" là Scale trên GUI; tham số 1 "Scale" là bảng cổ điển, không dùng.
    assert ho_so["Auto-Tune Pro"] == {"key_root": 2, "scale_type": 162, "tone_auto": -1}
    m = re.search(r"var SO_THAM_SO = (\d+)", src := open(JS_PATH, encoding="utf-8").read())
    assert m and int(m.group(1)) > 162, "SO_THAM_SO phải phủ chỉ số 162 của Auto-Tune Pro"
    with open(JS_PATH, encoding="utf-8") as f:
        src = f.read()
    # Mỗi hồ sơ có biến riêng bind vào tham số; knob CC của app chỉ chuyển giá trị sang hồ sơ đang chọn.
    assert "makeCustomValueVariable('ql_' + so + '_' + khoa)" in src
    assert "page.makeValueBinding(bien, idx >= 0 ? thamSo[idx] : insertViewer.mOn)" in src
    assert "hoSoHienTai.bien[k].setProcessValue(activeDevice, value)" in src
    assert "chonHoSoPlugin(pluginName)" in src
    # Reload Scripts không gọi lại mOnChangePluginIdentity → chọn hồ sơ theo tên tham số "Key".
    assert "if (objectTitle === 'Key') chonHoSoTheoChiSoKey(i)" in src
    assert "makeSubPage" not in src, "sub page: mActivate.trigger() từ callback không đổi binding"


def test_js_gan_tone_giong_vao_soundshifter():
    # Kênh NHAC: Waves SoundShifter Pitch Stereo (máy khách 2026-10-07), Semitones = tham số 4.
    with open(JS_PATH, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"var HO_SO_NHAC = \[(.*?)\n\]", src, re.S)
    assert m, "thiếu HO_SO_NHAC"
    assert re.search(r"ten:\s*'SoundShifter'.*?tone_voice:\s*4\b", m.group(1), re.S)
    assert "makeInsertEffectViewer('QuangLuuInsertNhac')" in src
    assert "page.makeValueBinding(bien, thamSoNhac[hoSo[khoa]])" in src


def test_js_gom_kenh_theo_ten():
    # Bài khách có 3 FX (Vang dai / Delay / Vang ngan): fader+mute Vang của app điều khiển cả nhóm theo tên.
    with open(JS_PATH, encoding="utf-8") as f:
        src = f.read()
    assert "function nhomTheoTen(ten)" in src
    for tu in ("'vang'", "'delay'", "'reverb'", "'giong'", "'beat'"):
        assert tu in src, f"nhomTheoTen thiếu từ khoá {tu}"
    assert "function datFaderNhom(activeDevice, nhom, value)" in src
    assert "function datMuteNhom(activeDevice, nhom, value)" in src
    assert "function doLech(nhom)" in src, "kênh sau giữ chênh lệch so với kênh đầu nhóm"
    assert "mocNhom" not in src, "mốc tại CC đầu tiên sai khi app đã ở -inf trước khi script nạp"
    assert "makeCustomValueVariable('qlk_fader_' + idx)" in src
    # CC fader/mute của app vẫn đúng với config (bảng CC được test riêng ở trên).
    assert "faderCCTheoNhom = { nhac: CC.mix_music, mic: CC.mix_mic, vang: CC.mix_reverb, be: CC.mix_backing }" in src
