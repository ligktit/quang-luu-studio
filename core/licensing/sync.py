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
  - Push CHỈ khi nội dung đổi: nhớ sha256 của lần đẩy thành công gần nhất
    (sync_state.json trong DATA_DIR); nội dung y hệt thì không đi mạng.
  - sync_all chạy 4 kind SONG SONG và KHÔNG chạy chồng: lượt nền 6 giờ và nút
    "Đồng bộ ngay" trong Thiết lập dùng chung một khoá, lượt sau trả
    {skipped:'busy'}. Trước đây 8 request tuần tự × timeout 10s = tới 80 giây
    chờ khi mạng chập chờn, lại còn hai lượt giẫm nhau.

KHÔNG sửa client.py — chỉ tái dùng các helper đọc cache của nó.
"""
import hashlib
import json
import logging
import os
import shutil
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

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


# ── Trạng thái đồng bộ (hash lần đẩy gần nhất) ──
_state_lock = threading.Lock()
# Khoá chống chạy chồng giữa lượt nền và lượt bấm tay.
_SYNC_LOCK = threading.Lock()


def _state_path() -> str:
    from core.config import DATA_DIR
    return os.path.join(DATA_DIR, "sync_state.json")


def _load_state() -> dict:
    try:
        with open(_state_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_state(state: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_state_path()), exist_ok=True)
        tmp = _state_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, _state_path())
    except Exception as e:
        log.debug("Không lưu được sync_state: %s", e)


def _remember_pushed(kind: str, text: str, version=None) -> None:
    """Ghi nhớ nội dung đã lên server (hoặc vừa lấy về) + version server, để lần
    sau khỏi đẩy lại và để nhận ra server bị lùi (khôi phục bản sao lưu cũ)."""
    with _state_lock:
        state = _load_state()
        state.setdefault("pushed", {})[kind] = _digest(text)
        if version is not None:
            try:
                state.setdefault("versions", {})[kind] = int(version)
            except (TypeError, ValueError):
                pass
        _write_state(state)


def _forget_pushed(kind: str) -> None:
    """Server không còn (hoặc lùi) dữ liệu của kind này → lần push kế phải đẩy lại."""
    with _state_lock:
        state = _load_state()
        (state.get("pushed") or {}).pop(kind, None)
        (state.get("versions") or {}).pop(kind, None)
        _write_state(state)


def _has_pushed_state(kind: str) -> bool:
    with _state_lock:
        return kind in (_load_state().get("pushed") or {})


def _remembered_version(kind: str):
    with _state_lock:
        return (_load_state().get("versions") or {}).get(kind)


def _already_pushed(kind: str, text: str) -> bool:
    with _state_lock:
        return (_load_state().get("pushed") or {}).get(kind) == _digest(text)


def _digest(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


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
    if _already_pushed(kind, text):
        return {"ok": True, "kind": kind, "noop": "unchanged"}

    status, body = _request("PUT", f"/api/v1/sync/{kind}", {
        **auth,
        "data": text,
        "updated_at": mtime or time.time(),
    })
    if status == 0:
        return {"ok": False, "error": "offline", "kind": kind}
    if status == 200 and body.get("ok"):
        _remember_pushed(kind, text, body.get("version"))
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
        # Server trống trong khi máy này từng đẩy → server mất dữ liệu. Quên hash
        # để lần push kế (ngay trong lượt này, xem _sync_kind) đẩy lại.
        had = _has_pushed_state(kind)
        if had:
            _forget_pushed(kind)
        return {"ok": True, "kind": kind, "noop": "no_remote_data", "repush": had}

    # Server trả version NHỎ HƠN version máy này đã đẩy → server được khôi phục
    # từ bản sao lưu cũ. Local thắng: không cho bản cũ đè, và đẩy lại local.
    mine = _remembered_version(kind)
    try:
        remote_version = int(body.get("version")) if body.get("version") is not None else None
    except (TypeError, ValueError):
        remote_version = None
    if mine is not None and remote_version is not None and remote_version < mine:
        _forget_pushed(kind)
        return {"ok": True, "kind": kind, "noop": "server_rolled_back", "repush": True,
                "remote_version": remote_version, "local_version": mine}

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

    # Bản vừa lấy về (không merge) chính là bản server đang giữ — nhớ lại để
    # lượt sau không đẩy ngược y nguyên nó lên.
    if not merged:
        _remember_pushed(kind, out_text, body.get("version"))

    return {
        "ok": True, "kind": kind, "merged": merged,
        "version": body.get("version"),
    }


def _sync_kind(kind: str) -> dict:
    try:
        out = {"push": push(kind), "pull": pull(kind)}
        # pull phát hiện server mất/lùi dữ liệu → đẩy lại ngay, không chờ lượt sau.
        if out["pull"].get("repush"):
            out["repush"] = push(kind)
        return out
    except Exception as e:  # pragma: no cover
        log.warning("sync_all lỗi kind=%s: %s", kind, e)
        return {"error": str(e)}


def sync_all() -> dict:
    """Push rồi pull mọi kind, các kind chạy song song. Fail-soft: lỗi 1 kind
    không chặn kind khác. Đang có lượt khác chạy → {skipped:'busy'}."""
    if not _is_premium():
        return {"skipped": "not_premium"}
    if not _SYNC_LOCK.acquire(blocking=False):
        return {"skipped": "busy"}
    try:
        kinds = list(ALL_KINDS)
        with ThreadPoolExecutor(max_workers=len(kinds), thread_name_prefix="cloud-sync") as pool:
            outcomes = list(pool.map(_sync_kind, kinds))
        return {"ok": True, "results": dict(zip(kinds, outcomes))}
    finally:
        _SYNC_LOCK.release()


def summarize(result: dict) -> str:
    """Một câu cho người dùng đọc — không bao giờ hiện dict thô lên UI."""
    if not isinstance(result, dict):
        return "Đồng bộ thất bại."
    skipped = result.get("skipped")
    if skipped == "not_premium":
        return "Chỉ dành cho gói Premium."
    if skipped == "busy":
        return "Đang có lượt đồng bộ khác chạy — chờ xong rồi thử lại."
    results = result.get("results") or {}
    if not results:
        return "Đồng bộ thất bại."

    failed = {}
    for kind, outcome in results.items():
        if "error" in outcome:
            failed[kind] = str(outcome["error"])
            continue
        for step in ("push", "pull", "repush"):
            part = outcome.get(step) or {}
            if part.get("ok") is False:
                failed[kind] = str(part.get("error") or "lỗi")
                break

    total = len(results)
    if not failed:
        return f"Đã đồng bộ xong ({total}/{total} mục)."
    if len(failed) == total and all(err == "offline" for err in failed.values()):
        return "Không kết nối được máy chủ — sẽ tự thử lại sau."
    detail = ", ".join(f"{kind}: {err}" for kind, err in failed.items())
    return f"Đồng bộ {total - len(failed)}/{total} mục, {len(failed)} lỗi ({detail})."
