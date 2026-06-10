# 📋 QUANG LƯU STUDIO - Project Context

> **Cập nhật lần cuối:** 2026-06-10  
> **Loại ứng dụng:** Desktop App (Windows)  
> **Ngôn ngữ:** Python  
> **GUI Framework:** PySide6 (Qt for Python, dark theme QSS)  
> **Build:** PyInstaller (`QuangLuuStudio.spec`) → EXE  

---

## 1. 🏗️ Kiến trúc tổng quan

Ứng dụng hỗ trợ ca sĩ/phòng thu (LiveStudio) với các tính năng:
- **Điều khiển MIDI** → Gửi CC messages đến Studio One (DAW) qua loopMIDI + Control Surface `QuangLuuMIDI`
- **Dò Tone bài hát** (AutoKey) → Tự động nhận diện key/scale từ audio (loopback hoặc YouTube)
- **Chấm điểm hát** → Phân tích pitch/volume từ audio
- **Quản lý bài hát** → Lưu/load danh sách bài hát + tone
- **YouTube integration** → Mở video, theo dõi qua CDP/WinRT Media, tự động dò tone, chấm điểm khi kết thúc
- **Ghi âm** → Subprocess `recorder_worker.py` (pyaudiowpatch WASAPI loopback)
- **Accessibility** → TTS (pyttsx3/SAPI5), voice command tiếng Việt offline (Vosk, model `models/vosk-vi/`), high contrast, focus announce
- **Hệ thống Activation** → License theo mã kích hoạt + trial
- **Auto-update** → `core/updater/` kiểm tra phiên bản mới (rate-limit 24h)

### Mô hình:
```
main.py          → Entry point: logging, DPI, activation gate, route Setup/Dashboard
backend.py       → Facade mỏng (~94 dòng): re-export từ core/ (lazy import PEP 562)
core/            → Business logic (package, tách module)
frontend_qt.py   → View chính PySide6 (~2.100 dòng): MainDashboard, SetupView, ActivationDialog
ui/              → Panels / dialogs / components Qt tách từ frontend_qt.py
```

---

## 2. 📁 Cấu trúc thư mục

```
quang-luu-studio/
├── main.py                  # Entry point: logging, excepthook, activation loop, update check
├── backend.py               # Facade mỏng — re-export core/ (SystemEngine, ToneDetector, ...)
├── frontend_qt.py           # GUI PySide6 (~2.100 dòng): MainDashboard, SetupView, ActivationDialog
├── recorder_worker.py       # Worker ghi âm chạy subprocess riêng (pyaudiowpatch)
├── detect_youtube.py        # Tool standalone: detect URL YouTube + phân tích key/BPM (tests dùng)
├── send_all_midi_keys.py    # Tool: gửi toàn bộ MIDI CC (đọc từ app_config.json) cho Studio One learn
├── close_browser_manual.py  # Tool thủ công: đóng cửa sổ/PWA YouTube (chỉ chạy trực tiếp)
├── sync_version.py          # Đồng bộ version vào core/version.py
├── core/                    # ⭐ Business logic package
│   ├── config.py            #   AppConfig/ConfigManager, đường dẫn %APPDATA%\QuangLuuStudio
│   ├── activation.py        #   ActivationManager (license + trial)
│   ├── midi.py              #   MidiHandler (mido + python-rtmidi, port "QuangLuuMIDI")
│   ├── tone_detector.py     #   ToneDetector (HPSS → Chroma CQT → multi-profile)
│   ├── tone_cache.py        #   ToneCacheManager + ManualToneTimeline
│   ├── scoring.py           #   ScoringEngine
│   ├── songs.py             #   SongManager
│   ├── recorder.py          #   AudioRecorder (điều khiển recorder_worker.py)
│   ├── cdp_monitor.py       #   Chrome DevTools Protocol monitor (websocket-client)
│   ├── media_monitor.py     #   WindowsMediaMonitor (WinRT Media Control)
│   ├── memory.py            #   MemoryProfiler / MemoryGuard
│   ├── logger.py / utils.py / version.py / ytdlp_support.py
│   ├── engine/              #   SystemEngine = composition các mixin:
│   │   ├── _lifecycle.py    #     khởi tạo / shutdown
│   │   ├── _midi.py         #     kết nối + gửi MIDI
│   │   ├── _tone.py         #     dò tone, cache, timeline
│   │   ├── _autokey.py      #     AutoKey liên tục
│   │   ├── _youtube.py      #     detect URL browser/PWA, watcher
│   │   ├── _recording.py    #     ghi âm + volume thiết bị (pycaw)
│   │   └── _session.py      #     phiên hát / chấm điểm
│   ├── accessibility/       #   announcer, speaker (TTS), voice_input (Vosk), shortcuts, theme
│   └── updater/             #   _version_check, _downloader, _verifier, _installer
├── ui/                      # ⭐ UI package (PySide6)
│   ├── design_tokens.py     #   màu / spacing / font tokens
│   ├── styles/main.qss      #   stylesheet
│   ├── panels/              #   header, mixer, tools, mode, bottom_bar
│   ├── dialogs/             #   settings_dialog, calibration, scoring_report, songs_list,
│   │                        #   edit_song, update_dialog, widget_builder
│   └── components/          #   painter_* (button/fader/knob/slider...), marquee, waveform_hero, svg_icons...
├── tools/                   # generate_code.py (tạo activation code), diagnose_*, batch_detect_tone,
│                            # enable/disable_cdp_flag.bat, export_youtube_cookies.bat
├── tests/                   # pytest (test_detect_youtube.py, ...)
├── models/vosk-vi/          # Model Vosk tiếng Việt (voice command offline)
├── studio_one/              # QuangLuuMIDI.surface.xml + deviceinfo.xml (Control Surface)
├── sfx/                     # Sound effects
├── Be_Vietnam_Pro/          # Font
├── app_config.json          # Config chương trình: MIDI CC map, key/scale map, accessibility
├── QuangLuuStudio.spec      # PyInstaller spec (datas, hiddenimports, Qt excludes)
├── build.bat / build_installer.bat
├── install_surface.bat      # Copy surface XML vào %APPDATA%\PreSonus\Studio One X
├── setup_all.bat            # Cài đặt tổng: loopMIDI + Surface + app
└── requirements.txt
```

> **User data** (settings.json, saved_songs.json, tone_cache.json, activation.json,
> manual_timelines.json, logs/) được tạo lúc runtime trong `%APPDATA%\QuangLuuStudio\`,
> KHÔNG bundle vào EXE.

---

## 3. 📦 Dependencies (requirements.txt)

| Package | Mục đích |
|---------|----------|
| `PySide6>=6.5` | GUI framework (Qt — KHÔNG phải PyQt5/CustomTkinter) |
| `mido>=1.3` + `python-rtmidi>=1.5` | MIDI I/O (port `QuangLuuMIDI`) |
| `pyaudiowpatch>=0.2.12` | WASAPI loopback capture (recorder_worker) |
| `sounddevice>=0.4` | Audio playback/capture |
| `librosa>=0.10,<1.0` | Phân tích audio, dò pitch/chroma/key (pin <1.0 — API beat.tempo) |
| `numpy>=1.24`, `scipy>=1.10` | Xử lý tín hiệu |
| `pycaw>=20240210` | Điều khiển âm lượng thiết bị Windows (core/engine/_recording.py) |
| `yt-dlp>=2024.1` | Tải audio/metadata YouTube |
| `websocket-client>=1.6` | CDP monitor (core/cdp_monitor.py) |
| `static_ffmpeg>=2.5` | Tự tải ffmpeg cho detect_youtube.py (tuỳ chọn) |
| `pywin32>=306` | Windows API (win32gui, win32con, win32process) |
| `pyautogui>=0.9` | Automation hotkey |
| `psutil>=5.9` | Quản lý process |
| `uiautomation>=2.0` | UI Automation (YT Watcher) |
| `winrt-Windows.Media.Control` + `winrt-Windows.Foundation` | Windows Media Monitor |
| `pyttsx3>=2.90` | TTS offline (SAPI5) — accessibility |
| `vosk>=0.3.45` | Voice command tiếng Việt offline (model `models/vosk-vi/`) |

---

## 4. 🔄 Luồng khởi động (main.py)

```
main()  — vòng lặp lifecycle (không đệ quy)
  ├── 0. Setup: DPI awareness, logging → %APPDATA%\QuangLuuStudio\logs\,
  │      excepthook (main + threads), cleanup _MEI khi thoát
  ├── 1. Activation gate (backend.ActivationManager.needs_activation())
  │     ├── Chưa kích hoạt / hết hạn / hết trial → ActivationDialog
  │     └── Trial còn hạn → log số ngày còn lại, đi tiếp
  ├── 2. Load settings (backend.ConfigManager.load_settings())
  │     ├── Có settings → MainDashboard(settings) + update check chạy nền
  │     └── Chưa có → SetupView (lưu xong quay lại vòng lặp)
  └── 3. Dashboard đóng → thoát (flush logs, _exit)
```

---

## 5. 🔧 Backend — `backend.py` facade + `core/` package

`backend.py` giờ chỉ là **facade ~94 dòng**: re-export class/constant từ `core/`
để code cũ (`import backend; backend.SystemEngine(...)`) vẫn chạy.
Symbol nhẹ (AppConfig, ConfigManager, ActivationManager, constants) import eager;
symbol nặng (SystemEngine, ToneDetector, AudioRecorder, ...) lazy qua PEP 562
`__getattr__` — import `backend` cho activation gate không kéo theo audio/MIDI stack.

### Các module chính trong `core/`:

| Module | Vai trò |
|--------|---------|
| `core.config` | ConfigManager/AppConfig — settings, đường dẫn `%APPDATA%\QuangLuuStudio\` |
| `core.activation` | ActivationManager — license + trial, format code `XXXX-XXXX-XXXX-XXXX-XXXX` |
| `core.midi` | MidiHandler — mở port `QuangLuuMIDI`, `send_cc()`, auto-reconnect |
| `core.engine` | **SystemEngine** ⭐ — composition từ các mixin `_lifecycle/_midi/_tone/_autokey/_youtube/_recording/_session` |
| `core.tone_detector` | ToneDetector — pipeline HPSS → Chroma CQT → multi-profile (Aarden/Temperley/KS) → disambiguation |
| `core.tone_cache` | ToneCacheManager (cache theo video ID) + ManualToneTimeline |
| `core.scoring` | ScoringEngine — phân tích pitch, tính điểm, feedback |
| `core.songs` | SongManager — saved_songs.json |
| `core.recorder` | AudioRecorder — điều khiển subprocess `recorder_worker.py` |
| `core.cdp_monitor` | Theo dõi tab YouTube qua Chrome DevTools Protocol (websocket) |
| `core.media_monitor` | WindowsMediaMonitor — WinRT Media Control (title/playback state) |
| `core.accessibility` | speaker (TTS), voice_input (Vosk push-to-talk Ctrl+Space), announcer, shortcuts, theme |
| `core.updater` | check version → download → verify → install |
| `core.memory` | MemoryProfiler / MemoryGuard |

---

## 6. 🎨 Frontend — `frontend_qt.py` + `ui/` package

`frontend_qt.py` (~2.100 dòng, PySide6) chứa các view chính:
- **ActivationDialog** — nhập activation code (lần đầu / hết hạn)
- **SetupView** — cấu hình ban đầu (Studio One path, browser, MIDI port)
- **MainDashboard** ⭐ — cửa sổ chính, compose từ các panel trong `ui/panels/`

Phần UI được tách dần sang package `ui/`:
- `ui/panels/` — `header` (tone selector, AutoKey indicator, marquee, score, MIDI status),
  `mixer` (faders Nhạc/Mic/Vang/Bè), `tools` (Dò Tone, Lấy Tone, ...), `mode`, `bottom_bar`
- `ui/dialogs/` — settings_dialog, calibration, scoring_report, songs_list, edit_song,
  update_dialog, widget_builder (import lazy — đã khai báo hiddenimports trong spec)
- `ui/components/` — custom-painted widgets: `painter_button/fader/knob/hslider/header/panel/record`,
  `marquee`, `waveform_hero`, `hmixer_channel`, `tabbed_dock`, `sfx_button_area`, `svg_icons`
- `ui/design_tokens.py` + `ui/styles/main.qss` — design tokens & stylesheet

UI update từ worker thread phải marshal về main thread qua Qt signal/`QTimer.singleShot`
(tương đương `after()` thời Tkinter).

---

## 7. 🔗 Luồng hoạt động chính

### 7.1 Dò Tone (Single-shot)
```
User click "Dò Tone" → engine (core/engine/_tone.py)
  → kiểm tra cache (ToneCacheManager) → nếu có: dùng luôn
  → ToneDetector.detect_key_from_system_audio()
      → WASAPI loopback capture → detect_key_from_audio() pipeline
  → hiện kết quả (Key, Scale, Confidence) → gửi MIDI key_root/key_scale
```

### 7.2 AutoKey (Continuous)
```
User bật AutoKey → engine.start_autokey() (core/engine/_autokey.py)
  → Loop: capture loopback theo segment
      → detect_key_from_audio()
      → Voting window tránh nhảy tone, threshold confidence
      → Key đổi → send MIDI CC → callback cập nhật UI (header panel)
```

### 7.3 YouTube Integration
```
Engine detect URL YouTube từ browser/PWA (core/engine/_youtube.py:
  win32gui titles + uiautomation + CDP monitor + WinRT media)
  → Kiểm tra cache tone (ToneCacheManager / ManualToneTimeline)
      → Có cache → replay timeline (gửi MIDI đúng thời điểm)
      → Không → auto_detect_youtube_timeline (tải audio yt-dlp, dò tone)
  → Theo dõi playback (media_monitor / cdp_monitor)
      → Video kết thúc → chấm điểm phiên hát (core/engine/_session.py)
```

### 7.4 Chấm điểm
```
User click "Chấm điểm" → chọn nguồn (File / YouTube / phiên ghi âm)
  → ScoringEngine: load audio → analyze_pitch() → calculate_score()
  → ui/dialogs/scoring_report.py hiển thị kết quả
```

### 7.5 Voice command (Accessibility)
```
Giữ Ctrl+Space → core/accessibility/voice_input.py
  → Vosk (models/vosk-vi/) nhận diện tiếng Việt offline
  → fuzzy intent matcher (bỏ dấu + word overlap) → thực thi lệnh
  → feedback TTS (speaker.py) + on-screen
```

---

## 8. 🎵 MIDI Integration

### Kết nối
- Sử dụng **mido** + **python-rtmidi**, port loopMIDI: `"QuangLuuMIDI"`
- Studio One nhận qua Control Surface `studio_one/QuangLuuMIDI.surface.xml` (cài bằng `install_surface.bat`)
- Tự động reconnect nếu mất kết nối

### CC Map (nguồn chuẩn: `app_config.json` → `midi_cc`)
| CC | Parameter | Mô tả |
|----|-----------|--------|
| 10 | tone_music | Tone Nhạc (mapped từ -12/+12) |
| 11 | tone_voice | Tone Giọng (mapped từ -12/+12) |
| 20 | mix_music | Volume Nhạc |
| 21 | mix_mic | Volume Mic |
| 22 | mix_reverb | Vang |
| 23 | mix_backing | Bè |
| 30 | mode / mode_danca | Mode Dân Ca |
| 31 | autokey / tone_auto | AutoKey toggle |
| 32 | score_trigger | Trigger chấm điểm |
| 33 | key_root | Key gốc → Auto-Tune (xem `key_midi_map`) |
| 34 | key_scale | Scale (Major=13, Minor=18 — xem `scale_midi_map`) |
| 35 | scale_type | Loại scale |
| 36 | tune_on_off / fix_meo | Bật/tắt tune (Fix Méo) |
| 37 | mode_lofi | Mode Lofi |
| 38 | mode_remix | Mode Remix |
| 39 | mode_datheloai | Mode Đa Thể Loại |
| 41-44 | mute_multi_cc (mix_reverb) | Mute Vang multi-CC |
| 50 | mute_music | Mute Nhạc |
| 51 | mute_mic | Mute Mic |
| 52 | mute_reverb | Mute Vang |
| 53 | mute_backing | Mute Bè |

> Tool `send_all_midi_keys.py` đọc map này từ `app_config.json` và gửi lần lượt
> từng CC (64 → 0) để Studio One MIDI Learn.

---

## 9. 🔐 Hệ thống Activation

### Format code: `XXXX-XXXX-XXXX-XXXX-XXXX`
- 4 nhóm đầu: random; nhóm 5: checksum
- Hỗ trợ **trial** (dùng thử) bên cạnh license đầy đủ

### Flow:
1. `tools/generate_code.py` → Tạo codes (admin tool)
2. User nhập code → `ActivationManager.activate(code)` → lưu activation.json (trong `%APPDATA%\QuangLuuStudio\`)
3. Mỗi lần mở app → `needs_activation()`:
   - Chưa activate / hết hạn / hết trial → ActivationDialog
   - OK → tiếp tục

---

## 10. 🔨 Build & Deploy

### Build EXE:
```bash
# ✅ Đúng: Build từ spec file
pyinstaller QuangLuuStudio.spec
# hoặc dùng build.bat / build_installer.bat

# ❌ Sai: Sẽ mất datas + hiddenimports
pyinstaller --onefile main.py
```

### Spec (`QuangLuuStudio.spec`) lo các việc:
- **datas**: `app_config.json`, `recorder_worker.py`, `core/`, `tools/`, `sfx/`,
  `studio_one/`, `Be_Vietnam_Pro/`, `ui/styles/`
- **hiddenimports**: rtmidi, mido.backends.rtmidi, librosa/scipy/sklearn internals,
  yt_dlp, pyaudiowpatch, uiautomation, winrt, pycaw, websocket, PySide6.QtMultimedia,
  ui.panels.*, ui.dialogs.* (lazy import)
- **Excludes Qt nặng**: QtWebEngine, QtQuick, Qt3D, ... (giảm ~250MB); GIỮ QtSvg (icon)
- Icon: `app_icon.ico`

### User data (KHÔNG bundle):
`settings.json`, `activation.json`, `saved_songs.json`, `tone_cache.json`,
`manual_timelines.json` — tạo runtime trong `%APPDATA%\QuangLuuStudio\`.

---

## 11. ⚠️ Lưu ý kỹ thuật

### Threading (Qt):
- Tone detection / YouTube watcher / update check chạy thread riêng (không block GUI)
- Ghi âm chạy **subprocess riêng** (`recorder_worker.py`) tránh GIL/crash kéo app
- UI update phải về main thread qua Qt signal / `QTimer.singleShot` — KHÔNG gọi widget từ worker thread

### Audio Processing:
- Loopback capture: WASAPI qua `pyaudiowpatch`
- ToneDetector pipeline: HPSS → Chroma CQT → Multi-profile correlation → Disambiguation
- `librosa` pin `<1.0` — `librosa.beat.tempo` bị xoá ở 1.0 (detect_youtube.py có fallback `librosa.feature.rhythm.tempo`)

### YouTube detection (nhiều tầng):
1. WinRT Media Control (title/playback)
2. CDP monitor (cần browser bật flag `--remote-debugging-port` — `tools/enable_cdp_flag.bat`)
3. win32gui window title + uiautomation (PWA)

### Logging & crash:
- Log ra `%APPDATA%\QuangLuuStudio\logs\` (`core/logger.py`)
- `sys.excepthook` + `threading.excepthook` bắt crash mọi thread

---

## 12. 📊 File dữ liệu (runtime, trong `%APPDATA%\QuangLuuStudio\`)

| File | Format | Mô tả |
|------|--------|--------|
| `settings.json` | JSON | Cấu hình user (paths, update prefs) |
| `activation.json` | JSON | Thông tin license/trial |
| `saved_songs.json` | JSON | Danh sách bài hát |
| `tone_cache.json` | JSON | Cache kết quả dò tone (theo video ID) |
| `manual_timelines.json` | JSON | Timeline tone chỉnh tay |
| `logs/` | Text | Log app (rotate) |

File cấu hình **chương trình** (bundle theo EXE): `app_config.json` (MIDI CC map, key/scale map, accessibility).

---

## 13. 🎯 Tóm tắt nhanh

> **Quang Lưu Studio** là ứng dụng desktop hỗ trợ ca sĩ/phòng thu, chạy trên Windows, GUI **PySide6** (dark theme). Ứng dụng kết nối **Studio One** (DAW) qua **MIDI CC** (loopMIDI + Control Surface) để điều khiển tone, mixer, Auto-Tune. Business logic nằm trong package **`core/`** (engine mixins, tone detector, scoring, accessibility, updater) — `backend.py` chỉ là facade mỏng. UI tách thành **`ui/`** (panels/dialogs/components) + `frontend_qt.py`. Tính năng nổi bật: **AutoKey** dò tone realtime từ loopback (WASAPI), tích hợp **YouTube** (detect URL đa tầng, replay timeline tone, chấm điểm), **voice command tiếng Việt offline** (Vosk) + TTS. Có hệ thống **activation/trial** và **auto-update**. Build EXE bằng **PyInstaller** từ `QuangLuuStudio.spec`.
