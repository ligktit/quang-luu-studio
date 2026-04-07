"""
Quang Luu Studio — System Engine
Class: SystemEngine (main orchestrator)
"""
import os
import sys
import re
import gc
import json
import time
import ctypes
import ctypes.wintypes
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

from core.config import (
    AppConfig, ConfigManager, MIDI_PORT_NAME, FFMPEG_LOCATION,
    SETTINGS_FILE, SONGS_FILE, ACTIVATION_FILE
)
from core.utils import extract_video_id
from core.memory import MemoryProfiler, MemoryGuard
from core.media_monitor import WindowsMediaMonitor, _WIN_MEDIA_AVAILABLE
from core.midi import MidiHandler
from core.tone_cache import ToneCacheManager, ManualToneTimeline
from core.recorder import AudioRecorder
from core.scoring import ScoringEngine
from core.tone_detector import ToneDetector


class SystemEngine:
    # Cache WNDENUMPROC type ở class-level (tránh re-create mỗi lần poll → leak ctypes refs)
    _WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    
    def __init__(self, settings=None):
        self.settings = settings or {}

        # Khởi tạo MidiHandler
        self.midi_handler = MidiHandler()
        
        # Khởi tạo Loopback AudioRecorder
        self.recorder = AudioRecorder()
        
        # Khởi tạo WindowsMediaMonitor
        self.media_monitor = WindowsMediaMonitor()
        
        # Trạng thái theo dõi YouTube
        self.current_youtube_url = None
        self.youtube_monitoring_active = False
        self.on_video_end_callback = None
        
        # Trạng thái dò tone liên tục
        self.tone_detection_active = False
        self.on_tone_detected_callback = None
        
        # Trạng thái AutoKey (dò tone liên tục toàn bài)
        self.autokey_active = False
        self._autokey_thread = None
        
        # Callback nhận MIDI CC
        self.on_midi_cc_callback = None
        self.midi_handler.on_cc_received = self._handle_midi_in
        
        # YouTube URL Watcher (auto dò tone khi mở YouTube)
        self._youtube_watcher_active = False
        self._youtube_watcher_thread = None
        self._last_watched_url = None
        self._auto_tone_running = False  # tránh dò chồng chéo
        self.on_auto_tone_complete = None  # Callback(result_dict)
        self.on_auto_tone_error = None     # Callback(error_msg)
        self.on_auto_tone_progress = None  # Callback(status_text)
        
        # Tối ưu YT WATCHER: 2-tier title check + PWA cache + adaptive polling
        self._prev_browser_titles = None   # Cache titles để so sánh thay đổi (str hash)
        self._pwa_title_cache = {}          # Cache PWA title → URL (tránh gọi yt-dlp search lặp lại)
        self._no_browser_count = 0          # Đếm số lần poll không thấy browser (adaptive interval)
        
        # ===== MEMORY GUARD: Tự động giải phóng RAM =====
        self._memory_guard = MemoryGuard(
            engine=self,
            interval=30,              # Kiểm tra mỗi 30 giây (giảm từ 60s)
            gc_threshold_mb=50,       # GC khi RAM tăng > 50MB
            cache_ttl_seconds=600,    # Xóa cache cũ hơn 10 phút
            emergency_threshold_mb=500  # Emergency cleanup khi > 500MB
        )
        self._memory_guard.start()

    def _handle_midi_in(self, cc, value):
        if self.on_midi_cc_callback:
            self.on_midi_cc_callback(cc, value)
    

    # --- MIDI WRAPPER METHODS (tương thích với code cũ) ---
    @property
    def midi_out(self):
        """Property để tương thích với code cũ"""
        return self.midi_handler.outport

    def register_midi_callback(self, callback):
        """
        Đăng ký callback để nhận thông báo khi trạng thái MIDI thay đổi
        callback(connected: bool, port_name: str = None)
        """
        # Không có callback system trong MidiHandler đơn giản
        pass

    def unregister_midi_callback(self, callback):
        """Hủy đăng ký callback"""
        # Không có callback system trong MidiHandler đơn giản
        pass

    def is_midi_connected(self):
        """Kiểm tra xem MIDI đã kết nối chưa"""
        return self.midi_handler.outport is not None

    def get_midi_port_name(self):
        """Lấy tên port MIDI hiện tại"""
        return MIDI_PORT_NAME

    def disconnect_midi(self):
        """Ngắt kết nối MIDI — đóng cả Out + In port, dừng listen thread"""
        # 1. Đóng MIDI Out
        if self.midi_handler.outport:
            try:
                self.midi_handler.outport.close()
                print("✅ Đã ngắt kết nối MIDI Out")
            except Exception as e:
                print(f"⚠️ Lỗi khi ngắt MIDI Out: {e}")
            finally:
                self.midi_handler.outport = None
        
        # 2. Đóng MIDI In (fix: trước đây bị leak!)
        if self.midi_handler.inport:
            try:
                self.midi_handler._is_listening = False
                self.midi_handler.inport.close()
                print("✅ Đã ngắt kết nối MIDI In")
            except Exception as e:
                print(f"⚠️ Lỗi khi ngắt MIDI In: {e}")
            finally:
                self.midi_handler.inport = None
                self.midi_handler._listen_thread = None

    def connect_midi(self, retry_count=3, delay=1.0, on_connected=None, on_failed=None):
        """
        Kết nối MIDI (wrapper cho MidiHandler.connect())
        Args:
            retry_count: Số lần thử lại (không dùng trong MidiHandler đơn giản)
            delay: Thời gian chờ giữa các lần thử (không dùng trong MidiHandler đơn giản)
            on_connected: Callback khi kết nối thành công (port_name)
            on_failed: Callback khi kết nối thất bại
        Returns:
            bool: True nếu kết nối thành công, False nếu thất bại
        """
        result = self.midi_handler.connect()
        if result and on_connected:
            try:
                on_connected(self.midi_handler.outport.name if self.midi_handler.outport else None)
            except Exception:
                pass
        elif not result and on_failed:
            try:
                on_failed()
            except Exception:
                pass
        return result

    def send_midi(self, cc, value, auto_reconnect=True):
        """
        Gửi MIDI Control Change message (wrapper cho MidiHandler.send_cc())
        Args:
            cc: Control Change number (0-127)
            value: Giá trị (0-127)
            auto_reconnect: Tự động thử kết nối lại nếu gửi thất bại
        Returns:
            bool: True nếu gửi thành công, False nếu thất bại
        """
        # Kiểm tra kết nối
        if not self.midi_handler.outport:
            if auto_reconnect:
                if self.midi_handler.connect():
                    print("✅ Đã kết nối lại MIDI")
                else:
                    return False
            else:
                return False
        
        try:
            # Validate và clamp giá trị
            cc = max(0, min(127, int(cc)))
            value = max(0, min(127, int(value)))
            
            # Gửi MIDI message qua MidiHandler
            self.midi_handler.send_cc(cc, value, channel=0)
            return True
            
        except Exception as e:
            print(f"⚠️ Lỗi gửi MIDI CC {cc} = {value}: {e}")
            return False

    # ── BROWSER VOLUME CONTROL (YouTube) ──
    # Điều khiển volume ứng dụng trình duyệt ở mức hệ thống Windows
    # Sử dụng pycaw (Windows Audio Session API) — giống kéo slider trong Volume Mixer
    
    BROWSER_PROCESS_NAMES = [
        "chrome.exe", "msedge.exe", "opera.exe", "firefox.exe", 
        "brave.exe", "vivaldi.exe", "chromium.exe"
    ]
    
    _original_browser_volume = None  # Lưu volume gốc để restore khi thoát
    
    def set_browser_volume(self, volume_percent):
        """
        Set volume cho trình duyệt (YouTube) ở mức hệ thống Windows.
        Lần đầu gọi sẽ lưu volume gốc để restore khi thoát app.
        
        Args:
            volume_percent: 0-100 (0 = mute, 100 = max volume)
        
        Returns:
            bool: True nếu thành công, False nếu không tìm thấy browser audio session
        """
        try:
            from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
        except ImportError:
            print("⚠️ [BROWSER VOL] pycaw chưa được cài đặt. Chạy: pip install pycaw")
            return False
        
        volume = max(0.0, min(1.0, volume_percent / 100.0))
        found = False
        
        try:
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                if session.Process:
                    process_name = session.Process.name().lower()
                    if process_name in self.BROWSER_PROCESS_NAMES:
                        volume_control = session._ctl.QueryInterface(ISimpleAudioVolume)
                        # Lưu volume gốc lần đầu tiên
                        if self._original_browser_volume is None:
                            self._original_browser_volume = volume_control.GetMasterVolume()
                            print(f"🔊 [BROWSER VOL] Lưu volume gốc: {int(self._original_browser_volume * 100)}%")
                        volume_control.SetMasterVolume(volume, None)
                        found = True
        except Exception as e:
            print(f"⚠️ [BROWSER VOL] Lỗi set volume: {e}")
            return False
        
        return found
    
    def restore_browser_volume(self):
        """
        Khôi phục volume trình duyệt về mức ban đầu (trước khi app thay đổi).
        Gọi khi đóng app trong closeEvent.
        """
        if self._original_browser_volume is None:
            return  # Chưa từng thay đổi volume → không cần restore
        
        try:
            from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                if session.Process:
                    process_name = session.Process.name().lower()
                    if process_name in self.BROWSER_PROCESS_NAMES:
                        volume_control = session._ctl.QueryInterface(ISimpleAudioVolume)
                        volume_control.SetMasterVolume(self._original_browser_volume, None)
            print(f"🔊 [BROWSER VOL] Đã restore volume về {int(self._original_browser_volume * 100)}%")
        except Exception as e:
            print(f"⚠️ [BROWSER VOL] Lỗi restore volume: {e}")
        finally:
            self._original_browser_volume = None
    
    def get_browser_volume(self):
        """
        Đọc volume hiện tại của trình duyệt.
        
        Returns:
            int: Volume 0-100, hoặc -1 nếu không tìm thấy browser
        """
        try:
            from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
        except ImportError:
            return -1
        
        try:
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                if session.Process:
                    process_name = session.Process.name().lower()
                    if process_name in self.BROWSER_PROCESS_NAMES:
                        volume_control = session._ctl.QueryInterface(ISimpleAudioVolume)
                        return int(volume_control.GetMasterVolume() * 100)
        except Exception as e:
            print(f"⚠️ [BROWSER VOL] Lỗi get volume: {e}")
        
        return -1

    def trigger_midi_learn(self, cc_list=None):
        """
        Gửi chuỗi tín hiệu MIDI CC để Studio One có thể 'learn' nhanh.
        Args:
            cc_list: Danh sách các CC number cần gửi. Nếu None, gửi một bộ mặc định.
        """
        if cc_list is None:
            # Bộ CC mặc định dựa trên mapping của app
            cc_list = [10, 11, 20, 21, 22, 23, 30, 31, 32, 33, 34, 35, 36, 50, 51, 52, 53]
        
        def run_learn():
            print(f"🚀 [MIDI LEARN] Bắt đầu gửi {len(cc_list)} tín hiệu MIDI...")
            for cc in cc_list:
                # Gửi giá trị trung bình để Studio One nhận diện
                self.send_midi(cc, 64)
                time.sleep(0.2)  # Nghỉ giữa các CC để tránh nghẽn
                self.send_midi(cc, 0)
                time.sleep(0.1)
            print("✅ [MIDI LEARN] Hoàn tất gửi chuỗi tín hiệu.")
            
        threading.Thread(target=run_learn, daemon=True).start()

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
                    if len(keys) == 1: pyautogui.press(keys[0])
                    else: pyautogui.hotkey(*keys)
                except Exception: pass
        threading.Thread(target=run, daemon=True).start()

    # Các file mở rộng của Studio One — mở bằng os.startfile() (để OS route đến Studio One)
    STUDIO_ONE_EXTENSIONS = (
        ".song", ".songversion", ".soundset", ".instrument",
        ".multiinstrument", ".pedalboard", ".channel", ".macro", ".fxchain",
    )

    def launch_app(self, path, is_web=False):
        if not path or not os.path.exists(path): return
        
        if is_web:
             threading.Thread(target=lambda: subprocess.Popen([path, "youtube.com"]), daemon=True).start()
        else:
            # Logic mở file Studio One (.song, .soundset, ...) hoặc .exe
            if path.lower().endswith(self.STUDIO_ONE_EXTENSIONS):
                try: os.startfile(path)
                except Exception: pass
            else:
                running = False
                for p in psutil.process_iter(['name']):
                    if "Studio One" in p.info['name']: running = True
                if not running:
                    threading.Thread(target=lambda: subprocess.Popen(path), daemon=True).start()

    def kill_app(self):
        try: os.system('taskkill /F /IM "Studio One.exe"')
        except Exception: pass
    
    def open_youtube_url(self, url, on_video_end_callback=None, on_tone_detected=None, manual_timeline=None):
        """
        Mở YouTube URL trong browser, tự động dò tone và chấm điểm khi kết thúc
        
        Args:
            url: YouTube URL
            on_video_end_callback: Callback(result) khi video kết thúc
            on_tone_detected: Callback(result) khi phát hiện tone/chuyển tone
            manual_timeline: list of {time, key_display, key_index, scale} - nếu có, ưu tiên replay thủ công
        """
        if not url:
            return
        
        # Dừng dò tone cũ nếu có
        self.stop_tone_detection()
        
        # Lưu URL và callback
        self.current_youtube_url = url
        self.on_video_end_callback = on_video_end_callback
        self.on_tone_detected_callback = on_tone_detected
        
        # Mở YouTube trong browser
        def open_browser():
            browser_path = self.settings.get("browser_path")
            browser_name = None
            
            if browser_path:
                browser_exe = os.path.basename(browser_path).lower()
                if "chrome" in browser_exe:
                    browser_name = "chrome.exe"
                elif "firefox" in browser_exe:
                    browser_name = "firefox.exe"
                elif "edge" in browser_exe:
                    browser_name = "msedge.exe"
                elif "brave" in browser_exe:
                    browser_name = "brave.exe"
                elif "opera" in browser_exe:
                    browser_name = "opera.exe"
            
            browser_running = False
            if browser_name:
                for proc in psutil.process_iter(['name']):
                    if proc.info['name'].lower() == browser_name.lower():
                        browser_running = True
                        break
            
            if browser_running:
                try:
                    hwnd = None
                    def enum_callback(h, _):
                        nonlocal hwnd
                        if win32gui.IsWindowVisible(h):
                            window_text = win32gui.GetWindowText(h).lower()
                            if any(keyword in window_text for keyword in ["chrome", "firefox", "edge", "brave", "opera", "youtube"]):
                                hwnd = h
                    
                    win32gui.EnumWindows(enum_callback, None)
                    
                    if hwnd:
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                        win32gui.SetForegroundWindow(hwnd)
                        time.sleep(0.3)
                except Exception as e:
                    print(f"⚠️ Không thể focus vào browser: {e}")
            
            if browser_path and os.path.exists(browser_path):
                try:
                    subprocess.Popen([browser_path, url])
                except Exception as e:
                    print(f"⚠️ Lỗi mở browser: {e}")
                    try:
                        os.startfile(url)
                    except Exception:
                        print(f"⚠️ Không thể mở URL: {url}")
            else:
                try:
                    os.startfile(url)
                except Exception:
                    print(f"⚠️ Không thể mở URL: {url}")
        
        threading.Thread(target=open_browser, daemon=True).start()
        
        # Xử lý tone: ưu tiên manual_timeline > cache > auto-detect
        if manual_timeline:
            # Có manual timeline → replay thủ công (bỏ qua cache + auto-detect)
            def replay_manual():
                print("🎵 [MANUAL TONE] Đợi Browser phát nhạc (Windows Media API)...")
                if not self.media_monitor.wait_for_playback(timeout=30):
                    print("⚠️ [MANUAL TONE] Timeout chờ phát, bắt đầu replay anyway...")
                self._replay_manual_timeline(manual_timeline)
            threading.Thread(target=replay_manual, daemon=True).start()
        else:
            # Kiểm tra manual timeline đã lưu trước
            saved_manual = ManualToneTimeline.load_timeline(url)
            if saved_manual and saved_manual.get('timeline'):
                def replay_saved_manual():
                    print("🎵 [MANUAL TONE] Đợi Browser phát nhạc (Windows Media API)...")
                    if not self.media_monitor.wait_for_playback(timeout=30):
                        print("⚠️ [MANUAL TONE] Timeout chờ phát, bắt đầu replay anyway...")
                    self._replay_manual_timeline(saved_manual['timeline'])
                threading.Thread(target=replay_saved_manual, daemon=True).start()
            else:
                # Không có manual → auto-detect (logic cũ)
                def auto_detect_tone():
                    print("🎵 [AUTO TONE] Đợi Browser phát nhạc (Windows Media API)...")
                    if not self.media_monitor.wait_for_playback(timeout=30):
                        print("⚠️ [AUTO TONE] Timeout chờ phát, bắt đầu detect anyway...")
                    
                    # Kiểm tra cache trước
                    cached = ToneCacheManager.get_cached_tone(url)
                    if cached:
                        print(f"✅ [AUTO TONE] Đã có cache: {cached.get('primary_key', '?')}")
                        self._replay_cached_timeline(cached)
                        return
                    
                    # Không có cache → dò tone liên tục
                    print("🔍 [AUTO TONE] Không có cache, bắt đầu dò tone liên tục...")
                    self.detect_tone_continuous(url=url)
                
                threading.Thread(target=auto_detect_tone, daemon=True).start()
        
        # Lấy duration của video và tạo timer
        self._start_youtube_monitoring(url)
    
    def _start_youtube_monitoring(self, youtube_url):
        """Bắt đầu theo dõi video YouTube và tự động chấm điểm khi kết thúc"""
        print("=" * 60)
        print("📺 [YOUTUBE MONITORING] Bắt đầu theo dõi video YouTube...")
        print(f"🔗 URL: {youtube_url}")
        
        def get_video_duration():
            """Lấy duration của video YouTube bằng yt-dlp"""
            try:
                print("⏱️  [YOUTUBE MONITORING] Đang lấy thông tin video...")
                import yt_dlp
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                }
                if FFMPEG_LOCATION:
                    ydl_opts['ffmpeg_location'] = FFMPEG_LOCATION
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(youtube_url, download=False)
                    duration = info.get('duration', 0)  # Duration tính bằng giây
                    title = info.get('title', 'N/A')
                    print(f"✅ [YOUTUBE MONITORING] Thông tin video:")
                    print(f"   📺 Tiêu đề: {title}")
                    print(f"   ⏱️  Thời lượng: {duration} giây ({duration // 60}:{duration % 60:02d})")
                    return duration
            except Exception as e:
                print(f"❌ [YOUTUBE MONITORING] Không thể lấy duration của video: {e}")
                import traceback
                print(traceback.format_exc())
                return None
        
        def on_video_end():
            """Callback khi video kết thúc - tự động chấm điểm"""
            try:
                print("=" * 60)
                print("🎬 [CHẤM ĐIỂM] Video YouTube đã kết thúc, bắt đầu chấm điểm tự động...")
                print(f"📺 URL: {youtube_url}")
                
                # Tạo ScoringEngine và chấm điểm
                print("🔧 [CHẤM ĐIỂM] Khởi tạo ScoringEngine...")
                # Assuming ScoringEngine is defined elsewhere and imported
                # from .scoring_engine import ScoringEngine 
                # For now, just a placeholder
                class ScoringEngine:
                    def download_youtube_audio(self, url): return None
                    def load_audio(self, path): return False
                    def calculate_score(self, video_end): return None
                    def cleanup_temp_file(self): pass
                    sample_rate = 48000
                scoring_engine = ScoringEngine()
                
                # Tải audio từ YouTube
                print("📥 [CHẤM ĐIỂM] Đang tải audio từ YouTube...")
                audio_path = scoring_engine.download_youtube_audio(youtube_url)
                if not audio_path:
                    print("❌ [CHẤM ĐIỂM] Lỗi: Không thể tải audio từ YouTube")
                    if self.on_video_end_callback:
                        self.on_video_end_callback(None)
                    return
                print(f"✅ [CHẤM ĐIỂM] Đã tải audio thành công: {audio_path}")
                
                # Load audio
                print("📂 [CHẤM ĐIỂM] Đang load audio file...")
                if not scoring_engine.load_audio(audio_path):
                    print("❌ [CHẤM ĐIỂM] Lỗi: Không thể load audio file")
                    scoring_engine.cleanup_temp_file()
                    if self.on_video_end_callback:
                        self.on_video_end_callback(None)
                    return
                print(f"✅ [CHẤM ĐIỂM] Đã load audio thành công (sample_rate: {scoring_engine.sample_rate} Hz)")
                
                # Tính điểm (với flag video_end=True để dùng thuật toán mới)
                print("🧮 [CHẤM ĐIỂM] Đang tính điểm (chế độ video_end=True)...")
                result = scoring_engine.calculate_score(video_end=True)
                
                if result:
                    print("=" * 60)
                    print("✅ [CHẤM ĐIỂM] Kết quả chấm điểm:")
                    print(f"   📊 Điểm tổng: {result.get('total_score', 0):.1f}")
                    print(f"   🔊 Độ nhất quán âm lượng: {result.get('volume_consistency', 0):.1f}")
                    print(f"   ⏱️  Thời lượng: {result.get('duration', 0):.2f} giây")
                    print(f"   💬 Feedback: {result.get('feedback', 'N/A')}")
                    print("=" * 60)
                else:
                    print("❌ [CHẤM ĐIỂM] Lỗi: Không thể tính điểm")
                
                # Cleanup
                print("🧹 [CHẤM ĐIỂM] Đang dọn dẹp file tạm...")
                scoring_engine.cleanup_temp_file()
                print("✅ [CHẤM ĐIỂM] Đã dọn dẹp xong")
                
                # Gọi callback nếu có
                if self.on_video_end_callback and result:
                    print("📞 [CHẤM ĐIỂM] Gọi callback với kết quả...")
                    self.on_video_end_callback(result)
                elif result:
                    print(f"✅ [CHẤM ĐIỂM] Hoàn thành! Điểm số: {result.get('total_score', 0):.1f}")
                    
            except Exception as e:
                print("=" * 60)
                print(f"❌ [CHẤM ĐIỂM] Lỗi khi chấm điểm tự động: {e}")
                import traceback
                print(traceback.format_exc())
                print("=" * 60)
                if self.on_video_end_callback:
                    self.on_video_end_callback(None)
        
        # Lấy duration trong thread riêng
        def monitor_video():
            # Đánh dấu đang monitoring
            self.youtube_monitoring_active = True
            print("✅ [YOUTUBE MONITORING] Đã bắt đầu monitoring...")
            
            duration = get_video_duration()
            if duration and duration > 0:
                wait_time = duration + 5  # +5 giây buffer
                print(f"⏳ [YOUTUBE MONITORING] Đang đợi video kết thúc...")
                print(f"   ⏱️  Thời gian chờ: {wait_time} giây ({wait_time // 60}:{wait_time % 60:02d})")
                
                # Đợi duration + 5 giây buffer để đảm bảo video đã kết thúc
                time.sleep(wait_time)
                
                # Chỉ chấm điểm nếu vẫn đang monitoring (chưa bị hủy)
                if self.youtube_monitoring_active:
                    print("⏰ [YOUTUBE MONITORING] Video đã kết thúc, bắt đầu chấm điểm...")
                    on_video_end()
                else:
                    print("⚠️ [YOUTUBE MONITORING] Monitoring đã bị hủy, bỏ qua chấm điểm")
            else:
                print("❌ [YOUTUBE MONITORING] Không thể lấy duration, bỏ qua tự động chấm điểm")
            
            # Kết thúc monitoring
            self.youtube_monitoring_active = False
            print("🏁 [YOUTUBE MONITORING] Đã kết thúc monitoring")
            print("=" * 60)
        
        # Dừng monitoring cũ nếu có
        self.youtube_monitoring_active = False
        
        # Bắt đầu monitoring trong thread riêng
        monitoring_thread = threading.Thread(target=monitor_video, daemon=True)
        monitoring_thread.start()


    # ── Dò Tone: Phát hiện YouTube URL từ trình duyệt ──
    # Logic lấy từ detect_youtube.py (đã kiểm chứng hoạt động)
    
    @staticmethod
    def _enum_all_visible_windows():
        """
        Liệt kê tất cả cửa sổ visible trên Windows (1 lần EnumWindows duy nhất).
        Được dùng chung bởi detect_youtube_url_from_browser() và _detect_youtube_from_pwa().
        
        Returns:
            list[tuple[int, str]]: Danh sách (hwnd, title) của tất cả cửa sổ visible.
        """
        all_windows = []
        
        def enum_callback(hwnd, _):
            if ctypes.windll.user32.IsWindowVisible(hwnd):
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                    all_windows.append((hwnd, buf.value))
            return True
        
        ctypes.windll.user32.EnumWindows(SystemEngine._WNDENUMPROC(enum_callback), 0)
        return all_windows
    
    @staticmethod
    def detect_youtube_url_from_browser(quiet=False, all_windows=None, pwa_title_cache=None):
        """
        Phát hiện YouTube URL đang mở trên trình duyệt (Windows).
        Sử dụng ctypes.windll.user32.EnumWindows + uiautomation.
        
        Args:
            quiet: Tắt log output
            all_windows: Danh sách (hwnd, title) đã được enum sẵn (tối ưu: tránh gọi EnumWindows lặp lại)
            pwa_title_cache: Dict {title → url} cache kết quả PWA yt-dlp search
        
        Returns:
            str: YouTube URL sạch (chỉ chứa video ID), hoặc None nếu không tìm thấy.
        """
        try:
            import uiautomation as auto
        except ImportError:
            if not quiet:
                print("❌ [DÒ TONE] Thư viện 'uiautomation' chưa được cài đặt.")
                print("   Chạy: pip install uiautomation")
            return None
        
        # Bao gồm "Microsoft​ Edge" (có U+200B) + "Edge" ngắn gọn để khớp mọi trường hợp
        browser_keywords = [
            "Google Chrome", "Microsoft\u200b Edge", "Microsoft Edge",
            "Mozilla Firefox", "Brave", "Opera", "Vivaldi", "Edge",
        ]
        
        # ── Bước 1: Liệt kê tất cả cửa sổ trình duyệt ──
        if all_windows is None:
            all_windows = SystemEngine._enum_all_visible_windows()
        
        # Lọc cửa sổ trình duyệt
        browser_windows = []
        for hwnd, title in all_windows:
            for keyword in browser_keywords:
                if keyword.lower() in title.lower():
                    browser_windows.append({"hwnd": hwnd, "title": title, "browser": keyword})
                    break
        
        if not quiet:
            print(f"🔍 [DÒ TONE] Tìm thấy {len(browser_windows)} cửa sổ trình duyệt")
        
        # ── Bước 2: Đọc URL từ thanh địa chỉ ──
        for bw in browser_windows:
            hwnd = bw["hwnd"]
            control = None
            children = None
            try:
                control = auto.ControlFromHandle(hwnd)
                if control is None:
                    continue
                
                # Phương pháp 1: Duyệt children → tìm EditControl
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
                                url = SystemEngine._normalize_url(value)
                                clean = SystemEngine._clean_youtube_url(url)
                                if clean:
                                    print(f"   ✅ YouTube URL: {clean}")
                                    return clean
                    except Exception:
                        continue
                del children  # Giải phóng COM objects từ GetChildren()
                children = None
                
                # Phương pháp 2: Tìm EditControl trực tiếp (fallback)
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
                        url = SystemEngine._normalize_url(value)
                        clean = SystemEngine._clean_youtube_url(url)
                        if clean:
                            print(f"   ✅ YouTube URL: {clean}")
                            return clean
                
                # Phương pháp 3: Tìm EditControl theo Name (Brave/Chromium-based)
                # Brave address bar có Name="Address and search bar" nhưng nằm sâu hơn
                try:
                    edit = control.EditControl(
                        searchDepth=15,
                        Name="Address and search bar"
                    )
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
                            url = SystemEngine._normalize_url(value)
                            clean = SystemEngine._clean_youtube_url(url)
                            if clean:
                                print(f"   ✅ YouTube URL (Brave): {clean}")
                                return clean
                except Exception:
                    pass
                
            except Exception as e:
                print(f"   ⚠️ Lỗi đọc cửa sổ {bw['browser']}: {e}")
                continue
            finally:
                # Giải phóng COM objects UIAutomation (tránh leak khi poll liên tục)
                del control, children
        
        # ── Bước 3: Fallback — tìm từ PWA YouTube (dùng lại all_windows + pwa_title_cache) ──
        pwa_url = SystemEngine._detect_youtube_from_pwa(quiet, all_windows=all_windows, pwa_title_cache=pwa_title_cache)
        if pwa_url:
            return pwa_url
        
        if not quiet:
            print("⚠️ [DÒ TONE] Không tìm thấy YouTube URL trên trình duyệt hoặc PWA.")
        return None
    
    @staticmethod
    def _normalize_url(url):
        """Thêm https:// nếu URL thiếu protocol."""
        url = url.strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        return url
    
    @staticmethod
    def _clean_youtube_url(url):
        """Trích xuất Video ID từ YouTube URL, loại bỏ params playlist."""
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
    
    @staticmethod
    def _detect_youtube_from_pwa(quiet=False, all_windows=None, pwa_title_cache=None):
        """
        Phát hiện YouTube URL từ PWA YouTube (cài từ Chrome/Edge).
        PWA không có thanh địa chỉ → dùng tiêu đề cửa sổ + yt-dlp search.
        
        Args:
            quiet: Tắt log output
            all_windows: Danh sách (hwnd, title) đã enum sẵn (tránh gọi EnumWindows lặp lại)
            pwa_title_cache: Dict {title → url} cache kết quả yt-dlp search trước đó
        
        Returns:
            str: YouTube URL sạch, hoặc None nếu không tìm thấy.
        """
        # Tên process của trình duyệt hỗ trợ PWA
        pwa_browsers = {"chrome.exe", "msedge.exe"}
        
        # ── Bước 1: Dùng all_windows đã enum sẵn hoặc enum mới ──
        if all_windows is None:
            all_windows = SystemEngine._enum_all_visible_windows()
        
        # ── Bước 2: Tìm cửa sổ PWA YouTube ──
        # PWA YouTube có tiêu đề dạng: "Video Title - YouTube"
        # Nhưng KHÔNG chứa tên trình duyệt (Google Chrome, Microsoft Edge...)
        browser_keywords_lower = [
            "google chrome", "microsoft edge", "mozilla firefox",
            "brave", "opera", "vivaldi",
        ]
        
        pwa_candidates = []
        for hwnd, title in all_windows:
            title_lower = title.lower().strip()
            
            # Phải chứa "- youtube" (tiêu đề PWA YouTube)
            if "- youtube" not in title_lower:
                continue
            
            # Loại trừ cửa sổ trình duyệt thông thường
            is_browser = False
            for kw in browser_keywords_lower:
                if kw in title_lower:
                    is_browser = True
                    break
            if is_browser:
                continue
            
            # Xác nhận process là chrome.exe hoặc msedge.exe
            # PWA chạy trong subprocess → cần kiểm tra cả process tree (parent, grandparent)
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                proc = psutil.Process(pid)
                proc_name = proc.name().lower()
                
                is_pwa_process = False
                
                # Kiểm tra trực tiếp: process chính là chrome/edge
                if proc_name in pwa_browsers:
                    is_pwa_process = True
                else:
                    # Kiểm tra parent process tree (PWA subprocess → parent là chrome/edge)
                    try:
                        parent = proc.parent()
                        for _ in range(5):  # Tối đa 5 cấp parent
                            if parent is None:
                                break
                            parent_name = parent.name().lower()
                            if parent_name in pwa_browsers:
                                is_pwa_process = True
                                if not quiet:
                                    print(f"   🔍 [PWA] Process {proc_name} → parent {parent_name} (PWA confirmed)")
                                break
                            parent = parent.parent()
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass
                
                if not is_pwa_process:
                    if not quiet:
                        print(f"   ⚠️ [PWA] Bỏ qua: process={proc_name} (pid={pid}), không phải PWA browser")
                    continue
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
                # Process đã kết thúc hoặc không có quyền truy cập → vẫn thử (PWA có thể valid)
                if not quiet:
                    print(f"   ⚠️ [PWA] Không thể xác minh process (pid={pid}): {e}, thử tiếp...")
            except Exception as e:
                if not quiet:
                    print(f"   ⚠️ [PWA] Lỗi kiểm tra process: {e}")
                continue
            
            pwa_candidates.append({"hwnd": hwnd, "title": title})
        
        if not pwa_candidates:
            return None
        
        if not quiet:
            print(f"📱 [DÒ TONE] Tìm thấy {len(pwa_candidates)} cửa sổ PWA YouTube")
        
        # ── Bước 3: Trích xuất tên video từ tiêu đề ──
        # Tiêu đề PWA YouTube (Edge/Chrome) có các dạng:
        #   - Đang phát:  "YouTube - (N) Video Title - YouTube"  (N = notification count)
        #   - Đang phát:  "Video Title - YouTube"                (Chrome PWA, không prefix)
        #   - Trang chủ:  "YouTube - (N) YouTube"                (không có video)
        #   - Trang chủ:  "YouTube"                               (không có video)
        import re as _re
        for candidate in pwa_candidates:
            title = candidate["title"]
            
            # Tách phần " - YouTube" cuối cùng
            yt_suffix_idx = title.rfind(" - YouTube")
            if yt_suffix_idx <= 0:
                continue
            
            video_title = title[:yt_suffix_idx].strip()
            if not video_title:
                continue
            
            # Strip prefix "YouTube - (N) " nếu có (Edge PWA format)
            video_title = _re.sub(r'^YouTube\s*-\s*(\(\d+\)\s*)?', '', video_title).strip()
            
            # Xóa Unicode directional markers (U+202A, U+202C) mà Edge inject vào @mentions
            video_title = video_title.replace('\u202a', '').replace('\u202c', '')
            
            if not video_title or video_title.lower() == "youtube":
                continue  # Trang chủ YouTube, không có video
            
            if not quiet:
                print(f"📱 [DÒ TONE] PWA YouTube: \"{video_title}\"")
            
            # ── Bước 4A: Kiểm tra PWA title cache trước ──
            if pwa_title_cache is not None and video_title in pwa_title_cache:
                cached_url = pwa_title_cache[video_title]
                if not quiet:
                    print(f"   ✅ PWA cache hit: {cached_url}")
                return cached_url
            
            # ── Bước 4B: Cache miss → Tìm YouTube URL bằng yt-dlp search ──
            try:
                import yt_dlp
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'skip_download': True,
                    'default_search': 'ytsearch',
                    'noplaylist': True,
                }
                if FFMPEG_LOCATION:
                    ydl_opts['ffmpeg_location'] = FFMPEG_LOCATION
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(f"ytsearch:{video_title}", download=False)
                    
                    if not info:
                        continue
                    
                    # ytsearch trả về entries list
                    entries = info.get('entries', [])
                    if entries:
                        first = entries[0]
                        video_id = first.get('id', '')
                        if video_id:
                            found_url = f"https://www.youtube.com/watch?v={video_id}"
                            print(f"   ✅ PWA YouTube URL: {found_url}")
                            # Lưu vào cache
                            if pwa_title_cache is not None:
                                pwa_title_cache[video_title] = found_url
                            return found_url
                            
            except Exception as e:
                if not quiet:
                    print(f"   ⚠️ [DÒ TONE] PWA search lỗi: {e}")
                continue
        
        return None
    
    def detect_tone_from_browser(self, on_complete=None, on_error=None, on_progress=None, url=None):
        """
        Dò Tone từ YouTube đang mở trên trình duyệt.
        Luồng: Phát hiện URL → Tải audio (45s) → detect_key_from_audio → Trả kết quả.
        
        Args:
            on_complete: Callback(result_dict) khi hoàn thành
            on_error: Callback(error_msg) khi lỗi
            on_progress: Callback(status_text) cập nhật trạng thái
            url: YouTube URL (nếu đã biết trước, bỏ qua bước phát hiện từ browser)
        """
        import numpy as np
        
        # Camelot wheel mapping
        CAMELOT_MAJOR = ["8B", "3B", "10B", "5B", "12B", "7B", "2B", "9B", "4B", "11B", "6B", "1B"]
        CAMELOT_MINOR = ["5A", "12A", "7A", "2A", "9A", "4A", "11A", "6A", "1A", "8A", "3A", "10A"]
        
        def _detect():
            try:
                # Bước 1: Lấy YouTube URL (dùng url truyền vào hoặc phát hiện từ browser)
                if url:
                    youtube_url = url
                else:
                    if on_progress:
                        on_progress("Đang tìm YouTube URL trên trình duyệt...")
                    
                    youtube_url = SystemEngine.detect_youtube_url_from_browser()
                    
                    if not youtube_url:
                        if on_error:
                            on_error("Không tìm thấy YouTube URL trên trình duyệt.\nHãy mở YouTube trên Chrome/Edge/Firefox.")
                        return
                
                self.current_youtube_url = youtube_url
                
                # Bước 2: Kiểm tra cache TRƯỚC (nhanh, không cần gọi yt-dlp)
                if on_progress:
                    on_progress("Đang kiểm tra cache...")
                
                cached = ToneCacheManager.get_cached_tone(youtube_url)
                if cached:
                    cached_title = cached.get('title', '')
                    print(f"✅ [DÒ TONE] Cache hit: {cached.get('primary_key', '?')} | Title: {cached_title or '(chưa có)'}")
                    timeline = cached.get('key_timeline', [])
                    if timeline:
                        entry = timeline[0]
                        key_idx = entry.get('key_index', 0)
                        scale = entry.get('scale', 'Major')
                        camelot = CAMELOT_MAJOR[key_idx] if scale == "Major" else CAMELOT_MINOR[key_idx]
                        
                        # Nếu cache chưa có title → lấy nhanh từ yt-dlp
                        if not cached_title:
                            try:
                                import yt_dlp
                                ydl_opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
                                if FFMPEG_LOCATION:
                                    ydl_opts['ffmpeg_location'] = FFMPEG_LOCATION
                                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                                    info = ydl.extract_info(youtube_url, download=False)
                                    cached_title = info.get('title', '') if info else ""
                                del info  # Giải phóng yt-dlp info dict (~10-20MB)
                                gc.collect()
                                # Cập nhật title vào cache
                                if cached_title:
                                    cached['title'] = cached_title
                                    ToneCacheManager.save_tone(youtube_url, cached)
                            except Exception:
                                pass
                        
                        result = {
                            'key': entry.get('key_display', 'C').replace('m', ''),
                            'key_display': entry.get('key_display', 'C'),
                            'key_index': key_idx,
                            'scale': scale,
                            'bpm': entry.get('bpm', 0),
                            'confidence': entry.get('confidence', 0),
                            'duration': entry.get('duration', 0),
                            'camelot': camelot,
                            'from_cache': True,
                            'url': youtube_url,
                            'title': cached_title,
                            'timeline': timeline,
                        }
                        self._send_tone_midi(result)
                        if on_complete:
                            on_complete(result)
                        return
                
                # Bước 3+4 tối ưu: Cache miss → Tải audio + lấy title trong 1 lần gọi yt-dlp
                if on_progress:
                    on_progress("Đang tải audio từ YouTube...")
                
                print(f"🎵 [DÒ TONE] Bắt đầu dò tone từ YouTube...")
                print(f"🔗 URL: {youtube_url}")
                
                scoring_engine = ScoringEngine()
                audio_path, video_title = scoring_engine.download_youtube_audio_with_info(youtube_url)
                
                if not audio_path:
                    if on_error:
                        on_error("Không thể tải audio từ YouTube.")
                    return
                
                try:
                    # Bước 5: Load audio bằng librosa (45s đầu — ưu tiên tốc độ)
                    if on_progress:
                        on_progress("Đang phân tích bài hát...")
                    
                    import librosa
                    
                    # Chỉ load 45 giây đầu — đủ để phát hiện key, nhanh hơn nhiều
                    audio_data, sr = librosa.load(audio_path, sr=22050, mono=True, duration=45)
                    song_duration = len(audio_data) / sr
                    
                    print(f"✅ [DÒ TONE] Loaded: {song_duration:.1f}s, sr={sr}")
                    
                    # Bước 6: Phát hiện Key & Scale
                    if on_progress:
                        on_progress("Đang phát hiện Key & Scale...")
                    
                    tone_result = ToneDetector.detect_key_from_audio(audio_data, sr)
                    del audio_data  # Giải phóng audio data ngay sau khi dò tone
                    
                    if not tone_result:
                        if on_error:
                            on_error("Không thể phát hiện tone bài hát.")
                        return
                    
                    # BPM & Camelot — tạm bỏ qua để trả kết quả nhanh hơn
                    key_idx = tone_result['key_index']
                    scale = tone_result['scale']
                    bpm = 0.0
                    camelot = ''
                    
                    # Kết quả
                    result = {
                        'key': tone_result.get('key', 'C'),
                        'key_display': tone_result.get('key_display', 'C'),
                        'key_index': key_idx,
                        'scale': scale,
                        'bpm': round(bpm, 1),
                        'confidence': tone_result.get('confidence', 0),
                        'duration': round(song_duration, 1),
                        'camelot': camelot,
                        'from_cache': False,
                        'url': youtube_url,
                        'title': video_title,
                    }
                    
                    print(f"🎯 [DÒ TONE] Kết quả:")
                    print(f"   Key: {result['key_display']}")
                    print(f"   Scale: {result['scale']}")
                    print(f"   Confidence: {result['confidence']:.3f}")
                    print(f"   Duration: {result['duration']}s")
                    
                    # Stop active manual replay
                    self.tone_detection_active = False
                    
                    # Gửi MIDI
                    self._send_tone_midi(result)
                    
                    # Lưu cache (dùng DRY helper)
                    SystemEngine._save_tone_to_cache(youtube_url, result, title=video_title)
                    
                    if on_complete:
                        on_complete(result)
                        
                finally:
                    scoring_engine.cleanup_temp_file()
                    del scoring_engine  # Giải phóng ScoringEngine + internal refs
                    MemoryGuard.force_cleanup()  # gc + clear librosa cache + trim RAM
                    
            except Exception as e:
                print(f"❌ [DÒ TONE] Lỗi: {e}")
                import traceback
                traceback.print_exc()
                if on_error:
                    on_error(str(e))
        
        threading.Thread(target=_detect, daemon=True).start()

    # ── YouTube URL Watcher — Tự động dò tone khi mở YouTube ──
    def start_youtube_watcher(self, poll_interval=1.5):
        """
        Bắt đầu theo dõi trình duyệt liên tục.
        Khi phát hiện YouTube URL mới → tự động dò tone.
        
        Args:
            poll_interval: Khoảng thời gian poll (giây), mặc định 1.5s
        """
        if self._youtube_watcher_active:
            return  # Đã chạy rồi
        
        self._youtube_watcher_active = True
        self._youtube_watcher_thread = threading.Thread(
            target=self._youtube_watcher_loop,
            args=(poll_interval,),
            daemon=True
        )
        self._youtube_watcher_thread.start()
        print("👁️ [YT WATCHER] Đã bắt đầu theo dõi trình duyệt...")
    
    def stop_youtube_watcher(self):
        """Dừng theo dõi trình duyệt."""
        self._youtube_watcher_active = False
        # Đợi thread dừng hẳn để tránh thread stacking khi restart
        if self._youtube_watcher_thread:
            self._youtube_watcher_thread.join(timeout=3.0)
            self._youtube_watcher_thread = None
        print("👁️ [YT WATCHER] Đã dừng theo dõi trình duyệt.")
    
    def _youtube_watcher_loop(self, poll_interval):
        """
        Thread loop: poll trình duyệt mỗi N giây, phát hiện YouTube URL mới.
        
        Tối ưu tài nguyên:
        - 2-Tier Strategy: Kiểm tra title (rất nhanh) trước, chỉ gọi UIAutomation khi title thay đổi
        - Adaptive Polling: Tăng interval khi đang dò tone hoặc không có browser
        - Shared EnumWindows: Gọi 1 lần duy nhất, dùng chung cho browser + PWA
        - PWA Cache: Cache kết quả yt-dlp search theo title
        - Periodic GC: gc.collect(0) mỗi ~30s để giải phóng COM objects + mảng trung gian
        
        Lưu ý: KHÔNG gọi CoInitializeEx thủ công — uiautomation tự khởi tạo COM (STA).
        Nếu gọi CoInitializeEx(MTA) trước → xung đột mode → RPC_E_CHANGED_MODE.
        """
        import weakref
        engine_ref = weakref.ref(self)
        mem = MemoryProfiler("YT_WATCHER")
        poll_count = 0  # Đếm số lần poll (cho periodic GC)
        
        while self._youtube_watcher_active:
            try:
                # ── Adaptive Polling: Tính interval phù hợp ──
                if self._auto_tone_running:
                    current_interval = 5.0  # Đang dò tone → poll chậm lại
                elif self._no_browser_count > 5:
                    current_interval = 5.0  # Không thấy browser lâu → poll chậm
                else:
                    current_interval = poll_interval  # Mặc định: 1.5s
                
                # ── Tầng 1 (nhẹ): EnumWindows + GetWindowText — so sánh title ──
                all_windows = SystemEngine._enum_all_visible_windows()
                
                # Tạo fingerprint CHỈ từ browser windows (bỏ qua Studio One, DAW, etc.)
                # Studio One cập nhật title liên tục (vị trí, trạng thái record) → nếu tính
                # fingerprint từ TẤT CẢ windows, hash thay đổi mỗi poll → UIAutomation 
                # scan chạy mỗi 1.5s → tạo hàng nghìn COM objects → TRÀN RAM!
                _BROWSER_TITLE_KEYS = ("chrome", "edge", "firefox", "brave", "opera", "vivaldi", "youtube")
                browser_titles = tuple(
                    title for _, title in all_windows
                    if any(k in title.lower() for k in _BROWSER_TITLE_KEYS)
                )
                titles_fingerprint = hash(browser_titles)
                
                if titles_fingerprint == self._prev_browser_titles:
                    # Title browser không đổi → skip UIAutomation (tiết kiệm ~90% CPU + RAM)
                    pass
                else:
                    # ── Tầng 2 (nặng): Title thay đổi → đọc URL qua UIAutomation ──
                    self._prev_browser_titles = titles_fingerprint
                    
                    url = SystemEngine.detect_youtube_url_from_browser(
                        quiet=True,
                        all_windows=all_windows,
                        pwa_title_cache=self._pwa_title_cache,
                    )
                    
                    if url:
                        self._no_browser_count = 0  # Reset counter
                        
                        if url != self._last_watched_url and not self._auto_tone_running:
                            # Phát hiện URL mới → tự động dò tone
                            print(f"👁️ [YT WATCHER] Phát hiện YouTube mới: {url}")
                            self._last_watched_url = url
                            self._auto_tone_running = True
                            
                            def _on_complete(result):
                                eng = engine_ref()
                                if eng is None:
                                    return
                                eng._auto_tone_running = False
                                result['auto_detected'] = True
                                if eng.on_auto_tone_complete:
                                    eng.on_auto_tone_complete(result)
                            
                            def _on_error(msg):
                                eng = engine_ref()
                                if eng is None:
                                    return
                                eng._auto_tone_running = False
                                if eng.on_auto_tone_error:
                                    eng.on_auto_tone_error(msg)
                            
                            
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
                                )
                            else:
                                def _on_full_scan_complete(data):
                                    _on_complete({'full_scan': True, 'data': data})
                                
                                self.auto_detect_youtube_timeline(
                                    url=url,
                                    on_complete=_on_full_scan_complete,
                                    on_error=_on_error,
                                    on_progress=_on_progress
                                )
                    else:
                        self._no_browser_count += 1
                
                del all_windows  # Giải phóng list (hwnd, title) ngay sau khi dùng
                    
            except Exception as e:
                print(f"⚠️ [YT WATCHER] Lỗi poll: {e}")
            
            # Periodic GC: mỗi 20 lần poll (~30s) — full cleanup
            poll_count += 1
            if poll_count % 20 == 0:
                MemoryGuard.force_cleanup()  # gc(2) + clear librosa cache + trim RAM
            
            mem.checkpoint("poll")
            
            # Chờ trước khi poll lại (dùng adaptive interval)
            for _ in range(int(current_interval * 10)):
                if not self._youtube_watcher_active:
                    mem.summary()
                    return
                time.sleep(0.1)

    # ── DRY Helpers: Cache kiểm tra/lưu tone (dùng chung nhiều hàm) ──
    
    def _check_tone_cache(self, url):
        """
        Kiểm tra cache tone cho YouTube URL. Nếu có, gửi MIDI và trả về result dict.
        
        Returns:
            dict: result dict (from_cache=True, key_timeline, ...) nếu cache hit
            None: nếu cache miss
        """
        cached = ToneCacheManager.get_cached_tone(url)
        if not cached:
            return None
        
        timeline = cached.get('key_timeline', [])
        if not timeline:
            return None
        
        print(f"✅ [CACHE] Hit: {cached.get('primary_key', '?')}")
        
        latest = timeline[-1]
        result = {
            'key_display': cached.get('primary_key', latest.get('key_display', 'C')),
            'key_index': latest.get('key_index', 0),
            'scale': latest.get('scale', 'Major'),
            'confidence': latest.get('confidence', 0),
            'from_cache': True,
            'key_timeline': timeline,
            'title': cached.get('title', ''),
        }
        self._send_tone_midi(result)
        return result
    
    @staticmethod
    def _save_tone_to_cache(url, result, title=""):
        """
        Lưu kết quả dò tone vào cache (format chuẩn).
        
        Args:
            url: YouTube URL
            result: dict chứa key_display, key_index, scale, confidence, ...
            title: Video title (optional)
        """
        cache_data = {
            'primary_key': result['key_display'],
            'title': title,
            'key_timeline': [{
                'time': 0,
                'key_display': result['key_display'],
                'key_index': result['key_index'],
                'scale': result['scale'],
                'confidence': result.get('confidence', 0),
                'bpm': result.get('bpm', 0),
                'duration': result.get('duration', 0),
            }]
        }
        ToneCacheManager.save_tone(url, cache_data)

    def detect_tone(self, duration=10, on_complete=None, on_error=None, on_progress=None):
        """
        Dò tone bài hát đang phát (single-shot). Kiểm tra cache trước.
        """
        def _detect():
            try:

                # Kiểm tra cache nếu có YouTube URL (dùng DRY helper)
                if self.current_youtube_url:
                    cached_result = self._check_tone_cache(self.current_youtube_url)
                    if cached_result:
                        if on_complete:
                            on_complete(cached_result)
                        return
                
                # Dò tone: ưu tiên YouTube download (audio sạch) > loopback
                result = None
                if self.current_youtube_url:
                    # YouTube download cho kết quả chính xác hơn loopback
                    # (loopback bị mất bass → F/C yếu, gây sai key)
                    print(f"🎵 [DÒ TONE] Dùng YouTube audio (chất lượng tốt hơn loopback)...")
                    try:
                        result = ToneDetector.detect_key_from_youtube(
                            self.current_youtube_url, duration_limit=30
                        )
                    except Exception as e:
                        print(f"⚠️ [DÒ TONE] YouTube download thất bại: {e}")
                        print(f"🔄 [DÒ TONE] Fallback sang loopback...")
                
                # Fallback: loopback nếu không có URL hoặc YouTube download thất bại
                if not result:
                    result = ToneDetector.detect_key_from_system_audio(
                        duration=duration,
                        on_progress=on_progress
                    )
                
                if result:
                    self._send_tone_midi(result)
                    
                    # Lưu cache nếu có YouTube URL (dùng DRY helper)
                    if self.current_youtube_url:
                        SystemEngine._save_tone_to_cache(self.current_youtube_url, result)
                    
                    if on_complete:
                        on_complete(result)
                else:
                    if on_error:
                        on_error("Không thể dò tone. Hãy đảm bảo đang phát nhạc.")
            except Exception as e:
                print(f"❌ [DÒ TONE] Lỗi: {e}")
                if on_error:
                    on_error(str(e))
            finally:
                MemoryGuard.force_cleanup()  # gc + clear librosa cache + trim RAM
        
        threading.Thread(target=_detect, daemon=True).start()
    
    def detect_tone_from_youtube(self, url=None, on_complete=None, on_error=None, on_progress=None):
        """
        Dò tone từ YouTube URL. Tải audio → nhận diện key/scale → gửi MIDI → cache.
        
        Args:
            url: YouTube URL (nếu None, dùng self.current_youtube_url)
            on_complete: Callback(result_dict) khi hoàn thành
            on_error: Callback(error_msg) khi lỗi
            on_progress: Callback(status_text) cập nhật trạng thái
        """
        youtube_url = url or self.current_youtube_url
        if not youtube_url:
            if on_error:
                on_error("Không có YouTube URL để dò tone.")
            return
        
        def _detect():
            try:
                # 1. Kiểm tra cache trước (dùng DRY helper)
                if on_progress:
                    on_progress("Đang kiểm tra cache...")
                
                cached_result = self._check_tone_cache(youtube_url)
                if cached_result:
                    if on_complete:
                        on_complete(cached_result)
                    return
                
                # 2. Tải audio từ YouTube
                if on_progress:
                    on_progress("Đang tải audio từ YouTube...")
                
                print(f"🎵 [LẤY TONE YT] Bắt đầu dò tone từ YouTube...")
                print(f"🔗 URL: {youtube_url}")
                
                result = ToneDetector.detect_key_from_youtube(youtube_url, duration_limit=30)
                
                if result:
                    # 3. Gửi MIDI
                    self._send_tone_midi(result)
                    
                    # 4. Lưu cache (dùng DRY helper)
                    SystemEngine._save_tone_to_cache(youtube_url, result)
                    
                    if on_complete:
                        on_complete(result)
                else:
                    if on_error:
                        on_error("Không thể dò tone từ YouTube. Hãy thử lại.")
            except Exception as e:
                print(f"❌ [LẤY TONE YT] Lỗi: {e}")
                import traceback
                traceback.print_exc()
                if on_error:
                    on_error(str(e))
            finally:
                MemoryGuard.force_cleanup()  # gc + clear librosa cache + trim RAM
        
        threading.Thread(target=_detect, daemon=True).start()

    def auto_detect_youtube_timeline(self, url, on_complete=None, on_error=None, on_progress=None):
        """
        Tự động dò tone toàn bài YouTube → lưu timeline chuyển tone vào manual_timelines.json.
        
        Tải toàn bộ audio → chia segment 10s → dò tone mỗi segment → voting window →
        phát hiện chuyển tone → lưu thành timeline (giống nhập thủ công).
        
        Args:
            url: YouTube URL
            on_complete: Callback(timeline_data) khi hoàn thành
                         timeline_data = {url, title, timeline: [{time, key_display, key_index, scale}, ...]}
            on_error: Callback(error_msg) khi lỗi
            on_progress: Callback(status_text) cập nhật trạng thái
        """
        if not url:
            if on_error:
                on_error("Không có YouTube URL.")
            return
        
        def _detect_full():
            self._auto_tone_running = True
            try:
                import librosa
                import numpy as np
                from PySide6.QtCore import QTimer
                
                SEGMENT_DURATION = 15  # giây per segment (15s như batch_detect_tone.py)
                
                # 1. Lấy title video
                if on_progress:
                    on_progress("Đang lấy thông tin video...")
                
                video_title = "Bài hát không tên"
                try:
                    import yt_dlp
                    ydl_opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
                    if FFMPEG_LOCATION:
                        ydl_opts['ffmpeg_location'] = FFMPEG_LOCATION
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        video_title = info.get('title', video_title)
                except Exception as e:
                    print(f"⚠️ [AUTO TIMELINE] Không lấy được title: {e}")
                
                # 2. Tải audio
                if on_progress:
                    on_progress(f"Đang tải audio...")
                
                print(f"🎵 [AUTO TIMELINE] Bắt đầu dò tone toàn bài: {video_title}")
                print(f"🔗 URL: {url}")
                
                scoring_engine = ScoringEngine()
                audio_path = scoring_engine.download_youtube_audio(url)
                
                if not audio_path:
                    if on_error:
                        on_error("Không thể tải audio từ YouTube.")
                    return
                
                try:
                    # 3. Load toàn bộ audio
                    if on_progress:
                        on_progress("Đang load file âm thanh...")
                    
                    audio_data, sr = librosa.load(audio_path, sr=22050, mono=True)
                    total_seconds = len(audio_data) / sr
                    
                    segment_samples = int(SEGMENT_DURATION * sr)
                    num_segments = int(np.ceil(total_seconds / SEGMENT_DURATION))
                    
                    print(f"✅ [AUTO TIMELINE] Audio: {total_seconds:.1f}s, {num_segments} segments (15s/segment)")
                    
                    # 4. Phân tích dò tone từ ToneDetector
                    timeline_entries = ToneDetector.detect_timeline_advanced(audio_data, sr, on_progress)
                    del audio_data  # Giải phóng audio data (~vài chục MB)
                    gc.collect()
                    
                    if not timeline_entries:
                        if on_error:
                            on_error("Không phát hiện được tone nào trong bài hát.")
                        return
                    
                    # 6. Lưu timeline
                    if on_progress:
                        on_progress("Đang lưu kết quả...")
                    
                    success = ManualToneTimeline.save_timeline(url, video_title, timeline_entries)
                    
                    if success:
                        print(f"✅ [AUTO TIMELINE] Đã lưu: {video_title} ({len(timeline_entries)} entries)")
                    
                    # 7. Lưu vào ToneCacheManager
                    cache_timeline = []
                    for e in timeline_entries:
                        cache_entry = dict(e)
                        if 'confidence' not in cache_entry:
                            cache_entry['confidence'] = 0.8
                        cache_timeline.append(cache_entry)
                    
                    cache_data = {
                        'primary_key': timeline_entries[0]['key_display'],
                        'key_timeline': cache_timeline
                    }
                    ToneCacheManager.save_tone(url, cache_data)
                    
                    # 8. Gửi MIDI cho key đầu tiên và bật replay
                    first_key = timeline_entries[0]
                    self._send_tone_midi({
                        'key_display': first_key['key_display'],
                        'key_index': first_key['key_index'],
                        'scale': first_key['scale']
                    })
                    
                    self.tone_detection_active = False
                    time.sleep(0.2)
                    self._replay_manual_timeline(timeline_entries)
                    
                    # 9. Callback
                    timeline_data = {
                        'url': url,
                        'title': video_title,
                        'timeline': timeline_entries,
                        'total_duration': total_seconds
                    }
                    
                    if on_complete:
                        on_complete(timeline_data)
                    
                finally:
                    scoring_engine.cleanup_temp_file()
                    del scoring_engine
                    MemoryGuard.force_cleanup()  # gc + clear librosa cache + trim RAM
                    
            except Exception as e:
                print(f"❌ [AUTO TIMELINE] Lỗi: {e}")
                import traceback
                traceback.print_exc()
                if on_error:
                    on_error(str(e))
            finally:
                self._auto_tone_running = False
        
        threading.Thread(target=_detect_full, daemon=True).start()

    def _send_tone_midi(self, result):
        """Gửi MIDI CC cho key/scale đến Auto-Tune

        Đọc key_midi_map + scale_midi_map từ app_config.json.
        Sửa file config → restart app để điều chỉnh giá trị MIDI gửi đến plugin.
        """
        # Lấy key_display, bỏ "m" suffix nếu có (Cm → C, Am → A)
        key_display = result.get("key_display", "C")
        key_root = key_display.replace("m", "") if key_display.endswith("m") and not key_display.endswith("#m") else key_display
        if key_display.endswith("#m"):
            key_root = key_display[:-1]  # "C#m" → "C#"

        key_midi_map = AppConfig.get_key_midi_map()
        scale_midi_map = AppConfig.get_scale_midi_map()

        key_midi = key_midi_map.get(key_root, 0)
        scale = result.get("scale", "Major")
        scale_midi = scale_midi_map.get(scale, 13)

        midi_cc = AppConfig.get_midi_cc()
        cc_key_root = midi_cc.get("key_root", 34)
        cc_key_scale = midi_cc.get("key_scale", 35)

        self.send_midi(cc_key_root, key_midi)
        time.sleep(0.05)
        self.send_midi(cc_key_scale, scale_midi)
        print(f"📤 [TONE] MIDI → CC{cc_key_root}={key_midi} (Key={key_root}), CC{cc_key_scale}={scale_midi} (Scale={scale})")
    
    def stop_tone_detection(self):
        """Dừng dò tone liên tục"""
        if self.tone_detection_active:
            print("⏹️ [TONE] Dừng dò tone liên tục")
        self.tone_detection_active = False
    
    # ============================================================
    # AutoKey: Dò tone liên tục toàn bài hát (tương tự Auto-Key)
    # ============================================================
    
    def start_autokey(self, on_key_update=None, segment_duration=5):
        """
        Bắt đầu dò tone liên tục (AutoKey mode).
        Thu âm loopback liên tục, phân tích mỗi segment_duration giây,
        gửi MIDI khi phát hiện chuyển tone.
        
        Args:
            on_key_update: Callback(result_dict) gọi mỗi khi có kết quả mới
            segment_duration: Thời lượng mỗi segment phân tích (giây)
        """
        if self.autokey_active:
            print("⚠️ [AUTOKEY] Đã đang chạy, bỏ qua.")
            return
        
        self.autokey_active = True
        self.on_tone_detected_callback = on_key_update
        
        def _autokey_loop():
            import numpy as np
            from collections import Counter
            
            VOTING_WINDOW = ToneDetector.VOTING_WINDOW
            current_key = None
            current_confidence = 0
            recent_keys = []
            
            # Khởi tạo COM cho thread này
            com_initialized = False
            try:
                hr = ctypes.windll.ole32.CoInitializeEx(None, 0)
                com_initialized = (hr == 0)
            except Exception:
                pass
            
            try:
                # Import pyaudiowpatch (thay thế soundcard)
                try:
                    import pyaudiowpatch as pyaudio
                except ImportError:
                    print("❌ [AUTOKEY] pyaudiowpatch không khả dụng. Cài đặt: pip install pyaudiowpatch")
                    self.autokey_active = False
                    return
                
                pa = pyaudio.PyAudio()
                
                # Tìm WASAPI loopback device (giống recorder_worker.py)
                wasapi_info = None
                for i in range(pa.get_host_api_count()):
                    info = pa.get_host_api_info_by_index(i)
                    if "wasapi" in info.get("name", "").lower():
                        wasapi_info = info
                        break
                
                if not wasapi_info:
                    print("❌ [AUTOKEY] Không tìm thấy WASAPI host API!")
                    pa.terminate()
                    self.autokey_active = False
                    return
                
                loopback_dev = None
                for i in range(pa.get_device_count()):
                    dev = pa.get_device_info_by_index(i)
                    if dev.get("isLoopbackDevice", False):
                        if dev.get("hostApi") == wasapi_info["index"]:
                            loopback_dev = dev
                            break
                
                if not loopback_dev:
                    print("❌ [AUTOKEY] Không tìm thấy thiết bị loopback!")
                    pa.terminate()
                    self.autokey_active = False
                    return
                
                SAMPLE_RATE = int(loopback_dev["defaultSampleRate"])
                channels = loopback_dev["maxInputChannels"]
                chunk_size = 1024
                
                print("=" * 60)
                print(f"🎹 [AUTOKEY] Bắt đầu — segment={segment_duration}s, device={loopback_dev['name']}")
                
                # ROLLING AUDIO BUFFER: pre-allocated ring buffer (tránh tạo array mới mỗi iteration)
                RECORD_CHUNK = segment_duration
                MAX_BUFFER_SEC = 30
                MAX_BUFFER_FRAMES = MAX_BUFFER_SEC * SAMPLE_RATE
                audio_buffer = np.zeros(MAX_BUFFER_FRAMES, dtype=np.float32)
                write_pos = 0  # Vị trí ghi hiện tại trong ring buffer
                
                print(f"🎹 [AUTOKEY] Rolling buffer: chunk={RECORD_CHUNK}s, max={MAX_BUFFER_SEC}s")
                mem = MemoryProfiler("AUTOKEY")
                gc_counter = 0  # Đếm số iteration để gc.collect() định kỳ
                
                stream = pa.open(
                    format=pyaudio.paFloat32,
                    channels=1,
                    rate=SAMPLE_RATE,
                    input=True,
                    input_device_index=loopback_dev["index"],
                    frames_per_buffer=chunk_size
                )
                
                try:
                    while self.autokey_active:
                        try:
                            # Thu âm chunk mới
                            frames_needed = RECORD_CHUNK * SAMPLE_RATE
                            chunks = []
                            frames_read = 0
                            while frames_read < frames_needed and self.autokey_active:
                                data = stream.read(chunk_size, exception_on_overflow=False)
                                chunk_np = np.frombuffer(data, dtype=np.float32).copy()  # Copy để giải phóng raw buffer
                                chunks.append(chunk_np)
                                frames_read += len(chunk_np)
                            
                            if not self.autokey_active:
                                break
                            
                            chunk = np.concatenate(chunks)
                            del chunks  # Giải phóng list chunks ngay lập tức
                            chunk = np.nan_to_num(chunk, nan=0.0, posinf=0.0, neginf=0.0)
                            
                            # Kiểm tra im lặng
                            rms = np.sqrt(np.mean(chunk ** 2))
                            if rms < 0.001:
                                if on_key_update:
                                    try:
                                        on_key_update({
                                            'status': 'listening',
                                            'key_display': current_key or '...',
                                            'confidence': 0,
                                            'message': 'Đang lắng nghe...'
                                        })
                                    except Exception:
                                        pass
                                continue
                            
                            # Thêm vào rolling buffer (in-place, không tạo array mới)
                            chunk_len = len(chunk)
                            if write_pos + chunk_len <= MAX_BUFFER_FRAMES:
                                # Còn chỗ: ghi trực tiếp
                                audio_buffer[write_pos:write_pos + chunk_len] = chunk
                                write_pos += chunk_len
                            else:
                                # Đầy: shift buffer sang trái, ghi chunk vào cuối
                                keep = MAX_BUFFER_FRAMES - chunk_len
                                audio_buffer[:keep] = audio_buffer[write_pos - keep:write_pos]
                                audio_buffer[keep:keep + chunk_len] = chunk
                                write_pos = MAX_BUFFER_FRAMES
                            del chunk  # Giải phóng chunk tạm
                            
                            buffer_sec = write_pos / SAMPLE_RATE
                            print(f"📦 [AUTOKEY] Buffer: {buffer_sec:.1f}s")
                            mem.checkpoint(f"buffer={buffer_sec:.0f}s")
                            
                            # Phân tích phần buffer đã ghi
                            result = ToneDetector.detect_key_from_audio(audio_buffer[:write_pos], SAMPLE_RATE)
                            gc_counter += 1
                            if gc_counter % 2 == 0:  # Mỗi 2 iteration (~10s) cleanup triệt để
                                MemoryGuard.force_cleanup()  # gc(2) + librosa cache + trim RAM
                            
                            if not result:
                                continue
                            
                            new_key = result['key_display']
                            confidence = result.get('confidence', 0)
                            
                            # Voting window
                            recent_keys.append(new_key)
                            if len(recent_keys) > VOTING_WINDOW:
                                recent_keys.pop(0)
                            
                            vote_counts = Counter(recent_keys)
                            voted_key = vote_counts.most_common(1)[0][0]
                            vote_ratio = vote_counts[voted_key] / len(recent_keys)
                            
                            # Quyết định chuyển tone
                            key_changed = False
                            if current_key is None:
                                current_key = voted_key
                                current_confidence = confidence
                                key_changed = True
                                print(f"🎹 [AUTOKEY] Key ban đầu: {voted_key} (conf={confidence:.2f})")
                            elif voted_key != current_key:
                                confidence_diff = confidence - current_confidence
                                if vote_ratio >= 0.67 and confidence_diff > -ToneDetector.KEY_CHANGE_THRESHOLD:
                                    print(f"🔄 [AUTOKEY] {current_key} → {voted_key} "
                                          f"(vote={vote_ratio:.0%}, conf={confidence:.2f})")
                                    current_key = voted_key
                                    current_confidence = confidence
                                    key_changed = True
                            
                            # Gửi MIDI khi chuyển tone
                            if key_changed:
                                self._send_tone_midi(result)
                            
                            # Callback UI luôn (để cập nhật live indicator)
                            if on_key_update:
                                try:
                                    on_key_update({
                                        'status': 'detected',
                                        'key_display': current_key,
                                        'key_index': result['key_index'],
                                        'scale': result['scale'],
                                        'confidence': confidence,
                                        'raw_key': new_key,
                                        'voted_key': voted_key,
                                        'key_changed': key_changed
                                    })
                                except Exception:
                                    pass
                            
                        except Exception as e:
                            print(f"❌ [AUTOKEY] Lỗi segment: {e}")
                            time.sleep(1)
                finally:
                    mem.summary()
                    stream.stop_stream()
                    stream.close()
                    pa.terminate()
                
            except Exception as e:
                print(f"❌ [AUTOKEY] Lỗi khởi tạo: {e}")
                import traceback
                print(traceback.format_exc())
            finally:
                if com_initialized:
                    try:
                        ctypes.windll.ole32.CoUninitialize()
                    except Exception:
                        pass
                self.autokey_active = False
                print("🏁 [AUTOKEY] Đã dừng")
                MemoryGuard.force_cleanup()  # gc + clear librosa cache + trim RAM
                
                # Gửi callback cuối cùng để UI biết đã dừng
                if on_key_update:
                    try:
                        on_key_update({'status': 'stopped'})
                    except Exception:
                        pass
        
        self._autokey_thread = threading.Thread(target=_autokey_loop, daemon=True)
        self._autokey_thread.start()
    
    def stop_autokey(self):
        """Dừng AutoKey mode"""
        if self.autokey_active:
            print("⏹️ [AUTOKEY] Đang dừng...")
        self.autokey_active = False
        # Đợi thread dừng hẳn (đảm bảo PyAudio stream + COM được giải phóng)
        if self._autokey_thread:
            self._autokey_thread.join(timeout=6.0)  # Dài hơn vì stream.read() có thể block
            self._autokey_thread = None
    
    def detect_tone_continuous(self, url=None, segment_duration=5):
        """
        Dò tone liên tục suốt bài hát, phát hiện chuyển tone.
        Chạy trên thread hiện tại, dừng khi youtube_monitoring_active = False.
        
        Cải tiến:
        - Segment 5s (thay vì 10s) → phản hồi nhanh hơn
        - Voting window (3 segments) → tránh nhảy tone lung tung  
        - Confidence threshold (5%) → chỉ chuyển khi chắc chắn
        """
        from collections import Counter
        import numpy as np
        self.tone_detection_active = True
        current_key = None
        current_confidence = 0
        key_timeline = []
        recent_keys = []  # Voting window
        elapsed = 0
        VOTING_WINDOW = ToneDetector.VOTING_WINDOW
        
        print("=" * 60)
        print(f"🎵 [TONE CONTINUOUS] Bắt đầu dò tone liên tục (segment={segment_duration}s, voting={VOTING_WINDOW})")
        
        # ── Khởi tạo PyAudio + COM MỘT LẦN (tránh tạo/hủy mỗi segment → leak PortAudio native memory) ──
        com_initialized = False
        pa = None
        stream = None
        try:
            import ctypes
            hr = ctypes.windll.ole32.CoInitializeEx(None, 0)
            com_initialized = (hr == 0)
        except Exception:
            pass
        
        try:
            import pyaudiowpatch as pyaudio
        except ImportError:
            print("❌ [TONE CONTINUOUS] pyaudiowpatch không khả dụng")
            self.tone_detection_active = False
            return
        
        try:
            pa = pyaudio.PyAudio()
            
            # Tìm WASAPI loopback device
            wasapi_info = None
            for i in range(pa.get_host_api_count()):
                info = pa.get_host_api_info_by_index(i)
                if "wasapi" in info.get("name", "").lower():
                    wasapi_info = info
                    break
            
            if not wasapi_info:
                print("❌ [TONE CONTINUOUS] Không tìm thấy WASAPI host API!")
                self.tone_detection_active = False
                return
            
            loopback_dev = None
            for i in range(pa.get_device_count()):
                dev = pa.get_device_info_by_index(i)
                if dev.get("isLoopbackDevice", False):
                    if dev.get("hostApi") == wasapi_info["index"]:
                        loopback_dev = dev
                        break
            
            if not loopback_dev:
                print("❌ [TONE CONTINUOUS] Không tìm thấy thiết bị loopback!")
                self.tone_detection_active = False
                return
            
            device_sr = int(loopback_dev["defaultSampleRate"])
            chunk_size = 1024
            
            stream = pa.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=device_sr,
                input=True,
                input_device_index=loopback_dev["index"],
                frames_per_buffer=chunk_size
            )
            
            print(f"✅ [TONE CONTINUOUS] Loopback: {loopback_dev['name']}, sr={device_sr}")
            
            # ── Vòng lặp chính: thu âm + dò tone per segment ──
            _seg_count = 0
            while self.tone_detection_active and self.youtube_monitoring_active:
                try:
                    # Thu âm segment_duration giây qua stream đã mở
                    audio_chunks = []
                    frames_needed = segment_duration * device_sr
                    frames_read = 0
                    while frames_read < frames_needed and self.tone_detection_active:
                        data = stream.read(chunk_size, exception_on_overflow=False)
                        chunk_np = np.frombuffer(data, dtype=np.float32)
                        audio_chunks.append(chunk_np)
                        frames_read += len(chunk_np)
                    
                    if not self.tone_detection_active:
                        break
                    
                    audio_data = np.concatenate(audio_chunks)
                    del audio_chunks
                    audio_data = np.nan_to_num(audio_data, nan=0.0, posinf=0.0, neginf=0.0)
                    
                    # Kiểm tra im lặng
                    rms = np.sqrt(np.mean(audio_data ** 2))
                    if rms < 0.001:
                        del audio_data
                        print(f"   ⚠️ [TONE] t={elapsed}s: Không phát hiện âm thanh")
                        elapsed += segment_duration
                        continue
                    
                    # Dò tone trực tiếp (reuse audio_data, không tạo PyAudio mới)
                    result = ToneDetector.detect_key_from_audio(audio_data, device_sr)
                    del audio_data
                    
                    # Periodic cleanup (mỗi 3 segment ~ 15s)
                    _seg_count += 1
                    if _seg_count % 3 == 0:
                        MemoryGuard.force_cleanup()
                    
                    if result:
                        new_key = result['key_display']
                        confidence = result.get('confidence', 0)
                        
                        # Thêm vào voting window
                        recent_keys.append(new_key)
                        if len(recent_keys) > VOTING_WINDOW:
                            recent_keys.pop(0)
                        
                        # Voting: key xuất hiện nhiều nhất trong window
                        vote_counts = Counter(recent_keys)
                        voted_key = vote_counts.most_common(1)[0][0]
                        vote_ratio = vote_counts[voted_key] / len(recent_keys)
                        
                        # Ghi vào timeline (luôn ghi raw detection)
                        entry = {
                            'time': elapsed,
                            'key_display': voted_key,
                            'key_index': result['key_index'],
                            'scale': result['scale'],
                            'confidence': round(confidence, 3)
                        }
                        key_timeline.append(entry)
                        # Giữ tối đa 500 entries gần nhất (~ 40 phút ở 5s/segment)
                        if len(key_timeline) > 500:
                            del key_timeline[:len(key_timeline) - 500]
                        
                        # Phát hiện chuyển tone với temporal smoothing + confidence threshold
                        should_change = False
                        if current_key is None:
                            should_change = True
                        elif voted_key != current_key:
                            confidence_diff = confidence - current_confidence
                            if vote_ratio >= 0.67 and confidence_diff > -ToneDetector.KEY_CHANGE_THRESHOLD:
                                should_change = True
                                print(f"🔄 [TONE] CHUYỂN TONE: {current_key} → {voted_key} "
                                      f"(t={elapsed}s, vote={vote_ratio:.0%}, conf={confidence:.2f}, Δ={confidence_diff:+.3f})")
                            else:
                                print(f"   ⏸️ [TONE] t={elapsed}s: raw={new_key} nhưng giữ {current_key} "
                                      f"(vote={vote_ratio:.0%}, Δconf={confidence_diff:+.3f})")
                        
                        if should_change:
                            if current_key is None:
                                print(f"🎵 [TONE] Key ban đầu: {voted_key} (conf={confidence:.2f})")
                            
                            current_key = voted_key
                            current_confidence = confidence
                            
                            self._send_tone_midi(result)
                            
                            if self.on_tone_detected_callback:
                                try:
                                    self.on_tone_detected_callback(result)
                                except Exception:
                                    pass
                        elif voted_key == current_key:
                            print(f"   🎵 [TONE] t={elapsed}s: {voted_key} (stable, conf={confidence:.2f})")
                        
                        elapsed += segment_duration
                    else:
                        print(f"   ⚠️ [TONE] t={elapsed}s: Không phát hiện âm thanh")
                        elapsed += segment_duration
                        
                except Exception as e:
                    print(f"❌ [TONE CONTINUOUS] Lỗi segment: {e}")
                    elapsed += segment_duration
        
        finally:
            # Cleanup PyAudio + COM MỘT LẦN khi kết thúc
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            if pa:
                try:
                    pa.terminate()
                except Exception:
                    pass
            if com_initialized:
                try:
                    import ctypes
                    ctypes.windll.ole32.CoUninitialize()
                except Exception:
                    pass
        
        # Kết thúc → lưu cache
        self.tone_detection_active = False
        
        if key_timeline and url:
            from collections import Counter
            key_counts = Counter(e['key_display'] for e in key_timeline)
            primary_key = key_counts.most_common(1)[0][0]
            
            cache_data = {
                'primary_key': primary_key,
                'key_timeline': key_timeline
            }
            ToneCacheManager.save_tone(url, cache_data)
            print(f"💾 [TONE] Đã lưu cache: primary={primary_key}, {len(key_timeline)} segments")
        
        print("🏁 [TONE CONTINUOUS] Kết thúc dò tone liên tục")
        MemoryGuard.force_cleanup()
    
    def _replay_cached_timeline(self, cached_data):
        """
        Replay timeline tone từ cache: gửi MIDI đúng thời điểm.
        Sử dụng Windows Media Control API để đồng bộ hoàn hảo với Browser Play/Pause/Seek.
        Chạy trong thread riêng.
        """
        timeline = cached_data.get('key_timeline', [])
        if not timeline:
            return
        
        self.tone_detection_active = True
        primary_key = cached_data.get('primary_key', timeline[0]['key_display'])
        print(f"▶️ [TONE REPLAY] Replay từ cache: primary={primary_key}, {len(timeline)} segments")
        
        # Sắp xếp timeline để chắc chắn
        timeline = sorted(timeline, key=lambda x: x['time'])
        
        def _replay():
            current_key = None
            last_idx = -1
            _gc_counter = 0  # Periodic GC counter
            
            # Nếu win_media_available thì đồng bộ 100%, nếu không fallback absolute time
            fallback_enabled = not _WIN_MEDIA_AVAILABLE
            if fallback_enabled:
                print("⚠️ [REPLAY] Không có winrt, dùng fallback absolute time")
                start_mono = time.monotonic()
                paused_total = 0
            
            while self.tone_detection_active:
                if fallback_enabled:
                    # Logic Fallback
                    elapsed = (time.monotonic() - start_mono) - paused_total
                    if not self.media_monitor.is_playing:
                        # Nếu module MediaMonitor giả lập pause hoặc có trạng thái
                        paused_total += 0.1
                else:
                    # Lấy vị trí từ Browser
                    if not self.media_monitor.is_playing:
                        time.sleep(0.1)
                        continue
                        
                    elapsed = self.media_monitor.current_position
                    
                # Tìm entry cuối cùng LỚN HƠN elapsed (logic áp dụng cho cả seek tua tới tua lui)
                # Ta muốn key hiện tại là key có thời gian <= elapsed gần nhất
                target_idx = -1
                for i in range(len(timeline)):
                    if timeline[i]['time'] <= elapsed:
                        target_idx = i
                    else:
                        break
                
                # Cập nhật MIDI nếu index thay đổi (và index >= 0)
                if target_idx >= 0 and target_idx != last_idx:
                    entry = timeline[target_idx]
                    new_key = entry['key_display']
                    
                    if new_key != current_key or last_idx == -1:
                        current_key = new_key
                        self._send_tone_midi(entry)
                        print(f"▶️ [REPLAY] t={elapsed:.1f}s (target={entry['time']}s): {new_key}")
                        
                        if self.on_tone_detected_callback:
                            try:
                                self.on_tone_detected_callback(entry)
                            except Exception:
                                pass
                                
                    last_idx = target_idx
                
                # Periodic GC: mỗi 300 iterations (~30s) thu hồi COM/WinRT refs
                _gc_counter += 1
                if _gc_counter % 300 == 0:
                    gc.collect(0)
                
                time.sleep(0.1) # Loop cực nhẹ
            
            print(f"🏁 [TONE REPLAY] Kết thúc replay")
        
        threading.Thread(target=_replay, daemon=True).start()
    
    def _replay_manual_timeline(self, timeline):
        """
        Replay timeline tone thủ công: gửi MIDI đúng thời điểm.
        Sử dụng Windows Media Control API để đồng bộ cực kỳ chính xác.
        Chạy trong thread riêng.
        
        Args:
            timeline: list of {time, key_display, key_index, scale}
        """
        if not timeline:
            return
        
        self.tone_detection_active = True
        print(f"▶️ [MANUAL REPLAY] Bắt đầu replay thủ công: {len(timeline)} entries")
        
        # Phải sort timeline để logic chạy seek cho chuẩn
        timeline = sorted(timeline, key=lambda x: x['time'])
        
        def _replay():
            current_key = None
            last_idx = -1
            _gc_counter = 0  # Periodic GC counter
            
            fallback_enabled = not _WIN_MEDIA_AVAILABLE
            if fallback_enabled:
                print("⚠️ [MANUAL REPLAY] Không có winrt, dùng fallback absolute time")
                start_mono = time.monotonic()
                paused_total = 0
            
            while self.tone_detection_active:
                if fallback_enabled:
                    elapsed = (time.monotonic() - start_mono) - paused_total
                    if not self.media_monitor.is_playing:
                        paused_total += 0.1
                else:
                    if not self.media_monitor.is_playing:
                        time.sleep(0.1)
                        continue
                    
                    elapsed = self.media_monitor.current_position
                
                # Tìm Tone ứng với elapsed
                target_idx = -1
                for i in range(len(timeline)):
                    if timeline[i]['time'] <= elapsed:
                        target_idx = i
                    else:
                        break
                        
                if target_idx >= 0 and target_idx != last_idx:
                    entry = timeline[target_idx]
                    new_key = entry['key_display']
                    
                    if new_key != current_key or last_idx == -1:
                        current_key = new_key
                        self._send_tone_midi(entry)
                        time_str = ManualToneTimeline.seconds_to_time_str(entry['time'])
                        print(f"▶️ [MANUAL REPLAY] t={elapsed:.1f}s (trigger={time_str}): {new_key}")
                        
                        if self.on_tone_detected_callback:
                            try:
                                self.on_tone_detected_callback(entry)
                            except Exception:
                                pass
                                
                    last_idx = target_idx
                
                # Periodic GC: mỗi 300 iterations (~30s) thu hồi COM/WinRT refs
                _gc_counter += 1
                if _gc_counter % 300 == 0:
                    gc.collect(0)
                
                time.sleep(0.1)
            
            print(f"🏁 [MANUAL REPLAY] Kết thúc replay thủ công")
        
        threading.Thread(target=_replay, daemon=True).start()

