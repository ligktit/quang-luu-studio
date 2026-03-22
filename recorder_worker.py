"""
Quang Lưu Studio — Audio Recorder Worker (Subprocess)
Chạy trong process riêng biệt để tránh xung đột COM với PySide6.
Thu âm MIX: WASAPI Loopback (nhạc phát ra loa) + Microphone (giọng hát).

Sử dụng callback streams để thu đồng thời 2 nguồn âm thanh,
mix lại với nhau và ghi ra file WAV.
"""
import sys
import wave
import os
import time
import threading
import numpy as np


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


def find_default_mic(pa):
    """Tìm microphone mặc định (input device)."""
    try:
        # Lấy default input device
        default_idx = pa.get_default_input_device_info()["index"]
        dev = pa.get_device_info_by_index(default_idx)
        if dev["maxInputChannels"] > 0:
            return dev
    except Exception:
        pass
    
    # Fallback: tìm bất kỳ input device nào có channels > 0
    for i in range(pa.get_device_count()):
        try:
            dev = pa.get_device_info_by_index(i)
            if dev["maxInputChannels"] > 0 and not dev.get("isLoopbackDevice", False):
                return dev
        except Exception:
            continue
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
    loopback_dev = find_loopback_device(pa)
    mic_dev = find_default_mic(pa)
    
    if not loopback_dev:
        print("ERROR: No WASAPI loopback device found", file=sys.stderr)
        pa.terminate()
        sys.exit(2)
    
    # ── Thông số Loopback (nhạc) ──
    lb_rate = int(loopback_dev["defaultSampleRate"])
    lb_channels = loopback_dev["maxInputChannels"]
    
    # ── Thông số output: dùng sample rate của loopback ──
    out_rate = lb_rate
    out_channels = 2  # Luôn ghi stereo
    chunk_size = 512
    
    print(f"LOOPBACK: {loopback_dev['name']}", flush=True)
    print(f"RATE: {out_rate}", flush=True)
    print(f"CHANNELS: {out_channels}", flush=True)
    
    if mic_dev:
        mic_rate = int(mic_dev["defaultSampleRate"])
        mic_channels = mic_dev["maxInputChannels"]
        print(f"MIC: {mic_dev['name']} (rate={mic_rate}, ch={mic_channels})", flush=True)
    else:
        print("WARNING: No microphone found, recording loopback only", flush=True)
    
    # ── Buffers thread-safe ──
    # Dùng lock để đồng bộ giữa 2 callback streams
    lock = threading.Lock()
    loopback_buffer = []
    mic_buffer = []
    
    def loopback_callback(in_data, frame_count, time_info, status):
        with lock:
            loopback_buffer.append(in_data)
        return (None, pyaudio.paContinue)
    
    def mic_callback(in_data, frame_count, time_info, status):
        with lock:
            mic_buffer.append(in_data)
        return (None, pyaudio.paContinue)
    
    # ── Mở streams ──
    lb_stream = pa.open(
        format=pyaudio.paInt16,
        channels=lb_channels,
        rate=lb_rate,
        input=True,
        input_device_index=loopback_dev["index"],
        frames_per_buffer=chunk_size,
        stream_callback=loopback_callback
    )
    
    mic_stream = None
    if mic_dev:
        try:
            mic_stream = pa.open(
                format=pyaudio.paInt16,
                channels=min(mic_channels, 2),  # Giới hạn 2 channels
                rate=mic_rate,
                input=True,
                input_device_index=mic_dev["index"],
                frames_per_buffer=chunk_size,
                stream_callback=mic_callback
            )
            actual_mic_channels = min(mic_channels, 2)
        except Exception as e:
            print(f"WARNING: Cannot open mic stream: {e}", flush=True)
            mic_stream = None
    
    # ── Mở file WAV output ──
    sample_width = pa.get_sample_size(pyaudio.paInt16)
    wf = wave.open(output_path, 'wb')
    wf.setnchannels(out_channels)
    wf.setsampwidth(sample_width)
    wf.setframerate(out_rate)
    
    # ── Bắt đầu thu ──
    lb_stream.start_stream()
    if mic_stream:
        mic_stream.start_stream()
    
    print("STARTED", flush=True)
    
    frames_written = 0
    frame_count = 0
    
    try:
        while os.path.exists(stop_flag):
            time.sleep(0.02)  # 20ms polling
            
            # Lấy data từ buffers
            with lock:
                lb_chunks = list(loopback_buffer)
                loopback_buffer.clear()
                mc_chunks = list(mic_buffer)
                mic_buffer.clear()
            
            if not lb_chunks and not mc_chunks:
                continue
            
            # ── Chuyển loopback data → numpy stereo ──
            if lb_chunks:
                lb_raw = b"".join(lb_chunks)
                lb_arr = np.frombuffer(lb_raw, dtype=np.int16)
                # Chuyển về stereo nếu cần
                if lb_channels == 1:
                    lb_stereo = np.column_stack([lb_arr, lb_arr])
                elif lb_channels == 2:
                    lb_stereo = lb_arr.reshape(-1, 2)
                else:
                    # Nhiều hơn 2 channels → lấy 2 đầu
                    lb_arr = lb_arr.reshape(-1, lb_channels)
                    lb_stereo = lb_arr[:, :2]
            else:
                lb_stereo = None
            
            # ── Chuyển mic data → numpy stereo ──
            if mc_chunks and mic_stream:
                mc_raw = b"".join(mc_chunks)
                mc_arr = np.frombuffer(mc_raw, dtype=np.int16)
                
                if actual_mic_channels == 1:
                    mc_stereo = np.column_stack([mc_arr, mc_arr])
                else:
                    mc_stereo = mc_arr.reshape(-1, 2)
                
                # Resample nếu mic rate khác loopback rate
                if mic_rate != lb_rate and lb_stereo is not None:
                    target_len = lb_stereo.shape[0]
                    if mc_stereo.shape[0] != target_len and mc_stereo.shape[0] > 0:
                        # Simple linear interpolation resample
                        indices = np.linspace(0, mc_stereo.shape[0] - 1, target_len)
                        mc_left = np.interp(indices, np.arange(mc_stereo.shape[0]), mc_stereo[:, 0].astype(np.float32))
                        mc_right = np.interp(indices, np.arange(mc_stereo.shape[0]), mc_stereo[:, 1].astype(np.float32))
                        mc_stereo = np.column_stack([mc_left, mc_right]).astype(np.int16)
                elif mic_rate != lb_rate and lb_stereo is None:
                    # Chỉ có mic, resample về out_rate
                    ratio = out_rate / mic_rate
                    target_len = int(mc_stereo.shape[0] * ratio)
                    if target_len > 0 and mc_stereo.shape[0] > 0:
                        indices = np.linspace(0, mc_stereo.shape[0] - 1, target_len)
                        mc_left = np.interp(indices, np.arange(mc_stereo.shape[0]), mc_stereo[:, 0].astype(np.float32))
                        mc_right = np.interp(indices, np.arange(mc_stereo.shape[0]), mc_stereo[:, 1].astype(np.float32))
                        mc_stereo = np.column_stack([mc_left, mc_right]).astype(np.int16)
            else:
                mc_stereo = None
            
            # ── Mix 2 nguồn ──
            if lb_stereo is not None and mc_stereo is not None:
                # Cắt/pad cho cùng độ dài
                min_len = min(lb_stereo.shape[0], mc_stereo.shape[0])
                lb_f = lb_stereo[:min_len].astype(np.float32)
                mc_f = mc_stereo[:min_len].astype(np.float32)
                
                # Mix: cộng lại và clip để tránh overflow int16
                mixed = lb_f + mc_f
                mixed = np.clip(mixed, -32768, 32767).astype(np.int16)
                
                # Ghi phần còn lại (nếu một bên dài hơn)
                if lb_stereo.shape[0] > min_len:
                    remainder = lb_stereo[min_len:]
                    mixed = np.vstack([mixed, remainder])
                elif mc_stereo.shape[0] > min_len:
                    remainder = mc_stereo[min_len:]
                    mixed = np.vstack([mixed, remainder])
                    
            elif lb_stereo is not None:
                mixed = lb_stereo
            elif mc_stereo is not None:
                mixed = mc_stereo
            else:
                continue
            
            # ── Ghi ra file ──
            wf.writeframes(mixed.tobytes())
            frames_written += mixed.shape[0]
            
            # Cleanup intermediate arrays — tránh tích lũy objects trong GC gen-0
            del lb_chunks, mc_chunks, lb_stereo, mc_stereo, mixed
            
            # Periodic GC mỗi 250 frames (~5s) — chỉ gen 0, rất nhẹ
            frame_count += 1
            if frame_count % 250 == 0:
                import gc
                gc.collect(0)
            
    except KeyboardInterrupt:
        pass
    
    # ── Cleanup ──
    if mic_stream:
        try:
            mic_stream.stop_stream()
            mic_stream.close()
        except Exception:
            pass
    
    try:
        lb_stream.stop_stream()
        lb_stream.close()
    except Exception:
        pass
    
    wf.close()
    pa.terminate()
    
    duration = frames_written / out_rate if out_rate > 0 else 0
    print(f"DONE: {duration:.1f}s written to {output_path}", flush=True)


if __name__ == "__main__":
    main()
