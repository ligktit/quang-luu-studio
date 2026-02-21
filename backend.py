import os
import json
import threading
import time
import subprocess
import psutil
import mido
import pyautogui
import win32gui
import win32con
import sys
import ctypes

# Patch numpy.fromstring TRƯỚC khi import soundcard
# soundcard dùng np.fromstring(binary) đã bị xóa trong numpy 2.x
import numpy as np
_orig_np_fromstring = np.fromstring
def _patched_fromstring(string, dtype=float, count=-1, *, sep='', like=None):
    if not sep:
        # Binary mode → dùng frombuffer (nhận mọi buffer-like object kể cả cffi.buffer)
        return np.frombuffer(string, dtype=dtype, count=count)
    return _orig_np_fromstring(string, dtype=dtype, count=count, sep=sep)
np.fromstring = _patched_fromstring

# Import soundcard ở module level (main thread) để COM init thành công
try:
    import soundcard as sc
    _SOUNDCARD_AVAILABLE = True
except Exception:
    sc = None
    _SOUNDCARD_AVAILABLE = False

# Suppress soundcard warnings (data discontinuity spam)
import warnings
warnings.filterwarnings('ignore', message='data discontinuity')

# --- CẤU HÌNH CỐT LÕI ---
SETTINGS_FILE = "settings.json"
SONGS_FILE = "saved_songs.json"
ACTIVATION_FILE = "activation.json"
MIDI_PORT_NAME = "QuangLuuMIDI"


class ConfigManager:
    @staticmethod
    def load():
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f: return json.load(f)
            except: return None
        return None

    @staticmethod
    def save(s1, web, auto_launch_studio_one=False, midi_port_name=None):
        settings = {
            "studio_one_path": s1, 
            "browser_path": web,
            "auto_launch_studio_one": auto_launch_studio_one
        }
        # Thêm MIDI port name nếu được cung cấp
        if midi_port_name:
            settings["midi_port_name"] = midi_port_name
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4)

# --- CLASS QUẢN LÝ MIDI ---
class MidiHandler:
    def __init__(self):
        self.outport = None
        self._warned = False
        self.connect()
    def connect(self):
        try:
            outputs = mido.get_output_names()
            port_name = next((name for name in outputs if MIDI_PORT_NAME in name), None)
            if port_name:
                self.outport = mido.open_output(port_name)
                print(f"✅ MIDI Connected: {port_name}")
                self._warned = False
                return True
            else:
                if not self._warned:
                    print(f"⚠️ Lỗi: Không tìm thấy cổng '{MIDI_PORT_NAME}'. Hãy mở loopMIDI!")
                    self._warned = True
                return False
        except Exception as e:
            if not self._warned:
                print(f"⚠️ Lỗi MIDI: {e}")
                self._warned = True
            return False
    def send_cc(self, cc_number, value, channel=0):
        """
        Gửi MIDI Control Change message.
        
        Args:
            cc_number (int): Số CC parameter (0-127)
            value (int): Giá trị CC (0-127)
            channel (int, optional): MIDI channel (0-15). Mặc định là 0.
        
        Safety Check: Chỉ gửi nếu self.outport hợp lệ.
        """
        if self.outport:
            msg = mido.Message('control_change', channel=channel, control=cc_number, value=value)
            self.outport.send(msg)

TONE_CACHE_FILE = "tone_cache.json"

class ToneCacheManager:
    """Quản lý cache kết quả dò tone theo YouTube video ID"""
    
    @staticmethod
    def _extract_video_id(url):
        """Trích xuất video ID từ YouTube URL"""
        import re
        if not url:
            return None
        patterns = [
            r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
            r'(?:embed/)([a-zA-Z0-9_-]{11})',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    @staticmethod
    def load_cache():
        if os.path.exists(TONE_CACHE_FILE):
            try:
                with open(TONE_CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    @staticmethod
    def save_cache(cache):
        try:
            with open(TONE_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            return True
        except:
            return False
    
    # Cache TTL: 30 ngày
    CACHE_TTL_DAYS = 30
    # Confidence tối thiểu để lưu cache
    MIN_CACHE_CONFIDENCE = 0.3
    
    @staticmethod
    def get_cached_tone(url):
        """Tra cứu cache theo YouTube URL, trả về dict hoặc None. Kiểm tra TTL."""
        video_id = ToneCacheManager._extract_video_id(url)
        if not video_id:
            return None
        cache = ToneCacheManager.load_cache()
        entry = cache.get(video_id)
        if entry:
            # Kiểm tra TTL
            cached_at = entry.get('cached_at', 0)
            if cached_at > 0:
                age_days = (time.time() - cached_at) / 86400
                if age_days > ToneCacheManager.CACHE_TTL_DAYS:
                    print(f"⏰ [CACHE] Hết hạn ({age_days:.0f} ngày), dò lại...")
                    return None
            return entry
        return None
    
    @staticmethod
    def save_tone(url, result):
        """Lưu kết quả dò tone vào cache.
        Không lưu nếu confidence trung bình < MIN_CACHE_CONFIDENCE.
        result = {
            'primary_key': 'Dm',
            'key_timeline': [{time, key_display, key_index, scale, confidence}, ...],
            'url': url
        }
        """
        video_id = ToneCacheManager._extract_video_id(url)
        if not video_id:
            return False
        
        # Kiểm tra confidence trung bình
        timeline = result.get('key_timeline', [])
        if timeline:
            avg_conf = sum(e.get('confidence', 0) for e in timeline) / len(timeline)
            if avg_conf < ToneCacheManager.MIN_CACHE_CONFIDENCE:
                print(f"⚠️ [CACHE] Confidence quá thấp ({avg_conf:.3f} < {ToneCacheManager.MIN_CACHE_CONFIDENCE}), không lưu cache")
                return False
        
        cache = ToneCacheManager.load_cache()
        result["detected_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        result["cached_at"] = time.time()
        result["url"] = url
        cache[video_id] = result
        return ToneCacheManager.save_cache(cache)

class SystemEngine:
    def __init__(self, settings=None):
        self.settings = settings or {}
        
        # Khởi tạo MidiHandler
        self.midi_handler = MidiHandler()
        
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
        """Ngắt kết nối MIDI"""
        if self.midi_handler.outport:
            try:
                self.midi_handler.outport.close()
                print("✅ Đã ngắt kết nối MIDI")
            except Exception as e:
                print(f"⚠️ Lỗi khi ngắt kết nối MIDI: {e}")
            finally:
                self.midi_handler.outport = None

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
            except:
                pass
        elif not result and on_failed:
            try:
                on_failed()
            except:
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
                except: pass
        threading.Thread(target=run, daemon=True).start()

    def launch_app(self, path, is_web=False):
        if not path or not os.path.exists(path): return
        
        if is_web:
             threading.Thread(target=lambda: subprocess.Popen([path, "youtube.com"]), daemon=True).start()
        else:
            # Logic mở file .song hoặc .exe
            if path.lower().endswith(".song"):
                try: os.startfile(path)
                except: pass
            else:
                running = False
                for p in psutil.process_iter(['name']):
                    if "Studio One" in p.info['name']: running = True
                if not running:
                    threading.Thread(target=lambda: subprocess.Popen(path), daemon=True).start()

    def kill_app(self):
        try: os.system('taskkill /F /IM "Studio One.exe"')
        except: pass
    
    def open_youtube_url(self, url, on_video_end_callback=None, on_tone_detected=None):
        """
        Mở YouTube URL trong browser, tự động dò tone và chấm điểm khi kết thúc
        
        Args:
            url: YouTube URL
            on_video_end_callback: Callback(result) khi video kết thúc
            on_tone_detected: Callback(result) khi phát hiện tone/chuyển tone
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
                    except:
                        print(f"⚠️ Không thể mở URL: {url}")
            else:
                try:
                    os.startfile(url)
                except:
                    print(f"⚠️ Không thể mở URL: {url}")
        
        threading.Thread(target=open_browser, daemon=True).start()
        
        # Tự động dò tone sau 5s delay
        def auto_detect_tone():
            print("🎵 [AUTO TONE] Đợi 5s cho nhạc bắt đầu phát...")
            time.sleep(5)
            
            # Kiểm tra cache trước
            cached = ToneCacheManager.get_cached_tone(url)
            if cached:
                print(f"✅ [AUTO TONE] Đã có cache: {cached.get('primary_key', '?')}")
                # Replay timeline từ cache
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
    
    def detect_tone(self, duration=10, on_complete=None, on_error=None, on_progress=None):
        """
        Dò tone bài hát đang phát (single-shot). Kiểm tra cache trước.
        """
        def _detect():
            try:
                # Kiểm tra cache nếu có YouTube URL
                if self.current_youtube_url:
                    cached = ToneCacheManager.get_cached_tone(self.current_youtube_url)
                    if cached:
                        print(f"✅ [DÒ TONE] Cache hit: {cached.get('primary_key', '?')}")
                        # Trả về primary key từ cache
                        timeline = cached.get('key_timeline', [])
                        if timeline:
                            latest = timeline[-1] if timeline else timeline[0]
                            result = {
                                'key_display': cached.get('primary_key', latest.get('key_display', 'C')),
                                'key_index': latest.get('key_index', 0),
                                'scale': latest.get('scale', 'Major'),
                                'confidence': latest.get('confidence', 0),
                                'from_cache': True,
                                'key_timeline': timeline
                            }
                            self._send_tone_midi(result)
                            if on_complete:
                                on_complete(result)
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
                    
                    # Lưu cache nếu có YouTube URL (confidence check nằm trong save_tone)
                    if self.current_youtube_url:
                        cache_data = {
                            'primary_key': result['key_display'],
                            'key_timeline': [{
                                'time': 0,
                                'key_display': result['key_display'],
                                'key_index': result['key_index'],
                                'scale': result['scale'],
                                'confidence': result.get('confidence', 0)
                            }]
                        }
                        ToneCacheManager.save_tone(self.current_youtube_url, cache_data)
                    
                    if on_complete:
                        on_complete(result)
                else:
                    if on_error:
                        on_error("Không thể dò tone. Hãy đảm bảo đang phát nhạc.")
            except Exception as e:
                print(f"❌ [DÒ TONE] Lỗi: {e}")
                if on_error:
                    on_error(str(e))
        
        threading.Thread(target=_detect, daemon=True).start()
    
    def _send_tone_midi(self, result):
        """Gửi MIDI CC cho key/scale đến Auto-Tune"""
        key_midi = ToneDetector.key_index_to_midi(result["key_index"])
        scale_midi = ToneDetector.scale_to_midi(result["scale"])
        self.send_midi(34, key_midi)
        time.sleep(0.05)
        self.send_midi(35, scale_midi)
        print(f"📤 [TONE] MIDI → CC34={key_midi} ({result['key_display']}), CC35={scale_midi} ({result['scale']})")
    
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
            SAMPLE_RATE = 48000  # Windows WASAPI loopback = device output rate (thường 48kHz)
            current_key = None
            current_confidence = 0
            recent_keys = []
            
            # Khởi tạo COM cho thread này
            com_initialized = False
            try:
                hr = ctypes.windll.ole32.CoInitializeEx(None, 0)
                com_initialized = (hr == 0)
            except:
                pass
            
            try:
                # Kiểm tra soundcard
                if not _SOUNDCARD_AVAILABLE:
                    print("❌ [AUTOKEY] soundcard không khả dụng")
                    self.autokey_active = False
                    return
                
                # Tìm loopback mic một lần duy nhất
                all_mics = sc.all_microphones(include_loopback=True)
                loopback_mic = None
                default_speaker = sc.default_speaker()
                speaker_name = default_speaker.name if default_speaker else ""
                
                for mic in all_mics:
                    is_loopback = hasattr(mic, 'isloopback') and mic.isloopback
                    if is_loopback:
                        if loopback_mic is None:
                            loopback_mic = mic
                        if speaker_name and speaker_name.lower() in mic.name.lower():
                            loopback_mic = mic
                
                if not loopback_mic:
                    try:
                        loopback_mic = sc.get_microphone(
                            id=str(default_speaker.name), include_loopback=True
                        )
                    except:
                        pass
                
                if not loopback_mic:
                    print("❌ [AUTOKEY] Không tìm thấy thiết bị loopback!")
                    self.autokey_active = False
                    return
                
                print("=" * 60)
                print(f"🎹 [AUTOKEY] Bắt đầu — segment={segment_duration}s, mic={loopback_mic.name}")
                
                # Giữ recorder mở suốt session → tránh init lại mỗi segment
                # ROLLING AUDIO BUFFER: tích lũy audio thật, phân tích toàn bộ
                RECORD_CHUNK = segment_duration  # Thu 5s mỗi lần
                MAX_BUFFER_SEC = 30  # Giữ tối đa 30s audio (bao phủ nhiều chord hơn)
                MAX_BUFFER_FRAMES = MAX_BUFFER_SEC * SAMPLE_RATE
                audio_buffer = np.array([], dtype=np.float32)
                
                print(f"🎹 [AUTOKEY] Rolling buffer: chunk={RECORD_CHUNK}s, max={MAX_BUFFER_SEC}s")
                
                with loopback_mic.recorder(samplerate=SAMPLE_RATE, channels=1) as recorder:
                    while self.autokey_active:
                        try:
                            # Thu âm chunk mới
                            frames = RECORD_CHUNK * SAMPLE_RATE
                            chunk = recorder.record(numframes=frames)
                            
                            if chunk.ndim > 1:
                                chunk = chunk[:, 0]
                            chunk = chunk.astype(np.float32)
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
                                    except:
                                        pass
                                continue
                            
                            # Thêm vào rolling buffer
                            audio_buffer = np.concatenate([audio_buffer, chunk])
                            
                            # Cắt giữ tối đa MAX_BUFFER_SEC
                            if len(audio_buffer) > MAX_BUFFER_FRAMES:
                                audio_buffer = audio_buffer[-MAX_BUFFER_FRAMES:]
                            
                            buffer_sec = len(audio_buffer) / SAMPLE_RATE
                            print(f"📦 [AUTOKEY] Buffer: {buffer_sec:.1f}s")
                            
                            # Phân tích TOÀN BỘ buffer (giống test_tone_youtube phân tích 30s)
                            result = ToneDetector.detect_key_from_audio(audio_buffer, SAMPLE_RATE)
                            
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
                                except:
                                    pass
                            
                        except Exception as e:
                            print(f"❌ [AUTOKEY] Lỗi segment: {e}")
                            time.sleep(1)
                
            except Exception as e:
                print(f"❌ [AUTOKEY] Lỗi khởi tạo: {e}")
                import traceback
                print(traceback.format_exc())
            finally:
                if com_initialized:
                    try:
                        ctypes.windll.ole32.CoUninitialize()
                    except:
                        pass
                self.autokey_active = False
                print("🏁 [AUTOKEY] Đã dừng")
                
                # Gửi callback cuối cùng để UI biết đã dừng
                if on_key_update:
                    try:
                        on_key_update({'status': 'stopped'})
                    except:
                        pass
        
        self._autokey_thread = threading.Thread(target=_autokey_loop, daemon=True)
        self._autokey_thread.start()
    
    def stop_autokey(self):
        """Dừng AutoKey mode"""
        if self.autokey_active:
            print("⏹️ [AUTOKEY] Đang dừng...")
        self.autokey_active = False
    
    def detect_tone_continuous(self, url=None, segment_duration=5):
        """
        Dò tone liên tục suốt bài hát, phát hiện chuyển tone.
        Chạy trên thread hiện tại, dừng khi youtube_monitoring_active = False.
        
        Cải tiến:
        - Segment 5s (thay vì 10s) → phản hồi nhanh hơn
        - Voting window (3 segments) → tránh nhảy tone lung tung  
        - Confidence threshold (5%) → chỉ chuyển khi chắc chắn
        """
        self.tone_detection_active = True
        current_key = None
        current_confidence = 0
        key_timeline = []
        recent_keys = []  # Voting window
        elapsed = 0
        VOTING_WINDOW = ToneDetector.VOTING_WINDOW
        
        print("=" * 60)
        print(f"🎵 [TONE CONTINUOUS] Bắt đầu dò tone liên tục (segment={segment_duration}s, voting={VOTING_WINDOW})")
        
        while self.tone_detection_active and self.youtube_monitoring_active:
            try:
                result = ToneDetector.detect_key_from_system_audio(
                    duration=segment_duration
                )
                
                if result:
                    new_key = result['key_display']
                    confidence = result.get('confidence', 0)
                    
                    # Thêm vào voting window
                    recent_keys.append(new_key)
                    if len(recent_keys) > VOTING_WINDOW:
                        recent_keys.pop(0)
                    
                    # Voting: key xuất hiện nhiều nhất trong window
                    from collections import Counter
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
                    
                    # Phát hiện chuyển tone với temporal smoothing + confidence threshold
                    should_change = False
                    if current_key is None:
                        # Key đầu tiên: luôn chấp nhận
                        should_change = True
                    elif voted_key != current_key:
                        # Chuyển tone: cần voting đa số VÀ confidence chênh lệch > threshold
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
                        
                        # Gửi MIDI mới
                        self._send_tone_midi(result)
                        
                        # Callback UI
                        if self.on_tone_detected_callback:
                            try:
                                self.on_tone_detected_callback(result)
                            except:
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
        
        # Kết thúc → lưu cache
        self.tone_detection_active = False
        
        if key_timeline and url:
            # Xác định primary key (key xuất hiện nhiều nhất)
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
    
    def _replay_cached_timeline(self, cached_data):
        """
        Replay timeline tone từ cache: gửi MIDI đúng thời điểm.
        Chạy trong thread riêng.
        """
        timeline = cached_data.get('key_timeline', [])
        if not timeline:
            return
        
        self.tone_detection_active = True
        primary_key = cached_data.get('primary_key', timeline[0]['key_display'])
        print(f"▶️ [TONE REPLAY] Replay từ cache: primary={primary_key}, {len(timeline)} segments")
        
        def _replay():
            prev_time = 0
            current_key = None
            
            for entry in timeline:
                if not self.tone_detection_active:
                    break
                
                # Đợi đến thời điểm
                wait = entry['time'] - prev_time
                if wait > 0:
                    # Đợi theo chunk 1s để check dừng sớm
                    for _ in range(int(wait)):
                        if not self.tone_detection_active:
                            break
                        time.sleep(1)
                prev_time = entry['time']
                
                if not self.tone_detection_active:
                    break
                
                new_key = entry['key_display']
                if new_key != current_key:
                    current_key = new_key
                    # Gửi MIDI
                    self._send_tone_midi(entry)
                    print(f"▶️ [REPLAY] t={entry['time']}s: {new_key}")
                    
                    # Callback UI
                    if self.on_tone_detected_callback:
                        try:
                            self.on_tone_detected_callback(entry)
                        except:
                            pass
            
            self.tone_detection_active = False
            print("🏁 [TONE REPLAY] Kết thúc replay")
        
        threading.Thread(target=_replay, daemon=True).start()
    
class SongManager:
    """Quản lý danh sách bài hát đã lưu"""
    @staticmethod
    def load_songs():
        """Load danh sách bài hát từ file"""
        if os.path.exists(SONGS_FILE):
            try:
                with open(SONGS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return []
        return []
    
    @staticmethod
    def save_songs(songs_list):
        """Lưu danh sách bài hát vào file"""
        try:
            with open(SONGS_FILE, "w", encoding="utf-8") as f:
                json.dump(songs_list, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Lỗi lưu danh sách bài hát: {e}")
            return False
    
    @staticmethod
    def add_song(title, url, tone):
        """Thêm bài hát mới vào danh sách"""
        songs = SongManager.load_songs()
        
        # Kiểm tra xem bài hát đã tồn tại chưa
        for song in songs:
            if song.get("url") == url:
                # Cập nhật tone nếu đã tồn tại
                song["tone"] = tone
                song["title"] = title
                SongManager.save_songs(songs)
                return True
        
        # Thêm bài hát mới
        new_song = {
            "id": len(songs) + 1 if songs else 1,
            "title": title,
            "url": url,
            "tone": tone,
            "date_added": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        songs.append(new_song)
        return SongManager.save_songs(songs)
    
    @staticmethod
    def delete_song(song_id):
        """Xóa bài hát khỏi danh sách"""
        songs = SongManager.load_songs()
        songs = [s for s in songs if s.get("id") != song_id]
        return SongManager.save_songs(songs)
    
    @staticmethod
    def get_song_by_id(song_id):
        """Lấy thông tin bài hát theo ID"""
        songs = SongManager.load_songs()
        for song in songs:
            if song.get("id") == song_id:
                return song
        return None

class ScoringEngine:
    """Engine chấm điểm sau khi hát"""
    def __init__(self):
        self.audio_data = None
        self.sample_rate = None
        self.temp_audio_path = None
    
    def download_youtube_audio(self, youtube_url, output_dir="temp_audio"):
        """Tải audio từ YouTube URL"""
        try:
            print(f"📥 [DOWNLOAD] Bắt đầu tải audio từ YouTube: {youtube_url}")
            try:
                import yt_dlp
            except ImportError:
                raise ImportError("Thư viện 'yt-dlp' chưa được cài đặt. Vui lòng chạy: pip install yt-dlp")
            
            import os
            import tempfile
            
            # Tạo thư mục temp nếu chưa có
            if not os.path.exists(output_dir):
                print(f"📁 [DOWNLOAD] Tạo thư mục temp: {output_dir}")
                os.makedirs(output_dir)
            
            # Tạo file tạm
            temp_file = tempfile.NamedTemporaryFile(
                delete=False, 
                suffix='.wav', 
                dir=output_dir
            )
            temp_path = temp_file.name
            temp_file.close()
            print(f"📄 [DOWNLOAD] Tạo file tạm: {temp_path}")
            
            # Cấu hình yt-dlp
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': temp_path.replace('.wav', '.%(ext)s'),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'wav',
                    'preferredquality': '192',
                }],
                'quiet': True,
                'no_warnings': True,
            }
            
            print("⬇️  [DOWNLOAD] Đang tải video từ YouTube...")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([youtube_url])
            print("✅ [DOWNLOAD] Đã tải video thành công")
            
            # Tìm file đã tải (có thể có extension khác)
            base_path = temp_path.replace('.wav', '')
            for ext in ['.wav', '.mp3', '.m4a', '.webm']:
                if os.path.exists(base_path + ext):
                    self.temp_audio_path = base_path + ext
                    file_size = os.path.getsize(self.temp_audio_path) / (1024 * 1024)  # MB
                    print(f"✅ [DOWNLOAD] Tìm thấy file audio: {self.temp_audio_path} ({file_size:.2f} MB)")
                    return self.temp_audio_path
            
            raise Exception("Không tìm thấy file audio đã tải")
            
        except ImportError as e:
            print(f"❌ [DOWNLOAD] Lỗi import: {e}")
            raise e
        except Exception as e:
            print(f"❌ [DOWNLOAD] Lỗi tải YouTube audio: {e}")
            import traceback
            print(traceback.format_exc())
            return None
    
    def cleanup_temp_file(self):
        """Xóa file tạm nếu có"""
        import os
        if self.temp_audio_path and os.path.exists(self.temp_audio_path):
            try:
                os.remove(self.temp_audio_path)
            except:
                pass
            self.temp_audio_path = None
    
    def load_audio(self, file_path):
        """Load file audio để phân tích"""
        try:
            print(f"📂 [LOAD AUDIO] Đang load file: {file_path}")
            try:
                import librosa
                import numpy as np
            except ImportError:
                raise ImportError("Thư viện 'librosa' chưa được cài đặt. Vui lòng chạy: pip install librosa numpy")
            
            print("🔄 [LOAD AUDIO] Đang đọc audio file với librosa...")
            self.audio_data, self.sample_rate = librosa.load(file_path, sr=None, mono=True)
            duration = len(self.audio_data) / self.sample_rate
            print(f"✅ [LOAD AUDIO] Đã load thành công:")
            print(f"   📊 Sample rate: {self.sample_rate} Hz")
            print(f"   ⏱️  Duration: {duration:.2f} giây")
            print(f"   📈 Samples: {len(self.audio_data)}")
            return True
        except ImportError as e:
            print(f"❌ [LOAD AUDIO] Lỗi import: {e}")
            raise e
        except Exception as e:
            print(f"❌ [LOAD AUDIO] Lỗi load audio: {e}")
            import traceback
            print(traceback.format_exc())
            return False
    
    def analyze_pitch(self):
        """Phân tích pitch từ audio"""
        try:
            try:
                import librosa
                import numpy as np
            except ImportError:
                raise ImportError("Thư viện 'librosa' chưa được cài đặt. Vui lòng chạy: pip install librosa numpy")
            
            if self.audio_data is None:
                return None
            
            # Sử dụng pyin để detect pitch (chính xác hơn piptrack)
            f0, voiced_flag, voiced_probs = librosa.pyin(
                self.audio_data,
                fmin=librosa.note_to_hz('C2'),  # Tần số thấp nhất (C2)
                fmax=librosa.note_to_hz('C7'),  # Tần số cao nhất (C7)
                frame_length=2048
            )
            
            # Lọc bỏ các giá trị NaN và chỉ lấy các frame có voice
            pitch_values = []
            for i, pitch in enumerate(f0):
                if not np.isnan(pitch) and voiced_flag[i]:
                    pitch_values.append(pitch)
            
            return np.array(pitch_values) if pitch_values else None
        except Exception as e:
            print(f"Lỗi phân tích pitch: {e}")
            return None
    
    def calculate_score(self, target_notes=None, video_end=False):
        """
        Tính điểm dựa trên phân tích audio - Random 77-100, ưu tiên điểm cao dựa vào độ ổn định âm lượng
        
        Args:
            target_notes: Target notes (không dùng trong thuật toán mới)
            video_end: True nếu được gọi khi video YouTube kết thúc (dùng thuật toán đơn giản hơn)
        """
        try:
            import numpy as np
            import random
            
            if self.audio_data is None:
                return None
            
            # Nếu được gọi khi video YouTube kết thúc, chỉ tính điểm dựa trên volume_consistency
            if video_end:
                print("🎯 [CALCULATE SCORE] Chế độ: video_end=True (chỉ tính dựa trên volume_consistency)")
                
                # Tính volume_consistency
                print("📊 [CALCULATE SCORE] Đang tính volume_consistency...")
                audio_abs = np.abs(self.audio_data)
                volume_std = np.std(audio_abs)
                volume_mean = np.mean(audio_abs)
                volume_consistency = max(0, 100 - (volume_std / volume_mean * 100)) if volume_mean > 0 else 50
                volume_consistency = min(100, volume_consistency)
                print(f"   🔊 Volume mean: {volume_mean:.4f}")
                print(f"   📈 Volume std: {volume_std:.4f}")
                print(f"   ✅ Volume consistency: {volume_consistency:.1f}")
                
                # Random điểm từ 77-100, ưu tiên điểm cao dựa vào volume_consistency
                base_score = 77
                score_range = 23  # 100 - 77 = 23
                
                # Tính điểm dựa trên volume_consistency (0-100) -> ảnh hưởng đến random range
                volume_factor = volume_consistency / 100.0  # 0.0 - 1.0
                random_bonus = random.uniform(0, score_range * volume_factor)
                total_score = base_score + random_bonus
                total_score = min(100, max(77, total_score))
                
                print(f"🎲 [CALCULATE SCORE] Random calculation:")
                print(f"   📌 Base score: {base_score}")
                print(f"   📊 Volume factor: {volume_factor:.3f}")
                print(f"   🎲 Random bonus: {random_bonus:.2f}")
                print(f"   ✅ Total score: {total_score:.1f}")
                
                duration = len(self.audio_data) / self.sample_rate
                feedback = self._generate_feedback(total_score, 0, 0)
                
                return {
                    "total_score": round(total_score, 1),
                    "pitch_accuracy": round(0, 1),
                    "pitch_stability": round(0, 1),
                    "volume_consistency": round(volume_consistency, 1),
                    "timing_accuracy": round(85, 1),
                    "pitch_mean": round(0, 2),
                    "pitch_std": round(0, 2),
                    "duration": round(duration, 2),
                    "feedback": feedback
                }
            
            # Phân tích pitch
            pitches = self.analyze_pitch()
            if pitches is None or len(pitches) == 0:
                # Nếu không có pitch, vẫn tính điểm dựa trên volume
                audio_abs = np.abs(self.audio_data)
                volume_std = np.std(audio_abs)
                volume_mean = np.mean(audio_abs)
                volume_consistency = max(0, 100 - (volume_std / volume_mean * 100)) if volume_mean > 0 else 50
                volume_consistency = min(100, volume_consistency)
                
                # Random điểm từ 77-100, ưu tiên điểm cao dựa vào volume_consistency
                # Volume consistency càng cao thì điểm càng cao
                base_score = 77
                score_range = 23  # 100 - 77 = 23
                
                # Tính điểm dựa trên volume_consistency (0-100) -> ảnh hưởng đến random range
                # Volume consistency cao -> điểm cao hơn
                volume_factor = volume_consistency / 100.0  # 0.0 - 1.0
                random_bonus = random.uniform(0, score_range * volume_factor)
                total_score = base_score + random_bonus
                total_score = min(100, max(77, total_score))
                
                duration = len(self.audio_data) / self.sample_rate
                feedback = self._generate_feedback(total_score, 0, 0)
                
                return {
                    "total_score": round(total_score, 1),
                    "pitch_accuracy": round(0, 1),
                    "pitch_stability": round(0, 1),
                    "volume_consistency": round(volume_consistency, 1),
                    "timing_accuracy": round(85, 1),
                    "pitch_mean": round(0, 2),
                    "pitch_std": round(0, 2),
                    "duration": round(duration, 2),
                    "feedback": feedback
                }
            
            # 1. Pitch Accuracy (độ chính xác pitch)
            pitch_mean = np.mean(pitches)
            pitch_std = np.std(pitches)
            pitch_accuracy = max(0, 100 - (pitch_std / pitch_mean * 100)) if pitch_mean > 0 else 0
            pitch_accuracy = min(100, pitch_accuracy)
            
            # 2. Pitch Stability (độ ổn định)
            pitch_stability = max(0, 100 - (pitch_std / pitch_mean * 200)) if pitch_mean > 0 else 0
            pitch_stability = min(100, pitch_stability)
            
            # 3. Volume Consistency (độ nhất quán âm lượng) - QUAN TRỌNG CHO ĐIỂM
            audio_abs = np.abs(self.audio_data)
            volume_std = np.std(audio_abs)
            volume_mean = np.mean(audio_abs)
            volume_consistency = max(0, 100 - (volume_std / volume_mean * 100)) if volume_mean > 0 else 50
            volume_consistency = min(100, volume_consistency)
            
            # 4. Timing Accuracy (giả lập - dựa trên độ dài audio)
            duration = len(self.audio_data) / self.sample_rate
            timing_accuracy = 85  # Giá trị mặc định
            
            # THUẬT TOÁN MỚI: Random từ 77-100, ưu tiên điểm cao dựa vào độ ổn định âm lượng
            base_score = 77
            score_range = 23  # 100 - 77 = 23
            
            # Tính điểm dựa trên volume_consistency (0-100) -> ảnh hưởng đến random range
            # Volume consistency càng cao thì điểm càng cao
            volume_factor = volume_consistency / 100.0  # 0.0 - 1.0
            
            # Random bonus dựa trên volume_factor
            # Volume consistency cao -> random bonus cao hơn
            random_bonus = random.uniform(0, score_range * volume_factor)
            total_score = base_score + random_bonus
            total_score = min(100, max(77, total_score))
            
            # Tạo feedback
            feedback = self._generate_feedback(total_score, pitch_accuracy, pitch_stability)
            
            return {
                "total_score": round(total_score, 1),
                "pitch_accuracy": round(pitch_accuracy, 1),
                "pitch_stability": round(pitch_stability, 1),
                "volume_consistency": round(volume_consistency, 1),
                "timing_accuracy": round(timing_accuracy, 1),
                "pitch_mean": round(pitch_mean, 2),
                "pitch_std": round(pitch_std, 2),
                "duration": round(duration, 2),
                "feedback": feedback
            }
        except Exception as e:
            print(f"Lỗi tính điểm: {e}")
            return {
                "total_score": 0,
                "pitch_accuracy": 0,
                "pitch_stability": 0,
                "volume_consistency": 0,
                "timing_accuracy": 0,
                "feedback": f"Lỗi: {str(e)}"
            }
    
    def _generate_feedback(self, total_score, pitch_accuracy, pitch_stability):
        """Tạo feedback dựa trên điểm số"""
        if total_score >= 90:
            return "🎉 Xuất sắc! Bạn hát rất tốt!"
        elif total_score >= 80:
            return "👍 Tốt! Hãy tiếp tục luyện tập!"
        elif total_score >= 70:
            return "👌 Khá tốt! Cần cải thiện thêm một chút."
        elif total_score >= 60:
            return "💪 Ổn! Hãy luyện tập nhiều hơn."
        else:
            return "📚 Cần luyện tập thêm để cải thiện!"

class ToneDetector:
    """
    Dò Tone bài hát - Phát hiện key/tonality từ audio
    Pipeline: HPSS → Chroma CQT (energy-weighted) → Weighted Multi-profile (Aarden/Temperley/KS) → Disambiguation
    """
    
    # Krumhansl-Schmuckler key profiles (1990) - weight 20%
    KS_MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
    KS_MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
    
    # Temperley key profiles (CBMS, 2001) - weight 30%
    TEMP_MAJOR = [5.0, 2.0, 3.5, 2.0, 4.5, 4.0, 2.0, 4.5, 2.0, 3.5, 1.5, 4.0]
    TEMP_MINOR = [5.0, 2.0, 3.5, 4.5, 2.0, 4.0, 2.0, 4.5, 3.5, 2.0, 1.5, 4.0]
    
    # Aarden-Essen key profiles (corpus-based) - weight 50% (tối ưu cho pop)
    AARDEN_MAJOR = [17.7661, 0.145624, 14.9265, 0.160186, 19.8049, 11.3587,
                    0.291248, 22.062, 0.145624, 8.15494, 0.232998, 4.95122]
    AARDEN_MINOR = [18.2648, 0.737619, 14.0499, 16.8599, 0.702494, 14.4362,
                    0.702494, 18.6161, 4.56621, 1.93186, 7.37619, 1.75623]
    
    # Trọng số từng bộ profile
    PROFILE_WEIGHTS = {
        'aarden': 0.50,
        'temperley': 0.30,
        'ks': 0.20
    }
    
    # Backward compatibility aliases
    MAJOR_PROFILE = KS_MAJOR
    MINOR_PROFILE = KS_MINOR
    
    # Key names - khớp với UI tone selector
    MAJOR_KEY_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
    MINOR_KEY_NAMES = ["Cm", "C#m", "Dm", "D#m", "Em", "Fm", "F#m", "Gm", "G#m", "Am", "Bbm", "Bm"]
    
    # Relative key pairs: Major index → Minor index (cách 9 semitone)
    # C Major (0) ↔ Am (9), D Major (2) ↔ Bm (11), ...
    RELATIVE_MINOR_OFFSET = 9  # Major + 9 semitone = relative Minor
    
    # Confidence threshold: chỉ chuyển tone khi chênh lệch > 5%
    KEY_CHANGE_THRESHOLD = 0.05
    
    # Voting window: số segments cần đồng thuận trước khi chuyển tone
    VOTING_WINDOW = 3
    
    @staticmethod
    def _correlate_profiles(chroma_avg, major_profile, minor_profile):
        """
        Tính correlation cho 1 bộ profile (Major + Minor) với chroma vector.
        Trả về dict {uid: correlation} cho 24 keys.
        """
        import numpy as np
        results = {}
        for i in range(12):
            rotated = np.roll(chroma_avg, -i)
            major_corr = float(np.corrcoef(rotated, major_profile)[0, 1])
            uid_major = f"{ToneDetector.MAJOR_KEY_NAMES[i]}_Major"
            results[uid_major] = {
                "key": ToneDetector.MAJOR_KEY_NAMES[i],
                "scale": "Major",
                "correlation": major_corr,
                "key_index": i
            }
            minor_corr = float(np.corrcoef(rotated, minor_profile)[0, 1])
            uid_minor = f"{ToneDetector.MINOR_KEY_NAMES[i]}_Minor"
            results[uid_minor] = {
                "key": ToneDetector.MINOR_KEY_NAMES[i],
                "scale": "Minor",
                "correlation": minor_corr,
                "key_index": i
            }
        return results
    
    @staticmethod
    def _is_relative_pair(key1_idx, scale1, key2_idx, scale2):
        """Kiểm tra 2 key có phải relative pair không (C Major ↔ Am)"""
        if scale1 == "Major" and scale2 == "Minor":
            return (key1_idx + ToneDetector.RELATIVE_MINOR_OFFSET) % 12 == key2_idx
        if scale1 == "Minor" and scale2 == "Major":
            return (key2_idx + ToneDetector.RELATIVE_MINOR_OFFSET) % 12 == key1_idx
        return False
    
    @staticmethod
    def _are_closely_related(key1_idx, scale1, key2_idx, scale2):
        """
        Kiểm tra 2 key có closely related không (chia sẻ >= 6/7 nốt).
        Bao gồm: relative keys, parallel keys, và các key lân cận trên circle of fifths.
        VD: Eb Major ↔ Fm, C Major ↔ Am, C Major ↔ Dm, G Major ↔ Em, ...
        """
        # Tạo scale degrees cho mỗi key
        major_intervals = [0, 2, 4, 5, 7, 9, 11]  # W W H W W W H
        minor_intervals = [0, 2, 3, 5, 7, 8, 10]  # Natural minor
        
        if scale1 == "Major":
            notes1 = set((key1_idx + i) % 12 for i in major_intervals)
        else:
            notes1 = set((key1_idx + i) % 12 for i in minor_intervals)
        
        if scale2 == "Major":
            notes2 = set((key2_idx + i) % 12 for i in major_intervals)
        else:
            notes2 = set((key2_idx + i) % 12 for i in minor_intervals)
        
        overlap = len(notes1 & notes2)
        return overlap >= 6  # Chia sẻ ít nhất 6 nốt

    @staticmethod
    def detect_key_from_audio(audio_data, sample_rate, accumulated_chroma=None):
        """
        Phát hiện tone/key của bài hát từ audio data.
        Pipeline: Robust Preprocessing → CQT chroma (energy-weighted) → Weighted Multi-profile → Disambiguation
        """
        try:
            import librosa
            import numpy as np
            
            audio_data = np.nan_to_num(audio_data, nan=0.0, posinf=0.0, neginf=0.0)
            
            # === BƯỚC 0: Robust Preprocessing ===
            
            # Stage 1: Clip extreme outliers (corrupted samples, VD: max=1.8e29)
            audio_data = np.clip(audio_data, -1e6, 1e6)
            
            # Stage 2: Percentile-based normalize (tránh 1 sample lỗi phá hủy signal)
            p999 = np.percentile(np.abs(audio_data), 99.9)
            if p999 > 0:
                audio_data = audio_data / p999
            audio_data = np.clip(audio_data, -1.0, 1.0)
            
            # Stage 3: DC offset removal
            audio_data = audio_data - np.mean(audio_data)
            
            # Stage 4: Quality validation
            rms_check = np.sqrt(np.mean(audio_data ** 2))
            if rms_check < 0.001:
                print("   ⚠️ Audio quá nhỏ hoặc im lặng, bỏ qua")
                return None
            
            # Stage 5: Adaptive hum removal (PYIN detect → notch filter)
            try:
                f0_detect, voiced, _ = librosa.pyin(
                    audio_data, fmin=50, fmax=80, sr=sample_rate,
                    frame_length=4096
                )
                valid_f0 = f0_detect[~np.isnan(f0_detect) & voiced]
                if len(valid_f0) > 100:
                    hum_freq = np.median(valid_f0)
                    hum_ratio = np.sum(np.abs(valid_f0 - hum_freq) < 2) / len(valid_f0)
                    if hum_ratio > 0.95:
                        S = librosa.stft(audio_data)
                        freqs = librosa.fft_frequencies(sr=sample_rate)
                        for harmonic_n in range(1, 4):
                            target = hum_freq * harmonic_n
                            S[np.abs(freqs - target) < 5] = 0
                        audio_data = librosa.istft(S, length=len(audio_data))
                        print(f"   ✅ Notch: loại hum {hum_freq:.0f}Hz ({hum_ratio*100:.0f}%)")
            except Exception:
                pass
            
            print(f"   ✅ Preprocessing OK (p99.9={p999:.4f}, rms={rms_check:.4f})")
            print("🎵 [DÒ TONE] Pipeline: CQT → Weighted Multi-profile...")
            
            # === BƯỚC 1: Chroma CQT (energy-weighted) ===
            chroma_cqt = librosa.feature.chroma_cqt(y=audio_data, sr=sample_rate)
            rms = librosa.feature.rms(y=audio_data)[0]
            min_frames = min(len(rms), chroma_cqt.shape[1])
            rms = rms[:min_frames]
            rms_sum = np.sum(rms)
            if rms_sum > 0:
                chroma_avg = np.average(chroma_cqt[:, :min_frames], axis=1, weights=rms / rms_sum)
            else:
                chroma_avg = np.mean(chroma_cqt, axis=1)
            
            # Normalize
            cs = np.sum(chroma_avg)
            if cs > 0:
                chroma_avg = chroma_avg / cs
            
            # Lưu normalized (cho disambiguation)
            cqt_normalized = chroma_avg.copy()
            
            print(f"   ✅ Chroma CQT (energy-weighted)")
            print(f"📊 [DÒ TONE] Chroma: {[f'{x:.3f}' for x in chroma_avg]}")
            
            # === BƯỚC 2b: EMA (AutoKey mode) ===
            if accumulated_chroma is not None:
                alpha = 0.3
                chroma_for_analysis = alpha * chroma_avg + (1 - alpha) * accumulated_chroma
                cs2 = np.sum(chroma_for_analysis)
                if cs2 > 0:
                    chroma_for_analysis = chroma_for_analysis / cs2
                print(f"   ✅ EMA blending (α={alpha})")
            else:
                chroma_for_analysis = chroma_avg
            
            # === BƯỚC 3: Weighted Multi-profile correlation ===
            W = ToneDetector.PROFILE_WEIGHTS
            
            ks_results = ToneDetector._correlate_profiles(
                chroma_for_analysis, ToneDetector.KS_MAJOR, ToneDetector.KS_MINOR
            )
            temp_results = ToneDetector._correlate_profiles(
                chroma_for_analysis, ToneDetector.TEMP_MAJOR, ToneDetector.TEMP_MINOR
            )
            aarden_results = ToneDetector._correlate_profiles(
                chroma_for_analysis, ToneDetector.AARDEN_MAJOR, ToneDetector.AARDEN_MINOR
            )
            
            all_uids = set(ks_results.keys()) | set(temp_results.keys()) | set(aarden_results.keys())
            all_results = []
            for uid in all_uids:
                ks_c = ks_results.get(uid, {}).get('correlation', 0)
                temp_c = temp_results.get(uid, {}).get('correlation', 0)
                aarden_c = aarden_results.get(uid, {}).get('correlation', 0)
                
                weighted_corr = W['ks'] * ks_c + W['temperley'] * temp_c + W['aarden'] * aarden_c
                
                ref = ks_results.get(uid) or temp_results.get(uid) or aarden_results.get(uid)
                
                all_results.append({
                    "key": ref["key"], "scale": ref["scale"],
                    "correlation": weighted_corr, "key_index": ref["key_index"],
                    "ks_corr": ks_c, "temp_corr": temp_c, "aarden_corr": aarden_c
                })
            
            all_results.sort(key=lambda x: x["correlation"], reverse=True)
            
            # === BƯỚC 4: Key Family Disambiguation ===
            # Tìm TẤT CẢ keys closely-related trong top 7 → chọn key tốt nhất
            best = all_results[0]
            
            # Key commonality: keys phổ biến trong pop/Vietnamese music
            # Score 1.0 = rất phổ biến, 0.0 = rất hiếm
            KEY_COMMON = {
                # Major
                'C': 1.0, 'G': 0.9, 'D': 0.9, 'A': 0.8, 'E': 0.7,
                'F': 0.9, 'Bb': 0.8, 'Eb': 0.8, 'Ab': 0.7,
                'Db': 0.5, 'Gb': 0.3, 'B': 0.5,
                # Minor
                'Am': 1.0, 'Em': 0.9, 'Dm': 0.9, 'Bm': 0.7,
                'Gm': 0.8, 'Cm': 0.8, 'Fm': 0.8, 'Bbm': 0.5,
                'F#m': 0.6, 'C#m': 0.6, 'G#m': 0.3, 'D#m': 0.3,
            }
            
            # Thu thập candidates closely-related với best
            family = [best]
            for r in all_results[1:7]:
                if ToneDetector._are_closely_related(
                    best["key_index"], best["scale"],
                    r["key_index"], r["scale"]
                ):
                    family.append(r)
            
            if len(family) >= 2:
                print(f"   🔍 Key family ({len(family)} candidates):")
                
                best_candidate = None
                best_score = -1
                family_scores = []  # Lưu combined score cho tiebreaker
                
                for r in family:
                    # Tonic + 5th + 3rd strength
                    tonic = cqt_normalized[r["key_index"]]
                    fifth = cqt_normalized[(r["key_index"] + 7) % 12]
                    if r["scale"] == "Minor":
                        third = cqt_normalized[(r["key_index"] + 3) % 12]
                    else:
                        third = cqt_normalized[(r["key_index"] + 4) % 12]
                    
                    tonal_strength = tonic + fifth * 0.7 + third * 0.5
                    
                    # Combined: profile correlation (chính) + tonal strength (phụ)
                    combined = r["correlation"] * 0.85 + tonal_strength * 0.15
                    family_scores.append((r, combined))
                    
                    print(f"      {r['key']:4s}: corr={r['correlation']:.3f} T={tonic:.3f} 5={fifth:.3f} 3={third:.3f} → {combined:.4f}")
                    
                    if combined > best_score:
                        best_score = combined
                        best_candidate = r
                
                # Commonality tiebreaker: chỉ khi top-2 chênh nhau < 2%
                if best_candidate and len(family_scores) >= 2:
                    family_scores.sort(key=lambda x: x[1], reverse=True)
                    top1, top1_combined = family_scores[0]
                    top2, top2_combined = family_scores[1]
                    if abs(top1_combined - top2_combined) < 0.02:
                        # Dùng commonality phân giải
                        top1_common = KEY_COMMON.get(top1["key"], 0.5)
                        top2_common = KEY_COMMON.get(top2["key"], 0.5)
                        if top2_common > top1_common:
                            best_candidate = top2
                            print(f"   🎯 Tiebreaker: {top1['key']} ({top1_common:.1f}) → {top2['key']} ({top2_common:.1f})")
                

                
                if best_candidate and best_candidate["key"] != best["key"]:
                    print(f"   🔄 Family winner: {best['key']} → {best_candidate['key']}")
                else:
                    print(f"   ✅ Giữ {best['key']}")
                best = best_candidate or best
            
            best_key = best["key_index"]
            best_scale = best["scale"]
            best_corr = best["correlation"]
            
            if best_scale == "Major":
                key_display = ToneDetector.MAJOR_KEY_NAMES[best_key]
            else:
                key_display = ToneDetector.MINOR_KEY_NAMES[best_key]
            
            print(f"🎯 [DÒ TONE] Kết quả: {key_display} (confidence: {best_corr:.4f})")
            print(f"   📊 KS={best.get('ks_corr',0):.4f}  T={best.get('temp_corr',0):.4f}  A={best.get('aarden_corr',0):.4f}")
            print(f"🎯 [DÒ TONE] Top 5:")
            for r in all_results[:5]:
                print(f"   {r['key']}: {r['correlation']:.4f}")
            
            return {
                "key": ToneDetector.MAJOR_KEY_NAMES[best_key],
                "key_index": best_key,
                "scale": best_scale,
                "confidence": best_corr,
                "key_display": key_display,
                "top_results": all_results[:5],
                "chroma_vector": chroma_avg
            }
            
        except Exception as e:
            print(f"❌ [DÒ TONE] Lỗi phân tích: {e}")
            import traceback
            print(traceback.format_exc())
            return None
    
    @staticmethod
    def detect_key_from_system_audio(duration=10, sample_rate=48000, on_progress=None):
        """
        Thu âm loopback từ hệ thống (bắt âm thanh đang phát trên loa)
        và phát hiện tone bài hát. Không cần tải từ YouTube.
        
        Sử dụng WASAPI Loopback (Windows) qua thư viện soundcard.
        """
        import numpy as np
        
        # Kiểm tra soundcard
        if not _SOUNDCARD_AVAILABLE:
            print("❌ [DÒ TONE] Thư viện 'soundcard' chưa được cài đặt.")
            print("   Chạy: pip install soundcard")
            return None
        
        # Khởi tạo COM cho background thread (WASAPI yêu cầu COM per-thread)
        com_initialized = False
        try:
            hr = ctypes.windll.ole32.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED
            com_initialized = (hr == 0)  # Chỉ tính khi S_OK
        except:
            pass
        
        try:
            print("=" * 60)
            print(f"🎤 [DÒ TONE] Thu âm loopback từ hệ thống ({duration}s)...")
            
            # Tìm loopback microphone
            all_mics = sc.all_microphones(include_loopback=True)
            
            loopback_mic = None
            default_speaker = sc.default_speaker()
            speaker_name = default_speaker.name if default_speaker else ""
            
            print(f"🔊 [DÒ TONE] Default speaker: {speaker_name}")
            print(f"🎙️ [DÒ TONE] Tìm thấy {len(all_mics)} microphone(s):")
            
            for mic in all_mics:
                is_loopback = hasattr(mic, 'isloopback') and mic.isloopback
                print(f"   {'🔄' if is_loopback else '🎙️'} {mic.name} (loopback={is_loopback})")
                
                if is_loopback:
                    if loopback_mic is None:
                        loopback_mic = mic
                    if speaker_name and speaker_name.lower() in mic.name.lower():
                        loopback_mic = mic
            
            if not loopback_mic:
                try:
                    loopback_mic = sc.get_microphone(id=str(default_speaker.name), include_loopback=True)
                except:
                    pass
            
            if not loopback_mic:
                print("❌ [DÒ TONE] Không tìm thấy thiết bị loopback!")
                return None
            
            print(f"✅ [DÒ TONE] Sử dụng loopback: {loopback_mic.name}")
            print(f"⏺️  [DÒ TONE] Đang thu âm {duration} giây...")
            
            # Thu âm theo từng giây để cập nhật progress
            audio_chunks = []
            with loopback_mic.recorder(samplerate=sample_rate, channels=1) as recorder:
                for i in range(duration):
                    chunk = recorder.record(numframes=sample_rate)
                    audio_chunks.append(chunk)
                    
                    remaining = duration - i - 1
                    if on_progress:
                        try:
                            on_progress(remaining)
                        except:
                            pass
                    
                    print(f"   ⏱️  Còn {remaining}s...")
            
            # Ghép các chunks
            audio_data = np.concatenate(audio_chunks, axis=0)
            if audio_data.ndim > 1:
                audio_data = audio_data[:, 0]
            audio_data = audio_data.astype(np.float32)
            
            actual_duration = len(audio_data) / sample_rate
            print(f"✅ [DÒ TONE] Đã thu: {actual_duration:.1f}s, {len(audio_data)} samples")
            
            # Kiểm tra âm thanh
            rms = np.sqrt(np.mean(audio_data ** 2))
            print(f"📊 [DÒ TONE] RMS level: {rms:.6f}")
            
            if rms < 0.001:
                print("⚠️ [DÒ TONE] Không phát hiện âm thanh! Hãy đảm bảo đang phát nhạc.")
                return None
            
            
            # Phân tích key
            result = ToneDetector.detect_key_from_audio(audio_data, sample_rate)
            return result
            
        except Exception as e:
            print(f"❌ [DÒ TONE] Lỗi thu âm: {e}")
            import traceback
            print(traceback.format_exc())
            return None
        finally:
            if com_initialized:
                try:
                    ctypes.windll.ole32.CoUninitialize()
                except:
                    pass
    
    @staticmethod
    def detect_key_from_youtube(youtube_url, duration_limit=60):
        """
        Tải audio từ YouTube và phát hiện tone
        Chỉ phân tích tối đa duration_limit giây đầu tiên
        """
        try:
            import librosa
            
            print("=" * 60)
            print(f"🎵 [DÒ TONE] Bắt đầu dò tone từ YouTube...")
            print(f"🔗 URL: {youtube_url}")
            
            # Download audio
            scoring_engine = ScoringEngine()
            audio_path = scoring_engine.download_youtube_audio(youtube_url)
            
            if not audio_path:
                print("❌ [DÒ TONE] Không thể tải audio")
                return None
            
            try:
                # Load audio (giới hạn thời gian để tăng tốc)
                print(f"📂 [DÒ TONE] Loading audio (max {duration_limit}s)...")
                audio_data, sr = librosa.load(
                    audio_path,
                    sr=22050,
                    mono=True,
                    duration=duration_limit
                )
                
                actual_duration = len(audio_data) / sr
                print(f"✅ [DÒ TONE] Loaded: {actual_duration:.1f}s, sr={sr}")
                
                # Detect key
                result = ToneDetector.detect_key_from_audio(audio_data, sr)
                return result
                
            finally:
                scoring_engine.cleanup_temp_file()
                
        except Exception as e:
            print(f"❌ [DÒ TONE] Lỗi: {e}")
            import traceback
            print(traceback.format_exc())
            return None
    
    @staticmethod
    def key_index_to_midi(key_index):
        """Chuyển key index (0-11) sang MIDI CC value (0-127)"""
        return min(127, max(0, int(key_index * 127 / 11)))
    
    @staticmethod
    def scale_to_midi(scale):
        """Chuyển scale type sang MIDI CC value (0=Major, 127=Minor)"""
        return 127 if scale == "Minor" else 0

class ActivationManager:
    """Quản lý activation code và thời hạn sử dụng"""
    
    # Thời hạn sử dụng: 1 năm (365 ngày)
    LICENSE_DURATION_DAYS = 365
    
    # Secret key - PHẢI GIỐNG VỚI generate_code.py
    SECRET_KEY = "QUANGLUU_STUDIO_2026_SECRET_KEY_CHANGE_THIS"
    
    @staticmethod
    def _validate_code_structure(code):
        """Kiểm tra format của code: XXXX-XXXX-XXXX-XXXX-XXXX"""
        if not code:
            return False
        
        code = code.strip().upper()
        parts = code.split('-')
        
        if len(parts) != 5:
            return False
        
        for part in parts:
            if len(part) != 4:
                return False
            # Mỗi phần phải có chữ và số
            if not any(c.isalpha() for c in part) or not any(c.isdigit() for c in part):
                return False
        
        return True
    
    @staticmethod
    def _verify_code_checksum(code):
        """Xác minh checksum của code"""
        import hashlib
        
        parts = code.split('-')
        if len(parts) != 5:
            return False
        
        base_code = '-'.join(parts[:4])
        provided_checksum = parts[4]
        
        # Tính checksum
        checksum_input = base_code + ActivationManager.SECRET_KEY
        calculated_checksum = hashlib.md5(checksum_input.encode()).hexdigest()[:4].upper()
        
        return provided_checksum == calculated_checksum
    
    @staticmethod
    def _validate_code(code):
        """
        Xác thực activation code
        Kiểm tra cả format và checksum
        """
        if not code:
            return False
        
        code = code.strip().upper()
        
        # Kiểm tra format
        if not ActivationManager._validate_code_structure(code):
            return False
        
        # Kiểm tra checksum
        if not ActivationManager._verify_code_checksum(code):
            return False
        
        return True
    
    @staticmethod
    def load_activation():
        """Load thông tin activation từ file"""
        if os.path.exists(ACTIVATION_FILE):
            try:
                with open(ACTIVATION_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return None
        return None
    
    @staticmethod
    def save_activation(code):
        """Lưu thông tin activation sau khi kích hoạt thành công"""
        activation_data = {
            "activation_code": code.strip().upper(),
            "activation_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "activation_timestamp": time.time()
        }
        try:
            with open(ACTIVATION_FILE, "w", encoding="utf-8") as f:
                json.dump(activation_data, f, indent=4)
            return True
        except Exception as e:
            print(f"Lỗi lưu activation: {e}")
            return False
    
    @staticmethod
    def is_activated():
        """Kiểm tra xem app đã được kích hoạt chưa"""
        activation = ActivationManager.load_activation()
        if not activation:
            return False
        
        # Kiểm tra xem có activation_date không
        if "activation_date" not in activation:
            return False
        
        return True
    
    @staticmethod
    def is_expired():
        """Kiểm tra xem activation đã hết hạn chưa (sau 1 năm)"""
        activation = ActivationManager.load_activation()
        if not activation:
            return True  # Chưa kích hoạt = hết hạn
        
        # Lấy timestamp từ activation
        if "activation_timestamp" in activation:
            activation_time = activation["activation_timestamp"]
        elif "activation_date" in activation:
            # Parse date string nếu không có timestamp
            try:
                from datetime import datetime
                activation_time = datetime.strptime(
                    activation["activation_date"], 
                    "%Y-%m-%d %H:%M:%S"
                ).timestamp()
            except:
                return True  # Lỗi parse = hết hạn
        else:
            return True  # Không có thông tin = hết hạn
        
        # Tính số ngày đã trôi qua
        current_time = time.time()
        days_passed = (current_time - activation_time) / (24 * 60 * 60)
        
        # Kiểm tra xem đã vượt quá thời hạn chưa
        return days_passed >= ActivationManager.LICENSE_DURATION_DAYS
    
    @staticmethod
    def get_days_remaining():
        """Lấy số ngày còn lại của license"""
        activation = ActivationManager.load_activation()
        if not activation:
            return 0
        
        if "activation_timestamp" in activation:
            activation_time = activation["activation_timestamp"]
        elif "activation_date" in activation:
            try:
                from datetime import datetime
                activation_time = datetime.strptime(
                    activation["activation_date"], 
                    "%Y-%m-%d %H:%M:%S"
                ).timestamp()
            except:
                return 0
        else:
            return 0
        
        current_time = time.time()
        days_passed = (current_time - activation_time) / (24 * 60 * 60)
        days_remaining = ActivationManager.LICENSE_DURATION_DAYS - days_passed
        
        return max(0, int(days_remaining))
    
    @staticmethod
    def activate(code):
        """Kích hoạt app với code được cung cấp"""
        if not ActivationManager._validate_code(code):
            return False, "Mã kích hoạt không hợp lệ. Vui lòng kiểm tra lại."
        
        # Lưu activation
        if ActivationManager.save_activation(code):
            return True, "Kích hoạt thành công!"
        else:
            return False, "Lỗi khi lưu thông tin kích hoạt."
    
    @staticmethod
    def needs_activation():
        """Kiểm tra xem app có cần kích hoạt không"""
        # Chưa kích hoạt hoặc đã hết hạn
        return not ActivationManager.is_activated() or ActivationManager.is_expired()