"""Thư viện tone cộng đồng — chuẩn hoá, băm và xếp hạng biến thể.

Toàn bộ luật "kết quả nào là đúng" nằm ở đây, tách khỏi router để test được mà
không cần dựng HTTP.

Vì sao SERVER băm chứ không nhận hash từ client: hash là thứ quyết định hai kết
quả có được coi là một hay không. Để client tự tính thì (a) client cũ/mới đổi
công thức là cả thư viện vỡ thành nghìn mảnh, (b) một client sửa đổi có thể gửi
hash trùng với biến thể đang thắng để "mượn" phiếu của nó.
"""
import hashlib
import json
import re

# song_key CHỈ nhận YouTube video_id 11 ký tự. Đường dẫn file local vừa là dữ
# liệu cá nhân vừa không khớp được giữa các máy — chặn ngay ở cổng.
SONG_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

SOURCES = ("auto", "human")

# Trần độ dài timeline. Một bài 10 phút chuyển tone mỗi 5 giây cũng chỉ ~120 mốc;
# 300 là dư dả mà vẫn chặn được payload phá hoại.
MAX_ENTRIES = 300

# Trọng số nguồn: một người nghe rồi sửa tay đáng tin hơn hẳn ba máy dò tự động
# — máy dò sai theo cùng một kiểu thì càng nhiều máy càng sai giống nhau.
SOURCE_WEIGHT = {"human": 3, "auto": 1}

# Mỗi lượt báo sai trừ nặng hơn một phiếu thuận: hát sai tone tốn tiền của quán,
# còn bỏ sót một bản đúng thì chỉ tốn một lần dò lại.
REPORT_PENALTY = 2


def valid_song_key(song_key) -> bool:
    return bool(song_key) and bool(SONG_KEY_RE.match(str(song_key)))


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
