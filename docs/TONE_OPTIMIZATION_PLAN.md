# Tối ưu luồng Dò Tone & Dò Lại Tone

## Context

Lúc chạy "Dò Lại Tone" (fast mode) mất 5–15 giây: phần lớn là network download, cộng thêm các chi phí lặp không cần thiết bên Python (cache JSON đọc 2–3 lần, reload lại cache ngay sau khi mới save, PYIN hum-detection luôn chạy dù audio YouTube hiếm khi có hum điện, librosa decode ở `sr=22050` trong khi chroma chỉ cần ≤ 8 kHz). Ngoài ra user không có cách huỷ khi quét đang chạy: nút `Dò Lại` bị disable cho tới khi xong hoặc lỗi.

Yêu cầu hiện tại: rút ngắn độ trễ + cho phép huỷ giữa chừng, **không** thêm pre-fetch speculative.

Code gốc:
- `core/engine/_tone.py` — pipeline chính (`detect_tone_from_browser`, `auto_detect_youtube_timeline`, `_resolve_tone`, `_check_tone_cache`)
- `core/tone_detector.py` — `detect_key_from_audio` (có đoạn PYIN hum detection ~100–200 ms), `detect_timeline_advanced`
- `core/scoring.py` — `download_youtube_audio_with_info` (range 0–60 s), `download_youtube_audio` (range 0–60 s)
- `core/tone_cache.py` — `ToneCacheManager.get_cached_tone` (đọc cả file JSON mỗi lần gọi)
- `frontend_qt.py` — `_on_force_rescan` (gọi `_tone_session.stop()` 2 lần, không có nhánh Huỷ)
- `ui/panels/tools.py` — nút "Dò Lại" dòng 124
- `core/engine/_youtube.py` — `_dispatch_auto_detect` (routing fast/full)

## Thay đổi theo tier

### Tier 1 — Khử trùng lặp (an toàn, impact lớn)

**1.1. `core/engine/_tone.py`: dùng `resolved_data` thay vì re-lookup cache**

Trong cả `detect_tone`, `detect_tone_from_youtube`, `detect_tone_from_browser`:
- Khi `_resolve_tone()` trả về `('cache', resolved_data)`, build `result` trực tiếp từ `resolved_data` thay vì gọi lại `self._check_tone_cache(url)` (đã đọc cache lần 2).
- Gộp logic build-result + send MIDI vào 1 helper private mới `_build_cache_result(cached)` thay thế `_check_tone_cache` (rename để chỉ còn 1 entry point).

**1.2. `core/engine/_tone.py:362`: bỏ `ToneCacheManager.get_cached_tone(youtube_url)` sau khi vừa `save_tone_to_cache`**

Dòng 362-365 hiện đang gọi lại `get_cached_tone` để lấy data vừa lưu cho `_replay_cached_timeline`. Thay bằng: dựng dict timeline từ `result` đã có trong scope → tiết kiệm 1 file read.

**1.3. `frontend_qt.py:_on_force_rescan` (~line 445–449): bỏ double `_tone_session.stop()`**

Kéo 1 lần duy nhất ra trước if/else.

**1.4. In-session memoization cho tone cache**

Thêm `self._tone_resolve_cache: OrderedDict[str, tuple]` (max 8 entries) trong `SystemEngine.__init__` (file `core/engine/_base.py` hoặc mixin phù hợp). Trong `_resolve_tone`:
- Nếu url có trong cache in-session → return luôn tuple đã cache.
- Khi load từ disk xong, đẩy vào cache in-session.
- Khi `save_tone` hoặc `save_timeline` được gọi → invalidate entry cho url đó.

Mục tiêu: user bấm "Dò Lại" liên tiếp hoặc YT watcher re-dispatch cùng URL sẽ không đọc JSON đi đọc lại.

### Tier 2 — Speedup CPU/network

**2.1. `core/scoring.py`: giảm download range 60 s → 50 s**

Trong `download_youtube_audio_with_info` (line 143) và `download_youtube_audio` (line 72), đổi `'end_time': 60` → `'end_time': 50`. Fast scan analysis chỉ load 45 s; 5 s margin là đủ cho encoder/container padding.

Không đổi cho full-scan timeline (`download_youtube_audio` vẫn cần full track khi scan_mode='full').
→ **Thực tế:** tách thành tham số `max_seconds=None` cho `download_youtube_audio`; fast path truyền `max_seconds=50`, full path truyền `max_seconds=None` (full track). `download_youtube_audio_with_info` mặc định `max_seconds=50`.

**2.2. `core/engine/_tone.py`: hạ `sr` cho fast scan từ 22050 → 16000**

- `detect_tone_from_browser` dòng 328: `librosa.load(audio_path, sr=16000, mono=True, duration=45)`.
- `detect_key_from_youtube` (trong `core/tone_detector.py` dòng 534): thêm tham số `sr=16000` cho fast path — giữ 22050 cho full-scan (`auto_detect_youtube_timeline` line 455 không đổi, vì có thể ảnh hưởng novelty curve chính xác cao hơn với sr cao).

Chroma CQT chỉ quan tâm pitch ≤ 4 kHz → sr=16000 đủ, cắt 27% khối lượng tính.

**2.3. `core/tone_detector.py`: thêm `skip_hum_detection=False` cho `detect_key_from_audio`**

Block PYIN hum detection (dòng 162–183 của `tone_detector.py`) chỉ có ích cho audio loopback (có thể dính 50/60 Hz hum từ phần cứng). YouTube audio đã được encoder làm sạch, không cần.

- Thêm kwarg `skip_hum_detection=False`.
- Trong `detect_tone_from_browser` và `detect_key_from_youtube`: gọi với `skip_hum_detection=True`.
- `detect_key_from_system_audio` và `auto_detect_youtube_timeline` giữ mặc định `False` (hum check vẫn chạy).

### Tier 3 — UX huỷ giữa chừng

**3.1. `core/engine/_tone.py`: thêm cancel checkpoints**

Trong `detect_tone_from_browser` và `auto_detect_youtube_timeline`, thêm `if cancel.is_set(): return` ngay sau các điểm blocking:
- Sau `scoring_engine.download_youtube_audio_with_info(...)` (đã có).
- **Thêm** trước `librosa.load(...)` (hiện chưa có).
- **Thêm** giữa `librosa.load()` và `ToneDetector.detect_key_from_audio(...)` (hiện chưa có) — load audio có thể mất 0.5–1.5 s ở đây.

**3.2. `ui/panels/tools.py` + `frontend_qt.py`: nút Dò Lại chuyển thành Huỷ khi đang quét**

- `_on_force_rescan` hiện disable button và đổi text thành "⏳ Đang dò...". Thay đổi:
  - Khi `_do_tone_running` → button đổi thành "❌ Huỷ", **vẫn enabled**, kết nối đến handler mới `_on_cancel_rescan`.
  - Handler `_on_cancel_rescan()`: gọi `self.engine._tone_session.stop()`, set `_do_tone_running = False`, reset button về "Dò Lại" (teal), clear marquee "♪ Đang dò... ♪".
- `_handle_tone_result` (nhánh error hiện tại) khi nhận được kết quả hoặc error phải trả button về state "Dò Lại" chuẩn.
- Tách helper `_set_rescan_button_state(state: Literal["idle","running","cancel"])` để tránh rải logic state ở 3 chỗ.

**3.3. Signal marshal trên main thread**

`_on_cancel_rescan` chạy trên main thread (Qt button click) → gọi trực tiếp `.stop()` là thread-safe (chỉ set `threading.Event`). Không cần signal. Background detect thread sẽ thấy `cancel.is_set()` ở checkpoint tiếp theo và return; `finally` block của nó tự gọi `self._tone_session.stop()` (đã có). Main thread chỉ cần reset UI ngay lập tức sau khi set flag.

## Critical files to modify

| File | Thay đổi chính |
|------|---------------|
| `core/engine/_tone.py` | 1.1, 1.2, 1.4, 2.2, 3.1 |
| `core/engine/_base.py` *(hoặc mixin khởi tạo)* | 1.4 — khởi tạo `_tone_resolve_cache` |
| `core/tone_detector.py` | 2.3 — tham số `skip_hum_detection` |
| `core/scoring.py` | 2.1 — tham số `max_seconds` |
| `frontend_qt.py` | 1.3, 3.2 — handler Huỷ + state machine button |
| `ui/panels/tools.py` | 3.2 — (nếu cần thêm text variant) |

## Verification

1. **Manual test trên Windows (bắt buộc)**:
   - Mở 1 video YouTube chưa có trong cache → bấm "Dò Lại" → đo thời gian từ lúc bấm tới lúc marquee hiển thị key. So sánh trước/sau (kỳ vọng: giảm 1–3 s).
   - Bấm "Dò Lại" **lần 2 trên cùng URL** (đã có cache) → phải trả kết quả < 200 ms (in-session cache hit, không I/O).
   - Bắt đầu "Dò Lại" → bấm "❌ Huỷ" ngay trong lúc đang download → marquee dừng, button về "Dò Lại", không có exception trong log.
   - Bắt đầu "Dò Lại" → để chạy xong → button tự về "Dò Lại".

2. **Full-scan mode**:
   - Đổi "Chế độ: Full" → chạy 1 bài chưa có timeline → phải vẫn chạy đúng với sr=22050 (không bị Tier 2.2 ảnh hưởng). Kết quả timeline giống phiên bản cũ.

3. **Autokey (system audio)**:
   - Bật Auto-Tune / AutoKey → phải vẫn có hum detection (block PYIN vẫn chạy). Log kiểm: `✅ Notch: loại hum` hiện khi có hum.

4. **Regression check key accuracy**:
   - Chọn 3 bài đã biết key (VD: Am, C, F#m) → so sánh kết quả fast scan cũ vs mới. Cho phép lệch relative-pair (VD C ↔ Am) nhưng không được lệch xa hơn.

5. **Test log patterns**:
   - Dò hit cache → log có `✅ [RESOLVE] Tone cache hit` **một lần duy nhất** (trước đây có thể có 2 lần: RESOLVE + CACHE).
   - Dò lần 2 cùng URL trong session → log mới `✅ [RESOLVE] In-session hit` (hoặc tương tự).

Không cần unit test riêng — thay đổi đều nằm trong pipeline đã được integration-test qua UI.
