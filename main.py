import sys
from PySide6.QtWidgets import QApplication
import backend
import frontend_qt as frontend

def main():
    """
    Hàm chính khởi chạy ứng dụng (PySide6)
    - Kiểm tra activation trước khi vào app
    - Cấu hình (settings.json) được giữ nguyên khi kích hoạt lại
    """
    # Đảm bảo QApplication tồn tại
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    # 1. Kiểm tra activation trước
    if backend.ActivationManager.needs_activation():
        is_expired = backend.ActivationManager.is_activated() and backend.ActivationManager.is_expired()
        activation_dialog = frontend.ActivationDialog(callback=main, is_expired=is_expired)
        activation_dialog.mainloop()
        return

    # 2. Load cấu hình (settings.json)
    settings = backend.ConfigManager.load()

    # 3. Điều hướng
    if settings:
        window = frontend.MainDashboard(settings)
        window.show()
        sys.exit(app.exec())
    else:
        setup = frontend.SetupView(callback=main)
        setup.mainloop()

if __name__ == "__main__":
    main()