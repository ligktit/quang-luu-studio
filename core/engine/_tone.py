"""Tone detection pipeline for SystemEngine."""
import gc
import sys
import time
import threading
import traceback
import numpy as np

from core import tone_cache as tone_cache_module
from core import ytdlp_support
from core.memory import MemoryGuard
from core.numba_cache import run_healing
from core.tone_cache import ToneCacheManager, ManualToneTimeline
from core.tone_detector import ToneDetector
from core.utils import song_match_key
from core.scoring import ScoringEngine
from core.ytdlp_support import extract_info_with_auth, make_ydl_opts
from core.engine._youtube import _extract_key_root

# Camelot wheel
_CAMELOT_MAJOR = ["8B", "3B", "10B", "5B", "12B", "7B", "2B", "9B", "4B", "11B", "6B", "1B"]
_CAMELOT_MINOR = ["5A", "12A", "7A", "2A", "9A", "4A", "11A", "6A", "1A", "8A", "3A", "10A"]

# Hard deadlines for the detection pipeline. If the worker thread does not
# return within these windows, the watchdog fires on_error so the UI can
# recover instead of displaying "Đang dò..." forever. Fast scan is capped
# tighter because it only downloads 45s of audio.
#
# 60s / 240s (trước: 90s / 300s). Lượt dò nhanh khoẻ mạnh mất 5–15s, tải chỉ ~2s;
# mọi tầng dưới giờ đều có hạn riêng (mạng 10s/thao tác, ffmpeg -rw_timeout, nghe
# loa tối đa thời lượng + 5s) nên hạn tổng không cần rộng như trước.
_FAST_SCAN_TIMEOUT_SEC = 60
_FULL_SCAN_TIMEOUT_SEC = 240

# Thời lượng thu loopback (giây) cho PHƯƠNG ÁN DỰ PHÒNG khi yt-dlp tải thất bại.
# Bài hát phải đang phát trên loa để thu được — đây là cách dò tone cho các
# video không tải được (chặn vùng miền, đăng nhập, lỗi định dạng...).
_LOOPBACK_FALLBACK_SEC = 12


# Quy ước thông báo lỗi:
#   - DEV  → _ToneJob.note_error(exc) trong luồng dò; khi on_error được gọi,
#            _ToneJob.log_failure ghi đầy đủ exception + traceback vào nhật ký.
#   - USER → on_error/on_progress với câu chữ dễ hiểu, có gợi ý xử lý;
#            TUYỆT ĐỐI không đẩy str(exc)/traceback ra giao diện.

# Thông báo chung, thân thiện cho người dùng phổ thông khi gặp lỗi không lường trước.
_USER_ERR_GENERIC = (
    "Đã xảy ra lỗi khi dò tone. Vui lòng thử lại sau giây lát; "
    "nếu vẫn lỗi, hãy khởi động lại ứng dụng."
)


class _ToneCancelled(Exception):
    """Phiên dò đã huỷ/hết giờ — ném từ on_progress để cắt ngang vòng phân tích."""


class _ToneJob:
    """Gắn MỘT lần dò tone với luồng worker của nó.

    Watchdog chỉ báo lỗi lên giao diện được, không giết được luồng Python. Trước
    đây luồng kẹt (mạng đứng, loa không đẩy dữ liệu...) cứ nằm đó mãi mà nhật ký
    không để lại dấu vết gì về chỗ kẹt. Đối tượng này:
      - PHÁT HIỆN: hết giờ thì ghi vào nhật ký ngăn xếp hiện tại của luồng worker
        (kẹt ở hàm nào, dòng nào) + luồng đó thoát muộn bao lâu sau hạn chót;
      - NGĂN CHẶN: cấp hàm cancelled() cho các tầng dưới (yt-dlp qua
        ytdlp_support.set_cancel_check, thu loa, phân tích) để dừng ở điểm kế tiếp;
      - không để luồng kẹt giữ bộ đếm phiên dò của MemoryGuard (chặn dọn RAM).
      - NHẬT KÝ LỖI: luồng đánh dấu bước (step) và ghi nhận lỗi gốc (note_error /
        note); khi on_error được gọi, log_failure ghi MỘT bản ghi ERROR đủ để chẩn
        đoán mà không cần tái hiện: chế độ, URL, bước lỗi, dòng thời gian các
        bước, câu báo khách, lỗi gốc + chuỗi nguyên nhân + traceback.
    """

    def __init__(self, label, timeout_sec, watchdog_cancel):
        self.label = label
        self.timeout_sec = timeout_sec
        self.url = None
        self.stage = "khoi dong"
        self._steps = []        # [(tên bước, giây kể từ lúc bắt đầu)]
        self._errors = []       # lỗi gốc (exception) đã ghi nhận
        self._notes = []        # chi tiết dạng chữ (lý do nghe loa hỏng...)
        self._watchdog_cancel = watchdog_cancel
        self._session_cancel = None
        self._thread_id = None
        self._started = None
        self._counted = False   # đã tăng bộ đếm phiên dò của MemoryGuard chưa
        self._released = False
        self._lock = threading.Lock()

    # ── Nhật ký ──────────────────────────────────────────────────────────────

    def _elapsed(self):
        return time.monotonic() - self._started if self._started is not None else 0.0

    def step(self, name):
        """Đánh dấu luồng bắt đầu một bước mới."""
        self.stage = name
        self._steps.append((name, self._elapsed()))

    def note_error(self, exc):
        """Ghi nhận lỗi gốc (kể cả lỗi đã được xử lý / chuyển sang dự phòng)."""
        if isinstance(exc, BaseException) and all(e is not exc for e in self._errors):
            self._errors.append(exc)

    def note(self, text):
        if text:
            self._notes.append(str(text))

    def _describe(self, outcome, reason=None, stuck_stack=None):
        lines = [
            f"[DÒ TONE] {outcome} — {self.label}",
            f"  URL: {self.url or '(chua xac dinh)'}",
            f"  Buoc cuoi: {self.stage} (sau {self._elapsed():.1f}s)",
            "  Cac buoc: " + (" -> ".join(f"{n} @{t:.1f}s" for n, t in self._steps)
                              or "(chua co)"),
        ]
        if reason:
            lines.append(f"  Bao khach: {reason}")
        for text in self._notes:
            lines.append(f"  Chi tiet: {text}")
        for i, exc in enumerate(self._errors, 1):
            lines.append(f"  Loi goc #{i}: {type(exc).__name__}: {exc}")
            cause = exc.__cause__ or exc.__context__
            depth = 0
            while cause is not None and depth < 5:
                lines.append(f"    <- do {type(cause).__name__}: {cause}")
                cause = cause.__cause__ or cause.__context__
                depth += 1
            tb = "".join(traceback.format_exception(exc)).rstrip()
            lines.extend("    | " + ln for ln in tb.splitlines())
        if stuck_stack is not None:
            lines.append("  Luong worker dang ket tai:")
            lines.extend("    | " + ln for ln in stuck_stack.rstrip().splitlines())
        return "\n".join(lines)

    def log_failure(self, reason):
        """MỘT bản ghi ERROR cho mỗi lần dò thất bại (vào cả errors.log)."""
        _log_error(self._describe("THAT BAI", reason))

    def log_success(self):
        _log_info("[DÒ TONE] XONG — %s | %s | %.1fs | %s", self.label,
                  self.url or "-", self._elapsed(),
                  " -> ".join(f"{n} @{t:.1f}s" for n, t in self._steps) or "-")

    # Gọi ở ĐẦU luồng worker.
    def attach(self):
        self._thread_id = threading.get_ident()
        self._started = time.monotonic()
        # Cùng khoá với _release: watchdog bắn đúng lúc này thì hoặc chưa đếm
        # (không trừ), hoặc đã đếm (trừ đúng một lần) — không bao giờ lệch.
        with self._lock:
            if not self._released:
                MemoryGuard.begin_tone_job()
                self._counted = True
        ytdlp_support.set_cancel_check(self.cancelled)

    def watch(self, cancel):
        """Gắn cancel của phiên (tone_session) khi luồng đã có nó."""
        self._session_cancel = cancel

    def cancelled(self):
        return _cancelled(self._session_cancel, self._watchdog_cancel)

    def progress(self, on_progress):
        """Bọc on_progress: phiên đã huỷ thì ném _ToneCancelled để dừng vòng lặp
        phân tích dài (timeline toàn bài) ngay ở lần báo tiến độ kế tiếp."""
        def _wrapped(*args, **kwargs):
            if self.cancelled():
                raise _ToneCancelled()
            if on_progress:
                on_progress(*args, **kwargs)
        return _wrapped

    def _release(self):
        with self._lock:
            if self._released:
                return
            self._released = True
            # Chưa đếm thì không trừ — trừ là trừ nhầm phiên khác.
            if not self._counted:
                return
        MemoryGuard.end_tone_job()

    # Gọi trong finally của luồng worker.
    def detach(self):
        if self._thread_id == threading.get_ident():
            ytdlp_support.set_cancel_check(None)
        if self._watchdog_cancel.is_set() and self._started is not None:
            _log_warning("[WATCHDOG] %s: luong worker thoat muon, %.1fs sau khi bat dau "
                         "(han %ds)", self.label, time.monotonic() - self._started,
                         self.timeout_sec)
        self._release()

    def report_hang(self, reason=None):
        """Watchdog hết giờ: ghi luồng worker đang kẹt ở đâu, rồi nhả phiên RAM."""
        frame = sys._current_frames().get(self._thread_id) if self._thread_id else None
        if frame is None:
            where = "(luong worker chua chay hoac da ket thuc)"
        else:
            where = "".join(traceback.format_stack(frame))
        _log_error(self._describe(f"QUA GIO {self.timeout_sec}s", reason,
                                  stuck_stack=where))
        self._release()


def _log_at(level, msg, *args):
    try:
        import logging
        logging.getLogger(__name__).log(level, msg, *args)
    except Exception:
        pass


def _log_warning(msg, *args):
    import logging
    _log_at(logging.WARNING, msg, *args)


def _log_error(msg, *args):
    import logging
    _log_at(logging.ERROR, msg, *args)


def _log_info(msg, *args):
    import logging
    _log_at(logging.INFO, msg, *args)


def _install_watchdog(timeout_sec, on_complete, on_error, label, on_timeout_hook=None):
    """Wrap detection callbacks with a once-only timeout guard.

    Returns (safe_complete, safe_error, cancel_event, job). When the deadline fires,
    `on_timeout_hook` (if provided) is invoked so the worker thread can stop
    cleanly via the session state machine, and `job` logs where the worker is
    stuck. Both callbacks are idempotent. The worker must call job.attach() first
    and job.detach() in its finally.
    """
    done = threading.Event()
    watchdog_cancel = threading.Event()
    job = _ToneJob(label, timeout_sec, watchdog_cancel)

    def _safe_complete(result):
        if done.is_set():
            return
        done.set()
        timer.cancel()
        try:
            job.log_success()
        except Exception:
            pass
        if on_complete:
            on_complete(result)

    def _safe_error(msg):
        if done.is_set():
            return
        done.set()
        timer.cancel()
        try:
            job.log_failure(msg)
        except Exception:
            pass
        if on_error:
            on_error(msg)

    def _fire_timeout():
        if done.is_set():
            return
        done.set()
        watchdog_cancel.set()
        # Log via stderr-safe ASCII to avoid UnicodeEncodeError on cp1252 consoles
        # which would crash the Timer thread before on_error fires.
        try:
            import logging
            logging.getLogger(__name__).warning(
                "[WATCHDOG] %s timeout after %ds", label, timeout_sec
            )
        except Exception:
            pass
        timeout_msg = (
            f"Dò tone quá lâu (quá {timeout_sec}s khi {label}) nên đã dừng. "
            "Thử bấm Dò Lại; nếu video bị chặn, app sẽ tự nghe từ loa."
        )
        try:
            job.report_hang(timeout_msg)
        except Exception:
            pass
        if on_timeout_hook:
            try:
                on_timeout_hook()
            except Exception:
                pass
        if on_error:
            try:
                on_error(timeout_msg)
            except Exception:
                pass

    timer = threading.Timer(timeout_sec, _fire_timeout)
    timer.daemon = True
    timer.start()
    return _safe_complete, _safe_error, watchdog_cancel, job


def _cancelled(cancel, watchdog_cancel=None):
    """True nếu phiên bị hủy (session cancel) HOẶC watchdog đã timeout.

    Trước đây watchdog_cancel gần như là dead code: khi timeout, on_timeout_hook
    gọi _tone_session.stop() — việc này set SESSION cancel nên worker vẫn dừng ở
    điểm poll kế. Nhưng nếu UI/luồng khác mở phiên MỚI ngay sau timeout (state về
    SCANNING với cancel event khác), session cancel của phiên cũ không còn được
    set, worker cũ có thể chạy tiếp tới các bước side-effect (gửi MIDI / ghi cache)
    SAU KHI UI đã báo timeout. watchdog_cancel là cờ RIÊNG của phiên này nên một
    khi đã timeout sẽ mãi True → kết hợp ở đây để worker dừng dứt khoát, không phụ
    thuộc việc session cancel có bị "tái sử dụng" hay không.
    """
    if cancel is not None and cancel.is_set():
        return True
    if watchdog_cancel is not None and watchdog_cancel.is_set():
        return True
    return False


class _ToneMixin:
    # ── DRY Helpers ──────────────────────────────────────────────────────────────

    def _tone_resolve_cache_lock_obj(self):
        """Trả về lock bảo vệ _tone_resolve_cache.

        Dùng getattr-default để an toàn với các instance được tạo trước khi
        __init__ thêm lock (vd. test cũ build engine kiểu khác) — không có lock
        thì rơi về một RLock dùng-một-lần (vẫn đúng, chỉ không chia sẻ).
        """
        lock = getattr(self, "_tone_resolve_cache_lock", None)
        if lock is None:
            lock = threading.Lock()
            self._tone_resolve_cache_lock = lock
        return lock

    def _resolve_tone(self, url):
        # In-session memoization: check RAM cache first (dưới khóa).
        cache_key = song_match_key(url)
        with self._tone_resolve_cache_lock_obj():
            self._tone_resolve_cache_sync_gen()
            if cache_key in self._tone_resolve_cache:
                self._tone_resolve_cache.move_to_end(cache_key)
                source, data = self._tone_resolve_cache[cache_key]
                print(f"[RESOLVE] Cache phiên: {source}")
                return (source, data)

        saved_manual = ManualToneTimeline.load_timeline(url)
        if saved_manual and saved_manual.get('timeline'):
            print(f"[RESOLVE] Khớp timeline thủ công: {len(saved_manual['timeline'])} đoạn")
            self._tone_resolve_cache_put(url, ('manual', saved_manual))
            return ('manual', saved_manual)

        cached = ToneCacheManager.get_cached_tone(url)
        if cached and cached.get('key_timeline'):
            print(f"[RESOLVE] Khớp bộ nhớ đệm: {cached.get('primary_key', '?')}")
            self._tone_resolve_cache_put(url, ('cache', cached))
            return ('cache', cached)

        # Tone người dùng đã lưu ở Danh sách bài hát (saved_songs.json → "tone").
        # Đứng SAU tone_cache (cache mới hơn và có cả timeline nhiều đoạn) nhưng
        # TRƯỚC thư viện cộng đồng (dữ liệu của chính khách thắng dữ liệu người
        # lạ) và tất nhiên trước việc dò lại từ đầu.
        saved_song = self._saved_song_tone(url)
        if saved_song:
            print(f"[RESOLVE] Khớp tone bài đã lưu: {saved_song['timeline'][0]['key_display']}")
            self._tone_resolve_cache_put(url, ('manual', saved_song))
            return ('manual', saved_song)

        # Local trượt → hỏi thư viện tone cộng đồng. Trả về dưới nhãn 'cache'
        # (chứ không phải một nguồn thứ ba) vì tone_share đã ghi kết quả xuống
        # tone_cache local rồi — với engine thì đây ĐÚNG là một cú trúng cache,
        # và _build_cache_result xử lý sẵn đúng hình dạng dữ liệu này.
        #
        # An toàn về thread: cả ba nơi gọi _resolve_tone đều nằm trong worker
        # dò tone, không phải UI thread. Mất mạng thì tone_share trả None sau
        # tối đa 10s và luồng dò cũ chạy tiếp như chưa có gì.
        shared = self._lookup_shared_tone(url)
        if shared and shared.get('key_timeline'):
            print(f"[RESOLVE] Lấy từ thư viện cộng đồng: {shared.get('primary_key', '?')}")
            self._tone_resolve_cache_put(url, ('cache', shared))
            return ('cache', shared)

        return (None, None)

    @staticmethod
    def _saved_song_tone(url):
        """Tone bài đã lưu (Danh sách bài hát) dạng timeline 1 mốc, hoặc None."""
        return tone_cache_module.song_tone_entry(url)

    @staticmethod
    def _lookup_shared_tone(url):
        """Tra thư viện tone cộng đồng. Không bao giờ ném lỗi ra luồng dò tone."""
        try:
            from core import tone_share
            return tone_share.lookup(url)
        except Exception as e:
            print(f"[RESOLVE] Bỏ qua thư viện cộng đồng: {e}")
            return None

    @staticmethod
    def _share_tone(url, title, cache_data, source='auto', diag=None):
        """Đóng góp kết quả vừa dò cho mạng lưới. Xếp hàng + gửi nền, không chặn.

        diag: số đo kỹ thuật của lượt dò (xem _detection_diag) — server lưu riêng
        cho dev chấm thuật toán, không hiển thị ở đâu cho khách.
        """
        try:
            from core import tone_share
            tone_share.contribute(url, title, cache_data, source=source, diag=diag)
        except Exception as e:
            print(f"[SHARE] Không đóng góp được tone: {e}")

    @staticmethod
    def _detection_diag(mode, audio, entries, primary_key):
        """Số đo của một lượt máy dò: độ tin cậy của tone chính + tuning.

        mode: 'nhanh' | 'toan-bai'; audio: 'youtube' | 'loa'.
        """
        entries = entries or []
        main = next((e for e in entries if e.get('key_display') == primary_key),
                    entries[0] if entries else {})
        tuning = next((e.get('tuning_cents') for e in entries
                       if e.get('tuning_cents') is not None), None)
        return {
            'mode':         mode,
            'audio':        audio or '',
            'confidence':   main.get('confidence'),
            'tuning_cents': tuning,
        }

    def _tone_resolve_cache_sync_gen(self):
        """Bỏ sạch đệm phiên nếu dữ liệu tone trên đĩa đã đổi từ lần đọc trước.

        Gọi khi ĐANG GIỮ _tone_resolve_cache_lock. Đây là chốt chặn cho mọi
        đường ghi dữ liệu (dialog sửa chuỗi tone, sửa thông tin bài, tools chạy
        song song…) — không phụ thuộc việc từng call site có nhớ gọi
        _tone_resolve_cache_invalidate hay không.
        """
        gen = tone_cache_module.data_version()
        if getattr(self, "_tone_resolve_cache_gen", None) != gen:
            if self._tone_resolve_cache:
                print("[RESOLVE] Dữ liệu tone đã đổi → bỏ đệm phiên")
            self._tone_resolve_cache.clear()
            self._tone_resolve_cache_gen = gen

    def _tone_resolve_cache_put(self, url, entry):
        """Insert into in-session cache, evicting oldest if over max size.

        Khóa theo song_match_key (video_id) chứ không phải chuỗi URL thô: cùng
        một bài mở bằng link chia sẻ (youtu.be/…?si=), link có &list=… hay link
        chuẩn đều phải trúng CÙNG một entry, đúng như tầng đĩa.
        """
        key = song_match_key(url)
        with self._tone_resolve_cache_lock_obj():
            self._tone_resolve_cache_sync_gen()
            self._tone_resolve_cache[key] = entry
            self._tone_resolve_cache.move_to_end(key)
            while len(self._tone_resolve_cache) > self._TONE_RESOLVE_CACHE_MAX:
                self._tone_resolve_cache.popitem(last=False)

    def _tone_resolve_cache_invalidate(self, url):
        """Remove a URL from the in-session cache (called after save)."""
        with self._tone_resolve_cache_lock_obj():
            self._tone_resolve_cache.pop(song_match_key(url), None)

    def _build_cache_result(self, cached):
        """Build a flat result dict from already-loaded cache data + send MIDI.
        Replaces the old _check_tone_cache which re-read JSON from disk."""
        timeline = cached.get('key_timeline', [])
        if not timeline:
            return None

        latest      = timeline[-1]
        key_display = cached.get('primary_key', latest.get('key_display', 'C'))
        # Lấy entry KHỚP với key_display đang hiển thị (primary_key) để key_index/
        # scale gửi MIDI đúng với key người dùng thấy — không lấy đại entry cuối
        # timeline (đoạn cuối bài có thể đã chuyển sang tone khác).
        match = next(
            (e for e in timeline if e.get('key_display') == key_display),
            latest,
        )
        result = {
            'key_display': key_display,
            'key':         _extract_key_root(key_display),   # root note cho UI dropdown
            'key_index':   match.get('key_index', 0),
            'scale':       match.get('scale', 'Major'),
            'confidence':  match.get('confidence', 0),
            'from_cache':  True,
            'key_timeline': timeline,
            'title':       cached.get('title', ''),
        }
        self._send_tone_midi(result)
        return result


    def _save_tone_to_cache(self, url, result, title=""):
        cache_data = {
            'primary_key': result['key_display'],
            'title': title,
            'key_timeline': [{
                'time':        0,
                'key_display': result['key_display'],
                'key_index':   result['key_index'],
                'scale':       result['scale'],
                'confidence':  result.get('confidence', 0),
                'bpm':         result.get('bpm', 0),
                'duration':    result.get('duration', 0),
            }]
        }
        ToneCacheManager.save_tone(url, cache_data)
        self._share_tone(url, title, cache_data, diag={
            # nhanh-mo-rong: 45s đầu kém tự tin nên đã tự dò thêm (detect_key_from_file)
            'mode':         'nhanh-mo-rong' if result.get('extended_seconds') else 'nhanh',
            'audio':        result.get('audio_source', ''),
            'confidence':   result.get('confidence'),
            'tuning_cents': result.get('tuning_cents'),
        })
        # Invalidate in-session cache so next resolve re-reads fresh data
        self._tone_resolve_cache_invalidate(url)

    @staticmethod
    def _representative_primary_key(timeline_entries):
        """Chọn tone 'tiêu biểu' của bài = key_display chiếm NHIỀU thời lượng nhất.

        Mỗi entry có 'time' (giây bắt đầu đoạn). Thời lượng đoạn = time đoạn sau
        trừ time đoạn này; đoạn cuối tính bằng thời lượng trung bình các đoạn
        trước (hoặc 1 nếu chỉ có 1 đoạn) để không bị bỏ qua. Tránh thiên vị
        đoạn intro (entry[0]) như cách lấy timeline_entries[0] trước đây.
        """
        if not timeline_entries:
            return 'C'
        if len(timeline_entries) == 1:
            return timeline_entries[0].get('key_display', 'C')

        times     = [float(e.get('time', 0) or 0) for e in timeline_entries]
        durations = []
        for i in range(len(timeline_entries) - 1):
            durations.append(max(0.0, times[i + 1] - times[i]))
        # Đoạn cuối: dùng thời lượng trung bình các đoạn trước làm ước lượng.
        avg_prev = (sum(durations) / len(durations)) if durations else 1.0
        durations.append(avg_prev if avg_prev > 0 else 1.0)

        totals = {}
        order  = {}  # giữ thứ tự xuất hiện đầu tiên để phá hòa ổn định
        for idx, (entry, dur) in enumerate(zip(timeline_entries, durations)):
            kd = entry.get('key_display', 'C')
            totals[kd] = totals.get(kd, 0.0) + dur
            order.setdefault(kd, idx)
        # Tổng thời lượng lớn nhất; hòa thì ưu tiên key xuất hiện sớm hơn.
        return max(totals, key=lambda kd: (totals[kd], -order[kd]))

    @staticmethod
    def _extract_key_root(key_display):
        return _extract_key_root(key_display)

    # ── Loopback fallback (yt-dlp tải thất bại) ──────────────────────────────────

    def _loopback_fallback_detect(self, on_progress=None, cancel=None,
                                  duration=_LOOPBACK_FALLBACK_SEC, reason_out=None,
                                  cancelled=None):
        """Dò tone bằng cách NGHE TRỰC TIẾP âm thanh đang phát trên loa.

        Dùng làm phương án dự phòng khi yt-dlp KHÔNG tải được audio (video bị
        chặn, cần đăng nhập, lỗi định dạng...). Chỉ hiệu quả khi bài hát đang
        thực sự phát. Trả về result dict (đánh dấu ``from_loopback``) hoặc None.

        ``reason_out``: list (tùy chọn) — khi thất bại sẽ chứa câu mô tả nguyên nhân.
        ``cancelled``: hàm kiểm tra huỷ (gồm cả watchdog); mặc định chỉ xét ``cancel``.
        """
        if cancel is not None and cancel.is_set():
            return None
        if on_progress:
            on_progress(f"⚠️ Không tải được YouTube — đang nghe trực tiếp từ loa ({duration}s)…")
        print("[DÒ TONE] yt-dlp thất bại → chuyển sang thu loopback từ loa")

        def _cap_progress(remaining):
            if on_progress:
                try:
                    on_progress(f"Đang nghe từ loa… còn {remaining}s")
                except Exception:
                    pass

        if cancel is not None and cancel.is_set():
            return None
        if cancelled is None and cancel is not None:
            cancelled = cancel.is_set
        result = ToneDetector.detect_key_from_system_audio(
            duration=duration, on_progress=_cap_progress, reason_out=reason_out,
            cancelled=cancelled,
        )
        if result:
            result['from_loopback'] = True
        return result

    def _current_media_title(self):
        """Best-effort: tên bài đang phát từ media monitor (cho fallback loopback)."""
        try:
            return self.media_monitor.current_title or ''
        except Exception:
            return ''

    def _send_tone_midi(self, result):
        from core.config import AppConfig

        if getattr(self, 'key_locked', False) is True:
            print(f"[MIDI] Bỏ qua tone {result.get('key_display', '?')} — tone đang chốt tay")
            return

        key_index = result.get('key_index', 0)
        scale     = result.get('scale', 'Major')

        key_map   = AppConfig.get_key_midi_map()
        scale_map = AppConfig.get_scale_midi_map()
        midi_cc   = AppConfig.get_midi_cc()

        # Key
        key_names  = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        if 0 <= key_index < 12:
            # Nhạc đang dịch N bán cung (Tone Nhạc) → tone thật đang vang cũng dịch N.
            try:
                transpose = int(getattr(self, 'tone_transpose', 0) or 0)
            except (TypeError, ValueError):
                transpose = 0
            key_name = key_names[(key_index + transpose) % 12]
        else:
            key_name = 'C'
        key_cc_val = key_map.get(key_name, 0)

        # Scale
        scale_cc_val = scale_map.get(scale, scale_map.get('Major', 13))

        # Send via MIDI CCs
        tone_cc  = midi_cc.get('key_root', 33)
        scale_cc = midi_cc.get('scale_type', midi_cc.get('key_scale', 35))

        # Gửi NGUYÊN TỬ cặp key_root + scale_type để không thread nào chen vào
        # giữa, tránh tình huống Live nhận key mới với scale cũ (hoặc ngược lại).
        self.send_midi_pair(tone_cc, key_cc_val, scale_cc, scale_cc_val)

        print(f"[MIDI] Key={key_name} (cc={tone_cc}, val={key_cc_val}) "
              f"Scale={scale} (cc={scale_cc}, val={scale_cc_val})")

    # ── Detect from system audio ────────────────────────────────────────────────

    def detect_tone(self, duration=10, on_complete=None, on_error=None, on_progress=None):
        on_complete, on_error, watchdog_cancel, job = _install_watchdog(
            _FAST_SCAN_TIMEOUT_SEC, on_complete, on_error,
            label="dò tone từ loa",
            on_timeout_hook=lambda: self._tone_session.stop(),
        )

        # Snapshot field dùng chung MỘT LẦN: thread khác có thể đổi
        # current_youtube_url giữa chừng → nếu re-read, có thể dò URL này nhưng
        # cache vào URL kia. Dùng biến local nhất quán xuyên suốt worker.
        youtube_url = self.current_youtube_url

        # Đi qua session để chống bấm chồng: start_scanning() hủy phiên cũ
        # (set cancel của nó) và cấp token mới cho phiên này.
        cancel = self._tone_session.start_scanning(youtube_url or "")
        job.watch(cancel)
        job.url = youtube_url

        def _detect():
            job.attach()
            try:
                if youtube_url:
                    job.step("tra cache")
                    source, resolved_data = self._resolve_tone(youtube_url)
                    if source == 'manual':
                        timeline = resolved_data['timeline']
                        first    = timeline[0]
                        kd       = first.get('key_display', 'C')
                        result   = {
                            'key_display': kd,
                            'key':         _extract_key_root(kd),
                            'key_index':   first.get('key_index', 0),
                            'scale':       first.get('scale', 'Major'),
                            'confidence':  first.get('confidence', 0),
                            'from_manual': True,
                            'title':       resolved_data.get('title', ''),
                        }
                        self._send_tone_midi(result)
                        if on_complete:
                            on_complete(result)
                        return
                    elif source == 'cache':
                        cached_result = self._build_cache_result(resolved_data)
                        if cached_result:
                            if on_complete:
                                on_complete(cached_result)
                            return

                if _cancelled(cancel, watchdog_cancel):
                    return

                result = None
                if youtube_url:
                    print("[DÒ TONE] Dùng YouTube audio...")
                    job.step("tai + phan tich YouTube")
                    _yt_errors = []
                    try:
                        result = ToneDetector.detect_key_from_youtube(
                            youtube_url, duration_limit=30, errors_out=_yt_errors
                        )
                    except Exception as e:
                        print(f"[DÒ TONE] YouTube download thất bại: {e}")
                        _yt_errors.append(e)
                    for _e in _yt_errors:
                        job.note_error(_e)

                if _cancelled(cancel, watchdog_cancel):
                    return

                if not result:
                    job.step("nghe loa")
                    _reasons = []
                    result = ToneDetector.detect_key_from_system_audio(
                        duration=duration, on_progress=on_progress,
                        cancelled=job.cancelled, reason_out=_reasons,
                    )
                    for _r in _reasons:
                        job.note(f"Nghe loa: {_r}")

                # Kiểm tra timeout/cancel TRƯỚC mọi side-effect (gửi MIDI / ghi
                # cache): nếu UI đã báo timeout thì không gửi MIDI/ghi cache muộn.
                if _cancelled(cancel, watchdog_cancel):
                    return

                if result:
                    self._send_tone_midi(result)
                    if youtube_url:
                        self._save_tone_to_cache(youtube_url, result)
                    if on_complete:
                        on_complete(result)
                else:
                    if on_error:
                        on_error("Không thể dò tone. Hãy đảm bảo đang phát nhạc.")
            except Exception as e:
                job.note_error(e)
                if on_error:
                    on_error(_USER_ERR_GENERIC)
            finally:
                job.detach()
                if self._tone_session.is_scanning:
                    self._tone_session.stop()

        threading.Thread(target=_detect, daemon=True).start()

    # ── Detect from YouTube URL ─────────────────────────────────────────────────

    def detect_tone_from_youtube(self, url=None, on_complete=None, on_error=None, on_progress=None):
        youtube_url = url or self.current_youtube_url
        if not youtube_url:
            if on_error:
                on_error("Không có YouTube URL để dò tone.")
            return

        on_complete, on_error, watchdog_cancel, job = _install_watchdog(
            _FAST_SCAN_TIMEOUT_SEC, on_complete, on_error,
            label="dò tone từ YouTube",
            on_timeout_hook=lambda: self._tone_session.stop(),
        )

        # Đi qua session để chống bấm chồng (hủy phiên cũ + cấp token mới).
        cancel = self._tone_session.start_scanning(youtube_url)
        job.watch(cancel)
        job.url = youtube_url

        def _detect():
            job.attach()
            try:
                job.step("tra cache")
                if on_progress:
                    on_progress("Đang kiểm tra cache...")

                source, resolved_data = self._resolve_tone(youtube_url)
                if source == 'manual':
                    timeline = resolved_data['timeline']
                    first    = timeline[0]
                    kd       = first.get('key_display', 'C')
                    result   = {
                        'key_display': kd,
                        'key':         _extract_key_root(kd),
                        'key_index':   first.get('key_index', 0),
                        'scale':       first.get('scale', 'Major'),
                        'confidence':  first.get('confidence', 0),
                        'from_manual': True,
                        'title':       resolved_data.get('title', ''),
                    }
                    self._send_tone_midi(result)
                    if on_complete:
                        on_complete(result)
                    return
                elif source == 'cache':
                    cached_result = self._build_cache_result(resolved_data)
                    if cached_result:
                        if on_complete:
                            on_complete(cached_result)
                        return

                if _cancelled(cancel, watchdog_cancel):
                    return

                if on_progress:
                    on_progress("Đang tải audio từ YouTube...")

                job.step("tai + phan tich YouTube")
                _yt_errors = []
                result = ToneDetector.detect_key_from_youtube(
                    youtube_url, duration_limit=30, errors_out=_yt_errors)
                for _e in _yt_errors:
                    job.note_error(_e)

                # Kiểm tra timeout/cancel TRƯỚC side-effect (gửi MIDI / ghi cache).
                if _cancelled(cancel, watchdog_cancel):
                    return

                if result:
                    self._send_tone_midi(result)
                    self._save_tone_to_cache(youtube_url, result)
                    if on_complete:
                        on_complete(result)
                else:
                    if on_error:
                        on_error("Không thể dò tone từ YouTube. Hãy thử lại.")
            except Exception as e:
                job.note_error(e)
                if on_error:
                    on_error(_USER_ERR_GENERIC)
            finally:
                job.detach()
                if self._tone_session.is_scanning:
                    self._tone_session.stop()

        threading.Thread(target=_detect, daemon=True).start()

    # ── detect_tone_from_browser (fast scan) ────────────────────────────────────

    def detect_tone_from_browser(self, on_complete=None, on_error=None, on_progress=None,
                                  url=None, skip_resolve=False):
        on_complete, on_error, watchdog_cancel, job = _install_watchdog(
            _FAST_SCAN_TIMEOUT_SEC, on_complete, on_error,
            label="dò tone nhanh",
            on_timeout_hook=lambda: self._tone_session.stop(),
        )

        def _detect():
            job.attach()
            try:
                # 1. Xác định URL
                youtube_url = url
                if not youtube_url:
                    job.step("tim URL tren trinh duyet")
                    if on_progress:
                        on_progress("Đang tìm URL YouTube...")
                    youtube_url = self.detect_youtube_url_from_browser(quiet=True)

                if not youtube_url:
                    if on_error:
                        on_error("Không tìm thấy YouTube đang mở trên trình duyệt.")
                    return

                # 2. Bắt đầu session
                cancel = self._tone_session.start_scanning(youtube_url)
                job.watch(cancel)
                job.url = youtube_url

                # 3. Kiểm tra manual/cache (trừ khi skip_resolve)
                if not skip_resolve:
                    job.step("tra cache")
                    source, resolved_data = self._resolve_tone(youtube_url)
                    if source == 'manual':
                        timeline    = resolved_data['timeline']
                        first       = timeline[0]
                        kd          = first.get('key_display', 'C')
                        flat_result = {
                            'key_display':  kd,
                            'key':          _extract_key_root(kd),
                            'key_index':    first.get('key_index', 0),
                            'scale':        first.get('scale', 'Major'),
                            'confidence':   first.get('confidence', 0),
                            'from_manual':  True,
                            'title':        resolved_data.get('title', ''),
                            'key_timeline': timeline,
                        }
                        self._send_tone_midi(flat_result)
                        self.current_youtube_url = youtube_url

                        # Transition sang REPLAYING (truyền token để không chuyển nhầm phiên)
                        replay_cancel = self._tone_session.transition_to_replaying(expected_token=cancel)
                        if replay_cancel is not None:
                            self._replay_manual_timeline(timeline, cancel_event=replay_cancel)

                        if on_complete:
                            on_complete(flat_result)
                        return

                    elif source == 'cache':
                        cached_result = self._build_cache_result(resolved_data)
                        if cached_result:
                            self.current_youtube_url = youtube_url
                            replay_cancel = self._tone_session.transition_to_replaying(expected_token=cancel)
                            if replay_cancel is not None:
                                self._replay_cached_timeline(
                                    resolved_data,
                                    cancel_event=replay_cancel,
                                )
                            if on_complete:
                                on_complete(cached_result)
                            return

                if _cancelled(cancel, watchdog_cancel):
                    return

                # 4. Tải audio từ YouTube (45s)
                job.step("tai audio YouTube")
                if on_progress:
                    on_progress("Đang tải audio từ YouTube...")

                scoring_engine = ScoringEngine()
                try:
                    # Tải đủ cho lần dò bổ sung của detect_key_from_file (một lần đi
                    # mạng; audio nén ~2MB cho 125s nên chênh lệch không đáng kể).
                    audio_path, video_title = scoring_engine.download_youtube_audio_with_info(
                        youtube_url, max_seconds=ToneDetector.FAST_EXTEND_SECONDS + 5)
                except Exception as e:
                    job.note_error(e)
                    audio_path, video_title = None, ''
                if not audio_path:
                    job.note_error(getattr(scoring_engine, 'last_download_error', None))

                if _cancelled(cancel, watchdog_cancel):
                    return

                result = None
                fail_reason = None  # nguyên nhân cụ thể khi thất bại
                if audio_path:
                    job.step("phan tich am dieu")
                    if on_progress:
                        on_progress("Đang phân tích âm điệu...")

                    # 5. Load + detect (sr=16000 for fast scan — CQT chroma only needs ≤4 kHz).
                    # 45s đầu; kém tự tin thì tự dò thêm trên 120s — ngầm, không báo khách
                    # (xem ToneDetector.detect_key_from_file). Lời gọi librosa đầu tiên
                    # đi qua run_healing bên trong (cache numba hỏng thì tự chữa).
                    try:
                        if _cancelled(cancel, watchdog_cancel):
                            return
                        result = ToneDetector.detect_key_from_file(
                            audio_path, sr=16000,
                            cancelled=lambda: _cancelled(cancel, watchdog_cancel))

                        if _cancelled(cancel, watchdog_cancel):
                            return
                        if result:
                            result['audio_source'] = 'youtube'
                        if not result:
                            fail_reason = ("Đã tải được audio từ YouTube nhưng không nhận diện "
                                           "được tone (bài quá nhiễu / không có giai điệu rõ).")
                    except Exception as e:
                        job.note_error(e)
                        fail_reason = ("Đã tải được audio nhưng phân tích âm điệu bị lỗi. "
                                       "Vui lòng thử lại sau giây lát.")
                    finally:
                        scoring_engine.cleanup_temp_file()
                        del scoring_engine
                else:
                    # PHƯƠNG ÁN DỰ PHÒNG: yt-dlp tải thất bại → nghe trực tiếp từ loa
                    try:
                        scoring_engine.cleanup_temp_file()
                    except Exception:
                        pass
                    del scoring_engine
                    _reasons = []
                    job.step("nghe loa (du phong)")
                    result = self._loopback_fallback_detect(on_progress, cancel, reason_out=_reasons,
                                                         cancelled=job.cancelled)
                    for _r in _reasons:
                        job.note(f"Nghe loa: {_r}")
                    if result and not video_title:
                        video_title = self._current_media_title()
                    if not result:
                        lb_reason = _reasons[0] if _reasons else "không nghe được âm thanh từ loa."
                        fail_reason = ("Không tải được audio từ YouTube (video bị chặn / cần đăng "
                                       "nhập / lỗi mạng) và phương án nghe loa cũng thất bại: " + lb_reason)

                # Kiểm tra timeout/cancel TRƯỚC side-effect (gửi MIDI / ghi cache / replay).
                if _cancelled(cancel, watchdog_cancel):
                    return

                if result:
                    result.update({
                        'title':       video_title,
                        'key':         _extract_key_root(result.get('key_display', 'C')),
                        'camelot':     _CAMELOT_MAJOR[result['key_index']] if result.get('scale') == 'Major'
                                       else _CAMELOT_MINOR[result['key_index']],
                        'key_timeline': [{
                            'time':        0,
                            'key_display': result['key_display'],
                            'key_index':   result['key_index'],
                            'scale':       result['scale'],
                            'confidence':  result.get('confidence', 0),
                        }],
                    })

                    self._send_tone_midi(result)
                    self.current_youtube_url = youtube_url
                    self._save_tone_to_cache(youtube_url, result, title=video_title)

                    # Replay đơn giản (single tone) — build replay dict from result in scope
                    replay_cancel = self._tone_session.transition_to_replaying(expected_token=cancel)
                    if replay_cancel is not None:
                        replay_data = {
                            'primary_key':  result['key_display'],
                            'key_timeline': result.get('key_timeline', []),
                        }
                        self._replay_cached_timeline(
                            replay_data,
                            cancel_event=replay_cancel,
                        )

                    if on_complete:
                        on_complete(result)
                else:
                    if on_error:
                        on_error(fail_reason or "Không thể dò tone. Hãy đảm bảo bài hát đang phát "
                                 "(phương án nghe từ loa cần có âm thanh).")

            except Exception as e:
                job.note_error(e)
                if on_error:
                    on_error(_USER_ERR_GENERIC)
            finally:
                job.detach()

        threading.Thread(target=_detect, daemon=True).start()

    # ── Auto detect full timeline ────────────────────────────────────────────────

    def auto_detect_youtube_timeline(self, url, on_complete=None, on_error=None, on_progress=None, skip_resolve=False):
        if not url:
            if on_error:
                on_error("Không có YouTube URL.")
            return

        on_complete, on_error, watchdog_cancel, job = _install_watchdog(
            _FULL_SCAN_TIMEOUT_SEC, on_complete, on_error,
            label="dò tone toàn bộ bài",
            on_timeout_hook=lambda: self._tone_session.stop(),
        )

        if not skip_resolve:
            # DÙNG CHUNG chuỗi resolve với chế độ nhanh (đệm phiên → timeline thủ
            # công → tone_cache → tone bài đã lưu → thư viện cộng đồng). Trước
            # đây chỗ này chỉ xét timeline thủ công nên chế độ "dò toàn bài" tải
            # + phân tích lại cả bài dù tone đã nằm sẵn trong cache — vừa chậm
            # vừa có thể ra tone khác lần trước.
            #
            # Kết quả TỰ ĐỘNG chỉ nằm ở tone_cache (có TTL) nên không khóa cứng
            # tone: bấm Dò Lại (skip_resolve=True) hay cache hết hạn đều dò mới.
            source, resolved_data = self._resolve_tone(url)
            if source is not None:
                is_manual = (source == 'manual')
                timeline  = (resolved_data.get('timeline') if is_manual
                             else resolved_data.get('key_timeline')) or []
                title     = resolved_data.get('title', '')
                label     = "timeline thủ công" if is_manual else "bộ nhớ đệm"
                if timeline:
                    print(f"[AUTO TIMELINE] Đã có {label} ({len(timeline)} đoạn), đang phát lại")
                    # Gửi MIDI NGAY một lần: bản cache đi qua _build_cache_result
                    # để key hiển thị / MIDI / cache là cùng một entry (bất biến
                    # nhất quán ở TONE_FLOWS §7b).
                    if is_manual:
                        self._send_tone_midi(timeline[0])
                    else:
                        self._build_cache_result(resolved_data)

                    cancel = self._tone_session.start_scanning(url)
                    replay_cancel = self._tone_session.transition_to_replaying(expected_token=cancel)
                    if replay_cancel is not None:
                        if is_manual:
                            self._replay_manual_timeline(timeline, cancel_event=replay_cancel)
                        else:
                            self._replay_cached_timeline(resolved_data, cancel_event=replay_cancel)

                    if on_complete:
                        on_complete({
                            'url': url, 'title': title,
                            'timeline': timeline, 'total_duration': 0,
                            'from_manual': is_manual,
                            'from_cache':  not is_manual,
                        })
                    return

        cancel = self._tone_session.start_scanning(url)
        job.watch(cancel)
        job.url = url

        def _detect_full():
            job.attach()
            scoring_engine = None
            audio_data     = None
            try:
                import librosa, math

                SEGMENT_DURATION = 15

                job.step("lay thong tin video")
                if on_progress:
                    on_progress("Đang lấy thông tin video...")

                video_title = "Bài hát không tên"
                try:
                    info        = extract_info_with_auth(
                        url, make_ydl_opts(skip_download=True), download=False,
                        log_prefix="⚠️ [AUTO TIMELINE]",
                    )
                    video_title = info.get('title', video_title)
                    del info
                    gc.collect()
                except Exception as e:
                    print(f"[AUTO TIMELINE] Không lấy được title: {e}")
                    job.note(f"Lay tieu de loi (khong chan): {type(e).__name__}: {e}")

                if _cancelled(cancel, watchdog_cancel):
                    return

                job.step("tai audio YouTube")
                if on_progress:
                    on_progress("Đang tải audio...")

                scoring_engine = ScoringEngine()
                # PHẢI truyền max_seconds: download_youtube_audio mặc định chỉ
                # tải 60 GIÂY ĐẦU (download_ranges). Thiếu tham số này thì chế độ
                # "dò toàn bài" chỉ quét được 60s đầu — timeline cụt, bài đổi tone
                # giữa chừng bị bỏ sót. Trần bằng đúng trần lúc nạp file bên dưới.
                audio_path     = scoring_engine.download_youtube_audio(
                    url, max_seconds=ToneDetector.TIMELINE_MAX_SECONDS)
                if not audio_path:
                    job.note_error(getattr(scoring_engine, 'last_download_error', None))

                if _cancelled(cancel, watchdog_cancel):
                    return

                total_seconds    = 0
                timeline_entries = None
                fail_reason      = None  # nguyên nhân cụ thể khi thất bại
                timeline_audio   = 'youtube'  # số đo nội bộ: nguồn audio thật sự đã dò

                if audio_path:
                    job.step("nap file am thanh")
                    if on_progress:
                        on_progress("Đang load file âm thanh...")

                    if _cancelled(cancel, watchdog_cancel):
                        return

                    # Trần cứng: chặn NGAY TỪ LÚC NẠP, không nạp cả bài rồi mới
                    # cắt. Một video 2 tiếng lọt vào đây là ~300MB audio thô cộng
                    # chi phí giải mã — đủ để hạ app trên máy quán đang chạy kèm
                    # Studio One. 20 phút dư cho mọi bài karaoke/liên khúc.
                    # run_healing: xem chú thích ở _detect() — cache numba hỏng
                    # thì tự xoá rồi nạp lại một lần.
                    audio_data, sr = run_healing(
                        librosa.load, audio_path, sr=22050, mono=True,
                        duration=ToneDetector.TIMELINE_MAX_SECONDS)
                    total_seconds  = len(audio_data) / sr
                    num_segments   = math.ceil(total_seconds / SEGMENT_DURATION)
                    print(f"[AUTO TIMELINE] Audio: {total_seconds:.1f}giây, {num_segments} đoạn")

                    if _cancelled(cancel, watchdog_cancel):
                        del audio_data
                        audio_data = None
                        return

                    job.step("phan tich timeline")
                    timeline_entries = ToneDetector.detect_timeline_advanced(
                        audio_data, sr, job.progress(on_progress))

                    del audio_data
                    audio_data = None
                    if not timeline_entries:
                        fail_reason = ("Đã tải được audio từ YouTube nhưng không nhận diện được "
                                       "tone nào (bài quá nhiễu / không có giai điệu rõ).")
                else:
                    # PHƯƠNG ÁN DỰ PHÒNG: yt-dlp tải thất bại → nghe trực tiếp từ loa.
                    # Không tải được toàn bài nên chỉ dò được MỘT tone (timeline 1 mốc).
                    _reasons = []
                    job.step("nghe loa (du phong)")
                    fb = self._loopback_fallback_detect(on_progress, cancel, reason_out=_reasons,
                                                         cancelled=job.cancelled)
                    for _r in _reasons:
                        job.note(f"Nghe loa: {_r}")
                    if fb:
                        timeline_audio = 'loa'
                        timeline_entries = [{
                            'time':        0,
                            'key_display': fb.get('key_display', 'C'),
                            'key_index':   fb.get('key_index', 0),
                            'scale':       fb.get('scale', 'Major'),
                            'confidence':  fb.get('confidence', 0),
                            'tuning_cents': fb.get('tuning_cents'),
                        }]
                        if not video_title or video_title == "Bài hát không tên":
                            video_title = self._current_media_title() or video_title
                    else:
                        lb_reason = _reasons[0] if _reasons else "không nghe được âm thanh từ loa."
                        fail_reason = ("Không tải được audio từ YouTube (video bị chặn / cần đăng "
                                       "nhập / lỗi mạng) và phương án nghe loa cũng thất bại: " + lb_reason)

                # Kiểm tra timeout/cancel TRƯỚC side-effect (ghi cache / gửi MIDI / replay).
                if _cancelled(cancel, watchdog_cancel):
                    return

                if not timeline_entries:
                    if on_error:
                        on_error(fail_reason or "Không phát hiện được tone nào trong bài hát.")
                    return

                job.step("luu ket qua")
                if on_progress:
                    on_progress("Đang lưu kết quả...")

                # QUYẾT ĐỊNH SẢN PHẨM: kết quả TỰ ĐỘNG chỉ ghi vào tone_cache (TTL),
                # KHÔNG ghi vào ManualToneTimeline nữa (manual chỉ dành cho user sửa
                # tay). Nhờ vậy tone không bị khóa cứng và có thể dò lại khi cần.
                primary_key = self._representative_primary_key(timeline_entries)
                cache_timeline = [{**e, **{'confidence': e.get('confidence', 0.8)}} for e in timeline_entries]
                auto_entry = {
                    'primary_key':  primary_key,
                    'key_timeline': cache_timeline,
                    'title':        video_title,
                }
                ToneCacheManager.save_tone(url, auto_entry)
                # Chỉ có YouTube mới dò được cả bài; nghe loa thì chỉ một tone.
                self._share_tone(url, video_title, auto_entry, diag=self._detection_diag(
                    'toan-bai' if timeline_audio == 'youtube' else 'nhanh',
                    timeline_audio, timeline_entries, primary_key))
                print(f"[AUTO TIMELINE] Đã lưu cache: {video_title} "
                      f"({len(timeline_entries)} đoạn, tone tiêu biểu {primary_key})")
                # Invalidate in-session cache after disk writes
                self._tone_resolve_cache_invalidate(url)

                first_key = timeline_entries[0]
                self._send_tone_midi(first_key)

                # Kết quả tự động nằm ở cache → replay theo đường CACHE cho nhất quán.
                replay_cancel = self._tone_session.transition_to_replaying(expected_token=cancel)
                if replay_cancel is not None:
                    self._replay_cached_timeline(
                        {'primary_key': primary_key, 'key_timeline': cache_timeline},
                        cancel_event=replay_cancel,
                    )

                if on_complete:
                    on_complete({
                        'url':            url,
                        'title':          video_title,
                        'timeline':       timeline_entries,
                        'total_duration': total_seconds,
                        'from_loopback':  audio_path is None,
                    })

            except _ToneCancelled:
                print("[AUTO TIMELINE] Phiên dò đã huỷ/hết giờ — dừng phân tích")
            except Exception as e:
                job.note_error(e)
                if on_error:
                    on_error(_USER_ERR_GENERIC)
            finally:
                if audio_data is not None:
                    del audio_data
                if scoring_engine is not None:
                    try:
                        scoring_engine.cleanup_temp_file()
                    except Exception:
                        pass
                    del scoring_engine
                job.detach()
                if self._tone_session.is_scanning:
                    self._tone_session.stop()

                # Xử lý URL pending nếu có
                pending_url = None
                with self._pending_url_lock:
                    if self._pending_url_queue:
                        pending_url = self._pending_url_queue.pop(0)
                        self._pending_url_queue.clear()
                if pending_url and pending_url != url:
                    import weakref
                    self._dispatch_auto_detect(pending_url, weakref.ref(self))

        threading.Thread(target=_detect_full, daemon=True).start()

    # ── Stop ────────────────────────────────────────────────────────────────────

    def stop_tone_detection(self):
        self._tone_session.stop()
