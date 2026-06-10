# Plan: Timeline Tone, AutoKey & Đồng bộ YouTube

> Tài liệu kế hoạch triển khai cho 4 tính năng: (1) UI timeline tone + sửa tay, (2) Giảm trễ AutoKey, (3) Đồng bộ pause/seek YouTube + hàng đợi bài hát, (4) Mã hoá cookie YouTube bằng DPAPI.
> Phạm vi: app desktop PySide6 tại `D:\Projects\LiveStudio\quang-luu-studio`. Mọi trích dẫn `file:dòng` đã được đối chiếu trực tiếp với mã nguồn hiện tại (2026-06-10).

---

## Tổng quan kiến trúc hiện tại (đã khảo sát)

| Thành phần | File | Ghi chú |
|---|---|---|
| Engine mixins | `core/engine/__init__.py` (`SystemEngine`), `_tone.py`, `_autokey.py`, `_youtube.py`, `_session.py` | `cdp_monitor` khởi tạo tại `core/engine/__init__.py:57-58`, `_tone_session` tại `:66` |
| Replay timeline | `core/engine/_autokey.py:410` (`_replay_cached_timeline`), `:477` (`_replay_manual_timeline`) | Cả hai **đã** poll vị trí player thật qua CDP/WinRT mỗi 0.1s |
| Cache & manual timeline | `core/tone_cache.py` (`ToneCacheManager`, `ManualToneTimeline`) | File JSON tại `DATA_DIR` (`core/config.py:71-72`) |
| CDP monitor | `core/cdp_monitor.py` | Poll `getCurrentTime() / getPlayerState() / getDuration() / location.href` mỗi `CDP_POLL_INTERVAL = 0.1s` (`core/config.py:340`) |
| Resolve thứ tự tone | `core/engine/_tone.py:89-109` (`_resolve_tone`) | Manual timeline **ưu tiên hơn** cache; có RAM-cache phiên (`_tone_resolve_cache_invalidate` `:118`) |
| UI dashboard | `frontend_qt.py` | Kết quả tone về main thread qua `_tone_result_signal` (`:89`, slot `_handle_tone_result` `:680`) |
| Editor timeline hiện có | `ui/dialogs/edit_song.py` (`EditSongDialog`) | Dạng bảng dòng `MM:SS + key combo`, lưu qua `ManualToneTimeline.save_timeline` (`:289`) |
| Cookie YouTube | `core/ytdlp_support.py` | `_AUTO_COOKIE_FILE = DATA_DIR/youtube_cookies.txt` **plaintext** (`:19`) |

---

## Feature 1: UI timeline tone + sửa tay

### Mục tiêu
- Thanh timeline trực quan trên dashboard: các đoạn key của bài hát tô màu theo key/scale, marker vị trí phát hiện tại chạy theo player thật.
- Click vào một đoạn → đổi key/scale (hoặc kéo mốc thời gian) → lưu vào manual timeline theo video ID → ghi đè cache → replay áp dụng ngay không cần mở lại bài.

### Hiện trạng
- **Dữ liệu đã có đủ**:
  - Cache: `tone_cache.json` entry `{primary_key, key_timeline: [{time, key_display, key_index, scale, confidence}], cached_at}` — được ghi bởi `detect_tone_continuous` (`core/engine/_autokey.py:396-403`), `_save_tone_to_cache` (`core/engine/_tone.py:145-161`), `auto_detect_youtube_timeline` (`core/engine/_tone.py:594-603`).
  - Manual: `manual_timelines.json` dạng `{video_id: {url, title, timeline: [{time, key_display, key_index, scale}], updated_at}}`.
- **Replay hiện tại**: `_replay_cached_timeline` (`core/engine/_autokey.py:410-475`) và `_replay_manual_timeline` (`:477-541`) chạy thread riêng, mỗi 0.1s đọc `cdp_monitor.current_position` (fallback `media_monitor.current_position`), tra mốc bằng `ManualToneTimeline.get_entry_at_position` (`core/tone_cache.py:181-195`), gửi MIDI qua `_send_tone_midi` (`core/engine/_tone.py:167-194`) và bắn `on_tone_detected_callback` về UI. Cancel qua `ToneSession` (`core/engine/_session.py:31-44`).
- **UI hiện tại**: không có hình ảnh timeline. Marquee chỉ hiển thị chuỗi `Gm → A# → Cm…` (`frontend_qt.py:768-775`). `WaveformHeroPanel` có transport bar nhưng progress đang **hard-code 0.35** và time text giả `"2:34 / 4:12"` (`ui/components/waveform_hero.py:610, 630`); dashboard hiện đặt `self._waveform = None` (`frontend_qt.py:143`) — timeline bar phải là widget độc lập.
- **Sửa tay hiện tại**: chỉ qua dialog bảng `EditSongDialog` (`ui/dialogs/edit_song.py`), không trực quan, và sau khi lưu **không** tự áp dụng vào replay đang chạy.

### Kiến trúc đề xuất
```
┌─ frontend_qt.py (dashboard) ─────────────────────────────┐
│  ToneTimelineBar (widget mới, QWidget paintEvent)        │
│   ├─ data: list[entry] + duration  ← engine result/cache │
│   ├─ marker: QTimer 250ms đọc engine.cdp_monitor         │
│   ├─ click segment → SegmentEditPopup (key/scale/time)   │
│   └─ signal timeline_edited(list[entry])                 │
└──────────────────────────────────────────────────────────┘
            │ lưu                                ▲ replay highlight
            ▼                                    │ (entry có 'time')
ManualToneTimeline.save_timeline()      _tone_result_signal
            │
SystemEngine.apply_manual_timeline(url, entries)  ← API engine mới
  = _tone_resolve_cache_invalidate(url)
  + _tone_session.stop() → start_scanning(url) → transition_to_replaying()
  + _replay_manual_timeline(entries, cancel_event=...)
```
- **Một nguồn dữ liệu hiển thị duy nhất**: dashboard giữ `self._current_timeline` (list entry) + `self._current_video_url`, cập nhật từ `_handle_tone_result` (`frontend_qt.py:680`) — result đã chứa `key_timeline` (cache/fast-scan, `core/engine/_tone.py:138, 444-451`) hoặc `timeline` (full-scan/manual, `core/engine/_youtube.py:600-615`).
- **Ghi đè cache**: không cần xoá cache — `_resolve_tone` (`core/engine/_tone.py:97-101`) đã ưu tiên manual trước cache; chỉ cần invalidate RAM-cache phiên (`:118`).

### Các bước triển khai theo phase

**Phase 1 — Widget ToneTimelineBar (UI thuần, chưa tương tác)**
1. Tạo `ui/components/tone_timeline_bar.py`:
   - `class ToneTimelineBar(QWidget)`: `set_timeline(entries, duration)`, `set_position(seconds)`, `set_active_index(idx)`.
   - `paintEvent`: vẽ dải ngang; mỗi segment từ `entry[i].time` → `entry[i+1].time` (segment cuối → `duration`); màu theo `key_index` (bảng 12 màu từ `ui/design_tokens.py`, Major đậm / Minor nhạt); label key ở giữa segment nếu đủ rộng; marker vị trí là vạch dọc + đầu tròn.
   - `duration` lấy từ `engine.cdp_monitor.duration` (`core/cdp_monitor.py:208`); nếu 0 thì dùng `max(time) + 30s` tạm.
2. Gắn vào dashboard: thêm 1 hàng cao ~28px trong `_build_body` (`frontend_qt.py:319-334`), trên `top_dock`; ẩn khi chưa có timeline.
3. Cập nhật dữ liệu trong `_handle_tone_result` (`frontend_qt.py:680`):
   - Nhánh kết quả toàn bài (`'time' not in result`, `:767`): `set_timeline(result.get('timeline') or result.get('key_timeline'), engine.cdp_monitor.duration)`.
   - Nhánh sự kiện replay (entry có `'time'`): chỉ `set_active_index` để highlight segment đang phát.
4. Marker: `QTimer` 250ms (main thread) đọc `engine.cdp_monitor.current_position / duration / is_playing`, fallback `engine.media_monitor` (giống logic `_update_browser_status`, `frontend_qt.py:406-424`).

**Phase 2 — Sửa tay trên timeline**
5. `mousePressEvent`: hit-test segment → popup nhỏ (`QMenu` hoặc `QDialog` frameless): combo 24 key (`_ALL_KEYS` tái dùng từ `ui/dialogs/edit_song.py:13-16`), ô thời gian bắt đầu (MM:SS, parse bằng `ManualToneTimeline.parse_time_str`, `core/tone_cache.py:214-217`), nút "Tách đoạn tại vị trí phát", "Xoá mốc", "Mở editor đầy đủ…" (mở `EditSongDialog`).
6. Chuẩn hoá entry khi lưu: tách logic build entry của `EditSongDialog._on_save` (`ui/dialogs/edit_song.py:250-283`) thành hàm module-level `build_timeline_entry(time, key_display)` trong `core/tone_cache.py` để dialog và popup dùng chung.
7. Persist: `ManualToneTimeline.save_timeline(url, title, entries)` (`core/tone_cache.py:128-149`); cập nhật `SongManager.update_song(id, tone=entries[0].key_display)` nếu bài có trong danh sách (giống `edit_song.py:291-292`).

**Phase 3 — Áp dụng ngay vào replay (điểm tích hợp engine)**
8. Thêm method `apply_manual_timeline(self, url, entries)` vào `core/engine/_autokey.py`:
   ```
   self._tone_resolve_cache_invalidate(url)            # _tone.py:118
   self._tone_session.stop()                           # huỷ replay cũ (_session.py:40)
   self._send_tone_midi(entry hiện tại theo cdp position)  # áp key ngay
   self._tone_session.start_scanning(url)
   replay_cancel = self._tone_session.transition_to_replaying()
   if replay_cancel: self._replay_manual_timeline(entries, cancel_event=replay_cancel)
   ```
   Pattern sao chép đúng luồng replay manual sẵn có ở `core/engine/_youtube.py:381-389` và `core/engine/_tone.py:367-371` — không đổi state machine.
9. Frontend gọi `engine.apply_manual_timeline` trong handler `timeline_edited`; cập nhật lại `ToneTimelineBar.set_timeline`.
10. `EditSongDialog._on_save` (`ui/dialogs/edit_song.py:289-296`): sau khi lưu, nếu `engine.current_youtube_url` trùng video ID đang sửa → gọi `apply_manual_timeline` luôn.

### Phụ thuộc mới
Không có (PySide6 thuần).

### Rủi ro & cách giảm
- **Race giữa replay cũ và mới**: `ToneSession.stop()` set cancel event trước khi tạo session mới (cơ chế đã có, `_session.py:23-29`); thêm `cancel_event.wait(0.15)` ngắn trước khi start thread mới nếu cần.
- **Duration = 0 khi CDP chưa kết nối** → re-render khi duration thay đổi (timer 250ms đã có), lưu `duration` vào cache entry khi dò full (đã có field `duration` trong `_save_tone_to_cache`, `_tone.py:156`).
- **Timeline quá dày (cache 5s/segment, tới 500 entry — `_autokey.py:349-350`)**: merge các entry liên tiếp cùng `key_display` trước khi vẽ (giống logic merge trong `tone_detector.py:734-780`).
- **Callback replay từ worker thread đụng QWidget**: luôn route qua `_tone_result_signal` (pattern `frontend_qt.py:568-574`).

### Tiêu chí nghiệm thu
1. Mở bài có cache/manual timeline → thanh timeline hiện đúng số đoạn, đúng màu, marker chạy theo video (sai số ≤ 0.5s).
2. Pause video → marker đứng; seek → marker nhảy theo trong ≤ 0.5s.
3. Click đoạn, đổi `A#` → `Cm`, lưu → `manual_timelines.json` cập nhật đúng video ID; MIDI key đổi ngay nếu vị trí phát đang nằm trong đoạn đó; lần sau phát ra key mới không cần dò lại.
4. Sửa qua `EditSongDialog` khi bài đang phát → replay áp dụng ngay không cần mở lại bài.

### Ước lượng effort
**4–5 ngày công** (P1: 1.5, P2: 1.5, P3: 1, test/polish: 0.5–1).

---

## Feature 2: Giảm trễ AutoKey (adaptive analysis + hysteresis)

### Mục tiêu
Giảm độ trễ nhận chuyển key từ ~10–15s xuống mục tiêu **3–5s**, không tăng false-positive (flapping giữa 2 key, đặc biệt cặp relative major/minor).

### Hiện trạng (thuật toán thực tế trong `core/engine/_autokey.py`)
- `start_autokey(segment_duration=5)` (`:18`); mỗi vòng đọc đúng `RECORD_CHUNK = 5s` audio (`:77, :95-102`).
- **Buffer tích luỹ**: audio dồn vào ring buffer 30s (`MAX_BUFFER_SEC=30`, `:78-81, :126-133`) và `detect_key_from_audio` chạy trên **toàn bộ** `audio_buffer[:write_pos]` (`:136-138`) — sau phút đầu, mỗi lần dò là chroma trung bình của 30s gần nhất → key cũ "đè" key mới thêm ~10–15s ngoài voting.
- **Voting**: `VOTING_WINDOW = 3` (`core/tone_detector.py:53`), cần `vote_ratio >= 0.67` + điều kiện `confidence_diff > -KEY_CHANGE_THRESHOLD` (0.05, `tone_detector.py:50`) — logic tại `_autokey.py:149-168`.
- → Trễ lý thuyết tối thiểu khi đổi key thật: 2 segment × 5s = 10s (voting) + quán tính buffer 30s ⇒ thực tế thường 15s+.
- Logic giống hệt được lặp lại trong `detect_tone_continuous` (`_autokey.py:333-364`) — sửa phải áp cho cả hai.

### Kiến trúc đề xuất
1. **Tách cửa sổ phân tích khỏi chu kỳ đọc (hop ≠ window)**:
   - Ring buffer giữ nguyên, nhưng dò trên **cửa sổ trượt đuôi** `audio_buffer[max(0, write_pos - WINDOW*sr) : write_pos]` thay vì toàn buffer — xoá quán tính 30s.
   - Chế độ **ổn định (stable)**: hop = 3s, window = 9s.
   - Chế độ **cảnh giác (alert)**: hop = 1.5s, window = 5s.
2. **Máy trạng thái chuyển chế độ theo độ tin cậy**:
   - Vào *alert* khi: kết quả segment khác `current_key`, HOẶC `confidence` tụt > 0.08 so với trung bình trượt, HOẶC RMS vừa hồi sau khoảng lặng.
   - Về *stable* sau N=3 segment liên tiếp đồng thuận với `current_key`.
3. **Hysteresis chống flapping** (thay vote_ratio đơn thuần):
   - Chỉ đổi key khi: `K_consec = 2` segment **liên tiếp** cùng key mới (ở alert-mode 1.5s hop ⇒ ~3s), VÀ `confidence_new >= confidence_cur − KEY_CHANGE_THRESHOLD`, VÀ đã qua **dwell time tối thiểu 8s** kể từ lần đổi trước.
   - Cặp relative major/minor (`key_index` chênh 9 semitone — `RELATIVE_MINOR_OFFSET`, `tone_detector.py:47`) và key cách nhau quint: yêu cầu `K_consec = 3` + chênh confidence ≥ +0.03.
4. **Trích chung thành class tái sử dụng** `KeyChangeVoter` (file mới `core/key_voter.py`): `feed(result) -> (changed: bool, stable_key, mode)`; giữ state `recent`, `last_change_ts`, `mode`. Dùng ở cả `start_autokey` và `detect_tone_continuous` (xoá 2 bản copy logic `:149-168` và `:333-364`).

### Các bước triển khai theo phase

**Phase 1 — Refactor không đổi hành vi (0.5 ngày)**
1. Tạo `core/key_voter.py` với `KeyChangeVoter` tái hiện đúng logic hiện tại (window 3, ratio 0.67, threshold 0.05); thay vào `_autokey.py:149-168` và `:333-364`. Unit test mô phỏng chuỗi result giả (không cần audio).

**Phase 2 — Sliding window + hop (1 ngày)**
2. Trong `_autokey_loop`: thêm hằng `ANALYSIS_WINDOW_SEC`, `HOP_SEC` (đọc từ `AppConfig` với default, pattern như `CDP_POLL_INTERVAL` ở `core/config.py:340`); vòng đọc audio theo `HOP_SEC`; gọi `detect_key_from_audio` trên lát đuôi window thay vì `audio_buffer[:write_pos]` (`:136-138`).
3. Áp tương tự cho `detect_tone_continuous` (`elapsed += HOP` thay vì `segment_duration` — chú ý `key_timeline` entry `time` vẫn phải là mốc bắt đầu cửa sổ để replay đúng).

**Phase 3 — Adaptive mode + hysteresis (1 ngày)**
4. Bổ sung state machine stable/alert vào `KeyChangeVoter`; expose `voter.hop_sec` để vòng loop điều chỉnh.
5. Thêm dwell-time + luật relative-key; log mỗi quyết định (`[AUTOKEY] mode=alert voted=Cm consec=2/3 …`) phục vụ tinh chỉnh.
6. UI: payload `on_key_update` (`_autokey.py:173-187`) thêm field `mode` để dashboard hiển thị trạng thái "đang nghi ngờ đổi tone" (chấm vàng nhấp nháy trên `autokey_dot`).

**Phase 4 — Tinh chỉnh thực địa (0.5–1 ngày)**
7. Test với 5–10 bài có đổi tone thật (dữ liệu trong `manual_timelines.json` làm ground truth); đo độ trễ = thời điểm gửi MIDI − mốc `time` trong manual timeline; chỉnh các hằng.

### Phụ thuộc mới
Không có. (CPU: detect ~3 lần/9s thay vì 1 lần/5s, nhưng window 5–9s nhỏ hơn buffer 30s hiện tại → tổng CPU tương đương hoặc thấp hơn. Giữ nhịp `MemoryGuard.force_cleanup()` theo số segment như `:139-141`.)

### Rủi ro & cách giảm
- **Flapping tăng do window ngắn** → hysteresis dwell 8s + K_consec; luật riêng cho relative keys.
- **Đoạn rap/percussion confidence thấp** → alert-mode không tự đổi key khi `confidence < 0.15` (giữ key cũ, chỉ log).
- **Hồi quy `detect_tone_continuous` ghi cache sai mốc `time`** → unit test riêng cho mapping elapsed/hop; so sánh cache trước–sau trên cùng file audio mẫu.
- **Vỡ tương thích tests hiện có** → chạy suite trước khi merge.

### Tiêu chí nghiệm thu
1. Bộ bài test có đổi tone: trễ trung bình ≤ 5s, p95 ≤ 8s (đo bằng log so với ground truth manual timeline).
2. Bài **không** đổi tone 4 phút: 0 lần đổi key giả (chạy 3 lần).
3. Đoạn lặng/nói chuyện giữa bài không gây đổi key.
4. CPU trung bình của thread autokey không tăng quá 30% (đo bằng `MemoryProfiler` checkpoint sẵn có `:189`).

### Ước lượng effort
**3 ngày công** (+0.5 buffer tinh chỉnh).

---

## Feature 3: Đồng bộ pause/seek YouTube + hàng đợi bài hát

### Mục tiêu
- Mọi cơ chế theo thời gian (replay, kết thúc video) bám theo `currentTime` thật của player — pause/seek không làm lệch.
- Hàng đợi bài đã lưu: phát xong tự chuyển bài kế (auto-play-next).

### Hiện trạng
- **CDP đã đọc đủ dữ liệu**: script tại `core/cdp_monitor.py:189-202` trả `{time, state, duration, url}`; cập nhật `current_position`, `duration`, `is_playing = (state == 1)` tại `:207-213`. **`state == 0` (ended) và `state == 2` (paused) hiện bị vứt bỏ**.
- **Replay ĐÃ chạy theo player time**: `_replay_cached_timeline`/`_replay_manual_timeline` đọc `cdp_monitor.current_position` mỗi 0.1s, có xử lý seek-back (`elapsed < last_position - 2.0` → reset `last_idx`, `_autokey.py:441-446, 506-511`) và pause (`:432-435`). → Phần này cơ bản đạt yêu cầu.
- **Điểm dùng wall-clock cần thay**:
  1. `_start_youtube_monitoring` (`core/engine/_youtube.py:399-450`): lấy `duration` qua yt-dlp rồi **`time.sleep(duration + 5)`** (`:441-443`) để bắn `on_video_end` — pause 1 phút là báo kết thúc sớm 1 phút.
  2. `open_youtube_url` nhánh manual replay: **`time.sleep(3)`** chờ browser (`_youtube.py:383`) rồi gửi MIDI mốc đầu — nếu browser mở chậm, MIDI bắn trước khi nhạc phát.
- **Hàng đợi**: chưa có. `SongManager` (`core/songs.py`) chỉ là CRUD; `SongsListDialog._make_play` (`ui/dialogs/songs_list.py:179-202`) phát 1 bài.

### Kiến trúc đề xuất
```
CDPYouTubeMonitor (mở rộng)
  + player_state: int   (giữ nguyên giá trị YT: -1/0/1/2/3/5)
  + is_ended (state == 0)

SystemEngine._start_youtube_monitoring (viết lại)
  vòng poll 0.5s:
    - CDP connected → kết thúc khi player_state == 0
                      hoặc (duration>0 và position >= duration - 1.0 và !is_playing)
    - CDP không có  → fallback wall-clock như cũ (degraded)

core/playlist.py (mới): PlayQueue
  - queue: list[song], index, repeat/off
  - next()/peek()/clear()

Engine.play_queue + on_video_end → engine.play_next_in_queue()
  → open_youtube_url(next.url, manual_timeline=resolve…)
```

### Các bước triển khai theo phase

**Phase 1 — Video-end theo player thật (1 ngày)**
1. `core/cdp_monitor.py`: thêm `self.player_state = -1`, set trong `_monitor_loop` (`:207-213`); thêm `is_ended`. Không đổi API cũ.
2. Viết lại `monitor_video` trong `_start_youtube_monitoring` (`core/engine/_youtube.py:437-450`):
   - Vòng `while self.youtube_monitoring_active`, poll 0.5s.
   - Điều kiện kết thúc chính: `cdp_monitor.is_connected and player_state == 0` **và** URL tab vẫn là video đang theo dõi (so `extract_video_id(cdp_monitor.target_url)` — dùng `core/utils.extract_video_id` sẵn có).
   - Watchdog: nếu CDP mất kết nối > 60s → fallback đếm wall-clock như hiện tại (`duration + 5`), để PWA/WinRT-only vẫn hoạt động.
3. Sửa nhánh manual replay của `open_youtube_url` (`_youtube.py:381-389`): thay `time.sleep(3)` bằng `cdp_monitor.wait_for_playback(timeout=15)` (đã có sẵn, `cdp_monitor.py:234-240`; fallback `media_monitor.wait_for_playback`) rồi mới `_send_tone_midi(manual_timeline[0])`. Đồng thời **gọi `_start_youtube_monitoring(url)` cả ở nhánh manual** (hiện nhánh này không monitor video-end → auto-next không chạy cho bài có manual timeline nếu không sửa).

**Phase 2 — PlayQueue + auto-play-next (1 ngày)**
4. Tạo `core/playlist.py`: `PlayQueue` thread-safe (lock như `core/songs.py:15`), item là dict song. Engine giữ `self.play_queue` (khởi tạo trong `core/engine/__init__.py` cạnh `:57-66`).
5. Engine: method `play_song(song)` (gói logic của `SongsListDialog._make_play:180-193`) và `play_next_in_queue()`. Trong `on_video_end` (`_youtube.py:418-435`): sau nhánh quick-score, nếu queue còn bài → `play_next_in_queue()` (delay 2s); bắn callback UI cập nhật marquee/timeline bar.
6. Tương tác với YT watcher: `open_youtube_url` đã set `_last_watched_url = url` (`_youtube.py:314`) nên watcher (`:489-503`) không dò trùng — giữ nguyên.

**Phase 3 — UI hàng đợi (1 ngày)**
7. `ui/dialogs/songs_list.py`: thêm nút "➕ Hàng đợi" mỗi card (cạnh play/edit/del, `:146-163`); footer hiển thị số bài trong queue + "Phát hàng đợi" / "Xoá hàng đợi".
8. Dashboard: hiển thị "Tiếp theo: <title>" trên marquee hoặc badge nhỏ; auto-next route kết quả tone qua `_tone_result_signal` như luồng phát thường.

### Phụ thuộc mới
Không có.

### Rủi ro & cách giảm
- **YouTube autoplay của browser** chuyển bài trước app → khi queue active: nếu URL mới do watcher phát hiện ≠ bài kế trong queue trong vòng 5s sau video-end → bỏ qua watcher event; cân nhắc pause player qua CDP khi state==0.
- **`getPlayerState()==0` bắn sớm do buffering**: debounce — yêu cầu state 0 giữ qua 2 lần poll liên tiếp (1s).
- **PWA không có CDP**: fallback wall-clock giữ nguyên hành vi hiện tại, không tệ hơn.
- **`_send_command` đa luồng**: đã có khoá toàn trình `_lock` (`cdp_monitor.py:128-157`) — mọi lệnh CDP mới phải đi qua `_send_command`.

### Tiêu chí nghiệm thu
1. Phát bài có timeline, pause 30s giữa chừng → key MIDI không nhảy mốc; resume → đúng mốc.
2. Seek tới 2:30 → MIDI đổi sang key của mốc 2:30 trong ≤ 0.5s; seek lùi về 0:10 → key mốc đầu.
3. Pause 2 phút cuối bài → app **không** báo video-end sớm; video chạy hết → video-end bắn ≤ 2s sau khi player ended.
4. Queue 3 bài → tự chuyển hết; bài có manual timeline replay đúng; UI cập nhật theo từng bài.

### Ước lượng effort
**3 ngày công**.

---

## Feature 4: Mã hoá cookie YouTube bằng DPAPI

### Mục tiêu
`youtube_cookies.txt` không còn plaintext lâu dài trên đĩa; mã hoá at-rest bằng Windows DPAPI (per-user), migration tự động file cũ, vẫn tương thích yt-dlp (chỉ nhận file Netscape plaintext).

### Hiện trạng
- `core/ytdlp_support.py:19`: `_AUTO_COOKIE_FILE = os.path.join(DATA_DIR, "youtube_cookies.txt")` — **plaintext**.
- **Ghi**: `export_cookies_to_file` (`ytdlp_support.py:48-87`).
- **Đọc**: `_build_auth_attempts` (`:203-216`) thêm attempt `cookie_file` từ (a) `youtube_cookie_file` user config (set bởi `configure_youtube_cookies.bat`) hoặc (b) `_AUTO_COOKIE_FILE`; `_apply_auth` (`:255-256`) set `opts["cookiefile"]`.
- **Choke-point duy nhất**: mọi call đi qua `run_with_auth_fallback` (`:143-200`) — chỗ chèn decrypt/cleanup.
- `pywin32>=306` đã có → `win32crypt` sẵn dùng, **không thêm dependency**.

### Kiến trúc đề xuất
```
core/cookie_vault.py (mới)
  ENC_FILE   = DATA_DIR/youtube_cookies.dat      (DPAPI blob + magic "QLSCKV1\0")
  PLAIN_FILE = DATA_DIR/youtube_cookies.txt      (legacy, sẽ migrate)

  encrypt_to_vault(plaintext_bytes)  → CryptProtectData(..., entropy=APP_ENTROPY) → ghi atomic .dat
  read_vault() → bytes | None        → CryptUnprotectData
  migrate_legacy_plaintext()         → nếu .txt tồn tại: encrypt → xoá .txt (overwrite best-effort trước unlink)
  @contextmanager decrypted_cookie_file() → giải mã ra temp file
      (NamedTemporaryFile(delete=False, dir=DATA_DIR, prefix=".ck_", suffix=".tmp"))
      yield path → finally: overwrite 0-byte + os.remove
  cleanup_stale_temp()               → xoá .ck_*.tmp mồ côi (crash lần trước)
```
- **yt-dlp handoff**: trong `run_with_auth_fallback`, attempt kind mới `"cookie_vault"`: decrypt ra temp trước operation; xoá temp ngay trong `finally` của attempt.
- **Export**: `export_cookies_to_file` ghi tạm ra temp → `encrypt_to_vault` + xoá temp — plaintext chỉ tồn tại vài giây.
- `youtube_cookie_file` user chỉ định thủ công: giữ nguyên plaintext (file của user), nhưng thêm option import vào vault (`youtube_cookie_encrypt_import`, mặc định True) → copy vào vault, reset `youtube_cookie_file=""`, thông báo 1 lần.

### Các bước triển khai theo phase

**Phase 1 — Module vault + migration (1 ngày)**
1. Tạo `core/cookie_vault.py`; entropy cố định của app (hằng bytes — không phải bí mật, chỉ tránh decrypt nhầm blob app khác).
2. Gọi `migrate_legacy_plaintext()` + `cleanup_stale_temp()` lúc khởi động engine (`core/engine/__init__.py` gần `:57`) — chạy nền.
3. Unit test (`tests/test_cookie_vault.py`): round-trip, migration xoá file cũ, context manager xoá temp kể cả khi raise.

**Phase 2 — Tích hợp ytdlp_support (1 ngày)**
4. `_build_auth_attempts` (`:203-216`): chèn attempt `{"kind": "cookie_vault"}` vào vị trí hiện tại của `_AUTO_COOKIE_FILE`; bỏ nhánh đọc `.txt` trực tiếp.
5. `run_with_auth_fallback` (`:162-192`): với attempt vault:
   ```
   with cookie_vault.decrypted_cookie_file() as tmp_path:
       current_opts["cookiefile"] = tmp_path
       return operation(ydl)
   ```
   (xử lý ngay trong vòng for vì cần lifecycle, `_apply_auth` thuần set-opt không đủ).
6. `export_cookies_to_file` (`:48-87`): output ra temp → encrypt → xoá; cập nhật message lỗi `_build_cookie_db_error_message` (`:322-332`).
7. `configure_youtube_cookies.bat`: thêm dòng thông báo cookie sẽ được import & mã hoá ở lần chạy kế.

**Phase 3 — Hardening + tài liệu (0.5 ngày)**
8. Temp file tạo trong `DATA_DIR` (cùng volume/ACL profile user); hidden; ghi đè zero trước unlink (best-effort — không chống forensic SSD, ghi rõ docstring).
9. Cập nhật `PROJECT_CONTEXT.md` / `Youtube Analyzer Guide.md` mục cookie.

### Phụ thuộc mới
Không (pywin32 đã có).

### Rủi ro & cách giảm (trung thực)
- **Rủi ro tồn dư cố hữu**: (a) trong lúc yt-dlp chạy, plaintext tạm tồn tại vài giây–vài chục giây; (b) DPAPI CurrentUser: process nào chạy cùng user đều decrypt được — DPAPI chỉ chống đọc offline/khác user/copy sang máy khác. Ghi rõ trong docs.
- **Crash để lại temp** → `cleanup_stale_temp()` khi khởi động + prefix `.ck_`.
- **User reset mật khẩu Windows** → blob không giải mã được → `read_vault()` None, fallback cookies-from-browser như hiện tại + log hướng dẫn export lại.
- **Hồi quy luồng auth**: giữ nguyên thứ tự attempt; test thủ công cả 3 nguồn (none / vault / browser).
- **Hai instance cùng decrypt** → tên temp ngẫu nhiên per-call.

### Tiêu chí nghiệm thu
1. Máy có `youtube_cookies.txt` cũ: chạy app → `.txt` biến mất, có `youtube_cookies.dat`; mở `.dat` không thấy cookie plaintext; dò tone bài bị bot-check vẫn thành công.
2. Trong khi dò tone: file `.ck_*.tmp` chỉ tồn tại lúc yt-dlp chạy, bị xoá ngay sau; kill app giữa chừng → lần mở sau temp mồ côi bị dọn.
3. Copy `.dat` sang máy/user khác → không giải mã được.
4. Vault hỏng → app vẫn hoạt động qua cookies-from-browser, log cảnh báo rõ.

### Ước lượng effort
**2–2.5 ngày công**.

---

## Thứ tự thực hiện đề xuất & tổng effort

| Thứ tự | Feature | Lý do | Effort |
|---|---|---|---|
| 1 | F4 — DPAPI cookie | Độc lập, rủi ro hồi quy thấp, đóng lỗ hổng bảo mật | 2–2.5 ngày |
| 2 | F3 — Đồng bộ pause/seek + queue | Nền tảng position/state cho marker của F1 | 3 ngày |
| 3 | F1 — UI timeline + sửa tay | Hưởng `player_state/duration` từ F3 | 4–5 ngày |
| 4 | F2 — Giảm trễ AutoKey | Cần thời gian tinh chỉnh thực địa nhiều nhất | 3–3.5 ngày |

**Tổng: ~12–14 ngày công** (1 dev, đã gồm test thủ công; chưa gồm build installer/regression toàn app ~1 ngày).

---

### File quan trọng khi triển khai
- `core/engine/_autokey.py` — thuật toán autokey, voting, 2 hàm replay timeline (F1, F2, F3)
- `core/engine/_youtube.py` — open_youtube_url, _start_youtube_monitoring (wall-clock cần thay), YT watcher (F3)
- `core/cdp_monitor.py` — nguồn currentTime/playerState/duration, cần expose player_state (F1, F3)
- `core/ytdlp_support.py` — choke-point cookie attempts/run_with_auth_fallback cho DPAPI vault (F4)
- `frontend_qt.py` — _handle_tone_result, signals, điểm gắn ToneTimelineBar (F1)
