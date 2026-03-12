import os
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
    settings = backend.ConfigManager.load()
    
    # 3. Điều hướng
    if settings:
        app = frontend_qt.MainDashboard(settings)
        app.mainloop()
    else:
        app = frontend_qt.SetupView(callback=main)
        app.mainloop()

if __name__ == "__main__":
    main()