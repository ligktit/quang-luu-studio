"""Debug: run recording inline (no subprocess) to test if PyAudioWPatch captures audio."""
import pyaudiowpatch as pyaudio
import wave
import time

pa = pyaudio.PyAudio()

# Find loopback
dev = None
for i in range(pa.get_device_count()):
    d = pa.get_device_info_by_index(i)
    if d.get("isLoopbackDevice", False):
        dev = d
        break

if not dev:
    print("No loopback device!")
    pa.terminate()
    exit(1)

print(f"Device: {dev['name']}")
print(f"Rate: {dev['defaultSampleRate']}, Channels: {dev['maxInputChannels']}")

sr = int(dev["defaultSampleRate"])
ch = dev["maxInputChannels"]
frames = []

def callback(in_data, frame_count, time_info, status):
    frames.append(in_data)
    return (None, pyaudio.paContinue)

stream = pa.open(
    format=pyaudio.paInt16,
    channels=ch,
    rate=sr,
    input=True,
    input_device_index=dev["index"],
    frames_per_buffer=1024,
    stream_callback=callback
)
stream.start_stream()

print(f"Recording for 3 seconds...")
for i in range(30):
    time.sleep(0.1)
    if i % 10 == 0:
        print(f"  {i/10:.0f}s - frames: {len(frames)}")

stream.stop_stream()
stream.close()
pa.terminate()

print(f"\nTotal frames captured: {len(frames)}")
if frames:
    wf = wave.open("test_direct.wav", "wb")
    wf.setnchannels(ch)
    wf.setsampwidth(2)
    wf.setframerate(sr)
    wf.writeframes(b''.join(frames))
    wf.close()
    import os
    print(f"Saved test_direct.wav ({os.path.getsize('test_direct.wav')} bytes)")
