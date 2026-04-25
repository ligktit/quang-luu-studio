import os
import sys
import ctypes
import atexit
import shutil
import threading
import logging

# ── PyInstaller _MEI cleanup ──────────────────────────────────────────────────
def _cleanup_mei():
    """Xóa thư mục tạm _MEI khi app thoát (chỉ chạy trong PyInstaller frozen mode)."""
    if not getattr(sys, 'frozen', False):
        return
    mei_dir = getattr(sys, '_MEIPASS', None)
    if mei_dir and os.path.isdir(mei_dir):
        shutil.rmtree(mei_dir, ignore_errors=True)

atexit.register(_cleanup_mei)

# ── DPI awareness — BEFORE Qt import ─────────────────────────────────────────
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_ssize_t(-4))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
os.environ["QT_OPENGL"] = "angle"

# ── Logging — init before any core import ─────────────────────────────────────
from pathlib import Path
from core.logger import setup_logging, get_logger
try:
    from core.logger import flush_logs
except ImportError:
    def flush_logs(): pass  # noqa: E704 — fallback cho bản build cũ
from core.config import _get_data_dir

_LOG_DIR = Path(_get_data_dir()) / "logs"
setup_logging(_LOG_DIR, level=logging.INFO)
log = get_logger(__name__)

# Bắt crash không được xử lý từ bất kỳ thread nào
def _excepthook(exc_type, exc_value, exc_tb):
    log.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
    flush_logs()
sys.excepthook = _excepthook

def _thread_excepthook(args):
    if args.exc_type is SystemExit:
        return
    log.critical("Unhandled exception in thread '%s'", args.thread, exc_info=(
        args.exc_type, args.exc_value, args.exc_tb))
    flush_logs()
threading.excepthook = _thread_excepthook

from core.version import __version__
log.info("Quang Lưu Studio v%s starting", __version__)

import backend
import frontend_qt


# ── Update check ──────────────────────────────────────────────────────────────

def _schedule_update_check():
    """
    Chạy sau khi MainDashboard đã hiển thị (non-blocking background thread).
    Nếu có phiên bản mới, emit signal để show dialog ở main thread.
    """
    from core.updater import check_and_notify_update
    from core.config import ConfigManager
    import time

    # Respect user preference
    settings   = ConfigManager.load_settings() or {}
    update_cfg = settings.get("update", {})
    if not update_cfg.get("auto_check", True):
        return

    # Rate-limit: check at most once per 24h
    import time as _time
    last_check = update_cfg.get("last_check_timestamp", 0)
    if _time.time() - last_check < 86400:
        log.info("Update check skipped (checked within last 24h)")
        return

    def _on_update_available(release):
        from ui.dialogs.update_dialog import UpdateDialog
        if UpdateDialog.should_skip(release.version):
            log.info("Update %s skipped by user preference", release.version)
            return

        # Marshal to Qt main thread via QMetaObject.invokeMethod / signal
        try:
            from PySide6.QtCore import QMetaObject, Qt
            from PySide6.QtWidgets import QApplication

            def _show():
                app = QApplication.instance()
                if app:
                    dlg = UpdateDialog(release)
                    dlg.exec()

            QMetaObject.invokeMethod(
                QApplication.instance(),
                "invokeMethod",
                Qt.QueuedConnection,
            )
            # Simpler fallback: schedule via singleShot
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, _show)
        except Exception as e:
            log.warning("Could not show update dialog: %s", e)

    check_and_notify_update(on_update_available=_on_update_available)

    # Update last check timestamp
    try:
        from core.config import ConfigManager
        import time as _t
        settings   = ConfigManager.load_settings() or {}
        update_cfg = settings.get("update", {})
        update_cfg["last_check_timestamp"] = _t.time()
        settings["update"] = update_cfg
        ConfigManager.save_settings(settings)
    except Exception:
        pass


# ── App lifecycle ─────────────────────────────────────────────────────────────

def _license_or_trial_expired():
    am = backend.ActivationManager
    return (am.is_activated() and am.is_expired()) or am.is_trial_expired()


def main():
    """
    App lifecycle loop — avoid recursion to prevent stack accumulation
    when the user reactivates or saves setup multiple times.
    """
    while True:
        # 1. Activation / trial gate
        if backend.ActivationManager.needs_activation():
            dialog = frontend_qt.ActivationDialog(is_expired=_license_or_trial_expired())
            dialog.mainloop()
            if not dialog.activated:
                log.info("User exited without activating")
                return
            continue

        if backend.ActivationManager.is_trial_active():
            days = backend.ActivationManager.get_trial_days_remaining()
            log.info("[TRIAL] %d days remaining", int(days))

        # 2. Settings
        settings = backend.ConfigManager.load_settings()

        # 3. Route
        if settings:
            # Launch update check in background after dashboard shows
            threading.Thread(target=_schedule_update_check, daemon=True).start()
            frontend_qt.MainDashboard(settings).mainloop()
            log.info("Dashboard closed, exiting")
            return
        else:
            setup = frontend_qt.SetupView()
            setup.mainloop()
            if not setup._saved:
                log.info("Setup cancelled, exiting")
                return


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("Unhandled exception in main()")
    finally:
        log.info("App exiting — log dir: %s", _LOG_DIR)
        flush_logs()
        logging.shutdown()
        _cleanup_mei()
        os._exit(0)
