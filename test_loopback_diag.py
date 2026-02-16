"""
Diagnostic: Detect correct sample rate for loopback, then analyze key.
Tries both 44100 and 48000, picks the one with smallest tuning offset.
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
    
    DURATION = 15
    NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    
    # Find loopback mic
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
    print(f"Loopback mic: {loopback_mic.name}")
    
    # === TEST BOTH SAMPLE RATES ===
    for test_rate in [44100, 48000]:
        print(f"\n{'='*60}")
        print(f"THU AM VOI SAMPLE_RATE = {test_rate}")
        print(f"{'='*60}")
        print(f"Thu am {DURATION}s...")
        
        try:
            with loopback_mic.recorder(samplerate=test_rate, channels=1) as recorder:
                audio = recorder.record(numframes=DURATION * test_rate)
        except Exception as e:
            print(f"LOI: {e}")
            continue
        
        if audio.ndim > 1:
            audio = audio[:, 0]
        audio = audio.astype(np.float32)
        audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
        
        rms_val = np.sqrt(np.mean(audio ** 2))
        print(f"RMS: {rms_val:.6f}")
        if rms_val < 0.001:
            print("Im lang!")
            continue
        
        # Tuning
        tuning = librosa.estimate_tuning(y=audio, sr=test_rate)
        print(f"Tuning offset: {tuning:+.4f} semitones")
        
        if abs(tuning) < 0.15:
            print(">>> TUNING TOT! Sample rate nay co ve dung.")
        elif abs(tuning) > 0.3:
            print(">>> TUNING LON! Sample rate nay co the sai.")
        
        # Chroma CQT
        harmonic, _ = librosa.effects.hpss(audio)
        c1 = librosa.feature.chroma_cqt(y=harmonic, sr=test_rate)
        rms_h = librosa.feature.rms(y=harmonic)[0]
        mf = min(len(rms_h), c1.shape[1])
        w = rms_h[:mf] / np.sum(rms_h[:mf]) if np.sum(rms_h[:mf]) > 0 else None
        cqt_avg = np.average(c1[:, :mf], axis=1, weights=w) if w is not None else np.mean(c1, axis=1)
        
        norm = cqt_avg / np.sum(cqt_avg) if np.sum(cqt_avg) > 0 else cqt_avg
        print(f"\nChroma CQT (energy-weighted):")
        for i in range(12):
            bar = "#" * int(norm[i] * 100)
            print(f"  {NOTE_NAMES[i]:3s}: {norm[i]:.4f} {bar}")
        
        # Key detection
        print(f"\nKEY DETECTION (sr={test_rate}):")
        from backend import ToneDetector
        result = ToneDetector.detect_key_from_audio(audio, test_rate)
        if result:
            print(f"  >>> Detected: {result['key_display']} ({result['scale']})")
            print(f"  >>> Confidence: {result['confidence']:.4f}")
            for r in result.get('top_results', []):
                print(f"      {r['key']:4s}: {r['correlation']:.4f}")
        else:
            print("  No result!")

if __name__ == "__main__":
    main()
