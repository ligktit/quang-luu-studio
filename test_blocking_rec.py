"""Test blocking read mode for WASAPI loopback."""
import pyaudiowpatch as pyaudio
import wave
import time
import os

pa = pyaudio.PyAudio()

dev = None
for i in range(pa.get_device_count()):
    d = pa.get_device_info_by_index(i)
    if d.get("isLoopbackDevice", False):
        dev = d
        break

print(f"Device: {dev['name']}")
sr = int(dev["defaultSampleRate"])
ch = dev["maxInputChannels"]

# Blocking mode (no callback)
stream = pa.open(
    format=pyaudio.paInt16,
    channels=ch,
    rate=sr,
    input=True,
    input_device_index=dev["index"],
    frames_per_buffer=1024
)

frames = []
print(f"Recording 3 seconds (blocking read)...")
for i in range(int(sr / 1024 * 3)):
    data = stream.read(1024, exception_on_overflow=False)
    frames.append(data)

stream.stop_stream()
stream.close()
pa.terminate()

print(f"Captured {len(frames)} frames")
wf = wave.open("test_blocking.wav", "wb")
wf.setnchannels(ch)
wf.setsampwidth(2)
wf.setframerate(sr)
wf.writeframes(b''.join(frames))
wf.close()
print(f"Saved: test_blocking.wav ({os.path.getsize('test_blocking.wav')} bytes)")
