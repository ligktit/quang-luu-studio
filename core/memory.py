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
        if abs(delta) > 5 * 1024 * 1024:  # Chỉ log khi thay đổi > 5MB
            print(f"📊 [{self._tag}] {label}: RSS={rss / 1024 / 1024:.1f}MB "
                  f"(Δ={delta / 1024 / 1024:+.1f}MB)")
    
    def summary(self):
        rss = self._process.memory_info().rss
        total_delta = rss - self._start_rss
        peak_delta = self._peak_rss - self._start_rss
        print(f"📊 [{self._tag}] SUMMARY: "
              f"current={rss / 1024 / 1024:.1f}MB, "
              f"peak={self._peak_rss / 1024 / 1024:.1f}MB, "
              f"tăng={total_delta / 1024 / 1024:+.1f}MB, "
              f"peak tăng={peak_delta / 1024 / 1024:+.1f}MB, "
              f"checkpoints={self._count}")


class MemoryGuard:
    """Daemon thread tự động giải phóng RAM theo chu kỳ.
    
    Chiến lược:
    1. Periodic GC: Mỗi `interval` giây, kiểm tra RSS. Nếu tăng > `gc_threshold_mb` 
       so với lần cleanup trước → gọi gc.collect() + trim working set.
    2. Cache Cleanup: Xóa các entry cũ trong PWA title cache (> `cache_ttl_seconds`).
    3. Temp File Cleanup: Xóa file .wav/.m4a/.webm tạm trong thư mục temp_audio/.
    4. Emergency Mode: Nếu RSS > `emergency_threshold_mb` → force gc + trim + xóa mọi cache.
    
    Sử dụng:
        guard = MemoryGuard(engine)  # engine = SystemEngine instance
        guard.start()  # Chạy daemon thread
        guard.stop()   # Dừng thread
    """
    
    @staticmethod
    def _trim_working_set():
        """Yêu cầu Windows trim working set — trả lại RAM cho OS sau gc.collect().
        
        gc.collect() giải phóng Python objects nhưng pymalloc giữ lại memory pools
        → RSS không giảm ở OS level. API này force Windows trả lại các page không dùng.
        """
        try:
            import ctypes
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            ctypes.windll.kernel32.SetProcessWorkingSetSizeEx(
                handle,
                ctypes.c_size_t(-1),  # MinWorkingSetSize = -1 (trim)
                ctypes.c_size_t(-1),  # MaxWorkingSetSize = -1 (trim)
                0                     # Flags = 0
            )
        except Exception:
            pass
    
    @staticmethod
    def force_cleanup():
        """Giải phóng RAM triệt để sau khi dò tone.
        
        Pipeline:
        1. gc.collect(2) — thu hồi tất cả Python objects (generations 0-2)
        2. Clear librosa CQT filter cache — giữ ~10-30MB numpy arrays
        3. _trim_working_set() — trả lại memory pages cho Windows
        
        Gọi sau mỗi lần dò tone xong (detect_key_from_audio, detect_tone, autokey, ...)
        """
        # 1. Full GC (tất cả generations)
        gc.collect(2)
        
        # 2. Xóa librosa internal caches (CQT filter kernels, basis matrices)
        try:
            import librosa.core.constantq as _cq
            # Chỉ xóa các cache đã biết — KHÔNG dùng dir() vì sẽ clear __builtins__!
            for cache_name in ('__CQT_FILTER_CACHE', '_CQT_FILTER_CACHE',
                               '__EARLY_DOWNSAMPLE_CACHE', '_BASIS_CACHE'):
                cache = getattr(_cq, cache_name, None)
                if isinstance(cache, dict) and len(cache) > 0:
                    cache.clear()
        except Exception:
            pass
        
        try:
            # librosa.cache (joblib) — clear disk + memory cache
            import librosa
            if hasattr(librosa, 'cache') and hasattr(librosa.cache, 'clear'):
                librosa.cache.clear()
        except Exception:
            pass
        
        # 3. Force Windows trả lại RAM
        MemoryGuard._trim_working_set()
    
    def __init__(self, engine=None, interval=60, gc_threshold_mb=50, 
                 cache_ttl_seconds=600, emergency_threshold_mb=500):
        self._engine = engine
        self._interval = interval  # Giây giữa mỗi lần kiểm tra
        self._gc_threshold = int(gc_threshold_mb * 1024 * 1024)  # Bytes
        self._cache_ttl = cache_ttl_seconds  # TTL cho PWA cache (10 phút)
        self._emergency_threshold = int(emergency_threshold_mb * 1024 * 1024)
        self._last_rss = 0
        self._running = False
        self._thread = None
    
    def start(self):
        """Bắt đầu daemon thread giám sát RAM"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        print(f"🛡️ [MEMORY GUARD] Đã khởi động (interval={self._interval}s, "
              f"gc_threshold={self._gc_threshold // (1024*1024)}MB, "
              f"emergency={self._emergency_threshold // (1024*1024)}MB)")
    
    def stop(self):
        """Dừng daemon thread"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
    
    def _monitor_loop(self):
        """Thread loop: kiểm tra và cleanup RAM theo chu kỳ"""
        import psutil
        while self._running:
            try:
                process = psutil.Process(os.getpid())
                rss = process.memory_info().rss
                
                # ── Mức 1: Periodic GC (nhẹ) ──
                if self._last_rss > 0:
                    delta = rss - self._last_rss
                    if delta > self._gc_threshold:
                        MemoryGuard.force_cleanup()  # gc(2) + librosa cache + trim
                        new_rss = process.memory_info().rss
                        freed = rss - new_rss
                        print(f"🧹 [MEMORY GUARD] GC: freed {freed // (1024*1024)}MB, "
                              f"RSS: {new_rss // (1024*1024)}MB")
                        rss = new_rss
                
                # ── Mức 2: Cache Cleanup (trung bình) ──
                self._cleanup_caches()
                
                # ── Mức 3: Temp File Cleanup ──
                self._cleanup_temp_files()
                
                # ── Mức 4: Emergency Mode (nặng) ──
                if rss > self._emergency_threshold:
                    print(f"🚨 [MEMORY GUARD] EMERGENCY! RSS={rss // (1024*1024)}MB "
                          f"> {self._emergency_threshold // (1024*1024)}MB")
                    # Clear all caches trước khi force cleanup
                    if self._engine:
                        if hasattr(self._engine, '_pwa_title_cache'):
                            self._engine._pwa_title_cache.clear()
                    MemoryGuard.force_cleanup()  # gc(2) + librosa cache + trim
                    new_rss = process.memory_info().rss
                    print(f"🚨 [MEMORY GUARD] Emergency cleanup done: "
                          f"RSS={new_rss // (1024*1024)}MB")
                    rss = new_rss
                
                self._last_rss = rss
                
            except Exception as e:
                print(f"⚠️ [MEMORY GUARD] Lỗi: {e}")
            
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
                print(f"🧹 [MEMORY GUARD] PWA cache: trimmed to {len(cache)} entries")
        except Exception:
            pass
    
    def _cleanup_temp_files(self):
        """Xóa file tạm cũ trong temp_audio/"""
        temp_dir = "temp_audio"
        if not os.path.isdir(temp_dir):
            return
        try:
            now = time.time()
            patterns = ["*.wav", "*.m4a", "*.webm", "*.mp3"]
            for pattern in patterns:
                for fpath in glob.glob(os.path.join(temp_dir, pattern)):
                    try:
                        age = now - os.path.getmtime(fpath)
                        if age > self._cache_ttl:
                            os.remove(fpath)
                            print(f"🧹 [MEMORY GUARD] Xóa temp: {os.path.basename(fpath)} "
                                  f"(age={int(age)}s)")
                    except Exception:
                        pass
        except Exception:
            pass
    
    def get_status(self):
        """Lấy trạng thái hiện tại của MemoryGuard"""
        import psutil
        process = psutil.Process(os.getpid())
        rss = process.memory_info().rss
        return {
            "running": self._running,
            "rss_mb": rss / (1024 * 1024),
            "last_rss_mb": self._last_rss / (1024 * 1024),
            "gc_threshold_mb": self._gc_threshold / (1024 * 1024),
            "emergency_threshold_mb": self._emergency_threshold / (1024 * 1024),
        }
