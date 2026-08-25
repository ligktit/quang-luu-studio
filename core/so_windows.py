"""
Quang Lưu Studio — Thao tác cửa sổ Studio One (thuần win32, không phụ thuộc Qt).

Gom một chỗ mọi thứ liên quan tới việc tìm / ẩn / hiện / đưa lên trước cửa sổ
Studio One, để cả UI (nút mắt, khoá kỹ thuật) lẫn engine (đóng an toàn lúc thoát)
dùng chung một cách hiểu về "cửa sổ nào là của Studio One".

Nguyên tắc: tìm theo **PID của process** chứ không theo tiêu đề cửa sổ — plugin,
mixer, cửa sổ nhạc cụ của Studio One có tiêu đề tuỳ ý, chỉ PID là chắc chắn.
"""
import ctypes
import logging
import threading
import time

log = logging.getLogger(__name__)

PROCESS_KEYWORDS = ("studio one",)
MAIN_TITLE_KEYWORD = "studio one"

SW_HIDE = 0
SW_SHOW = 5
SW_RESTORE = 9


def win32_modules():
    """Trả (win32gui, win32con, win32process) hoặc None nếu thiếu pywin32."""
    try:
        import win32gui
        import win32con
        import win32process
        return win32gui, win32con, win32process
    except ImportError:
        return None


# ── Tìm process / cửa sổ ─────────────────────────────────────────────────────

def studio_one_pids():
    """Tập PID của mọi process Studio One đang chạy."""
    try:
        import psutil
    except ImportError:
        return set()
    pids = set()
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if any(kw in name for kw in PROCESS_KEYWORDS):
                pids.add(proc.info["pid"])
        except Exception:
            continue
    return pids


def is_running() -> bool:
    return bool(studio_one_pids())


def windows_of(pids):
    """Mọi top-level window (kể cả đang ẩn) thuộc các PID đã cho."""
    mods = win32_modules()
    if not mods or not pids:
        return []
    win32gui, _, win32process = mods
    found = []

    def _cb(hwnd, _):
        try:
            if not win32gui.IsWindow(hwnd):
                return True
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid in pids:
                found.append(hwnd)
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception as e:
        log.debug("EnumWindows lỗi: %s", e)
    return found


def all_windows():
    return windows_of(studio_one_pids())


def main_windows(hwnds=None):
    """Các cửa sổ chính — tiêu đề có chứa "Studio One" (kể cả đang ẩn).

    Hộp thoại con của Studio One thường KHÔNG mang tên này, nên dùng để phân biệt
    "cửa sổ chính" với "hộp thoại vừa bật lên".
    """
    mods = win32_modules()
    if not mods:
        return []
    win32gui = mods[0]
    out = []
    for hwnd in (all_windows() if hwnds is None else hwnds):
        try:
            if MAIN_TITLE_KEYWORD in (win32gui.GetWindowText(hwnd) or "").lower():
                out.append(hwnd)
        except Exception:
            continue
    return out


def any_visible() -> bool:
    mods = win32_modules()
    if not mods:
        return False
    win32gui = mods[0]
    for hwnd in all_windows():
        try:
            if win32gui.IsWindowVisible(hwnd):
                return True
        except Exception:
            continue
    return False


# ── Ẩn / hiện ────────────────────────────────────────────────────────────────

def hide_all() -> int:
    """Ẩn mọi cửa sổ Studio One (kể cả plugin). Trả số cửa sổ vừa ẩn.

    SW_HIDE gỡ luôn cửa sổ khỏi thanh tác vụ và khỏi Alt+Tab — khách không còn
    đường nào chạm tới.
    """
    mods = win32_modules()
    if not mods:
        return 0
    win32gui = mods[0]
    count = 0
    for hwnd in all_windows():
        try:
            if win32gui.IsWindowVisible(hwnd):
                win32gui.ShowWindow(hwnd, SW_HIDE)
                count += 1
        except Exception:
            continue
    if count:
        log.info("Đã ẩn %d cửa sổ Studio One", count)
    return count


def show_all(focus_main=True) -> int:
    """Hiện lại mọi cửa sổ Studio One. Trả số cửa sổ vừa hiện."""
    mods = win32_modules()
    if not mods:
        return 0
    win32gui = mods[0]
    hwnds = all_windows()
    count = 0
    for hwnd in hwnds:
        try:
            if not win32gui.IsWindowVisible(hwnd):
                win32gui.ShowWindow(hwnd, SW_SHOW)
                count += 1
        except Exception:
            continue
    if focus_main:
        for hwnd in main_windows(hwnds):
            if force_foreground(hwnd):
                break
    if count:
        log.info("Đã hiện %d cửa sổ Studio One", count)
    return count


def force_foreground(hwnd) -> bool:
    """Đưa cửa sổ lên trước và trao focus bàn phím thật sự.

    SetForegroundWindow trần bị Windows từ chối khi process gọi không giữ focus.
    Mượn quyền bằng AttachThreadInput với thread đang giữ foreground — đây là
    cách duy nhất để phím Ctrl+S / Enter thực sự tới được Studio One.
    """
    mods = win32_modules()
    if not mods or not hwnd:
        return False
    win32gui = mods[0]
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    attached = False
    tid_me = tid_fg = 0
    try:
        try:
            win32gui.ShowWindow(hwnd, SW_RESTORE)
        except Exception:
            pass
        fg = user32.GetForegroundWindow()
        tid_me = kernel32.GetCurrentThreadId()
        tid_fg = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        if tid_fg and tid_fg != tid_me:
            attached = bool(user32.AttachThreadInput(tid_me, tid_fg, True))
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    except Exception as e:
        log.debug("force_foreground lỗi: %s", e)
    finally:
        if attached:
            try:
                user32.AttachThreadInput(tid_me, tid_fg, False)
            except Exception:
                pass
    try:
        return int(user32.GetForegroundWindow()) == int(hwnd)
    except Exception:
        return False


# ── Chờ Studio One dựng xong cửa sổ rồi ẩn ───────────────────────────────────

def wait_for_main_window(timeout=180.0, poll=1.0):
    """Chờ tới khi Studio One dựng xong cửa sổ chính. Trả hwnd hoặc None.

    Studio One nạp bài + quét plugin có thể mất hàng chục giây; ẩn ngay sau khi
    khởi chạy là ẩn vào khoảng không.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        wins = main_windows()
        if wins:
            return wins[0]
        time.sleep(poll)
    return None


def hide_when_ready(timeout=180.0, follow_seconds=60.0, on_done=None):
    """Chạy nền: chờ cửa sổ chính xuất hiện rồi ẩn toàn bộ. Trả Thread.

    Ẩn một phát là chưa đủ: trong lúc nạp bài, Studio One còn bật thêm cửa sổ
    plugin/mixer sau đó. Bám theo thêm `follow_seconds` để ẩn nốt những cửa sổ
    mọc lên muộn, rồi mới buông (watchdog thường trực là tuỳ chọn riêng —
    xem HideGuard).
    """
    def _run():
        hwnd = wait_for_main_window(timeout=timeout)
        if hwnd is None:
            log.info("Không thấy cửa sổ Studio One trong %.0fs — bỏ qua việc ẩn", timeout)
            if on_done:
                on_done(0)
            return
        total = hide_all()
        deadline = time.monotonic() + follow_seconds
        while time.monotonic() < deadline:
            time.sleep(1.5)
            total += hide_all()
        if on_done:
            on_done(total)

    t = threading.Thread(target=_run, daemon=True, name="so-hide-when-ready")
    t.start()
    return t


# ── Watchdog giữ ẩn ──────────────────────────────────────────────────────────

class HideGuard:
    """Vòng nền ẩn lại bất kỳ cửa sổ Studio One nào bật lên khi đang khoá.

    Bắt được cả trường hợp khách tự mở Studio One từ Start Menu/desktop. Mặc
    định TẮT (tech_lock.keep_hidden) vì mỗi vòng quét đều duyệt process list.
    """

    def __init__(self, should_hide, interval=1.5):
        self._should_hide = should_hide
        self._interval = interval
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self.is_running():
            return
        # Vòng cũ vừa bị stop() có thể còn thoi thóp — phải chờ nó chết hẳn, nếu
        # không cờ _stop sẽ bị clear ngay dưới rồi vòng cũ chạy tiếp thành hai vòng.
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="so-hide-guard")
        self._thread.start()
        log.info("Bật watchdog giữ ẩn Studio One")

    def stop(self):
        self._stop.set()
        log.info("Tắt watchdog giữ ẩn Studio One")

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    def _loop(self):
        while not self._stop.wait(self._interval):
            try:
                if self._should_hide():
                    hide_all()
            except Exception as e:
                log.debug("HideGuard lỗi: %s", e)
