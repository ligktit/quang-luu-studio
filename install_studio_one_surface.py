"""
Install QuangLuuMIDI Control Surface vào Studio One 7.
"""

import os
import shutil
import sys

# Đường dẫn nguồn
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_DIR = os.path.join(SCRIPT_DIR, "studio_one")

# Đường dẫn đích trong Studio One
APPDATA = os.environ.get("APPDATA", "")
STUDIO_ONE_VERSIONS = [
    os.path.join(APPDATA, "PreSonus", "Studio One 7", "User Devices"),
    os.path.join(APPDATA, "PreSonus", "Studio One 6", "User Devices"),
    os.path.join(APPDATA, "PreSonus", "Studio One 5", "User Devices"),
]

def find_studio_one_dir():
    """Tìm thư mục Studio One đã cài đặt."""
    for path in STUDIO_ONE_VERSIONS:
        parent = os.path.dirname(path)
        if os.path.exists(parent):
            return path
    return None

def install():
    """Copy các file cấu hình vào Studio One."""
    user_devices_dir = find_studio_one_dir()
    if not user_devices_dir:
        print("❌ Không tìm thấy Studio One!")
        return False

    # Tạo thư mục đích (Cấu trúc mới: QuangLuuStudio/QuangLuuMIDI)
    dest_dir = os.path.join(user_devices_dir, "QuangLuuStudio", "QuangLuuMIDI")
    os.makedirs(dest_dir, exist_ok=True)

    print(f"📁 Đang cài đặt vào: {dest_dir}")

    # Copy files
    if not os.path.exists(SOURCE_DIR):
        print(f"❌ Không tìm thấy thư mục nguồn: {SOURCE_DIR}")
        return False

    for filename in os.listdir(SOURCE_DIR):
        src_path = os.path.join(SOURCE_DIR, filename)
        if os.path.isfile(src_path):
            shutil.copy2(src_path, os.path.join(dest_dir, filename))
            print(f"   - Đã copy: {filename}")

    print("\n" + "=" * 60)
    print("✅ Đã cài đặt QuangLuuMIDI Control Surface thành công!")
    print("=" * 60)
    print("\n🎵 Bước tiếp theo trong Studio One:")
    print("   1. Mở Studio One → Options → External Devices")
    print("   2. Click 'Add...'")
    print("   3. Chọn 'QuangLuuMIDI' trong danh sách")
    print("   4. Chọn Receive From: QuangLuuMIDI (loopMIDI port)")
    print("   5. Click OK")
    return True

if __name__ == "__main__":
    if install():
        print("\nSẵn sàng! Hãy khởi động lại Studio One.")
    else:
        sys.exit(1)
    
    if sys.stdin.isatty():
        input("\nNhấn Enter để đóng...")
