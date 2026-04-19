import os
import sys
import ctypes
import atexit
import shutil

# ── PyInstaller _MEI cleanup ──────────────────────────
# Khi build --onefile, PyInstaller giải nén vào thư mục tạm _MEIxxxxx.
# Nếu daemon threads/subprocesses vẫn giữ file handles khi thoát,
# Windows không thể xóa thư mục → báo lỗi "Failed to remove temporary directory".

def _cleanup_mei():
    """Xóa thư mục tạm _MEI khi app thoát (chỉ chạy trong PyInstaller frozen mode)."""
    if not getattr(sys, 'frozen', False):
        return
    mei_dir = getattr(sys, '_MEIPASS', None)
    if mei_dir and os.path.isdir(mei_dir):
        shutil.rmtree(mei_dir, ignore_errors=True)

# atexit là safety net cho nhánh exit bất thường; đường thoát chính gọi _cleanup_mei() thủ công
# vì os._exit(0) bỏ qua mọi atexit handler.
atexit.register(_cleanup_mei)

# Set DPI awareness TRƯỚC khi import Qt (tránh "SetProcessDpiAwarenessContext() failed" trong PyInstaller)
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_ssize_t(-4))  # PER_MONITOR_AWARE_V2
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Fallback cho Windows 8.1
    except Exception:
        pass

os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
os.environ["QT_OPENGL"] = "angle"  # ANGLE ổn định hơn native OpenGL trên Windows

import backend
import frontend_qt


def _license_or_trial_expired():
    am = backend.ActivationManager
    return (am.is_activated() and am.is_expired()) or am.is_trial_expired()


def main():
    """
    Vòng đời app — dùng loop thay vì đệ quy callback để tránh tích lũy stack frames
    khi user reactivate / lưu setup nhiều lần.
    """
    while True:
        # 1. Activation / trial gate
        if backend.ActivationManager.needs_activation():
            dialog = frontend_qt.ActivationDialog(is_expired=_license_or_trial_expired())
            dialog.mainloop()
            if not dialog.activated:
                return  # User đóng dialog mà chưa kích hoạt → thoát
            continue

        if backend.ActivationManager.is_trial_active():
            days = backend.ActivationManager.get_trial_days_remaining()
            print(f"🎁 [TRIAL] Đang dùng thử — Còn {days:.1f} ngày")

        # 2. Settings
        settings = backend.ConfigManager.load_settings()

        # 3. Điều hướng
        if settings:
            frontend_qt.MainDashboard(settings).mainloop()
            return  # Dashboard đóng = thoát app
        else:
            setup = frontend_qt.SetupView()
            setup.mainloop()
            if not setup._saved:
                return  # User bỏ qua setup → thoát


if __name__ == "__main__":
    try:
        main()
    finally:
        # Cleanup thủ công vì os._exit bypass atexit.
        # os._exit cần thiết để buộc OS thu hồi mọi file handle
        # do daemon threads (MIDI, media monitor, memory guard) còn giữ.
        _cleanup_mei()
        os._exit(0)
