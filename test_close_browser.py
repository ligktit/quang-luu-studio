import time
import psutil

try:
    import win32gui
    import win32con
except ImportError:
    win32gui = None

print("=== BẮT ĐẦU TEST ĐÓNG YOUTUBE ===")

# Tầng 1: Dùng psutil tiêu diệt PWA
print("[1] Đang quét các process PWA bằng psutil...")
try:
    for proc in psutil.process_iter(['name', 'cmdline']):
        name = (proc.info.get('name') or '').lower()
        cmdline = proc.info.get('cmdline') or []
        if name in ('chrome.exe', 'msedge.exe', 'brave.exe', 'coccoc.exe'):
            cmd_str = ' '.join(cmdline).lower()
            if 'youtube.com' in cmd_str and ('--app=' in cmd_str or '--app-id=' in cmd_str):
                try:
                    proc.terminate()
                    print(f" -> Đã terminate PWA: {name} (PID: {proc.pid})")
                except Exception as e:
                    print(f" -> Lỗi terminate {name} (PID: {proc.pid}): {e}")
except Exception as e:
    print(f"Lỗi quét psutil: {e}")

# Tầng 2: Dùng win32gui
if win32gui:
    print("\n[2] Đang quét các cửa sổ YouTube bằng win32gui...")
    yt_hwnds = []

    def _enum_cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd).lower()
        if "youtube" in title or "youtu.be" in title or "yt music" in title:
            yt_hwnds.append((hwnd, title))
        return True

    try:
        win32gui.EnumWindows(_enum_cb, None)
    except Exception as e:
        print(f"Lỗi EnumWindows: {e}")

    if not yt_hwnds:
        print(" -> Không tìm thấy cửa sổ YouTube nào.")
    else:
        for hwnd, title in yt_hwnds:
            print(f" -> Đã phát hiện cửa sổ: '{title}' (HWND: {hwnd})")
            try:
                win32gui.SendMessageTimeout(hwnd, win32con.WM_SYSCOMMAND, win32con.SC_CLOSE, 0, win32con.SMTO_ABORTIFHUNG, 500)
                win32gui.SendMessageTimeout(hwnd, win32con.WM_CLOSE, 0, 0, win32con.SMTO_ABORTIFHUNG, 500)
                print("    -> Đã gửi lệnh SC_CLOSE và WM_CLOSE")
            except Exception as e:
                print(f"    -> Lỗi gửi lệnh: {e}")
else:
    print("\n[2] win32gui không được cài đặt, bỏ qua phần quét cửa sổ.")

print("\n=== HOÀN TẤT ===")
