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
import ctypes.wintypes
import queue
import re
import win32process

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
        self._loop.run_until_complete(self._monitor_loop())
        
    async def _monitor_loop(self):
        try:
            manager = await MediaManager.request_async()
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
                    else:
                        self.is_playing = False
                except Exception as e:
                    pass
                
                await asyncio.sleep(0.1)  # Cập nhật 10 lần/giây
        except Exception as e:
            print(f"Lỗi khởi tạo MediaManager: {e}")
            
    def stop(self):
        self._running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
            
    def wait_for_playback(self, timeout=30):
        """Chờ cho đến khi media thực sự PLAYING"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.is_playing:
                return True
            time.sleep(0.5)
        return False

# WASAPI loopback sử dụng pyaudiowpatch (thay thế soundcard)
# - recorder_worker.py: subprocess thu âm
# - ToneDetector.detect_key_from_system_audio: dò tone
# - SystemEngine._autokey_loop: dò tone liên tục

# --- CẤU HÌNH CỐT LÕI ---
SETTINGS_FILE = "settings.json"
SONGS_FILE = "saved_songs.json"
ACTIVATION_FILE = "activation.json"
MIDI_PORT_NAME = "QuangLuuMIDI"
MANUAL_TIMELINES_FILE = "manual_timelines.json"


class ConfigManager:
    @staticmethod
    def load():
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f: return json.load(f)
            except: return None
        return None

    @staticmethod
    def save(settings_or_s1=None, web=None, auto_launch_studio_one=False, midi_port_name=None):
        # Hỗ trợ cả dict lẫn positional args
        if isinstance(settings_or_s1, dict):
            settings = settings_or_s1
        else:
            settings = {
                "studio_one_path": settings_or_s1 or "", 
                "browser_path": web or "",
                "auto_launch_studio_one": auto_launch_studio_one
            }
            if midi_port_name:
                settings["midi_port_name"] = midi_port_name
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4)

# --- CLASS QUẢN LÝ MIDI ---
class MidiHandler:
    def __init__(self):
        self.outport = None
        self.inport = None
        self._warned = False
        self._is_listening = False
        self._listen_thread = None
        self.on_cc_received = None
        self.connect()

    def connect(self):
        try:
            outputs = mido.get_output_names()
            inputs = mido.get_input_names()
            
            port_name = next((name for name in outputs if MIDI_PORT_NAME in name), None)
            in_name = next((name for name in inputs if MIDI_PORT_NAME in name), None)

            if port_name:
                self.outport = mido.open_output(port_name)
                print(f"✅ MIDI Out Connected: {port_name}")
            
            if in_name:
                try:
                    self.inport = mido.open_input(in_name)
                    print(f"✅ MIDI In Connected: {in_name}")
                    self.start_listening()
                except Exception as ein:
                    print(f"⚠️ Lỗi kết nối MIDI In: {ein}")

            if port_name or in_name:
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

    def start_listening(self):
        if self._is_listening or not self.inport: return
        self._is_listening = True
        import threading
        self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listen_thread.start()

    def _listen_loop(self):
        try:
            for msg in self.inport:
                if msg.type == 'control_change':
                    if self.on_cc_received:
                        self.on_cc_received(msg.control, msg.value)
        except Exception as e:
            print(f"⚠️ MIDI Listen Error: {e}")
            self._is_listening = False
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

class ManualToneTimeline:
    """Quản lý timeline tone thủ công per YouTube video"""
    
    # Danh sách key hợp lệ (khớp với Auto-Tune sharp notation)
    MAJOR_KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    MINOR_KEYS = ["Cm", "C#m", "Dm", "D#m", "Em", "Fm", "F#m", "Gm", "G#m", "Am", "A#m", "Bm"]
    ALL_KEYS = MAJOR_KEYS + MINOR_KEYS
    
    @staticmethod
    def parse_key_display(key_display):
        """
        Parse key_display (VD: 'Cm', 'D', 'F#m') thành dict {key_index, scale, key_display}.
        Trả về None nếu key không hợp lệ.
        """
        if key_display in ManualToneTimeline.MAJOR_KEYS:
            key_index = ManualToneTimeline.MAJOR_KEYS.index(key_display)
            return {"key_index": key_index, "scale": "Major", "key_display": key_display}
        elif key_display in ManualToneTimeline.MINOR_KEYS:
            key_index = ManualToneTimeline.MINOR_KEYS.index(key_display)
            return {"key_index": key_index, "scale": "Minor", "key_display": key_display}
        return None
    
    @staticmethod
    def parse_time_str(time_str):
        """
        Parse thời gian 'MM:SS' hoặc 'H:MM:SS' thành giây (float).
        Trả về None nếu format sai.
        """
        try:
            parts = time_str.strip().split(':')
            if len(parts) == 2:
                minutes, seconds = int(parts[0]), int(parts[1])
                return minutes * 60 + seconds
            elif len(parts) == 3:
                hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
                return hours * 3600 + minutes * 60 + seconds
        except (ValueError, IndexError):
            pass
        return None
    
    @staticmethod
    def seconds_to_time_str(seconds):
        """Chuyển giây (int/float) thành 'MM:SS'"""
        seconds = int(seconds)
        m, s = divmod(seconds, 60)
        return f"{m}:{s:02d}"
    
    @staticmethod
    def load_all():
        """Load tất cả manual timelines từ file"""
        if os.path.exists(MANUAL_TIMELINES_FILE):
            try:
                with open(MANUAL_TIMELINES_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    @staticmethod
    def _save_all(data):
        """Lưu tất cả timelines vào file"""
        try:
            with open(MANUAL_TIMELINES_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"❌ Lỗi lưu manual timelines: {e}")
            return False
    
    @staticmethod
    def load_timeline(url):
        """
        Load timeline cho 1 URL cụ thể.
        Trả về dict {url, title, timeline: [{time, key_display, key_index, scale}, ...]} hoặc None.
        """
        video_id = ToneCacheManager._extract_video_id(url)
        if not video_id:
            return None
        data = ManualToneTimeline.load_all()
        return data.get(video_id)
    
    @staticmethod
    def save_timeline(url, title, timeline_entries):
        """
        Lưu timeline thủ công.
        timeline_entries: list of {time: float (giây), key_display: str}
        """
        video_id = ToneCacheManager._extract_video_id(url)
        if not video_id:
            print("❌ Không thể trích xuất video ID từ URL")
            return False
        
        # Parse và validate từng entry
        parsed_entries = []
        for entry in timeline_entries:
            t = entry.get("time")
            key_display = entry.get("key_display", "")
            
            if t is None or t < 0:
                continue
            
            key_info = ManualToneTimeline.parse_key_display(key_display)
            if key_info is None:
                print(f"⚠️ Bỏ qua key không hợp lệ: {key_display}")
                continue
            
            parsed_entries.append({
                "time": float(t),
                "key_display": key_info["key_display"],
                "key_index": key_info["key_index"],
                "scale": key_info["scale"]
            })
        
        # Sắp xếp theo thời gian
        parsed_entries.sort(key=lambda x: x["time"])
        
        if not parsed_entries:
            print("⚠️ Không có entry hợp lệ để lưu")
            return False
        
        data = ManualToneTimeline.load_all()
        data[video_id] = {
            "url": url,
            "title": title,
            "timeline": parsed_entries,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        success = ManualToneTimeline._save_all(data)
        if success:
            print(f"✅ Đã lưu manual timeline: {title} ({len(parsed_entries)} entries)")
        return success
    
    @staticmethod
    def delete_timeline(url):
        """Xóa timeline theo URL"""
        video_id = ToneCacheManager._extract_video_id(url)
        if not video_id:
            return False
        data = ManualToneTimeline.load_all()
        if video_id in data:
            del data[video_id]
            return ManualToneTimeline._save_all(data)
        return False

class AudioRecorder:
    """Thu âm loopback (WASAPI) chạy trong subprocess riêng biệt — tránh xung đột COM với PySide6."""
    
    def __init__(self):
        self._process = None
        self._stop_flag_path = None
        self._temp_wav_path = None
        self._is_recording = False

    def start_recording(self):
        import subprocess, tempfile
        if self._is_recording:
            return
        
        # Tạo file tạm cho output WAV và stop flag
        self._temp_wav_path = os.path.join(tempfile.gettempdir(), f"qlstudio_rec_{int(time.time())}.wav")
        self._stop_flag_path = os.path.join(tempfile.gettempdir(), f"qlstudio_rec_flag_{int(time.time())}.tmp")
        
        # Tạo file flag (worker sẽ chạy cho đến khi file này bị xóa)
        with open(self._stop_flag_path, 'w') as f:
            f.write("recording")
        
        # Tìm đường dẫn recorder_worker.py cùng thư mục với backend.py
        worker_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recorder_worker.py")
        
        self._process = subprocess.Popen(
            [sys.executable, worker_script, self._temp_wav_path, self._stop_flag_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        self._is_recording = True
        
        # Đọc stdout trong thread riêng để theo dõi trạng thái
        def monitor():
            try:
                for line in self._process.stdout:
                    line = line.strip()
                    if line:
                        print(f"🎤 [RECORDING] {line}")
            except:
                pass
        threading.Thread(target=monitor, daemon=True).start()
        print(f"🎤 [RECORDING] Đã khởi chạy subprocess thu âm (PID: {self._process.pid})")

    def stop_recording(self, save_path=None):
        """Dừng thu âm. Nếu save_path được cung cấp, di chuyển file WAV tạm đến đó."""
        import shutil
        
        if not self._is_recording:
            return False
        self._is_recording = False
        
        # Xóa file flag → subprocess sẽ tự dừng (nếu không bị blocking)
        if self._stop_flag_path and os.path.exists(self._stop_flag_path):
            try:
                os.remove(self._stop_flag_path)
            except:
                pass
        
        # Đợi 1s, nếu subprocess vẫn chạy (WASAPI block) → kill nó
        # File WAV vẫn hợp lệ vì worker ghi streaming trực tiếp ra disk
        if self._process:
            try:
                self._process.wait(timeout=1.0)
            except:
                try:
                    self._process.terminate()
                    self._process.wait(timeout=0.5)
                except:
                    self._process.kill()
            self._process = None
        
        # Kiểm tra file WAV tạm
        if not self._temp_wav_path or not os.path.exists(self._temp_wav_path):
            print("⚠️ [RECORDING] Không tìm thấy file thu âm tạm.")
            return False
        
        file_size = os.path.getsize(self._temp_wav_path)
        if file_size < 100:  # WAV header ~44 bytes, nếu chỉ có header = rỗng
            print("⚠️ [RECORDING] File thu âm rỗng (không thu được âm thanh).")
            try: os.remove(self._temp_wav_path)
            except: pass
            return False 
        
        if not save_path:
            try: os.remove(self._temp_wav_path)
            except: pass
            return False
        
        try:
            shutil.move(self._temp_wav_path, save_path)
            size_mb = file_size / (1024 * 1024)
            print(f"✅ [RECORDING] Đã lưu file: {save_path} ({size_mb:.1f} MB)")
            return True
        except Exception as e:
            print(f"⚠️ [RECORDING] Lỗi khi lưu file: {e}")
            return False

class SystemEngine:
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
                except: pass
        threading.Thread(target=run, daemon=True).start()

    # Các file mở rộng của Studio One
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
                    except:
                        print(f"⚠️ Không thể mở URL: {url}")
            else:
                try:
                    os.startfile(url)
                except:
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
    def detect_youtube_url_from_browser():
        """
        Phát hiện YouTube URL đang mở trên trình duyệt (Windows).
        Sử dụng ctypes.windll.user32.EnumWindows + uiautomation.
        
        Returns:
            str: YouTube URL sạch (chỉ chứa video ID), hoặc None nếu không tìm thấy.
        """
        try:
            import uiautomation as auto
        except ImportError:
            print("❌ [DÒ TONE] Thư viện 'uiautomation' chưa được cài đặt.")
            print("   Chạy: pip install uiautomation")
            return None
        
        # Bao gồm "Microsoft​ Edge" (có U+200B) + "Edge" ngắn gọn để khớp mọi trường hợp
        browser_keywords = [
            "Google Chrome", "Microsoft\u200b Edge", "Microsoft Edge",
            "Mozilla Firefox", "Brave", "Opera", "Vivaldi", "Edge",
        ]
        
        # ── Bước 1: Liệt kê tất cả cửa sổ trình duyệt ──
        all_windows = []
        
        def enum_callback(hwnd, _):
            if ctypes.windll.user32.IsWindowVisible(hwnd):
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                    all_windows.append((hwnd, buf.value))
            return True
        
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        ctypes.windll.user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
        
        # Lọc cửa sổ trình duyệt
        browser_windows = []
        for hwnd, title in all_windows:
            for keyword in browser_keywords:
                if keyword.lower() in title.lower():
                    browser_windows.append({"hwnd": hwnd, "title": title, "browser": keyword})
                    break
        
        print(f"🔍 [DÒ TONE] Tìm thấy {len(browser_windows)} cửa sổ trình duyệt")
        
        # ── Bước 2: Đọc URL từ thanh địa chỉ ──
        for bw in browser_windows:
            hwnd = bw["hwnd"]
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
        
        print("⚠️ [DÒ TONE] Không tìm thấy YouTube URL trên trình duyệt.")
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
    
    def detect_tone_from_browser(self, on_complete=None, on_error=None, on_progress=None):
        """
        Dò Tone từ YouTube đang mở trên trình duyệt.
        Luồng: Phát hiện URL → Tải audio → Phân tích Key/Scale/BPM/Camelot → Trả kết quả.
        
        Args:
            on_complete: Callback(result_dict) khi hoàn thành
            on_error: Callback(error_msg) khi lỗi
            on_progress: Callback(status_text) cập nhật trạng thái
        """
        import numpy as np
        
        # Camelot wheel mapping
        CAMELOT_MAJOR = ["8B", "3B", "10B", "5B", "12B", "7B", "2B", "9B", "4B", "11B", "6B", "1B"]
        CAMELOT_MINOR = ["5A", "12A", "7A", "2A", "9A", "4A", "11A", "6A", "1A", "8A", "3A", "10A"]
        
        def _detect():
            try:
                # Bước 1: Phát hiện YouTube URL từ browser
                if on_progress:
                    on_progress("Đang tìm YouTube URL trên trình duyệt...")
                
                youtube_url = SystemEngine.detect_youtube_url_from_browser()
                
                if not youtube_url:
                    if on_error:
                        on_error("Không tìm thấy YouTube URL trên trình duyệt.\nHãy mở YouTube trên Chrome/Edge/Firefox.")
                    return
                
                self.current_youtube_url = youtube_url
                
                # Bước 2: Kiểm tra cache
                if on_progress:
                    on_progress("Đang kiểm tra cache...")
                
                cached = ToneCacheManager.get_cached_tone(youtube_url)
                if cached:
                    print(f"✅ [DÒ TONE] Cache hit: {cached.get('primary_key', '?')}")
                    timeline = cached.get('key_timeline', [])
                    if timeline:
                        entry = timeline[0]
                        key_idx = entry.get('key_index', 0)
                        scale = entry.get('scale', 'Major')
                        camelot = CAMELOT_MAJOR[key_idx] if scale == "Major" else CAMELOT_MINOR[key_idx]
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
                        }
                        self._send_tone_midi(result)
                        if on_complete:
                            on_complete(result)
                        return
                
                # Bước 3: Tải audio từ YouTube
                if on_progress:
                    on_progress("Đang tải audio từ YouTube...")
                
                print(f"🎵 [DÒ TONE] Bắt đầu dò tone từ YouTube...")
                print(f"🔗 URL: {youtube_url}")
                
                scoring_engine = ScoringEngine()
                audio_path = scoring_engine.download_youtube_audio(youtube_url)
                
                if not audio_path:
                    if on_error:
                        on_error("Không thể tải audio từ YouTube.")
                    return
                
                try:
                    # Bước 4: Load audio bằng librosa
                    if on_progress:
                        on_progress("Đang phân tích bài hát...")
                    
                    import librosa
                    
                    audio_data, sr = librosa.load(audio_path, sr=22050, mono=True)
                    song_duration = len(audio_data) / sr
                    
                    print(f"✅ [DÒ TONE] Loaded: {song_duration:.1f}s, sr={sr}")
                    
                    # Bước 4a: Phát hiện Key & Scale
                    if on_progress:
                        on_progress("Đang phát hiện Key & Scale...")
                    
                    tone_result = ToneDetector.detect_key_from_audio(audio_data, sr)
                    
                    if not tone_result:
                        if on_error:
                            on_error("Không thể phát hiện tone bài hát.")
                        return
                    
                    # Bước 4b: BPM & Camelot — tạm bỏ qua để trả kết quả nhanh hơn
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
                    }
                    
                    print(f"🎯 [DÒ TONE] Kết quả:")
                    print(f"   Key: {result['key_display']}")
                    print(f"   Scale: {result['scale']}")
                    print(f"   BPM: {result['bpm']}")
                    print(f"   Camelot: {result['camelot']}")
                    print(f"   Confidence: {result['confidence']:.3f}")
                    print(f"   Duration: {result['duration']}s")
                    
                    # Gửi MIDI
                    self._send_tone_midi(result)
                    
                    # Lưu cache
                    cache_data = {
                        'primary_key': result['key_display'],
                        'key_timeline': [{
                            'time': 0,
                            'key_display': result['key_display'],
                            'key_index': key_idx,
                            'scale': scale,
                            'confidence': result['confidence'],
                            'bpm': result['bpm'],
                            'duration': result['duration'],
                        }]
                    }
                    ToneCacheManager.save_tone(youtube_url, cache_data)
                    
                    if on_complete:
                        on_complete(result)
                        
                finally:
                    scoring_engine.cleanup_temp_file()
                    
            except Exception as e:
                print(f"❌ [DÒ TONE] Lỗi: {e}")
                import traceback
                traceback.print_exc()
                if on_error:
                    on_error(str(e))
        
        threading.Thread(target=_detect, daemon=True).start()

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
                # 1. Kiểm tra cache trước
                if on_progress:
                    on_progress("Đang kiểm tra cache...")
                
                cached = ToneCacheManager.get_cached_tone(youtube_url)
                if cached:
                    print(f"✅ [LẤY TONE YT] Cache hit: {cached.get('primary_key', '?')}")
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
                
                # 2. Tải audio từ YouTube
                if on_progress:
                    on_progress("Đang tải audio từ YouTube...")
                
                print(f"🎵 [LẤY TONE YT] Bắt đầu dò tone từ YouTube...")
                print(f"🔗 URL: {youtube_url}")
                
                result = ToneDetector.detect_key_from_youtube(youtube_url, duration_limit=30)
                
                if result:
                    # 3. Gửi MIDI
                    self._send_tone_midi(result)
                    
                    # 4. Lưu cache
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
                    ToneCacheManager.save_tone(youtube_url, cache_data)
                    
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
                    
                    # 8. Gửi MIDI cho key đầu tiên
                    first_key = timeline_entries[0]
                    self._send_tone_midi({
                        'key_display': first_key['key_display'],
                        'key_index': first_key['key_index'],
                        'scale': first_key['scale']
                    })
                    
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
                    
            except Exception as e:
                print(f"❌ [AUTO TIMELINE] Lỗi: {e}")
                import traceback
                traceback.print_exc()
                if on_error:
                    on_error(str(e))
        
        threading.Thread(target=_detect_full, daemon=True).start()

    def _send_tone_midi(self, result):
        """Gửi MIDI CC cho key/scale đến Auto-Tune
        
        Plugin nhận 0-127 → hiển thị 0-100%. Công thức: round(knob% × 127/100)
        Key (CC 34): Giá trị knob thực tế trên plugin:
          C=0%, Db=8.66%, D=18.11%, Eb=26.77%, E=36.22%, F=44.88%, F#=54.33%,
          G=62.99%, Ab=72.44%, A=81.10%, Bb=90.55%, B=100%
        Scale (CC 35): Major=10.24%, Minor=14.17%
        """
        # Bảng ánh xạ Key → MIDI CC value (từ knob% thực tế trên plugin)
        KEY_MIDI_MAP = {
            "C": 0,   "C#": 11,  "Db": 11,  "D": 23,  "D#": 34,  "Eb": 34,
            "E": 46,  "F": 57,   "F#": 69,  "G": 80,
            "G#": 92, "Ab": 92,  "A": 103,  "A#": 115, "Bb": 115, "B": 127,
        }
        # Scale → MIDI CC value (từ knob% thực tế trên plugin)
        SCALE_MIDI_MAP = {
            "Major": 13,
            "Minor": 18,
        }
        
        # Lấy key_display, bỏ "m" suffix nếu có (Cm → C, Am → A)
        key_display = result.get("key_display", "C")
        is_minor = key_display.endswith("m")
        
        if is_minor:
            key_root = key_display[:-1] if key_display.endswith("#m") else key_display.replace("m", "")
            default_scale = "Minor"
        else:
            key_root = key_display
            default_scale = "Major"
        
        key_midi = KEY_MIDI_MAP.get(key_root, 0)
        scale = result.get("scale", default_scale)
        scale_midi = SCALE_MIDI_MAP.get(scale, 14)
        
        self.send_midi(34, key_midi)
        time.sleep(0.05)
        self.send_midi(35, scale_midi)
        print(f"📤 [TONE] MIDI → CC34={key_midi} (Key={key_root}), CC35={scale_midi} (Scale={scale})")
    
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
            except:
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
                
                # ROLLING AUDIO BUFFER: tích lũy audio, phân tích toàn bộ
                RECORD_CHUNK = segment_duration
                MAX_BUFFER_SEC = 30
                MAX_BUFFER_FRAMES = MAX_BUFFER_SEC * SAMPLE_RATE
                audio_buffer = np.array([], dtype=np.float32)
                
                print(f"🎹 [AUTOKEY] Rolling buffer: chunk={RECORD_CHUNK}s, max={MAX_BUFFER_SEC}s")
                
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
                                chunk_np = np.frombuffer(data, dtype=np.float32)
                                chunks.append(chunk_np)
                                frames_read += len(chunk_np)
                            
                            if not self.autokey_active:
                                break
                            
                            chunk = np.concatenate(chunks)
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
                            
                            # Phân tích TOÀN BỘ buffer
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
                finally:
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
                            except:
                                pass
                                
                    last_idx = target_idx
                
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
                            except:
                                pass
                                
                    last_idx = target_idx
                
                time.sleep(0.1)
            
            print(f"🏁 [MANUAL REPLAY] Kết thúc replay thủ công")
        
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
    
    def load_audio_data(self, audio_data, sample_rate=44100):
        """Load audio trực tiếp từ numpy array (không cần file)"""
        import numpy as np
        self.audio_data = audio_data.astype(np.float32)
        self.sample_rate = sample_rate
        duration = len(self.audio_data) / self.sample_rate
        print(f"✅ [LOAD AUDIO] Loaded from memory: {duration:.1f}s, {len(self.audio_data)} samples")
        return True
    
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
    
    def calculate_score(self, target_notes=None, video_end=False, quick=False):
        """
        Tính điểm dựa trên phân tích audio - Random 77-100, ưu tiên điểm cao dựa vào độ ổn định âm lượng
        
        Args:
            target_notes: Target notes (không dùng trong thuật toán mới)
            video_end: True nếu được gọi khi video YouTube kết thúc (dùng thuật toán đơn giản hơn)
            quick: True = chế độ nhanh (bỏ qua pitch analysis, chỉ dùng volume, điểm nhẹ tay 80-100)
        """
        try:
            import numpy as np
            import random
            
            if self.audio_data is None:
                return None
            
            # Quick mode: bỏ qua pitch analysis, chấm nhẹ tay (80-100)
            if quick or video_end:
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
                total_score = min(100, max(80, total_score))
                
                print(f"🎲 [CALCULATE SCORE] Random calculation:")
                print(f"   📌 Base score: {base_score}")
                print(f"   📊 Volume factor: {volume_factor:.3f}")
                print(f"   🎲 Random bonus: {random_bonus:.2f}")
                print(f"   ✅ Total score: {total_score:.1f}")
                
                duration = len(self.audio_data) / self.sample_rate
                feedback = self._generate_feedback(total_score, 0, 0, volume_consistency, 85)
                
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
                feedback = self._generate_feedback(total_score, 0, 0, volume_consistency, 85)
                
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
            feedback = self._generate_feedback(total_score, pitch_accuracy, pitch_stability, volume_consistency, timing_accuracy)
            
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
                "feedback": {"main": f"Lỗi: {str(e)}", "tips": []}
            }
    
    def _generate_feedback(self, total_score, pitch_accuracy, pitch_stability,
                           volume_consistency=0, timing_accuracy=0):
        """Tạo feedback + gợi ý cải thiện dựa trên điểm số"""
        # Main feedback
        if total_score >= 95:
            main = "🏆 Tuyệt vời! Giọng hát cực kỳ ấn tượng!"
        elif total_score >= 90:
            main = "🎉 Xuất sắc! Bạn hát rất tốt!"
        elif total_score >= 85:
            main = "👍 Rất tốt! Gần hoàn hảo rồi!"
        elif total_score >= 80:
            main = "👌 Tốt! Hãy tiếp tục luyện tập!"
        else:
            main = "💪 Ổn! Hãy luyện tập thêm nhé!"
        
        # Gợi ý cải thiện dựa trên từng chỉ số
        tips = []
        
        if pitch_accuracy > 0 and pitch_accuracy < 85:
            tips.append("🎵 Hãy nghe kỹ beat và cố gắng hát đúng cao độ hơn. Luyện từng đoạn ngắn trước.")
        
        if pitch_stability > 0 and pitch_stability < 85:
            tips.append("📈 Giữ hơi đều hơn để giọng không bị rung. Tập thở bụng sẽ giúp ổn định giọng.")
        
        if volume_consistency > 0 and volume_consistency < 80:
            tips.append("🔊 Giữ khoảng cách với micro ổn định hơn để âm lượng đều hơn.")
        elif volume_consistency >= 90:
            tips.append("🔊 Âm lượng rất ổn định, tuyệt vời!")
        
        if timing_accuracy > 0 and timing_accuracy < 85:
            tips.append("⏱️ Cố gắng vào nhịp chính xác hơn. Nghe nhạc nền nhiều lần để quen beat.")
        
        # Thêm gợi ý chung nếu điểm cao
        if total_score >= 90 and len(tips) == 0:
            tips.append("⭐ Tiếp tục duy trì phong độ này! Thử thách với bài khó hơn nhé.")
            tips.append("🎤 Thử thêm cảm xúc và kỹ thuật vocal để nâng tầm giọng hát.")
        elif total_score >= 85 and len(tips) == 0:
            tips.append("🎯 Còn chút nữa là hoàn hảo! Chú ý những nốt cao và nốt dài.")
            tips.append("💡 Nghe lại bản thu và so sánh với bài gốc để tìm điểm cần cải thiện.")
        elif len(tips) == 0:
            tips.append("💡 Luyện tập đều đặn mỗi ngày sẽ giúp bạn tiến bộ nhanh chóng.")
            tips.append("🎧 Nghe và hát theo bài gốc nhiều lần trước khi thu âm.")
        
        return {
            "main": main,
            "tips": tips[:3]  # Tối đa 3 gợi ý
        }

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
    
    # Key names - khớp với Auto-Tune (đều dùng sharp notation)
    MAJOR_KEY_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    MINOR_KEY_NAMES = ["Cm", "C#m", "Dm", "D#m", "Em", "Fm", "F#m", "Gm", "G#m", "Am", "A#m", "Bm"]
    
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
                # Major (sharp notation - khớp Auto-Tune)
                'C': 1.0, 'G': 0.9, 'D': 0.9, 'A': 0.8, 'E': 0.7,
                'F': 0.9, 'A#': 0.8, 'D#': 0.8, 'G#': 0.7,
                'C#': 0.5, 'F#': 0.3, 'B': 0.5,
                # Minor (sharp notation - khớp Auto-Tune)
                'Am': 1.0, 'Em': 0.9, 'Dm': 0.9, 'Bm': 0.7,
                'Gm': 0.8, 'Cm': 0.8, 'Fm': 0.8, 'A#m': 0.5,
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
        
        Sử dụng WASAPI Loopback (Windows) qua thư viện pyaudiowpatch.
        """
        import numpy as np
        
        # Import pyaudiowpatch (thay thế soundcard)
        try:
            import pyaudiowpatch as pyaudio
        except ImportError:
            print("❌ [DÒ TONE] Thư viện 'pyaudiowpatch' chưa được cài đặt.")
            print("   Chạy: pip install pyaudiowpatch")
            return None
        
        # Khởi tạo COM cho background thread (WASAPI yêu cầu COM per-thread)
        com_initialized = False
        try:
            hr = ctypes.windll.ole32.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED
            com_initialized = (hr == 0)  # Chỉ tính khi S_OK
        except:
            pass
        
        pa = None
        stream = None
        try:
            print("=" * 60)
            print(f"🎤 [DÒ TONE] Thu âm loopback từ hệ thống ({duration}s)...")
            
            pa = pyaudio.PyAudio()
            
            # Tìm WASAPI loopback device
            wasapi_info = None
            for i in range(pa.get_host_api_count()):
                info = pa.get_host_api_info_by_index(i)
                if "wasapi" in info.get("name", "").lower():
                    wasapi_info = info
                    break
            
            if not wasapi_info:
                print("❌ [DÒ TONE] Không tìm thấy WASAPI host API!")
                return None
            
            loopback_dev = None
            for i in range(pa.get_device_count()):
                dev = pa.get_device_info_by_index(i)
                if dev.get("isLoopbackDevice", False):
                    if dev.get("hostApi") == wasapi_info["index"]:
                        loopback_dev = dev
                        break
            
            if not loopback_dev:
                print("❌ [DÒ TONE] Không tìm thấy thiết bị loopback!")
                return None
            
            device_sr = int(loopback_dev["defaultSampleRate"])
            chunk_size = 1024
            
            print(f"✅ [DÒ TONE] Sử dụng loopback: {loopback_dev['name']}")
            print(f"⏺️  [DÒ TONE] Đang thu âm {duration} giây...")
            
            stream = pa.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=device_sr,
                input=True,
                input_device_index=loopback_dev["index"],
                frames_per_buffer=chunk_size
            )
            
            # Thu âm theo từng giây để cập nhật progress
            audio_chunks = []
            for sec in range(duration):
                frames_needed = device_sr
                frames_read = 0
                while frames_read < frames_needed:
                    data = stream.read(chunk_size, exception_on_overflow=False)
                    chunk_np = np.frombuffer(data, dtype=np.float32)
                    audio_chunks.append(chunk_np)
                    frames_read += len(chunk_np)
                
                remaining = duration - sec - 1
                if on_progress:
                    try:
                        on_progress(remaining)
                    except:
                        pass
                
                print(f"   ⏱️  Còn {remaining}s...")
            
            # Ghép các chunks
            audio_data = np.concatenate(audio_chunks)
            audio_data = np.nan_to_num(audio_data, nan=0.0, posinf=0.0, neginf=0.0)
            
            actual_duration = len(audio_data) / device_sr
            print(f"✅ [DÒ TONE] Đã thu: {actual_duration:.1f}s, {len(audio_data)} samples")
            
            # Kiểm tra âm thanh
            rms = np.sqrt(np.mean(audio_data ** 2))
            print(f"📊 [DÒ TONE] RMS level: {rms:.6f}")
            
            if rms < 0.001:
                print("⚠️ [DÒ TONE] Không phát hiện âm thanh! Hãy đảm bảo đang phát nhạc.")
                return None
            
            
            # Phân tích key
            result = ToneDetector.detect_key_from_audio(audio_data, device_sr)
            return result
            
        except Exception as e:
            print(f"❌ [DÒ TONE] Lỗi thu âm: {e}")
            import traceback
            print(traceback.format_exc())
            return None
        finally:
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except:
                    pass
            if pa:
                try:
                    pa.terminate()
                except:
                    pass
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
    def detect_timeline_advanced(audio_data, sr, on_progress=None):
        """
        Dò tone tiên tiến:
        1. Dùng novelty-based segmentation để tìm đổi cấu trúc.
        2. Refine với sliding window nhỏ (±3s).
        3. Dò tone mỗi segment.
        4. Merge segment cùng key.
        5. Filter chuyển tone ngắn (<8s).
        """
        import librosa
        import numpy as np
        import scipy.signal
        
        duration = len(audio_data) / sr
        if on_progress: on_progress("Đang phân tích cấu trúc bài hát (novelty curve)...")
        print("🔍 [NOVELTY] Bắt đầu phân tích cấu trúc...")
        
        # 1. Novelty curve (dựa trên chroma)
        hop_length = int(sr / 2) # 0.5s per frame
        chroma = librosa.feature.chroma_cqt(y=audio_data, sr=sr, hop_length=hop_length)
        
        novelty = np.zeros(chroma.shape[1])
        window_frames = 10 # 5s
        for i in range(window_frames, chroma.shape[1] - window_frames):
            past = np.mean(chroma[:, i-window_frames:i], axis=1)
            future = np.mean(chroma[:, i:i+window_frames], axis=1)
            n_p = np.linalg.norm(past)
            n_f = np.linalg.norm(future)
            if n_p > 0 and n_f > 0:
                novelty[i] = 1.0 - np.dot(past, future) / (n_p * n_f)
                
        peaks, _ = scipy.signal.find_peaks(novelty, prominence=0.03, distance=16) # distance = 8s
        initial_boundaries = [p * hop_length / sr for p in peaks]
        print(f"📊 [NOVELTY] Đã tìm thấy {len(initial_boundaries)} điểm thay đổi cấu trúc thô")
        
        # 2. Refine với sliding window (±3s)
        if on_progress: on_progress("Đang tinh chỉnh các điểm chuyển đoạn...")
        refined_boundaries = []
        for b in initial_boundaries:
            start_frame = int(max(0, b - 3.0) * sr / hop_length)
            end_frame = int(min(duration, b + 3.0) * sr / hop_length)
            if start_frame < end_frame:
                local_nov = novelty[start_frame:end_frame]
                local_max_idx = np.argmax(local_nov)
                refined_b = max(0, b - 3.0) + local_max_idx * hop_length / sr
                refined_boundaries.append(refined_b)
            else:
                refined_boundaries.append(b)
                
        boundaries = [0.0] + refined_boundaries + [duration]
        boundaries = sorted(list(set(boundaries)))
        print(f"🎯 [NOVELTY] Refined {len(refined_boundaries)} điểm chuyển cấu trúc")
        
        # 3. Detect tone cho mỗi phân đoạn
        segments = []
        for i in range(len(boundaries) - 1):
            start = boundaries[i]
            end = boundaries[i+1]
            
            if on_progress:
                pct = int((i + 1) / (len(boundaries) - 1) * 100)
                on_progress(f"Dò tone phân đoạn {i+1}/{len(boundaries)-1} ({pct}%)...")
                
            seg_audio = audio_data[int(start*sr):int(end*sr)]
            if len(seg_audio) < sr * 2:
                continue
                
            rms = np.sqrt(np.mean(seg_audio ** 2))
            if rms < 0.005:
                segments.append({'start': start, 'end': end, 'key_display': 'Silence', 'result': None})
                continue
                
            result = ToneDetector.detect_key_from_audio(seg_audio, sr)
            if result:
                segments.append({
                    'start': start, 'end': end,
                    'key_display': result['key_display'],
                    'result': result
                })
                print(f"   🎵 Phân đoạn [{start:.1f}s - {end:.1f}s]: {result['key_display']} (conf={result.get('confidence',0):.3f})")
            else:
                segments.append({'start': start, 'end': end, 'key_display': 'Unknown', 'result': None})
                
        # 4. Merge adjacent segments (bỏ Silence/Unknown)
        merged_segments = []
        for seg in segments:
            if not merged_segments:
                merged_segments.append(seg)
            else:
                last_seg = merged_segments[-1]
                if seg['key_display'] in ['Silence', 'Unknown']:
                    last_seg['end'] = seg['end']
                elif last_seg['key_display'] in ['Silence', 'Unknown']:
                    last_seg['key_display'] = seg['key_display']
                    last_seg['result'] = seg['result']
                    last_seg['end'] = seg['end']
                elif last_seg['key_display'] == seg['key_display']:
                    last_seg['end'] = seg['end']
                    if seg['result'] and last_seg['result']:
                        if seg['result'].get('confidence',0) > last_seg['result'].get('confidence',0):
                            last_seg['result'] = seg['result']
                else:
                    merged_segments.append(seg)
                    
        # 5. Filter short segments (<8s) (Loc Nhiễu)
        MIN_DURATION = 8.0
        filtered_segments = []
        for seg in merged_segments:
            seg_dur = seg['end'] - seg['start']
            if seg_dur < MIN_DURATION:
                if not filtered_segments:
                    filtered_segments.append(seg)
                else:
                    filtered_segments[-1]['end'] = seg['end']
                    print(f"   ✂️ Bỏ qua đoạn chuyển nhiễu ({seg_dur:.1f}s), gộp vào {filtered_segments[-1]['key_display']}")
            else:
                if filtered_segments and filtered_segments[-1]['key_display'] == seg['key_display']:
                    filtered_segments[-1]['end'] = seg['end']
                else:
                    filtered_segments.append(seg)
                    
        # Final pass merge
        final_segments = []
        for seg in filtered_segments:
            if not final_segments:
                final_segments.append(seg)
            elif final_segments[-1]['key_display'] == seg['key_display']:
                final_segments[-1]['end'] = seg['end']
            else:
                final_segments.append(seg)
                
        # Tạo kết quả cuối cùng
        timeline_entries = []
        for seg in final_segments:
            if seg['result'] and seg['key_display'] not in ['Silence', 'Unknown']:
                entry = {
                    'time': float(seg['start']),
                    'key_display': seg['result']['key_display'],
                    'key_index': seg['result']['key_index'],
                    'scale': seg['result']['scale'],
                    'confidence': float(seg['result'].get('confidence', 0.8))
                }
                timeline_entries.append(entry)
                print(f"✅ [TIMELINE] {seg['start']:.1f}s → {seg['key_display']}")
                
        # Xử lý case track toàn bị Silent/ngắn
        if not timeline_entries and final_segments and final_segments[0]['result']:
            seg = final_segments[0]
            timeline_entries.append({
                'time': 0.0,
                'key_display': seg['result']['key_display'],
                'key_index': seg['result']['key_index'],
                'scale': seg['result']['scale'],
                'confidence': float(seg['result'].get('confidence', 0.8))
            })
            
        return timeline_entries
        
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