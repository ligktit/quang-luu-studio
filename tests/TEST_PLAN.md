# Unit Test Plan — Quang Lưu Studio

**Ngày:** 2026-04-24  
**Framework:** `pytest` + `pytest-mock` + `pytest-qt`  
**Tổng modules cần test:** 15 module Python

---

## 1. Cấu trúc thư mục test

```
tests/
├── TEST_PLAN.md          (file này)
├── conftest.py           (fixtures dùng chung)
├── core/
│   ├── test_activation.py
│   ├── test_config.py
│   ├── test_utils.py
│   ├── test_songs.py
│   ├── test_tone_cache.py
│   ├── test_tone_detector.py
│   ├── test_midi.py
│   ├── test_memory.py
│   ├── test_recorder.py
│   ├── test_scoring.py
│   ├── test_ytdlp_support.py
│   └── test_engine.py
├── ui/
│   ├── test_design_tokens.py
│   └── test_panels.py
└── test_detect_youtube.py
```

---

## 2. Quy tắc chung

| Nguyên tắc | Lý do |
|---|---|
| Mock tất cả I/O ngoài (file, mido, pyaudio, yt-dlp, WinRT) | Tests phải chạy offline, không cần thiết bị MIDI hoặc YouTube |
| Dùng `tmp_path` của pytest cho file tạm | Tránh ô nhiễm trạng thái giữa các tests |
| Không test `frontend_qt.py` + Painter widgets bằng unit test | Qt rendering cần `pytest-qt` và màn hình — để integration test riêng |
| Test `core/engine.py` ở mức unit (mock thread, mock midi) | Engine quá nặng để chạy end-to-end trong unit test |
| AAA pattern: Arrange → Act → Assert | Dễ đọc, dễ maintain |

---

## 3. Test fixtures (conftest.py)

```python
# tests/conftest.py

@pytest.fixture
def tmp_config(tmp_path):
    """app_config.json tạm với giá trị mặc định."""

@pytest.fixture
def tmp_settings(tmp_path):
    """settings.json tạm."""

@pytest.fixture
def sample_tone_result():
    """Dict tone result chuẩn để tái sử dụng."""
    return {
        "tone": "D Major", "key_idx": 2, "scale": "Major",
        "confidence": 0.87, "key_midi": 23, "scale_midi": 13
    }

@pytest.fixture
def sample_song():
    return {
        "id": 1, "title": "Test Song",
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "tone": "C Major", "date_added": "2026-04-24 10:00:00"
    }

@pytest.fixture
def mock_midi_handler(mocker):
    """MidiHandler với mido bị mock."""
    mocker.patch("mido.open_output")
    mocker.patch("mido.get_output_names", return_value=["QuangLuuMIDI"])
```

---

## 4. Module: `core/utils.py`

**Hàm cần test:** `find_ffmpeg()`, `extract_video_id(url)`

### 4.1 `extract_video_id(url)`

| # | Test case | Input | Expected |
|---|---|---|---|
| U-01 | URL dạng watch?v= | `https://www.youtube.com/watch?v=dQw4w9WgXcQ` | `"dQw4w9WgXcQ"` |
| U-02 | URL dạng youtu.be/ | `https://youtu.be/dQw4w9WgXcQ` | `"dQw4w9WgXcQ"` |
| U-03 | URL dạng embed/ | `https://www.youtube.com/embed/dQw4w9WgXcQ` | `"dQw4w9WgXcQ"` |
| U-04 | URL dạng shorts/ | `https://www.youtube.com/shorts/dQw4w9WgXcQ` | `"dQw4w9WgXcQ"` |
| U-05 | URL có thêm params | `https://youtu.be/dQw4w9WgXcQ?t=42` | `"dQw4w9WgXcQ"` |
| U-06 | URL không phải YouTube | `https://vimeo.com/123456` | `None` hoặc `""` |
| U-07 | Video ID ngắn hơn 11 ký tự | `https://youtu.be/abc` | `None` hoặc `""` |
| U-08 | Chuỗi rỗng | `""` | `None` hoặc `""` |

### 4.2 `find_ffmpeg()`

| # | Test case | Setup | Expected |
|---|---|---|---|
| U-09 | ffmpeg có trong PATH | Mock `shutil.which` trả về path | Trả về đúng path |
| U-10 | ffmpeg không tồn tại | Mock tất cả lookups trả về None | Trả về `None` |
| U-11 | ffmpeg tồn tại ở WinGet path | Mock os.path.exists cho WinGet path | Trả về WinGet path |

---

## 5. Module: `core/config.py`

**Classes:** `AppConfig`, `ConfigManager`  
**Hàm free:** `_get_app_dir()`, `_get_data_dir()`, `_get_recordings_dir()`

### 5.1 `AppConfig`

| # | Test case | Setup | Expected |
|---|---|---|---|
| C-01 | `load()` đọc file JSON hợp lệ | Tạo file JSON tạm | Config được merge với defaults |
| C-02 | `load()` khi file không tồn tại | Không tạo file | Trả về defaults, không raise exception |
| C-03 | `load()` file JSON bị hỏng (malformed) | Ghi nội dung không hợp lệ | Trả về defaults, log warning |
| C-04 | `get(key)` với key tồn tại | Config đã load | Trả về đúng giá trị |
| C-05 | `get(key, default)` với key không tồn tại | Config đã load | Trả về `default` |
| C-06 | `get_midi_cc()` | Config có `midi_cc` | Trả về dict CC |
| C-07 | `get_scale_values()` | Config đầy đủ | Trả về `{"major": int, "minor": int}` |
| C-08 | `get_key_midi_map()` | Config đầy đủ | Dict 12 keys C-B |
| C-09 | `get_scale_midi_map()` | Config đầy đủ | Dict Major/Minor |
| C-10 | `get_mode_midi_map()` | Config đầy đủ | Dict 5 modes |
| C-11 | `update(key, value)` + `save()` | tmp_path | File được ghi với giá trị mới |
| C-12 | `reload()` | Thay đổi file ngoài | Config phản ánh file mới |
| C-13 | Singleton: gọi 2 lần | — | Cùng object instance |

### 5.2 `ConfigManager`

| # | Test case | Setup | Expected |
|---|---|---|---|
| C-14 | `load_settings()` file tồn tại | File JSON hợp lệ | Dict settings đúng |
| C-15 | `load_settings()` file không tồn tại | Không có file | Dict rỗng hoặc defaults |
| C-16 | `save_settings(settings)` | Dict hợp lệ + tmp_path | File được ghi, có thể đọc lại |
| C-17 | Round-trip: save rồi load | — | Dữ liệu không thay đổi |

---

## 6. Module: `core/activation.py`

**Class:** `ActivationManager`

### 6.1 Validation code

| # | Test case | Input | Expected |
|---|---|---|---|
| A-01 | `_validate_code_structure()` đúng format | `"ABCD-EFGH-IJKL-MNOP-QRST"` | `True` |
| A-02 | Format thiếu segment | `"ABCD-EFGH-IJKL-MNOP"` | `False` |
| A-03 | Segment sai độ dài | `"ABC-EFGH-IJKL-MNOP-QRST"` | `False` |
| A-04 | Có ký tự đặc biệt | `"ABCD-EFG!-IJKL-MNOP-QRST"` | `False` |
| A-05 | `_verify_code_checksum()` checksum đúng | Code hợp lệ có MD5 correct | `True` |
| A-06 | `_verify_code_checksum()` checksum sai | Code bị sửa 1 ký tự | `False` |

### 6.2 Activation lifecycle

| # | Test case | Setup | Expected |
|---|---|---|---|
| A-07 | `is_activated()` khi chưa có file | File không tồn tại | `False` |
| A-08 | `is_activated()` sau khi activate | Gọi `activate(valid_code)` | `True` |
| A-09 | `is_expired()` license mới | `activation_timestamp` = now | `False` |
| A-10 | `is_expired()` license cũ 366 ngày | Timestamp 366 ngày trước | `True` |
| A-11 | `get_days_remaining()` còn 100 ngày | Timestamp 265 ngày trước | `100` (±1) |
| A-12 | `activate(code)` code hợp lệ | Mock checksum pass | Trả về `True`, file được ghi |
| A-13 | `activate(code)` code không hợp lệ | Code format sai | Trả về `False` |

### 6.3 Trial period

| # | Test case | Setup | Expected |
|---|---|---|---|
| A-14 | `start_trial()` | Chưa có trial | `trial_start` được ghi vào file |
| A-15 | `is_trial_active()` trong 3 ngày | `trial_start` = 1 ngày trước | `True` |
| A-16 | `is_trial_expired()` sau 3 ngày | `trial_start` = 4 ngày trước | `True` |
| A-17 | `get_trial_days_remaining()` | `trial_start` = 1 ngày trước | `2` (±1) |
| A-18 | `needs_activation()` — chưa activated, trial hết | — | `True` |
| A-19 | `needs_activation()` — đang trial | Trial còn 3 ngày | `False` |

---

## 7. Module: `core/songs.py`

**Class:** `SongManager`

| # | Test case | Setup | Expected |
|---|---|---|---|
| S-01 | `load_songs()` file rỗng | File `[]` | Trả về `[]` |
| S-02 | `load_songs()` file không tồn tại | Không có file | Trả về `[]` |
| S-03 | `add_song()` mới | Danh sách rỗng | Song được thêm, ID = 1 |
| S-04 | `add_song()` tiếp theo | Có 1 song ID=1 | Song mới ID = 2 |
| S-05 | `add_song()` update nếu URL đã có | URL trùng | Không tạo duplicate, update tone |
| S-06 | `get_song_by_id()` tồn tại | ID = 1 | Trả về đúng song dict |
| S-07 | `get_song_by_id()` không tồn tại | ID = 999 | `None` |
| S-08 | `delete_song()` tồn tại | ID = 1 | Song bị xóa khỏi danh sách |
| S-09 | `delete_song()` không tồn tại | ID = 999 | Không raise, danh sách không đổi |
| S-10 | `update_song()` trường title | ID = 1, title="New" | Title được cập nhật |
| S-11 | `save_songs()` + `load_songs()` round-trip | 3 songs | Dữ liệu khớp hoàn toàn |

---

## 8. Module: `core/tone_cache.py`

**Classes:** `ToneCacheManager`, `ManualToneTimeline`

### 8.1 `ToneCacheManager`

| # | Test case | Setup | Expected |
|---|---|---|---|
| TC-01 | `get_cached_tone()` chưa có cache | File rỗng | `None` |
| TC-02 | `get_cached_tone()` có cache còn hạn | Timestamp trong 30 ngày | Trả về dict tone |
| TC-03 | `get_cached_tone()` cache hết hạn (>30 ngày) | Timestamp 31 ngày trước | `None` |
| TC-04 | `save_tone()` | URL + tone_data | Entry được ghi vào file |
| TC-05 | `save_tone()` rồi `get_cached_tone()` | — | Round-trip thành công |
| TC-06 | `clear_cache()` | Có 3 entries | File được ghi với `{}` |
| TC-07 | URL có params bị strip | `?t=42&list=abc` | Lookup bằng video_id thuần |

### 8.2 `ManualToneTimeline`

| # | Test case | Setup | Expected |
|---|---|---|---|
| TC-08 | `time_str_to_seconds("01:30")` | — | `90` |
| TC-09 | `time_str_to_seconds("00:05")` | — | `5` |
| TC-10 | `seconds_to_time_str(90)` | — | `"01:30"` |
| TC-11 | `seconds_to_time_str(3661)` | — | `"61:01"` hoặc `"1:01:01"` |
| TC-12 | `get_entry_at_position()` giữa timeline | Timeline: [0s→C, 30s→D, 60s→G], pos=45s | Entry D |
| TC-13 | `get_entry_at_position()` trước entry đầu | pos=0 | Entry đầu tiên |
| TC-14 | `save_timeline()` + `load_timeline()` | URL + entries | Round-trip đúng |
| TC-15 | `delete_timeline()` | URL có timeline | Timeline bị xóa |
| TC-16 | `list_all_timelines()` | 2 URL có timeline | Trả về list 2 entries |

---

## 9. Module: `core/tone_detector.py`

**Class:** `ToneDetector` (static methods chính)

> **Lưu ý:** Các method liên quan đến audio capture (`detect_key_from_system_audio`, `detect_key_from_youtube`) cần mock librosa, sounddevice, yt-dlp.

### 9.1 Utility / Algorithm Methods (pure, không cần mock)

| # | Test case | Input | Expected |
|---|---|---|---|
| TD-01 | `key_index_to_midi(0)` — C | `key_idx=0, scale="Major"` | Giá trị MIDI từ config |
| TD-02 | `key_index_to_midi(7)` — G | `key_idx=7, scale="Major"` | Giá trị MIDI đúng |
| TD-03 | `scale_to_midi("Major")` | — | Giá trị `scale_values.major` |
| TD-04 | `scale_to_midi("Minor")` | — | Giá trị `scale_values.minor` |
| TD-05 | `_is_relative_pair()` C Major — A Minor (+9) | idx=0,Major, idx=9,Minor | `True` |
| TD-06 | `_is_relative_pair()` C Major — D Major | idx=0,Major, idx=2,Major | `False` |
| TD-07 | `_correlate_profiles()` trả về 24 values | chroma_avg 12-dim | `len(result) == 24` |

### 9.2 Main detection (mock librosa + sounddevice)

| # | Test case | Setup | Expected |
|---|---|---|---|
| TD-08 | `detect_key_from_audio()` C Major sine | Mock librosa.cqt trả về chroma C | Trả về `key_idx=0, scale="Major"` hoặc confident |
| TD-09 | `detect_key_from_audio()` audio rỗng | `np.zeros(44100)` | Không raise, trả về kết quả hoặc confidence thấp |
| TD-10 | `detect_key_from_system_audio()` | Mock sounddevice.rec | Gọi `detect_key_from_audio()` với data đúng |
| TD-11 | `detect_key_from_youtube()` | Mock yt-dlp download + librosa | Trả về tone result dict với các keys bắt buộc |
| TD-12 | `detect_timeline_advanced()` | Mock librosa, 3 segments | Trả về list entries với `time` và `key_idx` |

---

## 10. Module: `core/midi.py`

**Class:** `MidiHandler`

| # | Test case | Setup | Expected |
|---|---|---|---|
| M-01 | `connect()` tìm thấy port | Mock `mido.get_output_names` trả về `["QuangLuuMIDI"]` | `connected = True` |
| M-02 | `connect()` không tìm thấy port | Port list rỗng | Raise exception hoặc trả về `False` |
| M-03 | `send_cc(cc, value)` sau khi connect | Mock mido output | `mido.Message` được gửi với đúng cc/value |
| M-04 | `send_cc()` khi chưa connect | `connected = False` | Không raise, hoặc raise `RuntimeError` |
| M-05 | `send_cc(cc, value, channel=1)` | — | Message có `channel=1` |

---

## 11. Module: `core/memory.py`

**Classes:** `MemoryProfiler`, `MemoryGuard`

### 11.1 `MemoryProfiler`

| # | Test case | Setup | Expected |
|---|---|---|---|
| MM-01 | `checkpoint()` ghi log khi RAM tăng >20MB | Mock psutil trả về tăng 30MB | Log message chứa delta |
| MM-02 | `checkpoint()` không log khi RAM tăng <20MB | Delta = 2MB | Không log |
| MM-03 | `summary()` không raise | Sau 3 checkpoints | Không exception |

### 11.2 `MemoryGuard`

| # | Test case | Setup | Expected |
|---|---|---|---|
| MM-04 | `start()` + `stop()` | Mock engine + interval=0.1s | Thread daemon chạy rồi dừng clean |
| MM-05 | `force_cleanup()` | Mock gc, librosa cache | gc.collect() được gọi |
| MM-06 | `_cleanup_temp_files()` | Tạo files .wav/.m4a trong tmp_path | Files bị xóa |
| MM-07 | `get_status()` | Sau 1 cleanup | Trả về dict với `cleaned_count` |

---

## 12. Module: `core/scoring.py`

**Class:** `ScoringEngine`

| # | Test case | Setup | Expected |
|---|---|---|---|
| SC-01 | `load_audio_data()` numpy array | `np.zeros(44100)`, sr=44100 | `self.audio_data` được set |
| SC-02 | `load_audio()` từ file | Mock librosa.load | Trả về audio array |
| SC-03 | `analyze_pitch()` sau load_audio_data | Mock librosa.yin | `self.pitch_data` được set |
| SC-04 | `calculate_score()` perfect pitch | Mock pitch_data = target_notes đúng | `total_score >= 90` |
| SC-05 | `calculate_score()` pitch hoàn toàn sai | pitch_data lệch nhiều | `total_score < 50` |
| SC-06 | `calculate_score()` thiếu audio | Chưa gọi load | Raise hoặc trả về score = 0 |
| SC-07 | `_generate_feedback()` score ≥90 | — | `rank = "Excellent"` |
| SC-08 | `_generate_feedback()` score 70-89 | — | `rank = "Good"` |
| SC-09 | `_generate_feedback()` score <50 | — | `rank` chứa "Needs Practice" hoặc tương đương |
| SC-10 | `download_youtube_audio()` | Mock yt-dlp | Gọi yt-dlp với đúng URL, trả về path |
| SC-11 | `cleanup_temp_file()` | File tạm tồn tại | File bị xóa |

---

## 13. Module: `core/ytdlp_support.py`

**Hàm:** `make_ydl_opts`, `extract_info_with_auth`, `download_with_auth`, `run_with_auth_fallback`, các helpers

| # | Test case | Setup | Expected |
|---|---|---|---|
| Y-01 | `make_ydl_opts()` default | — | Dict có `format`, `quiet` |
| Y-02 | `make_ydl_opts(**extra)` | `extra_opts={"noplaylist": True}` | Key extra được merge |
| Y-03 | `_is_bot_challenge()` exception YouTube bot | Exception message = "Sign in to confirm" | `True` |
| Y-04 | `_is_bot_challenge()` exception khác | Exception message thường | `False` |
| Y-05 | `_is_cookie_db_access_error()` | Locked DB exception | `True` |
| Y-06 | `_describe_auth()` không có auth | `auth = None` | Chuỗi "no auth" |
| Y-07 | `run_with_auth_fallback()` thành công lần 1 | Mock yt-dlp không raise | Operation được gọi 1 lần |
| Y-08 | `run_with_auth_fallback()` retry với cookies | Lần 1 bot challenge, lần 2 OK | Operation được gọi 2 lần |
| Y-09 | `run_with_auth_fallback()` thất bại tất cả | Mọi attempt đều raise | Raise `YouTubeAuthenticationRequiredError` |
| Y-10 | `_map_browser_path_to_cookie_source()` Edge | Path chứa "msedge" | Trả về `"edge"` |
| Y-11 | `_map_browser_path_to_cookie_source()` Chrome | Path chứa "chrome" | Trả về `"chrome"` |

---

## 14. Module: `core/engine.py` (SystemEngine)

> Tất cả tests đều mock: `MidiHandler`, `threading.Thread`, `subprocess`, `ToneDetector`, `AudioRecorder`

### 14.1 MIDI Methods

| # | Test case | Setup | Expected |
|---|---|---|---|
| E-01 | `connect_midi()` thành công | Mock MidiHandler.connect() OK | `is_midi_connected == True` |
| E-02 | `connect_midi()` thất bại 3 lần | Mock raise exception | Gọi `on_failed` callback |
| E-03 | `connect_midi()` thành công | — | Gọi `on_connected` callback |
| E-04 | `disconnect_midi()` | Connected | `is_midi_connected == False` |
| E-05 | `send_midi(cc, value)` | Connected | MidiHandler.send_cc được gọi với đúng args |
| E-06 | `send_midi()` khi disconnected, auto_reconnect=True | — | Thử connect lại trước khi send |
| E-07 | `register_midi_callback()` | — | Callback trong danh sách |
| E-08 | `unregister_midi_callback()` | Callback đã register | Callback bị remove |
| E-09 | `_handle_midi_in(cc, value)` | 2 callbacks đã register | Cả 2 callback được gọi |

### 14.2 URL Utilities

| # | Test case | Input | Expected |
|---|---|---|---|
| E-10 | `_normalize_url()` URL với www | `https://www.youtube.com/watch?v=abc` | URL chuẩn |
| E-11 | `_clean_youtube_url()` URL có list param | `?v=abc&list=PL123` | Chỉ còn `?v=abc` |
| E-12 | `_extract_key_root("D Major")` | — | `"D"` |
| E-13 | `_extract_key_root("C# Minor")` | — | `"C#"` |

### 14.3 Tone Detection Orchestration

| # | Test case | Setup | Expected |
|---|---|---|---|
| E-14 | `detect_tone()` gọi `on_complete` | Mock ToneDetector trả về result | `on_complete(result)` được gọi |
| E-15 | `detect_tone()` gọi `on_error` khi exception | Mock ToneDetector raise | `on_error(msg)` được gọi |
| E-16 | `stop_tone_detection()` | Detection đang chạy | Cancel event được set |
| E-17 | `_check_tone_cache(url)` cache hit | ToneCacheManager có entry | Trả về cached result |
| E-18 | `_check_tone_cache(url)` cache miss | Không có entry | `None` |
| E-19 | `_save_tone_to_cache(url, result)` | — | ToneCacheManager.save_tone được gọi |

### 14.4 Recording

| # | Test case | Setup | Expected |
|---|---|---|---|
| E-20 | `start_quick_score()` | Mock AudioRecorder | Recorder.start_recording được gọi |
| E-21 | `stop_quick_score()` | Đang record | Recorder.stop_recording được gọi, score được tính |
| E-22 | `stop_quick_score(cancel=True)` | Đang record | Recorder dừng, không tính score |

### 14.5 YouTube Watcher

| # | Test case | Setup | Expected |
|---|---|---|---|
| E-23 | `start_youtube_watcher()` + `stop_youtube_watcher()` | Mock threading | Thread được start rồi stop |
| E-24 | `_normalize_url()` idempotent | Gọi 2 lần với cùng URL | Kết quả không đổi |

---

## 15. Module: `detect_youtube.py`

**Hàm:** `extract_video_id`, `_normalize_url`, `clean_video_url`, `get_browser_windows`

| # | Test case | Setup | Expected |
|---|---|---|---|
| DY-01 | `extract_video_id()` — trùng với utils | Các URL dạng chuẩn | Như U-01 đến U-08 |
| DY-02 | `clean_video_url()` | URL có `&list=...&index=2` | Chỉ giữ `?v=<id>` |
| DY-03 | `_normalize_url()` không thay đổi URL chuẩn | URL đã clean | Trả về URL nguyên vẹn |
| DY-04 | `get_browser_windows()` | Mock `win32gui.EnumWindows` | Trả về list HWNDs |

---

## 16. Module: `core/design_tokens.py`

| # | Test case | Expected |
|---|---|---|
| DT-01 | `lighten(color, factor)` trả về chuỗi | String hex hợp lệ (#RRGGBB) |
| DT-02 | `darken(color, factor)` trả về chuỗi | String hex hợp lệ (#RRGGBB) |
| DT-03 | `lighten` + `darken` inverse nhau | `lighten(darken(c, 0.5), 0.5) ≈ c` |
| DT-04 | `C` dict có đủ keys | Có `bg`, `primary`, `text`, `border` |
| DT-05 | `SP` dict có đủ breakpoints | Có `XS`, `SM`, `MD`, `LG`, `XL` |

---

## 17. Setup cài đặt

### requirements (test)

```txt
pytest>=7.0
pytest-mock>=3.12
pytest-qt>=4.3      # cho UI tests sau này
pytest-cov>=4.0
numpy>=1.24
```

### Cài đặt

```bash
pip install pytest pytest-mock pytest-cov
pytest tests/ -v --cov=core --cov-report=term-missing
```

### Chạy từng module

```bash
pytest tests/core/test_utils.py -v
pytest tests/core/test_activation.py -v
pytest tests/core/test_engine.py -v -k "midi"  # chỉ chạy tests MIDI
```

### Coverage target

| Module | Target coverage |
|---|---|
| `core/utils.py` | 100% |
| `core/activation.py` | 95% |
| `core/config.py` | 90% |
| `core/songs.py` | 100% |
| `core/tone_cache.py` | 90% |
| `core/tone_detector.py` (pure logic) | 80% |
| `core/midi.py` | 85% |
| `core/scoring.py` | 80% |
| `core/ytdlp_support.py` | 85% |
| `core/engine.py` | 70% |
| `design_tokens.py` | 100% |

---

## 18. Thứ tự implement

```
Sprint 1 (Pure logic, không cần mock):
  → test_utils.py       (U-01..U-11)
  → test_config.py      (C-01..C-17)
  → test_design_tokens.py (DT-01..DT-05)

Sprint 2 (File I/O với tmp_path):
  → test_activation.py  (A-01..A-19)
  → test_songs.py       (S-01..S-11)
  → test_tone_cache.py  (TC-01..TC-16)

Sprint 3 (Cần mock external libs):
  → test_midi.py        (M-01..M-05)
  → test_scoring.py     (SC-01..SC-11)
  → test_ytdlp_support.py (Y-01..Y-11)
  → test_memory.py      (MM-01..MM-07)

Sprint 4 (Complex orchestration):
  → test_tone_detector.py (TD-01..TD-12)
  → test_engine.py      (E-01..E-24)
  → test_detect_youtube.py (DY-01..DY-04)
```

---

*Tổng: 149 test cases trên 15 modules*
