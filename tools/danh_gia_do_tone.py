"""
Chấm điểm thuật toán dò tone — thước đo trước mọi thay đổi thuật toán.

Xem docs/NGHIEN_CUU_DO_TONE.md (Giai đoạn 0). Hai lệnh:

  tong-hop   Âm thanh tổng hợp có tone biết trước (6 vòng hợp âm × 12 tone, có
             trống/nhiễu, lệch tuning). Không cần mạng — dùng làm test hồi quy.

  chay FILE  Chấm trên bộ đáp án thật. FILE là một trong:
             - JSON tải từ admin server: /admin/library/export
             - data/manual_timelines.json trên máy (tone đã sửa tay)
             - JSON tự soạn: [{"url" hoặc "path": ..., "key": "Am"}, ...]
                              (hoặc "timeline": [{"time", "key_display"}, ...])

  --che-do nhanh     giống "Dò tone" nhanh của app: 45s đầu, sr=16000; kém tự
                     tin thì tự dò thêm 120s (ToneDetector.detect_key_from_file)
  --che-do toan-bai  giống "Dò toàn bài": cả bài, sr=22050, chuỗi tone

Ba con số chính:
  Đúng tuyệt đối — đúng cả chủ âm lẫn trưởng/thứ.
  Điểm MIREX     — chuẩn học thuật (mir_eval.key): đúng 1, quãng 5 0.5,
                   giọng song song (C↔Am) 0.3, cùng tên (C↔Cm) 0.2.
                   Ở đây tính quãng 5 cả hai chiều (allow_descending_fifths).
  Đúng tập nốt   — đúng tuyệt đối HOẶC giọng song song: Auto-Tune kéo giọng về
                   cùng 7 nốt nên với người hát hai kết quả này như nhau.

Ví dụ:
  .venv\\Scripts\\python.exe tools\\danh_gia_do_tone.py tong-hop
  .venv\\Scripts\\python.exe tools\\danh_gia_do_tone.py chay dap_an_tone.json --bao-cao kq.csv
"""
import argparse
import contextlib
import csv
import io
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

NOTES_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NOTES_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

DUNG, QUANG5, SONG_SONG, CUNG_TEN, KHAC, KHONG_RA = (
    "dung", "quang5", "song_song", "cung_ten", "khac", "khong_ra")
DIEM_MIREX = {DUNG: 1.0, QUANG5: 0.5, SONG_SONG: 0.3, CUNG_TEN: 0.2, KHAC: 0.0, KHONG_RA: 0.0}
TEN_LOI = {
    QUANG5: "nhầm quãng 5", SONG_SONG: "nhầm giọng song song (C↔Am)",
    CUNG_TEN: "nhầm cùng tên (C↔Cm)", KHAC: "sai hẳn", KHONG_RA: "không ra kết quả",
}

FAST_SECONDS = 45      # khớp _tone.py: librosa.load(..., sr=16000, duration=45)
FAST_SR = 16000
FULL_SR = 22050


# ─────────────────────────────────────────────────────────────────────────────
# Phần thuần (không cần librosa) — có test ở tests/tools/test_danh_gia_do_tone.py
# ─────────────────────────────────────────────────────────────────────────────

def parse_key(value):
    """'C#m' / 'Bb' / 'A Minor' / {key_display, key_index, scale} → (index, scale).

    Trả None nếu không đọc được. Với dict, ưu tiên key_display (thứ người dùng
    nhìn thấy và sửa) rồi mới tới key_index + scale.
    """
    if isinstance(value, dict):
        parsed = parse_key(value.get("key_display"))
        if parsed:
            return parsed
        try:
            idx = int(value.get("key_index"))
            scale = str(value.get("scale", "Major")).capitalize()
            if 0 <= idx <= 11 and scale in ("Major", "Minor"):
                return idx, scale
        except (TypeError, ValueError):
            pass
        return None
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    words = s.split()
    if len(words) == 2 and words[1].lower() in ("major", "minor", "maj", "min", "trưởng", "thứ"):
        root, scale = words[0], ("Minor" if words[1].lower() in ("minor", "min", "thứ") else "Major")
    elif len(words) == 1 and s.endswith("m") and len(s) > 1:
        root, scale = s[:-1], "Minor"
    elif len(words) == 1:
        root, scale = s, "Major"
    else:
        return None
    root = root[0].upper() + root[1:]
    if root in NOTES_SHARP:
        return NOTES_SHARP.index(root), scale
    if root in NOTES_FLAT:
        return NOTES_FLAT.index(root), scale
    return None


def key_name(key):
    if not key:
        return "—"
    idx, scale = key
    return NOTES_SHARP[idx] + ("m" if scale == "Minor" else "")


def classify(truth, pred):
    """Xếp loại kết quả dò so với đáp án (cả hai là (index, scale))."""
    if pred is None:
        return KHONG_RA
    (ti, ts), (pi, ps) = truth, pred
    if ti == pi and ts == ps:
        return DUNG
    if ts == ps and (pi - ti) % 12 in (5, 7):
        return QUANG5
    if ts != ps:
        # song song: C trưởng ↔ La thứ — chủ âm thứ = chủ âm trưởng + 9
        major, minor = (ti, pi) if ts == "Major" else (pi, ti)
        if (major + 9) % 12 == minor:
            return SONG_SONG
        if ti == pi:
            return CUNG_TEN
    return KHAC


def same_pitch_set(cls):
    return cls in (DUNG, SONG_SONG)


def normalize_timeline(entries):
    """[{time, key_display...}] → [(time, key)] đã sắp xếp, bỏ mốc không đọc được."""
    out = []
    for e in entries or []:
        if not isinstance(e, dict):
            continue
        key = parse_key(e)
        if key is None:
            continue
        try:
            t = float(e.get("time", 0) or 0)
        except (TypeError, ValueError):
            continue
        out.append((max(0.0, t), key))
    out.sort(key=lambda x: x[0])
    return out


def key_at(timeline, t):
    """Tone đang hiệu lực tại thời điểm t (mốc đầu tiên phủ cả đoạn trước nó)."""
    if not timeline:
        return None
    current = timeline[0][1]
    for start, key in timeline:
        if start <= t:
            current = key
        else:
            break
    return current


def dominant_key(timeline, start, end):
    """Tone chiếm nhiều thời gian nhất trong [start, end]."""
    if not timeline or end <= start:
        return key_at(timeline, start)
    bounds = sorted({start, end} | {t for t, _ in timeline if start < t < end})
    total = {}
    for a, b in zip(bounds, bounds[1:]):
        k = key_at(timeline, (a + b) / 2)
        total[k] = total.get(k, 0.0) + (b - a)
    return max(total.items(), key=lambda kv: kv[1])[0]


def timeline_agreement(truth, pred, duration, step=0.5):
    """Tỉ lệ thời lượng bài mà tone dò khớp đáp án: (đúng tuyệt đối, đúng tập nốt)."""
    if not truth or not pred or duration <= 0:
        return 0.0, 0.0
    n = max(1, int(duration / step))
    exact = pitch = 0
    for i in range(n):
        t = (i + 0.5) * step
        cls = classify(key_at(truth, t), key_at(pred, t))
        exact += cls == DUNG
        pitch += same_pitch_set(cls)
    return exact / n, pitch / n


def count_changes(timeline):
    return sum(1 for (_, a), (_, b) in zip(timeline, timeline[1:]) if a != b)


def load_dataset(path):
    """Đọc bộ đáp án → [{id, title, source (url|path), timeline}]."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    raw = []
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        # file xuất từ /admin/library/export
        for it in data["items"]:
            raw.append({"id": it.get("song_key"), "title": it.get("title", ""),
                        "url": f"https://www.youtube.com/watch?v={it.get('song_key')}",
                        "timeline": it.get("timeline")})
    elif isinstance(data, dict):
        # manual_timelines.json: {song_key: {title, url, timeline, source}}
        for song_key, it in data.items():
            if not isinstance(it, dict):
                continue
            if (it.get("source") or "human") != "human":
                continue
            raw.append({"id": song_key, "title": it.get("title", ""),
                        "url": it.get("url") or song_key, "timeline": it.get("timeline")})
    elif isinstance(data, list):
        for i, it in enumerate(data):
            if not isinstance(it, dict):
                continue
            tl = it.get("timeline") or ([{"time": 0, "key_display": it["key"]}] if it.get("key") else None)
            raw.append({"id": it.get("id") or it.get("url") or it.get("path") or str(i),
                        "title": it.get("title", ""), "url": it.get("url"),
                        "path": it.get("path"), "timeline": tl})

    items = []
    for it in raw:
        tl = normalize_timeline(it.get("timeline"))
        if not tl or not (it.get("url") or it.get("path")):
            continue
        it["timeline"] = tl
        items.append(it)
    return items


def summarize(rows, title):
    """In bảng tổng kết. rows: dict có 'cls', 'confidence', 'tuning_cents' (tuỳ chọn)."""
    n = len(rows)
    if not n:
        print(f"\n== {title}: không có bài nào để chấm")
        return {}
    counts = {}
    for r in rows:
        counts[r["cls"]] = counts.get(r["cls"], 0) + 1
    exact = counts.get(DUNG, 0)
    pitch = sum(1 for r in rows if same_pitch_set(r["cls"]))
    mirex = sum(DIEM_MIREX[r["cls"]] for r in rows) / n

    print(f"\n== {title} — {n} bài")
    print(f"   Đúng tuyệt đối : {exact}/{n} = {100 * exact / n:.1f}%")
    print(f"   Điểm MIREX     : {100 * mirex:.1f}")
    print(f"   Đúng tập nốt   : {pitch}/{n} = {100 * pitch / n:.1f}%   (Auto-Tune không phân biệt)")
    for cls in (QUANG5, SONG_SONG, CUNG_TEN, KHAC, KHONG_RA):
        if counts.get(cls):
            print(f"     - {TEN_LOI[cls]}: {counts[cls]}")

    # Độ tin cậy có nói thật không: chia theo mức confidence, xem tỉ lệ đúng.
    with_conf = [r for r in rows if isinstance(r.get("confidence"), (int, float))]
    if with_conf:
        print("   Độ tin cậy ↔ tỉ lệ đúng tuyệt đối:")
        edges = [(-1, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 2)]
        for lo, hi in edges:
            grp = [r for r in with_conf if lo <= r["confidence"] < hi]
            if grp:
                ok = sum(r["cls"] == DUNG for r in grp)
                label = f"<{hi:.1f}" if lo < 0 else (f"≥{lo:.1f}" if hi > 1 else f"{lo:.1f}–{hi:.1f}")
                print(f"     {label:>8}: {ok}/{len(grp)} đúng")

    tunings = [r["tuning_cents"] for r in rows if isinstance(r.get("tuning_cents"), (int, float))]
    if tunings:
        lech = sum(abs(c) > 15 for c in tunings)
        print(f"   Tuning: {lech}/{len(tunings)} bài lệch quá ±15 cent so với A=440")
    return {"n": n, "exact": exact, "pitch": pitch, "mirex": mirex, "counts": counts}


# ─────────────────────────────────────────────────────────────────────────────
# Phần chạy thuật toán thật (cần librosa)
# ─────────────────────────────────────────────────────────────────────────────

@contextlib.contextmanager
def _quiet(enabled):
    if not enabled:
        yield
        return
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        yield


def fetch_audio(item, cache_dir, full):
    """Đường dẫn file audio của bài: file local, hoặc tải YouTube vào cache."""
    if item.get("path"):
        return item["path"] if os.path.exists(item["path"]) else None
    from core.tone_detector import ToneDetector
    from core.utils import extract_video_id

    vid = extract_video_id(item["url"]) or "".join(c for c in item["id"] if c.isalnum())[:40]
    full_path = os.path.join(cache_dir, f"{vid}.full.wav")
    # tên theo độ dài: file 50s đời cũ không đủ cho lần dò bổ sung
    fast_path = os.path.join(cache_dir, f"{vid}.nhanh{ToneDetector.FAST_EXTEND_SECONDS + 5}.wav")
    if os.path.exists(full_path):
        return full_path
    if not full and os.path.exists(fast_path):
        return fast_path

    from core.scoring import ScoringEngine
    os.makedirs(cache_dir, exist_ok=True)
    engine = ScoringEngine()
    seconds = ToneDetector.TIMELINE_MAX_SECONDS if full else ToneDetector.FAST_EXTEND_SECONDS + 5
    got = engine.download_youtube_audio(item["url"], output_dir=cache_dir, max_seconds=seconds)
    if not got or not os.path.exists(got):
        return None
    target = full_path if full else fast_path
    os.replace(got, target)
    engine.temp_audio_path = None
    return target


def run_fast(audio_path, verbose=False):
    """Đúng đường app đi: 45s đầu, kém tự tin thì tự dò thêm (detect_key_from_file)."""
    from core.tone_detector import ToneDetector
    with _quiet(not verbose):
        return ToneDetector.detect_key_from_file(audio_path, sr=FAST_SR)


def run_full(audio_path, verbose=False):
    import librosa
    from core.tone_detector import ToneDetector
    y, sr = librosa.load(audio_path, sr=FULL_SR, mono=True,
                         duration=ToneDetector.TIMELINE_MAX_SECONDS)
    duration = len(y) / sr
    with _quiet(not verbose):
        entries = ToneDetector.detect_timeline_advanced(y, sr)
    return entries, duration


def cmd_chay(args):
    items = load_dataset(args.file)
    if args.gioi_han:
        items = items[:args.gioi_han]
    print(f"Bộ đáp án: {len(items)} bài có tone đọc được — chế độ {args.che_do}")
    full = args.che_do == "toan-bai"
    rows = []
    for i, it in enumerate(items, 1):
        label = (it.get("title") or it["id"])[:50]
        try:
            path = fetch_audio(it, args.cache, full)
        except Exception as e:
            path = None
            print(f"[{i}/{len(items)}] {label}: lỗi tải ({e})")
        if not path:
            print(f"[{i}/{len(items)}] {label}: bỏ qua — không lấy được audio")
            continue

        t0 = time.time()
        row = {"id": it["id"], "title": it.get("title", "")}
        if not full:
            truth = dominant_key(it["timeline"], 0, FAST_SECONDS)
            res = run_fast(path, args.chi_tiet)
            pred = (res["key_index"], res["scale"]) if res else None
            row.update(truth=key_name(truth), pred=key_name(pred), cls=classify(truth, pred),
                       confidence=res.get("confidence") if res else None,
                       tuning_cents=res.get("tuning_cents") if res else None,
                       mo_rong=bool(res.get("extended_seconds")) if res else False)
        else:
            entries, duration = run_full(path, args.chi_tiet)
            pred_tl = normalize_timeline(entries)
            truth = dominant_key(it["timeline"], 0, duration)
            pred = dominant_key(pred_tl, 0, duration) if pred_tl else None
            ex, pc = timeline_agreement(it["timeline"], pred_tl, duration)
            truth_changes = count_changes([e for e in it["timeline"] if e[0] < duration])
            row.update(truth=key_name(truth), pred=key_name(pred), cls=classify(truth, pred),
                       confidence=None, khop_thoi_luong=round(ex, 3),
                       khop_tap_not=round(pc, 3), doi_tone_dap_an=truth_changes,
                       doi_tone_do_duoc=count_changes(pred_tl))
        row["giay"] = round(time.time() - t0, 2)
        rows.append(row)
        mark = "✓" if row["cls"] == DUNG else ("≈" if same_pitch_set(row["cls"]) else "✗")
        extra = f"  khớp {100 * row['khop_thoi_luong']:.0f}% thời lượng" if full else ""
        print(f"[{i}/{len(items)}] {mark} {label}: đáp án {row['truth']}, dò {row['pred']}{extra}")

    summarize(rows, f"Chế độ {args.che_do}")
    if full and rows:
        n = len(rows)
        print(f"   Khớp theo thời lượng: tuyệt đối {100 * sum(r['khop_thoi_luong'] for r in rows) / n:.1f}%, "
              f"tập nốt {100 * sum(r['khop_tap_not'] for r in rows) / n:.1f}%")
        thua = sum(r["doi_tone_do_duoc"] > r["doi_tone_dap_an"] for r in rows)
        thieu = sum(r["doi_tone_do_duoc"] < r["doi_tone_dap_an"] for r in rows)
        print(f"   Số lần đổi tone: {thua} bài báo thừa, {thieu} bài báo thiếu")

    if args.bao_cao and rows:
        fields = list(dict.fromkeys(k for r in rows for k in r))
        with open(args.bao_cao, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print(f"\nĐã ghi chi tiết từng bài: {args.bao_cao}")


# ─────────────────────────────────────────────────────────────────────────────
# Bộ thử tổng hợp
# ─────────────────────────────────────────────────────────────────────────────

CHORD = {"maj": [0, 4, 7], "min": [0, 3, 7]}
SCALES = {"Major": [0, 2, 4, 5, 7, 9, 11], "Minor": [0, 2, 3, 5, 7, 8, 10]}
# Am–F–C–G (i–VI–III–VII) KHÔNG có ở đây: trùng nốt hoàn toàn với C vi–IV–I–V,
# không thuật toán trung bình chroma nào tách được — đưa vào chỉ tạo lỗi giả.
PROGRESSIONS = {
    "I-V-vi-IV": ("Major", [(0, "maj"), (7, "maj"), (9, "min"), (5, "maj")]),
    "I-IV-V-I": ("Major", [(0, "maj"), (5, "maj"), (7, "maj"), (0, "maj")]),
    "vi-IV-I-V": ("Major", [(9, "min"), (5, "maj"), (0, "maj"), (7, "maj")]),
    "i-iv-V-i": ("Minor", [(0, "min"), (5, "min"), (7, "maj"), (0, "min")]),
    "i-VII-VI-V": ("Minor", [(0, "min"), (10, "maj"), (8, "maj"), (7, "maj")]),
    "vong-quang-5-thu": ("Minor", [(0, "min"), (5, "min"), (10, "maj"), (3, "maj"),
                                   (8, "maj"), (2, "min"), (7, "maj"), (0, "min")]),
}


def synth_song(tonic, prog, sr, secs=30, chord_dur=2.0, drums=False, noise=0.0, cents=0.0, seed=0):
    import numpy as np
    rng = np.random.default_rng(seed)

    def tone(midi, dur, amp, nh, decay=True):
        t = np.arange(int(dur * sr)) / sr
        f = 440.0 * 2 ** ((midi - 69) / 12)
        y = sum((1 / h) * np.sin(2 * np.pi * f * h * t) for h in range(1, nh + 1) if f * h < sr / 2)
        env = np.exp(-1.5 * t) if decay else 1.0
        return amp * y * env * np.minimum(1, t / 0.01)

    scale, chords = PROGRESSIONS[prog]
    n = int(secs * sr)
    y = np.zeros(n)
    base, shift = 48 + tonic, cents / 100.0
    k, t0 = 0, 0.0
    while t0 < secs - 0.01:
        root, q = chords[k % len(chords)]
        i0, seg = int(t0 * sr), min(chord_dur, secs - t0)
        for part in [tone(base - 12 + root + shift, seg, 0.35, 6)] + \
                    [tone(base + root + iv + shift, seg, 0.12, 8, decay=False) for iv in CHORD[q]]:
            y[i0:i0 + len(part)] += part
        chord_pcs = [(root + iv) % 12 for iv in CHORD[q]]
        for j in range(4):
            pc = chord_pcs[rng.integers(3)] if j % 2 == 0 else SCALES[scale][rng.integers(7)]
            m = tone(base + 12 + pc + shift, seg / 4, 0.18, 5)
            s = i0 + int(j * seg / 4 * sr)
            y[s:s + len(m)] += m[:max(0, n - s)]
        t0 += chord_dur
        k += 1
    if drums:
        for s in range(0, n, int(0.5 * sr)):
            L = min(int(0.08 * sr), n - s)
            tt = np.arange(L) / sr
            y[s:s + L] += 0.6 * np.sin(2 * np.pi * (60 + 80 * np.exp(-40 * tt)) * tt) * np.exp(-25 * tt)
            y[s:s + L] += 0.15 * rng.standard_normal(L) * np.exp(-60 * tt)
    if noise:
        y += noise * rng.standard_normal(n)
    return (y / np.max(np.abs(y)) * 0.8).astype(np.float32)


def cmd_tong_hop(args):
    from core.tone_detector import ToneDetector
    tonics = range(0, 12, 3) if args.nhanh else range(12)
    scenarios = [
        ("Sạch, sr=16000 (dò nhanh)", dict(sr=FAST_SR)),
        ("Trống + nhiễu, sr=16000", dict(sr=FAST_SR, drums=True, noise=0.02)),
        ("Lệch tuning -32 cent (A=432Hz)", dict(sr=FAST_SR, cents=-32)),
        ("Lệch tuning +20 cent", dict(sr=FAST_SR, cents=20)),
        ("Lệch tuning +40 cent", dict(sr=FAST_SR, cents=40)),
    ]
    all_rows = []
    for title, kw in scenarios:
        sr = kw.pop("sr")
        rows = []
        for prog, (scale, _) in PROGRESSIONS.items():
            for tonic in tonics:
                y = synth_song(tonic, prog, sr, seed=tonic, **kw)
                with _quiet(not args.chi_tiet):
                    res = ToneDetector.detect_key_from_audio(y, sr, skip_hum_detection=True)
                pred = (res["key_index"], res["scale"]) if res else None
                rows.append({"cls": classify((tonic, scale), pred), "prog": prog,
                             "confidence": res.get("confidence") if res else None,
                             "tuning_cents": res.get("tuning_cents") if res else None})
        summarize(rows, title)
        bad = {}
        for r in rows:
            if r["cls"] != DUNG:
                bad[r["prog"]] = bad.get(r["prog"], 0) + 1
        if bad:
            print("   Sai theo vòng hợp âm:", ", ".join(f"{p} {c}" for p, c in bad.items()))
        all_rows += rows
    summarize(all_rows, "TỔNG")


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = argparse.ArgumentParser(description="Chấm điểm thuật toán dò tone")
    sub = p.add_subparsers(dest="lenh", required=True)

    t = sub.add_parser("tong-hop", help="bộ thử âm thanh tổng hợp (không cần mạng)")
    t.add_argument("--nhanh", action="store_true", help="chỉ 4 tone/vòng thay vì 12")
    t.add_argument("--chi-tiet", action="store_true", help="in log của bộ dò")
    t.set_defaults(func=cmd_tong_hop)

    c = sub.add_parser("chay", help="chấm trên bộ đáp án thật")
    c.add_argument("file", help="dap_an_tone.json | manual_timelines.json | JSON tự soạn")
    c.add_argument("--che-do", choices=["nhanh", "toan-bai"], default="nhanh")
    c.add_argument("--cache", default=os.path.join(ROOT, ".cache", "danh_gia_tone"),
                   help="thư mục giữ audio đã tải (mặc định .cache/danh_gia_tone)")
    c.add_argument("--gioi-han", type=int, default=0, help="chỉ chấm N bài đầu")
    c.add_argument("--bao-cao", help="ghi chi tiết từng bài ra CSV")
    c.add_argument("--chi-tiet", action="store_true", help="in log của bộ dò")
    c.set_defaults(func=cmd_chay)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
