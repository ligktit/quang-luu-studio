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

# ── QtWebEngine: chia sẻ OpenGL context ──────────────────────────────────────
# Bắt buộc set TRƯỚC khi QApplication được tạo, nếu không QWebEngineView (màn hình
# karaoke nhúng của bản Heavy) chỉ hiện màn đen. Vô hại với bản Light (không có
# QtWebEngine) — chỉ là 1 cờ thuộc tính của Qt.
try:
    from PySide6.QtCore import Qt, QCoreApplication
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
except Exception:
    pass

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

# Gửi crash về server (best-effort, không raise nếu reporter lỗi)
def _report_crash(exc_type, exc_value, exc_tb):
    try:
        from core.crash_reporter import report_exception
        report_exception(exc_type, exc_value, exc_tb)
    except Exception:
        pass

# Bắt crash không được xử lý từ bất kỳ thread nào
def _excepthook(exc_type, exc_value, exc_tb):
    log.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
    _report_crash(exc_type, exc_value, exc_tb)
    flush_logs()
sys.excepthook = _excepthook

def _thread_excepthook(args):
    if args.exc_type is SystemExit:
        return
    log.critical("Unhandled exception in thread '%s'", args.thread, exc_info=(
        args.exc_type, args.exc_value, args.exc_tb))
    _report_crash(args.exc_type, args.exc_value, args.exc_tb)
    flush_logs()
threading.excepthook = _thread_excepthook

from core.version import __version__
log.info("Quang Lưu Studio v%s starting", __version__)

# Theme VIP: ghi đè palette sang Gold & Kim cương TRƯỚC khi import frontend_qt
# (APP_QSS = load_qss() đóng băng lúc import) để toàn app mang tông vàng.
try:
    from ui.premium_theme import apply_if_premium
    if apply_if_premium():
        log.info("Áp theme Premium: Gold & Diamond")
except Exception as e:
    log.debug("premium theme skipped: %s", e)

import backend
import frontend_qt


# ── Update check ──────────────────────────────────────────────────────────────

from PySide6.QtCore import QObject, Signal


class _UpdateNotifier(QObject):
    """Cầu nối thread: worker emit signal → slot chạy trên main thread (queued)."""
    update_available = Signal(object)


def _show_update_dialog(release):
    """Slot main-thread: hiển thị dialog cập nhật."""
    try:
        from ui.dialogs.update_dialog import UpdateDialog
        dlg = UpdateDialog(release)
        dlg.exec()
    except Exception as e:
        log.warning("Could not show update dialog: %s", e)


def _schedule_update_check(notifier):
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
        # Marshal sang main thread: emit signal từ worker → AutoConnection
        # thành queued vì notifier thuộc main thread → slot show dialog an toàn.
        notifier.update_available.emit(release)

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


class _LicenseNotifier(QObject):
    """Cầu nối thread cho cảnh báo license (worker → dialog ở main thread)."""
    license_lost = Signal(str)


def _show_license_lost_dialog(message):
    """Slot main-thread: báo license không còn hiệu lực giữa phiên đang chạy.

    Cố tình KHÔNG đóng app: máy này thường đang hát trực tiếp trước khán giả.
    Quyền Premium đã bị thu ngay khi cache bị xoá; cổng kích hoạt sẽ chặn ở lần
    mở app kế tiếp.
    """
    try:
        from PySide6.QtWidgets import QMessageBox
        box = QMessageBox()
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Giấy phép không còn hiệu lực")
        box.setText(message)
        box.setInformativeText(
            "Các tính năng Premium đã được tắt. Buổi đang chạy vẫn tiếp tục, "
            "nhưng lần mở app sau sẽ cần kích hoạt lại."
        )
        box.exec()
    except Exception as e:
        log.warning("Không hiện được cảnh báo license: %s", e)


# Khoảng cách giữa hai lần check-in trong cùng một phiên. Máy hát thường mở
# liên tục nhiều ngày; nếu chỉ check-in lúc khởi động thì lệnh thu hồi phải chờ
# tới lần khởi động sau mới tới nơi.
_LICENSE_RECHECK_SECONDS = 6 * 3600
_LICENSE_LOST_STATUSES = frozenset({"revoked", "expired", "not_activated", "invalid"})


def _background_maintenance(notifier=None):
    """
    Nền (daemon): flush crash queue, rồi lặp check-in license + cloud sync.

    Vòng lặp ngủ theo lát nhỏ để process thoát dứt điểm khi user đóng app.
    """
    import time as _t

    try:
        from core.crash_reporter import flush_queue
        flush_queue()
    except Exception as e:
        log.debug("crash flush skipped: %s", e)

    while True:
        try:
            from core.licensing import client as _lic
            if _lic.has_online_license():
                result = _lic.verify_online()
                status = result.get("status")
                if status in _LICENSE_LOST_STATUSES:
                    # verify_online đã xoá cache → Premium tắt ngay lập tức.
                    log.warning("License không còn hiệu lực (%s)", status)
                    if notifier is not None:
                        notifier.license_lost.emit(
                            result.get("error")
                            or "Giấy phép của máy này đã bị thu hồi hoặc hết hạn."
                        )
        except Exception as e:
            log.debug("license re-verify skipped: %s", e)

        # Cloud Sync nền (Premium). Fail-soft: lỗi mạng/không cấu hình → bỏ qua.
        try:
            from core import entitlements
            if entitlements.is_premium():
                from core.licensing import sync as _sync
                res = _sync.sync_all()
                log.info("Cloud sync nền: %s", res.get("results", res))
        except Exception as e:
            log.debug("cloud sync skipped: %s", e)

        slept = 0
        while slept < _LICENSE_RECHECK_SECONDS:
            _t.sleep(30)
            slept += 30


def main():
    """
    App lifecycle loop — avoid recursion to prevent stack accumulation
    when the user reactivates or saves setup multiple times.
    """
    # Dọn cache license trước cổng kiểm tra: máy nâng cấp từ bản cũ còn giữ
    # token định dạng cũ, đổi lấy token mới ở đây để không bị đá ra vô cớ.
    try:
        from core.licensing import client as _lic
        _lic.startup_reconcile()
    except Exception as e:
        log.debug("startup reconcile skipped: %s", e)

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
            # Tạo dashboard TRƯỚC (đảm bảo QApplication tồn tại) rồi mới tạo
            # notifier + thread check update — signal queued về main thread.
            dashboard = frontend_qt.MainDashboard(settings)
            notifier = _UpdateNotifier()
            notifier.update_available.connect(_show_update_dialog)
            threading.Thread(
                target=_schedule_update_check, args=(notifier,), daemon=True
            ).start()
            # Nền: gửi lại crash report tồn đọng + check-in license định kỳ.
            lic_notifier = _LicenseNotifier()
            lic_notifier.license_lost.connect(_show_license_lost_dialog)
            threading.Thread(
                target=_background_maintenance, args=(lic_notifier,), daemon=True
            ).start()
            dashboard.mainloop()
            log.info("Dashboard closed, exiting")
            # Chờ bg-shutdown (closeEvent) xong với timeout ngắn — os._exit(0)
            # trong finally sẽ kill daemon thread giữa chừng, orphan ffmpeg/yt-dlp.
            t = getattr(dashboard, "_bg_shutdown_thread", None)
            if t is not None and t.is_alive():
                t.join(timeout=4.0)
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
