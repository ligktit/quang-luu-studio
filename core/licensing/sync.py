"""
Cloud Sync (tính năng Premium) — đồng bộ file dữ liệu người dùng qua licensing
server.

Các loại blob đồng bộ (kind → file local):
  songs     → saved_songs.json
  timelines → manual_timelines.json
  tones     → tone_cache.json
  scores    → score_history.json

Nguyên tắc:
  - CHỈ chạy khi entitlements.is_premium(). Standard → mọi hàm trả {skipped:'not_premium'}.
  - Đọc token/code/fingerprint từ activation cache (qua core.licensing.client._load()).
  - Gọi server bằng urllib (helper _request riêng, timeout 10s), fail-soft khi mạng lỗi.
  - Last-write-wins theo updated_at (mtime file local). Server giữ bản mới hơn.
  - Pull AN TOÀN: backup file local (.bak) trước khi ghi đè; với "songs" cố gắng
    MERGE theo song_match_key (giữ bài chỉ có ở local), các kind khác last-write-wins.

KHÔNG sửa client.py — chỉ tái dùng các helper đọc cache của nó.
"""
import json
import logging
import os
import shutil
import time
import urllib.error
import urllib.request

from core.config import (
    MANUAL_TIMELINES_FILE,
    SONGS_FILE,
    TONE_CACHE_FILE,
)
from core.utils import song_match_key

log = logging.getLogger(__name__)

_TIMEOUT = 10


def _scores_file() -> str:
    """Đường dẫn score_history.json (import trễ để tránh kéo phụ thuộc nặng)."""
    try:
        from core.score_history import HISTORY_FILE
        return HISTORY_FILE
    except Exception:
        from core.config import DATA_DIR
        return os.path.join(DATA_DIR, "score_history.json")


def _kind_files() -> dict:
    return {
        "songs": SONGS_FILE,
        "timelines": MANUAL_TIMELINES_FILE,
        "tones": TONE_CACHE_FILE,
        "scores": _scores_file(),
    }


KIND_FILES = _kind_files()
ALL_KINDS = tuple(KIND_FILES.keys())


# ── Tiện ích nội bộ ──
def _is_premium() -> bool:
    try:
        from core import entitlements
        return bool(entitlements.is_premium())
    except Exception as e:  # pragma: no cover - phòng thủ
        log.debug("is_premium fallback False: %s", e)
        return False


def _server_base() -> str:
    try:
        from core.licensing import client
        return client.server_url()
    except Exception:
        return ""


def _cache() -> dict:
    try:
        from core.licensing import client
        return client._load()
    except Exception:
        return {}


def _fingerprint() -> str:
    try:
        from core.licensing.device import get_fingerprint
        return get_fingerprint()
    except Exception:
        return str(_cache().get("device_fingerprint", "") or "")


def _request(method: str, path: str, payload: dict) -> tuple[int, dict]:
    """Gọi server bằng urllib. Trả (status, body). status=0 nếu mạng lỗi/không cấu hình."""
    base = _server_base()
    if not base:
        return 0, {}
    url = f"{base}{path}"
    try:
        from core.version import __version__
        ua = f"QuangLuuStudio/{__version__}"
    except Exception:
        ua = "QuangLuuStudio"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": ua},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}
    except Exception as e:  # network down / DNS / timeout
        log.info("Sync server unreachable: %s", e)
        return 0, {}


def _auth_fields() -> dict | None:
    """token + code + device_fingerprint cho request. None nếu chưa kích hoạt online."""
    cache = _cache()
    token = cache.get("license_token")
    code = cache.get("license_code")
    fp = _fingerprint()
    if not (token or code) or not fp:
        return None
    return {"token": token, "code": code, "device_fingerprint": fp}


def _read_local(path: str) -> tuple[str, float]:
    """Đọc nội dung file thô + mtime. ('', 0.0) nếu không có."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        return text, os.path.getmtime(path)
    except Exception:
        return "", 0.0


def _backup(path: str) -> None:
    try:
        if os.path.exists(path):
            shutil.copy2(path, path + ".bak")
    except Exception as e:
        log.warning("Không backup được %s: %s", path, e)


def _atomic_write(path: str, text: str) -> None:
    """Ghi text an toàn (tận dụng atomic_write_json nếu parse được JSON)."""
    from core.utils import atomic_write_json
    try:
        obj = json.loads(text)
        atomic_write_json(path, obj)
        return
    except Exception:
        pass
    # Fallback: ghi thô (không phải JSON hợp lệ — hiếm).
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def _merge_songs(local_text: str, remote_text: str) -> str:
    """Merge 2 list bài theo song_match_key(url). Giữ bài có ở cả hai; bản
    remote ưu tiên khi trùng key (last-write-wins ở cấp blob). Bài chỉ có local
    KHÔNG bị mất."""
    try:
        local = json.loads(local_text) if local_text else []
        remote = json.loads(remote_text) if remote_text else []
        if not isinstance(local, list) or not isinstance(remote, list):
            return remote_text
    except Exception:
        return remote_text

    merged: dict = {}
    order: list = []

    def _key(song):
        if not isinstance(song, dict):
            return None
        return song_match_key(song.get("url", "")) or song.get("id")

    for song in local:
        k = _key(song)
        if k is None:
            continue
        if k not in merged:
            order.append(k)
        merged[k] = song
    for song in remote:  # remote đè local khi trùng key
        k = _key(song)
        if k is None:
            continue
        if k not in merged:
            order.append(k)
        merged[k] = song

    return json.dumps([merged[k] for k in order], ensure_ascii=False, indent=4)


# ── API công khai ──
def push(kind: str) -> dict:
    """Đẩy file local lên server. Trả dict trạng thái."""
    if kind not in KIND_FILES:
        return {"ok": False, "error": f"kind không hợp lệ: {kind}"}
    if not _is_premium():
        return {"skipped": "not_premium", "kind": kind}
    auth = _auth_fields()
    if auth is None:
        return {"ok": False, "error": "not_activated", "kind": kind}

    path = KIND_FILES[kind]
    text, mtime = _read_local(path)
    if not text:
        return {"ok": True, "kind": kind, "noop": "no_local_data"}

    status, body = _request("PUT", f"/api/v1/sync/{kind}", {
        **auth,
        "data": text,
        "updated_at": mtime or time.time(),
    })
    if status == 0:
        return {"ok": False, "error": "offline", "kind": kind}
    if status == 200 and body.get("ok"):
        return {
            "ok": True, "kind": kind,
            "version": body.get("version"),
            "stale": bool(body.get("stale")),
        }
    return {"ok": False, "error": body.get("message") or f"http_{status}", "kind": kind}


def pull(kind: str) -> dict:
    """Kéo blob từ server, backup file local, ghi đè (hoặc merge với songs)."""
    if kind not in KIND_FILES:
        return {"ok": False, "error": f"kind không hợp lệ: {kind}"}
    if not _is_premium():
        return {"skipped": "not_premium", "kind": kind}
    auth = _auth_fields()
    if auth is None:
        return {"ok": False, "error": "not_activated", "kind": kind}

    status, body = _request("POST", f"/api/v1/sync/{kind}/get", auth)
    if status == 0:
        return {"ok": False, "error": "offline", "kind": kind}
    if status != 200 or not body.get("ok"):
        return {"ok": False, "error": body.get("message") or f"http_{status}", "kind": kind}
    if not body.get("exists"):
        return {"ok": True, "kind": kind, "noop": "no_remote_data"}

    remote_text = body.get("data") or ""
    if not remote_text:
        return {"ok": True, "kind": kind, "noop": "empty_remote"}

    path = KIND_FILES[kind]
    local_text, _ = _read_local(path)
    _backup(path)

    if kind == "songs":
        out_text = _merge_songs(local_text, remote_text)
        merged = True
    else:
        out_text = remote_text  # last-write-wins
        merged = False

    try:
        _atomic_write(path, out_text)
    except Exception as e:
        log.warning("Ghi %s thất bại: %s", path, e)
        return {"ok": False, "error": "write_failed", "kind": kind}

    return {
        "ok": True, "kind": kind, "merged": merged,
        "version": body.get("version"),
    }


def sync_all() -> dict:
    """Push rồi pull mọi kind. Fail-soft: lỗi 1 kind không chặn kind khác."""
    if not _is_premium():
        return {"skipped": "not_premium"}
    results: dict = {}
    for kind in ALL_KINDS:
        try:
            results[kind] = {"push": push(kind), "pull": pull(kind)}
        except Exception as e:  # pragma: no cover
            log.warning("sync_all lỗi kind=%s: %s", kind, e)
            results[kind] = {"error": str(e)}
    return {"ok": True, "results": results}
