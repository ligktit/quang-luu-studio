# Plan: Voice Control, Vận hành & Licensing

**Dự án:** Quang Lưu Studio (`D:\Projects\LiveStudio\quang-luu-studio`) — PySide6, Python, Windows
**Phiên bản hiện tại:** 1.5.0 (`core/version.py:1`)
**Ngày lập:** 2026-06-10
**Đối tượng người dùng:** ca sĩ / phòng thu live tiếng Việt, không rành kỹ thuật — mọi giải pháp ưu tiên **đơn giản, fail-soft, không cần thao tác thủ công**.

**Thứ tự ưu tiên đề xuất:** Feature 2 (model download — đang là lỗi thực tế ở bản cài đặt) → Feature 4 (crash reporting — cần dữ liệu lỗi trước khi mở rộng) → Feature 3 (auto-update — phần lớn đã có sẵn) → Feature 1 (voice control mở rộng) → Feature 5 (licensing).

---

## Feature 1: Mở rộng Voice Control

### Mục tiêu
1. Lệnh có **tham số**: "tăng vang lên bảy mươi", "tone lên hai", "mở bài Duyên Phận" — parse số tiếng Việt và tên bài hát.
2. **Wake word "Studio ơi"** làm lựa chọn thay thế cho push-to-talk Ctrl+Space (bật/tắt trong Settings).
3. **Beep ngắn xác nhận** thay cho câu TTS đầy đủ khi đang phát nhạc (tránh TTS đè lên nhạc khi hát live).

### Hiện trạng
- **Intent matcher keyword tĩnh, không tham số:** `core/accessibility/voice_input.py:50-82` (`_KEYWORD_INTENTS` — 17 intent cố định). Dataclass `Intent` đã có field `arg: Optional[str]` (`voice_input.py:47`) nhưng **chưa nơi nào dùng**.
- **Vosk dùng constrained grammar:** `build_vosk_grammar()` (`voice_input.py:96-105`) phẳng hóa toàn bộ phrase + từng từ riêng + `"[unk]"`, truyền vào `KaldiRecognizer` tại `voice_input.py:257-263` (có fallback open-vocab). **Hệ quả: mọi từ mới (số đếm, tên bài) phải được thêm vào grammar, nếu không Vosk không bao giờ nhận ra.**
- **Fuzzy matching 2 cấp:** `match_intent()` (`voice_input.py:130-157`) — cấp 1 substring sau `_normalize()` bỏ dấu (`:108-117`), cấp 2 word-overlap ≥ 0.7 (`:120-127`).
- **Handler intent:** `frontend_qt.py:1770-1819` (`_a11y_on_voice_intent`) — dict `actions` map intent name → callback **không nhận tham số**; volume step cố định ±5/±1 qua `_a11y_step_volume` (`frontend_qt.py:1821-1829`).
- **PTT:** app-level `eventFilter` bắt Ctrl+Space (`frontend_qt.py:1530-1556`), `_a11y_voice_start/_stop` (`:1558-1592`). Đã có beep winsound 880Hz/440Hz báo bắt đầu/kết thúc nghe — nhưng **xác nhận thực thi lệnh vẫn là câu TTS đầy đủ** "Đã thực hiện" (`frontend_qt.py:1813-1815`).
- **Bài hát đã lưu:** `core/songs.py:20-29` (`SongManager.load_songs()`). Phát bài qua `engine.open_youtube_url` — xem `ui/dialogs/songs_list.py:179-202` (`_make_play`).
- **SFX:** thư mục `sfx/` (3 file wav), `_on_sfx_play` dùng `QMediaPlayer + QAudioOutput` (`frontend_qt.py:1301-1353`, fallback winsound).
- **Settings voice:** checkbox duy nhất `voice_command_enabled` (`ui/dialogs/settings_dialog.py:910-924`), lưu qua `_a11y_collect_and_apply` (`:978-1035`).
- **Trạng thái phát nhạc:** `core/media_monitor.py` (WinRT Media Control, dùng tại `frontend_qt.py:1909`) — dùng để biết "đang phát nhạc hay không".

### Kiến trúc đề xuất

```
voice_input.py (mở rộng)
├── vi_numbers.py (MỚI)      parse "bảy mươi lăm" → 75, "hai" → 2
├── _PARAM_INTENTS (MỚI)     bảng intent có slot: (name, trigger_phrases, slot_type)
│       slot_type ∈ {number, percent, delta, song_title}
├── build_vosk_grammar(extra_phrases)   thêm từ số đếm + từ trong tên bài
├── match_intent(transcript, song_titles) → Intent(name, text, arg)
└── WakeWordListener (MỚI)   stream liên tục, grammar ["studio ơi", "[unk]"]

frontend_qt.py
├── _a11y_on_voice_intent    nhánh mới đọc intent.arg
├── _a11y_set_volume_abs / _a11y_step_tone(delta=n) / _play_song_by_name
└── _a11y_confirm(ok=True)   beep nếu nhạc đang phát, TTS nếu không
```

**Parse số tiếng Việt** (`core/accessibility/vi_numbers.py` — mới, thuần Python):
- Từ vựng: `không một hai ba bốn năm sáu bảy tám chín mười mươi lăm tư linh lẻ trăm` + biến thể không dấu mà Vosk small-vn hay trả về. `parse_vi_number(text) -> Optional[int]` xử lý cả chữ số ("70") lẫn chữ ("bảy mươi", "bảy lăm"). Phạm vi: 0–127.
- Toàn bộ từ vựng số **phải được nối vào grammar** trong `build_vosk_grammar()`.

**Intent có tham số** — bảng `_PARAM_INTENTS` cạnh `_KEYWORD_INTENTS`:

| Intent | Mẫu câu | arg |
|---|---|---|
| `set_volume_reverb` | "tăng/để/chỉnh vang lên N", "vang N" | N (0–100) |
| `set_volume_music` / `set_volume_mic` | tương tự | N |
| `tone_up` / `tone_down` | "tone lên N", "tone xuống N" | N (mặc định 1) |
| `open_song` | "mở bài X", "phát bài X", "hát bài X" | X (tên bài) |

`match_intent()` chạy theo thứ tự: (1) param intents — tách trigger prefix, phần còn lại qua `parse_vi_number` hoặc fuzzy match tên bài; (2) keyword intents như hiện tại (backward-compat — "tăng vang" không số vẫn ra `volume_up_reverb`).

**Match tên bài hát:** so khớp `_normalize(phần-sau-"mở bài")` với `_normalize(song.title)` bằng word-overlap (tái dùng `_word_overlap_score`), ngưỡng ≥ 0.6, lấy điểm cao nhất; trả `arg = str(song_id)`. Title được nạp **mỗi lần start_listening** và đưa vào grammar động: `VoiceInput.set_dynamic_phrases(phrases)`. Tên bài ngoài vocab model nhỏ → chấp nhận tỉ lệ nhận sai, fuzzy bù; không match → đọc "Không tìm thấy bài...".

**Wake word "Studio ơi":**
- Class `WakeWordListener`: một `sd.RawInputStream` chạy liên tục, `KaldiRecognizer` riêng với grammar tối giản `["studio ơi", "ơi studio", "studio", "[unk]"]` — grammar 3-4 từ làm CPU decode rất nhẹ (dùng chung `self._model` đã load).
- Khi Result chứa "studio ơi" (yêu cầu **đủ cả 2 từ**): beep "thức dậy" → nghe lệnh trong cửa sổ 5 giây (tái dùng đường đi PTT) → quay về chế độ wake-word.
- **Giảm false-trigger:** (a) cụm 2 âm tiết; (b) cooldown 3 giây; (c) tự tạm dừng khi đang ghi âm (`is_recording`) và khi PTT đang giữ; (d) tắt mặc định — opt-in (`voice_wake_word_enabled`, mặc định `False`).
- **Tránh xung đột mic:** wake listener `pause()` khi PTT `start_listening()`, `resume()` sau `stop_listening()`. Tích hợp tại `_a11y_voice_start/_stop` (`frontend_qt.py:1558, 1578`) và `closeEvent` (`:1879-1884`).

**Beep xác nhận:**
- Thêm 2 file wav ngắn (~150ms) vào `sfx/`: `sfx_voice_ok.wav`, `sfx_voice_err.wav` (đã được bundle qua spec + iss).
- `MainDashboard._a11y_confirm(ok, msg)`: nếu `media_monitor` báo đang phát nhạc (hoặc `is_recording`) → beep; ngược lại → TTS. Thay các call-site `self._a11y_speak("Đã thực hiện", ...)` (`frontend_qt.py:1815`) và nhánh lỗi 1777, 1807.
- Setting `voice_feedback_mode: "auto" | "beep" | "tts"` (mặc định `auto`).

### Các bước triển khai theo phase

**Phase 1A — Parameterized intents:**
1. Tạo `core/accessibility/vi_numbers.py` + unit test `tests/core/test_vi_numbers.py` ("bảy mươi"→70, "bảy lăm"→75, "hai"→2, "mười"→10, "70"→70, rác→None).
2. Sửa `voice_input.py`: thêm `_PARAM_INTENTS`, mở rộng `all_phrases()`/`build_vosk_grammar(extra_phrases=None)`; mở rộng `match_intent()` trả `Intent.arg`; thêm `set_dynamic_phrases()`.
3. Sửa `frontend_qt.py:_a11y_on_voice_intent`: action mới nhận `intent.arg` — `_a11y_set_volume_abs(cc_key, value)` (map 0–100 → slider, tái dùng `self._mixer_sliders` như `_a11y_step_volume:1821`), `_a11y_step_tone(which, ±n)` (đã có tại `frontend_qt.py:1724`, truyền delta=n).
4. Nạp song titles trong `_a11y_voice_start` → `set_dynamic_phrases`; thêm `_play_song_by_name(arg)` (copy logic từ `ui/dialogs/songs_list.py:179-202`).
5. Cập nhật hint text trong Settings (`settings_dialog.py:916-923`).

**Phase 1B — Beep confirmations:** tạo 2 file wav, thêm `_a11y_confirm`, thay 3 call-site, thêm combo `voice_feedback_mode` vào tab Trợ năng.

**Phase 1C — Wake word:** `WakeWordListener` + lifecycle (init trong `_a11y_init_voice` `frontend_qt.py:1505`, pause/resume quanh PTT và recording, stop trong `closeEvent`), checkbox Settings, indicator "🎙 Studio ơi: BẬT" ở header.

### Phụ thuộc mới
Không có — Vosk + sounddevice + winsound/QtMultimedia đều đã có.

### Rủi ro & cách giảm
- **Vosk small-vn nhận sai số** ("bảy mươi" → "bảy mười"): thêm biến thể lỗi vào từ điển `vi_numbers` (pattern hiện có `voice_input.py:51-55`); test với mic thật.
- **Tên bài ngoài vocab** → fallback "Không tìm thấy"; hướng dẫn user đặt tên bài ngắn gọn.
- **Wake word ngốn CPU/mic 24/7**: grammar nhỏ + blocksize 4000; opt-in + auto-pause khi ghi âm.
- **False trigger khi hát live**: cooldown + yêu cầu đủ cụm; nếu vẫn nhiều → chỉ match trong `Result` (final), bỏ `PartialResult`.
- **Race threading**: giữ kỷ luật lock hiện có (`voice_input.py:326-339`); wake listener dùng lock/flag riêng.

### Tiêu chí nghiệm thu
- "tăng vang lên bảy mươi" → slider reverb = 70, beep (khi nhạc phát) hoặc TTS.
- "tone lên hai" → tone +2; "mở bài <tên trong saved_songs.json>" → phát đúng bài với fuzzy ≥ 1 từ sai/thiếu.
- Lệnh cũ không tham số vẫn hoạt động như trước.
- Wake word: "Studio ơi... tắt nhạc" không chạm bàn phím → nhạc tắt; 30 phút phát nhạc liên tục → ≤ 1 false trigger.
- Tắt voice/thiếu model → app chạy bình thường (fail-soft).

### Ước lượng effort
Phase 1A: **3 ngày** · 1B: **1 ngày** · 1C: **3 ngày** → **Tổng ~7 ngày công**

---

## Feature 2: Model Vosk tải lần đầu (download-on-first-run)

### Mục tiêu
Gỡ model 51MB khỏi repo/installer; app tự tải model từ GitHub Releases khi user bật voice lần đầu, có progress + checksum + resume; voice tắt êm khi chưa có model.

### Hiện trạng
- Model 51MB **đang commit trong git** (`models/vosk-vi/`).
- **Phát hiện quan trọng: bản cài đặt hiện tại KHÔNG có model.** `QuangLuuStudio.spec:10-19` (datas) và `QuangLuuStudio_Setup.iss:74-96` ([Files]) đều **không** đóng gói `models/` → trên máy khách `VoiceInput.available` (`voice_input.py:187-189`) luôn `False`, voice **chết im lặng**; `_default_model_path()` (`voice_input.py:191-198`) trỏ `<thư-mục-exe>\models\vosk-vi` — nằm trong Program Files (read-only). Hint trong Settings bảo user "tải model vào models/vosk-vi" (`settings_dialog.py:917`) — bất khả thi với người không rành kỹ thuật. **Feature này là bug fix, không chỉ là tối ưu dung lượng.**
- Khi thiếu model: `_a11y_init_voice` đọc TTS "Chưa có model giọng nói..." rồi set `self._a11y_voice = None` (`frontend_qt.py:1515-1517`) — fallback đã graceful, chỉ thiếu hành động khắc phục.
- **Tái sử dụng được ngay:** `core/updater/_downloader.py:7-61` (download có resume `.part` + progress callback) và `core/updater/_verifier.py` (`verify_sha256`) — generic.
- Thư mục data user: `%APPDATA%\QuangLuuStudio\` qua `_get_data_dir()` (`core/config.py:33-44`).

### Kiến trúc đề xuất

```
core/model_manager.py (MỚI)
├── MODEL_SPEC = {name, urls (GitHub Release asset .zip + mirror), sha256, size, version}
├── model_dir() → %APPDATA%\QuangLuuStudio\models\vosk-vi   (dev: project/models/vosk-vi)
├── is_model_installed() → check marker file model_dir/.complete (version+sha)
├── download_model(on_progress, cancel_event) →
│     tải zip vào DATA_DIR/models/vosk-vi.zip.part (resume — tái dùng _downloader)
│     → verify_sha256 → giải nén vào models/vosk-vi.tmp → ghi .complete → rename atomic
└── delete_partial() — dọn khi hỏng

ui/dialogs/model_download_dialog.py (MỚI)
└── QProgressBar + nhãn MB/MB + nút Hủy/Thử lại — pattern copy từ UpdateDialog
    (ui/dialogs/update_dialog.py:96-133: thread nền + Signal marshal về main thread)
```

- **Hosting:** release tag riêng `models-v1` trên repo GitHub, upload asset `vosk-model-small-vn.zip` — asset tới 2GB, băng thông miễn phí, không cần server. URL + SHA256 hardcode trong `MODEL_SPEC`.
- **Trigger tải:** (1) user tick "Bật lệnh giọng nói" trong Settings mà model chưa có (`settings_dialog.py:1030-1035`): dialog hỏi "Tính năng cần tải bộ nhận giọng nói (~51 MB). Tải ngay?"; (2) khởi động mà `voice_command_enabled=True` nhưng model thiếu (`frontend_qt.py:1435`): toast + nút "Tải model" trong Settings.

### Các bước triển khai theo phase

**Phase 2A — Module tải model:**
1. Nén model thành zip, tính SHA256, upload lên GitHub Release `models-v1`.
2. Viết `core/model_manager.py` (tái dùng `download_with_progress`, `verify_sha256`); `zipfile` stdlib; giải nén vào `*.tmp` rồi `os.replace` atomic.
3. Viết `ui/dialogs/model_download_dialog.py` (clone skeleton signal/thread của `update_dialog.py:13-31, 96-133`).

**Phase 2B — Tích hợp:**
4. Sửa `voice_input.py:_default_model_path` (191-198): ưu tiên `model_manager.model_dir()`; giữ fallback `<exe>/models/vosk-vi` và project-root (dev mode).
5. Sửa `settings_dialog.py:_a11y_collect_and_apply` (1030-1035): tick voice mà `not is_model_installed()` → `ModelDownloadDialog`; tải xong mới `_a11y_init_voice()`. Sửa hint text.
6. Sửa `frontend_qt.py:_a11y_init_voice` (1505-1524): message "Chưa tải bộ nhận giọng nói — vào Cài đặt → Trợ năng để tải".

**Phase 2C — Dọn repo/installer:**
7. `git rm -r --cached models/vosk-vi` + thêm `models/` vào `.gitignore` (lịch sử git vẫn còn 51MB — lên lịch riêng `git filter-repo`, KHÔNG làm chung commit feature).
8. Spec/iss không cần sửa (chưa từng đóng gói model). Cập nhật `BUILD.md`. Tuỳ chọn: mục `[Files]` optional cho "bản cài offline" nội bộ: `Source: "models\vosk-vi\*"; DestDir: "{userappdata}\QuangLuuStudio\models\vosk-vi"; Flags: external skipifsourcedoesntexist recursesubdirs`.

### Phụ thuộc mới
Không có (urllib + zipfile + hashlib stdlib; downloader/verifier có sẵn).

### Rủi ro & cách giảm
- **Mạng yếu/rớt giữa chừng:** resume `.part` có sẵn (`_downloader.py:29-42`); "Thử lại" tiếp tục từ chỗ đứt.
- **Zip hỏng:** verify SHA256 trước giải nén; marker `.complete` + thư mục `.tmp`.
- **GitHub bị chặn ở một số mạng VN:** `MODEL_SPEC["urls"]` là list (mirror dự phòng — ví dụ `alphacephei.com/vosk/models`).
- **User dev có model cạnh exe:** thứ tự fallback path giữ tương thích.

### Tiêu chí nghiệm thu
- Cài bản mới máy sạch → bật voice → dialog tải progress → xong → Ctrl+Space hoạt động ngay không restart.
- Ngắt mạng giữa chừng → Thử lại tải tiếp; sửa 1 byte zip → báo lỗi checksum, xoá file.
- Không model + không mạng → app chạy bình thường, voice tắt, thông báo dễ hiểu.
- Sau `git rm --cached`: build EXE/installer thành công.

### Ước lượng effort
**3 ngày công** (module 1, UI + tích hợp 1, test máy sạch + dọn repo 1).

---

## Feature 3: Auto-update thật

### Mục tiêu
Hoàn thiện chu trình: phát hiện → tải installer từ GitHub Releases → verify hash/size → chạy Inno Setup `/SILENT` → app tự thoát đúng cách → cài đè → mở lại. Không hỏi user quá 1 click.

### Hiện trạng — phần lớn đã có, còn 4 lỗ hổng
Đã có (xác nhận):
- Check nền sau khi dashboard hiện, rate-limit 24h, marshal signal về main thread: `main.py:86-129, 162-170`.
- `core/updater/_version_check.py:40-95`: GitHub API, tìm asset `*setup*.exe`, đọc `SHA256SUMS.txt` nếu có (71-85), trả `ReleaseInfo` (có `size_bytes`).
- `core/updater/__init__.py:47-86` (`download_and_install`): tải (resume) → `verify_sha256` (71-78, xoá file nếu sai) → `run_installer`.
- `core/updater/_installer.py:7-32`: chạy installer detached với `/SILENT /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS`.
- `ui/dialogs/update_dialog.py`: dialog đầy đủ — Cài/Để sau/Bỏ qua phiên bản (141-161), progress bar.

4 lỗ hổng phát hiện khi đọc code:
1. **BUG handoff khi app đang chạy:** `_installer.py:32` gọi `sys.exit(0)` từ **thread nền daemon** (`update_dialog.py:103-112`) — chỉ kết thúc thread đó, **app không thoát** → Inno `/CLOSEAPPLICATIONS` dựa vào Restart Manager mà PyInstaller GUI app thường không đăng ký → installer treo/báo file locked.
2. **`.iss` thiếu `AppMutex`** (`QuangLuuStudio_Setup.iss:21-65`) và app không tạo mutex.
3. **Verify size không được dùng:** `ReleaseInfo.size_bytes` có (`_version_check.py:22, 94`) nhưng không so sánh khi thiếu `SHA256SUMS.txt`; và **build chưa sinh `SHA256SUMS.txt`** (`build_installer.bat`).
4. **`PrivilegesRequired=admin`** (`QuangLuuStudio_Setup.iss:53`) → update bật UAC prompt (chấp nhận được, cần message cho user).

### Kiến trúc đề xuất
Giữ nguyên kiến trúc hiện tại, vá 4 điểm:

```
UpdateDialog._on_install
└── download_and_install(..., on_ready_to_install=callback)   # TÁCH bước launch
      ├── download + verify sha256 HOẶC verify size_bytes (fallback)
      └── emit signal "ready" → MAIN THREAD: run_installer() → QApplication.quit()
main.py: tạo named mutex "QuangLuuStudioMutex" lúc khởi động
.iss:    AppMutex=QuangLuuStudioMutex + CloseApplications=yes + RestartApplications=yes
build_installer.bat: bước cuối sinh SHA256SUMS.txt cạnh Setup exe
```

**Rollback (giữ đơn giản):** Inno tự rollback khi abort giữa chừng. Sau cài, nếu bản mới hỏng: installer bản cũ vẫn còn tại `%APPDATA%\QuangLuuStudio\updates\` (dest hiện tại — `core/updater/__init__.py:60`) — **giữ lại 2 bản gần nhất**, đừng xoá sau khi cài; dialog lỗi ghi "Cài lại bản trước tại thư mục...". Không làm auto-rollback phức tạp.

### Các bước triển khai theo phase

**Phase 3A — Sửa handoff (quan trọng nhất):**
1. `core/updater/_installer.py`: bỏ `sys.exit(0)` (dòng 31-32); `run_installer` chỉ `Popen` và return.
2. `core/updater/__init__.py:download_and_install`: thêm callback `on_ready(dest_path)` thay vì tự gọi `run_installer`.
3. `ui/dialogs/update_dialog.py`: thêm Signal `ready_to_install`; slot main-thread: `run_installer(dest)` rồi `QApplication.instance().quit()`. Vòng đời `main.py:171-178` (join `_bg_shutdown_thread` rồi `os._exit(0)`) tương thích — installer đã detached.
4. `main.py`: tạo mutex Windows đầu `main()`: `ctypes.windll.kernel32.CreateMutexW(None, False, "QuangLuuStudioMutex")` (giữ handle suốt vòng đời).
5. `QuangLuuStudio_Setup.iss [Setup]`: thêm `AppMutex=QuangLuuStudioMutex`, `CloseApplications=yes`, `RestartApplications=yes`.

**Phase 3B — Verify + pipeline:**
6. `download_and_install`: nếu `release.sha256 is None` → so `dest.stat().st_size == release.size_bytes`, lệch → lỗi.
7. `build_installer.bat`: thêm bước sau ISCC — `certutil -hashfile installer_output\Setup_QuangLuuStudio_v%VER%.exe SHA256` → format "hash  filename" khớp parser `_version_check.py:79-84` → `SHA256SUMS.txt`; ghi checklist release vào `BUILD.md`: upload cả 2 file.
8. Giữ tối đa 2 installer trong `updates/` (dọn file cũ hơn trong `download_and_install`).

**Phase 3C — Trải nghiệm:**
9. UpdateDialog: thêm dòng "Ứng dụng sẽ tự đóng và mở lại sau khi cập nhật. Windows có thể hỏi quyền Administrator — hãy bấm Yes."; sau verify đổi status "Đang cài đặt — app sẽ khởi động lại...".
10. (Tuỳ chọn) Settings tab System: nút "Kiểm tra cập nhật ngay" bỏ qua rate-limit 24h (`main.py:103-105`).

### Phụ thuộc mới
Không có.

### Rủi ro & cách giảm
- **UAC gián đoạn:** chấp nhận 1 prompt; message giải thích trước. Không chuyển per-user install phase này (thay đổi lớn, dễ vỡ migration).
- **App không thoát kịp → file locked:** mutex + `CloseApplications` + chủ động `quit()` từ main thread — 3 lớp.
- **Quên upload SHA256SUMS.txt:** fallback verify size vẫn chặn file hỏng; checklist BUILD.md.
- **Bản mới crash ngay:** Feature 4 (crash report) + installer cũ còn trong `updates/`.

### Tiêu chí nghiệm thu
- Tạo release giả v1.5.1 → app v1.5.0 hiện dialog → "Tải & Cài đặt" → app tự đóng, Inno `/SILENT`, v1.5.1 tự mở lại — chỉ 1 click + UAC.
- Sửa hash trong SHA256SUMS.txt → báo lỗi, file bị xoá, app vẫn chạy.
- App đang ghi âm → update vẫn đóng app sạch (closeEvent chạy đủ).
- "Bỏ qua phiên bản này" → không hỏi lại version đó (regression).

### Ước lượng effort
**2.5 ngày công** (handoff + mutex 1, verify + pipeline 0.5, test end-to-end với release thật 1).

---

## Feature 4: Crash reporting "Gửi báo lỗi"

### Mục tiêu
Mọi crash được ghi nhận; user gửi gói chẩn đoán (logs + config đã scrub) về dev bằng 1 nút; thêm nút "Gửi báo lỗi" thủ công trong Settings.

### Hiện trạng
- `sys.excepthook` + `threading.excepthook` đã có, chỉ log + flush: `main.py:46-57`. **Chưa có** `qInstallMessageHandler` và **chưa có UI** sau crash.
- Logging tốt sẵn: `core/logger.py:setup_logging` — `app.log` (rotating 5MB×3) + `errors.log` (2MB×5) tại `%APPDATA%\QuangLuuStudio\logs` (`main.py:41`); frozen mode mọi `print()` redirect vào log (`_StreamToLogger`).
- Dữ liệu nhạy cảm cần scrub: `activation.json` chứa activation code (`core/activation.py:103-107`); **YouTube cookies** ở `cdp_profile/` và file cookie — TUYỆT ĐỐI không đưa vào zip; log có thể chứa URL YouTube (chấp nhận được).
- Chỗ đặt nút: Settings tab Tools (`ui/dialogs/settings_dialog.py:399`, `_build_tools_tab`).

### Kiến trúc đề xuất

**Kênh gửi — khuyến nghị: Telegram Bot API.** So sánh cho solo dev:

| Kênh | Ưu | Nhược |
|---|---|---|
| **Telegram Bot (chọn)** | Miễn phí, không server, notify tức thì lên điện thoại, file tới 50MB, HTTPS POST multipart bằng urllib stdlib, hoạt động tốt ở VN | Bot token nhúng trong EXE có thể bị trích xuất |
| Email SMTP | Quen thuộc | App-password Gmail hay bị khoá, port 587 bị chặn nhiều mạng |
| HTTPS endpoint riêng | Sạch nhất | Cần server — chưa có cho tới F5 Phase 2 |

Giảm rủi ro token: bot chỉ add vào **1 private channel** nhận report; bị abuse → revoke qua BotFather, bản update sau đổi token; khi F5 Phase 2 có server thì chuyển kênh (interface `send_report(zip_bytes) -> bool` để swap).

```
core/crash_report.py (MỚI)
├── scrub_json(dict) → loại key match {activation_code, cookie, token, password, secret}
├── build_report_zip() → bytes (in-memory ZipFile):
│     logs/app.log* + errors.log* (tail 2MB cuối mỗi file)
│     settings.json (scrubbed), accessibility_overrides.json, app_config.json
│     sysinfo.txt: version, Windows ver, RAM, Python, last traceback
│     KHÔNG: cdp_profile/, cookies, recordings, activation.json (chỉ hash của code)
├── send_report(zip_bytes, user_note="") → Telegram sendDocument (urllib, multipart)
└── mark_crash(exc_info) → ghi DATA_DIR/last_crash.json (timestamp, traceback)

ui/dialogs/crash_report_dialog.py (MỚI)
└── "Ứng dụng gặp lỗi" + ô mô tả (tuỳ chọn) + [Gửi báo lỗi] [Bỏ qua]
```

**Luồng bắt lỗi 3 tầng:**
1. `sys.excepthook` (sửa `main.py:46-49`): log → `mark_crash()` → nếu QApplication còn sống và ở main thread → `CrashReportDialog`; nếu không → chỉ mark, **lần khởi động sau** thấy `last_crash.json` mới hơn lần gửi trước → hỏi "Lần trước app bị lỗi. Gửi báo lỗi cho nhà phát triển?" (đường tin cậy nhất).
2. `threading.excepthook` (sửa `main.py:51-57`): log + `mark_crash()` (không dialog).
3. `qInstallMessageHandler` (thêm vào `main.py`): route `QtWarningMsg+` vào logger, `QtFatalMsg` → `mark_crash`.

### Các bước triển khai theo phase

**Phase 4A:** viết `core/crash_report.py` (scrub + zip + send) + test unit cho `scrub_json` và giới hạn zip (< 10MB); tạo bot Telegram + private channel; token obfuscate nhẹ base64 (không phải bảo mật, chỉ tránh grep lộ liễu).

**Phase 4B:** sửa `main.py` 3 hook; viết `CrashReportDialog`; logic "hỏi khi khởi động sau crash" trong `main()` trước khi tạo dashboard (`main.py:162`).

**Phase 4C:** nút "Gửi báo lỗi" trong Settings tab Tools (`settings_dialog.py:399`) — mở `CrashReportDialog` chế độ thủ công; gửi thread nền + "Đã gửi, cảm ơn!".

### Phụ thuộc mới
Không có (urllib + zipfile + json stdlib). Không `requests`/`sentry-sdk` để khỏi phình EXE.

### Rủi ro & cách giảm
- **Crash dialog tự crash:** mọi hook bọc try/except; tầng cuối luôn là ghi `last_crash.json` + log.
- **Lộ dữ liệu nhạy cảm:** scrub denylist + KHÔNG đụng `cdp_profile/`; test snapshot nội dung zip trước phát hành.
- **Mạng chặn Telegram:** fallback "Lưu file báo lỗi ra Desktop" (zip) + hướng dẫn gửi Zalo.
- **Spam report trùng:** hash traceback, mỗi traceback chỉ hỏi gửi 1 lần (lưu trong `last_crash.json`).

### Tiêu chí nghiệm thu
- `raise RuntimeError` test → dialog → Gửi → zip về channel Telegram < 30s, có logs + sysinfo, KHÔNG có cookie/activation code (grep nội dung zip).
- Crash thread nền → log + mark, không dialog; lần mở sau hỏi gửi.
- Kill app (không exception) → lần mở sau KHÔNG hỏi.
- Nút "Gửi báo lỗi" trong Settings hoạt động khi không có crash.

### Ước lượng effort
**3 ngày công** (module + scrub 1, hooks + dialogs 1, kênh Telegram + test 1).

---

## Feature 5: Licensing nâng cấp

### Mục tiêu
- **Phase 1 (offline):** code gắn máy (HWID), bản ghi activation có chữ ký chống sửa, phát hiện vặn ngược đồng hồ, chống reset trial — **giữ nguyên UX nhập code**.
- **Phase 2 (online, tuỳ chọn):** server license tối giản, activate/validate/deactivate, grace period offline, migrate khách cũ.

### Hiện trạng
- Code format `XXXX-XXXX-XXXX-XXXX-XXXX`, checksum = 4 hex đầu của `MD5(base + SECRET_KEY)` (`core/activation.py:52-66`); generator `tools/generate_code.py` (key đã xoay sau sự cố lộ).
- **Không gắn máy:** 1 code dùng được mọi máy.
- **Bản ghi không ký:** `activation.json` JSON trần (`save_activation`, `activation.py:100-114`; path `core/config.py:70`) — user sửa `activation_timestamp` để gia hạn vô tận.
- **Trial reset được:** `trial_start` cùng file (`activation.py:230-238`) — xoá file là trial lại 3 ngày.
- **Vặn đồng hồ:** `is_expired` chỉ so `time.time()` — lùi đồng hồ là license sống lại.
- Gate khởi động: `main.py:144-157` (`needs_activation` → `ActivationDialog`).

### Kiến trúc đề xuất

**Phase 1 — Offline, gắn máy:**

```
core/machine_id.py (MỚI)
└── get_machine_id() → SHA256(MachineGuid + system-volume-serial)[:16].upper()
     • MachineGuid: HKLM\SOFTWARE\Microsoft\Cryptography\MachineGuid (winreg —
       ổn định qua reinstall app, đổi khi cài lại Windows)
     • Volume serial: GetVolumeInformationW(C:\) qua ctypes
     • KHÔNG dùng MAC (đổi theo adapter/VPN/dock) — tránh khách bị "mất kích hoạt" oan
     • Hiển thị "Mã máy: ABCD-EF12-3456-7890" trong ActivationDialog

core/activation.py (nâng cấp, giữ class ActivationManager)
├── Bản ghi ký: record = {code, hwid, activated_at, last_seen, trial_start}
│   + "sig" = HMAC-SHA256(canonical_json(record), key=SHA256(SECRET_KEY + "rec"))
├── load_activation(): verify sig — sai/thiếu → coi như chưa kích hoạt (tamper)
├── Mirror chống xoá-reset-trial: bản sao record vào
│   HKCU\Software\QuangLuuStudio\state (winreg). Mất file nhưng còn registry
│   → khôi phục (trial không reset). Mất cả hai → chấp nhận thua (giữ đơn giản).
├── Clock rollback: mỗi lần chạy, last_seen = max(last_seen, now); nếu
│   now < last_seen - 6h → "clock_tampered" → yêu cầu chỉnh lại giờ
└── Code v2 gắn máy (giai đoạn 1.5, tuỳ chọn): khách đọc "mã máy" qua Zalo,
    dev chạy generate_code.py --hwid ABCD... → code chỉ kích hoạt máy đó
    (checksum = HMAC(base + hwid + SECRET)). App verify v2 trước, fallback v1
    — v1 bind-on-activate: lần đầu nhập ghi hwid vào record ký; copy
    activation.json sang máy khác → hwid lệch → từ chối.
```

**Phase 2 — Online tối giản (khuyến nghị: Cloudflare Worker + D1, $0/tháng):**

So sánh thực tế cho solo dev:
- **Cloudflare Worker + D1 (khuyến nghị):** free tier dư sức (vài nghìn user), không vá OS, không mất server khi quên gia hạn VPS, latency tốt ở VN. Nhược: viết JS/TS (~150-200 dòng).
- FastAPI + SQLite trên VPS $5: quen Python, nhưng $60/năm + tự lo HTTPS/backup/uptime.

```
API (3 endpoint, JSON):
POST /activate   {code, hwid, app_version} → {license_token} | lỗi
POST /validate   {license_token, hwid}     → {valid, expires_at}
POST /deactivate {license_token, hwid}     → giải phóng 1 slot máy
DB: licenses(code, customer, max_machines=1, expires_at), activations(code, hwid, activated_at, active)

license_token = JSON {code_hash, hwid, expires_at, issued_at} + chữ ký Ed25519 server.
App nhúng PUBLIC KEY → verify offline không cần mạng.
Offline grace: validate nền tối đa 1 lần/ngày (pattern rate-limit update check
main.py:103-105); lỗi mạng → vẫn chạy nếu lần validate thành công gần nhất < 30 ngày;
quá 30 ngày → nhắc, khoá sau 37 ngày (ca sĩ live không được chết show vì mất mạng).

Migration khách cũ: import code v1 đã phát vào DB; app mới thấy activation.json
kiểu cũ → tự gọi /activate với code cũ → nhận token; server unreachable →
tiếp tục chạy offline kiểu Phase 1.
```

### Các bước triển khai theo phase

**Phase 5.1 — Offline hardening (làm trước, độc lập):**
1. `core/machine_id.py` + test (chạy 2 lần cùng ID; mock registry).
2. `core/activation.py`: `_sign_record/_verify_record` (hmac, hashlib stdlib); sửa `save_activation` (100-114) ghi record ký + mirror registry; sửa `load_activation` (89-98) verify sig + fallback registry; sửa `is_expired/is_trial_*`; thêm check `last_seen` clock rollback trong `needs_activation` (198-209). Giữ nguyên API static method để `main.py:144-157` và `ActivationDialog` không phải đổi.
3. Migration tại chỗ: `load_activation` gặp file cũ không sig → nếu code valid v1 thì tự nâng cấp thành record ký (bind hwid hiện tại) — khách cũ không thấy gì khác.
4. `ActivationDialog`: thêm "Mã máy: XXXX..." (copy được) + thông báo lỗi mới ("Mã này đã kích hoạt trên máy khác", "Đồng hồ máy tính không đúng").
5. `tools/generate_code.py`: mode `--hwid` sinh code v2 gắn máy.

**Phase 5.2 — Online (chỉ làm khi doanh số đáng kể):**
6. Worker + D1 schema + 3 endpoint + script import code cũ (1 file TS ~200 dòng, deploy `wrangler`).
7. App: `core/license_client.py` (urllib, timeout ngắn, mọi lỗi mạng = im lặng dùng offline); verify Ed25519 — cần lib `cryptography` hoặc `pynacl` (phụ thuộc mới); validate nền tích hợp vào luồng update check (`main.py:166-170`).
8. UX đổi máy: nút "Chuyển máy" trong ActivationDialog gọi `/deactivate`.

### Phụ thuộc mới
- Phase 1: không (winreg, ctypes, hmac, hashlib stdlib).
- Phase 2: `cryptography` (client verify Ed25519); Cloudflare account (free) + `wrangler` (dev-side).

### Rủi ro & cách giảm
- **HWID đổi oan (thay ổ, cài lại Win):** 2 nguồn (MachineGuid + volume serial), khớp 1/2 vẫn chấp nhận (soft match); đường dây nóng Zalo cấp lại code.
- **Python dễ reverse:** chấp nhận — mục tiêu chặn chia sẻ casual, không chống cracker chuyên nghiệp; không đầu tư obfuscation.
- **Registry mirror bị antivirus nghi:** chỉ HKCU (không cần admin), key tên rõ ràng.
- **Server chết làm khách bị khoá (P2):** grace 30+7 ngày + fallback offline vĩnh viễn nếu record offline ký còn hạn.
- **Đứt gãy migration:** test ma trận: file cũ hợp lệ / hết hạn / không file / file sửa tay.

### Tiêu chí nghiệm thu
- Copy `activation.json` đã kích hoạt sang máy khác → từ chối, báo đúng thông điệp.
- Sửa 1 ký tự trong `activation.json` → coi như chưa kích hoạt (không crash).
- Xoá `activation.json` sau khi trial hết → trial KHÔNG reset (registry mirror).
- Lùi đồng hồ 30 ngày → yêu cầu chỉnh giờ, không gia hạn lậu.
- Khách cũ (code v1, file cũ) update bản mới → vào thẳng app, không nhập lại.
- (P2) Activate code trên máy 2 khi `max_machines=1` → từ chối; rút mạng 29 ngày → vẫn chạy.

### Ước lượng effort
- Phase 5.1: **4 ngày công** (machine_id 0.5, ký + mirror + rollback 1.5, migration + dialog 1, test ma trận 1)
- Phase 5.2: **6–8 ngày công** (Worker+DB 2-3, client + token 2, migration + đổi máy UX 1, test 1-2)

---

## Tổng hợp effort & lộ trình

| Feature | Effort | Gợi ý sprint |
|---|---|---|
| F2 Model download (bug fix thực tế) | 3 ngày | Sprint 1 |
| F4 Crash reporting | 3 ngày | Sprint 1 |
| F3 Auto-update hoàn thiện | 2.5 ngày | Sprint 2 |
| F1 Voice control mở rộng | 7 ngày | Sprint 2–3 |
| F5.1 Licensing offline | 4 ngày | Sprint 3 |
| F5.2 Licensing online (tuỳ chọn) | 6–8 ngày | Khi cần |
| **Tổng (không F5.2)** | **~19.5 ngày công** | |

Ghi chú phối hợp: F3 phát hành **trước** F1/F5 để các bản sau tự lan toả qua auto-update; F4 phát hành sớm để thu crash data trong lúc làm F1 (voice/audio threading là vùng dễ sinh lỗi nhất).

### File quan trọng khi triển khai
- `core/accessibility/voice_input.py`
- `frontend_qt.py`
- `core/updater/__init__.py` (cùng `_installer.py`, `_downloader.py`)
- `core/activation.py`
- `main.py` (cùng `QuangLuuStudio_Setup.iss`, `ui/dialogs/settings_dialog.py`)
