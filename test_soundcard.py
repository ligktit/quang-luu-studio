import soundcard as sc
import threading
import time

def record_loop():
    print("Start recording loop...")
    loopback = sc.default_speaker()
    mic = None
    all_mics = sc.all_microphones(include_loopback=True)
    speaker_name = loopback.name if loopback else ""
    for m in all_mics:
        if hasattr(m, 'isloopback') and m.isloopback:
            if speaker_name and speaker_name.lower() in m.name.lower():
                mic = m
    try:
        if not mic: mic = sc.get_microphone(id=str(loopback.name), include_loopback=True)
    except:
        pass
        
    try:
        with mic.recorder(samplerate=44100, channels=1) as rec:
            print("Recording 4410 frames...")
            chunk = rec.record(numframes=4410)
            print("Got chunk:", len(chunk))
    except Exception as e:
        print("Error:", e)
    print("Record loop done.")

t = threading.Thread(target=record_loop)
t.start()

for i in range(5):
    print(f"Main thread waiting {i}")
    time.sleep(1)

print("Main thread done. Now exiting.")
