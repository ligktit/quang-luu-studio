import os
import sys
import ctypes
import atexit
import shutil

# ── PyInstaller _MEI cleanup ──────────────────────────
# Khi build --onefile, PyInstaller giải nén vào thư mục tạm _MEIxxxxx.
# Nếu daemon threads/subprocesses vẫn giữ file handles khi thoát,
# Windows không thể xóa thư mục → báo lỗi "Failed to remove temporary directory".
# Giải pháp: đăng ký atexit handler để force cleanup.

def _cleanup_mei():
    """Xóa thư mục tạm _MEI khi app thoát (chỉ chạy trong PyInstaller frozen mode)."""
    if not getattr(sys, 'frozen', False):
        return
    mei_dir = getattr(sys, '_MEIPASS', None)
    if mei_dir and os.path.isdir(mei_dir):
        try:
            shutil.rmtree(mei_dir, ignore_errors=True)
        except Exception:
            pass

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
os.environ["QT_OPENGL"] = "angle"                # Dùng ANGLE thay vì native OpenGL — tương thích tốt hơn
os.environ["QT_QUICK_BACKEND"] = "software"       # Fallback software rendering cho QtQuick
os.environ["LIBGL_ALWAYS_SOFTWARE"] = "1"          # Force Mesa software rasterizer nếu cần

import backend
import frontend_qt

def main():
    """
    Hàm chính khởi chạy ứng dụng
    - Kiểm tra activation trước khi vào app
    - Cấu hình (settings.json) được giữ nguyên khi kích hoạt lại
    """
    # 1. Kiểm tra activation / trial trước
    # LƯU Ý: Khi kích hoạt lại, chỉ cập nhật activation.json
    # Cấu hình (settings.json) và dữ liệu khác vẫn được giữ nguyên
    if backend.ActivationManager.needs_activation():
        is_expired = (
            (backend.ActivationManager.is_activated() and backend.ActivationManager.is_expired())
            or backend.ActivationManager.is_trial_expired()
        )
        activation_dialog = frontend_qt.ActivationDialog(callback=main, is_expired=is_expired)
        activation_dialog.mainloop()
        return  # Sau khi kích hoạt, callback sẽ gọi lại main() để tiếp tục
    
    # Hiển thị trial info nếu đang dùng thử
    if backend.ActivationManager.is_trial_active():
        days = backend.ActivationManager.get_trial_days_remaining()
        print(f"🎁 [TRIAL] Đang dùng thử — Còn {days:.1f} ngày")
    
    # 2. Load cấu hình (settings.json) - không bị ảnh hưởng bởi activation
    settings = backend.ConfigManager.load_settings()
    
    # 3. Điều hướng
    if settings:
        app = frontend_qt.MainDashboard(settings)
        app.mainloop()
    else:
        app = frontend_qt.SetupView(callback=main)
        app.mainloop()

if __name__ == "__main__":
    main()
    # Force terminate process sau khi Qt event loop kết thúc.
    # Daemon threads (MIDI, media monitor, memory guard, etc.) vẫn có thể
    # đang chạy → giữ lock trên files trong _MEI → os._exit() buộc OS
    # giải phóng tất cả handles ngay lập tức.
    os._exit(0)