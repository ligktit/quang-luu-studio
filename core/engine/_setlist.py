"""
core.engine._setlist — SetlistController (Live Setlist / Auto-Pilot)

Controller logic THUẦN (không phụ thuộc Qt) cho tính năng Premium "Live Setlist":
giữ một hàng đợi bài hát (theo thứ tự playlist), con trỏ bài hiện tại/kế tiếp, và
PREFETCH tone của bài kế trong nền (thread) để khi chuyển bài đã có tone sẵn trong
ToneCacheManager.

Thiết kế tách rời (decoupling):
  * Controller KHÔNG import SystemEngine / engine internals. Hàm dò tone được
    INJECT qua ``detect_fn(url, on_done=None)`` để controller không cứng phụ thuộc
    vào pipeline dò tone cụ thể nào. Integrator (frontend) hoặc
    ``SystemEngine.make_setlist`` nối ``detect_fn`` vào hàm dò tone 1-URL hiện có
    (xem docs/integration/phase5_setlist.md).
  * Kiểm tra "đã có tone chưa" qua ToneCacheManager (read-only) — nếu bài kế đã
    nằm trong cache (hoặc có timeline thủ công) thì BỎ QUA prefetch, không tốn
    mạng/CPU.

Fail-soft: mọi lỗi prefetch đều nuốt (log) — không bao giờ làm hỏng luồng live.
Thread-safe: con trỏ bảo vệ bằng lock; prefetch chạy ở daemon thread, chống
trùng (không prefetch cùng 1 URL 2 lần đồng thời).
"""
import logging
import threading

from core.tone_cache import ToneCacheManager, ManualToneTimeline

_log = logging.getLogger(__name__)


def _song_url(song):
    """Lấy URL từ 1 song dict (tương thích vài khóa tên)."""
    if not isinstance(song, dict):
        return ""
    return song.get("url") or song.get("youtube_url") or ""


def tone_already_cached(url):
    """True nếu URL đã có tone sẵn (cache auto HOẶC timeline thủ công).

    Đây là điều kiện để BỎ QUA prefetch. Read-only, fail-soft → mọi lỗi coi như
    "chưa có" (an toàn: cùng lắm prefetch thừa, không bao giờ chặn).
    """
    if not url:
        return False
    try:
        manual = ManualToneTimeline.load_timeline(url)
        if manual and manual.get("timeline"):
            return True
    except Exception:
        pass
    try:
        cached = ToneCacheManager.get_cached_tone(url)
        if cached and cached.get("key_timeline"):
            return True
    except Exception:
        pass
    return False


class SetlistController:
    """Hàng đợi bài cho buổi live + prefetch tone bài kế.

    songs: list[dict] theo thứ tự phát (mỗi dict tối thiểu có 'url'; thường có
           thêm 'title', 'tone', 'id', 'preset'...).
    """

    def __init__(self, songs=None):
        self._lock = threading.RLock()
        self._songs = [s for s in (songs or []) if isinstance(s, dict)]
        # Con trỏ bài hiện tại. -1 = chưa bắt đầu (chưa phát bài nào).
        self._index = -1
        # Theo dõi URL đang prefetch để không chạy trùng 2 thread cho cùng 1 bài.
        self._prefetching = set()
        self._prefetch_lock = threading.Lock()

    # ── Trạng thái hàng đợi ──────────────────────────────────────────────────

    def __len__(self):
        with self._lock:
            return len(self._songs)

    @property
    def songs(self):
        """Bản sao danh sách bài (an toàn cho UI duyệt)."""
        with self._lock:
            return list(self._songs)

    @property
    def index(self):
        with self._lock:
            return self._index

    def current(self):
        """Bài đang phát (dict) hoặc None nếu chưa bắt đầu / hàng đợi rỗng."""
        with self._lock:
            if 0 <= self._index < len(self._songs):
                return self._songs[self._index]
            return None

    def peek_next(self):
        """Bài KẾ TIẾP (không di chuyển con trỏ) hoặc None nếu đã hết."""
        with self._lock:
            nxt = self._index + 1
            if 0 <= nxt < len(self._songs):
                return self._songs[nxt]
            return None

    def has_next(self):
        with self._lock:
            return (self._index + 1) < len(self._songs)

    def advance(self):
        """Di chuyển con trỏ sang bài kế và trả về bài đó (hoặc None nếu hết).

        Lần gọi đầu (index == -1) sẽ trả về bài đầu tiên.
        """
        with self._lock:
            if (self._index + 1) < len(self._songs):
                self._index += 1
                return self._songs[self._index]
            return None

    def reset(self):
        """Đưa con trỏ về trạng thái chưa bắt đầu."""
        with self._lock:
            self._index = -1

    def set_songs(self, songs):
        """Thay danh sách bài (vd. khi đổi playlist) — reset con trỏ."""
        with self._lock:
            self._songs = [s for s in (songs or []) if isinstance(s, dict)]
            self._index = -1

    # ── Prefetch tone bài kế ─────────────────────────────────────────────────

    def prefetch_next(self, detect_fn, on_done=None):
        """Dò tone bài KẾ TIẾP trong nền nếu chưa có trong cache.

        detect_fn(url, on_done=callable|None): hàm dò tone 1-URL được inject. Nó
            có thể chạy đồng bộ hoặc tự spawn thread; controller chỉ bao thêm 1
            lớp daemon thread để chắc chắn không chặn caller. detect_fn nên ghi
            kết quả vào ToneCacheManager (các hàm dò tone của engine đã làm vậy).
        on_done(url, was_cached): callback tùy chọn khi xong (đã có tone hoặc dò
            xong). was_cached=True nếu bỏ qua vì đã có sẵn.

        Trả về True nếu đã KHỞI ĐỘNG prefetch (hoặc xác nhận đã cache), False nếu
        không có bài kế / không có URL.
        """
        nxt = self.peek_next()
        if not nxt:
            return False
        url = _song_url(nxt)
        if not url:
            return False

        # Đã có tone sẵn → không cần dò lại.
        if tone_already_cached(url):
            if on_done:
                try:
                    on_done(url, True)
                except Exception:
                    pass
            return True

        if detect_fn is None:
            _log.warning("[SETLIST] prefetch_next: detect_fn=None, bỏ qua URL %s", url)
            return False

        # Chống prefetch trùng cùng 1 URL.
        with self._prefetch_lock:
            if url in self._prefetching:
                return True
            self._prefetching.add(url)

        def _run():
            try:
                done_evt = threading.Event()

                def _inner_done(*_a, **_k):
                    done_evt.set()

                try:
                    # detect_fn nhận on_done nếu hỗ trợ; nếu không thì gọi trơn.
                    detect_fn(url, on_done=_inner_done)
                except TypeError:
                    detect_fn(url)
                    done_evt.set()
            except Exception as e:  # fail-soft tuyệt đối
                _log.warning("[SETLIST] prefetch tone thất bại cho %s: %s", url, e)
            finally:
                with self._prefetch_lock:
                    self._prefetching.discard(url)
                if on_done:
                    try:
                        on_done(url, False)
                    except Exception:
                        pass

        threading.Thread(target=_run, name="setlist-prefetch", daemon=True).start()
        return True

    def is_prefetching(self, url=None):
        """True nếu đang prefetch URL cho trước (hoặc bất kỳ nếu url=None)."""
        with self._prefetch_lock:
            if url is None:
                return bool(self._prefetching)
            return url in self._prefetching
