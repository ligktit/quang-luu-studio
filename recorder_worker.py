"""
Quang Lưu Studio — Audio Recorder Worker (Subprocess)
Chạy trong process riêng biệt để tránh xung đột COM với PySide6.

Thu âm MIX: nguồn nhạc (WASAPI Loopback HOẶC input device chỉ định) + Microphone.

Giao thức argv:
  Arg 1: Đường dẫn file WAV output
  Arg 2: Đường dẫn file flag (khi file này bị xóa → dừng thu)
  Arg 3: (tùy chọn) Index của loopback/input device để thu nhạc (-1 = auto)
  Arg 4: (tùy chọn) Index của microphone (-1 = auto)
"""
import sys
import wave
import os
import time
import queue
import numpy as np


def enumerate_all_devices(pa):
    """
    Trả về dict mô tả tất cả thiết bị âm thanh khả dụng.
    Dùng cho chẩn đoán và device picker.
    """
    devices = []
    for i in range(pa.get_device_count()):
        try:
            d = pa.get_device_info_by_index(i)
            api = pa.get_host_api_info_by_index(d["hostApi"])
            devices.append({
                "index": i,
                "name": d["name"],
                "host_api": api["name"],
                "in_ch": d["maxInputChannels"],
                "out_ch": d["maxOutputChannels"],
                "rate": int(d["defaultSampleRate"]),
                "is_loopback": d.get("isLoopbackDevice", False),
            })
        except Exception:
            continue
    return devices


def find_loopback_device(pa):
    """
    Tìm WASAPI loopback device tốt nhất để thu âm.

    Chiến lược (theo thứ tự ưu tiên):
      1. Loopback analogue của WASAPI default output (loa đang phát nhạc)
      2. Bất kỳ WASAPI loopback device nào còn lại

    Lý do: Nếu máy có nhiều loa (LoaX2, Speakers, Headset), phải lấy đúng
    loopback của loa đang phát nhạc, không phải loa random đầu tiên.
    """
    wasapi_info = None
    for i in range(pa.get_host_api_count()):
        info = pa.get_host_api_info_by_index(i)
        if "wasapi" in info.get("name", "").lower():
            wasapi_info = info
            break

    if not wasapi_info:
        print("ERROR: Windows WASAPI host API not found", file=sys.stderr, flush=True)
        return None

    wasapi_api_idx = wasapi_info["index"]

    # Thu thập tất cả loopback devices thuộc WASAPI
    all_loopbacks = []
    for i in range(pa.get_device_count()):
        try:
            dev = pa.get_device_info_by_index(i)
            if dev.get("isLoopbackDevice", False) and dev.get("hostApi") == wasapi_api_idx:
                all_loopbacks.append(dev)
        except Exception:
            continue

    if not all_loopbacks:
        return None

    # Ưu tiên 1: loopback analogue của WASAPI default output
    try:
        default_out_idx = wasapi_info.get("defaultOutputDevice", -1)
        if default_out_idx >= 0:
            default_out = pa.get_device_info_by_index(default_out_idx)
            default_out_name = default_out.get("name", "").lower()
            print(f"INFO: Default output: [{default_out_idx}] {default_out['name']!r}", flush=True)

            for lb in all_loopbacks:
                lb_name = lb.get("name", "").lower()
                lb_base = lb_name.replace("[loopback]", "").strip()
                if lb_base in default_out_name or default_out_name in lb_base:
                    print(f"INFO: Matched loopback analogue: [{lb['index']}] {lb['name']!r}", flush=True)
                    return lb

            # Thử helper API
            try:
                analogue = pa.get_wasapi_loopback_analogue_by_index(default_out_idx)
                if analogue:
                    print(f"INFO: Helper API loopback: [{analogue['index']}] {analogue['name']!r}", flush=True)
                    return analogue
            except (AttributeError, Exception):
                pass
    except Exception as e:
        print(f"WARNING: Could not find default output loopback: {e}", flush=True)

    # Ưu tiên 2: fallback về loopback đầu tiên
    fallback = all_loopbacks[0]
    print(f"WARNING: Using fallback loopback: [{fallback['index']}] {fallback['name']!r}", flush=True)
    return fallback


def find_default_mic(pa):
    """Tìm microphone mặc định (input device)."""
    try:
        default_idx = pa.get_default_input_device_info()["index"]
        dev = pa.get_device_info_by_index(default_idx)
        if dev["maxInputChannels"] > 0:
            return dev
    except Exception:
        pass

    # Fallback: tìm bất kỳ input device nào
    for i in range(pa.get_device_count()):
        try:
            dev = pa.get_device_info_by_index(i)
            if dev["maxInputChannels"] > 0 and not dev.get("isLoopbackDevice", False):
                return dev
        except Exception:
            continue
    return None


def open_input_stream(pa, dev_info, channels, rate, chunk_size, callback):
    """
    Mở input stream với fallback channels=2 nếu cần.
    Trả về (stream, actual_channels) hoặc raise Exception.
    """
    ch = channels
    if ch == 0:
        ch = 2

    for attempt_ch in [ch, 2, 1]:
        try:
            stream = pa.open(
                format=pa.get_format_from_width(2),  # paInt16
                channels=attempt_ch,
                rate=rate,
                input=True,
                input_device_index=dev_info["index"],
                frames_per_buffer=chunk_size,
                stream_callback=callback
            )
            if attempt_ch != channels:
                print(f"WARNING: Opened with channels={attempt_ch} (requested {channels})", flush=True)
            return stream, attempt_ch
        except Exception as e:
            print(f"WARNING: Open failed ch={attempt_ch}: {e}", flush=True)

    raise RuntimeError(f"Cannot open stream for device [{dev_info['index']}] {dev_info['name']!r}")


def main():
    if len(sys.argv) < 3:
        print("Usage: recorder_worker.py <output.wav> <stop_flag> [loopback_idx] [mic_idx]",
              file=sys.stderr)
        sys.exit(1)

    output_path = sys.argv[1]
    stop_flag = sys.argv[2]
    # Arg tùy chọn: device index (-1 = auto)
    req_loopback_idx = int(sys.argv[3]) if len(sys.argv) > 3 else -1
    req_mic_idx = int(sys.argv[4]) if len(sys.argv) > 4 else -1

    import pyaudiowpatch as pyaudio

    pa = pyaudio.PyAudio()

    # ── Chọn thiết bị thu nhạc ──────────────────────────────────────
    if req_loopback_idx >= 0:
        # Dùng device do user chỉ định
        try:
            loopback_dev = pa.get_device_info_by_index(req_loopback_idx)
            print(f"INFO: Using user-selected device: [{req_loopback_idx}] {loopback_dev['name']!r}", flush=True)
        except Exception as e:
            print(f"ERROR: Invalid loopback device index {req_loopback_idx}: {e}",
                  file=sys.stderr, flush=True)
            pa.terminate()
            sys.exit(2)
    else:
        loopback_dev = find_loopback_device(pa)
        if not loopback_dev:
            print("ERROR: No WASAPI loopback device found. "
                  "If using ASIO driver, please select the ASIOVADPRO WDM output device manually.",
                  file=sys.stderr, flush=True)
            pa.terminate()
            sys.exit(2)

    # ── Chọn microphone ─────────────────────────────────────────────
    if req_mic_idx == -2:
        # -2 = tắt mic hoàn toàn
        mic_dev = None
        print("INFO: Microphone disabled by user", flush=True)
    elif req_mic_idx >= 0:
        try:
            mic_dev = pa.get_device_info_by_index(req_mic_idx)
            print(f"INFO: Using user-selected mic: [{req_mic_idx}] {mic_dev['name']!r}", flush=True)
        except Exception as e:
            print(f"WARNING: Invalid mic device index {req_mic_idx}: {e}, using default", flush=True)
            mic_dev = find_default_mic(pa)
    else:
        mic_dev = find_default_mic(pa)

    # ── Thông số ────────────────────────────────────────────────────
    lb_rate = int(loopback_dev["defaultSampleRate"])
    lb_channels = loopback_dev["maxInputChannels"]
    if lb_channels == 0:
        lb_channels = 2
        print("WARNING: Loopback reported 0 channels, overriding to 2", flush=True)
    lb_channels = min(lb_channels, 8)

    out_rate = lb_rate
    out_channels = 2

    # Chunk size loopback: 1024 frames (~21ms @ 48kHz) — ổn định.
    CHUNK_SIZE = 1024

    print(f"LOOPBACK: {loopback_dev['name']}", flush=True)
    print(f"RATE: {out_rate}", flush=True)
    print(f"CHANNELS: {out_channels}", flush=True)
    print(f"CHUNK_SIZE: {CHUNK_SIZE}", flush=True)

    mic_rate = lb_rate  # default
    mic_channels = 2
    actual_mic_channels = 2
    # Tính resample ratio 1 lần duy nhất (cố định).
    mic_resample_ratio = 1.0
    # Mic chunk size tỉ lệ theo rate — đảm bảo callback mic kích hoạt
    # đúng nhịp tương đương loopback (~21ms), tránh lệch pha → giật.
    mic_chunk_size = CHUNK_SIZE  # sẽ tính lại sau khi biết mic_rate

    if mic_dev:
        mic_rate = int(mic_dev["defaultSampleRate"])
        mic_channels = mic_dev["maxInputChannels"]
        if mic_channels == 0:
            mic_channels = 2
        mic_resample_ratio = lb_rate / mic_rate
        # Chunk size tương đương ~21ms tại mic rate
        mic_chunk_size = max(256, int(round(CHUNK_SIZE * mic_rate / lb_rate)))
        print(
            f"MIC: {mic_dev['name']} "
            f"(rate={mic_rate}, ch={mic_channels}, "
            f"chunk={mic_chunk_size}, resample={mic_resample_ratio:.4f}x)",
            flush=True
        )
    else:
        print("WARNING: No microphone, recording loopback only", flush=True)

    # FIX 3: queue.Queue thay lock+list.
    # put_nowait() trong ASIO callback KHÔNG bao giờ block → không làm trễ
    # real-time thread của driver → không bị overrun/xif buffer.
    LB_QUEUE_MAXSIZE = 200   # ~4s buffer @ 1024 frames / 48kHz
    MC_QUEUE_MAXSIZE = 200

    lb_queue = queue.Queue(maxsize=LB_QUEUE_MAXSIZE)
    mc_queue = queue.Queue(maxsize=MC_QUEUE_MAXSIZE)
    overflow_count = [0]

    def loopback_callback(in_data, frame_count, time_info, status):
        try:
            lb_queue.put_nowait(in_data)
        except queue.Full:
            overflow_count[0] += 1  # Drop thay vì block callback
        return (None, pyaudio.paContinue)

    def mic_callback(in_data, frame_count, time_info, status):
        try:
            mc_queue.put_nowait(in_data)
        except queue.Full:
            overflow_count[0] += 1
        return (None, pyaudio.paContinue)

    # ── Mở loopback stream ──────────────────────────────────────────
    try:
        lb_stream, lb_channels = open_input_stream(
            pa, loopback_dev, lb_channels, lb_rate, CHUNK_SIZE, loopback_callback
        )
    except Exception as e:
        print(f"ERROR: Cannot open loopback stream: {e}", file=sys.stderr, flush=True)
        pa.terminate()
        sys.exit(3)

    # ── Mở mic stream ───────────────────────────────────────────────
    mic_stream = None
    if mic_dev:
        try:
            mic_stream, actual_mic_channels = open_input_stream(
                pa, mic_dev, mic_channels, mic_rate, mic_chunk_size, mic_callback
            )
        except Exception as e:
            print(f"WARNING: Cannot open mic stream: {e}", flush=True)
            mic_stream = None

    # ── Mở file WAV output ─────────────────────────────────────────
    sample_width = pa.get_sample_size(pyaudio.paInt16)
    wf = wave.open(output_path, 'wb')
    wf.setnchannels(out_channels)
    wf.setsampwidth(sample_width)
    wf.setframerate(out_rate)

    # ── Bắt đầu thu ────────────────────────────────────────────────
    lb_stream.start_stream()
    if mic_stream:
        mic_stream.start_stream()

    print("STARTED", flush=True)

    frames_written = 0

    # FIX 4: Sleep interval đồng bộ với chunk duration thực tế.
    # Cũ: 20ms cứng → lệch pha với chunk 10.67ms → burst write không đều.
    # Mới: 1 chunk duration = 1024/48000 ≈ 21.3ms → xử lý đúng nhịp.
    sleep_interval = CHUNK_SIZE / lb_rate

    try:
        while os.path.exists(stop_flag):
            time.sleep(sleep_interval)

            # Drain tất cả chunks tích lũy trong queue (không block)
            lb_chunks = []
            while True:
                try:
                    lb_chunks.append(lb_queue.get_nowait())
                except queue.Empty:
                    break

            mc_chunks = []
            if mic_stream:
                while True:
                    try:
                        mc_chunks.append(mc_queue.get_nowait())
                    except queue.Empty:
                        break

            # Nếu cả hai queue đều rỗng → chờ vòng tiếp theo
            if not lb_chunks and not mc_chunks:
                continue

            # Nếu CHỈ có mic data (loopback chưa kịp fill) → KHÔNG bỏ qua!
            # Mic chunks sẽ được xử lý và mix với silence loopback.

            # ── Chuyển loopback data → numpy float32 stereo ──
            if lb_chunks:
                lb_raw = b"".join(lb_chunks)
                lb_arr = np.frombuffer(lb_raw, dtype=np.int16)
                if lb_channels == 1:
                    lb_stereo = np.column_stack([lb_arr, lb_arr]).astype(np.float32)
                elif lb_channels == 2:
                    lb_stereo = lb_arr.reshape(-1, 2).astype(np.float32)
                else:
                    lb_arr2 = lb_arr.reshape(-1, lb_channels)
                    lb_stereo = lb_arr2[:, :2].astype(np.float32)
            else:
                lb_stereo = None

            # ── Chuyển mic data → numpy float32 stereo + resample ratio cố định ──
            mc_stereo = None
            if mc_chunks and mic_stream:
                mc_raw = b"".join(mc_chunks)
                mc_arr = np.frombuffer(mc_raw, dtype=np.int16)
                if actual_mic_channels == 1:
                    mc_float = np.column_stack([mc_arr, mc_arr]).astype(np.float32)
                else:
                    mc_float = mc_arr.reshape(-1, actual_mic_channels)[:, :2].astype(np.float32)

                if mic_resample_ratio != 1.0 and mc_float.shape[0] > 0:
                    src_len = mc_float.shape[0]
                    dst_len = max(1, int(round(src_len * mic_resample_ratio)))
                    src_idx = np.arange(src_len, dtype=np.float32)
                    dst_idx = np.linspace(0.0, src_len - 1, dst_len, dtype=np.float32)
                    left  = np.interp(dst_idx, src_idx, mc_float[:, 0])
                    right = np.interp(dst_idx, src_idx, mc_float[:, 1])
                    mc_stereo = np.column_stack([left, right]).astype(np.float32)
                else:
                    mc_stereo = mc_float

            # ── Mix 2 nguồn ──
            if lb_stereo is not None and mc_stereo is not None:
                min_len = min(lb_stereo.shape[0], mc_stereo.shape[0])
                mixed = np.clip(
                    lb_stereo[:min_len] + mc_stereo[:min_len],
                    -32768.0, 32767.0
                ).astype(np.int16)
                # Append phần dư của nguồn dài hơn (không bị cắt)
                if lb_stereo.shape[0] > min_len:
                    mixed = np.vstack([mixed, lb_stereo[min_len:].astype(np.int16)])
                elif mc_stereo.shape[0] > min_len:
                    mixed = np.vstack([mixed, mc_stereo[min_len:].astype(np.int16)])
            elif lb_stereo is not None:
                mixed = lb_stereo.astype(np.int16)
            elif mc_stereo is not None:
                mixed = mc_stereo.astype(np.int16)
            else:
                continue

            wf.writeframes(mixed.tobytes())
            frames_written += mixed.shape[0]

    except KeyboardInterrupt:
        pass

    # ── Cleanup ─────────────────────────────────────────────────────
    if overflow_count[0] > 0:
        print(
            f"WARNING: {overflow_count[0]} audio chunks dropped (queue overflow — "
            f"CPU quá tải hoặc write WAV quá chậm)",
            flush=True
        )

    for s in [mic_stream, lb_stream]:
        if s:
            try:
                s.stop_stream()
                s.close()
            except Exception:
                pass

    wf.close()
    pa.terminate()

    duration = frames_written / out_rate if out_rate > 0 else 0
    print(f"DONE: {duration:.1f}s written to {output_path}", flush=True)


if __name__ == "__main__":
    main()
