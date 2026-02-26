# 📋 QUANG LƯU STUDIO - Project Context

> **Cập nhật lần cuối:** 2026-02-25  
> **Loại ứng dụng:** Desktop App (Windows)  
> **Ngôn ngữ:** Python  
> **GUI Framework:** CustomTkinter (Dark mode)  
> **Build:** PyInstaller → EXE  

---

## 1. 🏗️ Kiến trúc tổng quan

Ứng dụng hỗ trợ ca sĩ/phòng thu (LiveStudio) với các tính năng:
- **Điều khiển MIDI** → Gửi CC messages đến Studio One (DAW)
- **Dò Tone bài hát** (AutoKey) → Tự động nhận diện key/scale từ audio (loopback hoặc YouTube)
- **Chấm điểm hát** → Phân tích pitch/volume từ audio
- **Quản lý bài hát** → Lưu/load danh sách bài hát + tone
- **YouTube integration** → Mở video, tự động dò tone, chấm điểm khi kết thúc
- **Hệ thống Activation** → License theo mã kích hoạt (hết hạn sau 365 ngày)

### Mô hình MVC đơn giản:
```
main.py          → Entry point, điều hướng flow
backend.py       → Model + Controller (business logic)
frontend.py      → View (GUI)
```

---

## 2. 📁 Cấu trúc thư mục

```
quang-luu-studio/
├── main.py                 # Entry point (31 dòng)
├── backend.py              # Backend logic (2116 dòng, ~93KB)
├── frontend.py             # GUI (2059 dòng, ~81KB)
├── generate_code.py        # Script tạo activation code (130 dòng)
├── requirements.txt        # Dependencies
├── settings.json           # Cấu hình user (studio_one_path, browser_path)
├── activation.json         # Thông tin activation (code, ngày, timestamp)
├── activation_codes.txt    # Danh sách codes đã tạo
├── main.spec               # PyInstaller spec (hiddenimports: mido.backends.rtmidi)
├── build.bat               # Script build EXE trên Windows
├── build.sh                # Script build EXE trên Linux/Mac
├── BUILD.md                # Hướng dẫn build
├── log.txt                 # Log output
├── ffmpeg.exe              # FFmpeg binary (~84MB) cho xử lý audio
├── test_loopback_diag.py   # Test loopback audio
├── test_tone_youtube.py    # Test dò tone từ YouTube
├── test_output.txt         # Kết quả test
├── temp_audio/             # Thư mục audio tạm (download YouTube)
├── build/                  # PyInstaller build artifacts
├── dist/                   # EXE output
├── .venv/                  # Virtual environment
└── __pycache__/            # Python cache
```

---

## 3. 📦 Dependencies (requirements.txt)

| Package | Mục đích |
|---------|----------|
| `librosa>=0.10.0` | Phân tích audio, dò pitch/chroma/key |
| `numpy>=1.24.0` | Xử lý mảng số |
| `soundfile>=0.12.0` | Đọc file audio |
| `yt-dlp>=2023.10.0` | Tải audio từ YouTube |
| `ffmpeg-python>=0.2.0` | Xử lý audio (cần ffmpeg.exe) |
| `customtkinter>=5.0.0` | GUI framework (Dark mode) |
| `mido>=1.2.10` | MIDI messages |
| `python-rtmidi>=1.5.0` | MIDI I/O |
| `pyautogui>=0.9.54` | Automation (hotkey) |
| `pywin32>=305` | Windows API (win32gui, win32con) |
| `psutil>=5.9.0` | Quản lý process |
| `soundcard>=0.4.2` | Loopback audio capture (WASAPI) |

---

## 4. 🔄 Luồng khởi động (main.py)

```
main()
  ├── 1. Kiểm tra activation (ActivationManager.needs_activation())
  │     ├── Chưa kích hoạt → Hiện ActivationDialog → callback main()
  │     └── Hết hạn → Hiện ActivationDialog (is_expired=True)
  │
  ├── 2. Load settings (ConfigManager.load())
  │     ├── Có settings → MainDashboard(settings)
  │     └── Chưa có → SetupView(callback=main)
  │
  └── 3. Hiện giao diện chính (MainDashboard)
```

---

## 5. 🔧 Backend (backend.py) - Chi tiết các Class

### 5.1 ConfigManager (static, Line 44-64)
Quản lý file `settings.json`:
- `load()` → Đọc settings, trả về dict hoặc None
- `save(s1, web, auto_launch_studio_one, midi_port_name)` → Lưu settings

**Format settings.json:**
```json
{
    "studio_one_path": "path/to/studio_one.exe",
    "browser_path": "path/to/browser.exe",
    "auto_launch_studio_one": false,
    "midi_port_name": "QuangLuuMIDI"
}
```

### 5.2 MidiHandler (Line 67-104)
Quản lý kết nối và gửi MIDI:
- `__init__()` → Khởi tạo, tự động connect
- `connect()` → Mở port `"QuangLuuMIDI"` qua mido (virtual port)
- `send_cc(cc_number, value, channel=0)` → Gửi MIDI Control Change

### 5.3 ToneCacheManager (static, Line 108-197)
Cache kết quả dò tone theo YouTube video ID:
- **File:** `tone_cache.json`
- **TTL:** 30 ngày
- **Min confidence:** 0.3
- `_extract_video_id(url)` → Trích xuất video ID từ YouTube URL
- `get_cached_tone(url)` → Tra cứu cache, kiểm tra TTL
- `save_tone(url, result)` → Lưu kết quả (primary_key, key_timeline, url)

### 5.4 SystemEngine (Line 199-1055) ⭐ Core Class
Engine chính điều khiển mọi thứ:

**Khởi tạo:**
- `settings`, `midi_handler` (MidiHandler)
- YouTube monitoring state, tone detection state, AutoKey state
- MIDI callbacks list

**MIDI:**
- `connect_midi(retry_count, delay, on_connected, on_failed)` → Wrapper kết nối
- `send_midi(cc, value, auto_reconnect)` → Wrapper gửi CC
- `register_midi_callback(callback)` / `unregister_midi_callback(callback)`
- `is_midi_connected()` / `get_midi_port_name()` / `disconnect_midi()`

**Hotkey & App:**
- `send_hotkey(keys)` → Gửi tổ hợp phím qua pyautogui (thread)
- `launch_app(path, is_web)` → Mở app bằng subprocess
- `kill_app()` → Tắt app

**YouTube:**
- `open_youtube_url(url, on_video_end_callback, on_tone_detected)` → Mở URL trong browser, auto dò tone, chấm điểm khi kết thúc
- `_start_youtube_monitoring(youtube_url)` → Theo dõi video: get duration (yt-dlp), monitor timer, gọi on_video_end khi hết

**Tone Detection:**
- `detect_tone(duration, on_complete, on_error, on_progress)` → Dò tone single-shot (kiểm tra cache trước)
- `_send_tone_midi(result)` → Gửi MIDI CC cho key/scale đến Auto-Tune
- `start_autokey(on_key_update, segment_duration)` → Dò tone liên tục (AutoKey mode)
  - Thu loopback liên tục, phân tích mỗi 5s
  - Voting window (3 segments) tránh nhảy tone
  - Confidence threshold (5%) chỉ chuyển khi chắc chắn  
- `stop_autokey()` → Dừng AutoKey
- `detect_tone_continuous(url, segment_duration)` → Dò tone liên tục suốt bài (cho YouTube monitoring)
- `_replay_cached_timeline(cached_data)` → Replay timeline tone từ cache (gửi MIDI đúng thời điểm)

### 5.5 SongManager (static, Line 1057-1120)
Quản lý danh sách bài hát (`saved_songs.json`):
- `load_songs()` / `save_songs(songs_list)`
- `add_song(title, url, tone)` → Thêm bài (tạo ID random)
- `delete_song(song_id)` / `get_song_by_id(song_id)`

### 5.6 ScoringEngine (Line 1122-1431)
Chấm điểm sau khi hát:
- `download_youtube_audio(youtube_url, output_dir)` → Tải audio qua yt-dlp
- `load_audio(file_path)` → Load audio bằng librosa
- `analyze_pitch()` → Phân tích pitch (piptrack)
- `calculate_score(target_notes, video_end)` → Tính điểm (random 77-100, ưu tiên điểm cao)
  - Metrics: pitch_accuracy, pitch_stability, volume_consistency, timing_accuracy
- `_generate_feedback(total_score, pitch_accuracy, pitch_stability)` → Tạo feedback text

### 5.7 ToneDetector (static, Line 1433-1932)
Dò tone bài hát - core algorithm:

**Pipeline:** HPSS → Chroma CQT (energy-weighted) → Weighted Multi-profile (Aarden/Temperley/KS) → Disambiguation

**Methods chính:**
- `_correlate_profiles(chroma_avg, major_profile, minor_profile)` → Tính correlation cho 24 keys
- `_is_relative_pair(key1, scale1, key2, scale2)` → Kiểm tra relative pair (C Major ↔ Am)
- `_are_closely_related(key1, scale1, key2, scale2)` → Kiểm tra closely related keys
- `detect_key_from_audio(audio_data, sample_rate, accumulated_chroma)` → Phát hiện key từ audio data
- `detect_key_from_system_audio(duration, sample_rate, on_progress)` → Thu loopback (WASAPI) + detect
- `detect_key_from_youtube(youtube_url, duration_limit)` → Tải từ YouTube + detect
- `key_index_to_midi(key_index)` → Key index (0-11) → MIDI CC (0-127)
- `scale_to_midi(scale)` → Scale → MIDI CC (0=Major, 127=Minor)

### 5.8 ActivationManager (static, Line 1934-2116)
Quản lý activation code:
- **License duration:** 365 ngày
- **Secret key:** `"QUANGLUU_STUDIO_2026_SECRET_KEY_CHANGE_THIS"`
- **Code format:** `XXXX-XXXX-XXXX-XXXX-XXXX` (4 nhóm + checksum)
- `_validate_code_structure(code)` → Kiểm tra format
- `_verify_code_checksum(code)` → Xác minh MD5 checksum
- `_validate_code(code)` → Validate toàn diện
- `load_activation()` / `save_activation(code)`
- `is_activated()` / `is_expired()` / `get_days_remaining()`
- `activate(code)` → Kích hoạt (validate + save)
- `needs_activation()` → Cần kích hoạt? (chưa activate hoặc đã hết hạn)

---

## 6. 🎨 Frontend (frontend.py) - Chi tiết các Class

### 6.1 Utility Functions (Line 1-62)
- `hex_to_rgb()`, `rgb_to_hex()`, `interpolate_color()` → Xử lý màu gradient

### 6.2 MIDI CC Mapping (Line 14-39)
```python
MIDI_CC = {
    # Sliders - Tone
    "tone_music": 10,       # Tone Nhạc
    "tone_voice": 11,       # Tone Giọng
    
    # Sliders - Mixer
    "mix_music": 20,        # Nhạc
    "mix_mic": 21,          # Mic
    "mix_reverb": 22,       # Vang
    "mix_backing": 23,      # Bè
    
    # Buttons - Tone Functions
    "do_tone": 30,          # Dò Tone
    "lay_tone": 31,         # Lấy Tone
    "tone_auto": 32,        # Tone Auto
    
    # Buttons - Mixer Functions
    "be": 40,               # Bè
    "vang": 41,             # Vang
    "nhac": 42,             # Nhạc
    "fix_meo": 43,          # Fix Méo
    
    # Auto-Tune Control
    "auto_tune_key": 34,    # Key gốc (0-127)
    "auto_tune_scale": 35,  # Scale type (0=Major, 127=Minor)
}
```

### 6.3 ScoringDialog (Line 63-199)
Dialog hiển thị kết quả chấm điểm:
- Điểm tổng (lớn, có màu theo mức)
- Chi tiết: Pitch Accuracy, Pitch Stability, Volume Consistency, Timing Accuracy
- Progress bar cho từng metric
- Thông tin bổ sung: pitch trung bình, độ lệch chuẩn, thời lượng
- Feedback text

### 6.4 ColorButton (Line 201-243)
Button custom với hiệu ứng hover/press:
- `on_enter()` → Sáng hơn 20%
- `on_leave()` → Về màu gốc
- `on_press()` → Tối hơn 20%
- `on_release()` → Về hover color

### 6.5 ActivationDialog (Line 246-416)
Dialog nhập activation code:
- Hiển thị khác nhau cho lần đầu vs hết hạn
- Input code + validate + feedback
- Bind Enter key

### 6.6 SetupView (Line 419-573)
Màn hình cấu hình ban đầu:
- Browse Studio One path (.exe/.song)
- Browse Browser path
- Checkbox "Tự động mở Studio One khi khởi động"
- Load existing settings nếu có

### 6.7 MainDashboard (Line 575-2053) ⭐ Giao diện chính

**Layout:** 1200x420px, always-on-top, grid 3 rows

```
┌─────────────────────────────────────────────────────────────┐
│ HEADER (Row 0): Tone Selector | AutoKey Indicator |         │
│   Marquee Text | Score Display | MIDI Status                │
├─────────────────────────────────────────────────────────────┤
│ MENU (Row 1): Buttons toolbar                               │
│   Dò Tone | Lấy Tone | Tone Auto | Bè | Vang | Nhạc |     │
│   Fix Méo | Lưu | Mở | Chấm điểm | Cấu hình | Lịch sử    │
├─────────────────────────────────────────────────────────────┤
│ BODY (Row 2): Sliders + Controls                            │
│   Tone Nhạc [-12,+12] | Tone Giọng [-12,+12]               │
│   Nhạc [0-100] | Mic [0-100] | Vang [0-100] | Bè [0-100]  │
│   + Mode selector (Đa Thể Loại, Bolero, Trữ Tình...)      │
└─────────────────────────────────────────────────────────────┘
```

**__init__() (Line 576-622):**
- Khởi tạo `backend.SystemEngine(settings)`
- State: tone_music_value, tone_voice_value, current_mode, is_recording, current_tone, current_score
- Toggle states: be_state, vang_state, autokey_active
- Setup header/menu/body
- Register MIDI callback, check connection, auto-launch Studio One

**Header (setup_header, Line 664-794):**
- Tone Selector (OptionMenu: C, Db, D... Cm, C#m, Dm...)
- AutoKey Live Indicator (ẩn khi chưa bật): đèn nhấp nháy + Key + Scale + Confidence
- Marquee scrolling text (bản quyền)
- Score display (điểm số hiện tại)
- MIDI status indicator (Đã kết nối / Chưa kết nối)

**Menu Toolbar (setup_menu, Line 837-895):**
- Buttons: Dò Tone, Lấy Tone, Tone Auto, Bè, Vang, Nhạc, Fix Méo
- Buttons: Lưu, Mở, Chấm Điểm
- Buttons: Cấu hình (→ SetupView), Lịch sử (→ songs list)

**AutoKey (on_do_tone, Line 898-999):**
- Toggle AutoKey on/off
- Khi bật: hiện indicator, start autokey, animate dot
- Khi tắt: ẩn indicator, stop autokey
- `_on_autokey_update(result)` → Schedule UI update via `after()`
- `_update_autokey_ui(result)` → Cập nhật Key, Scale, Confidence labels + update tone selector

**Toggle Buttons (Line 1009-1041):**
- `on_be()` → Toggle Bè: gửi MIDI CC 40 (127=on, 0=off)
- `on_vang()` → Toggle Vang: gửi MIDI CC 41 (127=on, 0=off)

**Tone Detection (Line 1044-1285):**
- `_start_tone_detection()` → Thu loopback 10s, hiện progress bar + dialog
- `_show_tone_result(result)` → Hiện dialog kết quả (Key, Scale, Confidence, Pitch Classes heatmap)

**Scoring (Line 1303-1553):**
- `on_score()` → Dialog chọn nguồn (File audio / YouTube URL)
- `_score_from_file()` → Browse file → process
- `_score_from_youtube()` → Nhập URL → download → process
- `_process_scoring(source, is_youtube)` → Chạy thread: load audio → analyze → calculate → show dialog

**Song Management (Line 1578-1797):**
- `_show_save_song_dialog()` → Dialog lưu bài (title, URL, tone)
- `_show_songs_list()` → Hiện danh sách bài đã lưu, play/delete

**Body Controls (setup_body, Line 1799-1957):**
- Tone controls: Tone Nhạc, Tone Giọng (nút +/-, range -12 to +12)
- Mixer sliders: Nhạc, Mic, Vang, Bè (range 0-100, gửi MIDI CC)
- Mode selector: Đa Thể Loại, Bolero, Trữ Tình, Nhạc Vàng, Pop

**Mode Selection (on_mode_selected, Line 2022-2053):**
- Mỗi mode preset khác nhau cho các slider (mix_music, mix_mic, mix_reverb, mix_backing)
- Gửi MIDI CC cho từng parameter

---

## 7. 🔗 Luồng hoạt động chính

### 7.1 Dò Tone (Single-shot)
```
User click "Dò Tone" → _start_tone_detection()
  → ToneDetector.detect_key_from_system_audio(10s)
      → WASAPI loopback capture 10s
      → detect_key_from_audio() pipeline
  → _show_tone_result(result)
      → Hiện dialog: Key, Scale, Confidence
      → User chọn gửi MIDI → engine._send_tone_midi()
```

### 7.2 AutoKey (Continuous)
```
User click "Dò Tone" (toggle) → on_do_tone()
  → engine.start_autokey(on_key_update, segment_duration=5)
      → Loop mỗi 5s:
          → Capture loopback 5s
          → detect_key_from_audio()
          → Voting window (3 segments)
          → Nếu key thay đổi → send MIDI CC
          → Callback → _update_autokey_ui()
```

### 7.3 YouTube Integration
```
User mở URL → engine.open_youtube_url(url, callbacks)
  → Mở browser
  → Kiểm tra cache (ToneCacheManager)
      → Có cache → replay_cached_timeline (gửi MIDI đúng thời điểm)
      → Không cache → detect_tone_continuous (dò tone live)
  → _start_youtube_monitoring()
      → get_video_duration (yt-dlp)
      → monitor_video timer
      → Khi hết video → on_video_end()
          → ScoringEngine.calculate_score()
          → Callback hiển thị kết quả
```

### 7.4 Chấm điểm
```
User click "Chấm điểm" → on_score()
  → Dialog chọn: File / YouTube
  → _process_scoring(source)
      → ScoringEngine.load_audio() hoặc download_youtube_audio()
      → analyze_pitch()
      → calculate_score() → Điểm 77-100 (random ưu tiên cao)
      → ScoringDialog hiển thị kết quả
```

---

## 8. 🎵 MIDI Integration

### Kết nối
- Sử dụng **mido** + **python-rtmidi**
- Tạo virtual MIDI port: `"QuangLuuMIDI"`
- Tự động reconnect mỗi 5s nếu mất kết nối

### CC Messages gửi đến Studio One
| CC | Parameter | Range | Mô tả |
|----|-----------|-------|--------|
| 10 | tone_music | 0-127 (mapped từ -12/+12) | Tone Nhạc |
| 11 | tone_voice | 0-127 (mapped từ -12/+12) | Tone Giọng |
| 20 | mix_music | 0-127 (mapped từ 0-100) | Volume Nhạc |
| 21 | mix_mic | 0-127 (mapped từ 0-100) | Volume Mic |
| 22 | mix_reverb | 0-127 (mapped từ 0-100) | Reverb |
| 23 | mix_backing | 0-127 (mapped từ 0-100) | Backing vocal |
| 30 | do_tone | 0/127 | Dò Tone toggle |
| 31 | lay_tone | 0/127 | Lấy Tone |
| 32 | tone_auto | 0/127 | Tone Auto |
| 34 | auto_tune_key | 0-127 | Key gốc → Auto-Tune |
| 35 | auto_tune_scale | 0/127 | Scale (0=Major, 127=Minor) → Auto-Tune |
| 40 | be | 0/127 | Bè toggle |
| 41 | vang | 0/127 | Vang toggle |
| 42 | nhac | 0/127 | Nhạc |
| 43 | fix_meo | 0/127 | Fix Méo |

---

## 9. 🔐 Hệ thống Activation

### Format code: `XXXX-XXXX-XXXX-XXXX-XXXX`
- 4 nhóm đầu: mỗi nhóm 2 chữ + 2 số (random)
- Nhóm 5: checksum MD5(base_code + SECRET_KEY)[:4]

### Flow:
1. `generate_code.py` → Tạo codes → `activation_codes.txt`
2. User nhập code → `ActivationManager.activate(code)`
   - Validate structure + checksum
   - Lưu `activation.json` (code, date, timestamp)
3. Mỗi lần mở app → `needs_activation()` kiểm tra:
   - Chưa activate → show dialog
   - Hết hạn (>365 ngày) → show dialog (is_expired)
   - OK → tiếp tục

---

## 10. 🔨 Build & Deploy

### Build EXE:
```bash
# ✅ Đúng: Build từ spec file
PyInstaller main.spec

# ❌ Sai: Sẽ ghi đè hiddenimports
PyInstaller --onefile main.py
```

### Hidden imports cần thiết:
```python
hiddenimports=['mido.backends.rtmidi']
```

### Files cần đi kèm EXE:
- `ffmpeg.exe` (xử lý audio YouTube)
- `settings.json` (tạo khi setup)
- `activation.json` (tạo khi activate)
- `saved_songs.json` (tạo khi lưu bài)
- `tone_cache.json` (tạo khi dò tone)

---

## 11. ⚠️ Lưu ý kỹ thuật

### numpy compatibility:
```python
# Patch numpy.fromstring TRƯỚC khi import soundcard
# soundcard dùng np.fromstring(binary) đã bị xóa trong numpy 2.x
```

### soundcard import:
```python
# Import soundcard ở module level (main thread) để COM init thành công
```

### Threading:
- Tone detection chạy trên thread riêng (không block GUI)
- YouTube monitoring chạy trên thread riêng
- MIDI send chạy trên thread riêng (cho hotkey)
- UI update phải qua `self.after()` (main thread only)

### Audio Processing:
- Loopback capture: WASAPI (Windows) qua `soundcard` library
- ToneDetector pipeline: HPSS → Chroma CQT → Multi-profile correlation → Disambiguation
- Scoring: Random 77-100, ưu tiên điểm cao (dựa vào volume stability)

---

## 12. 📊 File dữ liệu

| File | Format | Mô tả |
|------|--------|--------|
| `settings.json` | JSON | Cấu hình user |
| `activation.json` | JSON | Thông tin license |
| `saved_songs.json` | JSON | Danh sách bài hát |
| `tone_cache.json` | JSON | Cache kết quả dò tone (theo video ID, TTL 30 ngày) |
| `activation_codes.txt` | Text | Codes đã generate (admin tool) |

---

## 13. 🎯 Tóm tắt nhanh

> **Quang Lưu Studio** là ứng dụng desktop hỗ trợ ca sĩ/phòng thu, chạy trên Windows, sử dụng **CustomTkinter** (dark mode) cho giao diện. Ứng dụng kết nối với **Studio One** (DAW) qua **MIDI CC** để điều khiển tone, mixer, Auto-Tune. Tính năng nổi bật là **AutoKey** - dò tone tự động theo thời gian thực từ audio loopback (WASAPI), và tích hợp **YouTube** để phát nhạc, tự động nhận diện key/scale, chấm điểm sau khi hát. Có hệ thống **activation code** bảo vệ bản quyền (365 ngày). Build thành EXE bằng **PyInstaller**.
