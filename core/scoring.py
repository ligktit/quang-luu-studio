"""
Quang Luu Studio — Scoring Engine
Class: ScoringEngine

Entertainment-first scoring with real audio analysis.
Scores range ~65-98 with encouraging feedback and actionable tips.
"""
import os
import math
import time
import uuid

from core.config import RECORDINGS_DIR, TEMP_AUDIO_PREFIX
from core.ytdlp_support import download_with_auth, extract_info_with_auth, make_ydl_opts


def _make_temp_audio_path(output_dir):
    """Tạo đường dẫn file .wav tạm KHÔNG tạo file trước.

    QUAN TRỌNG: không dùng NamedTemporaryFile(delete=False) — file 0-byte
    tồn tại sẵn tại đúng path mà FFmpegExtractAudio nhắm tới khiến
    postprocessor bỏ qua bước convert → trả về wav 0-byte như thành công.
    """
    return os.path.join(output_dir, f"{TEMP_AUDIO_PREFIX}{uuid.uuid4().hex}.wav")


def _cleanup_temp_candidates(temp_path):
    """Xóa các file dở dang quanh temp_path khi download thất bại."""
    base_path = temp_path[:-4] if temp_path.endswith('.wav') else temp_path
    for ext in ['.wav', '.mp3', '.m4a', '.webm', '.part']:
        try:
            candidate = base_path + ext
            if os.path.exists(candidate):
                os.remove(candidate)
        except Exception:
            pass


# ── Musical constants ────────────────────────────────────────────────────────

_NOTE_TO_SEMITONE = {
    'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3,
    'E': 4, 'F': 5, 'F#': 6, 'Gb': 6, 'G': 7, 'G#': 8, 'Ab': 8,
    'A': 9, 'A#': 10, 'Bb': 10, 'B': 11,
}
_MAJOR_INTERVALS = frozenset({0, 2, 4, 5, 7, 9, 11})
_MINOR_INTERVALS = frozenset({0, 2, 3, 5, 7, 8, 10})


class ScoringEngine:
    """Engine cham diem sau khi hat — real analysis, encouraging results."""

    def __init__(self):
        self.audio_data = None
        self.sample_rate = None
        self.temp_audio_path = None
        self.key_reference = None  # e.g. "Am", "C", "F#m"

    # ── Audio Loading ────────────────────────────────────────────────────────

    def load_audio_data(self, audio_data, sample_rate=44100):
        """Load audio truc tiep tu numpy array."""
        import numpy as np
        self.audio_data = audio_data.astype(np.float32)
        self.sample_rate = sample_rate
        duration = len(self.audio_data) / self.sample_rate
        print(f"[SCORING] Loaded from memory: {duration:.1f}s, {len(self.audio_data)} samples")
        return True

    def load_audio(self, file_path):
        """Load file audio de phan tich."""
        try:
            print(f"[SCORING] Loading file: {file_path}")
            try:
                import librosa
                import numpy as np
            except ImportError:
                raise ImportError("Thu vien 'librosa' chua duoc cai dat. Chay: pip install librosa numpy")

            self.audio_data, self.sample_rate = librosa.load(file_path, sr=None, mono=True)
            duration = len(self.audio_data) / self.sample_rate
            print(f"[SCORING] Loaded: {duration:.1f}s, sr={self.sample_rate}Hz, {len(self.audio_data)} samples")
            return True
        except ImportError:
            raise
        except Exception as e:
            print(f"[SCORING] Load error: {e}")
            return False

    # ── YouTube Download ─────────────────────────────────────────────────────

    def download_youtube_audio(self, youtube_url, output_dir=None, max_seconds=None):
        """Tai audio tu YouTube URL."""
        try:
            if output_dir is None:
                output_dir = RECORDINGS_DIR
            print(f"[SCORING] Downloading audio: {youtube_url}")
            try:
                import yt_dlp
            except ImportError:
                raise ImportError("Thu vien 'yt-dlp' chua duoc cai dat.")

            os.makedirs(output_dir, exist_ok=True)

            # Tạo path tạm KHÔNG tạo file (tránh file 0-byte chặn FFmpegExtractAudio)
            temp_path = _make_temp_audio_path(output_dir)

            ydl_opts = make_ydl_opts(
                format='bestaudio/best',
                outtmpl=temp_path.replace('.wav', '.%(ext)s'),
                postprocessors=[{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'wav',
                    'preferredquality': '192',
                }],
            )

            dl_seconds = max_seconds or 60
            try:
                ydl_opts_partial = dict(ydl_opts)
                ydl_opts_partial['download_ranges'] = lambda info, ydl: [{'start_time': 0, 'end_time': dl_seconds}]
                download_with_auth(youtube_url, ydl_opts_partial, log_prefix="[SCORING]")
            except Exception:
                download_with_auth(youtube_url, ydl_opts, log_prefix="[SCORING]")

            base_path = temp_path.replace('.wav', '')
            for ext in ['.wav', '.mp3', '.m4a', '.webm']:
                if os.path.exists(base_path + ext):
                    self.temp_audio_path = base_path + ext
                    size_mb = os.path.getsize(self.temp_audio_path) / (1024 * 1024)
                    print(f"[SCORING] Downloaded: {self.temp_audio_path} ({size_mb:.2f} MB)")
                    return self.temp_audio_path

            raise Exception("Khong tim thay file audio da tai")
        except ImportError:
            raise
        except Exception as e:
            print(f"[SCORING] Download error: {e}")
            # Dọn file dở dang nếu download thất bại giữa chừng
            try:
                _cleanup_temp_candidates(temp_path)
            except NameError:
                pass
            return None

    def download_youtube_audio_with_info(self, youtube_url, output_dir=None):
        """Tai audio + lay title trong 1 lan goi."""
        try:
            if output_dir is None:
                output_dir = RECORDINGS_DIR
            print(f"[SCORING] Downloading audio + info: {youtube_url}")
            try:
                import yt_dlp
            except ImportError:
                raise ImportError("Thu vien 'yt-dlp' chua duoc cai dat.")

            os.makedirs(output_dir, exist_ok=True)

            # Tạo path tạm KHÔNG tạo file (tránh file 0-byte chặn FFmpegExtractAudio)
            temp_path = _make_temp_audio_path(output_dir)

            ydl_opts = make_ydl_opts(
                format='bestaudio/best',
                outtmpl=temp_path.replace('.wav', '.%(ext)s'),
                postprocessors=[{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'wav',
                    'preferredquality': '192',
                }],
            )

            video_title = ""
            try:
                ydl_opts_partial = dict(ydl_opts)
                ydl_opts_partial['download_ranges'] = lambda info, ydl: [{'start_time': 0, 'end_time': 50}]
                info = extract_info_with_auth(youtube_url, ydl_opts_partial, download=True, log_prefix="[SCORING]")
                video_title = info.get('title', '') if info else ""
            except Exception:
                info = extract_info_with_auth(youtube_url, ydl_opts, download=True, log_prefix="[SCORING]")
                video_title = info.get('title', '') if info else ""

            base_path = temp_path.replace('.wav', '')
            for ext in ['.wav', '.mp3', '.m4a', '.webm']:
                if os.path.exists(base_path + ext):
                    self.temp_audio_path = base_path + ext
                    return self.temp_audio_path, video_title

            raise Exception("Khong tim thay file audio da tai")
        except ImportError:
            raise
        except Exception as e:
            print(f"[SCORING] Download+info error: {e}")
            # Dọn file dở dang nếu download thất bại giữa chừng
            try:
                _cleanup_temp_candidates(temp_path)
            except NameError:
                pass
            return None, ""

    def cleanup_temp_file(self):
        """Xoa file tam + giai phong audio data."""
        self.audio_data = None
        self.sample_rate = None
        self.key_reference = None
        if self.temp_audio_path and os.path.exists(self.temp_audio_path):
            try:
                os.remove(self.temp_audio_path)
            except Exception:
                pass
            self.temp_audio_path = None

    # ── Core Scoring ─────────────────────────────────────────────────────────

    def calculate_score(self, target_notes=None, video_end=False, quick=False, key_reference=None):
        """
        Tinh diem dua tren phan tich audio thuc te.

        Args:
            key_reference: Key hien tai (VD: "Am", "C", "F#m"). Dung de
                           tinh do chinh xac theo thang am.
            quick: True = che do nhanh (chi volume + voiced ratio).
            video_end: True = goi khi video ket thuc.
        """
        try:
            import numpy as np

            if self.audio_data is None:
                return None

            if key_reference:
                self.key_reference = key_reference

            if quick or video_end:
                return self._calculate_quick_score()
            else:
                return self._calculate_full_score()

        except Exception as e:
            print(f"[SCORING] Error: {e}")
            import traceback
            print(traceback.format_exc())
            return {
                "total_score": 75.0,
                "pitch_intonation": 0,
                "pitch_stability": 0,
                "volume_consistency": 0,
                "rhythm_score": 0,
                "key_conformity": 0,
                "voiced_ratio": 0,
                "duration": 0,
                "feedback": {"rank": "Ca Si", "icon": "🎤", "main": f"Loi phan tich: {e}", "tips": []}
            }

    def _calculate_quick_score(self):
        """Quick mode: volume + basic voiced analysis (no full pyin)."""
        import numpy as np

        print("[SCORING] Quick mode: volume + voiced analysis")

        volume_consistency = self._compute_volume_consistency()
        voiced_ratio = self._compute_voiced_ratio_simple()

        # Quick score: weighted combination
        raw = volume_consistency * 0.5 + voiced_ratio * 0.5
        total = self._encourage(raw)

        duration = len(self.audio_data) / self.sample_rate

        feedback = self._generate_feedback(
            total_score=total,
            pitch_intonation=0,
            pitch_stability=0,
            volume_consistency=volume_consistency,
            rhythm_score=0,
            voiced_ratio=voiced_ratio,
            key_conformity=0,
        )

        print(f"[SCORING] Quick result: total={total:.1f} (vol={volume_consistency:.1f}, voiced={voiced_ratio:.1f})")

        return {
            "total_score": round(total, 1),
            "pitch_intonation": 0,
            "pitch_stability": 0,
            "volume_consistency": round(volume_consistency, 1),
            "rhythm_score": 0,
            "key_conformity": 0,
            "voiced_ratio": round(voiced_ratio, 1),
            "duration": round(duration, 2),
            "feedback": feedback,
        }

    def _calculate_full_score(self):
        """Full analysis with pitch tracking, rhythm, and key conformity."""
        import numpy as np
        import librosa

        print("[SCORING] Full analysis mode")

        # Volume consistency
        volume_consistency = self._compute_volume_consistency()

        # Pitch analysis via pyin
        f0, voiced_flag, voiced_probs = librosa.pyin(
            self.audio_data,
            fmin=librosa.note_to_hz('C2'),
            fmax=librosa.note_to_hz('C7'),
            frame_length=2048,
        )

        valid_mask = voiced_flag & ~np.isnan(f0)
        voiced_pitches = f0[valid_mask]
        has_pitch = len(voiced_pitches) >= 10

        if has_pitch:
            pitch_intonation = self._compute_pitch_intonation(f0, valid_mask)
            pitch_stability = self._compute_pitch_stability(f0, valid_mask, voiced_probs)
            key_conformity = self._compute_key_conformity(f0, valid_mask)
            voiced_ratio = (np.sum(valid_mask) / len(f0)) * 100
        else:
            pitch_intonation = 50
            pitch_stability = 50
            key_conformity = 80
            voiced_ratio = self._compute_voiced_ratio_simple()

        rhythm_score = self._compute_rhythm_score()

        # Weighted combination (raw 0-100)
        raw = (
            pitch_intonation * 0.30
            + pitch_stability * 0.25
            + volume_consistency * 0.20
            + rhythm_score * 0.15
            + key_conformity * 0.10
        )
        total = self._encourage(raw)

        duration = len(self.audio_data) / self.sample_rate

        feedback = self._generate_feedback(
            total_score=total,
            pitch_intonation=pitch_intonation,
            pitch_stability=pitch_stability,
            volume_consistency=volume_consistency,
            rhythm_score=rhythm_score,
            voiced_ratio=voiced_ratio,
            key_conformity=key_conformity,
        )

        print(
            f"[SCORING] Full result: total={total:.1f} "
            f"(intonation={pitch_intonation:.1f}, stability={pitch_stability:.1f}, "
            f"vol={volume_consistency:.1f}, rhythm={rhythm_score:.1f}, "
            f"key={key_conformity:.1f}, voiced={voiced_ratio:.1f}%)"
        )

        return {
            "total_score": round(total, 1),
            "pitch_intonation": round(pitch_intonation, 1),
            "pitch_stability": round(pitch_stability, 1),
            "volume_consistency": round(volume_consistency, 1),
            "rhythm_score": round(rhythm_score, 1),
            "key_conformity": round(key_conformity, 1),
            "voiced_ratio": round(voiced_ratio, 1),
            "duration": round(duration, 2),
            "feedback": feedback,
        }

    # ── Metric Computation ───────────────────────────────────────────────────

    def _compute_volume_consistency(self):
        """How stable the overall volume is (0-100)."""
        import numpy as np
        audio_abs = np.abs(self.audio_data)
        vol_mean = np.mean(audio_abs)
        if vol_mean <= 0:
            return 0
        vol_std = np.std(audio_abs)
        consistency = max(0, 100 - (vol_std / vol_mean * 100))
        return min(100, consistency)

    def _compute_voiced_ratio_simple(self):
        """Energy-based voice activity detection (no librosa.pyin needed)."""
        import numpy as np
        frame_len = 2048
        hop = 512
        n_frames = max(1, (len(self.audio_data) - frame_len) // hop + 1)

        rms_values = []
        for i in range(n_frames):
            start = i * hop
            frame = self.audio_data[start:start + frame_len]
            rms_values.append(np.sqrt(np.mean(frame ** 2)))

        rms_arr = np.array(rms_values)
        if len(rms_arr) == 0 or np.max(rms_arr) == 0:
            return 0

        # Threshold: frames above 10% of max RMS are considered "voiced"
        threshold = np.max(rms_arr) * 0.10
        voiced_count = np.sum(rms_arr > threshold)
        return (voiced_count / len(rms_arr)) * 100

    def _compute_pitch_intonation(self, f0, valid_mask):
        """How close each pitch is to the nearest musical semitone (0-100)."""
        import numpy as np
        voiced_pitches = f0[valid_mask]
        if len(voiced_pitches) < 10:
            return 50

        # Convert Hz to fractional MIDI note number
        midi_notes = 12 * np.log2(voiced_pitches / 440.0) + 69

        # Distance to nearest integer note, in cents (100 cents = 1 semitone)
        cents_deviation = np.abs(midi_notes - np.round(midi_notes)) * 100

        # Perfect intonation = 0 cents. Worst = 50 cents (halfway between notes).
        avg_deviation = np.mean(cents_deviation)

        # Score: 0 cents -> 100, 25 cents -> 50, 50 cents -> 0
        score = max(0, 100 - (avg_deviation / 25) * 50)
        return score

    def _compute_pitch_stability(self, f0, valid_mask, voiced_probs):
        """Low pitch jitter + high voiced probability = good stability (0-100)."""
        import numpy as np
        voiced_pitches = f0[valid_mask]
        if len(voiced_pitches) < 10:
            return 50

        # Frame-to-frame pitch change in semitones
        pitch_diffs = np.abs(12 * np.log2(voiced_pitches[1:] / voiced_pitches[:-1]))

        # Filter out large jumps (>6 semitones) — these are likely phrase boundaries
        phrase_diffs = pitch_diffs[pitch_diffs < 6]

        if len(phrase_diffs) > 0:
            mean_jitter = np.mean(phrase_diffs)
            # Good: < 0.3 semitones. Bad: > 2.0 semitones.
            jitter_score = max(0, min(100, 100 - (mean_jitter / 2.0) * 100))
        else:
            jitter_score = 50

        # Average voiced probability (how clear the voice signal is)
        valid_probs = voiced_probs[~np.isnan(voiced_probs)]
        voiced_prob_score = (np.mean(valid_probs) * 100) if len(valid_probs) > 0 else 50

        return jitter_score * 0.6 + voiced_prob_score * 0.4

    def _compute_key_conformity(self, f0, valid_mask):
        """What % of detected notes are in the expected key/scale (0-100)."""
        import numpy as np

        if not self.key_reference:
            return 80  # neutral if no key reference

        # Parse key reference (e.g. "Am", "C#", "Fm")
        key_str = str(self.key_reference)
        is_minor = key_str.endswith('m')
        root_name = key_str.rstrip('m').strip()

        root_semitone = _NOTE_TO_SEMITONE.get(root_name)
        if root_semitone is None:
            return 80  # unrecognized key

        intervals = _MINOR_INTERVALS if is_minor else _MAJOR_INTERVALS
        scale_notes = frozenset((root_semitone + i) % 12 for i in intervals)

        voiced_pitches = f0[valid_mask]
        if len(voiced_pitches) < 10:
            return 80

        midi_notes = 12 * np.log2(voiced_pitches / 440.0) + 69
        note_classes = np.round(midi_notes).astype(int) % 12

        in_key = sum(1 for n in note_classes if n in scale_notes)
        ratio = in_key / len(note_classes)

        return ratio * 100

    def _compute_rhythm_score(self):
        """Onset regularity — how rhythmically consistent the performance is (0-100)."""
        import numpy as np
        try:
            import librosa
            onsets = librosa.onset.onset_detect(
                y=self.audio_data, sr=self.sample_rate, units='time'
            )
        except Exception:
            return 70  # fallback

        if len(onsets) < 4:
            return 70  # not enough onsets to judge

        ioi = np.diff(onsets)
        mean_ioi = np.mean(ioi)
        if mean_ioi <= 0:
            return 70

        # Coefficient of variation (lower = more regular)
        cv = np.std(ioi) / mean_ioi

        # Good: CV < 0.4 (regular). Bad: CV > 1.2 (very irregular).
        score = max(0, min(100, 100 - (cv / 1.2) * 100))
        return score

    # ── Encouraging Transform ────────────────────────────────────────────────

    @staticmethod
    def _encourage(raw, floor=65, ceiling=98):
        """
        Transform raw 0-100 metric to encouraged range [floor, ceiling].
        Raw 0 -> 65, Raw 50 -> 81.5, Raw 100 -> 98.
        """
        return max(floor, min(ceiling, floor + (raw / 100) * (ceiling - floor)))

    # ── Feedback Generation ──────────────────────────────────────────────────

    def _generate_feedback(self, total_score, pitch_intonation, pitch_stability,
                           volume_consistency, rhythm_score, voiced_ratio, key_conformity):
        """Generate encouraging feedback with actionable tips based on real metrics."""
        import random

        # ── Rank & main comment ──
        if total_score >= 93:
            rank, icon = "Sieu Sao", "👑"
            mains = [
                "Tuyet voi qua! Giong hat cuc ky an tuong, bung no cam xuc!",
                "Hoan hao! Rat muot ma va day noi luc!",
                "10 diem khong co nhung! Co the di dien duoc roi!",
            ]
        elif total_score >= 88:
            rank, icon = "Ca Si Pro", "🏆"
            mains = [
                "Xuat sac! Ban hat rat tot va bat tai!",
                "Giong hat rat chuyen nghiep, xu ly muot ma!",
                "Rat cuon hut! Hay tiep tuc phat huy!",
            ]
        elif total_score >= 82:
            rank, icon = "Ngoi Sao Sang", "⭐"
            mains = [
                "Rat hay! Gan cham moc hoan hao roi do!",
                "Phong do rat tuyet, nghe rat phieu!",
                "Hat muot lam! Ghi chu lai bai nay lam 'bai tu' nhe!",
            ]
        elif total_score >= 75:
            rank, icon = "Giong Ca Trien Vong", "🎤"
            mains = [
                "Tot lam! Ban co chat giong rat bat mic!",
                "The hien tron ven cam xuc! Luyen them xiu nua la dinh!",
                "Rat on dinh! Co the tu tin khoe khoang duoc roi!",
            ]
        else:
            rank, icon = "Tap Su Day Tiem Nang", "💪"
            mains = [
                "Khong sao! Moi lan hat la mot lan tot hon ban than!",
                "Co co gang rat nhieu! Tap luyen them se rat bung no!",
                "Dam me la tren het! Thu lai nha!",
            ]

        main = random.choice(mains)

        # ── Actionable tips based on REAL metrics ──
        tips = []

        # Pitch intonation tips
        if pitch_intonation > 0:
            if pitch_intonation < 50:
                tips.append("Hay tap hat cham theo tung cau de giong chun hon. Thu hat theo piano/guitar.")
            elif pitch_intonation < 70:
                tips.append("Giong kha on, nhung mot so doan van con lech not. Thu tap voi tai nghe de nghe ro hon.")

        # Volume consistency tips
        if volume_consistency < 60:
            tips.append("Giu khoang cach voi mic deu dan hon — dung luc xa luc gan nhe.")
        elif volume_consistency < 75:
            tips.append("Am luong dang kha tot, thu kiem soat hoi tho deu hon o cac doan len cao.")

        # Key conformity tips
        if key_conformity > 0 and key_conformity < 60:
            tips.append("Co mot so not bi lech tong. Thu nghe ky nhac nen truoc khi bat dau hat.")
        elif key_conformity > 0 and key_conformity < 75:
            tips.append("Nhieu not da dung tong. Tap them vai lan nua se rat chinh xac!")

        # Rhythm tips
        if rhythm_score > 0 and rhythm_score < 50:
            tips.append("Nhip hat dang hoi lech. Thu go nhip chan hoac dung metronome de on dinh.")

        # Stability tips
        if pitch_stability > 0 and pitch_stability < 50:
            tips.append("Giong con rung mot chut. Thu hat nhe hon va giu hoi dai hon.")

        # Positive reinforcement for high scores
        if total_score >= 90 and len(tips) == 0:
            tips.append("Ban hat hay qua! Thu them cam xuc tinh te vao cac doan luyen/ngan nha.")
        elif total_score >= 82 and len(tips) == 0:
            tips.append("Lan toi hay de y them cac not cao nhat de khong bi hut hoi.")

        # Ensure at least 1 tip
        if not tips:
            tips.append("Luyen tap moi ngay se len than nhanh lam day!")

        return {
            "rank": rank,
            "icon": icon,
            "main": main,
            "tips": tips[:3],
        }
