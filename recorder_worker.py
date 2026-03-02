"""
Quang Lưu Studio — Audio Recorder Worker (Subprocess)
Chạy trong process riêng biệt để tránh xung đột COM với PySide6.
Thu âm WASAPI Loopback (tất cả âm thanh phát ra loa: nhạc + giọng hát qua DAW).

Sử dụng blocking stream.read() — WASAPI loopback sẽ tự động stream data
khi có âm thanh phát ra loa. Khi không có âm thanh, nó sẽ chờ (block).
Điều này không ảnh hưởng UI vì chạy trong subprocess riêng biệt.
"""
import sys
import wave
import os
import time

def find_loopback_device(pa):
    """Tìm WASAPI loopback device mặc định."""
    wasapi_info = None
    for i in range(pa.get_host_api_count()):
        info = pa.get_host_api_info_by_index(i)
        if "wasapi" in info.get("name", "").lower():
            wasapi_info = info
            break
    
    if not wasapi_info:
        return None
    
    for i in range(pa.get_device_count()):
        dev = pa.get_device_info_by_index(i)
        if dev.get("isLoopbackDevice", False):
            if dev.get("hostApi") == wasapi_info["index"]:
                return dev
    return None


def main():
    """
    Giao thức: 
      - Arg 1: Đường dẫn file WAV output
      - Arg 2: Đường dẫn file flag (khi file này bị xóa → dừng thu)
    """
    if len(sys.argv) < 3:
        print("Usage: recorder_worker.py <output.wav> <stop_flag_file>", file=sys.stderr)
        sys.exit(1)
    
    output_path = sys.argv[1]
    stop_flag = sys.argv[2]
    
    import pyaudiowpatch as pyaudio
    
    pa = pyaudio.PyAudio()
    dev = find_loopback_device(pa)
    
    if not dev:
        print("ERROR: No WASAPI loopback device found", file=sys.stderr)
        pa.terminate()
        sys.exit(2)
    
    sample_rate = int(dev["defaultSampleRate"])
    channels = dev["maxInputChannels"]
    sample_width = pa.get_sample_size(pyaudio.paInt16)
    chunk_size = 512  # Nhỏ hơn để giảm blocking time
    
    print(f"RECORDING: {dev['name']}", flush=True)
    print(f"RATE: {sample_rate}", flush=True)
    print(f"CHANNELS: {channels}", flush=True)
    
    # Mở file WAV để ghi trực tiếp (streaming) — không cần giữ trong RAM
    wf = wave.open(output_path, 'wb')
    wf.setnchannels(channels)
    wf.setsampwidth(sample_width)
    wf.setframerate(sample_rate)
    
    # Mở stream blocking mode
    stream = pa.open(
        format=pyaudio.paInt16,
        channels=channels,
        rate=sample_rate,
        input=True,
        input_device_index=dev["index"],
        frames_per_buffer=chunk_size
    )
    
    print("STARTED", flush=True)
    
    frames_written = 0
    try:
        while os.path.exists(stop_flag):
            try:
                data = stream.read(chunk_size, exception_on_overflow=False)
                wf.writeframes(data)
                frames_written += chunk_size
            except OSError:
                # Stream bị lỗi tạm thời, thử lại
                time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    
    # Cleanup
    stream.stop_stream()
    stream.close()
    wf.close()
    pa.terminate()
    
    duration = frames_written / sample_rate if sample_rate > 0 else 0
    print(f"DONE: {duration:.1f}s written to {output_path}", flush=True)


if __name__ == "__main__":
    main()
