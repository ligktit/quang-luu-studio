# Plan: Chấm điểm thật & Lịch sử điểm

**Dự án:** Quang Lưu Studio — `D:\Projects\LiveStudio\quang-luu-studio`
**Ngày:** 2026-06-10
**Phạm vi:** 2 tính năng — (1) Chấm điểm hát thật dựa trên so sánh cao độ với giai điệu tham chiếu, (2) Lịch sử điểm + tiến bộ theo bài.

---

## Feature 1: Chấm điểm hát THẬT (real singing scoring)

### Mục tiêu

- Thay pipeline chấm điểm "không tham chiếu" hiện tại bằng pipeline so sánh **cao độ người hát (mic)** với **giai điệu tham chiếu trích từ audio gốc của bài hát trên YouTube**.
- Các chỉ số thật: độ chính xác cao độ (cents), độ đúng nhịp (timing), độ ổn định, có khoan dung vibrato.
- Vẫn giữ tinh thần karaoke giải trí: điểm mang tính khích lệ, độ khắt khe cấu hình được.
- Hiển thị biểu đồ cao độ sau khi hát (sung pitch vs reference, tô đậm đoạn lệch tông) ngay trong dialog kết quả hiện có.
- Lưu kết quả vào lịch sử điểm theo bài (liên kết với Feature 2).

### Hiện trạng (file:line cụ thể)

**Chấm điểm hiện tại — phân tích thật nhưng KHÔNG có tham chiếu:**

- `core/scoring.py:214` — `ScoringEngine.calculate_score()` là entry point. Chế độ full (`_calculate_full_score`, dòng 293) chạy `librosa.pyin` trên **file mix** (nhạc + giọng trộn chung) rồi tính:
  - `_compute_pitch_intonation` (dòng 404): khoảng cách tới semitone gần nhất — không biết note ĐÚNG là note nào.
  - `_compute_key_conformity` (dòng 450): % note nằm trong thang âm của `key_reference`.
  - `_compute_volume_consistency` (dòng 371), `_compute_rhythm_score` (dòng 481): đo trên mix nên thực chất đo... bản nhạc, không phải người hát.
- `core/scoring.py:509-515` — `_encourage(raw, floor=65, ceiling=98)` nén mọi kết quả vào dải 65–98. Vì pyin chạy trên mix (nhạc nền luôn "đúng tông"), điểm thực tế dao động hẹp ~77–100 bất kể người hát thế nào → cảm giác "ngẫu nhiên".

**Thu âm — mic và nhạc bị TRỘN thành 1 file, không tách lại được:**

- `recorder_worker.py:164-489` — `main()` mở 2 stream: WASAPI loopback (nhạc ra loa, dòng 284-292) và microphone (dòng 294-303), nhưng `_write_mix()` (dòng 377-389) cộng thẳng `lb_seg + mc_seg` rồi ghi **một** file WAV stereo. Giao thức argv (dòng 7-11): `output.wav, stop_flag, loopback_idx, mic_idx`.
- `core/recorder.py:33` — `AudioRecorder.start_recording()` spawn worker (dev: subprocess dòng 135-148; frozen: exec inline dòng 308-381). `stop_recording()` ở dòng 248.
- `core/engine/_recording.py:13-69` — `start_quick_score()`: bắt đầu thu → chờ `quick_score_active=False` (user bấm dừng hoặc video kết thúc, xem `core/engine/_youtube.py:418-435` `on_video_end`) → `ScoringEngine.load_audio(rec_path)` → `calculate_score(quick=False, key_reference=...)`.

**Nguồn dữ liệu sẵn có để xây tham chiếu:**

- `core/scoring.py:92-144` — `download_youtube_audio()` đã tải được audio YouTube về WAV (mặc định chỉ 60s đầu — cần mở rộng).
- `core/tone_detector.py:130` — `detect_key_from_audio()` dùng CQT/chroma để dò key. **Lưu ý:** codebase hiện **chưa có HPSS** (grep `hpss|harmonic|percussive` không có kết quả thực) — sẽ thêm mới qua `librosa.effects.hpss` (librosa đã có sẵn trong `requirements.txt`).
- `core/cdp_monitor.py:170-217` — `_monitor_loop()` poll `player.getCurrentTime()/getDuration()/getPlayerState()` mỗi `CDP_POLL_INTERVAL` (0.1s, `core/config.py:340`) → biết chính xác vị trí video tại thời điểm bắt đầu thu âm → dùng làm offset căn chỉnh thô.
- `frontend_qt.py:863` — key hiện tại lấy từ `self.current_tone`; URL đang phát: `engine.current_youtube_url` (`core/engine/_tone.py:366`, `frontend_qt.py:898`).

**UI hiện tại:**

- `frontend_qt.py:838-870` — `_on_score()` toggle Quick Score; callback `on_score_ready` emit `_score_report_signal` (khai báo dòng 95, connect dòng 211).
- `frontend_qt.py:880-882` — `_show_scoring_report()` mở `ui/dialogs/scoring_report.py:37` `ScoringReportDialog` (header điểm + `_build_stats` dòng 138 + feedback). Toàn bộ UI vẽ bằng QPainter thuần (xem `_GradientBar` dòng 12-34 và bộ `ui/components/painter_*.py`, `waveform_hero.py`).

### Kiến trúc đề xuất

```
                      ┌─────────────────────────────────────────────┐
 Khi bài hát bắt đầu  │  core/melody_reference.py  (MỚI)            │
 (open_youtube_url)   │  - download full audio (tái dùng            │
 ────────────────────►│    ScoringEngine.download_youtube_audio)    │
   background thread  │  - HPSS → harmonic → pyin (dải giọng hát)   │
                      │  - lưu cache .npz theo video_id              │
                      │    (DATA_DIR/melody_cache/)                  │
                      └──────────────┬──────────────────────────────┘
                                     │ ReferenceMelody {times, f0, conf}
 Quick Score          ┌──────────────▼──────────────────────────────┐
 (start_quick_score)  │  recorder_worker.py (SỬA): ghi 2 file        │
 ────────────────────►│   recording_X.wav  = mix (như cũ)            │
   + lưu cdp offset   │   recording_X_mic.wav = mic-only (MỚI)       │
                      └──────────────┬──────────────────────────────┘
                                     │ mic.wav + mix.wav + video_pos_at_start
                      ┌──────────────▼──────────────────────────────┐
                      │  core/scoring.py (SỬA): calculate_real_score │
                      │  1. align: offset CDP + cross-correlation    │
                      │     onset-envelope(mix) vs onset(reference)  │
                      │  2. pyin trên mic.wav → sung f0              │
                      │  3. so sánh cents (octave-invariant),        │
                      │     timing, stability, vibrato tolerance     │
                      │  4. map điểm theo strictness (settings.json) │
                      │  5. fallback → _calculate_full_score cũ      │
                      └──────────────┬──────────────────────────────┘
                                     │ result dict + pitch_series
                      ┌──────────────▼──────────────────────────────┐
                      │  ui/components/pitch_chart.py (MỚI, QPainter)│
                      │  + ScoringReportDialog (SỬA): thêm panel chart│
                      │  + core/score_history.py (Feature 2)         │
                      └─────────────────────────────────────────────┘
```

**Các quyết định kiến trúc chính:**

1. **Tách kênh mic bằng file thứ hai** thay vì WAV 4 kênh: `recorder_worker.py` nhận thêm argv 5 (`mic_output_path`, optional). Hai file ghi từ cùng vòng `_write_mix` nên **sample-aligned tuyệt đối** với nhau (mix dùng để căn chỉnh với reference, mic dùng để chấm). Giữ nguyên file mix → không phá tính năng thu âm hiện có và test `tests/core/test_engine.py:318` (E-20).

2. **Tham chiếu từ audio YouTube gốc** (không phải từ loopback): tải full bằng `download_youtube_audio` (bỏ giới hạn `max_seconds=60`, cap ~8 phút), HPSS lấy phần harmonic, chạy `librosa.pyin` giới hạn dải giọng hát (G2–C6) + gating theo `voiced_prob` ≥ 0.5 và RMS cục bộ. Kết quả cache `.npz` (`times, f0_midi, conf`) theo `video_id` trong `DATA_DIR/melody_cache/` (pattern path theo `core/config.py:33-44`). Trích xuất chạy **nền ngay khi bài bắt đầu phát** (song song lúc người dùng hát) để khi bấm dừng là có sẵn.

3. **Căn chỉnh 2 tầng:**
   - Thô: tại thời điểm `start_quick_score`, đọc `engine.cdp_monitor.current_position` (`core/cdp_monitor.py:207`) → biết recording bắt đầu ở giây thứ mấy của bài.
   - Tinh: cross-correlation `librosa.onset.onset_strength` giữa mix.wav và đoạn reference tương ứng (±3s quanh offset thô) → offset chính xác ~±50ms. Nếu CDP không kết nối → search toàn dải bằng cross-correlation (chậm hơn nhưng vẫn chạy).

4. **So sánh khoan dung kiểu karaoke:**
   - Chỉ chấm các frame mà reference có confidence cao VÀ mic voiced.
   - Octave-invariant: lỗi cents tính theo `min over k của |Δmidi − 12k|` (nam hát bài nữ thấp hơn 1 quãng tám vẫn đúng). Đồng thời bù **key offset** nếu user đã đổi tone (`current_tone` vs tone gốc bài — chênh n semitone thì dịch reference n semitone).
   - Vibrato tolerance: smooth sung-f0 bằng median filter 5 frame trước khi tính lỗi; lỗi ≤ 50 cents coi như đúng 100%.
   - Timing: cho phép trễ/sớm ±150ms (so khớp với reference trong cửa sổ trượt, lấy lỗi nhỏ nhất).
   - Strictness: key mới trong `settings.json` (`ConfigManager`, `core/config.py:343-362`): `"scoring_strictness": "easy" | "normal" | "hard"` → đổi ngưỡng cents (easy: 70/100, normal: 50/100, hard: 35/100) và floor của `_encourage` (easy giữ floor 65, hard hạ floor 50, ceiling 100).

5. **Fallback bắt buộc:** nếu (a) tải reference thất bại, (b) reference có voiced ratio < 15% (video karaoke beat không lời), hoặc (c) mic gần như im lặng → quay về `_calculate_full_score` hiện tại, đánh dấu `"mode": "legacy"` trong result để UI ghi chú "Chấm theo chế độ cơ bản".

6. **Biểu đồ: QPainter custom, KHÔNG thêm pyqtgraph.** Lý do: toàn bộ UI app đã là QPainter thuần (`ui/components/painter_*.py`, `waveform_hero.py`, `_GradientBar` trong `scoring_report.py:12`), pyqtgraph kéo thêm dependency + phình PyInstaller build (`QuangLuuStudio.spec`) trong khi nhu cầu chỉ là 1 line-chart tĩnh sau khi hát. Widget mới `ui/components/pitch_chart.py` nhận `pitch_series` và vẽ trong `paintEvent`.

### Các bước triển khai theo phase

#### Phase 1.1 — Thu âm tách kênh mic (≈2 ngày)

| Việc | File | Chi tiết |
|---|---|---|
| Thêm argv 5 `mic_output_path` | `recorder_worker.py` (sửa `main()` dòng 164-175) | Nếu có arg 5: mở thêm `wave.open(mic_path)` 1 file stereo thứ hai; trong `_write_mix` (dòng 377) ghi thêm `mc_seg` (chưa cộng lb) vào file mic. Flush cuối (dòng 444-465) ghi cả 2 file. |
| API recorder | `core/recorder.py` — `start_recording()` dòng 33, `stop_recording()` dòng 248 | Tham số mới `capture_mic_separately: bool = False`; sinh `self.mic_output_path = output_path.replace('.wav', '_mic.wav')`; truyền vào argv subprocess (dòng 135-142) và `_sys.argv` frozen-mode (dòng 318-324). `stop_recording()` trả thêm path mic; `cleanup()` (dòng 384) xóa cả file mic. |
| Engine | `core/engine/_recording.py` — `start_quick_score()` dòng 13 | Gọi `score_recorder.start_recording(..., capture_mic_separately=True)`; ghi nhận `video_pos_at_start = self.cdp_monitor.current_position if self.cdp_monitor.is_connected else None` và `wall_time_start`. |
| Test | `tests/core/test_engine.py` (cạnh E-20 dòng 318) | Cập nhật assert tham số mới; test worker 2 file bằng WAV giả lập. |

**Điểm tích hợp:** không đổi hành vi khi `capture_mic_separately=False` → tính năng thu âm thường (nút Record) giữ nguyên.

#### Phase 1.2 — Trích giai điệu tham chiếu (≈3 ngày)

| Việc | File | Chi tiết |
|---|---|---|
| Module mới | `core/melody_reference.py` (MỚI) | Class `MelodyReferenceExtractor`: `extract(youtube_url, on_done, cancel_event)` chạy thread nền — (1) check cache `DATA_DIR/melody_cache/{video_id}.npz`; (2) tải full audio (tái dùng `ScoringEngine.download_youtube_audio`, `core/scoring.py:92`, truyền `max_seconds=None` và cap 480s); (3) `librosa.load(sr=22050, mono=True)` → `librosa.effects.hpss(y, margin=(1.0, 5.0))` → pyin trên harmonic, `fmin=G2, fmax=C6`, `hop_length=512`; (4) gate theo `voiced_prob` + RMS; (5) lưu npz `{times, f0_midi, conf, sr_hop}` + xóa wav tạm (prefix `qls_tmp_`, `core/config.py:80`). |
| Path mới | `core/config.py` (sau dòng 73) | `MELODY_CACHE_DIR = os.path.join(DATA_DIR, "melody_cache")` + dọn LRU >20 file. |
| Kích hoạt nền | `core/engine/_youtube.py` — trong `open_youtube_url` (vùng dòng 366-395) | Sau khi set `current_youtube_url`, spawn `MelodyReferenceExtractor.extract(url, ...)` với throttle (chờ 5s sau khi tone detect xong để không tranh CPU với `_tone.py:398-433`). Lưu handle vào `self._melody_ref_future`. Hủy qua `cancel_event` khi đổi bài (pattern `ToneSession`, `core/engine/_session.py:23-29`). |

#### Phase 1.3 — Chấm điểm so sánh (≈3 ngày)

| Việc | File | Chi tiết |
|---|---|---|
| Hàm chấm mới | `core/scoring.py` | Thêm `calculate_real_score(mic_path, mix_path, reference, video_pos_at_start, key_shift_semitones, strictness)`. Các hàm con mới: `_align_offset(mix, reference, coarse_offset)` (onset-strength cross-correlation, `scipy.signal.correlate`); `_extract_sung_pitch(mic)` (pyin + median filter); `_compare_pitch(sung, ref, offset)` → mảng lỗi cents per-frame (octave-invariant, timing window ±150ms); `_score_from_errors(errors, strictness)` → `pitch_accuracy`, `timing_score`, `stability_score` (jitter quanh ref thay vì jitter tuyệt đối), giữ `volume_consistency` đo trên mic. Trọng số: pitch 0.45, timing 0.20, stability 0.20, volume 0.15. `_encourage` nhận floor/ceiling theo strictness. |
| Pitch series cho chart | `core/scoring.py` | Result dict thêm: `"mode": "real"`, `"pitch_series": {"times": [...], "ref_midi": [...], "sung_midi": [...], "err_cents": [...]}` (downsample ~10 điểm/giây). |
| Fallback | `core/scoring.py` + `core/engine/_recording.py:43-55` | `start_quick_score` thử `calculate_real_score`; nếu reference chưa sẵn → chờ tối đa 20s (`_melody_ref_future`); hết hạn/thất bại → `calculate_score(quick=False)` cũ, `"mode": "legacy"`. |
| Strictness setting | `core/config.py` (ConfigManager) + `ui/dialogs/settings_dialog.py` | Combo "Độ khắt khe chấm điểm: Dễ / Vừa / Khó" lưu `settings["scoring_strictness"]`; `frontend_qt.py:859-870` đọc và truyền xuống `start_quick_score`. |

#### Phase 1.4 — Biểu đồ cao độ + UI (≈2.5 ngày)

| Việc | File | Chi tiết |
|---|---|---|
| Widget chart | `ui/components/pitch_chart.py` (MỚI) | `PitchChartWidget(QWidget)`: nhận `pitch_series`; `paintEvent` vẽ — nền card (`C["card"]`, token từ `ui/design_tokens.py`), đường reference (màu `C["primary"]`), đường sung pitch (màu `C["green"]` khi `|err|≤50 cents`, `C["accent"]` khi lệch — vẽ theo segment), vùng tô đỏ nhạt cho các đoạn off-key kéo dài >0.5s, trục thời gian mm:ss, nhãn note (C4, G4...) trục dọc. Tooltip hover (mouseMoveEvent) hiện thời điểm + lệch cents. Cao ~180px. |
| Cắm vào dialog | `ui/dialogs/scoring_report.py` — `_build_scroll()` dòng 116-136 | Khi `result["mode"]=="real"` và có `pitch_series`: chèn `PitchChartWidget` giữa `_build_stats` và `_build_feedback` (sau dòng 131). Thêm chú thích "Xanh: đúng tông · Đỏ: lệch tông". Mode legacy: hiện label "Chấm cơ bản (không có giai điệu tham chiếu)". |
| Metric labels | `ui/dialogs/scoring_report.py:160-166` | Thêm hàng "Đúng cao độ (so giai điệu)" và "Đúng nhịp" khi mode real. |

**Luồng không đổi:** `frontend_qt.py:850-857` `on_score_ready` → `_score_report_signal` → `_show_scoring_report` (dòng 880) — chỉ result dict giàu hơn.

#### Phase 1.5 — Kiểm thử & tinh chỉnh (≈2 ngày)

- Unit test `tests/core/test_scoring_real.py`: sinh tín hiệu sine theo giai điệu chuẩn (ref) + sung lệch 0/±30/±100/±200 cents → assert thứ tự điểm đơn điệu giảm; test octave-invariant; test fallback khi reference rỗng.
- Test align: mix = ref dịch 2.7s + noise → `_align_offset` sai số <100ms.
- Test thực địa với 3 bài karaoke Việt phổ biến (có bè giai điệu / beat trống không lời / video gốc có lời) — hiệu chỉnh ngưỡng strictness.

### Phụ thuộc mới

- **Không thêm thư viện bắt buộc nào.** `librosa>=0.10,<1.0`, `numpy`, `scipy` đã có (`requirements.txt`). HPSS = `librosa.effects.hpss`, pyin = `librosa.pyin`, cross-correlation = `scipy.signal`.
- Từ chối có chủ đích: `pyqtgraph` (thừa cho 1 chart tĩnh, phình build), `crepe`/`torchcrepe` (kéo TensorFlow/PyTorch — không chấp nhận được cho app PyInstaller), `demucs`/`spleeter` (tách vocal chất lượng cao nhưng nặng — ghi nhận là "nâng cấp tương lai" nếu HPSS+pyin không đủ).

### Rủi ro & cách giảm

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| HPSS+pyin trích giai điệu sai trên mix gốc (bắt nhầm nhạc cụ) | Cao | Giới hạn dải G2–C6; gate theo voiced_prob ≥0.5; chỉ chấm frame có conf cao (chấp nhận chỉ chấm 40-70% thời lượng); octave-invariant; test thực địa Phase 1.5; fallback legacy khi voiced ratio ref <15%. |
| Video karaoke beat-only không có giai điệu hát | Cao | Phát hiện ở extractor (voiced ratio thấp) → mode legacy + thông báo rõ trong dialog. |
| pyin full bài chậm (CPU yếu, đang vừa hát vừa thu) | Trung | sr=22050 mono, cap 8 phút, chạy nền có throttle sau tone-detect, cache npz theo video_id (lần 2 hát lại = 0 giây), `MemoryGuard.force_cleanup()` sau extract (pattern `core/engine/_recording.py:66`). |
| CDP không kết nối → mất offset thô | Trung | Cross-correlation toàn dải trên onset envelope; nếu vẫn fail → mode legacy. |
| User đổi tone bằng MIDI giữa bài (Auto-Tune dịch giọng) | Trung | Bù `key_shift_semitones` từ `current_tone` vs tone gốc; nếu có manual timeline đổi tone giữa bài → v1 chấp nhận sai số, ghi chú known-limitation. |
| File mic lệch sample với mix | Thấp | Hai file ghi cùng vòng lặp `_write_mix` → cùng frame count; thêm assert độ dài bằng nhau khi load. |
| Hồi quy thu âm thường | Thấp | Cờ `capture_mic_separately` mặc định False; chạy lại test E-20/E-21 hiện có. |

### Tiêu chí nghiệm thu

1. Hát đúng giai điệu (test bằng phát lại chính audio gốc vào mic ảo) → `pitch_accuracy` ≥ 90 raw; tổng điểm ≥ 90 ở strictness "Vừa".
2. Hát lệch đều +1 semitone toàn bài → `pitch_accuracy` raw giảm ≥ 30 điểm so với hát đúng; tổng điểm thấp hơn rõ rệt (≥ 8 điểm hiển thị).
3. Im lặng hoàn toàn (không hát) → không trả 77-100 như hiện nay; báo "voiced quá thấp" hoặc điểm sàn + tip phù hợp.
4. Hát thấp hơn 1 quãng tám nhưng đúng giai điệu → KHÔNG bị trừ pitch (octave-invariant).
5. Biểu đồ hiển thị trong ScoringReportDialog ≤ 300ms sau khi có result; đoạn lệch tông tô đỏ trùng khớp với `err_cents > ngưỡng`.
6. Video beat-only / mất mạng tải reference → app không crash, tự fallback legacy có ghi chú.
7. Strictness đổi trong Settings có hiệu lực ngay lần chấm sau, không cần restart.
8. Thu âm thường (nút Record) và toàn bộ test `tests/core/test_engine.py` pass không đổi.

### Ước lượng effort

| Phase | Ngày công |
|---|---|
| 1.1 Thu tách kênh mic | 2 |
| 1.2 Trích giai điệu tham chiếu + cache | 3 |
| 1.3 Align + so sánh + strictness | 3 |
| 1.4 Pitch chart + tích hợp dialog | 2.5 |
| 1.5 Test + tinh chỉnh thực địa | 2 |
| **Tổng Feature 1** | **≈ 12.5 ngày** |

---

## Feature 2: Lịch sử điểm + tiến bộ theo bài

### Mục tiêu

- Lưu bền vững mọi lần chấm điểm (điểm tổng, metrics, mode, thời điểm) gắn với bài hát (URL YouTube).
- Xem lại lịch sử và tiến bộ ngay từ danh sách bài hát hiện có ("Lịch sử" — `SongsListDialog`): điểm cao nhất, số lần hát, xu hướng tăng/giảm, sparkline đơn giản.
- Trong dialog kết quả: hiện "so với lần trước: +x điểm".

### Hiện trạng (file:line cụ thể)

- **Chưa có persistence điểm nào.** Result chỉ sống trong `ScoringReportDialog` rồi mất (`frontend_qt.py:880-882`).
- Pattern lưu JSON chuẩn của app: `core/songs.py:18-98` `SongManager` — module-level `threading.Lock` (dòng 15), `atomic_write_json` từ `core/utils.py`, file trong `DATA_DIR` (`core/config.py:33-44`, frozen = `%APPDATA%/QuangLuuStudio/`).
- UI danh sách bài: `ui/dialogs/songs_list.py:14` `SongsListDialog`, mở từ `frontend_qt.py:1363-1365` `_show_songs_list()`. Mỗi card (`_build_song_card`, dòng 104-164) đã có hàng phụ hiện tone/timeline/ngày (dòng 134-143) và 3 nút Play/Edit/Delete (dòng 146-159) — chỗ tự nhiên để thêm badge điểm + nút "Tiến bộ".
- Điểm hiện hành trên dashboard: `frontend_qt.py:1371-1375` `update_score_display()` đẩy vào `waveform_hero` score ring.

### Kiến trúc đề xuất

**Schema — `DATA_DIR/score_history.json`:**

```json
{
  "version": 1,
  "entries": [
    {
      "id": 17,
      "song_url": "https://www.youtube.com/watch?v=abc123",
      "video_id": "abc123",
      "song_title": "Duyên Phận",
      "tone": "Am",
      "timestamp": "2026-06-10 21:35:02",
      "mode": "real",
      "strictness": "normal",
      "total_score": 88.4,
      "metrics": {
        "pitch_accuracy": 82.1, "timing_score": 90.0,
        "pitch_stability": 85.3, "volume_consistency": 91.2
      },
      "duration": 245.6
    }
  ]
}
```

- Khóa nhóm theo `video_id` (normalize từ URL — bài đã lưu hay chưa lưu trong `saved_songs.json` đều ghi được lịch sử).
- Cap 1000 entries, tự cắt entry cũ nhất (FIFO) khi vượt.
- Module mới `core/score_history.py` — class `ScoreHistoryManager` (static methods, mirror `SongManager`):
  - `add_entry(result_dict, song_url, song_title, tone) -> entry`
  - `get_by_video(video_id) -> list[entry]` (sort theo timestamp)
  - `get_stats(video_id) -> {best, last, count, avg_last_5, trend}` (`trend` = delta avg 3 lần gần nhất vs 3 lần trước đó)
  - `get_recent(n=20)`

### Các bước triển khai theo phase

#### Phase 2.1 — Storage + hook ghi điểm (≈1 ngày)

| Việc | File | Chi tiết |
|---|---|---|
| Hằng path | `core/config.py` (sau dòng 73) | `SCORE_HISTORY_FILE = os.path.join(DATA_DIR, "score_history.json")`. |
| Module | `core/score_history.py` (MỚI) | `ScoreHistoryManager` như trên; lock + `atomic_write_json` theo đúng `core/songs.py:15,35`. |
| Export backend | `backend.py` | Re-export `ScoreHistoryManager` (theo pattern `SongManager`/`ManualToneTimeline` đang được `ui/dialogs/songs_list.py:1,28` import qua `backend`). |
| Hook ghi | `frontend_qt.py` — trong `on_score_ready` (dòng 850-857) | Sau khi result hợp lệ: `add_entry(...)`; lấy `prev = get_stats(...)` TRƯỚC khi add để tính delta, nhét `result["history_delta"]` + `result["history_best"]` vào dict trước khi emit `_score_report_signal`. |
| Test | `tests/core/test_score_history.py` (MỚI) | add/get/stats/cap/atomic. |

#### Phase 2.2 — UI tiến bộ (≈2 ngày)

| Việc | File | Chi tiết |
|---|---|---|
| Delta trong report | `ui/dialogs/scoring_report.py` — `_build_header()` dòng 75-114 | Dưới ngôi sao: label "So với lần trước: ▲ +3.2" (xanh `C["green"]`) / "▼ −1.5" (cam) / "Lần đầu hát bài này 🎉", đọc `result["history_delta"]`. |
| Sparkline widget | `ui/components/score_sparkline.py` (MỚI) | `ScoreSparkline(QWidget)` QPainter ~120×28px: polyline điểm các lần hát (tối đa 15 điểm gần nhất), chấm cuối to hơn, gradient theo `C["primary"]`. |
| Badge trong songs list | `ui/dialogs/songs_list.py` — `_build_song_card()` dòng 104-164 | Sau dòng 143: nếu `get_stats(video_id)['count']>0` → thêm `"  |  🏆 {best:.0f} ({count} lần)"` + `ScoreSparkline` nhỏ; thêm nút thứ 4 icon 📈 (thêm `SVG_CHART` vào `ui/components/svg_icons.py`) mở dialog lịch sử. |
| Dialog lịch sử bài | `ui/dialogs/score_history.py` (MỚI) | `ScoreHistoryDialog(parent, song)`: header tên bài + best/count/trend; sparkline to; danh sách cuộn các lần hát theo layout card của `songs_list.py:104`; footer nút Đóng. Đăng ký vào `ui/dialogs/__init__.py`. |
| Khi chưa từng hát | `ui/dialogs/score_history.py` | Empty-state theo mẫu `_build_empty_state` (`songs_list.py:76-102`). |

**Điểm tích hợp:** không thêm nút mới ở dashboard chính — vào qua danh sách "Lịch sử" bài hát sẵn có (`frontend_qt.py:1363`) và qua dialog kết quả chấm điểm.

### Phụ thuộc mới

Không có. JSON + QPainter thuần.

### Rủi ro & cách giảm

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| `current_youtube_url` là None lúc chấm | Trung | Vẫn ghi entry với `video_id="unknown"` + title từ marquee; chỉ hiện ở "gần đây", không gắn bài. |
| Ghi đồng thời từ thread chấm điểm + GUI | Thấp | Module lock + atomic write (pattern `core/songs.py`). |
| File history hỏng/corrupt | Thấp | Load lỗi → trả `{"version":1,"entries":[]}` và backup file hỏng thành `.bak`. |
| Songs list chậm khi nhiều entry | Thấp | `get_stats` đọc file 1 lần cho cả dialog (load once, group theo video_id). |

### Tiêu chí nghiệm thu

1. Chấm điểm xong → entry xuất hiện trong `score_history.json` (đúng schema, atomic), còn nguyên sau restart app.
2. Hát cùng bài lần 2 → dialog kết quả hiện delta so lần trước chính xác.
3. Danh sách bài hát hiện "🏆 best (n lần)" + sparkline cho bài đã hát; bài chưa hát hiển thị như cũ.
4. Nút 📈 mở dialog lịch sử với đầy đủ các lần hát, sắp xếp mới nhất trước.
5. Vượt 1000 entries → entry cũ nhất bị cắt, file không phình vô hạn.
6. Xóa bài trong `saved_songs.json` KHÔNG xóa lịch sử điểm (độc lập theo video_id).

### Ước lượng effort

| Phase | Ngày công |
|---|---|
| 2.1 Storage + hook | 1 |
| 2.2 UI (delta, sparkline, badge, dialog) | 2 |
| Test + polish | 0.5 |
| **Tổng Feature 2** | **≈ 3.5 ngày** |

---

## Thứ tự triển khai khuyến nghị

1. **Phase 2.1** trước (1 ngày, độc lập, ghi được lịch sử ngay cả với điểm legacy hiện tại — có data thật để test Feature 2).
2. Phase 1.1 → 1.2 → 1.3 (lõi chấm thật).
3. Phase 1.4 + 2.2 song song (cùng là UI QPainter).
4. Phase 1.5 chốt.

**Tổng cộng: ≈ 16 ngày công** (1 dev, đã gồm test).

---

### File quan trọng khi triển khai

- `core/scoring.py`
- `recorder_worker.py`
- `core/engine/_recording.py`
- `ui/dialogs/scoring_report.py`
- `ui/dialogs/songs_list.py`
