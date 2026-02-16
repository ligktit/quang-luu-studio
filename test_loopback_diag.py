"""
Diagnostic v3: PYIN pitch tracking + chroma comparison + raw spectral analysis
Xac dinh chinh xac tai sao G chiem 39% thay vi Ab/F cho bai Fm.
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
    
    SAMPLE_RATE = 44100  # Keep simple
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
    audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
    
    rms_val = np.sqrt(np.mean(audio ** 2))
    print(f"RMS: {rms_val:.6f}, Max: {np.max(np.abs(audio)):.6f}")
    if rms_val < 0.001:
        print("Im lang!")
        return
    
    # === 1. PYIN PITCH TRACKING (exact frequencies, no binning) ===
    print("\n" + "=" * 60)
    print("1. PYIN PITCH TRACKING")
    print("=" * 60)
    try:
        f0, voiced_flag, voiced_probs = librosa.pyin(
            audio, fmin=librosa.note_to_hz('C2'), 
            fmax=librosa.note_to_hz('C7'), sr=SAMPLE_RATE
        )
        valid = ~np.isnan(f0) & voiced_flag
        if np.sum(valid) > 0:
            midi_notes = librosa.hz_to_midi(f0[valid])
            pitch_classes = np.round(midi_notes % 12).astype(int) % 12
            
            # Histogram
            pyin_hist = np.bincount(pitch_classes, minlength=12).astype(float)
            pyin_hist /= pyin_hist.sum() if pyin_hist.sum() > 0 else 1
            
            print(f"   Voiced frames: {np.sum(valid)}/{len(f0)} ({100*np.sum(valid)/len(f0):.0f}%)")
            print(f"   Pitch class histogram (PYIN):")
            for i in range(12):
                bar = "#" * int(pyin_hist[i] * 100)
                print(f"    {NOTE_NAMES[i]:3s}: {pyin_hist[i]:.4f} {bar}")
            
            # Top 3 frequencies
            freqs = f0[valid]
            print(f"\n   Top frequencies: min={np.min(freqs):.1f}Hz, max={np.max(freqs):.1f}Hz, median={np.median(freqs):.1f}Hz")
            
            # Most common MIDI notes
            from collections import Counter
            midi_rounded = np.round(midi_notes).astype(int)
            note_counts = Counter(midi_rounded)
            print(f"   Most common notes:")
            for midi_val, count in note_counts.most_common(8):
                note_name = librosa.midi_to_note(midi_val)
                print(f"     {note_name}: {count} frames ({100*count/len(midi_rounded):.1f}%)")
        else:
            print("   No voiced frames detected!")
            pyin_hist = None
    except Exception as e:
        print(f"   PYIN error: {e}")
        pyin_hist = None
    
    # === 2. CHROMA WITHOUT HPSS ===
    print("\n" + "=" * 60)
    print("2. CHROMA CQT (WITHOUT HPSS)")
    print("=" * 60)
    c_raw = librosa.feature.chroma_cqt(y=audio, sr=SAMPLE_RATE)
    raw_avg = np.mean(c_raw, axis=1)
    raw_norm = raw_avg / np.sum(raw_avg) if np.sum(raw_avg) > 0 else raw_avg
    for i in range(12):
        bar = "#" * int(raw_norm[i] * 100)
        print(f"  {NOTE_NAMES[i]:3s}: {raw_norm[i]:.4f} {bar}")
    
    # === 3. CHROMA WITH HPSS ===
    print("\n" + "=" * 60)
    print("3. CHROMA CQT (WITH HPSS)")
    print("=" * 60)
    harmonic, _ = librosa.effects.hpss(audio)
    c_hpss = librosa.feature.chroma_cqt(y=harmonic, sr=SAMPLE_RATE)
    rms_h = librosa.feature.rms(y=harmonic)[0]
    mf = min(len(rms_h), c_hpss.shape[1])
    w = rms_h[:mf] / np.sum(rms_h[:mf]) if np.sum(rms_h[:mf]) > 0 else None
    hpss_avg = np.average(c_hpss[:, :mf], axis=1, weights=w) if w is not None else np.mean(c_hpss, axis=1)
    hpss_norm = hpss_avg / np.sum(hpss_avg) if np.sum(hpss_avg) > 0 else hpss_avg
    for i in range(12):
        bar = "#" * int(hpss_norm[i] * 100)
        print(f"  {NOTE_NAMES[i]:3s}: {hpss_norm[i]:.4f} {bar}")
    
    # === 4. KEY DETECTION (current algorithm) ===
    print("\n" + "=" * 60)
    print("4. KEY DETECTION (algorithm hien tai)")
    print("=" * 60)
    from backend import ToneDetector
    result = ToneDetector.detect_key_from_audio(audio, SAMPLE_RATE)
    if result:
        print(f"\n>>> Detected: {result['key_display']} ({result['scale']})")
        for r in result.get('top_results', []):
            print(f"    {r['key']:4s}: {r['correlation']:.4f}")
    
    # === 5. KEY DETECTION WITH PYIN CHROMA ===
    if pyin_hist is not None:
        print("\n" + "=" * 60)
        print("5. KEY DETECTION (PYIN histogram)")
        print("=" * 60)
        result2 = ToneDetector.detect_key_from_audio(audio, SAMPLE_RATE)
        # Manual detection using pyin_hist
        W = ToneDetector.PROFILE_WEIGHTS
        ks_r = ToneDetector._correlate_profiles(pyin_hist, ToneDetector.KS_MAJOR, ToneDetector.KS_MINOR)
        temp_r = ToneDetector._correlate_profiles(pyin_hist, ToneDetector.TEMP_MAJOR, ToneDetector.TEMP_MINOR)
        aarden_r = ToneDetector._correlate_profiles(pyin_hist, ToneDetector.AARDEN_MAJOR, ToneDetector.AARDEN_MINOR)
        
        results = []
        for uid in set(ks_r.keys()) | set(temp_r.keys()) | set(aarden_r.keys()):
            kc = ks_r.get(uid, {}).get('correlation', 0)
            tc = temp_r.get(uid, {}).get('correlation', 0)
            ac = aarden_r.get(uid, {}).get('correlation', 0)
            wc = W['ks'] * kc + W['temperley'] * tc + W['aarden'] * ac
            ref = ks_r.get(uid) or temp_r.get(uid) or aarden_r.get(uid)
            if ref["scale"] == "Minor":
                wc *= 1.02
            results.append({"key": ref["key"], "scale": ref["scale"], "correlation": wc})
        
        results.sort(key=lambda x: x["correlation"], reverse=True)
        print(f">>> PYIN-based key: {results[0]['key']} ({results[0]['scale']})")
        for r in results[:5]:
            print(f"    {r['key']:4s}: {r['correlation']:.4f}")

if __name__ == "__main__":
    main()
