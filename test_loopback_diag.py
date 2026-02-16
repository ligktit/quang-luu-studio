"""
Diagnostic: Thu loopback 15s -> phan tich chroma + key -> in chi tiet.
Chay bai nhac truoc roi chay script nay.
"""
import sys
sys.path.insert(0, '.')
import numpy as np
import ctypes

# Patch numpy.fromstring for Python 3.14 + soundcard compatibility
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
    
    SAMPLE_RATE = 48000  # Windows WASAPI loopback = device output rate
    DURATION = 15
    
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
    
    print(f"Mic: {loopback_mic.name}")
    print(f"Thu am {DURATION}s... (bat nhac truoc!)")
    
    with loopback_mic.recorder(samplerate=SAMPLE_RATE, channels=1) as recorder:
        audio = recorder.record(numframes=DURATION * SAMPLE_RATE)
    
    if audio.ndim > 1:
        audio = audio[:, 0]
    audio = audio.astype(np.float32)
    audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
    
    rms_val = np.sqrt(np.mean(audio ** 2))
    print(f"RMS: {rms_val:.6f}")
    if rms_val < 0.001:
        print("Im lang!")
        return
    
    print("\n" + "=" * 60)
    
    tuning = librosa.estimate_tuning(y=audio, sr=SAMPLE_RATE)
    print(f"Tuning offset: {tuning:.4f} semitones")
    
    harmonic, _ = librosa.effects.hpss(audio)
    
    NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    
    def print_chroma(name, chroma_vec):
        print(f"\n--- {name} ---")
        norm = chroma_vec / np.sum(chroma_vec) if np.sum(chroma_vec) > 0 else chroma_vec
        for i in range(12):
            bar = "#" * int(norm[i] * 100)
            print(f"  {NOTE_NAMES[i]:3s}: {norm[i]:.4f} {bar}")
        return norm
    
    # CQT energy-weighted
    c1 = librosa.feature.chroma_cqt(y=harmonic, sr=SAMPLE_RATE)
    rms_h = librosa.feature.rms(y=harmonic)[0]
    mf = min(len(rms_h), c1.shape[1])
    w = rms_h[:mf] / np.sum(rms_h[:mf]) if np.sum(rms_h[:mf]) > 0 else None
    cqt_avg = np.average(c1[:, :mf], axis=1, weights=w) if w is not None else np.mean(c1, axis=1)
    print_chroma("Chroma CQT (energy-weighted)", cqt_avg)
    
    # CQT with tuning correction
    c2 = librosa.feature.chroma_cqt(y=harmonic, sr=SAMPLE_RATE, tuning=tuning)
    mf2 = min(len(rms_h), c2.shape[1])
    w2 = rms_h[:mf2] / np.sum(rms_h[:mf2]) if np.sum(rms_h[:mf2]) > 0 else None
    cqt_t_avg = np.average(c2[:, :mf2], axis=1, weights=w2) if w2 is not None else np.mean(c2, axis=1)
    print_chroma("Chroma CQT (tuning-corrected)", cqt_t_avg)
    
    # CENS
    c3 = librosa.feature.chroma_cens(y=harmonic, sr=SAMPLE_RATE)
    cens_avg = np.mean(c3, axis=1)
    print_chroma("Chroma CENS", cens_avg)
    
    # STFT
    c4 = librosa.feature.chroma_stft(y=harmonic, sr=SAMPLE_RATE, tuning=tuning)
    stft_avg = np.mean(c4, axis=1)
    print_chroma("Chroma STFT (tuning-corrected)", stft_avg)
    
    # Key detection
    print("\n" + "=" * 60)
    print("KET QUA KEY DETECTION")
    print("=" * 60)
    from backend import ToneDetector
    result = ToneDetector.detect_key_from_audio(audio, SAMPLE_RATE)
    if result:
        print(f"\nDetected: {result['key_display']} ({result['scale']})")
        print(f"Confidence: {result['confidence']:.4f}")
        for r in result.get('top_results', []):
            print(f"  {r['key']:4s}: {r['correlation']:.4f}")
    else:
        print("No result!")

if __name__ == "__main__":
    main()
