"""
Thư viện tone cộng đồng — máy nào đã dò thì cả mạng lưới dùng lại.

ĐỪNG NHẦM với core/licensing/sync.py:
  sync.py   : blob RIÊNG TƯ của một license, đồng bộ giữa các máy của CHÍNH
              khách đó. Tính năng Premium.
  file này  : dữ liệu DÙNG CHUNG giữa các khách hàng. Mọi máy đã kích hoạt đều
              đọc và ghi được — càng nhiều máy đóng góp thì tone càng chính xác.

Gửi lên server đúng ba thứ: mã video YouTube, tên bài, chuỗi tone. Bài không có
video_id (file local, loopback) KHÔNG BAO GIỜ rời khỏi máy — đường dẫn file vừa
là dữ liệu cá nhân vừa chẳng khớp được với máy khác.

Mọi hàm đều fail-soft: mất mạng, server sập, license hết hạn → app quay về đúng
luồng dò tone cũ, không báo lỗi ra mặt người dùng.
"""
import json
import logging
import threading
import time
import urllib.error
import urllib.request

from core.utils import extract_video_id

log = logging.getLogger(__name__)

_TIMEOUT = 10

# Số bài gửi/hỏi trong một lần gọi. Khớp trần của server (lookup 200, góp 50).
LOOKUP_BATCH = 200
CONTRIBUTE_BATCH = 50

# Bài server không có: nhớ trong RAM để mỗi lần mở lại không tốn thêm một vòng
# mạng vô ích. Chỉ sống theo tiến trình — khởi động lại app là hỏi lại, chấp
# nhận được vì thư viện chung dày lên theo ngày chứ không theo phút.
_MISS_TTL = 24 * 3600
_miss_cache = {}
_hit_cache = {}
_cache_lock = threading.Lock()
_queue_lock = threading.Lock()


# ── Cấu hình ──
def enabled() -> bool:
    """
    Có được dùng thư viện chung không.

    Mặc định BẬT (quyết định sản phẩm: tự động nền, không hỏi), nhưng luôn có
    công tắc tắt trong Thiết lập → settings.json: {"tone_share": {"enabled": false}}.
    """
    try:
        from core.config import ConfigManager
        cfg = (ConfigManager.load_settings() or {}).get("tone_share", {})
        if not cfg.get("enabled", True):
            return False
    except Exception:
        pass
    return _has_license() and bool(_server_base())


def _server_base() -> str:
    try:
        from core.licensing import client
        return client.server_url()
    except Exception:
        return ""


def _has_license() -> bool:
    try:
        from core.licensing import client
        return bool(client.has_online_license())
    except Exception:
        return False


def _auth_fields():
    """token + fingerprint cho request. None nếu máy chưa kích hoạt online."""
    try:
        from core.licensing import client
        from core.licensing.device import get_fingerprint
        token = (client._load() or {}).get("license_token")
        fp = get_fingerprint()
        if not token or not fp:
            return None
        return {"token": token, "device_fingerprint": fp}
    except Exception:
        return None


def _app_version() -> str:
    try:
        from core.version import __version__
        return __version__
    except Exception:
        return ""


def song_key(url):
    """Khoá dùng chung của một bài = YouTube video_id. None nếu không phải YouTube."""
    return extract_video_id(url)


# ── HTTP ──
def _post(path: str, payload: dict):
    base = _server_base()
    if not base:
        return 0, {}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{base}{path}",
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": f"QuangLuuStudio/{_app_version()}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        log.info("Thư viện tone không truy cập được: %s", e)
        return 0, {}


# ── Bộ nhớ đệm phiên ──
def _remember_miss(key):
    with _cache_lock:
        _miss_cache[key] = time.time()


def _recently_missed(key) -> bool:
    with _cache_lock:
        stamp = _miss_cache.get(key, 0)
    return bool(stamp) and (time.time() - stamp) < _MISS_TTL


def _remember_hit(key, entry):
    with _cache_lock:
        _hit_cache[key] = entry
        _miss_cache.pop(key, None)


def clear_session_cache():
    """Quên các lần tra trước (dùng khi test hoặc khi user bấm Đồng bộ ngay)."""
    with _cache_lock:
        _miss_cache.clear()
        _hit_cache.clear()


# ── Chuyển đổi ──
def _to_cache_entry(result) -> dict:
    """Kết quả từ server → đúng hình dạng entry của ToneCacheManager."""
    return {
        "primary_key": result.get("primary_key", ""),
        "title": result.get("title", ""),
        "key_timeline": result.get("timeline") or [],
        # Dấu vết nguồn: để biết đường báo sai khi người dùng sửa tay bản này,
        # và để KHÔNG đóng góp ngược lại chính dữ liệu vừa tải về.
        "origin": "community",
        "payload_hash": result.get("payload_hash", ""),
    }


def _save_local(url, entry):
    """Lưu vào cache tone local để lần sau dùng được cả khi mất mạng."""
    try:
        from core.tone_cache import ToneCacheManager
        ToneCacheManager.save_tone(url, entry)
    except Exception as e:
        log.debug("Không lưu được tone cộng đồng vào cache local: %s", e)


# ── API công khai ──
def lookup(url):
    """
    Tra tone của một bài trong thư viện chung.

    Trả entry kiểu tone_cache (có key_timeline) hoặc None. Trúng thì lưu luôn
    vào cache local. CHỈ gọi từ luồng nền — có đi mạng.
    """
    key = song_key(url)
    if not key or not enabled():
        return None

    with _cache_lock:
        cached = _hit_cache.get(key)
    if cached is not None:
        return cached
    if _recently_missed(key):
        return None

    found = lookup_many([url])
    return found.get(url)


def lookup_many(urls) -> dict:
    """
    Tra nhiều bài một lượt. Trả {url: entry} cho những bài có trong thư viện.

    Dùng cho nút "Đồng bộ tone" của màn Danh sách bài hát: một vòng mạng cho cả
    trăm bài thay vì một vòng mỗi bài.
    """
    if not enabled():
        return {}
    auth = _auth_fields()
    if auth is None:
        return {}

    # Gom theo song_key, giữ lại mọi URL trỏ tới cùng video (link youtu.be và
    # link watch?v= phải cùng hưởng một kết quả).
    by_key = {}
    for url in urls or []:
        key = song_key(url)
        if key:
            by_key.setdefault(key, []).append(url)
    if not by_key:
        return {}

    results = {}
    keys = list(by_key.keys())
    for start in range(0, len(keys), LOOKUP_BATCH):
        chunk = keys[start:start + LOOKUP_BATCH]
        status, body = _post("/api/v1/library/lookup", dict(auth, keys=chunk))
        if status != 200 or not body.get("ok"):
            if status != 0:
                log.info("Tra thư viện tone thất bại (%s): %s", status, body.get("message", ""))
            continue

        found = body.get("results") or {}
        for key in chunk:
            result = found.get(key)
            if not result or not result.get("timeline"):
                _remember_miss(key)
                continue
            entry = _to_cache_entry(result)
            _remember_hit(key, entry)
            for url in by_key[key]:
                results[url] = entry
                _save_local(url, entry)
    return results


def contribute(url, title, cache_data, source="auto") -> bool:
    """
    Đóng góp kết quả dò tone của máy này. Xếp hàng rồi gửi nền.

    Trả True nếu đã nhận vào hàng đợi. KHÔNG chặn luồng gọi.
    """
    key = song_key(url)
    if not key or not enabled() or not isinstance(cache_data, dict):
        return False

    timeline = cache_data.get("key_timeline") or []
    if not timeline:
        return False

    # Đừng gửi ngược lại thứ vừa tải về: nó không phải bằng chứng độc lập, chỉ
    # làm phồng số phiếu của chính biến thể đó một cách giả tạo.
    if cache_data.get("origin") == "community" and source != "human":
        return False

    item = {
        "song_key": key,
        "title": (title or cache_data.get("title") or "")[:300],
        "primary_key": cache_data.get("primary_key", "")[:20],
        "source": "human" if source == "human" else "auto",
        "timeline": [
            {
                "time": float(entry.get("time", 0) or 0),
                "key_display": str(entry.get("key_display", "") or "")[:20],
                "key_index": int(entry.get("key_index", 0) or 0),
                "scale": str(entry.get("scale", "Major") or "Major")[:20],
            }
            for entry in timeline
            if isinstance(entry, dict) and entry.get("key_display")
        ],
    }
    if not item["timeline"]:
        return False

    _enqueue({"kind": "contribute", "item": item})
    flush_queue()
    return True


def report_wrong(url, payload_hash="") -> bool:
    """Báo bản tone cộng đồng của bài này là sai (người dùng vừa sửa tay)."""
    key = song_key(url)
    if not key or not enabled():
        return False
    with _cache_lock:
        _hit_cache.pop(key, None)
        _miss_cache.pop(key, None)
    _enqueue({"kind": "report", "song_key": key, "payload_hash": payload_hash or ""})
    flush_queue()
    return True


# ── Hàng đợi (chịu được mất mạng) ──
def _queue_path():
    from core.config import _get_data_dir
    import os
    return os.path.join(_get_data_dir(), "tone_share_queue.json")


def _load_queue() -> list:
    try:
        with open(_queue_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_queue(items) -> None:
    try:
        with open(_queue_path(), "w", encoding="utf-8") as f:
            # Giữ tối đa 500 mục: quán dò cả ngày mất mạng cũng không phình vô hạn.
            json.dump(items[-500:], f, ensure_ascii=False)
    except Exception as e:
        log.debug("Không lưu được hàng đợi thư viện tone: %s", e)


def _enqueue(entry) -> None:
    with _queue_lock:
        queue = _load_queue()
        queue.append(entry)
        _save_queue(queue)


def _send_queue() -> None:
    """Gửi hết hàng đợi. Chạy trong luồng nền (đồng bộ, có đi mạng)."""
    if not enabled():
        return
    auth = _auth_fields()
    if auth is None:
        return

    with _queue_lock:
        pending = _load_queue()
        if not pending:
            return
        # Nhấc ra khỏi file trước khi gửi; mục nào gửi hụt thì trả lại ở dưới.
        _save_queue([])

    items = [e["item"] for e in pending if e.get("kind") == "contribute" and e.get("item")]
    reports = [e for e in pending if e.get("kind") == "report"]
    failed = []

    for start in range(0, len(items), CONTRIBUTE_BATCH):
        chunk = items[start:start + CONTRIBUTE_BATCH]
        status, body = _post("/api/v1/library/contribute", dict(auth, items=chunk))
        if status == 0:
            # Mất mạng → giữ lại đúng phần chưa gửi được.
            failed.extend({"kind": "contribute", "item": item} for item in chunk)
        elif status != 200 or not body.get("ok"):
            log.info("Đóng góp tone bị từ chối (%s): %s", status, body.get("message", ""))

    for entry in reports:
        status, _body = _post("/api/v1/library/report", dict(
            auth, song_key=entry.get("song_key", ""), payload_hash=entry.get("payload_hash", ""),
        ))
        if status == 0:
            failed.append(entry)

    if failed:
        with _queue_lock:
            _save_queue(failed + _load_queue())


def flush_queue() -> None:
    """Gửi hàng đợi ở luồng nền. Gọi được từ UI thread, không bao giờ chặn."""
    if not enabled():
        return
    threading.Thread(target=_send_queue, daemon=True).start()
