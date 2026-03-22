"""
Quang Lưu Studio — Windows Media Monitor
Tracks media playback status via Windows Media Transport Controls API.
"""
import gc
import time
import threading

# ===== TÍCH HỢP WINDOWS MEDIA API =====
try:
    import asyncio
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MediaManager
    _WIN_MEDIA_AVAILABLE = True
except ImportError:
    _WIN_MEDIA_AVAILABLE = False
    print("Vui lòng cài đặt winrt để đồng bộ timeline: pip install winrt-Windows.Media.Control winrt-Windows.Foundation")


class WindowsMediaMonitor:
    """Class theo dõi trạng thái phát media của Windows (đặc biệt là Web Browser)"""
    def __init__(self):
        self.current_title = ""
        self.current_position = 0.0  # seconds
        self.is_playing = False
        self._loop = None
        self._thread = None
        self._running = False
        
        if _WIN_MEDIA_AVAILABLE:
            self._start()
    
    def _start(self):
        self._running = True
        # Chạy asyncio loop trong 1 thread riêng
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        
    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._monitor_loop())
        except RuntimeError:
            pass  # "Event loop stopped before Future completed" — bình thường khi app đóng
        
    async def _monitor_loop(self):
        try:
            manager = await MediaManager.request_async()
            _iter_count = 0
            while self._running:
                try:
                    current_session = manager.get_current_session()
                    if current_session:
                        # Thêm timeout cho await để không block mãi
                        info = await current_session.try_get_media_properties_async()
                        if info:
                            self.current_title = info.title
                        
                        timeline = current_session.get_timeline_properties()
                        if timeline:
                            self.current_position = timeline.position.total_seconds()
                        
                        playback_info = current_session.get_playback_info()
                        if playback_info:
                            # 4 = PLAYING, 5 = PAUSED
                            status_name = playback_info.playback_status.name
                            self.is_playing = (status_name == "PLAYING")
                        
                        # Release WinRT COM objects — tránh tích lũy references
                        del info, timeline, playback_info, current_session
                    else:
                        self.is_playing = False
                except Exception as e:
                    pass
                
                # Periodic GC: mỗi 100 iterations (~10s) thu hồi COM references tích lũy
                _iter_count += 1
                if _iter_count % 100 == 0:
                    gc.collect(0)
                
                await asyncio.sleep(0.1)  # Cập nhật 10 lần/giây
        except Exception as e:
            print(f"Lỗi khởi tạo MediaManager: {e}")
            
    def stop(self):
        self._running = False
        if self._loop:
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception:
                pass
        # Đợi thread kết thúc để đảm bảo asyncio loop dừng hẳn
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        # Close asyncio loop để giải phóng WinRT COM objects
        if self._loop:
            try:
                if not self._loop.is_closed():
                    self._loop.close()
            except Exception:
                pass
            self._loop = None
            
    def wait_for_playback(self, timeout=30):
        """Chờ cho đến khi media thực sự PLAYING"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.is_playing:
                return True
            time.sleep(0.5)
        return False
