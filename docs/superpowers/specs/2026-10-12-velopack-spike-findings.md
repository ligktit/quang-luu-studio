# Kết quả spike Velopack (2026-10-12)

Máy dev Windows (METTITECH-DEV), app thử `QLSSpike` + app thật `QuangLuuStudio` (code nhánh `feat/velopack-installer`, `main.py` vá tạm 2 dòng velopack, đã hoàn tác).

| # | Câu hỏi | Kết quả | Bằng chứng |
|---|---------|---------|-----------|
| 1 | Onedir app thật chạy đủ (audio, numba, ffmpeg, piper, ghi âm, SFX) | **Đạt phần tự động; phần giao diện CHƯA kiểm** (phát YouTube, SFX có tiếng, piper đọc, ghi âm 5 s — chỉ mới thấy file có mặt, chưa thấy tính năng chạy) | `--tu-kiem-tra` mã 0 (dò tone: numba/librosa/ffmpeg); `--thu-tai` mã 0; `ffmpeg\ffmpeg.exe -version` chạy; `tools\piper\piper.exe`, `_internal\sfx` (3 file), `_internal\recorder_worker.py` có; `_internal` còn nguyên sau khi thoát |
| 2 | Setup cài %LocalAppData% không UAC | **Có** | QLSSpike 1,8 s; app thật 7 s, cửa sổ ở giây 9; không bị chặn chờ UAC |
| 3 | Hook `--veloapp-*` + `VELOPACK_FIRSTRUN` | **Có** | Setup chạy `exe --veloapp-install 1.0.0` → `App().run()` xử lý và thoát, không mở UI; lần chạy đầu `VELOPACK_FIRSTRUN=true`, `on_first_run("1.0.0")`; cập nhật: `--veloapp-updated`, `before_update`/`after_update`; gỡ: `--veloapp-uninstall`, `before_uninstall`. Callback nhận **chuỗi phiên bản** |
| 4a | Tải ngầm khi app chạy | **Có** | `check -> 1.0.1 deltas=1`, tải xong 2,6 s, cửa sổ vẫn 1.0.0 |
| 4b | `wait_exit_then_apply_updates(silent=True, restart=False)` khi thoát | **Có** | Lần mở sau `current=1.0.1`, `VELOPACK_RESTART` rỗng; log không lỗi. (Không quan sát bằng mắt có cửa sổ nào lóe lên.) |
| 4c | Delta | **Có** | Chỉ GET `-delta.nupkg` 78 606 B (full 52 960 954 B); `packages\` dựng lại full cục bộ |
| 4d | Tắt ngang → tự áp dụng lần mở sau | **Có** | `taskkill /F` khi có bản chờ 1.0.2 → mở lại: áp dụng + cửa sổ sau 1,56 s; **`VELOPACK_RESTART=true` và `on_restarted("1.0.2")`** (Velopack khởi động lại app sau khi áp dụng lúc mở) |
| 5 | Gói tự tải không có Zone.Identifier | **Có** | `packages\*.nupkg` không có stream `Zone.Identifier` |
| — | Đường dẫn Unicode / có dấu cách trong tên người dùng | **CHƯA kiểm** | Máy dev: `C:\Users\GrantTuan\AppData\Local\QuangLuuStudio` (không dấu, không cách; `%TEMP%` có dạng 8.3 `GRANTT~1` chỉ vì tên dài) |
| 6 | Defender | **Sạch** | `MpCmdRun -Scan -ScanType 3 -File %LOCALAPPDATA%\QuangLuuStudio` → found no threats |

## Số đo

- Phiên bản: velopack (pip) **1.2.161**, vpk **1.2.161**, .NET SDK **10.0.302** (không cần SDK 8 — vpk chạy trên SDK có sẵn).
- Build PyInstaller onedir 162 s; chép tài nguyên + `vpk pack` 63 s.
- Kích thước: `dist\QuangLuuStudio` 1,2 GB; `full.nupkg` 553 MB; `Setup.exe` 561 MB (bộ cài Inno hiện tại ~488 MB).
- **Khởi động** (trung vị 3 lần, tới khi cửa sổ có tiêu đề): onedir **1,4 s** — onefile 1.8.0 trong Program Files **7,9 s**.
- Mất mạng (kết nối bị từ chối): cửa sổ 0,58 s; lỗi updater sau 2 s ở luồng nền, không treo.

## Định dạng releases.win.json (thật)

```json
{"Assets":[{"PackageId":"QLSSpike","Version":"1.0.1","Type":"Delta","FileName":"QLSSpike-1.0.1-delta.nupkg","SHA1":"…","SHA256":"…(HEX CHỮ HOA)","Size":78606}, …]}
```

- Không có `NotesMarkdown`/`NotesHtml` khi rỗng. SHA256 là hex **chữ hoa**.
- Feed của một bản **liệt kê cả tài sản các bản trước** có trong thư mục output.
- Client gọi `GET <base>/releases.win.json?localVersion=<v>&id=<packId>&stagingId=<guid>` rồi `GET <base>/<FileName>` (không query).

## Tên file vpk sinh ra

`<packId>-<ver>-full.nupkg`, `<packId>-<ver>-delta.nupkg` (khi output dir có bản trước), `<packId>-win-Setup.exe`, `<packId>-win-Portable.zip`, `releases.win.json`, `assets.win.json`, `RELEASES` (định dạng cũ, có BOM). Pack lặp lại vào cùng `--outputDir` tự sinh delta.

Bố cục cài: `%LOCALAPPDATA%\<packId>\{current\, packages\, Update.exe, <packId>.exe (exe mồi)}`. Shortcut Desktop + Start Menu **của người dùng**, trỏ `current\<exe>`. Gỡ: `QuietUninstallString` trong `HKCU\...\Uninstall`, xoá thư mục cài + shortcut, giữ `%APPDATA%`.

## Lệnh chép tài nguyên cạnh exe trước khi pack

Theo đúng `[Files]` của `.iss` (cmd, từ gốc repo, `OUT=dist\QuangLuuStudio`):

```bat
for %%F in (app_icon.ico setup_all.bat setup_midi_ports.ps1 configure_youtube_cookies.bat kiem_tra_tone.bat thu_tai_youtube.bat app_config.json binaries\qjs.exe) do copy /Y "%%F" "%OUT%\"
xcopy /E /I /Y /Q studio_one "%OUT%\studio_one"
xcopy /E /I /Y /Q cubase "%OUT%\cubase"
xcopy /E /I /Y /Q sfx "%OUT%\sfx"
xcopy /E /I /Y /Q models "%OUT%\models"
xcopy /E /I /Y /Q tools\piper "%OUT%\tools\piper"
xcopy /E /I /Y /Q binaries\ffmpeg "%OUT%\ffmpeg"
vpk pack --packId QuangLuuStudio --packVersion <ver> --packDir "%OUT%" --mainExe QuangLuuStudio.exe --icon app_icon.ico --outputDir <out>
```

Spec onedir: thay khối `EXE(pyz, a.scripts, a.binaries, a.datas, [], ...)` bằng `EXE(pyz, a.scripts, [], exclude_binaries=True, ...)` và thêm `COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, upx_exclude=[], name='QuangLuuStudio')`.

## Phát hiện phụ

- `main._cleanup_mei` từng xoá `sys._MEIPASS` = `current\_internal` của bản onedir → đã sửa (`core/frozen_paths.py`, bcfd0df).
- Log cũ cho thấy `%TEMP%` dạng 8.3 (`GRANTT~1`) → so sánh đường dẫn phải dùng `realpath` (35c6027).

## Điều chỉnh cần đưa vào Kế hoạch 4

1. `vpk pack --packTitle "Quang Lưu Studio"` (mục Apps đang hiện "QuangLuuStudio"); phiên bản hiển thị bỏ hậu tố prerelease.
2. Sau khi tự áp dụng lúc mở, app được Velopack **khởi động lại** với `VELOPACK_RESTART=true` — không coi đó là lần chạy đầu, không làm gì đặc biệt.
3. `UpdateManager(HttpSource(url, HttpOptions([], TimeoutMilliseconds=...)))` — đặt timeout cho mạng treo (spike chỉ thử trường hợp bị từ chối kết nối).
4. Thứ tự đầu `main.py`: `velopack.App().run()` phải chạy trước import nặng; hook cài/cập nhật/gỡ đều đi qua đường này.
5. CI không cần .NET SDK 8 riêng — `actions/setup-dotnet` bản bất kỳ ≥ 8 chạy được vpk 1.2.161 (đã chạy trên SDK 10).
6. Danh sách kiểm tay của Kế hoạch 4 phải có:
   - giao diện bản onedir: phát YouTube, SFX có tiếng, piper đọc, ghi âm 5 s rồi mở lại app;
   - cài + cập nhật trên máy ảo có **tên người dùng tiếng Việt có dấu và dấu cách** (`%LocalAppData%` Unicode);
   - quan sát có cửa sổ nào **lóe lên** khi thoát app lúc áp dụng cập nhật (4b chưa quan sát bằng mắt);
   - đo thời gian mở lần đầu khi có bản chờ so với mở thường (4d chưa có mốc so sánh).
7. Server (Kế hoạch 3): SHA256 so không phân biệt hoa thường (đã làm); feed của một bản có tài sản bản trước (import đã lọc theo `Version`).

## Kết luận

**ĐI TIẾP CÓ ĐIỀU KIỆN.** Câu 2–4 đạt đầy đủ; câu 1 đạt phần tự động (tự kiểm dò tone, thử tải, nhị phân đi kèm, `_internal` không bị xoá) nhưng **phần giao diện chưa kiểm** — điều kiện: mục 6 ở trên phải qua trước khi phát hành. Velopack đáp ứng mục tiêu "cài không UAC, cập nhật ngầm, không phải tắt app". Khởi động nhanh hơn rõ (1,4 s so với 7,9 s; lưu ý: onedir đo từ `%LocalAppData%`, onefile 1.8.0 từ Program Files, cả hai đều đã chạy trước đó — không phải lần lạnh).
