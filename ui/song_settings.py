"""Thiết lập theo bài hát — chụp lại khi lưu bài, khôi phục khi mở lại bài.

Mỗi thiết lập là MỘT mục trong SONG_SETTINGS, tự lo các việc:
  capture(dash)            → dict các khóa preset sẽ ghi (bỏ trống = không ghi gì)
  apply(dash, preset)      → áp lại từ preset đã normalize (core.presets)
  reset(dash, url, song)   → đưa về mặc định khi SANG BÀI MỚI (None = giữ nguyên)
  covers(preset)           → True nếu preset sẽ đặt lại mục này → bỏ qua reset,
                             tránh gửi MIDI "về mặc định" rồi lại "về giá trị
                             đã lưu" liền nhau (plugin bật/tắt chớp một nhịp)

Thêm thiết lập mới: viết thêm một SongSetting rồi nối vào SONG_SETTINGS. Không
phải sửa core/presets.py — khóa lạ được giữ nguyên văn khi lưu (xem module đó),
nên preset cũ/mới đọc qua lại được giữa các phiên bản app.

Thứ tự trong SONG_SETTINGS là thứ tự áp: Tone Nhạc phải áp TRƯỚC tone Auto-Tune,
vì tone lưu trong preset là tone đang vang (đã cộng Tone Nhạc).
"""
from dataclasses import dataclass
from typing import Callable, Optional

# Phiên bản schema do app ghi. v2: có tone_locked/tone_music/tone_voice/
# toggles, và "modes" rỗng nghĩa là TẮT HẾT (v1 thì rỗng = không rõ).
PRESET_VERSION = 2

# Nút bật/tắt panel Công cụ: {khóa preset: (thuộc tính trạng thái, handler đảo)}.
_TOGGLES = {
    "tone_auto": ("tune_state", "_on_tone_auto"),
    "fix_meo":   ("fix_meo_state", "_on_fix_meo"),
    "be":        ("be_state", "_on_be"),
    "tat_on":    ("tat_on_state", "_on_tat_on"),
}

# Kênh mixer quen thuộc: cc_key trên UI ↔ tên ngắn trong preset.
_MIXER_NAMES = {"mix_music": "music", "mix_mic": "mic",
                "mix_reverb": "reverb", "mix_backing": "backing"}
# Kênh do setting riêng lo — không lưu 2 lần. ("tone_music" chỉ còn ở
# ui_config.json kỹ thuật viên tự sửa tay; Tone Nhạc đã có setting riêng.)
_MIXER_SKIP = {"tone_music"}


@dataclass(frozen=True)
class SongSetting:
    name: str
    capture: Callable
    apply: Callable
    reset: Optional[Callable] = None
    covers: Optional[Callable] = None


# ── Tone Nhạc / Tone Giọng ────────────────────────────────────────────────
def _offset_setting(which):
    def capture(dash):
        return {which: dash._tone_offset(which)}

    def apply(dash, preset):
        value = preset.get(which)
        if value is not None:
            dash._set_tone_offset(which, value, shift_key=False)

    def reset(dash, url, song):
        dash._set_tone_offset(which, 0, shift_key=False)

    def covers(preset):
        return preset.get(which) is not None

    return SongSetting(which, capture, apply, reset, covers)


# ── Tone Auto-Tune (nốt gốc + thể) ────────────────────────────────────────
def _key_capture(dash):
    # Đọc trạng thái sống (current_tone/current_scale) chứ không đọc chữ trên ô:
    # chọn tone bằng giọng nói/phím tắt đổi trạng thái trước, ô hiển thị theo sau.
    return {
        "tone": getattr(dash, "current_tone", None) or None,
        "scale": getattr(dash, "current_scale", None) or None,
        # Chỉ tone CHỐT TAY mới cần áp lại. Tone do dò/chuỗi tone của bài thì
        # lần mở sau tự có lại (kèm cả các mốc đổi tone giữa bài) — ép một tone
        # duy nhất lúc bấm lưu sẽ giết mất chuỗi đó.
        "tone_locked": bool(dash._manual_tone_override),
    }


def _key_apply(dash, preset):
    # tone_locked None = preset đời cũ (Smart Recall v1): giữ cách cũ là áp.
    if preset.get("tone_locked") is False:
        return
    tone = preset.get("tone")
    scale = preset.get("scale")
    if not tone and not scale:
        return
    from PySide6.QtCore import QSignalBlocker
    if tone:
        with QSignalBlocker(dash.tone_combo):
            dash.tone_combo.setCurrentText(tone)
        dash._on_tone_selected(tone)
    if scale:
        with QSignalBlocker(dash.scale_combo):
            dash.scale_combo.setCurrentText(scale)
        dash._on_scale_selected(scale)


def _key_reset(dash, url, song):
    # Bỏ khoá "chỉnh tay" của bài trước để tone bài mới được dò/gửi bình
    # thường, và thay timeline bài cũ bằng timeline đã lưu của bài mới (nếu
    # có) — không thì ô "kế tiếp" đếm ngược theo mốc của bài trước.
    dash._set_manual_tone_override(False)
    duration = (song or {}).get("duration", 0) or 0
    dash._set_tone_timeline(dash._saved_manual_timeline(url) or [], duration)


# ── Mixer ─────────────────────────────────────────────────────────────────
def _mixer_capture(dash):
    out = {}
    for cc_key, slider in (getattr(dash, "_mixer_sliders", None) or {}).items():
        if cc_key in _MIXER_SKIP:
            continue
        out[_MIXER_NAMES.get(cc_key, str(cc_key))] = slider.value()
    return {"mixer": out}


def _mixer_apply(dash, preset):
    by_name = {v: k for k, v in _MIXER_NAMES.items()}
    sliders = getattr(dash, "_mixer_sliders", None) or {}
    by_str = {str(k): k for k in sliders}
    for name, value in (preset.get("mixer") or {}).items():
        cc_key = by_name.get(name, by_str.get(name))
        slider = sliders.get(cc_key) if cc_key is not None else None
        if slider is not None and cc_key not in _MIXER_SKIP:
            slider.setValue(int(value))


# ── MODE ──────────────────────────────────────────────────────────────────
def _modes_capture(dash):
    active = dash.active_modes()
    # "mode" (1 nút) chỉ giữ lại cho bản cũ đọc được.
    return {"modes": active, "mode": active[0] if active else None}


def _modes_covered(preset):
    # v1 không phân biệt "lưu lúc tắt hết" với "chưa từng lưu mode" → rỗng thì
    # coi như không có. v2 ghi rõ: rỗng = tắt hết.
    return bool(preset.get("modes")) or (preset.get("v") or 1) >= 2


def _modes_apply(dash, preset):
    if _modes_covered(preset):
        dash._apply_mode_states(preset.get("modes") or [])


def _modes_reset(dash, url, song):
    # Bài mới bắt đầu với mọi MODE TẮT — thể loại của bài trước không kéo sang.
    dash._apply_mode_states([])


# ── Nút bật/tắt panel Công cụ ────────────────────────────────────────────
def _toggles_capture(dash):
    return {"toggles": {key: bool(getattr(dash, attr, False))
                        for key, (attr, _handler) in _TOGGLES.items()}}


def _toggles_apply(dash, preset):
    for key, want in (preset.get("toggles") or {}).items():
        spec = _TOGGLES.get(key)
        if spec is None:
            continue
        attr, handler = spec
        if bool(getattr(dash, attr, False)) != bool(want):
            getattr(dash, handler)()   # handler là nút đảo: gửi MIDI + đèn + dải


SONG_SETTINGS = (
    _offset_setting("tone_music"),
    _offset_setting("tone_voice"),
    SongSetting("key", _key_capture, _key_apply, _key_reset),
    SongSetting("mixer", _mixer_capture, _mixer_apply),
    SongSetting("modes", _modes_capture, _modes_apply, _modes_reset, _modes_covered),
    SongSetting("toggles", _toggles_capture, _toggles_apply),
)


def capture_all(dash) -> dict:
    """Ảnh chụp mọi thiết lập theo bài (chưa normalize)."""
    preset = {"v": PRESET_VERSION}
    for setting in SONG_SETTINGS:
        try:
            preset.update(setting.capture(dash) or {})
        except Exception as e:
            print(f"[SONG SETTINGS] Chụp '{setting.name}' lỗi: {e}")
    return preset


def apply_all(dash, preset) -> None:
    """Áp preset (đã normalize). Một mục lỗi không chặn các mục còn lại."""
    for setting in SONG_SETTINGS:
        try:
            setting.apply(dash, preset)
        except Exception as e:
            print(f"[SONG SETTINGS] Áp '{setting.name}' lỗi: {e}")


def reset_all(dash, url, song=None, preset=None) -> None:
    """Đưa các thiết lập theo bài về mặc định khi sang bài mới.

    preset: preset sắp được áp cho bài này (nếu có) — mục nào preset đặt lại
    thì không reset trước.
    """
    for setting in SONG_SETTINGS:
        if setting.reset is None:
            continue
        if preset and setting.covers is not None and setting.covers(preset):
            continue
        try:
            setting.reset(dash, url, song)
        except Exception as e:
            print(f"[SONG SETTINGS] Reset '{setting.name}' lỗi: {e}")
