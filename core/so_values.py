"""Quy đổi giá trị hiển thị trong Studio One ↔ giá trị MIDI CC (0–127).

Control Link của Studio One ánh xạ CC 0..127 TUYẾN TÍNH lên dải chuẩn hoá 0..1
của tham số được gán. Kỹ thuật viên nhìn thấy giá trị Studio One (On/Off, 75%,
+5 st, mục thứ 3 của danh sách…) chứ không thấy số MIDI — module này làm phép
đổi để Dev Mode cho nhập thẳng giá trị Studio One.

Mô tả một nút ("so_value" trong ui_config.json) là một dict:

    {"type": "switch",  "bypass": False}
    {"type": "percent", "on": 75, "off": 0}
    {"type": "range",   "min": -12, "max": 12, "unit": "st", "on": 5, "off": 0}
    {"type": "list",    "options": ["Tắt", "Nhẹ", "Mạnh"], "on": 2, "off": 0}
    {"type": "midi",    "on": 127, "off": 0}

"on"/"off" là giá trị Studio One khi nút trên app BẬT/TẮT (list: chỉ số 0-based).
Runtime KHÔNG đọc dict này — nó chỉ đọc on_value/off_value (MIDI) đã quy đổi sẵn
lúc lưu, nên mọi đường gửi/nhận MIDI cũ giữ nguyên.
"""

TYPES = ("switch", "percent", "range", "list", "midi")

TYPE_LABELS = {
    "switch":  "Công tắc (On/Off, Mute, Bypass…)",
    "percent": "Phần trăm (0–100%)",
    "range":   "Khoảng số (vd -12…+12 st)",
    "list":    "Danh sách lựa chọn",
    "midi":    "MIDI thô 0–127 (nâng cao)",
}

MIDI_MAX = 127


def _clamp_midi(v):
    return max(0, min(MIDI_MAX, int(round(v))))


def percent_to_midi(percent):
    return _clamp_midi(max(0.0, min(100.0, float(percent))) / 100.0 * MIDI_MAX)


def midi_to_percent(midi):
    return _clamp_midi(midi) / MIDI_MAX * 100.0


def range_to_midi(value, lo, hi):
    lo, hi = float(lo), float(hi)
    if hi == lo:
        return 0
    return _clamp_midi((float(value) - lo) / (hi - lo) * MIDI_MAX)


def midi_to_range(midi, lo, hi):
    lo, hi = float(lo), float(hi)
    return lo + _clamp_midi(midi) / MIDI_MAX * (hi - lo)


def list_to_midi(index, count):
    """Mục thứ `index` (0-based) của tham số có `count` lựa chọn.

    Lấy điểm k/(N-1) — nằm giữa vùng của mục đó theo cả hai cách plugin hay
    dùng để đổi ngược (làm tròn k = x·(N-1), hoặc cắt VST3 k = x·N).
    """
    count = int(count)
    if count <= 1:
        return 0
    index = max(0, min(count - 1, int(index)))
    return _clamp_midi(index / (count - 1) * MIDI_MAX)


def midi_to_list(midi, count):
    count = int(count)
    if count <= 1:
        return 0
    return max(0, min(count - 1, int(round(_clamp_midi(midi) / MIDI_MAX * (count - 1)))))


def switch_to_midi(on, bypass=False):
    """Công tắc: BẬT = 127, TẮT = 0. bypass=True → đảo chiều.

    Tham số Bypass của plugin hiểu 127 = bỏ qua = hiệu ứng TẮT, nên nút app
    BẬT phải gửi 0. Đảo ở đây thì phản hồi MIDI đọc về cũng khớp chiều.
    """
    on = bool(on) != bool(bypass)
    return MIDI_MAX if on else 0


def _state_to_midi(spec, key):
    t = spec.get("type")
    if t == "switch":
        return switch_to_midi(key == "on", spec.get("bypass", False))
    if t == "percent":
        return percent_to_midi(spec.get(key, 0))
    if t == "range":
        return range_to_midi(spec.get(key, 0), spec.get("min", 0), spec.get("max", 100))
    if t == "list":
        return list_to_midi(spec.get(key, 0), len(spec.get("options") or []))
    # "midi" (và mọi kiểu lạ) → giá trị thô
    return _clamp_midi(spec.get(key, MIDI_MAX if key == "on" else 0))


def midi_pair(spec):
    """(on_value, off_value) MIDI của một mô tả so_value."""
    return _state_to_midi(spec, "on"), _state_to_midi(spec, "off")


def infer_spec(on_value=127, off_value=0):
    """Dựng mô tả so_value từ cặp MIDI cũ (entry chưa có so_value).

    127/0 và 0/127 chính là công tắc thường / công tắc Bypass; còn lại giữ
    nguyên dạng MIDI thô để không làm sai lệch cấu hình đang chạy.
    """
    on_value, off_value = int(on_value), int(off_value)
    if (on_value, off_value) == (MIDI_MAX, 0):
        return {"type": "switch", "bypass": False}
    if (on_value, off_value) == (0, MIDI_MAX):
        return {"type": "switch", "bypass": True}
    return {"type": "midi", "on": on_value, "off": off_value}


def resolve_spec(spec, on_value, off_value):
    """Mô tả dùng để hiển thị lại trong Dev Mode.

    Giữ `spec` đã lưu nếu nó còn quy đổi ra đúng cặp MIDI đang chạy; lệch
    (ai đó sửa tay file cấu hình) thì suy lại từ MIDI — màn hình phải nói
    đúng thứ app đang gửi đi.
    """
    if isinstance(spec, dict) and spec.get("type") in TYPES:
        try:
            if midi_pair(spec) == (int(on_value), int(off_value)):
                return dict(spec)
        except (TypeError, ValueError):
            pass
    return infer_spec(on_value, off_value)


def describe(spec, key):
    """Giá trị Studio One mà MIDI đã quy đổi thật sự ứng với (sau làm tròn)."""
    midi = _state_to_midi(spec, key)
    t = spec.get("type")
    if t == "switch":
        high = midi >= 64
        if spec.get("bypass", False):
            return "Bypass On (plugin tắt)" if high else "Bypass Off (plugin chạy)"
        return "On" if high else "Off"
    if t == "percent":
        return f"≈ {midi_to_percent(midi):.1f}%"
    if t == "range":
        unit = spec.get("unit", "")
        v = midi_to_range(midi, spec.get("min", 0), spec.get("max", 100))
        return f"≈ {v:.2f}{(' ' + unit) if unit else ''}"
    if t == "list":
        options = spec.get("options") or []
        if not options:
            return "—"
        return options[midi_to_list(midi, len(options))]
    return str(midi)
