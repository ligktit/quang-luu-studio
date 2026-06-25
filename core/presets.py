"""
Quang Lưu Studio — Preset thuần (Smart Recall, tính năng Premium).

Module CHỈ chứa logic thuần Python để build / normalize / merge preset của một
bài hát. KHÔNG phụ thuộc Qt, MIDI hay engine — nhờ vậy test được mà không cần
khởi tạo UI, và có thể tái dùng ở cả client lẫn (sau này) cloud sync.

Schema preset chuẩn:
    {
        "tone":  str | None,            # vd "C", "Am", "F#m" (nốt gốc + thể)
        "scale": "Major" | "Minor" | None,
        "mixer": {                      # mức các kênh mixer (giá trị slider UI thô)
            "music":   int,
            "mic":     int,
            "reverb":  int,
            "backing": int,
        },
        "mode":  str | None,            # vd "Dân Ca", "Lofi", "Remix", "Đa Thể Loại"
    }

Mọi field đều TÙY CHỌN: bài cũ chưa có preset, hoặc preset thiếu field, vẫn hợp
lệ. normalize_preset luôn trả về dict có đủ khóa (field thiếu = None / mixer rỗng)
để phần áp preset ở UI không phải kiểm tra None rải rác.
"""

# Các khóa kênh mixer trong preset (tên ngắn, độc lập với cc_key của UI).
# Ánh xạ sang cc_key thật của mixer panel: music→mix_music, mic→mix_mic,
# reverb→mix_reverb, backing→mix_backing (xem integration notes Phase 2).
MIXER_KEYS = ("music", "mic", "reverb", "backing")

# Hai thể (scale) hợp lệ. Mọi giá trị khác → None (bỏ qua, không áp).
_VALID_SCALES = {"Major", "Minor"}


def empty_preset() -> dict:
    """Trả về một preset rỗng hợp lệ (đủ khóa, chưa có giá trị nào)."""
    return {"tone": None, "scale": None, "mixer": {}, "mode": None}


def _coerce_int(value):
    """Ép value về int nếu được, ngược lại trả None (bỏ qua field hỏng)."""
    if isinstance(value, bool):
        # bool là subclass của int — đừng nhận nhầm True/False thành 1/0.
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    if isinstance(value, str):
        try:
            return int(round(float(value.strip())))
        except (ValueError, AttributeError):
            return None
    return None


def normalize_mixer(raw) -> dict:
    """Chuẩn hóa phần mixer của preset.

    Chỉ giữ lại các khóa trong MIXER_KEYS có giá trị ép được về int. Field thiếu
    hoặc giá trị không hợp lệ bị bỏ qua (không chèn None) — nhờ vậy khi áp preset
    ta chỉ set những kênh thực sự được lưu, không đụng kênh khác.
    """
    out = {}
    if not isinstance(raw, dict):
        return out
    for key in MIXER_KEYS:
        if key not in raw:
            continue
        val = _coerce_int(raw.get(key))
        if val is not None:
            out[key] = val
    return out


def normalize_preset(raw) -> dict:
    """Chuẩn hóa preset thô (từ file/UI) về schema chuẩn, khoan dung lỗi.

    - Field thiếu → None (với mixer → dict rỗng).
    - tone: chuỗi không rỗng (strip) → giữ; ngược lại None.
    - scale: chỉ chấp nhận "Major" / "Minor"; giá trị khác → None.
    - mode: chuỗi không rỗng (strip) → giữ; ngược lại None.
    - mixer: xem normalize_mixer.

    LUÔN trả về dict có đủ 4 khóa (tone, scale, mixer, mode) để caller không
    phải kiểm tra sự tồn tại của khóa.
    """
    result = empty_preset()
    if not isinstance(raw, dict):
        return result

    tone = raw.get("tone")
    if isinstance(tone, str) and tone.strip():
        result["tone"] = tone.strip()

    scale = raw.get("scale")
    if isinstance(scale, str) and scale.strip() in _VALID_SCALES:
        result["scale"] = scale.strip()

    mode = raw.get("mode")
    if isinstance(mode, str) and mode.strip():
        result["mode"] = mode.strip()

    result["mixer"] = normalize_mixer(raw.get("mixer"))
    return result


def is_empty_preset(preset) -> bool:
    """True nếu preset (đã hoặc chưa normalize) không chứa thông tin gì để áp."""
    p = normalize_preset(preset)
    return (
        p["tone"] is None
        and p["scale"] is None
        and p["mode"] is None
        and not p["mixer"]
    )


def merge_preset(song, preset) -> dict:
    """Gắn preset (đã normalize) vào một bản sao của dict bài hát.

    Trả về dict bài mới với khóa "preset" được cập nhật, KHÔNG mutate `song` gốc.
    Dùng khi muốn lưu snapshot preset vào bài mà giữ nguyên các field khác.
    """
    new_song = dict(song) if isinstance(song, dict) else {}
    new_song["preset"] = normalize_preset(preset)
    return new_song
