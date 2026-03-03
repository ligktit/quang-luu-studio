"""
Audio Processor — Uses librosa and numpy to process audio buffers
for waveform visualization and music analysis (key, scale, tempo).
"""

import numpy as np
import librosa
from collections import deque, Counter


# Pitch class names — use conventional enharmonic spellings per scale.
# Major keys: C, Db, D, Eb, E, F, F#/Gb, G, Ab, A, Bb, B
# Minor keys: C, C#, D, D#/Eb, E, F, F#, G, G#, A, Bb, B
_MAJOR_KEY_NAMES = ["C", "Db", "D", "Eb", "E", "F",
                    "Gb", "G", "Ab", "A", "Bb", "B"]
_MINOR_KEY_NAMES = ["C", "C#", "D", "Eb", "E", "F",
                    "F#", "G", "G#", "A", "Bb", "B"]

# Major and minor profiles (Krumhansl-Kessler)
_MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                           2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                           2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


class AudioProcessor:
    """Processes raw audio buffers for visualization and analysis."""

    def __init__(self, sample_rate=44100):
        self.sample_rate = sample_rate
        self._history = np.zeros(4096, dtype=np.float32)
        self._rms_smooth = 0.0
        self._spectral_centroid_smooth = 0.5

        # Longer buffer for key/tempo analysis (~8 seconds)
        self._analysis_buffer_size = sample_rate * 8
        self._analysis_buffer = np.zeros(self._analysis_buffer_size, dtype=np.float32)
        self._analysis_fill = 0

        # Smoothed analysis results
        self._key = "--"
        self._scale = "--"
        self._bpm = 0.0
        self._analysis_counter = 0

        # Key vote history for stable detection (majority voting)
        self._key_votes = deque(maxlen=15)

    def process(self, audio_buffer):
        """
        Process a raw audio buffer and return visualization + analysis data.

        Returns dict with:
            - waveform: smoothed waveform array for drawing
            - rms: RMS energy (0.0 - 1.0 range, smoothed)
            - spectral_centroid_norm: normalized spectral centroid (0.0 - 1.0)
            - zcr: zero crossing rate
            - key: detected musical key (e.g. "C", "A#")
            - scale: "Major" or "Minor"
            - bpm: estimated beats per minute
        """
        if audio_buffer is None or len(audio_buffer) == 0:
            return self._empty_result()

        # Update rolling history (for waveform display)
        buf_len = len(audio_buffer)
        self._history = np.roll(self._history, -buf_len)
        self._history[-buf_len:] = audio_buffer

        # Update analysis buffer (for key/tempo)
        self._append_analysis_buffer(audio_buffer)

        # --- RMS Energy ---
        rms = librosa.feature.rms(
            y=audio_buffer, frame_length=512, hop_length=256
        )[0]
        rms_val = float(np.mean(rms)) if len(rms) > 0 else 0.0
        self._rms_smooth = self._rms_smooth * 0.7 + rms_val * 0.3
        rms_normalized = min(1.0, self._rms_smooth * 5.0)

        # --- Spectral Centroid ---
        try:
            sc = librosa.feature.spectral_centroid(
                y=audio_buffer, sr=self.sample_rate
            )[0]
            sc_val = float(np.mean(sc)) if len(sc) > 0 else 0.0
            sc_norm = min(1.0, sc_val / (self.sample_rate / 2))
        except Exception:
            sc_norm = 0.5
        self._spectral_centroid_smooth = (
            self._spectral_centroid_smooth * 0.8 + sc_norm * 0.2
        )

        # --- Zero Crossing Rate ---
        zcr = librosa.feature.zero_crossing_rate(audio_buffer)[0]
        zcr_val = float(np.mean(zcr)) if len(zcr) > 0 else 0.0

        # --- Key / Scale / BPM (run every ~10 blocks to save CPU) ---
        self._analysis_counter += 1
        if self._analysis_counter >= 10 and self._analysis_fill > self.sample_rate:
            self._analysis_counter = 0
            self._run_analysis()

        # --- Waveform for display ---
        display_points = 800
        step = max(1, len(self._history) // display_points)
        waveform = self._history[::step][:display_points]

        if rms_normalized > 0.01:
            scale = min(1.0, 0.3 / (rms_normalized + 0.001))
            waveform = waveform * scale
        else:
            waveform = waveform * 0.1

        return {
            "waveform": waveform,
            "rms": rms_normalized,
            "spectral_centroid_norm": self._spectral_centroid_smooth,
            "zcr": zcr_val,
            "key": self._key,
            "scale": self._scale,
            "bpm": self._bpm,
        }

    def _append_analysis_buffer(self, audio_buffer):
        """Append audio to the rolling analysis buffer."""
        n = len(audio_buffer)
        if n >= self._analysis_buffer_size:
            self._analysis_buffer[:] = audio_buffer[-self._analysis_buffer_size:]
            self._analysis_fill = self._analysis_buffer_size
        else:
            self._analysis_buffer = np.roll(self._analysis_buffer, -n)
            self._analysis_buffer[-n:] = audio_buffer
            self._analysis_fill = min(self._analysis_fill + n,
                                      self._analysis_buffer_size)

    def _run_analysis(self):
        """Estimate key, scale, and BPM from the analysis buffer."""
        buf = self._analysis_buffer[-self._analysis_fill:]

        # Skip if audio is too quiet (silence)
        if np.max(np.abs(buf)) < 0.005:
            self._key = "--"
            self._scale = "--"
            self._bpm = 0.0
            return

        try:
            self._detect_key(buf)
        except Exception:
            pass

        try:
            self._detect_tempo(buf)
        except Exception:
            pass

    def _detect_key(self, buf):
        """Detect key and scale using chroma features with majority voting."""
        chroma = librosa.feature.chroma_cqt(
            y=buf, sr=self.sample_rate, hop_length=512
        )
        chroma_mean = np.mean(chroma, axis=1)  # 12-element vector

        if np.sum(chroma_mean) < 1e-6:
            return

        # Correlate with major/minor profiles for each possible key
        best_corr = -1.0
        best_key = 0
        best_scale = "Major"

        for shift in range(12):
            rolled = np.roll(chroma_mean, -shift)
            corr_major = float(np.corrcoef(rolled, _MAJOR_PROFILE)[0, 1])
            corr_minor = float(np.corrcoef(rolled, _MINOR_PROFILE)[0, 1])

            if corr_major > best_corr:
                best_corr = corr_major
                best_key = shift
                best_scale = "Major"
            if corr_minor > best_corr:
                best_corr = corr_minor
                best_key = shift
                best_scale = "Minor"

        # Ignore weak detections (low confidence)
        if best_corr < 0.5:
            return

        # Add this detection to the vote history
        if best_scale == "Major":
            key_name = _MAJOR_KEY_NAMES[best_key]
        else:
            key_name = _MINOR_KEY_NAMES[best_key]
        self._key_votes.append((key_name, best_scale))

        # Majority vote: only update if a key clearly dominates
        if len(self._key_votes) >= 3:
            vote_counts = Counter(self._key_votes)
            winner, count = vote_counts.most_common(1)[0]
            # Require at least 40% of votes to switch
            if count >= len(self._key_votes) * 0.4:
                self._key = winner[0]
                self._scale = winner[1]

    def _detect_tempo(self, buf):
        """Estimate tempo/BPM."""
        tempo = librosa.beat.tempo(y=buf, sr=self.sample_rate)
        bpm_val = float(tempo[0]) if len(tempo) > 0 else 0.0
        # Smooth BPM to avoid jitter
        if self._bpm > 0:
            self._bpm = self._bpm * 0.6 + bpm_val * 0.4
        else:
            self._bpm = bpm_val

    def _empty_result(self):
        return {
            "waveform": np.zeros(800, dtype=np.float32),
            "rms": 0.0,
            "spectral_centroid_norm": 0.5,
            "zcr": 0.0,
            "key": "--",
            "scale": "--",
            "bpm": 0.0,
        }

    def reset(self):
        """Reset all history and smoothed values."""
        self._history = np.zeros(4096, dtype=np.float32)
        self._analysis_buffer = np.zeros(self._analysis_buffer_size, dtype=np.float32)
        self._analysis_fill = 0
        self._rms_smooth = 0.0
        self._spectral_centroid_smooth = 0.5
        self._key = "--"
        self._scale = "--"
        self._bpm = 0.0
        self._analysis_counter = 0
        self._key_votes.clear()
