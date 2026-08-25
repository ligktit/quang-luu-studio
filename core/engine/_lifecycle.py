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
                    proc = subprocess.Popen(args)
                    self._browser_process = proc
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

    def close_studio_one_safely(self, timeout_sec: float = 30.0, save: bool = True,
                                force_kill: bool = False, on_progress=None,
                                should_abort=None) -> dict:
        """Lưu bài rồi đóng Studio One **sạch**, không dùng taskkill.

        Vì sao phải làm khác cách cũ: taskkill để lại cờ "thoát bất thường" trong
        Studio One → lần mở sau nó đòi phục hồi phiên và không vào thẳng file đã
        lưu được. Muốn hết cảnh báo đó thì Studio One phải tự thoát.

        Trình tự:
          1. Ctrl+S trước — bài đã lưu thì lúc đóng Studio One không hỏi gì cả,
             tức là không còn hộp thoại nào để đoán mò.
          2. WM_CLOSE tới cửa sổ chính.
          3. Còn hộp thoại nào bật lên thì giành foreground thật (AttachThreadInput)
             rồi Enter — nút mặc định của Studio One là "Save".
          4. Chờ process biến mất.

        Hết giờ thì **không** giết process (trừ khi force_kill=True): để Studio One
        chạy tiếp còn an toàn hơn là giết nó giữa lúc đang ghi file.

        Trả dict {"status": ..., "saved": bool} với status là một trong
        "closed" | "not_running" | "timeout" | "force_killed" | "aborted".
        """
        from core import so_windows

        def _p(msg):
            print(f"[STUDIO ONE] {msg}")
            if on_progress:
                try:
                    on_progress(msg)
                except Exception:
                    pass

        def _aborted():
            try:
                return bool(should_abort and should_abort())
            except Exception:
                return False

        if not so_windows.studio_one_pids():
            return {"status": "not_running", "saved": False}

        mods = so_windows.win32_modules()
        if not mods:
            _p("Thiếu pywin32 — không đóng an toàn được")
            if force_kill:
                self._force_kill_studio_one()
                return {"status": "force_killed", "saved": False}
            return {"status": "timeout", "saved": False}
        win32gui, win32con, _ = mods

        mains = so_windows.main_windows()
        saved = False

        if save and mains:
            saved = self._studio_one_save(mains[0], on_progress=_p)
        elif save:
            _p("Không thấy cửa sổ chính — bỏ qua bước lưu")

        if _aborted():
            return {"status": "aborted", "saved": saved}

        _p("Đang đóng Studio One...")
        # Chụp lại toàn bộ cửa sổ TRƯỚC khi xin đóng: cái nào mọc lên sau mới là
        # hộp thoại hỏi lưu. Lọc theo cách này thì cửa sổ plugin đang mở sẵn không
        # bị nhận nhầm rồi ăn Enter oan.
        known = set(so_windows.all_windows())
        for hwnd in (mains or known):
            try:
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception:
                pass

        deadline = time.time() + timeout_sec
        last_enter = 0.0
        enter_count = 0

        while time.time() < deadline:
            if _aborted():
                return {"status": "aborted", "saved": saved}
            if not so_windows.studio_one_pids():
                _p("Studio One đã thoát sạch")
                return {"status": "closed", "saved": saved}

            # Hộp thoại = cửa sổ của Studio One đang hiện và mới mọc lên sau WM_CLOSE.
            if time.time() - last_enter > 1.2 and enter_count < 5:
                for hwnd in so_windows.all_windows():
                    if hwnd in known:
                        continue
                    try:
                        if not win32gui.IsWindowVisible(hwnd):
                            continue
                        title = win32gui.GetWindowText(hwnd) or "(không tên)"
                    except Exception:
                        continue
                    _p(f"Xác nhận hộp thoại: {title}")
                    if so_windows.force_foreground(hwnd):
                        time.sleep(0.2)
                        try:
                            pyautogui.press("enter")
                        except Exception as e:
                            print(f"[STUDIO ONE] Không gửi được Enter: {e}")
                    else:
                        # Không giành được foreground — bắn phím thẳng vào cửa sổ.
                        VK_RETURN = 0x0D
                        try:
                            win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, VK_RETURN, 0)
                            win32gui.PostMessage(hwnd, win32con.WM_KEYUP, VK_RETURN, 0)
                        except Exception:
                            pass
                    last_enter = time.time()
                    enter_count += 1
                    break

            time.sleep(0.4)

        if force_kill:
            _p("Quá hạn chờ — buộc phải tắt cứng (lần sau Studio One sẽ đòi phục hồi)")
            self._force_kill_studio_one()
            return {"status": "force_killed", "saved": saved}

        _p("Studio One chưa đóng xong — để nguyên cho an toàn, vui lòng đóng tay")
        return {"status": "timeout", "saved": saved}

    def _studio_one_save(self, hwnd, on_progress=None) -> bool:
        """Giành foreground rồi gửi Ctrl+S. Trả True nếu đã gửi được phím lưu."""
        from core import so_windows

        def _p(msg):
            if on_progress:
                on_progress(msg)
            else:
                print(f"[STUDIO ONE] {msg}")

        mods = so_windows.win32_modules()
        if not mods:
            return False
        win32gui, _, _ = mods

        # Cửa sổ đang bị ẩn (chế độ khách) thì phải hiện lại — phím chỉ tới được
        # cửa sổ đang hiển thị và giữ focus.
        try:
            if not win32gui.IsWindowVisible(hwnd):
                win32gui.ShowWindow(hwnd, so_windows.SW_SHOW)
        except Exception:
            pass

        _p("Đang lưu bài trong Studio One...")
        if not so_windows.force_foreground(hwnd):
            _p("Không giành được focus — bỏ qua bước lưu")
            return False

        before = set(so_windows.all_windows())
        time.sleep(0.25)
        try:
            pyautogui.hotkey("ctrl", "s")
        except Exception as e:
            _p(f"Không gửi được Ctrl+S: {e}")
            return False

        # Chờ Studio One ghi xong. Nếu bài chưa từng lưu, nó bật hộp thoại đặt tên
        # — Enter để nhận mặc định, còn hơn kẹt lại rồi rơi vào tắt cứng.
        # Im lặng 1.5s liên tục = coi như đã ghi xong; tối đa 2 hộp thoại.
        quiet_until = time.time() + 1.5
        handled = 0
        while time.time() < quiet_until and handled < 2:
            time.sleep(0.3)
            visible_extra = []
            for h in so_windows.all_windows():
                if h in before:
                    continue
                try:
                    if win32gui.IsWindowVisible(h):
                        visible_extra.append(h)
                except Exception:
                    pass
            if not visible_extra:
                continue
            dlg = visible_extra[0]
            try:
                title = win32gui.GetWindowText(dlg) or "(không tên)"
            except Exception:
                title = "(không tên)"
            _p(f"Xác nhận khi lưu: {title}")
            if so_windows.force_foreground(dlg):
                time.sleep(0.2)
                try:
                    pyautogui.press("enter")
                except Exception:
                    pass
            before.add(dlg)
            handled += 1
            quiet_until = time.time() + 2.0

        _p("Đã lưu bài")
        return True

    def kill_studio_one_gracefully(self, timeout_sec: int = 15):
        """Tên gọi cũ — giữ cho code/bản build cũ. Không còn tắt cứng mặc định."""
        return self.close_studio_one_safely(timeout_sec=timeout_sec, save=True,
                                            force_kill=False)

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
        """Đóng mọi tab YouTube đang mở.
        - Browser nhiều tab: chỉ tab YouTube đóng, các tab khác giữ nguyên.
        - Browser/PWA chỉ có 1 tab YouTube: tab cuối đóng → window/process exit theo.
        Ưu tiên CDP (chính xác, không động chạm tab khác). Fallback win32 cho
        trường hợp browser được mở thủ công không có --remote-debugging-port."""
        closed_via_cdp = 0
        if hasattr(self, 'cdp_monitor'):
            try:
                closed_via_cdp = self.cdp_monitor.close_all_youtube_tabs()
            except Exception as e:
                print(f"[YOUTUBE] Lỗi enumerate CDP: {e}")

        if closed_via_cdp > 0:
            print(f"[YOUTUBE] Đã đóng {closed_via_cdp} tab YouTube qua CDP")
            return

        # Fallback: không có CDP port (browser mở thủ công). Tìm theo title.
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
            if "youtube" in title or "youtu.be" in title or "yt music" in title:
                yt_hwnds.append(hwnd)
            return True

        try:
            win32gui.EnumWindows(_enum_cb, None)
        except Exception:
            return

        if not yt_hwnds:
            print("[YOUTUBE] Không tìm thấy cửa sổ YouTube để đóng (fallback)")
            return

        for hwnd in yt_hwnds:
            try:
                win32gui.SendMessageTimeout(hwnd, win32con.WM_SYSCOMMAND, win32con.SC_CLOSE, 0, win32con.SMTO_ABORTIFHUNG, 500)
                win32gui.SendMessageTimeout(hwnd, win32con.WM_CLOSE, 0, 0, win32con.SMTO_ABORTIFHUNG, 500)
            except Exception:
                pass
        print(f"[YOUTUBE] Đã yêu cầu đóng {len(yt_hwnds)} cửa sổ YouTube (fallback win32)")
