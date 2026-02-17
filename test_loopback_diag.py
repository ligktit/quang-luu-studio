"""
Diagnostic v4: Test robust preprocessing pipeline
Verify rằng CQT chroma (no HPSS) + notch filter cho kết quả đúng
"""
import sys
sys.path.insert(0, '.')
import numpy as np

# Patch numpy.fromstring
_orig = np.fromstring
def _patched(string, dtype=float, count=-1, *, sep='', like=None):
    if not sep:
        return np.frombuffer(string, dtype=dtype, count=count)
    return _orig(string, dtype=dtype, count=count, sep=sep)
np.fromstring = _patched

def main():
    try:
        import soundcard as sc
    except ImportError:
        print("pip install soundcard")
        return
    
    import librosa
    
    SAMPLE_RATE = 44100
    DURATION = 15
    NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    
    # Find loopback
    all_mics = sc.all_microphones(include_loopback=True)
    default_speaker = sc.default_speaker()
    speaker_name = default_speaker.name if default_speaker else ""
    loopback_mic = None
    for mic in all_mics:
        if hasattr(mic, 'isloopback') and mic.isloopback:
            if loopback_mic is None:
                loopback_mic = mic
            if speaker_name and speaker_name.lower() in mic.name.lower():
                loopback_mic = mic
    
    if not loopback_mic:
        print("Khong tim thay loopback mic!")
        return
    
    print(f"Speaker: {speaker_name}")
    print(f"Loopback: {loopback_mic.name}")
    print(f"Thu am {DURATION}s...")
    
    with loopback_mic.recorder(samplerate=SAMPLE_RATE, channels=1) as recorder:
        audio = recorder.record(numframes=DURATION * SAMPLE_RATE)
    
    if audio.ndim > 1:
        audio = audio[:, 0]
    audio = audio.astype(np.float32)
    
    raw_max = np.max(np.abs(audio))
    print(f"Raw max: {raw_max:.6f}")
    
    # === 1. Raw chroma (baseline - no preprocessing) ===
    print("\n" + "=" * 60)
    print("1. RAW CHROMA (no preprocessing, no HPSS)")
    print("=" * 60)
    audio_clean = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
    audio_clean = np.clip(audio_clean, -1e6, 1e6)
    p999 = np.percentile(np.abs(audio_clean), 99.9)
    if p999 > 0:
        audio_clean = audio_clean / p999
    audio_clean = np.clip(audio_clean, -1.0, 1.0)
    
    c_raw = librosa.feature.chroma_cqt(y=audio_clean, sr=SAMPLE_RATE)
    raw_avg = np.mean(c_raw, axis=1)
    raw_norm = raw_avg / np.sum(raw_avg) if np.sum(raw_avg) > 0 else raw_avg
    for i in range(12):
        bar = "#" * int(raw_norm[i] * 100)
        print(f"  {NOTE_NAMES[i]:3s}: {raw_norm[i]:.4f} {bar}")
    
    # === 2. With notch filter ===
    print("\n" + "=" * 60)
    print("2. CHROMA AFTER NOTCH FILTER (no HPSS)")
    print("=" * 60)
    audio_notch = audio_clean.copy()
    audio_notch = audio_notch - np.mean(audio_notch)  # DC removal
    try:
        f0_detect, voiced, _ = librosa.pyin(
            audio_notch, fmin=50, fmax=150, sr=SAMPLE_RATE, frame_length=4096
        )
        valid_f0 = f0_detect[~np.isnan(f0_detect) & voiced]
        if len(valid_f0) > 100:
            hum_freq = np.median(valid_f0)
            hum_ratio = np.sum(np.abs(valid_f0 - hum_freq) < 2) / len(valid_f0)
            print(f"  Hum detected: {hum_freq:.1f}Hz ({hum_ratio*100:.0f}% consistency)")
            if hum_ratio > 0.8:
                S = librosa.stft(audio_notch)
                freqs = librosa.fft_frequencies(sr=SAMPLE_RATE)
                for n in range(1, 4):
                    target = hum_freq * n
                    S[np.abs(freqs - target) < 5] = 0
                audio_notch = librosa.istft(S, length=len(audio_notch))
                print(f"  Applied notch at {hum_freq:.0f}Hz + harmonics")
        else:
            print("  No hum detected")
    except Exception as e:
        print(f"  Hum detection error: {e}")
    
    c_notch = librosa.feature.chroma_cqt(y=audio_notch, sr=SAMPLE_RATE)
    notch_avg = np.mean(c_notch, axis=1)
    notch_norm = notch_avg / np.sum(notch_avg) if np.sum(notch_avg) > 0 else notch_avg
    for i in range(12):
        bar = "#" * int(notch_norm[i] * 100)
        print(f"  {NOTE_NAMES[i]:3s}: {notch_norm[i]:.4f} {bar}")
    
    # === 3. Full pipeline (backend algorithm) ===
    print("\n" + "=" * 60)
    print("3. FULL PIPELINE (backend detect_key_from_audio)")
    print("=" * 60)
    from backend import ToneDetector
    result = ToneDetector.detect_key_from_audio(audio, SAMPLE_RATE)
    if result:
        print(f"\n>>> KẾT QUẢ: {result['key_display']} ({result['scale']})")
        print(f">>> Confidence: {result['confidence']:.4f}")
        for r in result.get('top_results', []):
            print(f"    {r['key']:4s}: {r['correlation']:.4f}")
    else:
        print(">>> No result!")

if __name__ == "__main__":
    main()