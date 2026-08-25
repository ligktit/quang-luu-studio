"""
Hỗ trợ — kênh HAI CHIỀU giữa khách và dev, đi qua licensing server.

Khác core/crash_reporter.py (tự động, một chiều, chỉ bắt được lỗi làm app SẬP):
ở đây khách chủ động mô tả vấn đề, dev trả lời trên admin web, khách đọc lại
ngay trong app.

Đặc điểm:
  - Chỉ cần device fingerprint, KHÔNG cần license token: máy đang không kích
    hoạt được chính là máy cần hỗ trợ nhất.
  - Hàng đợi offline: gửi hụt thì cất vào support_queue.json, thử lại ở lần
    chạy sau (flush_queue()) — quán karaoke hay mất mạng giữa chừng.
  - Mọi hàm đều fail-soft, không bao giờ raise ra UI.

Tích hợp: ui/dialogs/support_dialog.py gọi submit()/inbox()/reply(); main.py gọi
flush_queue() + poll_inbox() trong _background_maintenance.
"""
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

_TIMEOUT = 10

CATEGORIES = (
    ("loi", "Báo lỗi"),
    ("huong_dan", "Cần hướng dẫn"),
    ("tinh_nang", "Góp ý tính năng"),
    ("khac", "Khác"),
)

# Số yêu cầu chưa đọc, cập nhật bởi poll_inbox()/inbox(). UI đọc qua
# unread_count() để vẽ chấm đỏ mà không phải gọi mạng.
_unread = 0
_unread_lock = threading.Lock()


def _server_base() -> str:
    """Dùng lại URL server của licensing (không tự chế cấu hình riêng)."""
    try:
        from core.licensing import client
        return client.server_url()
    except Exception:
        return ""


def _fingerprint() -> str:
    try:
        from core.licensing.device import get_fingerprint
        return get_fingerprint()
    except Exception:
        return ""


def _app_version() -> str:
    try:
        from core.version import __version__
        return __version__
    except Exception:
        return ""


def _device_context() -> dict:
    """hostname/os/license_code — best-effort, thiếu cái nào cũng không sao."""
    ctx = {"hostname": None, "os": None, "license_code": None, "app_version": _app_version()}
    try:
        from core.licensing.device import device_info
        info = device_info()
        ctx["hostname"] = info.get("hostname")
        ctx["os"] = info.get("os")
    except Exception:
        pass
    try:
        from core.config import ACTIVATION_FILE
        with open(ACTIVATION_FILE, encoding="utf-8") as f:
            act = json.load(f)
        ctx["license_code"] = act.get("license_code") or act.get("activation_code")
    except Exception:
        pass
    return ctx


def available() -> bool:
    """Có đủ điều kiện dùng kênh hỗ trợ không (có server + có fingerprint)."""
    return bool(_server_base()) and len(_fingerprint()) >= 8


def _log_tail(max_lines: int = 120) -> str:
    """Đuôi errors.log — dùng lại đúng hàm của crash_reporter, không viết lại."""
    try:
        from core.crash_reporter import _errors_log_tail
        return _errors_log_tail(max_lines)
    except Exception:
        return ""


# ── Hàng đợi offline ──
def _queue_path() -> Path:
    from core.config import _get_data_dir
    return Path(_get_data_dir()) / "support_queue.json"


def _load_queue() -> list:
    try:
        with open(_queue_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_queue(items: list) -> None:
    try:
        with open(_queue_path(), "w", encoding="utf-8") as f:
            json.dump(items[-20:], f, ensure_ascii=False)
    except Exception as e:
        log.debug("Không lưu được hàng đợi hỗ trợ: %s", e)


# ── HTTP ──
def _post(path: str, payload: dict) -> tuple:
    """POST tới server. Trả (status, body); status=0 nghĩa là không tới được server."""
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
        log.info("Máy chủ hỗ trợ không truy cập được: %s", e)
        return 0, {}


# ── API công khai ──
def submit(category, subject, body, contact="", include_logs=True) -> dict:
    """
    Gửi một yêu cầu hỗ trợ.

    Trả {ok, ticket_code, queued, message}. queued=True nghĩa là chưa gửi được
    (mất mạng) nhưng đã cất vào hàng đợi — KHÔNG phải lỗi, lần chạy sau tự gửi.
    """
    fp = _fingerprint()
    if len(fp) < 8:
        return {"ok": False, "queued": False, "ticket_code": "",
                "message": "Không xác định được máy này. Vui lòng khởi động lại app."}
    if not (subject or "").strip() or not (body or "").strip():
        return {"ok": False, "queued": False, "ticket_code": "",
                "message": "Vui lòng nhập tiêu đề và nội dung."}

    ctx = _device_context()
    payload = {
        "device_fingerprint": fp,
        "license_code": ctx["license_code"],
        "hostname": ctx["hostname"],
        "os": ctx["os"],
        "app_version": ctx["app_version"],
        "contact": (contact or "").strip()[:120] or None,
        "category": category if category in dict(CATEGORIES) else "khac",
        "subject": subject.strip()[:200],
        "body": body.strip()[:8000],
    }
    if include_logs:
        payload["log_excerpt"] = _log_tail()[:20000] or None

    status, resp = _post("/api/v1/support/ticket", payload)
    if status == 200 and resp.get("ok"):
        return {"ok": True, "queued": False, "ticket_code": resp.get("ticket_code", ""), "message": ""}
    if status == 0:
        queue = _load_queue()
        queue.append(payload)
        _save_queue(queue)
        return {"ok": False, "queued": True, "ticket_code": "",
                "message": "Chưa có mạng — yêu cầu đã được lưu và sẽ tự gửi khi máy online."}
    return {"ok": False, "queued": False, "ticket_code": "",
            "message": resp.get("message") or "Máy chủ từ chối yêu cầu. Vui lòng thử lại sau."}


def inbox() -> dict:
    """
    Lấy hộp thư của máy này. Trả {ok, unread_count, tickets, message}.

    Cập nhật luôn bộ đếm chưa đọc dùng cho chấm đỏ trên header.
    """
    fp = _fingerprint()
    if len(fp) < 8:
        return {"ok": False, "unread_count": 0, "tickets": [],
                "message": "Không xác định được máy này."}

    status, resp = _post("/api/v1/support/inbox", {"device_fingerprint": fp})
    if status == 200 and resp.get("ok"):
        _set_unread(int(resp.get("unread_count") or 0))
        return {"ok": True, "unread_count": unread_count(),
                "tickets": resp.get("tickets") or [], "message": ""}
    if status == 0:
        return {"ok": False, "unread_count": unread_count(), "tickets": [],
                "message": "Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại."}
    return {"ok": False, "unread_count": unread_count(), "tickets": [],
            "message": resp.get("message") or "Không tải được hộp thư."}


def reply(ticket_code, body) -> dict:
    """Khách trả lời tiếp trong một yêu cầu đã có."""
    fp = _fingerprint()
    if len(fp) < 8 or not (body or "").strip():
        return {"ok": False, "message": "Vui lòng nhập nội dung."}
    status, resp = _post("/api/v1/support/ticket/reply", {
        "device_fingerprint": fp,
        "ticket_code": ticket_code,
        "body": body.strip()[:8000],
    })
    if status == 200 and resp.get("ok"):
        return {"ok": True, "message": ""}
    if status == 0:
        return {"ok": False, "message": "Không kết nối được máy chủ. Vui lòng thử lại khi có mạng."}
    return {"ok": False, "message": resp.get("message") or "Không gửi được trả lời."}


def mark_read(ticket_code) -> bool:
    """Đánh dấu đã đọc trả lời của dev (tắt chấm đỏ)."""
    fp = _fingerprint()
    if len(fp) < 8:
        return False
    status, resp = _post("/api/v1/support/ticket/read", {
        "device_fingerprint": fp, "ticket_code": ticket_code,
    })
    ok = status == 200 and bool(resp.get("ok"))
    if ok:
        _set_unread(unread_count() - 1)
    return ok


def unread_count() -> int:
    """Số trả lời chưa đọc đã biết (KHÔNG gọi mạng — an toàn cho UI thread)."""
    with _unread_lock:
        return _unread


def _set_unread(value) -> None:
    global _unread
    with _unread_lock:
        _unread = max(0, int(value))


def poll_inbox() -> int:
    """
    Hỏi server xem có trả lời mới không. Gọi từ luồng NỀN.

    Trả về số yêu cầu chưa đọc (0 nếu không có / không hỏi được).
    """
    if not available():
        return 0
    try:
        result = inbox()
        return int(result.get("unread_count") or 0) if result.get("ok") else 0
    except Exception as e:
        log.debug("poll_inbox bỏ qua: %s", e)
        return 0


def flush_queue() -> None:
    """Gửi lại các yêu cầu tồn đọng. Gọi nền lúc khởi động / theo chu kỳ."""
    def _run():
        try:
            if not available():
                return
            remaining = []
            for payload in _load_queue():
                status, resp = _post("/api/v1/support/ticket", payload)
                if status == 200 and resp.get("ok"):
                    time.sleep(0.2)
                    continue
                if status == 0:
                    # Vẫn mất mạng → giữ nguyên phần còn lại cho lần sau.
                    remaining.append(payload)
                    break
                # Server từ chối hẳn (dữ liệu sai / quá hạn mức): bỏ, đừng kẹt
                # hàng đợi mãi mãi vì một mục hỏng.
                log.info("Bỏ yêu cầu hỗ trợ tồn đọng: %s", resp.get("message") or status)
            _save_queue(remaining)
        except Exception as e:
            log.debug("flush_queue hỗ trợ lỗi: %s", e)

    threading.Thread(target=_run, daemon=True).start()
