"""
Quang Lưu Studio — Scoring Engine
Class: ScoringEngine
"""
import os
import time

from core.config import FFMPEG_LOCATION, RECORDINGS_DIR


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
    
    def download_youtube_audio(self, youtube_url, output_dir=None):
        """Tải audio từ YouTube URL"""
        try:
            if output_dir is None:
                output_dir = RECORDINGS_DIR
            print(f"📥 [DOWNLOAD] Bắt đầu tải audio từ YouTube: {youtube_url}")
            try:
                import yt_dlp
            except ImportError:
                raise ImportError("Thư viện 'yt-dlp' chưa được cài đặt. Vui lòng chạy: pip install yt-dlp")
            
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
            
            # Cấu hình yt-dlp — chỉ tải 60 giây đầu để tăng tốc dò tone
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
            if FFMPEG_LOCATION:
                ydl_opts['ffmpeg_location'] = FFMPEG_LOCATION
            
            print("⬇️  [DOWNLOAD] Đang tải video từ YouTube...")
            
            # Thử tải 60s đầu (cần ffmpeg trong PATH cho download_ranges)
            try:
                ydl_opts_partial = dict(ydl_opts)
                ydl_opts_partial['download_ranges'] = lambda info, ydl: [{'start_time': 0, 'end_time': 60}]
                with yt_dlp.YoutubeDL(ydl_opts_partial) as ydl:
                    ydl.download([youtube_url])
            except Exception as e_partial:
                # Fallback: tải toàn bộ audio nếu download_ranges thất bại
                print(f"⚠️ [DOWNLOAD] Không thể tải 60s đầu ({e_partial.__class__.__name__}), tải toàn bộ...")
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
    
    def download_youtube_audio_with_info(self, youtube_url, output_dir=None):
        """
        Tải audio + lấy title video trong 1 lần gọi yt-dlp duy nhất (tối ưu: giảm 1 network request).
        
        Returns:
            tuple[str|None, str]: (audio_path, video_title) — audio_path=None nếu lỗi
        """
        try:
            if output_dir is None:
                output_dir = RECORDINGS_DIR
            print(f"📥 [DOWNLOAD+INFO] Bắt đầu tải audio + info: {youtube_url}")
            try:
                import yt_dlp
            except ImportError:
                raise ImportError("Thư viện 'yt-dlp' chưa được cài đặt. Vui lòng chạy: pip install yt-dlp")
            
            import tempfile
            
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            temp_file = tempfile.NamedTemporaryFile(
                delete=False, suffix='.wav', dir=output_dir
            )
            temp_path = temp_file.name
            temp_file.close()
            
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
            if FFMPEG_LOCATION:
                ydl_opts['ffmpeg_location'] = FFMPEG_LOCATION
            
            video_title = ""
            
            # Thử tải 60s đầu + lấy info trong 1 lần
            try:
                ydl_opts_partial = dict(ydl_opts)
                ydl_opts_partial['download_ranges'] = lambda info, ydl: [{'start_time': 0, 'end_time': 60}]
                with yt_dlp.YoutubeDL(ydl_opts_partial) as ydl:
                    info = ydl.extract_info(youtube_url, download=True)
                    video_title = info.get('title', '') if info else ""
            except Exception as e_partial:
                print(f"⚠️ [DOWNLOAD+INFO] Partial download failed ({e_partial.__class__.__name__}), tải toàn bộ...")
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(youtube_url, download=True)
                    video_title = info.get('title', '') if info else ""
            
            print(f"✅ [DOWNLOAD+INFO] Tải thành công | Title: {video_title}")
            
            # Tìm file đã tải
            base_path = temp_path.replace('.wav', '')
            for ext in ['.wav', '.mp3', '.m4a', '.webm']:
                if os.path.exists(base_path + ext):
                    self.temp_audio_path = base_path + ext
                    file_size = os.path.getsize(self.temp_audio_path) / (1024 * 1024)
                    print(f"✅ [DOWNLOAD+INFO] File: {self.temp_audio_path} ({file_size:.2f} MB)")
                    return self.temp_audio_path, video_title
            
            raise Exception("Không tìm thấy file audio đã tải")
            
        except ImportError as e:
            raise e
        except Exception as e:
            print(f"❌ [DOWNLOAD+INFO] Lỗi: {e}")
            import traceback
            print(traceback.format_exc())
            return None, ""
    
    def cleanup_temp_file(self):
        """Xóa file tạm nếu có + giải phóng audio data trong RAM"""
        # Giải phóng audio data trong RAM (tránh tràn bộ nhớ)
        self.audio_data = None
        self.sample_rate = None
        
        if self.temp_audio_path and os.path.exists(self.temp_audio_path):
            try:
                os.remove(self.temp_audio_path)
            except Exception:
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
                
                base_score = 77
                score_range = 23
                volume_factor = min(100, volume_consistency) / 100.0
                random_bonus = random.uniform(0, score_range * volume_factor)
                total_score = base_score + random_bonus
                total_score = min(100, max(80, total_score))
                
                duration = len(self.audio_data) / self.sample_rate
                feedback = self._generate_feedback(total_score, 0, 0, volume_consistency, 85)
                
                return {
                    "total_score": round(total_score, 1),
                    "pitch_accuracy": 0,
                    "pitch_stability": 0,
                    "volume_consistency": round(volume_consistency, 1),
                    "timing_accuracy": round(85, 1),
                    "pitch_mean": 0,
                    "pitch_std": 0,
                    "duration": round(duration, 2),
                    "feedback": feedback
                }
            
            # Có pitch → tính điểm chi tiết
            pitch_mean = float(np.mean(pitches))
            pitch_std = float(np.std(pitches))
            
            # Pitch stability (80-100, dựa trên std deviation)
            max_std = 100  # Hz
            pitch_stability = max(80, 100 - (pitch_std / max_std * 20))
            
            # Volume consistency
            audio_abs = np.abs(self.audio_data)
            volume_std = np.std(audio_abs)
            volume_mean = np.mean(audio_abs)
            volume_consistency = max(0, 100 - (volume_std / volume_mean * 100)) if volume_mean > 0 else 50
            volume_consistency = min(100, volume_consistency)
            
            # Pitch accuracy (random 80-95 vì không có reference)
            pitch_accuracy = random.uniform(80, 95)
            
            # Timing (random 80-95)
            timing_accuracy = random.uniform(80, 95)
            
            # Tổng điểm weighted
            total_score = (
                pitch_accuracy * 0.35 +
                pitch_stability * 0.25 +
                volume_consistency * 0.20 +
                timing_accuracy * 0.20
            )
            total_score = min(100, max(77, total_score))
            
            duration = len(self.audio_data) / self.sample_rate
            feedback = self._generate_feedback(total_score, pitch_accuracy, pitch_stability,
                                                volume_consistency, timing_accuracy)
            
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
            print(f"❌ [CALCULATE SCORE] Lỗi: {e}")
            import traceback
            print(traceback.format_exc())
            return {
                "total_score": 80.0,
                "pitch_accuracy": 0,
                "pitch_stability": 0,
                "volume_consistency": 0,
                "timing_accuracy": 0,
                "pitch_mean": 0,
                "pitch_std": 0,
                "duration": 0,
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
