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
    assert ho_so["Pitch Correct"] == {"key_root": 6, "scale_type": 7, "tone_auto": 3, "be": -1, "scale_dorian": -1, "scale_chromatic": -1, "scale_classic": -1}
    # Auto-Tune Pro: tham số 162 "Modern Scale" là Scale trên GUI; tham số 1 "Scale" là bảng cổ điển, không dùng.
    assert ho_so["Auto-Tune Pro"] == {"key_root": 2, "scale_type": 162, "tone_auto": -1, "be": 155, "be_la_bypass": 1, "scale_dorian": 45, "scale_chromatic": 2, "scale_classic": 1}
    m = re.search(r"var SO_THAM_SO = (\d+)", src := open(JS_PATH, encoding="utf-8").read())
    assert m and int(m.group(1)) > 162, "SO_THAM_SO phải phủ chỉ số 162 của Auto-Tune Pro"
    with open(JS_PATH, encoding="utf-8") as f:
        src = f.read()
    # Mỗi hồ sơ có biến riêng bind vào tham số; knob CC của app chỉ chuyển giá trị sang hồ sơ đang chọn.
    assert "makeCustomValueVariable('ql_' + so + '_' + khoa)" in src
    assert "page.makeValueBinding(bien, thamSo[idx])" in src
    assert "page.makeValueBinding(bien, insertViewer.mOn)" in src, "tone_auto = -1 -> nút On của insert slot"
    assert "if (bien) bien.setProcessValue(activeDevice, value)" in src
    # Nút Bè (CC 47) đi cùng bộ hồ sơ plugin kênh Mic (Harmony Player của Auto-Tune Pro), không còn là CC chỉ log.
    # Bè → 155 "HP Bypass Harmony Player" (Auto-Tune Pro 11, máy khách 2026-10-07): bypass nên đảo chiều.
    assert "if (k === 'be' && hoSoHienTai.be_la_bypass) value = 1 - value" in src
    assert "be: CC.be" in src and "CC.be," not in src.split("var ccChiLog")[1].split("\n")[0]
    assert "chonHoSoPlugin(pluginName)" in src
    # Reload Scripts không gọi lại mOnChangePluginIdentity → chọn hồ sơ theo tên tham số "Key".
    assert "if (valueTitle === 'Key') chonHoSoTheoChiSoKey(i)" in src, "valueTitle mới là tên tham số; objectTitle là tên plugin"
    assert "makeSubPage" not in src, "sub page: mActivate.trigger() từ callback không đổi binding"
    # Fix Méo (CC 45) → Chromatic, Dân Ca (CC 46) → Dorian trên Modern Scale; tắt mode trả về scale app gửi gần nhất.
    assert "function apScale(activeDevice)" in src
    assert "if (k === 'scale_type') { scaleApp = value; apScale(activeDevice); return }" in src
    assert "var modeScale = { fix_meo: false, mode_danca: false }" in src
    # Máy 3 (2026-10-08): GUI Auto-Tune đi theo tham số 1 "Scale" (bảng cổ điển) chứ không theo 162 → ghi cả hai.
    assert "function scaleCoDienTuModern(cc)" in src
    assert "page.makeValueBinding(hoSo.bien.scale_classic, thamSo[hoSo.scale_classic])" in src
    assert "if (bc && cd >= 0) bc.setProcessValue(activeDevice, cd / 127)" in src
    # Bản Auto-Tune trên máy 3 chỉ có bảng cổ điển trên GUI (không Dorian, kể cả Modern) → Dân Ca lùi về Minor ở tham số 1.
    assert "if (cc >= 41 && cc <= 49) return 5" in src, "Dorian (Modern 41-49) -> Minor trên bảng cổ điển"
    assert "classic_mode" not in src, "tắt/bật Classic Mode (tham số 11) không đổi được bộ scale của GUI, đã thử 2026-10-08"
    # App gửi Scale theo bảng Pitch Correct của hồ sơ DAW cubase (Major 43, Minor 85). Ba máy khách đều dùng Auto-Tune Pro,
    # 43 trên Modern Scale lại là Dorian → script quy đổi theo plugin, hết cần cân chỉnh từng máy (calibration_overrides).
    assert "scale_tu_pitch_correct: [[23, 63, 10], [64, 105, 18]]" in src
    assert "function scaleTheoHoSo(value)" in src
    assert "datScale(activeDevice, scaleTheoHoSo(scaleApp), null)" in src
    assert "if (k === 'scale_type') { scaleApp = value; apScale(activeDevice); return }" in src, "giữ giá trị thô, quy đổi lúc áp"


def test_js_co_phien_ban_de_kiem_tra():
    with open(JS_PATH, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"var QLS_SCRIPT_VERSION = '(\d{4}-\d{2}-\d{2}[a-z]?)'", src)
    assert m, "setup_all.bat / QLS_ChanDoan đọc dòng này để biết máy khách đang chạy bản nào"
    assert "log('driver active: Cubase da thay QuangLuuMIDI + QLS_PhanHoi (script " + "' + QLS_SCRIPT_VERSION + ')')" in src


def test_js_tone_nhac_va_tone_giong_vao_soundshifter():
    # Kênh NHAC: Waves SoundShifter Pitch Stereo (máy khách 2026-10-07), Semitones = tham số 4.
    # Tone Nhạc (CC 10) lẫn Tone Giọng (CC 11) cùng vào tham số đó, cộng dồn rồi kẹp ±12 (2026-10-07):
    # Tone Nhạc dịch nhạc + app tự gửi key_root đã dịch → Auto-Tune Key đổi theo; Tone Giọng giữ như khách đã dùng.
    with open(JS_PATH, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"var HO_SO_NHAC = \[(.*?)\n\]", src, re.S)
    assert m, "thiếu HO_SO_NHAC"
    assert re.search(r"ten:\s*'SoundShifter'.*?ban_cung:\s*4\b", m.group(1), re.S)
    assert "makeInsertEffectViewer('QuangLuuInsertNhac')" in src
    assert "page.makeValueBinding(hoSo.bien, thamSoNhac[hoSo.ban_cung])" in src
    assert "ccTheoKhoaNhac = { tone_music: CC.tone_music, tone_voice: CC.tone_voice }" in src
    assert "var tong = toneApp.tone_music + toneApp.tone_voice" in src
    assert "hoSoNhacHienTai.bien.setProcessValue(activeDevice, (tong + 12) / 24)" in src
    # Máy khách đặt tone_music = 55 trong app_config.json riêng → script nghe cả CC 10 lẫn CC 55 như Tone Nhạc.
    assert "var CC_TONE_MUSIC_KHACH = 55" in src
    assert "{ khoa: 'tone_music', cc: CC_TONE_MUSIC_KHACH }" in src


def test_ban_cung_tu_cc_khop_app():
    # App gửi cc = int((st + 12) / 24 * 127) (frontend_qt._set_tone_offset); script đọc lại bằng
    # round(cc / 127 * 24 - 12) phải ra đúng st với mọi bán cung -12..+12.
    for st in range(-12, 13):
        cc = int(((st + 12) / 24) * 127)
        assert round(cc / 127 * 24 - 12) == st, (st, cc)


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
