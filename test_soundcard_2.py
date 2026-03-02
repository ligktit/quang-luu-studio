import soundcard as sc
import numpy as np
import time
import soundfile as sf
import threading

def record_loop():
    print("Start recording loop...")
    loopback = sc.default_speaker()
    
    if not hasattr(np, 'fromstring'):
        np.fromstring = np.frombuffer

    mic = sc.get_microphone(id=str(loopback.name), include_loopback=True)
    recorded_audio = []
    chunk_size = int(44100 * 0.1)

    try:
        with mic.recorder(samplerate=44100, channels=2) as rec:
            for i in range(50): # 5 seconds
                chunk = rec.record(numframes=chunk_size)
                print(f"Recorded chunk {i} - len: {len(chunk)} - sum: {np.sum(np.abs(chunk))}")
                if len(chunk) > 0:
                    recorded_audio.append(chunk)
    except Exception as e:
        print("Error:", e)
    finally:
        print("Done recording chunks:", len(recorded_audio))
        if recorded_audio:
            audio_data = np.concatenate(recorded_audio, axis=0)
            print("Audio data shape:", audio_data.shape)
            print("Audio data values (max, min):", np.max(audio_data), np.min(audio_data))
            sf.write('test_out.wav', audio_data, 44100)
            print("Saved test_out.wav")

t = threading.Thread(target=record_loop)
t.start()
t.join()
