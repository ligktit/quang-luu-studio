"""
Diagnostic: Thu loopback 15s → phân tích chroma + key → in chi tiết.
So sánh kết quả với Auto-Key.
Chạy bài nhạc trước rồi chạy script này.
"""
import sys
sys.path.insert(0, '.')
import numpy as np
import ctypes

def main():
    # COM init
    try:
        ctypes.windll.ole32.CoInitializeEx(None, 0)
    except:
        pass
    
    try:
        import soundcard as sc
    except ImportError:
        print("❌ pip install soundcard")
        return
    
    SAMPLE_RATE = 44100
    DURATION = 15  # 15 giây
    
    # Tìm loopback
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
        print("❌ Không tìm thấy loopback mic!")
        return
    
    print(f"🎤 Microphone: {loopback_mic.name}")
    print(f"⏱️ Thu âm {DURATION}s... (bật nhạc trước!)")
    
    with loopback_mic.recorder(samplerate=SAMPLE_RATE, channels=1) as recorder:
        audio = recorder.record(numframes=DURATION * SAMPLE_RATE)
    
    if audio.ndim > 1:
        audio = audio[:, 0]
    audio = audio.astype(np.float32)
    audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
    
    rms = np.sqrt(np.mean(audio ** 2))
    print(f"📊 RMS: {rms:.6f}")
    if rms < 0.001:
        print("❌ Im lặng!")
        return
    
    # Phân tích chi tiết
    import librosa
    
    print("\n" + "=" * 60)
    print("PHÂN TÍCH CHI TIẾT")
    print("=" * 60)
    
    # Tuning
    tuning = librosa.estimate_tuning(y=audio, sr=SAMPLE_RATE)
    print(f"\n🎼 Tuning offset: {tuning:.4f} semitones (0 = standard A440)")
    
    # HPSS
    harmonic, _ = librosa.effects.hpss(audio)
    
    # So sánh chroma types
    NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    
    print("\n--- Chroma CQT (energy-weighted) ---")
    chroma_cqt = librosa.feature.chroma_cqt(y=harmonic, sr=SAMPLE_RATE)
    rms_h = librosa.feature.rms(y=harmonic)[0]
    mf = min(len(rms_h), chroma_cqt.shape[1])
    rms_h = rms_h[:mf]; chroma_cqt = chroma_cqt[:, :mf]
    rs = np.sum(rms_h)
    cqt_avg = np.average(chroma_cqt, axis=1, weights=rms_h/rs) if rs > 0 else np.mean(chroma_cqt, axis=1)
    cqt_norm = cqt_avg / np.sum(cqt_avg) if np.sum(cqt_avg) > 0 else cqt_avg
    for i, v in enumerate(cqt_norm):
        bar = "█" * int(v * 100)
        print(f"  {NOTE_NAMES[i]:3s}: {v:.4f} {bar}")
    
    print("\n--- Chroma CQT (with tuning correction) ---")
    chroma_cqt_t = librosa.feature.chroma_cqt(y=harmonic, sr=SAMPLE_RATE, tuning=tuning)
    cqt_t_avg = np.average(chroma_cqt_t[:, :mf], axis=1, weights=rms_h/rs) if rs > 0 else np.mean(chroma_cqt_t, axis=1)
    cqt_t_norm = cqt_t_avg / np.sum(cqt_t_avg) if np.sum(cqt_t_avg) > 0 else cqt_t_avg
    for i, v in enumerate(cqt_t_norm):
        bar = "█" * int(v * 100)
        print(f"  {NOTE_NAMES[i]:3s}: {v:.4f} {bar}")
    
    print("\n--- Chroma CENS ---")
    chroma_cens = librosa.feature.chroma_cens(y=harmonic, sr=SAMPLE_RATE)
    cens_avg = np.mean(chroma_cens, axis=1)
    cens_norm = cens_avg / np.sum(cens_avg) if np.sum(cens_avg) > 0 else cens_avg
    for i, v in enumerate(cens_norm):
        bar = "█" * int(v * 100)
        print(f"  {NOTE_NAMES[i]:3s}: {v:.4f} {bar}")
    
    print("\n--- Chroma STFT ---")
    chroma_stft = librosa.feature.chroma_stft(y=harmonic, sr=SAMPLE_RATE, tuning=tuning)
    stft_avg = np.mean(chroma_stft, axis=1)
    stft_norm = stft_avg / np.sum(stft_avg) if np.sum(stft_avg) > 0 else stft_avg
    for i, v in enumerate(stft_norm):
        bar = "█" * int(v * 100)
        print(f"  {NOTE_NAMES[i]:3s}: {v:.4f} {bar}")
    
    # Key detection với thuật toán hiện tại
    print("\n" + "=" * 60)
    print("KẾT QUẢ TỪ THUẬT TOÁN HIỆN TẠI")
    print("=" * 60)
    from backend import ToneDetector
    result = ToneDetector.detect_key_from_audio(audio, SAMPLE_RATE)
    if result:
        print(f"\n🎯 Detected: {result['key_display']} ({result['scale']})")
        print(f"   Confidence: {result['confidence']:.4f}")
        for r in result.get('top_results', []):
            print(f"   {r['key']:4s}: {r['correlation']:.4f}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
