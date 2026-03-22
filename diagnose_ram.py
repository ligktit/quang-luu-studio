"""
Quang Lưu Studio — Chẩn đoán RAM leak
Chạy: python diagnose_ram.py

Mở Studio One trong khi script đang chạy để thấy RSS thay đổi.
Script sẽ in RSS mỗi 2 giây trong 60 giây.
"""
import os
import gc
import time
import psutil
import threading

process = psutil.Process(os.getpid())

def get_rss_mb():
    return process.memory_info().rss / (1024 * 1024)

print("=" * 70)
print("🔍 CHẨN ĐOÁN RAM LEAK — Quang Lưu Studio")
print("=" * 70)
print(f"PID: {os.getpid()}")
print(f"RSS ban đầu: {get_rss_mb():.1f} MB")
print()

# ── Test 1: Chỉ WindowsMediaMonitor (100ms poll) ──
print("── Test 1: WindowsMediaMonitor (10 giây) ──")
print("   Nếu RAM tăng ở đây → WinRT COM leak!")
from core.media_monitor import WindowsMediaMonitor
rss_before = get_rss_mb()
monitor = WindowsMediaMonitor()
for i in range(5):
    time.sleep(2)
    rss_now = get_rss_mb()
    delta = rss_now - rss_before
    print(f"   t={i*2+2:2d}s: RSS={rss_now:.1f}MB (Δ={delta:+.1f}MB) | "
          f"playing={monitor.is_playing} title='{monitor.current_title[:30] if monitor.current_title else ''}'")
monitor.stop()
gc.collect()
rss_after_stop = get_rss_mb()
print(f"   → Sau stop+GC: RSS={rss_after_stop:.1f}MB (net Δ={rss_after_stop - rss_before:+.1f}MB)")
print()

# ── Test 2: Chỉ EnumWindows (YouTube watcher Tier 1) ──
print("── Test 2: EnumWindows polling (10 giây, mỗi 1.5s) ──")
print("   Nếu RAM tăng ở đây → ctypes/EnumWindows leak!")
import ctypes
import ctypes.wintypes
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
rss_before = get_rss_mb()
for i in range(7):
    windows = []
    def enum_cb(hwnd, _):
        if ctypes.windll.user32.IsWindowVisible(hwnd):
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                windows.append((hwnd, buf.value))
        return True
    ctypes.windll.user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    del windows
    time.sleep(1.5)
    if i % 2 == 1:
        rss_now = get_rss_mb()
        print(f"   t={int(i*1.5):2d}s: RSS={rss_now:.1f}MB (Δ={rss_now - rss_before:+.1f}MB)")
gc.collect()
rss_after = get_rss_mb()
print(f"   → Sau GC: RSS={rss_after:.1f}MB (net Δ={rss_after - rss_before:+.1f}MB)")
print()

# ── Test 3: UIAutomation (YouTube watcher Tier 2) ──
print("── Test 3: UIAutomation scan (10 giây, mỗi 2s) ──")
print("   Nếu RAM tăng ở đây → UIAutomation COM leak!")
try:
    import uiautomation as auto
    rss_before = get_rss_mb()
    for i in range(5):
        # Giả lập logic detect_youtube_url_from_browser
        windows = []
        def enum_cb2(hwnd, _):
            if ctypes.windll.user32.IsWindowVisible(hwnd):
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                    windows.append((hwnd, buf.value))
            return True
        ctypes.windll.user32.EnumWindows(WNDENUMPROC(enum_cb2), 0)
        
        browser_keywords = ["Google Chrome", "Microsoft Edge", "Mozilla Firefox", "Brave", "Opera", "Vivaldi", "Edge"]
        for hwnd, title in windows:
            for kw in browser_keywords:
                if kw.lower() in title.lower():
                    control = None
                    children = None
                    try:
                        control = auto.ControlFromHandle(hwnd)
                        if control:
                            children = control.GetChildren()
                            for child in children:
                                try:
                                    edit = child.EditControl(searchDepth=8)
                                    if edit and edit.Exists(0.1):
                                        try:
                                            pattern = edit.GetValuePattern()
                                            if pattern:
                                                _ = pattern.Value
                                        except Exception:
                                            pass
                                except Exception:
                                    continue
                    except Exception:
                        pass
                    finally:
                        del control, children
                    break
        del windows
        time.sleep(2)
        rss_now = get_rss_mb()
        delta = rss_now - rss_before
        print(f"   t={i*2+2:2d}s: RSS={rss_now:.1f}MB (Δ={delta:+.1f}MB)")
    gc.collect()
    rss_after = get_rss_mb()
    print(f"   → Sau GC: RSS={rss_after:.1f}MB (net Δ={rss_after - rss_before:+.1f}MB)")
except ImportError:
    print("   ⚠️ uiautomation không khả dụng")
print()

# ── Test 4: Full SystemEngine init (30 giây) ──
print("── Test 4: Full SystemEngine (20 giây) ──")
print("   Nếu RAM tăng ở đây nhưng KHÔNG ở Test 1-3 → vấn đề ở engine init!")
rss_before = get_rss_mb()
from core.engine import SystemEngine
engine = SystemEngine()
for i in range(10):
    time.sleep(2)
    rss_now = get_rss_mb()
    delta = rss_now - rss_before
    print(f"   t={i*2+2:2d}s: RSS={rss_now:.1f}MB (Δ={delta:+.1f}MB)")
print()

print("=" * 70)
print("🏁 KẾT THÚC CHẨN ĐOÁN")
print(f"   RSS cuối cùng: {get_rss_mb():.1f}MB")
print("=" * 70)
