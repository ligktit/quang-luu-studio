import pyaudiowpatch as pyaudio

print("SUCCESS: pyaudiowpatch imported")

pa = pyaudio.PyAudio()

print(f"Host APIs: {pa.get_host_api_count()}")
print(f"Devices: {pa.get_device_count()}")

for i in range(pa.get_device_count()):
    dev = pa.get_device_info_by_index(i)
    if dev.get("isLoopbackDevice", False):
        print(f"\n[LOOPBACK] #{i}: {dev['name']}")
        print(f"  Rate: {dev['defaultSampleRate']}")
        print(f"  Channels: {dev['maxInputChannels']}")
        print(f"  HostApi: {dev['hostApi']}")

pa.terminate()
print("\nDone!")
