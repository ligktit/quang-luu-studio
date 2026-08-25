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


# ── Thông số trộn tiếng ────────────────────────────────────────────────────────
# Cộng thẳng loopback + mic rồi cắt cứng ở ±32767 là nguồn gốc tiếng "rè rè":
# nhạc karaoke vốn đã gần 0 dBFS, cộng thêm giọng là méo vuông (hard clipping).
# Chừa headroom cho mỗi nguồn, phần đỉnh còn lại do PeakLimiter lo.
MIX_LB_GAIN = 0.80    # nhạc (loopback) — giảm ~1.9 dB
MIX_MIC_GAIN = 0.80   # giọng (mic)     — giảm ~1.9 dB

# Chunk lớn hơn → ít lần callback/giây hơn → ít cơ hội bị kẹt GIL khi worker
# chạy inline trong process GUI (bản đóng gói). 2048 frames ≈ 43ms @ 48kHz.
CHUNK_SIZE = 2048

# Hàng đợi ~20s: hấp thụ được cả lúc ghi đĩa bị antivirus chặn tạm thời.
QUEUE_MAXSIZE = 512


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
            print(f"INFO: Output: [{default_out_idx}] {default_out['name'][:30]}", flush=True)

            for lb in all_loopbacks:
                lb_name = lb.get("name", "").lower()
                lb_base = lb_name.replace("[loopback]", "").strip()
                if lb_base in default_out_name or default_out_name in lb_base:
                    print(f"INFO: Loopback: [{lb['index']}] {lb['name'][:30]}", flush=True)
                    return lb

            # Thử helper API
            try:
                analogue = pa.get_wasapi_loopback_analogue_by_index(default_out_idx)
                if analogue:
                    print(f"INFO: Loopback API: [{analogue['index']}] {analogue['name'][:30]}", flush=True)
                    return analogue
            except (AttributeError, Exception):
                pass
    except Exception as e:
        print(f"WARNING: Could not find default output loopback: {e}", flush=True)

    # Ưu tiên 2: fallback về loopback đầu tiên
    fallback = all_loopbacks[0]
    print(f"WARNING: Dùng loopback dự phòng: [{fallback['index']}] {fallback['name']!r}", flush=True)
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


class PeakLimiter:
    """
    Giới hạn đỉnh bằng cách hạ gain theo thời gian, không bẻ méo dạng sóng.

    Cắt cứng (np.clip) biến đỉnh sóng thành mặt phẳng → sinh hài bậc cao →
    đúng tiếng "rè rè" khách phản ánh. Uốn mềm bằng tanh cũng không cứu được
    khi tổng vượt ~1.3× full-scale vì phần dải còn lại quá hẹp.

    Ở đây gain được hạ dần trong một cửa sổ TRƯỚC khi đỉnh tới (nhìn trước
    64 mẫu ≈ 1.3ms) rồi thả về từ từ. Dạng sóng giữ nguyên hình, chỉ nhỏ đi —
    tai nghe ra là "nhạc khẽ chùng xuống lúc hát to", không phải méo tiếng.
    """

    WINDOW = 64          # mẫu mỗi bước tính gain (= độ trễ nhìn trước)
    RELEASE_COEF = 0.02  # tốc độ thả gain về 1.0 (~200ms @ 48kHz)

    def __init__(self, ceiling=0.97 * 32767.0):
        self.ceiling = ceiling
        self.gain = 1.0
        self.pending = np.zeros((0, 2), dtype=np.float32)
        self.limited_samples = 0
        self.min_gain = 1.0   # mức hạ sâu nhất — thước đo "tiếng vào quá to"

    def _max_gain_for(self, seg):
        """Gain lớn nhất mà seg còn nằm dưới trần."""
        peak = float(np.max(np.abs(seg))) if seg.shape[0] else 0.0
        return self.ceiling / peak if peak > self.ceiling else 1.0

    def _emit_window(self, seg, target):
        """Áp gain lên seg theo đường dốc tuyến tính từ gain hiện tại → target.

        Cả hai đầu đường dốc đều đã được chặn dưới `_max_gain_for(seg)` nên
        đường dốc đơn điệu này không thể đưa mẫu nào vượt trần.
        """
        ramp = np.linspace(self.gain, target, seg.shape[0],
                           dtype=np.float32).reshape(-1, 1)
        self.gain = target
        if target < 1.0 or ramp[0, 0] < 1.0:
            self.limited_samples += seg.shape[0]
            self.min_gain = min(self.min_gain, float(target), float(ramp[0, 0]))
        return seg * ramp

    def process(self, x):
        if x.shape[0]:
            self.pending = (np.concatenate([self.pending, x], axis=0)
                            if self.pending.shape[0] else x)

        w = self.WINDOW
        out = []
        # Chỉ xuất được cửa sổ k khi đã nhìn thấy cửa sổ k+1
        while self.pending.shape[0] >= 2 * w:
            allowed = self._max_gain_for(self.pending[:w])
            # Cửa sổ đầu tiên không có ai nhìn trước hộ → hạ ngay tại đây.
            # Về sau gain vào cửa sổ luôn ≤ allowed nên nhánh này không đụng.
            self.gain = min(self.gain, allowed)

            target = self._max_gain_for(self.pending[w:2 * w])
            if target >= self.gain:
                # release: thả lên từ từ, nhưng không được vượt trần cửa sổ này
                target = min(self.gain + (target - self.gain) * self.RELEASE_COEF,
                             allowed)

            out.append(self._emit_window(self.pending[:w], target))
            self.pending = self.pending[w:]

        if not out:
            return np.zeros((0, 2), dtype=np.float32)
        return np.concatenate(out, axis=0)

    def flush(self):
        """Xả nốt phần đuôi khi kết thúc thu."""
        if self.pending.shape[0] == 0:
            return np.zeros((0, 2), dtype=np.float32)
        allowed = self._max_gain_for(self.pending)
        self.gain = min(self.gain, allowed)
        tail = self._emit_window(self.pending, self.gain)
        self.pending = np.zeros((0, 2), dtype=np.float32)
        return tail


class StreamResampler:
    """
    Resample tuyến tính giữ liên tục pha qua nhiều lô dữ liệu.

    Bản cũ gọi np.linspace(0, n-1, m) cho từng lô: mỗi lô chỉ trải m mẫu ra
    n-1 khoảng (thay vì n) nên hụt đúng 1 mẫu nguồn mỗi lô → sai cao độ ~0.1%
    và tích luỹ lệch giọng/nhạc. Ở đây vị trí đọc (`pos`) và phần đuôi chưa
    dùng hết (`tail`) được mang sang lô kế → tỉ lệ đúng tuyệt đối, không có
    điểm gãy ở biên lô.
    """

    def __init__(self, ratio):
        # ratio = rate_đích / rate_nguồn; step = số mẫu nguồn cho mỗi mẫu đích
        self.step = 1.0 / ratio
        self.pos = 0.0
        self.tail = np.zeros((0, 2), dtype=np.float32)

    def process(self, src_new):
        if src_new.shape[0] == 0 and self.tail.shape[0] == 0:
            return np.zeros((0, 2), dtype=np.float32)

        src = (np.concatenate([self.tail, src_new], axis=0)
               if self.tail.shape[0] else src_new)
        n_src = src.shape[0]
        if n_src < 2:
            self.tail = src
            return np.zeros((0, 2), dtype=np.float32)

        # Số mẫu đích nội suy được mà không cần dữ liệu tương lai
        n_out = int(np.floor((n_src - 1 - self.pos) / self.step)) + 1
        if n_out <= 0:
            self.tail = src
            return np.zeros((0, 2), dtype=np.float32)

        idx = self.pos + self.step * np.arange(n_out, dtype=np.float64)
        grid = np.arange(n_src, dtype=np.float64)
        left = np.interp(idx, grid, src[:, 0])
        right = np.interp(idx, grid, src[:, 1])

        # Giữ lại tối thiểu 1 mẫu làm mốc nội suy cho lô sau
        next_pos = self.pos + n_out * self.step
        keep_from = min(int(np.floor(next_pos)), n_src - 1)
        self.pos = next_pos - keep_from
        self.tail = src[keep_from:]

        return np.column_stack([left, right]).astype(np.float32)


def _boost_realtime_priority():
    """
    Nâng độ ưu tiên luồng đang chạy (best-effort, chỉ Windows).

    Vòng lặp drain bị trễ → hàng đợi đầy → mất chunk → tiếng lách tách. Trên máy
    hát chạy kèm Studio One + trình duyệt, ưu tiên cao hơn giúp giữ nhịp.
    """
    try:
        import ctypes
        THREAD_PRIORITY_ABOVE_NORMAL = 1
        k32 = ctypes.windll.kernel32
        k32.SetThreadPriority(k32.GetCurrentThread(), THREAD_PRIORITY_ABOVE_NORMAL)
    except Exception:
        pass


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

    # Worker in nhật ký tiếng Việt có dấu. Khi chạy tiến trình riêng, stdout là
    # pipe nên Python lấy mã của hệ thống (cp1252/cp1258) → print ném
    # UnicodeEncodeError và giết cả tiến trình thu ngay ở dòng "Mic đã tắt".
    # (Bản .exe dựng windowed có sys.stdout = None nên print im lặng, không lộ.)
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # Bản đóng gói chạy worker inline trong process GUI (không tách được
    # subprocess vì không có python.exe kèm theo). Rút khoảng chuyển GIL từ 5ms
    # xuống 1ms để callback audio không phải chờ luồng Qt nhả GIL quá lâu —
    # chờ lâu là WASAPI overrun, nghe ra tiếng lách tách/rè. Cố ý không khôi
    # phục giá trị cũ: các phiên thu sau cũng cần độ trễ GIL thấp.
    try:
        sys.setswitchinterval(0.001)
    except Exception:
        pass
    _boost_realtime_priority()

    import pyaudiowpatch as pyaudio

    pa = pyaudio.PyAudio()

    # ── Chọn thiết bị thu nhạc ──────────────────────────────────────
    if req_loopback_idx >= 0:
        # Dùng device do user chỉ định
        try:
            loopback_dev = pa.get_device_info_by_index(req_loopback_idx)
            print(f"INFO: Loopback: [{req_loopback_idx}] {loopback_dev['name'][:30]}", flush=True)
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
        print("INFO: Mic đã tắt", flush=True)
    elif req_mic_idx >= 0:
        try:
            mic_dev = pa.get_device_info_by_index(req_mic_idx)
            print(f"INFO: Mic: [{req_mic_idx}] {mic_dev['name'][:30]}", flush=True)
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
    # đúng nhịp tương đương loopback, tránh lệch pha → giật.
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
        print("INFO: Chỉ thu nhạc", flush=True)

    # FIX 3: queue.Queue thay lock+list.
    # put_nowait() trong ASIO callback KHÔNG bao giờ block → không làm trễ
    # real-time thread của driver → không bị overrun/xif buffer.
    lb_queue = queue.Queue(maxsize=QUEUE_MAXSIZE)
    mc_queue = queue.Queue(maxsize=QUEUE_MAXSIZE)
    overflow_count = [0]
    # Driver báo mất mẫu (paInputOverflow) — trước đây tham số `status` bị bỏ
    # qua hoàn toàn nên không ai biết bản thu đã thủng lỗ chỗ.
    underrun_count = [0]

    def loopback_callback(in_data, frame_count, time_info, status):
        if status:
            underrun_count[0] += 1
        try:
            lb_queue.put_nowait(in_data)
        except queue.Full:
            overflow_count[0] += 1  # Drop thay vì block callback
        return (None, pyaudio.paContinue)

    def mic_callback(in_data, frame_count, time_info, status):
        if status:
            underrun_count[0] += 1
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
    # Mốc để đối chiếu "thu được bao nhiêu so với đáng lẽ phải thu". Khi luồng
    # audio bị đói CPU, driver vứt mẫu TRƯỚC khi tới callback nên drop/overrun
    # vẫn bằng 0 — chỉ tỉ lệ này lộ ra là bản thu đã mất tiếng.
    capture_started_at = time.time()

    # Sleep interval đồng bộ với chunk duration thực tế (~21.3ms @ 1024/48k).
    sleep_interval = CHUNK_SIZE / lb_rate

    # ── Residual buffers (sample-accurate sync) ─────────────────────────
    # Giữ phần dư giữa các iteration → không bao giờ ghi "solo mid-stream"
    # khi lb/mc lệch nhau. Chỉ emit số frame cả hai đều có → mix chuẩn.
    # Shape: (N, 2) float32 stereo ở out_rate (=lb_rate).
    lb_resid = np.zeros((0, 2), dtype=np.float32)
    mc_resid = np.zeros((0, 2), dtype=np.float32)

    # Grace period cho mic "lên trễ" ngay đầu (ASIO init chậm hơn WASAPI).
    # Trong khoảng này: nếu chỉ có lb và chưa có mic nào → buffer lb, chờ.
    # Sau khoảng này: mic được coi là đã ổn định, nếu vẫn không có mc data
    # → coi như mic im lặng (tránh block vô hạn khi mic chết giữa chừng).
    MIC_GRACE_SEC = 1.0
    mic_grace_deadline = time.time() + MIC_GRACE_SEC
    mic_ever_received = False

    # Trần cho phần dư mỗi bên (0.5s). Hai thiết bị chạy hai clock độc lập nên
    # bên nhanh hơn luôn tích luỹ dần; không cắt thì giọng trễ dần so với nhạc
    # và bộ nhớ phình theo thời lượng thu.
    MAX_RESID = int(lb_rate * 0.5)
    drift_dropped = [0]

    def _drain_queue(q):
        chunks = []
        while True:
            try:
                chunks.append(q.get_nowait())
            except queue.Empty:
                break
        return chunks

    def _to_stereo(chunks, channels):
        """int16 interleaved → (N, 2) float32. Cắt phần đuôi lẻ không đủ 1 frame
        (driver có thể trả buffer không tròn frame → reshape sẽ ném lỗi và giết
        cả vòng thu)."""
        arr = np.frombuffer(b"".join(chunks), dtype=np.int16)
        if channels <= 1:
            return np.column_stack([arr, arr]).astype(np.float32)
        usable = (arr.shape[0] // channels) * channels
        if usable != arr.shape[0]:
            arr = arr[:usable]
        return arr.reshape(-1, channels)[:, :2].astype(np.float32)

    def _lb_to_stereo(chunks):
        if not chunks:
            return np.zeros((0, 2), dtype=np.float32)
        return _to_stereo(chunks, lb_channels)

    # Resampler giữ pha liên tục — thay cho np.linspace từng lô (gây trôi cao độ
    # và gãy sóng ở biên mỗi lô khi mic 44.1kHz còn loa 48kHz).
    mic_resampler = (StreamResampler(mic_resample_ratio)
                     if mic_stream and mic_resample_ratio != 1.0 else None)

    def _mc_to_stereo(chunks):
        if not chunks or not mic_stream:
            return np.zeros((0, 2), dtype=np.float32)
        mc = _to_stereo(chunks, actual_mic_channels)
        if mic_resampler is not None and mc.shape[0] > 0:
            mc = mic_resampler.process(mc)
        return mc

    # Chỉ hạ gain khi thực sự trộn 2 nguồn. Thu loopback đơn thuần không có nguy
    # cơ cộng dồn quá đỉnh nên giữ nguyên mức, tránh làm bản thu nhỏ đi vô cớ.
    lb_gain = MIX_LB_GAIN if mic_stream else 1.0
    mic_gain = MIX_MIC_GAIN
    # Chỉ trộn 2 nguồn mới có nguy cơ vượt đỉnh. Thu loopback đơn thuần đi
    # thẳng, giữ nguyên mức và không thêm độ trễ nhìn trước.
    limiter = PeakLimiter() if mic_stream else None

    def _emit(samples):
        nonlocal frames_written
        if samples.shape[0] == 0:
            return
        mixed = np.clip(samples, -32768.0, 32767.0).astype(np.int16)
        wf.writeframes(mixed.tobytes())
        frames_written += mixed.shape[0]

    def _write_mix(lb_seg, mc_seg):
        """Mix sample-accurate 2 segment cùng độ dài → WAV."""
        if lb_seg.shape[0] == 0 and mc_seg.shape[0] == 0:
            return
        if lb_seg.shape[0] == 0:
            acc = mc_seg * mic_gain
        elif mc_seg.shape[0] == 0:
            acc = lb_seg * lb_gain
        else:
            acc = lb_seg * lb_gain + mc_seg * mic_gain
        _emit(limiter.process(acc) if limiter else acc)

    try:
        while os.path.exists(stop_flag):
            time.sleep(sleep_interval)

            lb_new = _lb_to_stereo(_drain_queue(lb_queue))
            mc_new = _mc_to_stereo(_drain_queue(mc_queue)) if mic_stream else np.zeros((0, 2), dtype=np.float32)

            if lb_new.shape[0]:
                lb_resid = np.concatenate([lb_resid, lb_new], axis=0) if lb_resid.shape[0] else lb_new
            if mc_new.shape[0]:
                mc_resid = np.concatenate([mc_resid, mc_new], axis=0) if mc_resid.shape[0] else mc_new
                mic_ever_received = True

            if not mic_stream:
                # Chế độ loopback-only: ghi thẳng, không cần sync.
                if lb_resid.shape[0]:
                    _write_mix(lb_resid, np.zeros((0, 2), dtype=np.float32))
                    lb_resid = np.zeros((0, 2), dtype=np.float32)
                continue

            # Grace period: chờ mic lên trước khi phát lb đơn độc.
            in_grace = (not mic_ever_received) and (time.time() < mic_grace_deadline)
            if in_grace:
                continue

            # Sau grace: nếu mic vẫn chưa có dữ liệu NÀO suốt 1s → coi mic silent,
            # fill zeros cho mc_resid bằng độ dài lb_resid để không kẹt.
            if not mic_ever_received and lb_resid.shape[0] > 0:
                mc_resid = np.zeros((lb_resid.shape[0], 2), dtype=np.float32)

            # Emit sample-accurate: min(len_lb, len_mc) frames đã mix chuẩn.
            n = min(lb_resid.shape[0], mc_resid.shape[0])
            if n == 0:
                if lb_resid.shape[0] > MAX_RESID:
                    # Mic đã chết giữa chừng → xả lb kèm silence để không drift.
                    pad = np.zeros((lb_resid.shape[0], 2), dtype=np.float32)
                    _write_mix(lb_resid, pad)
                    lb_resid = np.zeros((0, 2), dtype=np.float32)
                if mc_resid.shape[0] > MAX_RESID:
                    pad = np.zeros((mc_resid.shape[0], 2), dtype=np.float32)
                    _write_mix(pad, mc_resid)
                    mc_resid = np.zeros((0, 2), dtype=np.float32)
                continue

            _write_mix(lb_resid[:n], mc_resid[:n])
            lb_resid = lb_resid[n:]
            mc_resid = mc_resid[n:]

            # Bên nào vượt trần thì bỏ phần cũ nhất. Bản cũ chỉ chốt trần trong
            # nhánh n == 0 nên khi cả hai luồng đều có tiếng thì không bao giờ
            # chạy tới. Với sai lệch clock thường gặp (~50ppm) một lần cắt xảy
            # ra sau hàng giờ thu, không nghe thấy.
            if lb_resid.shape[0] > MAX_RESID:
                drift_dropped[0] += lb_resid.shape[0] - MAX_RESID
                lb_resid = lb_resid[-MAX_RESID:]
            if mc_resid.shape[0] > MAX_RESID:
                drift_dropped[0] += mc_resid.shape[0] - MAX_RESID
                mc_resid = mc_resid[-MAX_RESID:]

    except KeyboardInterrupt:
        pass

    # ── Flush cuối: xả phần dư còn lại (mix nếu có thể, else silence-pad) ──
    try:
        # Drain lần cuối
        lb_last = _lb_to_stereo(_drain_queue(lb_queue))
        mc_last = _mc_to_stereo(_drain_queue(mc_queue)) if mic_stream else np.zeros((0, 2), dtype=np.float32)
        if lb_last.shape[0]:
            lb_resid = np.concatenate([lb_resid, lb_last], axis=0) if lb_resid.shape[0] else lb_last
        if mc_last.shape[0]:
            mc_resid = np.concatenate([mc_resid, mc_last], axis=0) if mc_resid.shape[0] else mc_last

        n = min(lb_resid.shape[0], mc_resid.shape[0])
        if n > 0:
            _write_mix(lb_resid[:n], mc_resid[:n])
            lb_resid = lb_resid[n:]
            mc_resid = mc_resid[n:]
        # Phần còn dư: pad silence để giữ đúng thời lượng.
        if lb_resid.shape[0] > 0:
            _write_mix(lb_resid, np.zeros((lb_resid.shape[0], 2), dtype=np.float32))
        if mc_resid.shape[0] > 0:
            _write_mix(np.zeros((mc_resid.shape[0], 2), dtype=np.float32), mc_resid)
        # Xả nốt cửa sổ nhìn trước còn kẹt trong limiter
        if limiter:
            _emit(limiter.flush())
    except Exception as e:
        print(f"WARNING: Flush cuối lỗi: {e}", flush=True)

    # ── Cleanup ─────────────────────────────────────────────────────
    if overflow_count[0] > 0:
        print(
            f"WARNING: {overflow_count[0]} audio chunks dropped (queue overflow — "
            f"CPU quá tải hoặc write WAV quá chậm)",
            flush=True
        )

    # Dòng máy đọc được cho tiến trình cha: nhờ nó mà lần sau khách báo "thu bị
    # rè" là biết ngay do máy đói CPU (drop/overrun) hay do trộn quá đỉnh (limit).
    limited = limiter.limited_samples if limiter else 0
    limit_ratio = (limited / frames_written) if frames_written else 0.0
    gain_min = limiter.min_gain if limiter else 1.0
    elapsed = time.time() - capture_started_at
    # Phiên quá ngắn thì phần khởi động stream chiếm tỉ trọng lớn, tỉ lệ này
    # nhiễu và dễ báo oan → chỉ tính khi đã thu đủ lâu.
    capture_ratio = 1.0
    if elapsed >= 3.0:
        capture_ratio = min(1.0, frames_written / (elapsed * out_rate))
    print(
        f"STATS: drop={overflow_count[0]} overrun={underrun_count[0]} "
        f"drift={drift_dropped[0]} limit={limit_ratio:.4f} gainmin={gain_min:.3f} "
        f"capture={capture_ratio:.3f}",
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
    print(f"DONE: Đã ghi {duration:.1f}s", flush=True)


if __name__ == "__main__":
    main()
