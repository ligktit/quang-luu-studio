"""Thao tác thuần trên ui_config (Dev Mode) — không phụ thuộc Qt để test được.

Widget built-in = id có trong mặc định của panel. UiConfigManager nối lại id
built-in bị thiếu mỗi lần nạp, nên built-in chỉ ẩn được, không xoá được.
"""
import copy
import re

PANEL_TITLES = {"mixer": "Mixer", "tools": "Tools", "mode": "Mode"}

_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _defaults():
    from core.config import UiConfigManager
    return UiConfigManager._DEFAULT_UI_CONFIG


def default_ids(panel):
    return {d["id"] for d in _defaults().get(panel, [])}


def is_custom(panel, entry):
    return isinstance(entry, dict) and entry.get("id") not in default_ids(panel)


def index_of(entries, wid):
    for i, e in enumerate(entries):
        if isinstance(e, dict) and e.get("id") == wid:
            return i
    return -1


def move(entries, index, delta):
    """Dời entries[index] đi delta bước (chặn ở hai đầu). Trả index mới."""
    if not 0 <= index < len(entries):
        return index
    new = max(0, min(len(entries) - 1, index + delta))
    if new != index:
        entries.insert(new, entries.pop(index))
    return new


def reorder(entries, ids):
    """Sắp lại theo ids (thứ tự trên danh sách kéo-thả). Phần tử không có
    trong ids (hỏng / không phải dict) giữ ở cuối theo thứ tự cũ."""
    by_id = {}
    for e in entries:
        if isinstance(e, dict) and e.get("id") not in by_id:
            by_id[e.get("id")] = e
    head = [by_id[i] for i in ids if i in by_id]
    used = {id(e) for e in head}
    return head + [e for e in entries if id(e) not in used]


def set_hidden(entries, wid, hidden):
    i = index_of(entries, wid)
    if i < 0:
        return False
    entries[i]["hidden"] = bool(hidden)
    return True


def delete_custom(panel, entries, wid):
    i = index_of(entries, wid)
    if i < 0 or not is_custom(panel, entries[i]):
        return False
    del entries[i]
    return True


def reset_panel(config, panel):
    config[panel] = copy.deepcopy(_defaults().get(panel, []))


def is_valid_color(text, token_names=()):
    text = (text or "").strip()
    return bool(_HEX.match(text)) or text in token_names


def _as_int(value):
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def mixer_slider_on_cc(cc, ui_config, midi_cc, exclude_id=None):
    """Tên slider MIXER khác đang dùng CC `cc` (None nếu không có).

    Khác find_cc_conflicts (chỉ cảnh báo): hai slider MIXER cùng CC là lỗi —
    panel khoá kênh theo CC nên slider thứ hai không hiện ra được.
    """
    if cc is None or cc < 0:
        return None
    midi_cc = midi_cc or {}
    for e in (ui_config or {}).get("mixer") or []:
        if not isinstance(e, dict) or e.get("type", "slider") != "slider":
            continue
        if exclude_id is not None and e.get("id") == exclude_id:
            continue
        raw = e.get("cc")
        num = _as_int(midi_cc.get(raw)) if isinstance(raw, str) else _as_int(raw)
        if num == cc:
            return e.get("label") or e.get("id") or str(raw)
    return None


def find_cc_conflicts(cc, ui_config, midi_cc, exclude_id=None, mode_config=None):
    """Những thứ khác đang gửi trên CC `cc` — để cảnh báo (không chặn) trong
    Widget Builder. Gồm widget trên 3 panel (CC số hoặc tên tra midi_cc),
    CC của mode trong mode_config và key hệ thống trong midi_cc."""
    if cc is None or cc < 0:
        return []
    midi_cc = midi_cc or {}
    hits, used_keys = [], set()
    exclude_label = None
    for panel, title in PANEL_TITLES.items():
        entries = (ui_config or {}).get(panel)
        if not isinstance(entries, list):
            continue
        for e in entries:
            if not isinstance(e, dict):
                continue
            if exclude_id is not None and e.get("id") == exclude_id:
                exclude_label = e.get("label")
                continue
            raw = e.get("cc")
            if isinstance(raw, str):
                if _as_int(midi_cc.get(raw)) == cc:
                    hits.append(f"{e.get('label') or raw} ({title})")
                    used_keys.add(raw)
            elif _as_int(raw) == cc:
                hits.append(f"{e.get('label') or e.get('id')} ({title})")
    for label, mcfg in (mode_config or {}).items():
        if label == exclude_label or not isinstance(mcfg, dict):
            continue
        if _as_int(mcfg.get("cc")) == cc:
            hits.append(f"Mode {label}")
    for key, value in midi_cc.items():
        if key not in used_keys and _as_int(value) == cc:
            hits.append(f"CC hệ thống “{key}”")
    return list(dict.fromkeys(hits))
