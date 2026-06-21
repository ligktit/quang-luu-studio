"""
Crash reporter — gửi traceback tự động về server license/update.

Đặc điểm:
  - Chỉ hoạt động khi app_config.json có 'license_server_url' và người dùng
    không tắt (settings.json: crash_report.enabled, mặc định bật).
  - Gửi nền (thread) để không chặn lúc app đang crash.
  - Hàng đợi offline: nếu không gửi được, lưu vào crash_queue.json và thử lại
    ở lần chạy sau (flush_queue()).
  - Kèm: app version, OS, device fingerprint, mã license, đuôi errors.log.
  - KHÔNG gửi thông tin nhận dạng cá nhân ngoài hostname/fingerprint đã băm.

Tích hợp: main.py gọi report_exception() trong sys.excepthook / threading.excepthook,
và flush_queue() lúc khởi động.
"""
import json
import logging
import threading
import time
import traceback as _tb
import urllib.error
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

_TIMEOUT = 10


def _server_base() -> str:
    try:
        from core.config import AppConfig
        return str(AppConfig.get("license_server_url", "") or "").rstrip("/")
    except Exception:
        return ""


def _enabled() -> bool:
    if not _server_base():
        return False
    try:
        from core.config import ConfigManager
        cfg = (ConfigManager.load_settings() or {}).get("crash_report", {})
        return bool(cfg.get("enabled", True))
    except Exception:
        return True


def _queue_path() -> Path:
    from core.config import _get_data_dir
    return Path(_get_data_dir()) / "crash_queue.json"


def _errors_log_tail(max_lines: int = 120) -> str:
    try:
        from core.config import _get_data_dir
        log_file = Path(_get_data_dir()) / "logs" / "errors.log"
        if not log_file.exists():
            return ""
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max_lines:])
    except Exception:
        return ""


def _context() -> dict:
    """device fingerprint + mã license + os (best-effort)."""
    info = {"device_fingerprint": None, "license_code": None, "os": None}
    try:
        from core.licensing.device import device_info, get_fingerprint
        info["device_fingerprint"] = get_fingerprint()
        info["os"] = device_info().get("os")
    except Exception:
        pass
    try:
        from core.config import ACTIVATION_FILE
        with open(ACTIVATION_FILE, encoding="utf-8") as f:
            act = json.load(f)
        info["license_code"] = act.get("license_code") or act.get("activation_code")
    except Exception:
        pass
    return info


def _app_version() -> str:
    try:
        from core.version import __version__
        return __version__
    except Exception:
        return ""


# ── Hàng đợi offline ──
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
            json.dump(items[-50:], f)  # giữ tối đa 50 report gần nhất
    except Exception:
        pass


def _post(payload: dict) -> bool:
    base = _server_base()
    if not base:
        return False
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/api/v1/crash",
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": f"QuangLuuStudio/{_app_version()}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.status == 200
    except Exception as e:
        log.info("Crash report send failed: %s", e)
        return False


def _build_payload(tb_text: str) -> dict:
    ctx = _context()
    return {
        "device_fingerprint": ctx["device_fingerprint"],
        "license_code": ctx["license_code"],
        "app_version": _app_version(),
        "os": ctx["os"],
        "traceback": tb_text[:20000],
        "log_excerpt": _errors_log_tail()[:20000],
    }


def _send_or_queue(payload: dict) -> None:
    if not _post(payload):
        q = _load_queue()
        q.append(payload)
        _save_queue(q)


# ── API công khai ──
def report_exception(exc_type, exc_value, exc_tb, *, block: bool = False) -> None:
    """Gửi 1 crash report. Gọi trong excepthook. Không raise."""
    try:
        if not _enabled():
            return
        tb_text = "".join(_tb.format_exception(exc_type, exc_value, exc_tb))
        payload = _build_payload(tb_text)
        if block:
            _send_or_queue(payload)
        else:
            threading.Thread(target=_send_or_queue, args=(payload,), daemon=True).start()
    except Exception as e:  # crash reporter KHÔNG được tự gây crash
        log.debug("report_exception failed: %s", e)


def flush_queue() -> None:
    """Thử gửi lại các report tồn đọng. Gọi nền lúc khởi động."""
    def _run():
        try:
            if not _enabled():
                return
            remaining = []
            for payload in _load_queue():
                if not _post(payload):
                    remaining.append(payload)
                    break  # server vẫn lỗi → để lần sau
                time.sleep(0.2)
            _save_queue(remaining)
        except Exception as e:
            log.debug("flush_queue failed: %s", e)

    threading.Thread(target=_run, daemon=True).start()
