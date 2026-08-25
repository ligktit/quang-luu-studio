"""
Quang Lưu Studio — Bàn thử thu âm (mini tool)

Chạy đúng bộ máy thu của app (core/recorder.py + recorder_worker.py) mà không
phải mở toàn bộ giao diện, rồi tự chấm file WAV thu được để chỉ ra bản thu có
bị rè hay không và rè vì lý do gì.

Cách dùng:
    python tools/rec_test.py devices
    python tools/rec_test.py rec --sec 10
    python tools/rec_test.py rec --lb 12 --mic 3 --sec 15 --load 4
    python tools/rec_test.py rec --tone --mic off --sec 5
    python tools/rec_test.py compare --sec 10 --load 4
    python tools/rec_test.py analyze "D:\\ban_thu_cua_khach.wav"

Ghi chú về --mode:
    subprocess  Worker chạy tiến trình riêng — giống bản chạy từ mã nguồn.
    inline      Worker chạy trong luồng của chính process này — giống bản
                đóng gói (.exe) mà khách đang dùng. Đây là chế độ dễ lộ lỗi
                mất mẫu nhất, nhất là khi kèm --load.
"""
import argparse
import math
import os
import sys
import tempfile
import threading
import time
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Console Windows mặc định không phải UTF-8 → tiếng Việt có dấu làm vỡ print
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from core.recorder import AudioRecorder          # noqa: E402
from recorder_worker import enumerate_all_devices  # noqa: E402

FULL = 32768.0
MIC_OFF = -2      # quy ước của recorder_worker: -2 = tắt mic, -1 = tự chọn


# ── Tiện ích ─────────────────────────────────────────────────────────────────

def _db(x):
    return -math.inf if x <= 0 else 20 * math.log10(x / FULL)


def _fmt_db(x):
    v = _db(x)
    return "-inf" if v == -math.inf else f"{v:+.1f} dBFS"


def _open_pyaudio():
    try:
        import pyaudiowpatch as pyaudio
    except ImportError:
        print("❌ Thiếu pyaudiowpatch. Chạy: pip install pyaudiowpatch")
        sys.exit(1)
    return pyaudio


class GilLoad:
    """
    Giả lập máy yếu: các luồng Python giữ GIL liên tục.

    Đây là thứ tái hiện được lỗi khách gặp mà máy dev không gặp — bản .exe chạy
    worker chung process với giao diện, nên giao diện giữ GIL là callback audio
    bị trễ và mất mẫu.
    """

    def __init__(self, n_threads):
        self.n = n_threads
        self._running = False
        self._threads = []

    def _burn(self):
        while self._running:
            sum(i * i for i in range(20000))   # thuần Python → giữ GIL

    def __enter__(self):
        if self.n <= 0:
            return self
        self._running = True
        for _ in range(self.n):
            t = threading.Thread(target=self._burn, daemon=True)
            t.start()
            self._threads.append(t)
        print(f"⚙️  Đang ép tải {self.n} luồng để giả lập máy yếu")
        return self

    def __exit__(self, *exc):
        self._running = False
        for t in self._threads:
            t.join(timeout=1.0)


class TonePlayer:
    """Phát sine ra loa mặc định để có nguồn nhạc chuẩn cho loopback thu lại."""

    def __init__(self, freq=440.0, amplitude=0.5, rate=48000):
        self.freq = freq
        self.amp = amplitude
        self.rate = rate
        self._phase = 0
        self._stream = None
        self._pa = None

    def __enter__(self):
        pyaudio = _open_pyaudio()
        self._pa = pyaudio.PyAudio()

        def callback(in_data, frame_count, time_info, status):
            n = self._phase + np.arange(frame_count)
            self._phase += frame_count
            mono = np.sin(2 * np.pi * self.freq * n / self.rate) * self.amp * 32767
            frames = np.repeat(mono[:, None], 2, axis=1).astype(np.int16)
            return (frames.tobytes(), pyaudio.paContinue)

        self._stream = self._pa.open(
            format=pyaudio.paInt16, channels=2, rate=self.rate,
            output=True, frames_per_buffer=1024, stream_callback=callback,
        )
        self._stream.start_stream()
        print(f"🔊 Đang phát sine {self.freq:.0f}Hz ở {self.amp * 100:.0f}% mức")
        return self

    def __exit__(self, *exc):
        for close in (self._stream.stop_stream, self._stream.close, self._pa.terminate):
            try:
                close()
            except Exception:
                pass


# ── Lệnh: devices ────────────────────────────────────────────────────────────

def cmd_devices(args):
    pyaudio = _open_pyaudio()
    pa = pyaudio.PyAudio()
    try:
        devices = enumerate_all_devices(pa)
    finally:
        pa.terminate()

    print(f"\n{'Idx':<5}{'Tên thiết bị':<44}{'Host API':<20}{'In':>3}{'Rate':>8}  Ghi chú")
    print("-" * 92)
    for d in devices:
        note = "🔁 LOOPBACK (nguồn nhạc)" if d["is_loopback"] else (
            "🎤 mic được" if d["in_ch"] > 0 else "")
        print(f"{d['index']:<5}{d['name'][:42]:<44}{d['host_api'][:18]:<20}"
              f"{d['in_ch']:>3}{d['rate']:>8}  {note}")
    print("\nDùng số ở cột Idx cho --lb (nguồn nhạc) và --mic (giọng).")


# ── Lệnh: rec ────────────────────────────────────────────────────────────────

def _run_recording(out_path, lb_idx, mic_idx, seconds, inline):
    """
    Thu một lượt bằng đúng AudioRecorder của app.

    inline=True giả lập bản đóng gói: bật cờ sys.frozen và trỏ _MEIPASS về thư
    mục dự án để AudioRecorder đi vào nhánh chạy worker trong luồng nội bộ.
    """
    tmp_dir = tempfile.mkdtemp(prefix="qls_rec_")
    frozen_before = getattr(sys, "frozen", None)
    meipass_before = getattr(sys, "_MEIPASS", None)

    if inline:
        sys.frozen = True
        sys._MEIPASS = ROOT

    recorder = AudioRecorder()
    try:
        started = recorder.start_recording(
            output_dir=tmp_dir,
            loopback_device_index=lb_idx,
            mic_device_index=mic_idx,
        )
        if not started:
            print(f"❌ Không khởi động được: {recorder.last_error}")
            return None

        print(f"⏺️  Đang thu {seconds}s… (Ctrl+C để dừng sớm)")
        try:
            for remaining in range(seconds, 0, -1):
                print(f"\r   còn {remaining:3d}s", end="", flush=True)
                time.sleep(1.0)
        except KeyboardInterrupt:
            print("\n   dừng sớm theo yêu cầu")
        print()

        if recorder.stop_recording(save_path=out_path) is not True:
            print(f"❌ Lưu thất bại: {recorder.last_error}")
            return None
    finally:
        if inline:
            if frozen_before is None:
                del sys.frozen
            else:
                sys.frozen = frozen_before
            if meipass_before is None:
                if hasattr(sys, "_MEIPASS"):
                    del sys._MEIPASS
            else:
                sys._MEIPASS = meipass_before

    return {
        "stats": recorder._stats_line,
        "warning": recorder.quality_warning(),
    }


def _do_rec(out_path, args, inline):
    mic_idx = MIC_OFF if str(args.mic).lower() in ("off", "tat", "tắt") else int(args.mic)
    tone = TonePlayer(freq=args.tone_freq, amplitude=args.tone_level) if args.tone else None

    ctx_tone = tone if tone else _NullCtx()
    with ctx_tone, GilLoad(args.load):
        if not args.tone:
            print("▶️  Hãy phát nhạc karaoke lên loa trước, rồi để yên trong lúc thu.")
            time.sleep(1.0)
        result = _run_recording(out_path, int(args.lb), mic_idx, args.sec, inline)

    if result is None:
        return None
    if result["stats"]:
        print(f"📈 {result['stats']}")
    if result["warning"]:
        print(f"⚠️  App sẽ báo cho khách: {result['warning']}")
    return result


class _NullCtx:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def cmd_rec(args):
    out_path = args.out or os.path.join(
        ROOT, "temp_audio", f"rec_test_{time.strftime('%H%M%S')}.wav")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    inline = args.mode == "inline"
    print(f"\n🎚️  Chế độ {args.mode} "
          f"({'giống bản .exe của khách' if inline else 'giống bản chạy từ mã nguồn'})")

    if _do_rec(out_path, args, inline) is None:
        return 1

    print(f"💾 {out_path}")
    print_report(analyze_wav(out_path), expected_sec=args.sec)
    return 0


# ── Lệnh: compare ────────────────────────────────────────────────────────────

def cmd_compare(args):
    """Thu hai lượt cùng điều kiện, một inline một subprocess, rồi so kết quả."""
    os.makedirs(os.path.join(ROOT, "temp_audio"), exist_ok=True)
    rows = []

    for mode in ("subprocess", "inline"):
        out_path = os.path.join(
            ROOT, "temp_audio", f"rec_test_{mode}_{time.strftime('%H%M%S')}.wav")
        print(f"\n{'=' * 70}\n🎚️  Lượt {mode}\n{'=' * 70}")
        result = _do_rec(out_path, args, inline=(mode == "inline"))
        if result is None:
            return 1
        report = analyze_wav(out_path)
        print_report(report, expected_sec=args.sec)
        rows.append((mode, report, result))
        time.sleep(1.0)

    print(f"\n{'=' * 70}\n📊 SO SÁNH\n{'=' * 70}")
    print(f"{'Chế độ':<14}{'Bắt được':>12}{'Đỉnh':>12}{'Chạm trần':>12}"
          f"{'Gợn/phút':>12}{'Trống':>8}")
    for mode, report, _ in rows:
        # "Bắt được" so với số giây đã yêu cầu: thiếu là mất tiếng
        print(f"{mode:<14}{report['duration']:>10.1f}s{_fmt_db(report['peak']):>12}"
              f"{report['clipped']:>12}{report['clicks_per_min']:>12.1f}"
              f"{report['gaps']:>8}")
    print(f"{'yêu cầu':<14}{args.sec:>10.1f}s")
    for mode, _, result in rows:
        if result["stats"]:
            print(f"  {mode:<12} {result['stats']}")

    # Thước đo đáng tin nhất là số giây bắt được: khi driver vứt mẫu vì đói CPU
    # thì bộ đếm drop/overrun vẫn bằng 0 nhưng thời lượng hụt thấy rõ.
    worse = (rows[1][1]["duration"] < rows[0][1]["duration"] * 0.9
             or rows[1][1]["clicks_per_min"] > rows[0][1]["clicks_per_min"] * 2 + 1)
    print("\n👉 " + (
        "Chế độ inline thu kém hơn hẳn — đúng giả thuyết worker chạy chung "
        "process với giao diện thì bị đói CPU. Đáng tách worker ra tiến trình "
        "riêng cho bản đóng gói."
        if worse else
        "Hai chế độ tương đương — lỗi của khách nhiều khả năng không nằm ở việc "
        "worker chạy chung process."))
    return 0


# ── Lệnh: analyze ────────────────────────────────────────────────────────────

def analyze_wav(path):
    with wave.open(path, "rb") as wf:
        channels = wf.getnchannels()
        rate = wf.getframerate()
        width = wf.getsampwidth()
        frames = wf.getnframes()
        raw = wf.readframes(frames)

    if width != 2:
        raise ValueError(f"Chỉ đọc được WAV 16-bit, file này {width * 8}-bit")

    audio = np.frombuffer(raw, dtype=np.int16).reshape(-1, channels).astype(np.float64)
    mono = audio.mean(axis=1)
    duration = audio.shape[0] / rate if rate else 0.0

    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    rms = float(np.sqrt(np.mean(audio ** 2))) if audio.size else 0.0

    # Cắt cứng: mẫu nằm sát trần. Ba mẫu liền nhau trở lên là một mặt phẳng thật
    # sự, không phải đỉnh sóng tình cờ chạm mức.
    at_ceiling = np.abs(audio) >= 32700
    clipped = int(np.count_nonzero(at_ceiling))
    plateaus, longest = _count_runs(at_ceiling.any(axis=1), min_len=3)

    clicks = _count_clicks(mono, peak)
    clicks_per_min = clicks / (duration / 60) if duration > 0 else 0.0

    # Khoảng trống: im lặng tuyệt đối ≥ 5ms giữa bản thu → mất dữ liệu
    silent = np.all(audio == 0, axis=1)
    gaps, longest_gap = _count_runs(silent, min_len=max(1, int(rate * 0.005)))

    dc = [float(np.mean(audio[:, c])) for c in range(channels)]

    return {
        "path": path, "rate": rate, "channels": channels, "duration": duration,
        "peak": peak, "rms": rms, "clipped": clipped, "plateaus": plateaus,
        "longest_plateau": longest, "clicks": clicks, "clicks_per_min": clicks_per_min,
        "gaps": gaps, "longest_gap_ms": longest_gap * 1000.0 / rate if rate else 0.0,
        "dc": dc,
    }


def _count_clicks(mono, peak, block=256, ratio=6.0):
    """
    Đếm chỗ nối gãy (nghe ra tiếng lách tách) trong bản thu.

    So bước nhảy giữa 2 mẫu kề nhau với bước nhảy lớn nhất của các đoạn 5ms
    liền kề. Nhạc sáng và to có bước nhảy lớn nhưng đều đặn nên không bị đếm
    oan; chỗ nối do mất mẫu thì vọt hẳn lên so với hàng xóm.

    Ngưỡng tuyệt đối theo mức đỉnh giúp bỏ qua bản thu gần như im lặng — ở đó
    mọi thước đo tương đối đều nhiễu.
    """
    if mono.size <= block * 3 or peak <= 0:
        return 0

    d = np.abs(np.diff(mono))
    n_blocks = d.size // block
    if n_blocks < 3:
        return 0

    grid = d[:n_blocks * block].reshape(n_blocks, block)
    block_max = grid.max(axis=1)
    prev = np.concatenate([block_max[:1], block_max[:-1]])
    nxt = np.concatenate([block_max[1:], block_max[-1:]])
    # Mốc so sánh là hàng xóm hai bên, không tính chính đoạn đang xét
    reference = np.maximum(prev, nxt).reshape(-1, 1)

    floor = 0.05 * peak      # dưới mức này thì chỉ là nhiễu nền
    return int(np.count_nonzero((grid > ratio * reference) & (grid > floor)))


def _count_runs(mask, min_len):
    """Đếm số đoạn liên tiếp True dài ≥ min_len, và độ dài đoạn dài nhất."""
    if not mask.any():
        return 0, 0
    padded = np.concatenate([[False], mask, [False]])
    edges = np.diff(padded.astype(np.int8))
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1)
    lengths = ends - starts
    return int(np.count_nonzero(lengths >= min_len)), int(lengths.max())


def print_report(r, expected_sec=None):
    print(f"\n{'─' * 70}")
    print(f"📄 {os.path.basename(r['path'])}")
    print(f"   {r['duration']:.1f}s · {r['rate']}Hz · {r['channels']} kênh")
    print(f"   Đỉnh {_fmt_db(r['peak'])}   Trung bình {_fmt_db(r['rms'])}")
    print(f"   Mẫu chạm trần: {r['clipped']} "
          f"(mặt phẳng ≥3 mẫu: {r['plateaus']}, dài nhất {r['longest_plateau']} mẫu)")
    print(f"   Điểm gợn: {r['clicks']} ({r['clicks_per_min']:.1f}/phút)")
    print(f"   Khoảng trống: {r['gaps']} (dài nhất {r['longest_gap_ms']:.1f}ms)")
    print(f"   Lệch DC: {', '.join(f'{v:+.0f}' for v in r['dc'])} LSB")

    verdicts = []
    if expected_sec and r["duration"] < expected_sec * 0.95:
        verdicts.append(
            f"⛔ MẤT TIẾNG: chỉ bắt được {r['duration']:.1f}s trên {expected_sec}s yêu "
            f"cầu. Driver đã vứt mẫu vì luồng audio bị đói CPU — đây là dạng mất "
            f"dữ liệu mà bộ đếm drop/overrun không thấy được.")
    if r["duration"] <= 0.05:
        verdicts.append("⛔ File gần như rỗng — không bắt được tiếng từ thiết bị đã chọn.")
    if r["plateaus"] > 0:
        verdicts.append(
            f"⛔ MÉO DO QUÁ ĐỈNH: {r['plateaus']} đoạn bị cắt phẳng. Đây là tiếng rè "
            f"kinh điển — giảm âm lượng nhạc hoặc mic.")
    if r["gaps"] > 0:
        verdicts.append(
            f"⛔ MẤT DỮ LIỆU: {r['gaps']} khoảng im tuyệt đối. Máy không kịp phục vụ "
            f"luồng audio (đói CPU hoặc ghi đĩa chậm).")
    if r["clicks_per_min"] > 60:
        verdicts.append(
            f"⚠️  NHIỀU ĐIỂM GỢN ({r['clicks_per_min']:.0f}/phút): nghe ra tiếng lách "
            f"tách. Thường do mất mẫu, thử lại với --load 0 để đối chiếu.")
    if max(abs(v) for v in r["dc"]) > 300:
        verdicts.append("⚠️  Lệch DC lớn — thiết bị/driver thu có vấn đề, không phải app.")
    if _db(r["peak"]) < -30:
        verdicts.append("⚠️  Mức thu rất nhỏ — kiểm tra đã chọn đúng thiết bị nguồn nhạc chưa.")

    print()
    for v in verdicts or ["✅ Không thấy dấu hiệu rè: không cắt đỉnh, không mất dữ liệu."]:
        print(f"   {v}")
    print("─" * 70)


def cmd_analyze(args):
    if not os.path.exists(args.file):
        print(f"❌ Không thấy file: {args.file}")
        return 1
    print_report(analyze_wav(args.file))
    return 0


# ── CLI ──────────────────────────────────────────────────────────────────────

def _add_rec_options(p):
    p.add_argument("--lb", default=-1,
                   help="Idx thiết bị nguồn nhạc (-1 = tự tìm loopback)")
    p.add_argument("--mic", default="off",
                   help="Idx microphone, 'off' để tắt, -1 để lấy mic mặc định")
    p.add_argument("--sec", type=int, default=10, help="Số giây thu (mặc định 10)")
    p.add_argument("--load", type=int, default=0,
                   help="Số luồng ép tải để giả lập máy yếu (mặc định 0)")
    p.add_argument("--tone", action="store_true",
                   help="Tự phát sine ra loa thay vì phải mở nhạc")
    p.add_argument("--tone-freq", type=float, default=440.0)
    p.add_argument("--tone-level", type=float, default=0.35,
                   help="Mức sine phát ra, 0..1 (0 = im, chỉ để thử luồng)")


def main():
    parser = argparse.ArgumentParser(
        prog="rec_test",
        description="Bàn thử thu âm của Quang Lưu Studio",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("devices", help="Liệt kê thiết bị âm thanh")

    p_rec = sub.add_parser("rec", help="Thu một lượt rồi chấm chất lượng")
    _add_rec_options(p_rec)
    p_rec.add_argument("--mode", choices=["subprocess", "inline"], default="subprocess",
                       help="inline = giống bản .exe của khách")
    p_rec.add_argument("--out", help="Nơi lưu file WAV")

    p_cmp = sub.add_parser("compare", help="Thu 2 lượt inline vs subprocess rồi so")
    _add_rec_options(p_cmp)

    p_ana = sub.add_parser("analyze", help="Chấm một file WAV có sẵn")
    p_ana.add_argument("file")

    args = parser.parse_args()
    return {
        "devices": cmd_devices,
        "rec": cmd_rec,
        "compare": cmd_compare,
        "analyze": cmd_analyze,
    }[args.command](args)


if __name__ == "__main__":
    sys.exit(main() or 0)
