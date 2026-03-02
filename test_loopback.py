import pyaudio

pa = pyaudio.PyAudio()

for i in range(pa.get_device_count()):
    dev = pa.get_device_info_by_index(i)
    if dev.get("isLoopbackDevice", False):
        print(f"[LOOPBACK] #{i}: {dev['name']}")
        print(f"  Rate: {dev['defaultSampleRate']}")
        print(f"  Channels: {dev['maxInputChannels']}")

pa.terminate()
