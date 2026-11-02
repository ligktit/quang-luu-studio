"""
Quang Lưu Studio — Thao tác cửa sổ Studio One (thuần win32, không phụ thuộc Qt).

Gom một chỗ mọi thứ liên quan tới việc tìm / ẩn / hiện / đưa lên trước cửa sổ
Studio One, để cả UI (tự ẩn DAW, Cài đặt → Cửa sổ DAW) lẫn engine (đóng an toàn lúc thoát)
dùng chung một cách hiểu về "cửa sổ nào là của Studio One".

Nguyên tắc: tìm theo **PID của process** chứ không theo tiêu đề cửa sổ — plugin,
mixer, cửa sổ nhạc cụ của Studio One có tiêu đề tuỳ ý, chỉ PID là chắc chắn.
"""
import ctypes
import logging
import re
import threading
import time
from dataclasses import dataclass

log = logging.getLogger(__name__)

# Từ khoá nhận diện lấy theo hồ sơ DAW đang chọn (core.daw). Hai tên cũ giữ lại
# cho code/test cũ còn tham chiếu — chúng chỉ là giá trị của Studio One.
PROCESS_KEYWORDS = ("studio one",)
MAIN_TITLE_KEYWORD = "studio one"


def _profile():
    from core import daw
    return daw.active()


def process_keywords() -> tuple:
    return tuple(_profile().process_keywords)


def title_is_main(title) -> bool:
    """Tiêu đề này có phải cửa sổ chính của DAW không (mọi từ bắt buộc đều có)."""
    t = (title or "").lower()
    words = _profile().main_title_requires
    # Tiêu đề cửa sổ chính luôn BẮT ĐẦU bằng tên DAW ("Studio One - vp",
    # "Cubase Pro Project - mau"). Chỉ "có chứa" thì bảng ASIO Link Pro mở trong
    # tiến trình Studio One ("O Deus ASIO Link Pro … - Studio One.exe") bị nhận nhầm.
    return bool(words) and t.startswith(words[0]) and all(word in t for word in words)

SW_HIDE = 0
SW_SHOW = 5
SW_RESTORE = 9
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
_SWP_NOMOVE_NOSIZE_NOACTIVATE = 0x0002 | 0x0001 | 0x0010

# Cửa sổ nội bộ của DAW/Windows vốn ẩn từ đầu — hiện lên là rác trên màn hình
# (đo trên Cubase 13: ô "USB Change Listener" 136×39 ở góc trái trên, bộ gõ IME).
INTERNAL_WINDOW_CLASSES = ("IME", "MSCTFIME UI", "USB Change Listener", "SteinbergDevWnd")
# Cửa sổ ngầm 133×38 của plugin JUCE (Auto-Tune, Waves…) — đo trên Studio One 5.
INTERNAL_WINDOW_TITLES = ("JUCEWindow", "Default IME", "MSCTFIME UI")

# Cửa sổ đang được giữ TOPMOST để nổi trên app đang "Ghim trên cùng" (show_window).
# Phải bỏ cờ trước khi ẩn, nếu không lần hiện sau nó đè lên mọi thứ.
_pinned_topmost = set()

# KTV vừa tự hiện cửa sổ (show_all/show_window) → hide_when_ready ngừng bám ẩn:
# "không tự ẩn lại" cái KTV vừa bật.
_user_shown = threading.Event()

# Công cụ ASIO chạy tiến trình riêng (bảng ASIO mở từ trong DAW đã thuộc tiến trình DAW).
ASIO_PROCESS_NAMES = (
    "asiolink.exe", "asio link pro.exe", "asio link tool.exe",
    "asio4all.exe", "asio4allv2.exe", "asiovadpro.exe",
    "asiolink2.exe", "asiolinktool.exe", "asiolinkpro.exe",
)


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
    keywords = process_keywords()
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if any(kw in name for kw in keywords):
                pids.add(proc.info["pid"])
        except Exception:
            continue
    return pids


daw_pids = studio_one_pids


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
    """Các cửa sổ chính — tiêu đề đạt mọi từ khoá của DAW đang chọn (kể cả đang ẩn).

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
            if title_is_main(win32gui.GetWindowText(hwnd)):
                out.append(hwnd)
        except Exception:
            continue
    return out


def quit_windows(hwnds=None):
    """Cửa sổ cần gửi WM_CLOSE để DAW thoát hẳn.

    Studio One: chính là main_windows(). Cubase: cửa sổ ứng dụng có class bắt đầu
    bằng `quit_window_class_prefix` (SmtgMain) — đóng cửa sổ project chỉ đóng bài.
    Không thấy cửa sổ nào khớp class thì quay về main_windows().
    """
    prefix = _profile().quit_window_class_prefix
    if not prefix:
        return main_windows(hwnds)
    mods = win32_modules()
    if not mods:
        return []
    win32gui = mods[0]
    candidates = all_windows() if hwnds is None else hwnds
    out = [h for h in candidates if _class_of(win32gui, h).startswith(prefix)]
    return out or main_windows(hwnds)


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
    _unpin_all(win32gui)
    count = 0
    for hwnd in all_windows():
        try:
            if win32gui.IsWindowVisible(hwnd):
                win32gui.ShowWindow(hwnd, SW_HIDE)
                count += 1
        except Exception:
            continue
    if count:
        log.info("Đã ẩn %d cửa sổ %s", count, _profile().display_name)
    return count


def show_all(focus_main=True) -> int:
    """Hiện lại mọi cửa sổ Studio One. Trả số cửa sổ vừa hiện."""
    mods = win32_modules()
    if not mods:
        return 0
    win32gui = mods[0]
    _user_shown.set()
    hwnds = all_windows()
    count = 0
    for hwnd in hwnds:
        try:
            if _is_internal(win32gui, hwnd):
                continue
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
        log.info("Đã hiện %d cửa sổ %s", count, _profile().display_name)
    return count


# ── Từng cửa sổ (plugin, bảng ASIO…) ─────────────────────────────────────────

@dataclass(frozen=True)
class WindowEntry:
    hwnd: int
    title: str
    is_main: bool
    visible: bool
    source: str  # "daw" | "asio"


def _unpin(win32gui, hwnd):
    if hwnd in _pinned_topmost:
        _pinned_topmost.discard(hwnd)
        try:
            win32gui.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, _SWP_NOMOVE_NOSIZE_NOACTIVATE)
        except Exception as e:
            log.debug("bỏ topmost %s lỗi: %s", hwnd, e)


def _unpin_all(win32gui):
    for hwnd in list(_pinned_topmost):
        _unpin(win32gui, hwnd)


def _is_internal(win32gui, hwnd) -> bool:
    """Cửa sổ rác: không tiêu đề (tooltip, cửa sổ ngầm) hoặc lớp nội bộ đã biết."""
    try:
        title = win32gui.GetWindowText(hwnd)
        if not title or title in INTERNAL_WINDOW_TITLES:
            return True
        return win32gui.GetClassName(hwnd) in INTERNAL_WINDOW_CLASSES
    except Exception:
        return True


def asio_windows() -> list:
    """Cửa sổ có tiêu đề của các công cụ ASIO chạy tiến trình riêng.

    Chỉ nhận theo TÊN TIẾN TRÌNH — khớp theo tiêu đề thì cửa sổ trình duyệt
    đang mở trang "ASIO4ALL download" cũng bị tính là công cụ ASIO.
    """
    mods = win32_modules()
    if not mods:
        return []
    win32gui, _, win32process = mods
    try:
        import psutil
    except ImportError:
        return []
    names = {}
    found = []

    def _cb(hwnd, _):
        try:
            if not win32gui.IsWindow(hwnd) or not win32gui.GetWindowText(hwnd):
                return True
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid not in names:
                try:
                    names[pid] = psutil.Process(pid).name().lower()
                except Exception:
                    names[pid] = ""
            if names[pid] in ASIO_PROCESS_NAMES:
                found.append(hwnd)
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception as e:
        log.debug("EnumWindows (ASIO) lỗi: %s", e)
    return found


def list_windows() -> list:
    """Các cửa sổ KTV bật/tắt riêng được: cửa sổ DAW (chính đứng đầu) rồi tới ASIO.

    Bỏ cửa sổ rác và cửa sổ kích thước 0 (SmtgMain của Cubase).
    """
    mods = win32_modules()
    if not mods:
        return []
    win32gui = mods[0]
    daw_hwnds = all_windows()
    mains = set(main_windows(daw_hwnds))
    entries = []
    for source, hwnds in (("daw", daw_hwnds), ("asio", asio_windows())):
        for hwnd in hwnds:
            try:
                if _is_internal(win32gui, hwnd):
                    continue
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                if right - left <= 0 or bottom - top <= 0:
                    continue
                entries.append(WindowEntry(
                    hwnd=hwnd, title=win32gui.GetWindowText(hwnd),
                    is_main=source == "daw" and hwnd in mains,
                    visible=bool(win32gui.IsWindowVisible(hwnd)), source=source))
            except Exception:
                continue
    entries.sort(key=lambda e: (e.source != "daw", not e.is_main))
    return entries


def show_window(hwnd, above_topmost=False) -> bool:
    """Hiện đúng một cửa sổ và đưa lên trước. False nếu cửa sổ không còn.

    above_topmost: app đang "Ghim trên cùng" (cửa sổ topmost) thì cửa sổ thường
    luôn nằm dưới app — giữ cửa sổ này TOPMOST cho tới khi ẩn lại (hide_window /
    hide_all bỏ cờ). Đặt rồi bỏ ngay không đủ: NOTOPMOST = sau mọi cửa sổ topmost.
    """
    mods = win32_modules()
    if not mods:
        return False
    win32gui = mods[0]
    try:
        if not win32gui.IsWindow(hwnd):
            return False
        _user_shown.set()
        win32gui.ShowWindow(hwnd, SW_SHOW)
        if above_topmost:
            win32gui.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, _SWP_NOMOVE_NOSIZE_NOACTIVATE)
            _pinned_topmost.add(hwnd)
    except Exception as e:
        log.debug("show_window(%s) lỗi: %s", hwnd, e)
        return False
    force_foreground(hwnd)
    return True


def hide_window(hwnd) -> bool:
    """Ẩn đúng một cửa sổ. False nếu cửa sổ không còn."""
    mods = win32_modules()
    if not mods:
        return False
    win32gui = mods[0]
    try:
        if not win32gui.IsWindow(hwnd):
            _pinned_topmost.discard(hwnd)
            return False
        _unpin(win32gui, hwnd)
        win32gui.ShowWindow(hwnd, SW_HIDE)
        return True
    except Exception as e:
        log.debug("hide_window(%s) lỗi: %s", hwnd, e)
        return False


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


# ── Hộp thoại hỏi lưu: luôn chọn "Không lưu" ─────────────────────────────────
#
# Đóng Studio One lúc khởi động (để chép bản mẫu .song lên) thì tuyệt đối không
# được lưu: bài đang mở là bản khách đã táy máy. Nhấn Enter là **sai** — nút mặc
# định của hộp thoại là "Save". Phải tìm đúng nút "Don't Save" rồi bấm nó.
#
# Studio One hỏi bằng MessageBox chuẩn Windows: tiêu đề "Studio One", ba nút
# Yes - No - Cancel. "No" = không lưu, và nó luôn mang control ID = IDNO (7) dù
# Windows đang chạy ngôn ngữ nào. Bắt theo ID là chắc nhất; so nhãn chỉ là dự bị.
#
# Ba lớp, theo thứ tự:
#   1. Nút IDNO của hộp thoại chuẩn (#32770) — không phụ thuộc ngôn ngữ.
#   2. Nút Win32 có nhãn khớp (EnumChildWindows + BM_CLICK).
#   3. UI Automation (uiautomation) — cho nút do Studio One tự vẽ, không có HWND.
# Không có lớp "đoán phím tắt": đoán trượt là bấm trúng Save, đúng cái phải tránh.

BM_CLICK = 0x00F5
IDNO = 7                      # nút "No" của MessageBox chuẩn
DIALOG_CLASS = "#32770"       # class của hộp thoại chuẩn Windows

_NO_SAVE_EXACT = {
    "don't save", "dont save", "do not save", "discard", "no",
    "không lưu", "khong luu", "không", "khong",
}
# Khớp cụm đầy đủ, không khớp mỗi chữ "save" — "Save As..." cũng chứa chữ đó.
_NO_SAVE_PARTIAL = ("don't save", "dont save", "do not save", "discard", "không lưu")


def _norm_label(text) -> str:
    """Chuẩn hoá nhãn nút: bỏ dấu &, gộp khoảng trắng, bỏ dấu ba chấm."""
    s = (text or "").replace("&", "").strip().lower()
    s = s.rstrip(".…").strip()
    return re.sub(r"\s+", " ", s)


def is_no_save_label(text) -> bool:
    """Nhãn này có phải nút "không lưu" hay không (khắt khe, thà trượt còn hơn nhầm)."""
    n = _norm_label(text)
    if not n:
        return False
    if n in _NO_SAVE_EXACT:
        return True
    if any(p in n for p in _NO_SAVE_PARTIAL):
        return True
    return False


def _child_buttons(hwnd):
    """[(hwnd_con, nhãn)] của mọi control con — kể cả không phải class Button."""
    mods = win32_modules()
    if not mods or not hwnd:
        return []
    win32gui = mods[0]
    out = []

    def _cb(child, _):
        try:
            out.append((child, win32gui.GetWindowText(child) or ""))
        except Exception:
            pass
        return True

    try:
        win32gui.EnumChildWindows(hwnd, _cb, None)
    except Exception as e:
        log.debug("EnumChildWindows lỗi: %s", e)
    return out


def _class_of(win32gui, hwnd) -> str:
    try:
        return win32gui.GetClassName(hwnd) or ""
    except Exception:
        return ""


def _click_no_save_win32(hwnd) -> bool:
    mods = win32_modules()
    if not mods:
        return False
    win32gui = mods[0]
    is_std_dialog = _class_of(win32gui, hwnd) == DIALOG_CLASS

    by_id = None        # nút IDNO của hộp thoại chuẩn — ưu tiên tuyệt đối
    by_label = None
    for child, label in _child_buttons(hwnd):
        if is_std_dialog and _class_of(win32gui, child).lower() == "button":
            try:
                if win32gui.GetDlgCtrlID(child) == IDNO:
                    by_id = (child, label, "IDNO")
                    break
            except Exception:
                pass
        if by_label is None and is_no_save_label(label):
            by_label = (child, label, "nhãn")

    target = by_id or by_label
    if not target:
        return False
    child, label, how = target
    try:
        win32gui.PostMessage(child, BM_CLICK, 0, 0)
        log.info("Đã bấm nút '%s' (win32, theo %s)", (label or "No").strip(), how)
        return True
    except Exception as e:
        log.debug("Bấm nút win32 lỗi: %s", e)
        return False


def _click_no_save_uia(hwnd) -> bool:
    try:
        import uiautomation as auto
    except ImportError:
        log.debug("Thiếu uiautomation — bỏ lớp UIA")
        return False
    try:
        with auto.UIAutomationInitializerInThread(debug=False):
            root = auto.ControlFromHandle(hwnd)
            if not root:
                return False
            btn = root.ButtonControl(
                searchDepth=6,
                Compare=lambda c, d: is_no_save_label(c.Name),
            )
            if not btn.Exists(1.0, 0.2):
                return False
            name = btn.Name
            try:
                btn.GetInvokePattern().Invoke()
            except Exception:
                btn.Click(simulateMove=False, waitTime=0)
            log.info("Đã bấm nút '%s' (UIA)", name)
            return True
    except Exception as e:
        log.debug("UIA tìm nút không-lưu lỗi: %s", e)
        return False


def click_no_save(hwnd) -> bool:
    """Tìm và bấm nút "Không lưu" trong hộp thoại. False = không tìm thấy.

    False thì phía gọi PHẢI dừng lại (xem cancel_dialog) chứ không được nhấn
    Enter cho xong — Enter là Save.
    """
    if _click_no_save_win32(hwnd):
        return True
    return _click_no_save_uia(hwnd)


def cancel_dialog(hwnd) -> bool:
    """Đóng hộp thoại bằng Escape (= Cancel) — huỷ luôn việc đóng Studio One.

    Dùng khi không tìm được nút "Không lưu": thà để Studio One chạy tiếp còn hơn
    bấm bừa vào nút Save.
    """
    mods = win32_modules()
    if not mods or not hwnd:
        return False
    win32gui, win32con, _ = mods
    try:
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        return True
    except Exception as e:
        log.debug("Huỷ hộp thoại lỗi: %s", e)
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
    mọc lên muộn, rồi mới buông. KTV tự hiện cửa sổ (Cài đặt) giữa chừng thì
    ngừng bám ngay — không ẩn lại cái KTV vừa bật.
    """
    _user_shown.clear()

    def _run():
        hwnd = wait_for_main_window(timeout=timeout)
        if hwnd is None:
            log.info("Không thấy cửa sổ Studio One trong %.0fs — bỏ qua việc ẩn", timeout)
            if on_done:
                on_done(0)
            return
        total = 0 if _user_shown.is_set() else hide_all()
        deadline = time.monotonic() + follow_seconds
        while time.monotonic() < deadline and not _user_shown.is_set():
            time.sleep(1.5)
            if _user_shown.is_set():
                break
            total += hide_all()
        if on_done:
            on_done(total)

    t = threading.Thread(target=_run, daemon=True, name="so-hide-when-ready")
    t.start()
    return t


# ── Chờ Studio One sẵn sàng nhận MIDI ────────────────────────────────────────
#
# Vấn đề: cổng MIDI ảo (QuangLuuMIDI, loopMIDI) mở được ngay cả khi Studio One
# CHƯA chạy, nên `is_midi_connected()` bật True từ giây đầu. App bắn hết CC khởi
# tạo (mode, vang, auto-tune, khử ồn) trong lúc Studio One còn đang nạp bài →
# lệnh rơi vào khoảng không, cả buổi Studio One lệch trạng thái với giao diện mà
# không ai hay.
#
# Không có cách nào hỏi Studio One "nạp xong chưa". Nên làm hai việc:
#   1. Chờ nó thật sự dựng xong CỬA SỔ CHÍNH (mốc sớm nhất quan sát được).
#   2. Bắn lại **nhiều lần** theo mốc thời gian giãn dần — cửa sổ chính hiện ra
#      sớm hơn lúc bài nạp xong (MIDI map nằm trong bài), mà thời gian nạp thì
#      tuỳ máy, tuỳ số plugin. CC là lệnh idempotent nên gửi thừa hoàn toàn vô
#      hại, rẻ hơn nhiều so với đoán trượt một lần rồi lệch cả buổi.
#
# Studio One tắt rồi mở lại giữa phiên (KTV hoặc Tự sửa âm thanh) thì lịch được nạp
# lại từ đầu — cửa sổ mới nghĩa là bài mới nạp, phải đồng bộ lại.

# Mốc bắn lại, tính từ lúc THẤY cửa sổ chính (giây).
DEFAULT_RESEND_DELAYS = (3.0, 10.0, 25.0, 50.0)


class ReadySchedule:
    """Máy trạng thái thuần cho lịch bắn lại MIDI. Không ngủ, không thread.

    Tách khỏi phần polling để test được bằng thời gian giả: chỉ cần bơm
    (thời điểm, Studio One có cửa sổ chưa) rồi xem nó bảo bắn hay không.
    """

    def __init__(self, resend_delays=DEFAULT_RESEND_DELAYS):
        self._delays = tuple(sorted(float(d) for d in resend_delays))
        self._seen_at = None    # lúc thấy cửa sổ chính (None = chưa thấy)
        self._done = 0          # số lần đã bắn cho lần xuất hiện này

    @property
    def pending(self) -> bool:
        """Còn mốc bắn nào chưa tới hay không (dùng để chọn nhịp quét)."""
        return self._seen_at is not None and self._done < len(self._delays)

    def reset(self):
        self._seen_at = None
        self._done = 0

    def update(self, now: float, so_ready: bool) -> bool:
        """Bơm một lần quét. True = tới lúc bắn lại toàn bộ trạng thái MIDI.

        `so_ready` = Studio One đang có cửa sổ chính. Mất cửa sổ (thoát Studio
        One) thì lịch reset — lần mở sau được đồng bộ lại từ đầu.
        """
        if not so_ready:
            self.reset()
            return False

        if self._seen_at is None:
            # Vừa thấy cửa sổ — chưa bắn ngay, chờ mốc đầu tiên cho bài kịp nạp.
            self._seen_at = now
            return False

        if self._done < len(self._delays) and now - self._seen_at >= self._delays[self._done]:
            self._done += 1
            return True
        return False


class ReadyWatcher:
    """Vòng nền gọi `on_ready()` mỗi khi tới mốc bắn lại MIDI.

    `on_ready` chạy trên thread nền — phía Qt phải bắn signal về main thread chứ
    đừng đụng widget trực tiếp.

    Nhịp quét đổi theo trạng thái: dày (`poll`) trong lúc còn mốc chưa bắn để
    bám sát mốc, thưa (`idle_poll`) khi đang chờ Studio One xuất hiện hoặc đã
    bắn hết — mỗi vòng quét đều phải duyệt process list nên không quét dày mãi.
    """

    def __init__(self, on_ready, poll=2.0, idle_poll=6.0,
                 resend_delays=DEFAULT_RESEND_DELAYS):
        self._on_ready = on_ready
        self._poll = poll
        self._idle_poll = idle_poll
        self._schedule = ReadySchedule(resend_delays)
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self.is_running():
            return
        # Vòng cũ vừa bị stop() có thể còn thoi thóp — chờ nó chết hẳn, nếu không
        # cờ _stop bị clear ngay dưới rồi vòng cũ chạy tiếp thành hai vòng.
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._stop.clear()
        self._schedule.reset()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="so-ready-watcher")
        self._thread.start()
        log.info("Bật vòng chờ %s sẵn sàng nhận MIDI", _profile().display_name)

    def stop(self):
        self._stop.set()

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    def _loop(self):
        while True:
            try:
                if self._schedule.update(time.monotonic(), bool(main_windows())):
                    self._on_ready()
            except Exception as e:
                log.debug("ReadyWatcher lỗi: %s", e)
            interval = self._poll if self._schedule.pending else self._idle_poll
            if self._stop.wait(interval):
                return
