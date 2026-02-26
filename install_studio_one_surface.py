"""
Install QuangLuuMIDI Control Surface vào Studio One 7.

Script tự động copy file .surface.xml vào thư mục User Devices 
của Studio One 7 để đăng ký QuangLuuMIDI như một control surface.

Cách dùng:
    python install_studio_one_surface.py
"""

import os
import shutil
import sys

# Đường dẫn nguồn
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_FILE = os.path.join(SCRIPT_DIR, "studio_one", "QuangLuuMIDI.surface.xml")

# Đường dẫn đích trong Studio One 7
APPDATA = os.environ.get("APPDATA", "")
STUDIO_ONE_VERSIONS = [
    os.path.join(APPDATA, "PreSonus", "Studio One 7", "User Devices"),
    os.path.join(APPDATA, "PreSonus", "Studio One 6", "User Devices"),
    os.path.join(APPDATA, "PreSonus", "Studio One 5", "User Devices"),
]


def find_studio_one_dir():
    """Tìm thư mục Studio One đã cài đặt."""
    for path in STUDIO_ONE_VERSIONS:
        parent = os.path.dirname(path)  # Studio One X folder
        if os.path.exists(parent):
            return path
    return None


def install():
    """Copy file surface.xml vào thư mục User Devices của Studio One."""
    
    # Kiểm tra file nguồn
    if not os.path.exists(SOURCE_FILE):
        print(f"❌ Không tìm thấy file: {SOURCE_FILE}")
        print("   Đảm bảo file QuangLuuMIDI.surface.xml nằm trong thư mục studio_one/")
        return False
    
    # Tìm thư mục Studio One
    user_devices_dir = find_studio_one_dir()
    if not user_devices_dir:
        print("❌ Không tìm thấy Studio One!")
        print("   Đường dẫn đã kiểm tra:")
        for path in STUDIO_ONE_VERSIONS:
            print(f"   - {os.path.dirname(path)}")
        print("\n💡 Bạn có thể copy thủ công:")
        print(f"   Từ: {SOURCE_FILE}")
        print(f"   Đến: %APPDATA%\\PreSonus\\Studio One 7\\User Devices\\QuangLuuMIDI\\")
        return False
    
    # Tạo thư mục đích
    dest_dir = os.path.join(user_devices_dir, "QuangLuuMIDI")
    os.makedirs(dest_dir, exist_ok=True)
    
    # Copy file
    dest_file = os.path.join(dest_dir, "QuangLuuMIDI.surface.xml")
    shutil.copy2(SOURCE_FILE, dest_file)
    
    print("=" * 60)
    print("✅ Đã cài đặt QuangLuuMIDI Control Surface thành công!")
    print("=" * 60)
    print(f"\n📁 File đã copy vào:")
    print(f"   {dest_file}")
    print(f"\n🎵 Bước tiếp theo trong Studio One 7:")
    print(f"   1. Mở Studio One → Options → External Devices")
    print(f"   2. Click 'Add...'")
    print(f"   3. Tìm 'QuangLuuMIDI' trong danh sách (hoặc chọn 'New Control Surface')")
    print(f"   4. Chọn Receive From: QuangLuuMIDI (loopMIDI port)")
    print(f"   5. Click OK")
    print(f"\n🔗 Dùng Control Link để gán controls:")
    print(f"   - Mở Control Link panel (trên thanh menu)")
    print(f"   - Bật MIDI Learn")
    print(f"   - Di chuyển slider/nhấn nút trên app Quang Lưu Studio")
    print(f"   - Click vào parameter trong Studio One muốn điều khiển")
    print()
    
    return True


if __name__ == "__main__":
    success = install()
    
    if not success:
        sys.exit(1)
    
    input("Nhấn Enter để đóng...")
