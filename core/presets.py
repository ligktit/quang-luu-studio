"""
Quang Lưu Studio — Preset thuần (Smart Recall — thiết lập theo bài, mọi gói).

Module CHỈ chứa logic thuần Python để build / normalize / merge preset của một
bài hát. KHÔNG phụ thuộc Qt, MIDI hay engine — nhờ vậy test được mà không cần
khởi tạo UI, và có thể tái dùng ở cả client lẫn (sau này) cloud sync.

Schema preset chuẩn:
    {
        "tone":  str | None,            # vd "C", "Am", "F#m" (nốt gốc + thể)
        "scale": "Major" | "Minor" | None,
        "tone_locked": bool | None,     # True = tone do người dùng chốt tay;
                                        # False = tone dò/timeline của bài lo
        "tone_music": int | None,       # núm Tone Nhạc, -12..+12 bán cung
        "tone_voice": int | None,       # núm Tone Giọng, -12..+12 bán cung
        "mixer": {str: int},            # mức các kênh mixer (giá trị slider UI thô)
        "modes": list[str],             # các MODE đang bật, vd ["Lofi", "Remix"]
        "mode":  str | None,            # LEGACY: mode đầu tiên trong "modes"
        "toggles": {str: bool},         # Auto-Tune / Fix Méo / Bè / Tắt Ồn…
        ...                             # khóa khác: giữ NGUYÊN VĂN (xem dưới)
    }

Các nút MODE là toggle độc lập nên nhiều mode có thể cùng bật → nguồn sự thật
là "modes". Khóa "mode" (một chuỗi) chỉ còn để tương thích: preset lưu bởi bản
cũ vẫn đọc được, và bản cũ vẫn đọc được preset mới (dù chỉ thấy mode đầu tiên).

Mọi field đều TÙY CHỌN: bài cũ chưa có preset, hoặc preset thiếu field, vẫn hợp
lệ. normalize_preset luôn trả về dict có đủ khóa chuẩn (field thiếu = None /
rỗng) để phần áp preset ở UI không phải kiểm tra None rải rác.

Setting thêm sau này: khóa lạ KHÔNG bị bỏ — normalize giữ nguyên nếu là dữ liệu
JSON thuần. Nhờ vậy thêm một setting mới chỉ cần khai báo ở phía UI
(ui/song_settings.py), không phải sửa module này, và bản app cũ mở/lưu lại bài
cũng không làm rơi setting của bản mới.
"""

# Các khóa kênh mixer quen thuộc (tên ngắn, độc lập với cc_key của UI).
# Ánh xạ sang cc_key thật của mixer panel: music→mix_music, mic→mix_mic,
# reverb→mix_reverb, backing→mix_backing. Kênh tự thêm ở Dev Mode lưu bằng
# chính cc_key của nó (vd "60").
MIXER_KEYS = ("music", "mic", "reverb", "backing")

# Hai thể (scale) hợp lệ. Mọi giá trị khác → None (bỏ qua, không áp).
_VALID_SCALES = {"Major", "Minor"}

# Dải của hai núm tone (bán cung).
TONE_OFFSET_RANGE = (-12, 12)

# Khóa do module này chuẩn hoá — mọi khóa khác đi qua _keep_extra.
_KNOWN_KEYS = ("tone", "scale", "tone_locked", "tone_music", "tone_voice",
               "mixer", "modes", "mode", "toggles")


def empty_preset() -> dict:
    """Trả về một preset rỗng hợp lệ (đủ khóa, chưa có giá trị nào)."""
    return {
        "tone": None, "scale": None, "tone_locked": None,
        "tone_music": None, "tone_voice": None,
        "mixer": {}, "modes": [], "mode": None, "toggles": {},
    }


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


def _coerce_offset(value):
    """Độ dịch tone: int trong TONE_OFFSET_RANGE (kẹp biên), hỏng → None."""
    v = _coerce_int(value)
    if v is None:
        return None
    lo, hi = TONE_OFFSET_RANGE
    return max(lo, min(hi, v))


def normalize_mixer(raw) -> dict:
    """Chuẩn hóa phần mixer của preset.

    Giữ mọi kênh có tên là chuỗi và giá trị ép được về int. Field thiếu hoặc
    giá trị không hợp lệ bị bỏ qua (không chèn None) — nhờ vậy khi áp preset
    ta chỉ set những kênh thực sự được lưu, không đụng kênh khác.
    """
    out = {}
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip():
            continue
        val = _coerce_int(value)
        if val is not None:
            out[key.strip()] = val
    return out


def normalize_toggles(raw) -> dict:
    """{tên nút: bool}. Chỉ nhận bool thật — 1/0/"yes" coi là hỏng, bỏ qua."""
    if not isinstance(raw, dict):
        return {}
    return {k.strip(): v for k, v in raw.items()
            if isinstance(k, str) and k.strip() and isinstance(v, bool)}


def normalize_modes(raw) -> list:
    """Rút danh sách MODE đang bật từ preset thô.

    Ưu tiên khóa "modes" (list). Nếu thiếu thì lấy khóa "mode" đời cũ — hồi đó
    Lofi/Remix/Đa Thể Loại là nhóm radio nên chỉ lưu được đúng một mode.
    Bỏ chuỗi rỗng và bỏ trùng, giữ nguyên thứ tự.
    """
    if not isinstance(raw, dict):
        return []
    values = raw.get("modes")
    if not isinstance(values, list):
        values = [raw.get("mode")]

    out = []
    for value in values:
        if isinstance(value, str) and value.strip() and value.strip() not in out:
            out.append(value.strip())
    return out


def _is_plain_json(value, depth=0) -> bool:
    """True nếu value chỉ gồm kiểu JSON thuần (để ghi file an toàn)."""
    if depth > 8:
        return False
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, list):
        return all(_is_plain_json(v, depth + 1) for v in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _is_plain_json(v, depth + 1)
                   for k, v in value.items())
    return False


def normalize_preset(raw) -> dict:
    """Chuẩn hóa preset thô (từ file/UI) về schema chuẩn, khoan dung lỗi.

    - Field thiếu → None (mixer/toggles → dict rỗng, modes → list rỗng).
    - tone: chuỗi không rỗng (strip) → giữ; ngược lại None.
    - scale: chỉ chấp nhận "Major" / "Minor"; giá trị khác → None.
    - tone_locked: chỉ nhận bool; khác → None (= preset đời cũ, xem UI).
    - tone_music / tone_voice: int kẹp trong -12..+12; hỏng → None.
    - modes: list chuỗi không rỗng (strip, bỏ trùng, giữ thứ tự). Preset đời cũ
      chỉ có khóa "mode" (một chuỗi) → quy về list 1 phần tử.
    - mode: mirror của modes[0], giữ cho bản cũ đọc được.
    - mixer / toggles: xem normalize_mixer / normalize_toggles.
    - Khóa khác: giữ nguyên nếu là dữ liệu JSON thuần (setting thêm sau này).

    LUÔN trả về dict có đủ các khóa chuẩn để caller không phải kiểm tra sự tồn
    tại của khóa.
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

    if isinstance(raw.get("tone_locked"), bool):
        result["tone_locked"] = raw["tone_locked"]

    result["tone_music"] = _coerce_offset(raw.get("tone_music"))
    result["tone_voice"] = _coerce_offset(raw.get("tone_voice"))

    result["modes"] = normalize_modes(raw)
    result["mode"] = result["modes"][0] if result["modes"] else None

    result["mixer"] = normalize_mixer(raw.get("mixer"))
    result["toggles"] = normalize_toggles(raw.get("toggles"))

    for key, value in raw.items():
        if isinstance(key, str) and key not in _KNOWN_KEYS and _is_plain_json(value):
            result[key] = value
    return result


def is_empty_preset(preset) -> bool:
    """True nếu preset (đã hoặc chưa normalize) không chứa thông tin gì để áp."""
    p = normalize_preset(preset)
    return all(
        value in (None, {}, [])
        for key, value in p.items()
        if key != "mode"
    )


def merge_preset(song, preset) -> dict:
    """Gắn preset (đã normalize) vào một bản sao của dict bài hát.

    Trả về dict bài mới với khóa "preset" được cập nhật, KHÔNG mutate `song` gốc.
    Dùng khi muốn lưu snapshot preset vào bài mà giữ nguyên các field khác.
    """
    new_song = dict(song) if isinstance(song, dict) else {}
    new_song["preset"] = normalize_preset(preset)
    return new_song
