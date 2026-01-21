import backend
import frontend

def main():
    """
    Hàm chính khởi chạy ứng dụng
    - Kiểm tra activation trước khi vào app
    - Cấu hình (settings.json) được giữ nguyên khi kích hoạt lại
    """
    # 1. Kiểm tra activation trước
    # LƯU Ý: Khi kích hoạt lại, chỉ cập nhật activation.json
    # Cấu hình (settings.json) và dữ liệu khác vẫn được giữ nguyên
    if backend.ActivationManager.needs_activation():
        is_expired = backend.ActivationManager.is_activated() and backend.ActivationManager.is_expired()
        activation_dialog = frontend.ActivationDialog(callback=main, is_expired=is_expired)
        activation_dialog.mainloop()
        return  # Sau khi kích hoạt, callback sẽ gọi lại main() để tiếp tục
    
    # 2. Load cấu hình (settings.json) - không bị ảnh hưởng bởi activation
    settings = backend.ConfigManager.load()
    
    # 3. Điều hướng
    if settings:
        app = frontend.MainDashboard(settings)
        app.mainloop()
    else:
        app = frontend.SetupView(callback=main)
        app.mainloop()

if __name__ == "__main__":
    main()