"""Hai micro trên Studio One: mic 2 = kênh MIDI index 1, cùng số CC với mic 1.

Module thuần (không import core.config) — chỉ tính toán tập CC dùng chung và
nhân đôi tin nhắn. Các CC riêng từng mic (mix_mic, mute_mic) không bao giờ
được phát sang kênh 2.
"""
from typing import Iterable

MIC2_CHANNEL = 1
MIC_KEY = "mix_mic"
MIC2_KEY = "mix_mic_2"

# Tên hiển thị mặc định hai kênh mic (settings["mic_labels"] sửa được).
DEFAULT_LABELS = {MIC_KEY: "Mic Dây", MIC2_KEY: "Mic Không Dây"}

# Tên CC (trong midi_cc) cần phát cả hai kênh vì là trạng thái dùng chung
# (tone, vang, chế độ...) — mỗi mic có một chuỗi FX riêng trong Studio One.
DEFAULT_SHARED_NAMES = (
    "tone_voice", "mix_reverb", "mode", "key_root", "key_scale", "scale_type",
    "tune_on_off", "tone_auto", "fix_meo", "be", "tat_on", "mute_reverb",
    "voice_fx", "mode_danca", "mode_lofi", "mode_remix", "mode_datheloai",
)


def is_enabled(settings) -> bool:
    """Chỉ bật khi mic_count == 2 (chấp nhận cả chuỗi "2")."""
    if not settings:
        return False
    try:
        return int(settings.get("mic_count")) == 2
    except (TypeError, ValueError):
        return False


def labels(settings) -> dict:
    """Tên hai mic theo settings["mic_labels"]; thiếu/trống/hỏng -> mặc định."""
    saved = (settings or {}).get("mic_labels")
    if not isinstance(saved, dict):
        saved = {}
    out = {}
    for key, default in DEFAULT_LABELS.items():
        name = saved.get(key)
        name = name.strip() if isinstance(name, str) else ""
        out[key] = name or default
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
            if key == MIC_KEY or not isinstance(entries, (list, tuple)):
                continue
            for entry in entries:
                cc = _as_cc(entry)
                if cc is not None:
                    out.add(cc)
    for per_mic in (MIC_KEY, "mute_mic"):
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
