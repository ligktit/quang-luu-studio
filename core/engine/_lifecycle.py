"""App lifecycle: launch, kill Studio One, hotkeys, YouTube window management."""
import os
import re
import time
import threading
import subprocess

import psutil
import pyautogui

try:
    import win32gui
    import win32con
    import win32process
except ImportError:
    pass

from core.config import CDP_DEBUG_PORT


class _LifecycleMixin:
    STUDIO_ONE_EXTENSIONS = (
        ".song", ".songversion", ".soundset", ".instrument",
        ".multiinstrument", ".pedalboard", ".channel", ".macro", ".fxchain",
    )

    def send_hotkey(self, keys):
        def run():
            hwnd = None
            def cb(h, _):
                if win32gui.IsWindowVisible(h) and "Studio One" in win32gui.GetWindowText(h):
                    nonlocal hwnd; hwnd = h
            win32gui.EnumWindows(cb, None)
            if hwnd:
                try:
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(hwnd)
                    if len(keys) == 1:
                        pyautogui.press(keys[0])
                    else:
                        pyautogui.hotkey(*keys)
                except Exception:
                    pass
        threading.Thread(target=run, daemon=True).start()

    @staticmethod
    def _parse_browser_path(raw_path):
        import shlex
        s = raw_path.replace('\\', '/')
        try:
            parts = shlex.split(s)
            if parts and os.path.exists(parts[0]):
                return parts
        except ValueError:
            pass

        m = re.match(r'^(.+?\.exe)\b', s, re.IGNORECASE)
        if m:
            exe_path = m.group(1).strip().strip('"').strip("'")
            remainder = s[m.end():].strip()
            flags = []
            for token in re.split(r'\s+', remainder):
                token = token.strip('"').strip("'")
                if not token:
                    continue
                if token.startswith('http://') or token.startswith('https://'):
                    continue
                if token.startswith('-'):
                    flags.append(token)
                elif token.startswith('=') and flags:
                    flags[-1] += token
            return [exe_path] + flags
        return [s.strip().strip('"')]

    def launch_app(self, path, is_web=False):
        if not path:
            return

        if is_web:
            def _launch_web():
                args     = self._parse_browser_path(path)
                exe_path = args[0]
                if os.path.exists(exe_path):
                    is_pwa = any("--app-id" in a for a in args)
                    if not any("remote-debugging-port" in a for a in args):
                        args.insert(1, f"--remote-debugging-port={CDP_DEBUG_PORT}")
                    if not any("remote-allow-origins" in a for a in args):
                        args.insert(1, "--remote-allow-origins=*")
                    if not is_pwa:
                        args.append("youtube.com")
                    print(f"[AUTO LAUNCH] Mở {'PWA' if is_pwa else 'YouTube'} với CDP")
                    subprocess.Popen(args)
            threading.Thread(target=_launch_web, daemon=True).start()
        else:
            if not os.path.exists(path):
                return
            if path.lower().endswith(self.STUDIO_ONE_EXTENSIONS):
                try:
                    os.startfile(path)
                except Exception:
                    pass
            else:
                running = any("Studio One" in p.info['name'] for p in psutil.process_iter(['name']))
                if not running:
                    threading.Thread(target=lambda: subprocess.Popen(path), daemon=True).start()

    def kill_studio_one_gracefully(self, timeout_sec: int = 15):
        try:
            import win32gui
            import win32con
        except ImportError:
            self._force_kill_studio_one()
            return

        hwnd_list = []

        def _enum_main(hwnd, _):
            if win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd):
                if "Studio One" in win32gui.GetWindowText(hwnd):
                    hwnd_list.append(hwnd)
            return True

        try:
            win32gui.EnumWindows(_enum_main, None)
        except Exception:
            pass

        if not hwnd_list:
            self._force_kill_studio_one()
            return

        for hwnd in hwnd_list:
            try:
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception:
                pass
        print("[STUDIO ONE] Đã gửi WM_CLOSE, chờ dialog Save...")

        SAVE_DIALOG_KEYWORDS = ["save", "lưu", "unsaved", "changes", "studio one"]

        def _is_save_dialog(title):
            t = title.lower()
            return any(kw in t for kw in SAVE_DIALOG_KEYWORDS)

        enter_sent   = False
        poll_deadline = time.time() + 6

        while time.time() < poll_deadline and not enter_sent:
            time.sleep(0.25)
            dialog_hwnds = []

            def _enum_dialogs(hwnd, _):
                if win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title and _is_save_dialog(title) and hwnd not in hwnd_list:
                        dialog_hwnds.append((hwnd, title))
                return True

            try:
                win32gui.EnumWindows(_enum_dialogs, None)
            except Exception:
                pass

            if dialog_hwnds:
                dlg_hwnd, dlg_title = dialog_hwnds[0]
                print(f"[STUDIO ONE] Phát hiện dialog: '{dlg_title}' -> nhấn Enter để lưu")
                try:
                    win32gui.ShowWindow(dlg_hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(dlg_hwnd)
                    time.sleep(0.15)
                    pyautogui.press('enter')
                    enter_sent = True
                    print("[STUDIO ONE] Đã nhấn Enter xác nhận lưu")
                except Exception as e:
                    print(f"[STUDIO ONE] Không thể nhấn Enter: {e}")
                    try:
                        VK_RETURN = 0x0D
                        win32gui.PostMessage(dlg_hwnd, win32con.WM_KEYDOWN, VK_RETURN, 0)
                        win32gui.PostMessage(dlg_hwnd, win32con.WM_KEYUP,   VK_RETURN, 0)
                        enter_sent = True
                        print("[STUDIO ONE] Đã gửi WM_KEYDOWN Enter")
                    except Exception as e2:
                        print(f"[STUDIO ONE] WM_KEYDOWN cũng thất bại: {e2}")

        if not enter_sent:
            print("[STUDIO ONE] Không thấy dialog Save")

        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            still_running = any(
                "Studio One" in (p.info.get('name') or '')
                for p in psutil.process_iter(['name'])
            )
            if not still_running:
                print("[STUDIO ONE] Đã thoát hoàn toàn")
                return
            time.sleep(0.4)

        print("[STUDIO ONE] Timeout, chuyển sang force kill...")
        self._force_kill_studio_one()

    def _force_kill_studio_one(self):
        NAMES = [
            "Studio One.exe", "Studio One 7.exe", "Studio One 6.exe",
            "Studio One 5.exe", "Studio One Prime.exe",
        ]
        killed = False
        for name in NAMES:
            if os.system(f'taskkill /F /IM "{name}" /T >nul 2>&1') == 0:
                killed = True
        if killed:
            print("[STUDIO ONE] Force kill hoàn tất")
        else:
            print("[STUDIO ONE] Không tìm thấy process để kill")

    def kill_app(self):
        """Deprecated alias."""
        self._force_kill_studio_one()

    def close_youtube_windows(self):
        try:
            import win32gui
            import win32con
        except ImportError:
            return

        yt_hwnds = []

        def _enum_cb(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd).lower()
            if "youtube" in title or "youtu.be" in title:
                yt_hwnds.append(hwnd)
            return True

        try:
            win32gui.EnumWindows(_enum_cb, None)
        except Exception:
            return

        if not yt_hwnds:
            print("[YOUTUBE] Không tìm thấy cửa sổ YouTube để đóng")
            return

        for hwnd in yt_hwnds:
            try:
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception:
                pass
        print(f"[YOUTUBE] Đã gửi WM_CLOSE cho {len(yt_hwnds)} cửa sổ YouTube")
