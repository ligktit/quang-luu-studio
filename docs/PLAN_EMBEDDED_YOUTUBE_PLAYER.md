# Plan: Màn hình karaoke YouTube nhúng (player nhúng) + tách 2 phiên bản build

## Context

App hiện tại **không tự phát** YouTube: nó mở video trong **trình duyệt ngoài** rồi *đọc lén* URL + trạng thái phát qua nhiều tầng (`win32gui` title → `uiautomation` → CDP → WinRT Media) để dò tone và biết lúc video kết thúc. Hệ quả: màn hình khách nhìn thấy là cửa sổ Chrome đầy đủ (thanh địa chỉ, đề xuất, bình luận, quảng cáo) — không giống "app YouTube karaoke phòng hát" chỉ hiện đúng khung video.

Mục tiêu: thêm **màn hình karaoke sạch** = cửa sổ Qt thứ 2 (frameless, fullscreen, đặt trên màn hình treo phía trên) nhúng **YouTube IFrame Player API** qua `QtWebEngine`. Lợi ích kép: (1) màn hình do app kiểm soát 100%, chỉ có video; (2) IFrame API cho event playback trực tiếp (`onStateChange`, `getCurrentTime`, ended) — sạch hơn nhiều so với `sleep(duration+5)` và CDP scraping hiện tại.

`QtWebEngine` nặng (~250MB, hiện đang bị loại khỏi build). Vì vậy ship **2 phiên bản từ cùng một codebase**:
- **Light** (giữ nguyên hiện tại): không bundle QtWebEngine → máy yếu. Không có player nhúng, dùng luồng trình duyệt ngoài như cũ.
- **Heavy**: bundle QtWebEngine → máy mạnh. Có màn hình karaoke nhúng.

Cùng một code chạy được cả 2 build nhờ **phát hiện năng lực lúc chạy** (`try import QtWebEngine`). UX nạp bài: **ô tìm kiếm YouTube + dán link trong app** (đã chốt với user), cộng Bài đã lưu / Setlist phát thẳng vào màn 2.

## Nguyên tắc thiết kế

- **Capability ≠ entitlement.** Player nhúng phụ thuộc *build* (có QtWebEngine không), KHÔNG phải license tier. Không nhét vào `core/entitlements.py::PREMIUM_FEATURES` (sẽ kéo theo upsell dialog sai ngữ cảnh). Dùng cơ chế phát hiện riêng.
- **Single codebase, graceful degradation.** Mọi import QtWebEngine bọc `try/except ImportError` theo đúng pattern sẵn có ở `core/media_monitor.py:10-16` (`_WEBENGINE_AVAILABLE` flag).
- **Tone detection không đổi.** Dò tone tải audio riêng bằng yt-dlp theo URL (`core/engine/_tone.py:508` `detect_tone_from_browser`, `:690` `auto_detect_youtube_timeline`) — độc lập với trình duyệt, nên player nhúng không phá vỡ gì. Chỉ luồng *fallback loopback* (`_tone.py:267`) dựa `media_monitor.current_title`; ở chế độ nhúng sẽ lấy title từ IFrame meta thay thế.

---

## Phần 1 — Tách 2 phiên bản build (parametrize spec)

**`QuangLuuStudio.spec`** — QtWebEngine bị loại ở 3 chỗ phải đồng bộ:
- `_qt_excludes` (lines 81-101): `QtWebEngine`, `QtWebEngineCore`, `QtWebEngineWidgets`, **kèm `QtWebSockets` + `QtWebChannel`** (QtWebEngine cần lúc chạy).
- `_exclude_dlls` (lines 109-118): `Qt6WebEngine`, `Qt6WebChannel`, `Qt6WebSockets`.
- `_toc_should_exclude` (lines 145-149): pass thứ 2 strip DLL hook re-add.

Thay đổi:
- Đầu spec đọc env: `INCLUDE_WEBENGINE = os.environ.get("QLS_WEBENGINE") == "1"`.
- Gom 1 list `_WEBENGINE_NAMES` (module names + DLL substrings). Khi `INCLUDE_WEBENGINE` → **không** thêm các tên này vào cả 3 list. Khi không → thêm như cũ.
- EXE name (line 157) thêm hậu tố biến thể (vd `QuangLuuStudio` vs `QuangLuuStudio` — giữ tên process, chỉ khác output dir để 2 build cùng tồn tại).

**Pipeline build** — `build_installer.bat` là luồng thật (`sync_version.py` → `pyinstaller QuangLuuStudio.spec` → `ISCC QuangLuuStudio_Setup.iss`). `build.bat`/`build.sh` đã cũ (trỏ `main.spec` không tồn tại) — bỏ qua.
- Tạo `build_installer_heavy.bat`: set `QLS_WEBENGINE=1`, build với `--distpath dist_heavy`, gọi `ISCC /DVariant=heavy`. `build_installer.bat` hiện tại trở thành biến thể "light" (không set env).
- `QuangLuuStudio_Setup.iss`: tham số hoá `OutputBaseFilename` + `Source: "dist\..."` theo `Variant` để 2 installer không đè nhau (vd `Setup_QuangLuuStudio_Heavy_v{ver}.exe`).
- `build`/`dist` bị xoá mỗi lần chạy (`build_installer.bat:54-55`) → dùng distpath riêng cho heavy.
- Version vẫn 1 nguồn `core/version.py` (`sync_version.py` không đổi).

## Phần 2 — Phát hiện năng lực lúc chạy

**Mới: `core/capabilities.py`** (mirror `media_monitor.py:10-16`):
```python
try:
    from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa
    _WEBENGINE_AVAILABLE = True
except ImportError:
    _WEBENGINE_AVAILABLE = False

def embedded_player_available() -> bool:
    return _WEBENGINE_AVAILABLE
```
Settings dialog + dashboard gọi hàm này để bật/tắt tính năng. Light build → `False` → mọi UI player nhúng ẩn/disabled, app chạy y như cũ.

## Phần 3 — Cài đặt mới (settings.json qua ConfigManager)

`settings.json` là dict tự do (`core/config.py:469` `load_settings` / `:478` `save_settings`), default đặt inline tại call site.
- `use_embedded_player` (bool, default `False`).
- `display_monitor_index` (int, default `0`).

**`ui/dialogs/settings_dialog.py`** — thêm vào System tab (`_build_system_tab`, line 340), persist trong `_save()` (~line 1188, ghi `self._dashboard.settings` → `backend.ConfigManager.save_settings`):
- Checkbox "Dùng màn hình karaoke nhúng" — `setEnabled(capabilities.embedded_player_available())`; nếu light build hiển thị hint "Cần bản cài đặt đầy đủ (Heavy)".
- `QComboBox` chọn màn hình — populate từ `QGuiApplication.screens()` (tên + độ phân giải mỗi screen).

## Phần 4 — Cửa sổ màn hình karaoke

**Mới: `ui/karaoke_player.py`** (import gated bởi `capabilities`). Class `KaraokePlayerWindow(QMainWindow)`:
- Frameless + nền đen; `showFullScreen()` trên `QGuiApplication.screens()[display_monitor_index]` (validate index, fallback primary nếu out-of-range — cũng vá luôn lỗ hổng restore off-screen ở `frontend_qt.py:188-194`).
- Chứa `QWebEngineView` load file HTML cục bộ.
- `QWebChannel` bridge JS→Python. Qt Signals (theo pattern `_tone_result_signal` ở `frontend_qt.py:89`): `video_ended`, `time_updated(pos, dur)`, `video_meta(title, video_id)`, `embed_blocked(video_id)`.
- Method Python→JS: `load_video(video_id)`, `play()`, `pause()`, `set_volume(v)`, `seek(sec)`.

**Mới: `ui/assets/youtube_player.html`** (bundle qua spec `datas`): trang nền đen, IFrame Player API full-screen, `playerVars`: `controls=0, rel=0, modestbranding=1, iv_load_policy=3, autoplay=1, fs=0`. `onReady`/`onStateChange`/`onError` đẩy về Python qua `qwebchannel.js`. State `0`=ended, error 101/150 = chặn nhúng → emit `embed_blocked`.

## Phần 5 — Tích hợp vào MainDashboard + UI tìm kiếm

**`frontend_qt.py` (`MainDashboard`, class line 85):**
- Trong `__init__` (cạnh `_start_youtube_watcher()` line 226): nếu `use_embedded_player and capabilities.embedded_player_available()` → tạo `self._player_window`, connect signals; **và tắt watcher trình duyệt ngoài** (không mở browser ngoài ở chế độ nhúng → tránh dò trùng). Light/ tắt nhúng → giữ nguyên `_start_youtube_watcher()`.
- Method mới `_play_in_embedded(url)`:
  1. `video_id = _clean_youtube_url(url)` (reuse `core/engine/_youtube.py:44`).
  2. `self._player_window.load_video(video_id)`.
  3. Kích hoạt dò tone qua đúng đường engine sẵn có `engine._dispatch_auto_detect(url, ...)` (`_youtube.py:571`) + replay manual timeline nếu có (`backend.ManualToneTimeline.load_timeline(url)`) — đồng bộ logic với `songs_list.py:393`.
  4. Cập nhật tone combo / waveform / marquee như `_make_play` hiện tại.

**UI tìm kiếm + dán link** — thêm thanh nhỏ vào `ui/panels/tools.py` (hoặc header): `QLineEdit` + nút 🔍/Phát + danh sách kết quả (popup/`QListWidget`).
- Nếu input là URL (`_clean_youtube_url` ra video_id) → `_play_in_embedded` ngay.
- Nếu là từ khoá → chạy nền `extract_info_with_auth(f"ytsearch5:{q}", make_ydl_opts(skip_download=True, default_search='ytsearch'), download=False)` (reuse `core/ytdlp_support.py`, đúng như `_youtube.py:286`) → hiện 5 kết quả (title + thumbnail nếu có) → user chọn → `_play_in_embedded`. Chạy thread, kết quả marshal về GUI qua Qt signal mới.

**Transport control** (Play/Pause/Next + âm lượng) trên app chính → gọi method `KaraokePlayerWindow`. Âm lượng: ở chế độ nhúng route `set_player_volume` sang player window thay vì CDP (`core/engine/_recording.py:94`).

**Saved songs / Setlist** — `ui/dialogs/songs_list.py:386` `_make_play` và `frontend_qt.py:1239` `_setlist_play_song`: thêm nhánh — nếu chế độ nhúng bật → `_play_in_embedded(url)`; ngược lại giữ `engine.open_youtube_url(...)` như cũ.

## Phần 6 — Nguồn trạng thái playback (chấm điểm khi hết bài)

Ở chế độ nhúng, dùng event IFrame thay cho CDP/WinRT/`sleep(duration+5)`:
- `KaraokePlayerWindow.video_ended` → dashboard gọi engine kết thúc phiên (tái dùng logic `on_video_end` ở `_youtube.py:423`: nếu `quick_score_active` → set `False` để vòng quick-score dừng & chấm; gọi `on_video_end_callback`). Thêm method engine `notify_video_ended()` để dashboard gọi vào.
- `time_updated` → cập nhật progress/waveform nếu cần.
- `video_meta.title` → cấp cho luồng fallback loopback thay `media_monitor.current_title` (`_tone.py:299`).

---

## Files đụng tới (tóm tắt)

| File | Thay đổi |
|------|----------|
| `QuangLuuStudio.spec` | Parametrize QtWebEngine theo env `QLS_WEBENGINE` (3 list từ 1 nguồn) + datas thêm `ui/assets/youtube_player.html` |
| `build_installer_heavy.bat` (mới) | Build biến thể heavy (env + distpath + ISCC /D) |
| `QuangLuuStudio_Setup.iss` | Tham số hoá output/source theo `Variant` |
| `core/capabilities.py` (mới) | `embedded_player_available()` |
| `core/config.py` | (không sửa cấu trúc — chỉ thêm key qua call site) |
| `ui/dialogs/settings_dialog.py` | Checkbox player nhúng + combo màn hình (System tab + `_save`) |
| `ui/karaoke_player.py` (mới) | `KaraokePlayerWindow` (QWebEngineView + QWebChannel) |
| `ui/assets/youtube_player.html` (mới) | Trang IFrame Player sạch |
| `frontend_qt.py` | Tạo/wire player window, `_play_in_embedded`, gate watcher, transport, nhánh saved/setlist |
| `ui/panels/tools.py` | Thanh tìm kiếm/dán link + kết quả |
| `core/engine/_youtube.py` | `notify_video_ended()` helper (tái dùng `on_video_end`) |
| `core/engine/_recording.py` | Route âm lượng sang player window ở chế độ nhúng |

## Kiểm thử (end-to-end)

1. **Light build vẫn nguyên vẹn:** chạy `python main.py` trong môi trường *giả lập thiếu QtWebEngine* (tạm rename/PYTHONPATH chặn import) → `embedded_player_available()` = False → checkbox disabled, app hoạt động y như trước (watcher + browser ngoài). Chạy `pytest` (`tests/`) đảm bảo không vỡ.
2. **Heavy dev:** `python main.py` (PySide6 meta đã có QtWebEngine) → bật "Dùng màn hình karaoke nhúng", chọn màn 2 → cửa sổ karaoke fullscreen hiện trên màn 2.
3. **Tìm kiếm:** gõ tên bài → 5 kết quả → chọn → video phát sạch trên màn 2; dán link trực tiếp cũng phát.
4. **Dò tone:** xác nhận tone tự dò ra đúng (yt-dlp path) và MIDI gửi sang Studio One như cũ.
5. **Hết bài:** để video chạy hết → `video_ended` kích hoạt chấm điểm (quick score) — không còn phụ thuộc `sleep(duration+5)`.
6. **Embed bị chặn:** thử 1 MV chính chủ chặn nhúng → `embed_blocked` → fallback mở trình duyệt ngoài (`open_youtube_url`) + thông báo cho user.
7. **Build thật:** chạy `build_installer.bat` (light) và `build_installer_heavy.bat` → 2 installer riêng; kiểm tra dung lượng (heavy lớn hơn ~250MB) và heavy có DLL `Qt6WebEngineCore`.

## Rủi ro / lưu ý

- **MV chặn nhúng** là vấn đề thật của karaoke YouTube → bắt buộc có fallback browser ngoài (Phần 6, test 6).
- **Audio routing:** player nhúng phát qua default output → loopback fallback vẫn chạy; cần đảm bảo không tự thu nhạc nền app mix vào (đã có ở luồng hiện tại).
- **Tuân thủ ToS YouTube IFrame API** (không chặn quảng cáo, không tách audio) — ta chỉ phát qua player chính thống nên ổn.
- Hai build phải test riêng; CI hiện chỉ chạy test logic, không build EXE.

---

## Cập nhật 2026-07-07 — Backend phát KÉP + chống quảng cáo + sửa màn hình đen

Sau khi chạy thử, đã bổ sung/khắc phục (đã kiểm chứng end-to-end):

**1. Sửa "màn hình đen" của player nhúng** (`ui/karaoke_player.py`, `main.py`):
- `main.py`: set `AA_ShareOpenGLContexts` TRƯỚC khi tạo QApplication — thiếu nó thì `QWebEngineView` chỉ hiện đen (app dùng `QT_OPENGL=angle`).
- WebEngine settings: bật `LocalContentCanAccessRemoteUrls` + tắt `PlaybackRequiresUserGesture` (autoplay).
- Trang được phục vụ qua **HTTP loopback `127.0.0.1`** (`_LocalAssetServer`) thay vì `file://` → có origin http hợp lệ, hết **lỗi 153**. HTML thêm `origin: window.location.origin`.

**2. Backend NATIVE chống quảng cáo (mặc định)** — quán karaoke không dính QC dù không có Premium vì KHÔNG phát qua trang YouTube:
- `KaraokePlayerWindow` giờ có `QStackedWidget` gồm `QWebEngineView` (IFrame) + `QVideoWidget`/`QMediaPlayer` (native).
- `_play_in_embedded`/`play_youtube_in_app` → `_resolve_and_play_stream` (nền): yt-dlp trích **luồng progressive** (itag 22/18 = 1 file video+audio, phát thẳng không cần ffmpeg) rồi `play_stream()` phát bằng QMediaPlayer → **không quảng cáo**.
- ~~**Bắt buộc ép `player_client=[tv_embedded, android, ios]`** khi trích luồng~~ — **lỗi thời từ v1.7.3 (18/08/2026)**: `tv_embedded` đã bị yt-dlp 2026.07 bỏ, và danh sách này thực tế **chưa bao giờ có hiệu lực** vì `_apply_player_clients` xoá sạch nó ở mọi lượt. Nay `_resolve_and_play_stream` truyền `purpose=PURPOSE_VIDEO` và để `core/ytdlp_support.py` chọn thang client — đo 18/08/2026 bộ client mặc định (có PO Token) cho **7 luồng progressive tới 2160p**, hơn hẳn android (1 luồng, 360p). Xem [`PLAN_YOUTUBE_NO_ACCOUNT.md`](PLAN_YOUTUBE_NO_ACCOUNT.md).
- Fallback tự động: native lỗi (URL hết hạn/không mở được) → signal `stream_failed` → `load_video()` IFrame; IFrame bị chặn nhúng (101/150) → `embed_blocked` → trình duyệt ngoài. 3 tầng: native → IFrame → browser.
- Bài đã lưu / Setlist (`_load_embedded_video`) cũng đi qua luồng native no-ads này.

**3. Phần 5 (thanh tìm kiếm/dán link)**: đã hoàn thiện & chạy (UI `ui/panels/tools.py::_build_search_bar`, handler + tìm nền yt-dlp trong `frontend_qt.py`). Chỉ hiện khi bật chế độ nhúng.

**4. Spec Heavy**: thêm `PySide6.QtMultimediaWidgets` vào hiddenimports (QtMultimedia đã có). Cần verify bản đóng gói Heavy có **plugin ffmpeg media** của Qt (Qt6 dùng backend FFmpeg để phát mp4 stream) — `collect_all('PySide6')` nên gom, nhưng phải test EXE thật.

**Hạn chế đã biết:**
- Progressive tối đa **~720p** (itag 22), nhiều video chỉ có 360p (itag 18). Muốn nét hơn phải DASH + ffmpeg merge (không stream trực tiếp được) — bỏ qua cho karaoke.
- URL googlevideo gắn IP/phiên, thỉnh thoảng trả về không mở được → đã có fallback IFrame.

**Còn lại:** tách build Heavy/Light thật + test EXE (spec/iss đã tham số hoá; chưa build & đo).
