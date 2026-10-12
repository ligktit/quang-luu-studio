"""Cập nhật ngầm qua Velopack: kiểm → tải sẵn → áp dụng khi tắt app.

Chỉ chạy trên bản cài Velopack (%LocalAppData%\\QuangLuuStudio\\current, có
Update.exe ở thư mục cha). Nguồn duy nhất là feed của server — server quyết định
máy nào nhận bản nào (is_active, rollout_percent); KHÔNG có đường dự phòng GitHub.
Không hộp thoại: bản mới chỉ được tải sẵn, áp dụng khi app tắt bình thường
(hoặc Velopack tự áp dụng ở lần mở sau nếu app bị tắt ngang).
"""
import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

CHECK_DELAY_S = 60                       # chờ app mở xong rồi mới kiểm lần đầu
CHECK_INTERVAL_S = 6 * 3600              # máy hát mở liên tục nhiều ngày
CHECK_TIMEOUT_MS = 30_000                # hỏi feed: mạng treo thì bỏ, lần sau thử lại
DOWNLOAD_TIMEOUT_MS = 3 * 3600 * 1000    # gói Full ~550 MB qua 4G chập chờn
_FP_RE = re.compile(r"[A-Za-z0-9_-]{1,128}")   # khớp valid_fingerprint của server

_updater = None


def feed_url(base, fingerprint):
    base = str(base or "").strip().rstrip("/")
    if not base or not _FP_RE.fullmatch(fingerprint or ""):
        return None
    return f"{base}/api/v1/updates/velopack/{fingerprint}"


def make_manager(url, timeout_ms):
    import velopack   # import trễ: test và bản chạy từ mã nguồn không cần
    return velopack.UpdateManager(velopack.HttpSource(url, velopack.HttpOptions([], timeout_ms)))


@dataclass
class UpdateState:
    pending: Optional[str] = None       # đã tải sẵn, dùng ở lần mở sau
    downloading: Optional[str] = None
    checked_at: Optional[float] = None  # lần hỏi feed thành công gần nhất
    error: bool = False                 # lượt gần nhất lỗi (mạng, server, tải)


class BackgroundUpdater:
    def __init__(self, url, auto_check, manager_factory=make_manager, clock=time.time, wait=None):
        self._url = url
        self._auto_check = auto_check
        self._factory = manager_factory
        self._clock = clock
        self._stop = threading.Event()
        self._wait = wait or self._stop.wait   # trả True khi được yêu cầu dừng
        self._lock = threading.Lock()          # một lượt kiểm/tải tại một thời điểm
        self.state = UpdateState()

    def check_once(self):
        """Một lượt: hỏi feed, có bản mới thì tải sẵn. Không bao giờ ném lỗi."""
        if not self._lock.acquire(blocking=False):
            return
        try:
            mgr = self._factory(self._url, CHECK_TIMEOUT_MS)
            if self.state.pending is None:
                waiting = mgr.get_update_pending_restart()   # tải từ phiên trước, chưa áp dụng
                if waiting is not None:
                    self.state.pending = waiting.Version
            info = mgr.check_for_updates()
            self.state.checked_at = self._clock()
            self.state.error = False
            if info is None:
                return
            target = info.TargetFullRelease.Version
            if target == self.state.pending:
                return
            self.state.downloading = target
            log.info("Có bản %s — tải ngầm", target)
            self._factory(self._url, DOWNLOAD_TIMEOUT_MS).download_updates(info)
            self.state.pending = target
            log.info("Đã tải sẵn bản %s — sẽ dùng ở lần mở sau", target)
        except Exception as e:
            self.state.error = True
            log.warning("Kiểm tra/tải bản cập nhật lỗi (sẽ thử lại): %s", e)
        finally:
            self.state.downloading = None
            self._lock.release()

    def run(self):
        """Thân luồng nền: chờ CHECK_DELAY_S, rồi cứ CHECK_INTERVAL_S một lượt."""
        if self._wait(CHECK_DELAY_S):
            return
        while True:
            try:
                enabled = self._auto_check()
            except Exception:
                enabled = True
            if enabled:
                self.check_once()
            if self._wait(CHECK_INTERVAL_S):
                return

    def stop(self):
        self._stop.set()

    def apply_on_exit(self):
        """App tắt bình thường: có bản đã tải xong → Update.exe áp dụng im lặng sau khi
        tiến trình này thoát, không mở lại app. True nếu đã giao việc áp dụng."""
        try:
            mgr = self._factory(self._url, CHECK_TIMEOUT_MS)
            asset = mgr.get_update_pending_restart()
            if asset is None:
                return False
            mgr.wait_exit_then_apply_updates(asset, silent=True, restart=False)
            log.info("Sẽ áp dụng bản %s sau khi app thoát", asset.Version)
            return True
        except Exception as e:
            log.warning("Không giao được việc áp dụng bản cập nhật: %s", e)
            return False


def start_background_updates(app_dir, base_url, fingerprint, auto_check,
                             manager_factory=make_manager, start_thread=True):
    """Khởi động luồng cập nhật nền nếu đây là bản cài Velopack. Trả updater hoặc None."""
    global _updater
    from core import first_run
    if not first_run.is_velopack_install(app_dir):
        log.info("Không phải bản cài Velopack — không tự cập nhật")
        return None
    url = feed_url(base_url, fingerprint)
    if url is None:
        log.warning("Thiếu license_server_url hoặc mã máy không hợp lệ — không tự cập nhật")
        return None
    _updater = BackgroundUpdater(url, auto_check, manager_factory)
    if start_thread:
        threading.Thread(target=_updater.run, daemon=True, name="velopack-update").start()
    return _updater


def get_updater():
    return _updater


def apply_pending_on_exit():
    u = _updater
    return u.apply_on_exit() if u is not None else False


def status_text(version, updater, auto_check=True):
    head = f"Đang dùng {version}"
    if updater is None:
        return f"{head} — bản này không tự cập nhật (chạy từ mã nguồn hoặc bản cài cũ)."
    s = updater.state
    if s.pending:
        return f"{head} — đã tải sẵn {s.pending}, sẽ dùng ở lần mở sau."
    if s.downloading:
        return f"{head} — đang tải bản {s.downloading}…"
    if not auto_check:
        return f"{head} — tự cập nhật đang tắt."
    if s.error:
        return f"{head} — chưa kết nối được máy chủ cập nhật, sẽ thử lại sau."
    if s.checked_at is not None:
        when = time.strftime("%H:%M %d/%m", time.localtime(s.checked_at))
        return f"{head} — đã là bản mới nhất (kiểm lúc {when})."
    return f"{head} — sẽ kiểm tra bản mới khoảng 1 phút sau khi mở app."
