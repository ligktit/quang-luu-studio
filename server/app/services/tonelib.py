"""Thư viện tone cộng đồng — chuẩn hoá, băm và xếp hạng biến thể.

Toàn bộ luật "kết quả nào là đúng" nằm ở đây, tách khỏi router để test được mà
không cần dựng HTTP.

Vì sao SERVER băm chứ không nhận hash từ client: hash là thứ quyết định hai kết
quả có được coi là một hay không. Để client tự tính thì (a) client cũ/mới đổi
công thức là cả thư viện vỡ thành nghìn mảnh, (b) một client sửa đổi có thể gửi
hash trùng với biến thể đang thắng để "mượn" phiếu của nó.
"""
import base64
import hashlib
import json
import re
from datetime import datetime, timezone

# song_key CHỈ nhận YouTube video_id 11 ký tự. Đường dẫn file local vừa là dữ
# liệu cá nhân vừa không khớp được giữa các máy — chặn ngay ở cổng.
SONG_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

# auto: máy dò | human: người dùng sửa tay | admin: dev đặt trên /admin/library.
# CLIENT_SOURCES là tập client ĐƯỢC PHÉP gửi qua /contribute; "admin" chỉ do
# form admin tạo — client gửi "admin" là tự phong, router ép về "auto".
SOURCES = ("auto", "human", "admin")
CLIENT_SOURCES = ("auto", "human")

# Trần độ dài timeline. Một bài 10 phút chuyển tone mỗi 5 giây cũng chỉ ~120 mốc;
# 300 là dư dả mà vẫn chặn được payload phá hoại.
MAX_ENTRIES = 300

# Trọng số nguồn: một người nghe rồi sửa tay đáng tin hơn hẳn ba máy dò tự động
# — máy dò sai theo cùng một kiểu thì càng nhiều máy càng sai giống nhau.
# admin = 10: bản dev đặt luôn được ghim nên trọng số chỉ để xếp hạng hiển thị
# và phòng khi dev bỏ ghim mà vẫn muốn nó thắng.
SOURCE_WEIGHT = {"admin": 10, "human": 3, "auto": 1}

# Mỗi lượt báo sai trừ nặng hơn một phiếu thuận: hát sai tone tốn tiền của quán,
# còn bỏ sót một bản đúng thì chỉ tốn một lần dò lại.
REPORT_PENALTY = 2


def valid_song_key(song_key) -> bool:
    return bool(song_key) and bool(SONG_KEY_RE.match(str(song_key)))


# Link YouTube các dạng: watch?v=, youtu.be/, shorts/, embed/, live/.
_YT_URL_RE = re.compile(r"(?:[?&]v=|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])")


def song_key_from_input(text) -> str | None:
    """Ô tìm của admin → video_id nếu người gõ là mã 11 ký tự hoặc dán link YouTube.

    Kỹ thuật viên thường có sẵn link khách gửi; dán thẳng vào là mở đúng bài.
    """
    text = str(text or "").strip()
    if valid_song_key(text):
        return text
    match = _YT_URL_RE.search(text)
    return match.group(1) if match else None


def normalize_timeline(entries) -> list:
    """Rút timeline về phần CỐT LÕI để băm: (giây làm tròn, tên tone, scale).

    Bỏ confidence/bpm/duration vì chúng dao động theo từng lần dò — giữ lại thì
    hai máy dò ra cùng một chuỗi tone vẫn cho ra hash khác nhau và không bao giờ
    cộng được phiếu cho nhau.
    """
    result = []
    for entry in (entries or [])[:MAX_ENTRIES]:
        if not isinstance(entry, dict):
            continue
        try:
            time_s = int(round(float(entry.get("time", 0) or 0)))
        except (TypeError, ValueError):
            time_s = 0
        key_display = str(entry.get("key_display", "") or "").strip()
        if not key_display:
            continue
        scale = str(entry.get("scale", "") or "").strip() or "Major"
        result.append({"time": max(0, time_s), "key_display": key_display, "scale": scale})
    result.sort(key=lambda e: e["time"])
    return result


def payload_hash(song_key: str, normalized: list) -> str:
    """Băm ổn định: cùng chuỗi tone ⇒ cùng hash, không phụ thuộc thứ tự khoá JSON."""
    blob = json.dumps(
        {"k": song_key, "t": normalized},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def score(tone) -> int:
    """Điểm xếp hạng của một biến thể. Cao hơn = được chọn."""
    weight = SOURCE_WEIGHT.get((tone.source or "auto").lower(), 1)
    return weight * int(tone.votes or 0) - REPORT_PENALTY * int(tone.reports or 0)


def best_variant(tones):
    """Biến thể thắng trong một danh sách cùng bài.

    Thứ tự ưu tiên: dev ghim → điểm cao → bản do người sửa tay → mới cập nhật hơn.
    Bỏ qua biến thể đã bị ẩn và biến thể có điểm âm (báo sai áp đảo phiếu thuận).
    """
    usable = [t for t in tones if (t.status or "ok") == "ok"]
    if not usable:
        return None

    pinned = [t for t in usable if t.pinned]
    if pinned:
        return max(pinned, key=lambda t: (score(t), t.id))

    ranked = [t for t in usable if score(t) > 0]
    if not ranked:
        return None
    return max(
        ranked,
        key=lambda t: (
            score(t),
            1 if (t.source or "").lower() == "human" else 0,
            t.id,
        ),
    )


# ── So máy dò với bản người sửa (trang /admin/library/errors) ──
# Cùng quy ước với tools/danh_gia_do_tone.py ở client — đổi một bên thì đổi cả hai.
NOTES_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NOTES_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

# dung: đúng tuyệt đối | song_song: C↔Am (cùng 7 nốt — Auto-Tune kéo như nhau)
# quang5: lệch quãng 5 cùng thể | cung_ten: C↔Cm | khac: sai hẳn | khong_ro: không đọc được
ERROR_CLASSES = ("dung", "song_song", "quang5", "cung_ten", "khac", "khong_ro")


def parse_key(text):
    """'C#m' / 'Bb' / 'A Minor' → (index 0..11, 'Major'|'Minor'), hoặc None."""
    if not isinstance(text, str):
        return None
    words = text.strip().split()
    if not words:
        return None
    if len(words) == 2 and words[1].lower() in ("major", "minor", "maj", "min"):
        root, scale = words[0], ("Minor" if words[1].lower().startswith("min") else "Major")
    elif len(words) == 1 and len(words[0]) > 1 and words[0].endswith("m"):
        root, scale = words[0][:-1], "Minor"
    elif len(words) == 1:
        root, scale = words[0], "Major"
    else:
        return None
    root = root[0].upper() + root[1:]
    for names in (NOTES_SHARP, NOTES_FLAT):
        if root in names:
            return names.index(root), scale
    return None


def key_display(index: int, scale: str) -> str:
    """(6, 'Minor') → 'F#m' — cùng quy ước sharp của app (ToneDetector.MINOR_KEY_NAMES)."""
    return NOTES_SHARP[int(index) % 12] + ("m" if scale == "Minor" else "")


def parse_time(text) -> float | None:
    """'1:35' → 95.0, '95' → 95.0, '1:02:03' → 3723.0. None nếu không đọc được/âm."""
    parts = str(text or "").strip().split(":")
    if not parts or len(parts) > 3:
        return None
    # Chỉ chữ số và tối đa một dấu chấm: float() còn nhận "inf"/"nan"/"1e3" —
    # "inf" làm normalize_timeline ném OverflowError, "nan" đi vào timeline ghim
    # rồi phát tới mọi máy khách.
    if not all(re.fullmatch(r"\d+(\.\d+)?", p) for p in parts):
        return None
    nums = [float(p) for p in parts]
    total = 0.0
    for n in nums:
        total = total * 60 + n
    return total


def parse_timeline_text(text: str, primary_key: str) -> list | None:
    """Ô 'mốc thời gian' trên form admin → list entry chuẩn của thư viện.

    Mỗi mốc: `<mm:ss|giây> <tone>`, cách nhau bằng xuống dòng, dấu phẩy hoặc
    chấm phẩy (ô một dòng cũng gõ được nhiều mốc). Bỏ trống → một mốc 0s theo
    `primary_key`. Mốc đầu không ở 0s thì chèn `primary_key` vào 0s — thiếu cả
    hai thì không biết đầu bài hát tone gì. Mốc liền nhau cùng tone gộp làm một.
    Một mốc sai, hai mốc trùng giờ hay quá MAX_ENTRIES là trả None cho CẢ ô:
    admin sửa lại, không ghi nửa vời.
    """
    lines = [ln.strip() for ln in re.split(r"[\n\r,;]+", str(text or "")) if ln.strip()]
    if not lines:
        parsed = parse_key(primary_key)
        if not parsed:
            return None
        idx, scale = parsed
        return [{"time": 0.0, "key_display": key_display(idx, scale),
                 "key_index": idx, "scale": scale}]

    entries = []
    for line in lines:
        parts = line.split(None, 1)
        if len(parts) != 2:
            return None
        seconds = parse_time(parts[0])
        parsed = parse_key(parts[1])
        if seconds is None or not parsed:
            return None
        idx, scale = parsed
        entries.append({"time": seconds, "key_display": key_display(idx, scale),
                        "key_index": idx, "scale": scale})
    entries.sort(key=lambda e: e["time"])

    times = [e["time"] for e in entries]
    if len(set(times)) != len(times):
        return None
    if entries[0]["time"] > 0:
        parsed = parse_key(primary_key)
        if not parsed:
            return None
        idx, scale = parsed
        entries.insert(0, {"time": 0.0, "key_display": key_display(idx, scale),
                           "key_index": idx, "scale": scale})

    merged = [entries[0]]
    for entry in entries[1:]:
        if entry["key_display"] != merged[-1]["key_display"]:
            merged.append(entry)
    if len(merged) > MAX_ENTRIES:
        return None
    return merged


def _format_time(seconds: float) -> str:
    """95.0 → '1:35', 254.5 → '4:14.5', 3723 → '1:02:03' — đọc lại được bằng parse_time."""
    whole = int(seconds)
    frac = round(seconds - whole, 1)
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    tail = f"{secs:02d}" + (f"{frac:.1f}"[1:] if frac else "")
    return f"{hours}:{minutes:02d}:{tail}" if hours else f"{minutes}:{tail}"


def timeline_steps(entries) -> list:
    """Timeline → các bước để trang admin vẽ chuỗi 'Gm 0:00 → +1 → G#m 3:57'.

    delta = số nửa cung so với mốc trước, gần nhất trong -5..+6 ("" ở mốc đầu,
    "±0" khi chỉ đổi thể cùng chủ âm). Kỹ thuật viên cần biết bài nâng/hạ bao
    nhiêu chứ không chỉ tên tone.
    """
    if not isinstance(entries, list):
        return []
    steps, prev = [], None
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("key_display"):
            continue
        try:
            seconds = max(0.0, float(entry.get("time", 0) or 0))
        except (TypeError, ValueError):
            continue
        parsed = parse_key(entry["key_display"])
        delta = ""
        if prev is not None and parsed is not None:
            diff = (parsed[0] - prev[0]) % 12
            diff = diff - 12 if diff > 6 else diff
            delta = "±0" if diff == 0 else f"{diff:+d}"
        steps.append({"time": _format_time(seconds), "key": entry["key_display"], "delta": delta})
        prev = parsed
    return steps


def format_timeline(entries, sep: str = "\n") -> str:
    """Timeline đã lưu → chữ dạng ô 'mốc thời gian' (để hiện và điền sẵn form sửa)."""
    if not isinstance(entries, list):
        return ""
    parts = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("key_display"):
            continue
        try:
            seconds = max(0.0, float(entry.get("time", 0) or 0))
        except (TypeError, ValueError):
            continue
        parts.append(f"{_format_time(seconds)} {entry['key_display']}")
    return sep.join(parts)


# ── Cursor keyset cho /api/v1/library/changes ──
# Opaque với client: base64url(JSON {"ts": isoformat, "id": int}). `ts` giữ chuỗi
# ISO đúng như last_seen trong DB — đổi sang epoch float là lệch micro giây,
# vế tie-break `last_seen = :ts` không bao giờ khớp nữa.
def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def encode_cursor(last_seen: datetime, tone_id: int) -> str:
    payload = json.dumps({"ts": last_seen.isoformat(), "id": int(tone_id)}, separators=(",", ":"))
    return _b64(payload.encode("utf-8"))


def decode_cursor(text) -> tuple | None:
    """(last_seen, id) hoặc None nếu chuỗi hỏng — caller coi như cursor rỗng."""
    if not text or not isinstance(text, str):
        return None
    try:
        padded = text + "=" * (-len(text) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if not isinstance(data, dict) or not isinstance(data.get("ts"), str):
            return None
        ts = datetime.fromisoformat(data["ts"])
        tone_id = int(data["id"])
    except (ValueError, TypeError, KeyError, AttributeError):
        return None
    # Server luôn phát aware; chuỗi naive (file trạng thái bị sửa tay) mà để
    # nguyên thì Postgres cast theo TimeZone phiên → lệch giờ. Mốc là UTC.
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts, tone_id


def classify(truth, pred) -> str:
    """Xếp loại kết quả máy dò so với đáp án (cả hai là (index, scale) hoặc None)."""
    if truth is None or pred is None:
        return "khong_ro"
    (ti, ts), (pi, ps) = truth, pred
    if ti == pi and ts == ps:
        return "dung"
    if ts == ps and (pi - ti) % 12 in (5, 7):
        return "quang5"
    if ts != ps:
        major, minor = (ti, pi) if ts == "Major" else (pi, ti)
        if (major + 9) % 12 == minor:
            return "song_song"
        if ti == pi:
            return "cung_ten"
    return "khac"


def timeline_primary(tone_or_row):
    """Tone chính của một biến thể/lượt dò: primary_key, không có thì mốc đầu."""
    parsed = parse_key(getattr(tone_or_row, "primary_key", "") or "")
    if parsed:
        return parsed
    try:
        entries = json.loads(getattr(tone_or_row, "timeline", "") or "[]")
        return parse_key(entries[0].get("key_display", "")) if entries else None
    except (ValueError, TypeError, AttributeError):
        return None
