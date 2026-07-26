"""YouTube URL detection, watcher, open_youtube_url, and monitoring for SystemEngine."""
import gc
import os
import re
import time
import ctypes
import ctypes.wintypes
import threading
import subprocess
import weakref

import psutil

try:
    import win32gui
    import win32con
    import win32process
except ImportError:
    pass

from core.config import CDP_DEBUG_PORT
from core.memory import MemoryProfiler, MemoryGuard
from core.scoring import ScoringEngine
from core.ytdlp_support import extract_info_with_auth, make_ydl_opts

# Module-level ctypes callback type (cached once — prevents ctypes ref leaks on poll)
_WNDENUMPROC_TYPE = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

# Tự động thử lại khi dò tone TỰ ĐỘNG thất bại — áp dụng cho CẢ 2 chế độ (fast/full).
# Sau khi hết số lần thử, hiển thị rõ nguyên nhân lỗi cho người dùng.
_AUTO_DETECT_MAX_ATTEMPTS    = 3
_AUTO_DETECT_RETRY_DELAY_SEC = 3


# ── Pure URL utility functions (no self needed) ──────────────────────────────

def _normalize_url(url: str) -> str:
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    return url


def _clean_youtube_url(url: str):
    patterns = [
        r'(?:youtube\.com/watch\?.*v=)([a-zA-Z0-9_-]{11})',
        r'(?:youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com/shorts/)([a-zA-Z0-9_-]{11})',
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return f"https://www.youtube.com/watch?v={m.group(1)}"
    return None


class _YouTubeMixin:
    # Keep as static methods for backward compat (e.g. frontend calls SystemEngine._normalize_url)
    _normalize_url     = staticmethod(_normalize_url)
    _clean_youtube_url = staticmethod(_clean_youtube_url)

    # ── Enum Windows ────────────────────────────────────────────────────────────

    @staticmethod
    def _enum_all_visible_windows():
        all_windows = []
        def enum_callback(hwnd, _):
            if ctypes.windll.user32.IsWindowVisible(hwnd):
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                    all_windows.append((hwnd, buf.value))
            return True
        ctypes.windll.user32.EnumWindows(_WNDENUMPROC_TYPE(enum_callback), 0)
        return all_windows

    # ── URL Detection ───────────────────────────────────────────────────────────

    @staticmethod
    def detect_youtube_url_from_browser(quiet=False, all_windows=None, pwa_title_cache=None):
        try:
            import uiautomation as auto
        except ImportError:
            if not quiet:
                print("[DÒ TONE] Thư viện 'uiautomation' chưa được cài đặt.")
            return None

        browser_keywords = [
            "Google Chrome", "Microsoft​ Edge", "Microsoft Edge",
            "Mozilla Firefox", "Brave", "Opera", "Vivaldi", "Edge",
        ]

        if all_windows is None:
            all_windows = _YouTubeMixin._enum_all_visible_windows()

        browser_windows = []
        for hwnd, title in all_windows:
            for keyword in browser_keywords:
                if keyword.lower() in title.lower():
                    browser_windows.append({"hwnd": hwnd, "title": title, "browser": keyword})
                    break

        if not quiet:
            print(f"[DÒ TONE] Tìm thấy {len(browser_windows)} cửa sổ trình duyệt")

        for bw in browser_windows:
            hwnd    = bw["hwnd"]
            control = None
            children = None
            try:
                control  = auto.ControlFromHandle(hwnd)
                if control is None:
                    continue

                children = control.GetChildren()
                for child in children:
                    try:
                        edit = child.EditControl(searchDepth=8)
                        if edit and edit.Exists(0.1):
                            value = ""
                            try:
                                pattern = edit.GetValuePattern()
                                if pattern:
                                    value = pattern.Value
                            except Exception:
                                pass
                            if not value:
                                try:
                                    value = edit.GetWindowText() or ""
                                except Exception:
                                    pass
                            if value and ("youtube.com" in value or "youtu.be" in value):
                                url   = _normalize_url(value)
                                clean = _clean_youtube_url(url)
                                if clean:
                                    print(f"   YouTube URL: {clean}")
                                    return clean
                    except Exception:
                        continue
                del children
                children = None

                edit = control.EditControl(searchDepth=10)
                if edit and edit.Exists(0.5):
                    value = ""
                    try:
                        pattern = edit.GetValuePattern()
                        if pattern:
                            value = pattern.Value
                    except Exception:
                        pass
                    if not value:
                        try:
                            value = edit.GetWindowText() or ""
                        except Exception:
                            pass
                    if value and ("youtube.com" in value or "youtu.be" in value):
                        url   = _normalize_url(value)
                        clean = _clean_youtube_url(url)
                        if clean:
                            print(f"   YouTube URL: {clean}")
                            return clean

                try:
                    edit = control.EditControl(searchDepth=15, Name="Address and search bar")
                    if edit and edit.Exists(0.5):
                        value = ""
                        try:
                            pattern = edit.GetValuePattern()
                            if pattern:
                                value = pattern.Value
                        except Exception:
                            pass
                        if not value:
                            try:
                                value = edit.GetWindowText() or ""
                            except Exception:
                                pass
                        if value and ("youtube.com" in value or "youtu.be" in value):
                            url   = _normalize_url(value)
                            clean = _clean_youtube_url(url)
                            if clean:
                                print(f"   YouTube URL (Brave): {clean}")
                                return clean
                except Exception:
                    pass

            except Exception as e:
                print(f"   Lỗi đọc cửa sổ {bw['browser']}: {e}")
                continue
            finally:
                del control, children

        pwa_url = _YouTubeMixin._detect_youtube_from_pwa(
            quiet, all_windows=all_windows, pwa_title_cache=pwa_title_cache
        )
        if pwa_url:
            return pwa_url

        if not quiet:
            print("[DÒ TONE] Không tìm thấy YouTube URL trên trình duyệt hoặc PWA.")
        return None

    @staticmethod
    def _detect_youtube_from_pwa(quiet=False, all_windows=None, pwa_title_cache=None):
        pwa_browsers = {"chrome.exe", "msedge.exe", "brave.exe"}

        if all_windows is None:
            all_windows = _YouTubeMixin._enum_all_visible_windows()

        browser_keywords_lower = [
            "google chrome", "microsoft edge", "mozilla firefox",
            "brave", "opera", "vivaldi",
        ]

        pwa_candidates = []
        for hwnd, title in all_windows:
            title_lower = title.lower().strip()
            if "- youtube" not in title_lower:
                continue
            is_browser = any(kw in title_lower for kw in browser_keywords_lower)
            if is_browser:
                continue
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                proc      = psutil.Process(pid)
                proc_name = proc.name().lower()
                is_pwa_process = proc_name in pwa_browsers
                if not is_pwa_process:
                    try:
                        parent = proc.parent()
                        for _ in range(5):
                            if parent is None:
                                break
                            if parent.name().lower() in pwa_browsers:
                                is_pwa_process = True
                                break
                            parent = parent.parent()
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass
                if not is_pwa_process:
                    continue
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
            except Exception as e:
                if not quiet:
                    print(f"   [PWA] Lỗi kiểm tra process: {e}")
                continue
            pwa_candidates.append({"hwnd": hwnd, "title": title})

        if not pwa_candidates:
            return None

        if not quiet:
            print(f"[DÒ TONE] Tìm thấy {len(pwa_candidates)} cửa sổ PWA YouTube")

        import re as _re
        for candidate in pwa_candidates:
            title = candidate["title"]
            yt_suffix_idx = title.rfind(" - YouTube")
            if yt_suffix_idx <= 0:
                continue

            video_title = title[:yt_suffix_idx].strip()
            if not video_title:
                continue

            video_title = _re.sub(r'^YouTube\s*-\s*(\(\d+\)\s*)?', '', video_title).strip()
            video_title = video_title.replace('‪', '').replace('‬', '')

            if not video_title or video_title.lower() == "youtube":
                continue

            if not quiet:
                print(f"[DÒ TONE] PWA YouTube: \"{video_title}\"")

            if pwa_title_cache is not None and video_title in pwa_title_cache:
                cached_url = pwa_title_cache[video_title]
                if not quiet:
                    print(f"   PWA cache hit: {cached_url}")
                return cached_url

            try:
                info = extract_info_with_auth(
                    f"ytsearch:{video_title}",
                    make_ydl_opts(skip_download=True, default_search='ytsearch'),
                    download=False,
                    log_prefix="[DÒ TONE]",
                )
                if not info:
                    continue
                entries = info.get('entries', [])
                if entries:
                    video_id = entries[0].get('id', '')
                    if video_id:
                        found_url = f"https://www.youtube.com/watch?v={video_id}"
                        print(f"   PWA YouTube URL: {found_url}")
                        if pwa_title_cache is not None:
                            pwa_title_cache[video_title] = found_url
                        return found_url
            except Exception as e:
                if not quiet:
                    print(f"   [DÒ TONE] PWA search lỗi: {e}")
                continue
        return None

    # ── open_youtube_url ────────────────────────────────────────────────────────

    def open_youtube_url(self, url, on_video_end_callback=None, on_tone_detected=None,
                         manual_timeline=None, play_callback=None):
        """Phát URL YouTube.

        play_callback: nếu được cung cấp (chế độ màn hình karaoke nhúng), thay vì mở
        trình duyệt ngoài, gọi play_callback(url) để nạp video vào player nhúng. Toàn
        bộ logic replay manual timeline được giữ nguyên. Phần giám sát kết thúc video
        bằng heuristic sleep(duration+5) được bỏ qua vì player nhúng tự báo qua event.
        """
        if not url:
            return

        self.stop_tone_detection()
        self.current_youtube_url       = url
        self.on_video_end_callback     = on_video_end_callback
        self.on_tone_detected_callback = on_tone_detected
        self._last_watched_url         = url  # sync immediately so watcher doesn't cancel replay

        # ── Chế độ player nhúng: nạp thẳng vào màn hình karaoke, không mở browser ──
        if play_callback is not None:
            try:
                play_callback(url)
            except Exception as e:
                print(f"[PLAYER] play_callback lỗi: {e}")
            if manual_timeline:
                def replay_manual_embedded():
                    time.sleep(3)  # chờ player nạp video
                    self._send_tone_midi(manual_timeline[0])
                    cancel_ev = self._tone_session.start_scanning(url)
                    cancel_ev2 = self._tone_session.transition_to_replaying(expected_token=cancel_ev)
                    if cancel_ev2 is not None:
                        self._replay_manual_timeline(manual_timeline, cancel_event=cancel_ev2)
                threading.Thread(target=replay_manual_embedded, daemon=True).start()
            return

        def open_browser():
            browser_path = self.settings.get("browser_path")
            browser_name = None

            if browser_path:
                browser_exe = os.path.basename(browser_path).lower()
                if "chrome" in browser_exe:    browser_name = "chrome.exe"
                elif "firefox" in browser_exe: browser_name = "firefox.exe"
                elif "edge" in browser_exe:    browser_name = "msedge.exe"
                elif "brave" in browser_exe:   browser_name = "brave.exe"
                elif "opera" in browser_exe:   browser_name = "opera.exe"

            browser_running = False
            if browser_name:
                browser_running = any(
                    p.info['name'].lower() == browser_name.lower()
                    for p in psutil.process_iter(['name'])
                )

            if browser_running:
                try:
                    hwnd = None
                    def enum_callback(h, _):
                        nonlocal hwnd
                        if win32gui.IsWindowVisible(h):
                            text = win32gui.GetWindowText(h).lower()
                            if any(k in text for k in ["chrome", "firefox", "edge", "brave", "opera", "youtube"]):
                                hwnd = h
                    win32gui.EnumWindows(enum_callback, None)
                    if hwnd:
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                        win32gui.SetForegroundWindow(hwnd)
                        time.sleep(0.3)
                except Exception as e:
                    print(f"Không thể focus vào browser: {e}")

            if browser_path:
                try:
                    args     = self._parse_browser_path(browser_path)
                    exe_path = args[0]
                    if os.path.exists(exe_path):
                        if not any("remote-debugging-port" in a for a in args):
                            args.insert(1, f"--remote-debugging-port={CDP_DEBUG_PORT}")
                        if not any("remote-allow-origins" in a for a in args):
                            args.insert(1, "--remote-allow-origins=*")
                        args.append(url)
                        print(f"[BROWSER] Mở URL với CDP: {exe_path}")
                        subprocess.Popen(args)
                    else:
                        print(f"[BROWSER] Không tìm thấy file: {exe_path}. Mở bằng mặc định...")
                        os.startfile(url)
                except Exception as e:
                    print(f"[BROWSER] Lỗi khởi chạy: {e}")
                    try:
                        os.startfile(url)
                    except Exception:
                        pass
            else:
                try:
                    os.startfile(url)
                except Exception as e:
                    print(f"[BROWSER] Lỗi mở URL mặc định: {e}")

        threading.Thread(target=open_browser, daemon=True).start()

        if manual_timeline:
            def replay_manual():
                time.sleep(3)  # Chờ browser mở
                self._send_tone_midi(manual_timeline[0])
                cancel_ev = self._tone_session.start_scanning(url)
                cancel_ev2 = self._tone_session.transition_to_replaying(expected_token=cancel_ev)
                if cancel_ev2 is not None:
                    self._replay_manual_timeline(manual_timeline, cancel_event=cancel_ev2)
            threading.Thread(target=replay_manual, daemon=True).start()
        else:
            # Chờ browser mở rồi bắt đầu monitoring
            def delayed_monitoring():
                time.sleep(2)
                self._start_youtube_monitoring(url)
            threading.Thread(target=delayed_monitoring, daemon=True).start()

    # ── notify_video_ended ───────────────────────────────────────────────────────

    def notify_video_ended(self):
        """Báo video đã kết thúc (dùng cho màn hình karaoke nhúng — event IFrame
        thay cho heuristic sleep(duration+5)). Kích hoạt chấm điểm nếu đang ghi."""
        try:
            print("[VIDEO END] Video kết thúc (player nhúng).")
            self.youtube_monitoring_active = False
            if getattr(self, "quick_score_active", False):
                print("[VIDEO END] Quick Score đang ghi âm -> tự động dừng để chấm điểm.")
                self.quick_score_active = False
            elif self.on_video_end_callback:
                self.on_video_end_callback(None)
        except Exception as e:
            print(f"[VIDEO END] Lỗi: {e}")
            if self.on_video_end_callback:
                self.on_video_end_callback(None)

    # ── _start_youtube_monitoring ────────────────────────────────────────────────

    def _start_youtube_monitoring(self, youtube_url):
        print("[YOUTUBE MONITORING] Bắt đầu theo dõi video YouTube...")
        print(f"[YOUTUBE MONITORING] URL: {youtube_url}")

        def get_video_duration():
            try:
                print("[YOUTUBE MONITORING] Đang lấy thông tin video...")
                info = extract_info_with_auth(
                    youtube_url, make_ydl_opts(), download=False,
                    log_prefix="[YOUTUBE MONITORING]",
                )
                duration = info.get('duration', 0)
                title    = info.get('title', 'N/A')
                print(f"[YOUTUBE MONITORING] {title} ({duration // 60}:{duration % 60:02d})")
                return duration
            except Exception as e:
                print(f"[YOUTUBE MONITORING] Không thể lấy độ dài video: {e}")
                return None

        def on_video_end():
            """When video ends, trigger Quick Score to finish if active."""
            try:
                print("[VIDEO END] Video kết thúc.")
                if self.quick_score_active:
                    # Quick Score is recording — trigger it to stop and score
                    print("[VIDEO END] Quick Score đang ghi âm -> tự động dừng để chấm điểm.")
                    self.quick_score_active = False
                    # The _quick_score_task loop will detect this,
                    # stop recording, and score the user's actual audio.
                else:
                    print("[VIDEO END] Quick Score không hoạt động, bỏ qua chấm điểm.")
                    if self.on_video_end_callback:
                        self.on_video_end_callback(None)
            except Exception as e:
                print(f"[VIDEO END] Lỗi: {e}")
                if self.on_video_end_callback:
                    self.on_video_end_callback(None)

        def monitor_video():
            self.youtube_monitoring_active = True
            duration = get_video_duration()
            if duration and duration > 0:
                wait_time = duration + 5
                print(f"[YOUTUBE MONITORING] Đợi {wait_time}giây...")
                time.sleep(wait_time)
                if self.youtube_monitoring_active:
                    on_video_end()
            self.youtube_monitoring_active = False
            print("[YOUTUBE MONITORING] Đã kết thúc giám sát video")

        self.youtube_monitoring_active = False
        threading.Thread(target=monitor_video, daemon=True).start()

    # ── YouTube URL Watcher ──────────────────────────────────────────────────────

    def start_youtube_watcher(self, poll_interval=1.5):
        if self._youtube_watcher_active:
            return
        self._youtube_watcher_active = True
        self._youtube_watcher_thread = threading.Thread(
            target=self._youtube_watcher_loop,
            args=(poll_interval,),
            daemon=True,
        )
        self._youtube_watcher_thread.start()
        print("[YT WATCHER] Đã bắt đầu theo dõi trình duyệt...")

    def stop_youtube_watcher(self):
        self._youtube_watcher_active = False
        if self._youtube_watcher_thread:
            self._youtube_watcher_thread.join(timeout=3.0)
            self._youtube_watcher_thread = None
        with self._pending_url_lock:
            self._pending_url_queue.clear()
        print("[YT WATCHER] Đã dừng theo dõi trình duyệt.")

    def _youtube_watcher_loop(self, poll_interval):
        engine_ref = weakref.ref(self)
        mem        = MemoryProfiler("YT_WATCHER")
        poll_count = 0

        while self._youtube_watcher_active:
            try:
                if self._tone_session.is_active:
                    current_interval = 5.0
                elif self._no_browser_count > 5:
                    current_interval = 5.0
                else:
                    current_interval = poll_interval

                def _handle_new_url(url):
                    self._no_browser_count = 0
                    if url != self._last_watched_url:
                        if not self._tone_session.is_active:
                            self._dispatch_auto_detect(url, engine_ref)
                            self._last_watched_url = url
                        elif self._tone_session.is_scanning:
                            with self._pending_url_lock:
                                self._pending_url_queue = [url]
                            print(f"[YT WATCHER] {url[:60]}... sẽ được dò sau")
                        elif self._tone_session.is_replaying:
                            print("[YT WATCHER] URL mới trong lúc replay → hủy, dò mới")
                            self._tone_session.stop()
                            self._dispatch_auto_detect(url, engine_ref)
                            self._last_watched_url = url

                # Tier 0: CDP
                _url_from_cdp = False
                if self.cdp_monitor.is_connected and self.cdp_monitor.target_url:
                    cdp_url = _clean_youtube_url(self.cdp_monitor.target_url)
                    if cdp_url:
                        _url_from_cdp = True
                        _handle_new_url(cdp_url)

                if not _url_from_cdp:
                    all_windows = _YouTubeMixin._enum_all_visible_windows()

                    _BROWSER_TITLE_KEYS = ("chrome", "edge", "firefox", "brave", "opera", "vivaldi", "youtube")
                    browser_titles = tuple(
                        title for _, title in all_windows
                        if any(k in title.lower() for k in _BROWSER_TITLE_KEYS)
                    )
                    fingerprint = hash(browser_titles)

                    if fingerprint != self._prev_browser_titles:
                        self._prev_browser_titles = fingerprint
                        url = _YouTubeMixin.detect_youtube_url_from_browser(
                            quiet=True,
                            all_windows=all_windows,
                            pwa_title_cache=self._pwa_title_cache,
                        )
                        if url:
                            _handle_new_url(url)
                        else:
                            self._no_browser_count += 1

                    del all_windows

            except Exception as e:
                print(f"[YT WATCHER] Lỗi poll: {e}")

            if not self._tone_session.is_active:
                pending_url = None
                with self._pending_url_lock:
                    if self._pending_url_queue:
                        pending_url = self._pending_url_queue.pop(0)
                        self._pending_url_queue.clear()
                if pending_url and pending_url != self._last_watched_url:
                    print(f"[YT WATCHER] Đang xử lý URL đang chờ: {pending_url[:60]}...")
                    self._dispatch_auto_detect(pending_url, engine_ref)
                    self._last_watched_url = pending_url

            poll_count += 1
            if poll_count % 20 == 0:
                MemoryGuard.force_cleanup()

            # mem.checkpoint("poll")
            pass

            for _ in range(int(current_interval * 10)):
                if not self._youtube_watcher_active:
                    mem.summary()
                    return
                time.sleep(0.1)

    # ── Dispatch helper ──────────────────────────────────────────────────────────

    def _dispatch_auto_detect(self, url, engine_ref, skip_resolve=False, _attempt=1):
        max_attempts = _AUTO_DETECT_MAX_ATTEMPTS
        print(f"[YT WATCHER] Dò tone tự động: {url} (lần {_attempt}/{max_attempts})")

        # Đánh dấu URL đang được dò là URL "đang xem" ngay tại điểm dispatch DUY NHẤT
        # này. Nhờ vậy mọi đường gọi (watcher loop, hàng đợi pending của auto_detect
        # trong _tone.py, nút "Dò Lại" ở frontend) đều cập nhật _last_watched_url một
        # cách thống nhất → watcher KHÔNG dò trùng lại cùng URL đó như thể URL mới.
        # Chỉ làm ở lần thử đầu (retry giữ nguyên URL nên không cần ghi lại).
        if _attempt == 1:
            self._last_watched_url = url

        def _on_complete(result):
            eng = engine_ref()
            if eng is None:
                return
            result['auto_detected'] = True
            if eng.on_auto_tone_complete:
                eng.on_auto_tone_complete(result)

        def _on_error(msg):
            eng = engine_ref()
            if eng is None:
                return
            eng._tone_session.stop()

            # Còn lượt thử → tự động dò lại sau một khoảng chờ ngắn.
            if _attempt < max_attempts:
                print(f"[YT WATCHER] Dò tone lỗi (lần {_attempt}/{max_attempts}): {msg} → thử lại...")
                if eng.on_auto_tone_progress:
                    eng.on_auto_tone_progress(
                        f"⚠️ Dò tone lỗi, đang thử lại lần {_attempt + 1}/{max_attempts}…"
                    )

                def _retry():
                    time.sleep(_AUTO_DETECT_RETRY_DELAY_SEC)
                    eng2 = engine_ref()
                    if eng2 is None:
                        return
                    # Nếu đã có phiên dò khác chạy (user mở video mới) → bỏ thử lại.
                    if eng2._tone_session.is_active:
                        print("[YT WATCHER] Có phiên dò khác đang chạy → hủy thử lại.")
                        return
                    # Kẽ hở: phiên mới có thể kết thúc CỰC NHANH (cache hit) → session về
                    # IDLE trước khi _retry thức dậy. Nếu chỉ dựa is_active, ta sẽ dò lại
                    # URL CŨ và gửi MIDI sai tone đè lên bài user đang xem. Vì vậy chỉ thử
                    # lại khi URL đang retry VẪN là URL người dùng đang xem.
                    current_url = eng2._last_watched_url or eng2.current_youtube_url
                    if current_url is not None and current_url != url:
                        print(
                            f"[YT WATCHER] URL đã đổi (đang xem {str(current_url)[:60]}...) "
                            f"→ hủy thử lại URL cũ {url[:60]}..."
                        )
                        return
                    # Lần thử lại luôn bỏ qua cache (đã miss ở lần đầu) và dò tươi.
                    eng2._dispatch_auto_detect(
                        url, engine_ref, skip_resolve=True, _attempt=_attempt + 1,
                    )

                threading.Thread(target=_retry, daemon=True).start()
                return

            # Hết lượt thử → báo lỗi rõ nguyên nhân.
            final_msg = (
                f"Dò tone thất bại sau {max_attempts} lần thử.\n"
                f"Nguyên nhân: {msg}"
            )
            print(f"[YT WATCHER] {final_msg}")
            if eng.on_auto_tone_error:
                eng.on_auto_tone_error(final_msg)

        def _on_progress(text):
            eng = engine_ref()
            if eng and eng.on_auto_tone_progress:
                eng.on_auto_tone_progress(text)

        scan_mode = getattr(self, 'tone_scan_mode', 'fast')
        if scan_mode == 'fast':
            self.detect_tone_from_browser(
                on_complete=_on_complete,
                on_error=_on_error,
                on_progress=_on_progress,
                url=url,
                skip_resolve=skip_resolve,
            )
        else:
            def _on_full_scan_complete(data):
                timeline    = data.get('timeline', [])
                first_entry = timeline[0] if timeline else {}
                raw_key     = first_entry.get('key_display', 'C')
                key_root    = _extract_key_root(raw_key)
                flat_result = {
                    'full_scan':    True,
                    'url':          data.get('url', ''),
                    'title':        data.get('title', ''),
                    'timeline':     timeline,
                    'key_display':  raw_key,
                    'key':          key_root,
                    'scale':        first_entry.get('scale', 'Major'),
                    'confidence':   first_entry.get('confidence', 0),
                    'from_loopback': data.get('from_loopback', False),
                }
                _on_complete(flat_result)

            self.auto_detect_youtube_timeline(
                url=url,
                on_complete=_on_full_scan_complete,
                on_error=_on_error,
                on_progress=_on_progress,
                skip_resolve=skip_resolve,
            )


def _extract_key_root(key_display: str) -> str:
    """
    Trích xuất root note từ key_display.
    Xử lý cả 2 format:
      - 'Am', 'C#m', 'D#m'  → 'A', 'C#', 'D#'   (format từ ToneDetector)
      - 'D Major', 'Am Minor' → 'D', 'Am'          (format cũ có space)
    """
    if not key_display:
        return "C"
    s = key_display.strip()
    # Format có space: lấy phần đầu tiên
    if " " in s:
        return s.split()[0]
    # Format minor có suffix 'm': 'Am' → 'A', 'C#m' → 'C#', 'D#m' → 'D#'
    if s.endswith("m") and len(s) >= 2:
        return s[:-1]
    return s
