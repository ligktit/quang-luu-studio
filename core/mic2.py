"""Hai micro trên Studio One: mic 2 = kênh MIDI index 1, cùng số CC với mic 1.

Module thuần (không import core.config) — chỉ tính toán tập CC dùng chung và
nhân đôi tin nhắn. Các CC riêng từng mic (mức/tắt Mic, mức/tắt Vang và CC phụ
mute_multi_cc của hai kênh đó) không bao giờ được phát sang kênh 2: mic 2 có
kênh riêng trên mixer (Mic 2, Vang Mic 2) gửi thẳng kênh MIDI 2.
"""
from typing import Iterable

MIC2_CHANNEL = 1
MIC_KEY = "mix_mic"
MIC2_KEY = "mix_mic_2"
REVERB_KEY = "mix_reverb"
MIC2_REVERB_KEY = "mix_reverb_2"

# Kênh mixer chỉ có khi bật 2 mic -> kênh của mic 1 mà nó mượn số CC
# (mức, tắt, CC phụ mute_multi_cc), gửi trên kênh MIDI 2, không phát đôi.
MIC2_CHANNELS = {MIC2_KEY: MIC_KEY, MIC2_REVERB_KEY: REVERB_KEY}

# Tên CC riêng từng mic: không phát đôi dù cấu hình mic2_shared_cc có ghi.
# Vang từng tách riêng sau khi máy 826077C tắt Vang mic dây làm tắt luôn vang
# mic không dây đang hát (2026-11-03).
PER_MIC_NAMES = (MIC_KEY, "mute_mic", REVERB_KEY, "mute_reverb")

# Tên hiển thị mặc định hai kênh mic (settings["mic_labels"] sửa được).
DEFAULT_LABELS = {MIC_KEY: "Mic Dây", MIC2_KEY: "Mic Không Dây"}

# Tên CC (trong midi_cc) cần phát cả hai kênh vì là trạng thái dùng chung
# (tone, chế độ...) — mỗi mic có một chuỗi FX riêng trong Studio One.
DEFAULT_SHARED_NAMES = (
    "tone_voice", "mode", "key_root", "key_scale", "scale_type",
    "tune_on_off", "tone_auto", "fix_meo", "be", "tat_on",
    "voice_fx", "mode_danca", "mode_lofi", "mode_remix", "mode_datheloai",
)


def two_mics_configured(settings) -> bool:
    """settings ghi mic_count == 2 (chấp nhận cả chuỗi "2"), bất kể DAW."""
    if not settings:
        return False
    try:
        return int(settings.get("mic_count")) == 2
    except (TypeError, ValueError):
        return False


def is_enabled(settings) -> bool:
    """Hai mic CHỈ chạy trên Studio One: mic_count == 2 và DAW không phải Cubase.

    Thiếu/lạ daw_kind = Studio One, giống core.daw.kind_of (không import
    core.daw để module này thuần).
    """
    return two_mics_configured(settings) and settings.get("daw_kind") != "cubase"


def _saved_name(settings, key) -> str:
    saved = (settings or {}).get("mic_labels")
    name = saved.get(key) if isinstance(saved, dict) else None
    return name.strip() if isinstance(name, str) else ""


def labels(settings) -> dict:
    """Tên hai mic theo settings["mic_labels"]; thiếu/trống/hỏng -> mặc định."""
    return {key: _saved_name(settings, key) or default
            for key, default in DEFAULT_LABELS.items()}


def reverb2_label(settings) -> str:
    """Tên kênh Vang của mic 2: tự đặt trong mic_labels, không có thì "Vang <tên mic 2>"."""
    return _saved_name(settings, MIC2_REVERB_KEY) or f"Vang {labels(settings)[MIC2_KEY]}"


def with_label(settings, key, name) -> dict:
    """mic_labels mới sau khi đặt tên `key` = `name`.

    Trống -> tên mặc định (Vang Mic 2: bỏ tên tự đặt, quay về tên tự suy).
    Giữ nguyên các tên còn lại. Tên các kênh này chỉ đọc từ mic_labels, nên
    Dev Mode đổi tên phải ghi vào đây, không phải ui_config.
    """
    if key not in DEFAULT_LABELS and key != MIC2_REVERB_KEY:
        raise ValueError(f"không phải kênh mic: {key!r}")
    out = labels(settings)
    rv = _saved_name(settings, MIC2_REVERB_KEY)
    if rv:
        out[MIC2_REVERB_KEY] = rv
    name = name.strip() if isinstance(name, str) else ""
    if key == MIC2_REVERB_KEY:
        if name:
            out[key] = name
        else:
            out.pop(key, None)
    else:
        out[key] = name or DEFAULT_LABELS[key]
    return out


def _as_cc(entry):
    if isinstance(entry, dict):
        cc = entry.get("cc")
        if isinstance(cc, int) and not isinstance(cc, bool):
            return cc
    return None


def shared_cc_numbers(midi_cc: dict, names: Iterable[str], mode_config: dict,
                      mute_multi_cc: dict) -> frozenset:
    """Tập số CC cần nhân đôi sang mic 2; bỏ qua tên/entry hỏng."""
    out = set()
    midi_cc = midi_cc or {}
    for name in names or ():
        cc = midi_cc.get(name)
        if isinstance(cc, int) and not isinstance(cc, bool):
            out.add(cc)
    if isinstance(mode_config, dict):
        for entry in mode_config.values():
            cc = _as_cc(entry)
            if cc is not None:
                out.add(cc)
    if isinstance(mute_multi_cc, dict):
        for key, entries in mute_multi_cc.items():
            if key in (MIC_KEY, REVERB_KEY) or not isinstance(entries, (list, tuple)):
                continue
            for entry in entries:
                cc = _as_cc(entry)
                if cc is not None:
                    out.add(cc)
    for per_mic in PER_MIC_NAMES:
        cc = midi_cc.get(per_mic)
        if isinstance(cc, int):
            out.discard(cc)
    return frozenset(out)


def expand(pairs: Iterable, shared: frozenset) -> list:
    """(cc, value) -> [(channel, cc, value)]: kênh 0 trước, rồi bản sao mic 2."""
    pairs = list(pairs)
    msgs = [(0, cc, v) for cc, v in pairs]
    msgs += [(MIC2_CHANNEL, cc, v) for cc, v in pairs if cc in shared]
    return msgs
