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
        self.connect()
    def connect(self):
        try:
            outputs = mido.get_output_names()
            port_name = next((name for name in outputs if MIDI_PORT_NAME in name), None)
            if port_name:
                self.outport = mido.open_output(port_name)
                print(f"✅ MIDI Connected: {port_name}")
                return True
            else:
                print(f"⚠️ Lỗi: Không tìm thấy cổng '{MIDI_PORT_NAME}'. Hãy mở loopMIDI!")
                return False
        except Exception as e:
            print(f"⚠️ Lỗi MIDI: {e}")
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

class SystemEngine:
    def __init__(self, settings=None):
        self.settings = settings or {}
        
        # Khởi tạo MidiHandler
        self.midi_handler = MidiHandler()
    

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
                print("⚠️ MIDI chưa kết nối, đang thử kết nối lại...")
                if self.midi_handler.connect():
                    print("✅ Đã kết nối lại MIDI")
                else:
                    print("❌ Không thể kết nối lại MIDI")
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
            try:
                import yt_dlp
            except ImportError:
                raise ImportError("Thư viện 'yt-dlp' chưa được cài đặt. Vui lòng chạy: pip install yt-dlp")
            
            import os
            import tempfile
            
            # Tạo thư mục temp nếu chưa có
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # Tạo file tạm
            temp_file = tempfile.NamedTemporaryFile(
                delete=False, 
                suffix='.wav', 
                dir=output_dir
            )
            temp_path = temp_file.name
            temp_file.close()
            
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
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([youtube_url])
            
            # Tìm file đã tải (có thể có extension khác)
            base_path = temp_path.replace('.wav', '')
            for ext in ['.wav', '.mp3', '.m4a', '.webm']:
                if os.path.exists(base_path + ext):
                    self.temp_audio_path = base_path + ext
                    return self.temp_audio_path
            
            raise Exception("Không tìm thấy file audio đã tải")
            
        except ImportError as e:
            raise e
        except Exception as e:
            print(f"Lỗi tải YouTube audio: {e}")
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
            try:
                import librosa
                import numpy as np
            except ImportError:
                raise ImportError("Thư viện 'librosa' chưa được cài đặt. Vui lòng chạy: pip install librosa numpy")
            
            self.audio_data, self.sample_rate = librosa.load(file_path, sr=None, mono=True)
            return True
        except ImportError as e:
            raise e
        except Exception as e:
            print(f"Lỗi load audio: {e}")
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
    
    def calculate_score(self, target_notes=None):
        """Tính điểm dựa trên phân tích audio"""
        try:
            import numpy as np
            
            if self.audio_data is None:
                return None
            
            # Phân tích pitch
            pitches = self.analyze_pitch()
            if pitches is None or len(pitches) == 0:
                return {
                    "total_score": 0,
                    "pitch_accuracy": 0,
                    "pitch_stability": 0,
                    "volume_consistency": 0,
                    "timing_accuracy": 0,
                    "feedback": "Không thể phát hiện pitch trong audio"
                }
            
            # 1. Pitch Accuracy (độ chính xác pitch)
            pitch_mean = np.mean(pitches)
            pitch_std = np.std(pitches)
            pitch_accuracy = max(0, 100 - (pitch_std / pitch_mean * 100)) if pitch_mean > 0 else 0
            pitch_accuracy = min(100, pitch_accuracy)
            
            # 2. Pitch Stability (độ ổn định)
            pitch_stability = max(0, 100 - (pitch_std / pitch_mean * 200)) if pitch_mean > 0 else 0
            pitch_stability = min(100, pitch_stability)
            
            # 3. Volume Consistency (độ nhất quán âm lượng)
            audio_abs = np.abs(self.audio_data)
            volume_std = np.std(audio_abs)
            volume_mean = np.mean(audio_abs)
            volume_consistency = max(0, 100 - (volume_std / volume_mean * 100)) if volume_mean > 0 else 0
            volume_consistency = min(100, volume_consistency)
            
            # 4. Timing Accuracy (giả lập - dựa trên độ dài audio)
            duration = len(self.audio_data) / self.sample_rate
            timing_accuracy = 85  # Giá trị mặc định, có thể cải thiện với target timing
            
            # Tính điểm tổng (weighted average)
            total_score = (
                pitch_accuracy * 0.4 +
                pitch_stability * 0.25 +
                volume_consistency * 0.2 +
                timing_accuracy * 0.15
            )
            
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