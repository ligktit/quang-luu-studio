"""
Quang Lưu Studio — Memory Management
Classes: MemoryProfiler, MemoryGuard
"""
import os
import gc
import time
import threading
import glob


class MemoryProfiler:
    """Công cụ theo dõi RAM để xác định vị trí tràn bộ nhớ.

    Sử dụng:
        mem = MemoryProfiler("AUTOKEY")
        mem.checkpoint("init")      # Ghi nhận RSS tại vị trí cụ thể
        mem.checkpoint("buffer")    # So sánh với checkpoint trước
        mem.summary()               # In tổng kết cuối cùng
    """
    def __init__(self, tag=""):
        import psutil
        self._tag = tag
        self._process = psutil.Process(os.getpid())
        self._start_rss = self._process.memory_info().rss
        self._peak_rss = self._start_rss
        self._last_rss = self._start_rss
        self._count = 0

    def checkpoint(self, label=""):
        rss = self._process.memory_info().rss
        delta = rss - self._last_rss
        self._last_rss = rss
        self._peak_rss = max(self._peak_rss, rss)
        self._count += 1
        if abs(delta) > 20 * 1024 * 1024:  # Chỉ log khi thay đổi > 20MB
            print(f"[{self._tag}] {label}: RSS={rss / 1024 / 1024:.1f}MB "
                  f"(Δ={delta / 1024 / 1024:+.1f}MB)")

    def summary(self):
        rss = self._process.memory_info().rss
        total_delta = rss - self._start_rss
        peak_delta = self._peak_rss - self._start_rss
        print(f"[{self._tag}] SUMMARY: "
              f"current={rss / 1024 / 1024:.1f}MB, "
              f"peak={self._peak_rss / 1024 / 1024:.1f}MB, "
              f"tăng={total_delta / 1024 / 1024:+.1f}MB, "
              f"peak tăng={peak_delta / 1024 / 1024:+.1f}MB, "
              f"checkpoints={self._count}")


def _current_rss():
    """RSS hiện tại (bytes), 0 nếu không đo được."""
    try:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss
    except Exception:
        return 0


class MemoryGuard:
    """Dọn RAM SAU MỖI LẦN DÒ TONE + daemon dọn cache/file tạm định kỳ.

    Cơ chế dọn RAM:
    - Mỗi luồng dò tone gọi begin_tone_job() lúc bắt đầu và end_tone_job() trong
      finally. Khi phiên dò CUỐI CÙNG kết thúc → force_cleanup() trả RAM về Windows.
    - force_cleanup() gọi trong lúc CÒN phiên dò đang chạy sẽ bị bỏ qua (phiên đó
      tự dọn khi xong) — không GC/trim chen ngang làm chậm việc dò tone.

    Trước đây daemon còn dọn theo NGƯỠNG RAM (RSS tăng > 50MB, hoặc RSS > 500MB là
    "khẩn cấp"). Các ngưỡng này bắn cả khi đang dò tone — gc.collect(2) + trim
    working set giữa chừng khiến numpy/librosa phải page-fault lại toàn bộ bộ đệm
    đang dùng — nên đã bỏ. Daemon giờ chỉ còn:
    1. Cache Cleanup: giới hạn kích thước PWA title cache.
    2. Temp File Cleanup: xóa file audio tạm (prefix qls_tmp_) do app tải về.

    Sử dụng:
        guard = MemoryGuard(engine)  # engine = SystemEngine instance
        guard.start()  # Chạy daemon thread
        guard.stop()   # Dừng thread

        MemoryGuard.begin_tone_job()
        try:
            ...dò tone...
        finally:
            MemoryGuard.end_tone_job()
    """

    # Số phiên dò tone đang chạy (dùng chung toàn tiến trình). _job_lock cũng được
    # giữ SUỐT lúc dọn để phiên mới không bắt đầu giữa chừng một lần dọn.
    # RLock: finalizer chạy trong gc.collect() có thể gọi lại force_cleanup.
    _job_lock = threading.RLock()
    _active_tone_jobs = 0

    @classmethod
    def begin_tone_job(cls):
        """Đánh dấu bắt đầu một phiên dò tone (gọi ở đầu luồng dò)."""
        with cls._job_lock:
            cls._active_tone_jobs += 1

    @classmethod
    def end_tone_job(cls):
        """Kết thúc một phiên dò tone; phiên cuối cùng xong thì dọn RAM."""
        with cls._job_lock:
            cls._active_tone_jobs = max(0, cls._active_tone_jobs - 1)
        # Gọi trong finally của luồng dò, trước khi đóng phiên → không được ném lỗi.
        try:
            cls.force_cleanup()  # tự bỏ qua nếu vẫn còn phiên khác đang dò
        except Exception as e:
            try:
                print(f"[MEMORY GUARD] Lỗi dọn RAM: {e}")
            except Exception:
                pass

    @classmethod
    def active_tone_jobs(cls):
        with cls._job_lock:
            return cls._active_tone_jobs

    @staticmethod
    def _trim_working_set():
        """Yêu cầu Windows trim working set — trả lại RAM vật lý cho OS.

        gc.collect() giải phóng Python objects nhưng pymalloc giữ lại memory pools
        → RSS không giảm ở OS level. API này force Windows trả lại các page không dùng.
        """
        try:
            import ctypes
            # WinDLL riêng: khai báo argtypes mà không đụng prototype dùng chung
            # của ctypes.windll.kernel32 ở module khác.
            k32 = ctypes.WinDLL("kernel32")
            k32.GetCurrentProcess.restype = ctypes.c_void_p
            k32.SetProcessWorkingSetSizeEx.argtypes = [
                ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint32]
            k32.SetProcessWorkingSetSizeEx(
                k32.GetCurrentProcess(),
                ctypes.c_size_t(-1).value,  # MinWorkingSetSize = -1 (trim)
                ctypes.c_size_t(-1).value,  # MaxWorkingSetSize = -1 (trim)
                0                           # Flags = 0
            )
        except Exception:
            pass

    @staticmethod
    def _compact_heap():
        """Gộp khối rỗi của heap mặc định và decommit phần thừa về Windows.

        numpy/CRT cấp bộ nhớ vừa và nhỏ qua heap này; free() chỉ trả khối về heap,
        commit charge vẫn giữ nguyên. CHỈ compact heap mặc định (luôn có khóa
        tuần tự) — heap riêng của DLL khác có thể tạo với HEAP_NO_SERIALIZE, compact
        chúng khi luồng khác đang dùng là hỏng heap.
        """
        try:
            import ctypes
            k32 = ctypes.WinDLL("kernel32")
            k32.GetProcessHeap.restype = ctypes.c_void_p
            k32.HeapCompact.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            k32.HeapCompact.restype = ctypes.c_size_t
            heap = k32.GetProcessHeap()
            if heap:
                k32.HeapCompact(heap, 0)
        except Exception:
            pass

    @staticmethod
    def force_cleanup():
        """Giải phóng RAM triệt để và trả lại cho Windows.

        Pipeline:
        1. gc.collect(2) — thu hồi tất cả Python objects (generations 0-2)
        2. _compact_heap() — decommit vùng heap rỗi (trả commit charge)
        3. _trim_working_set() — trả lại memory pages cho Windows

        Nếu còn phiên dò tone đang chạy thì BỎ QUA (trả False): phiên cuối cùng sẽ
        dọn trong end_tone_job(). Nhờ vậy các lời gọi dọn giữa chừng (bên trong
        ToneDetector, watcher YouTube, chấm điểm...) không chen vào lúc đang dò.
        """
        with MemoryGuard._job_lock:
            if MemoryGuard._active_tone_jobs > 0:
                return False
            before = _current_rss()
            gc.collect(2)
            MemoryGuard._compact_heap()
            MemoryGuard._trim_working_set()
            after = _current_rss()
        freed = before - after
        if before and after and freed > 10 * 1024 * 1024:  # Chỉ log khi đáng kể
            # try: được gọi trong finally của luồng dò tone, TRƯỚC khi đóng phiên —
            # print lỗi (console cp1252 không in được tiếng Việt) không được lọt ra.
            try:
                print(f"[MEMORY GUARD] Đã trả RAM về Windows: "
                      f"{before // (1024*1024)}MB → {after // (1024*1024)}MB")
            except Exception:
                pass
        return True

    def __init__(self, engine=None, interval=60, cache_ttl_seconds=600):
        self._engine = engine
        self._interval = interval  # Giây giữa mỗi lần dọn cache/file tạm
        self._cache_ttl = cache_ttl_seconds  # TTL cho file tạm (10 phút)
        self._running = False
        self._thread = None

    def start(self):
        """Bắt đầu daemon thread dọn cache/file tạm"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        print(f"[MEMORY GUARD] Đã khởi động (interval={self._interval}s, "
              f"dọn RAM sau mỗi lần dò tone)")

    def stop(self):
        """Dừng daemon thread"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

    def _monitor_loop(self):
        """Thread loop: dọn cache + file tạm theo chu kỳ.

        KHÔNG dọn RAM theo ngưỡng RSS ở đây — RAM được trả về sau mỗi lần dò tone
        (end_tone_job), xem docstring lớp."""
        while self._running:
            try:
                self._cleanup_caches()
                self._cleanup_temp_files()
            except Exception as e:
                print(f"[MEMORY GUARD] Lỗi: {e}")

            # Chờ interval (kiểm tra dừng mỗi giây)
            for _ in range(self._interval):
                if not self._running:
                    return
                time.sleep(1)

    def _cleanup_caches(self):
        """Xóa các entry cũ trong PWA title cache"""
        if not self._engine:
            return
        try:
            cache = getattr(self._engine, '_pwa_title_cache', None)
            if cache and len(cache) > 50:
                # Giới hạn cache size
                keys = list(cache.keys())
                for key in keys[:-20]:  # Giữ 20 entry mới nhất
                    del cache[key]
                # print(f"🧹 [MEMORY GUARD] PWA cache: trimmed to {len(cache)} entries")
                pass
        except Exception:
            pass

    def _cleanup_temp_files(self):
        """Xóa file audio TẠM cũ do app tải về (yt-dlp/scoring).

        QUAN TRỌNG: chỉ xóa file có TEMP_AUDIO_PREFIX — RECORDINGS_DIR
        (Documents/QuangLuuStudio khi frozen) chứa cả recording của user,
        tuyệt đối KHÔNG được xóa file không có prefix (VD: recording_*.wav).
        """
        from core.config import RECORDINGS_DIR, TEMP_AUDIO_PREFIX
        temp_dir = RECORDINGS_DIR
        if not os.path.isdir(temp_dir):
            return
        try:
            now = time.time()
            patterns = [TEMP_AUDIO_PREFIX + "*.wav", TEMP_AUDIO_PREFIX + "*.m4a",
                        TEMP_AUDIO_PREFIX + "*.webm", TEMP_AUDIO_PREFIX + "*.mp3"]
            for pattern in patterns:
                for fpath in glob.glob(os.path.join(temp_dir, pattern)):
                    try:
                        age = now - os.path.getmtime(fpath)
                        if age > self._cache_ttl:
                            os.remove(fpath)
                            # print(f"🧹 [MEMORY GUARD] Xóa temp: {os.path.basename(fpath)} (age={int(age)}s)")
                            pass
                    except Exception:
                        pass
        except Exception:
            pass

    def get_status(self):
        """Lấy trạng thái hiện tại của MemoryGuard"""
        return {
            "running": self._running,
            "rss_mb": _current_rss() / (1024 * 1024),
            "active_tone_jobs": MemoryGuard.active_tone_jobs(),
        }
