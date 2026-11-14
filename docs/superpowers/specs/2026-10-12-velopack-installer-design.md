# Thiết kế: chuyển bản cài sang Velopack (cài theo người dùng, cập nhật ngầm)

Ngày: 2026-10-12 · Nhánh: `feat/velopack-installer` · Phiên bản đích: 1.9.0

## 1. Bối cảnh và mục tiêu

**Vấn đề hiện tại.** Bản cài Inno Setup (`QuangLuuStudio_Setup.iss`) cài vào Program Files với quyền admin.
Khi cài/cập nhật, Restart Manager phải đóng app đang chạy nhưng hay thất bại, nên khách phải tự tắt hết:

- `closeEvent` bỏ qua lệnh đóng đầu tiên để đóng Studio One an toàn (`frontend_qt.py:4182-4186`) — Restart Manager coi là app không chịu đóng.
- PyInstaller onefile chạy 2 tiến trình `QuangLuuStudio.exe`; tiến trình mồi không có cửa sổ nên không đóng lịch sự được.
- Tiến trình con dạng console nằm trong `{app}` (ffmpeg, piper, qjs) giữ khoá file.
- Bộ cập nhật trong app: `sys.exit(0)` chạy trong luồng nền (`update_dialog.py:113`) nên app không thoát, hộp thoại treo "Đang tải xuống..."; mỗi lần cập nhật hiện UAC; `/RESTARTAPPLICATIONS` vô tác dụng.
- `app_config.json` được app ghi vào thư mục cài (`config.py:535-547`) — trong Program Files thì ghi thất bại im lặng.

Thực tế bản cài khó tới mức kỹ thuật viên thường phải cài qua UltraViewer.

**Mục tiêu (người dùng đã chốt).**

1. Khách **tự cài được, không cần kỹ thuật viên**: tải một file, mở, xong.
2. **Không bao giờ phải tắt app** để cài/cập nhật.
3. Cập nhật **ngầm, áp dụng ở lần mở sau** — không hộp thoại, không gián đoạn buổi hát.
4. Gỡ cài đặt **giữ dữ liệu** người dùng.

**Tiêu chí thành công.**

- Cài mới trên máy sạch: không UAC (trừ khi phải cài loopMIDI), không trang Next, app tự mở.
- Bản mới tới máy khi app đang chạy mà khách không thấy gì; lần mở sau chạy bản mới.
- Không còn trường hợp "phải đóng ứng dụng X mới cài được".

**Quyết định đã chốt.** Dùng **Velopack** (phương án A), không tự xây trên Inno (B), không MSIX (C, bắt buộc ký số).
**Chưa ký số** (phương án 3): chấp nhận cảnh báo SmartScreen ở lần cài đầu tiên; thiết kế chừa chỗ ký sau.
Không tìm cách tắt SmartScreen/Defender trên máy khách (không làm được trước khi bộ cài chạy, và bị coi là hành vi mã độc).

## 2. Cách cài và lần chạy đầu tiên

### Trải nghiệm khách

Tải `QuangLuuStudio-Setup.exe` → mở → (một lần) SmartScreen: "Thông tin thêm" → "Vẫn chạy" →
màn hình chờ có logo vài giây → app tự mở, có shortcut Desktop + Start Menu. Không UAC, không trang Next.

### Bố cục cài đặt

```
%LocalAppData%\QuangLuuStudio\
  Update.exe                 ← của Velopack
  current\                   ← bản build PyInstaller onedir, BỊ THAY TOÀN BỘ mỗi lần cập nhật
    QuangLuuStudio.exe
    _internal\ ...
    ffmpeg\  qjs.exe  tools\piper\  models\  sfx\
    studio_one\  cubase\
    setup_all.bat  setup_midi_ports.ps1  *.bat
    app_config.json          ← chỉ là bản MẶC ĐỊNH (chỉ đọc)
  packages\                  ← gói tải sẵn chờ áp dụng
```

Shortcut do Velopack tạo trỏ vào đường dẫn ổn định → cập nhật không làm hỏng shortcut/ghim taskbar.

**Quy tắc: không ghi gì vào `current\`.**

- `app_config.json`: bản trong `current\` là mặc định; phần người dùng đổi nằm ở
  `%APPDATA%\QuangLuuStudio\app_config_overrides.json` (cùng kiểu `accessibility_overrides.json`,
  `calibration_overrides.json`; không đặt trùng tên `app_config.json` vì ở chế độ dev DATA_DIR = gốc repo).
  Đọc = mặc định ← `app_config.json` đóng gói ← overrides. `AppConfig.save()` chỉ ghi **phần khác** so với
  mặc định + bản đóng gói (trừ các khoá calibration, đã có file riêng) — để bản cập nhật sau đổi mặc định vẫn có tác dụng.
  `configure_youtube_cookies.bat`, `tools/export_youtube_cookies.bat`, `tools/chan_doan/QLS_SuaPOToken.ps1` đổi đích ghi theo.
- Sửa luôn lỗi lưu đường dẫn SFX mặc định dạng `%TEMP%\_MEIxxxx\sfx\*.wav` vào `settings.json`
  (`ui/components/sfx_button_area.py:791-799`): lưu đường dẫn tương đối/tên file mặc định, phân giải lúc chạy.
- Dữ liệu khác (settings, bài hát, kích hoạt, cache, log, ytdlp, pot) vốn đã ở `%APPDATA%` / Documents — không đổi.

### Lần chạy đầu tiên (thay cho `[Code]` của Inno)

Hook cài đặt của Velopack chỉ có 30 giây và không được hiện UI, nên mọi việc sau-cài chuyển vào app.
App nhận biết lần chạy đầu qua `VELOPACK_FIRSTRUN` **hoặc** cờ `first_run_done` chưa có trong `settings.json`
(cờ là nguồn chính, để chạy lại được nếu lần đầu bị tắt ngang). Các bước, trong trình hướng dẫn hiện có:

1. Tạo file JSON mặc định (activation, settings, saved_songs, playlists, tone_cache, manual_timelines) — logic của
   `CreateDefaultDataFiles` — và chọn sẵn DAW theo logic `DawMacDinh` (chỉ Cubase → `cubase`, còn lại `studio_one`).
2. Chạy `setup_all.bat /auto` (cổng MIDI, Surface Studio One, script Cubase), hiện tiến trình trong trình hướng dẫn,
   đọc mã thoát (bit 1/2/4) như `ChayCaiDatTuDong` để báo việc còn lại.
3. Máy **chưa có loopMIDI**: màn hình giải thích "Cần cài loopMIDI (một lần) — Windows sẽ hỏi quyền" → chạy cài có
   nâng quyền (`runas`) → kiểm lại cổng. Không mạng/không winget → hướng dẫn + nút mở trang tải loopMIDI.
4. Phát hiện bản cũ trong Program Files (xem mục 4, đường 2).
5. Tiếp tục kích hoạt + phần còn lại của trình hướng dẫn cũ.
6. Ghi `first_run_done`.

### Gỡ cài đặt

Qua "Apps & features". Hook `--veloapp-uninstall` không hỏi gì, **giữ** `%APPDATA%\QuangLuuStudio` và
`Documents\QuangLuuStudio`. Thêm nút "Xoá dữ liệu" trong Cài đặt cho ai cần xoá.

## 3. Cập nhật ngầm

### Phía client

1. **Kiểm tra**: luồng nền ~1 phút sau khi app mở, rồi mỗi 6 giờ khi app còn chạy. Tôn trọng `update.auto_check`.
   Dùng `velopack.UpdateManager` với nguồn là feed của server (mục dưới).
2. **Tải**: Velopack tải delta nếu có, không thì gói đầy đủ, kiểm SHA256 theo feed. Chỉ **lưu sẵn**, không áp dụng.
   Lỗi tải → bỏ qua, lần kiểm sau thử lại.
3. **Áp dụng**:
   - Khi app tắt bình thường (đường thoát trong `main.py`, trước `os._exit`): nếu có bản đang chờ thì gọi
     `wait_exit_then_apply_updates` chế độ im lặng, **không** khởi động lại.
   - Dự phòng: tắt ngang/mất điện → Velopack tự áp dụng bản đang chờ ở lần mở sau (chậm thêm vài giây).
4. **Giao diện**: bỏ `ui/dialogs/update_dialog.py` (Cập nhật ngay / Để sau / Bỏ qua) và `update.skipped_version`.
   Cài đặt chỉ còn dòng trạng thái, ví dụ "Đang dùng 1.9.0 — đã tải sẵn 1.9.1, sẽ dùng ở lần mở sau". Không có nút khởi động lại.
5. `main.py`: gọi `velopack.App().run()` **đầu tiên**, trước mọi import nặng (Qt, numba), để xử lý hook `--veloapp-*` và thoát nhanh.
   Hook `--veloapp-*` không làm gì khác ngoài thoát mã 0.
6. Bỏ `core/updater/_installer.py`, `_downloader.py`, `_verifier.py` (Velopack đảm nhận). `_version_check.py` bỏ đường dự phòng GitHub.

### Phía server (`qlstudio.duckdns.org`, `server/app/routers/updates.py`)

- Feed mới: `GET /api/v1/updates/velopack/{fingerprint}/releases.win.json` và
  `GET /api/v1/updates/velopack/{fingerprint}/{file}` (gói `.nupkg` full/delta). Mã máy nằm trong **đường dẫn**
  vì Velopack nối tên file vào URL gốc. Feed sinh động theo kênh `stable`, `is_active`, `rollout_bucket(fingerprint)` so với `rollout_percent`.
- **Bỏ dự phòng GitHub** ở client: nó đang vượt qua `rollout_percent`/`is_active`. Server không trả lời → lần đó không cập nhật.
- **Rút bản lỗi**: `is_active=false` dừng phát tán; máy đã nhận thì phát hành bản vá số cao hơn (Velopack không hạ phiên bản).
- **Trang admin**: thay "upload installer" bằng **"Nhập từ GitHub Release"** theo số phiên bản — server tải các tài sản
  Velopack (feed, `.nupkg`, `Setup.exe`) của release đó về `storage_dir`; người dùng vẫn bấm phát hành và chỉnh phần trăm bằng tay.
- **Link tải cố định** cho lần cài đầu: `/tai-ve` → `Setup.exe` của bản ổn định mới nhất đang `is_active` (100%).
- Endpoint cũ `/api/v1/updates/check` + `/download` giữ lại **chỉ để phát bộ cài cầu nối** cho máy 1.8.x (mục 4).

## 4. Chuyển các máy đang cài bản cũ (≤ 1.8.x, Inno, Program Files)

### Đường 1 — qua bộ cập nhật cũ (đa số)

Máy 1.8.x hỏi server `/api/v1/updates/check` trước, **server không trả bản nào thì đọc GitHub `releases/latest`**
và lấy file `.exe` đầu tiên có chữ "setup" trong tên (`_version_check.py:79-157`). Bảng `app_versions` trên server
đang trống nên hiện tại mọi máy cập nhật qua GitHub. Vì vậy:

- Từ 1.9.0, **GitHub Release được đánh dấu prerelease** → bộ cập nhật cũ bỏ qua GitHub (nó bỏ prerelease), chỉ còn
  server quyết định, giữ được `rollout_percent` cho cả máy cũ. `vpk download github` dùng cờ `--pre`.
- `Setup.exe` của Velopack được **đổi tên không chứa "setup"** (`QuangLuuStudio-CaiDat.exe`) trước khi đính kèm,
  phòng trường hợp release nào đó lỡ không đánh dấu prerelease.
- Bộ cài cầu nối mang tên kiểu cũ `Setup_QuangLuuStudio_v<ver>.exe`, được **upload lên server qua trang admin như hiện nay**
  (`/admin/versions/upload`) — máy cũ nhận nó qua `/check` + `/download` theo `rollout_percent`.
- CI build bộ cài cầu nối ở **mọi bản** cho tới khi log server cho thấy không còn máy 1.8.x (cầu nối bọc `Setup.exe` của chính bản đó).

Bộ cài cầu nối (cùng `AppId {B8F3E2A1-...}`):

1. `CloseApplications=force` (app cũ không tự thoát do lỗi luồng nền).
2. Nếu `{app}\app_config.json` khác bản mặc định đóng gói → gộp phần khác biệt vào `%APPDATA%\QuangLuuStudio\app_config_overrides.json`
   (khoá đã có trong overrides thì giữ), dưới quyền người dùng gốc.
3. Chạy `Setup.exe` Velopack im lặng bằng `ExecAsOriginalUser` (cài vào `%LocalAppData%` của người hát, không phải của admin).
4. Xoá thư mục Program Files, shortcut cũ (Desktop, Start Menu, các mục `.bat`), và khoá gỡ cài đặt
   `HKLM\...\Uninstall\{AppId}_is1`. **Không** gọi `unins000.exe` cũ — nó hiện MsgBox "Xoá dữ liệu?" (không bị
   `/SUPPRESSMSGBOXES` chặn), khách bấm nhầm là mất dữ liệu.
5. Mở app mới (`%LocalAppData%\QuangLuuStudio\current\QuangLuuStudio.exe`) bằng `ExecAsOriginalUser`, vì bộ cập nhật
   cũ không tự mở lại app.

Đây là lần cuối khách gặp UAC và cảnh đóng app.

### Đường 2 — cài `Setup.exe` mới đè lên máy có bản cũ

Lần chạy đầu, app thấy khoá `{AppId}_is1` → hỏi "Phát hiện bản cũ trong Program Files — dọn dẹp?" → làm bước 2 và 4
ở trên qua một script PowerShell nâng quyền một lần. "Để sau" → hai bản cùng tồn tại không xung đột (dữ liệu chung
`%APPDATA%`), nhắc lại lần mở sau.

### Dữ liệu và công cụ chẩn đoán

- Dữ liệu không cần chuyển. Cache numba biên dịch lại một lần (đường dẫn đổi).
- `tools/chan_doan/*.ps1`: thêm `%LocalAppData%\QuangLuuStudio\current` vào danh sách dò; ngoại lệ Defender
  (`QLS_SuaLoi.ps1`, `QLS_SuaManHinhNhung.ps1`) trỏ cả thư mục `%LocalAppData%\QuangLuuStudio` thay vì exe cụ thể.
- `.bat` dùng `%~dp0QuangLuuStudio.exe` vẫn đúng vì nằm cạnh exe trong `current\`. Shortcut Start Menu tới
  `configure_youtube_cookies.bat` / `kiem_tra_tone.bat` chuyển thành nút/lệnh trong app (Velopack chỉ tạo shortcut cho exe chính).

## 5. Build, CI, spike, kiểm thử

### Bước 0 — spike (~1 ngày, code bỏ đi)

Trả lời trước khi làm thật:

1. Build PyInstaller **onedir** (Python 3.13 `.venv`, numpy<2.3, Qt) chạy đủ: audio, numba, ffmpeg, piper.
2. `vpk pack` ra `Setup.exe` cài vào `%LocalAppData%` không UAC.
3. Gói `velopack` Python (1.2.x) nhận đúng hook `--veloapp-*` và `VELOPACK_FIRSTRUN` qua `App().run()`.
4. Tải bản mới khi app đang chạy → `wait_exit_then_apply_updates` im lặng áp dụng được; bản chờ tự áp dụng lần mở sau; delta hoạt động.
5. Gói do app tự tải không bị SmartScreen.
6. Defender không báo nhầm bản onedir / `Update.exe`.

Câu 1–4 có câu nào "không" → **dừng, báo người dùng** trước khi đi tiếp.

### CI (`.github/workflows/release.yml`)

- `actions/setup-dotnet` + `dotnet tool install -g vpk` ghim **cùng phiên bản** với `velopack` trong requirements.
- PyInstaller onedir (`QuangLuuStudio.spec`: thêm `COLLECT`).
- `vpk download github --pre` (lấy bản trước để tạo delta) → `vpk pack --packId QuangLuuStudio --packVersion <ver>
  --packDir dist\QuangLuuStudio --mainExe QuangLuuStudio.exe --icon app_icon.ico` → đổi tên `*-Setup.exe` thành
  `QuangLuuStudio-CaiDat.exe` → đính kèm GitHub Release **dạng prerelease** (xem mục 4).
- Chừa `--signParams` (tắt) cho chữ ký số sau này.
- Build thêm bộ cài cầu nối Inno (`QuangLuuStudio_Bridge.iss`) ở mọi bản cho tới khi hết máy 1.8.x.
- `sync_version.py` cập nhật theo (bỏ đồng bộ vào `.iss` chính khi Inno không còn là bộ cài chính).
- Cập nhật memory quy trình phát hành và build máy dev.

### Kiểm thử tự động

- `app_config.json`: gộp mặc định + bản người dùng; bản người dùng sống qua cập nhật; `save()` chỉ ghi `%APPDATA%`.
- Lần chạy đầu: chọn DAW, tạo file mặc định, cờ `first_run_done`, phát hiện bản cũ.
- Server: feed lọc `is_active` + `rollout_percent` theo fingerprint; chỉ trả bản đã nhập; `/tai-ve` trỏ bản đúng.
- Lịch kiểm tra cập nhật (1 phút, 6 giờ, `auto_check`).

### Kiểm thử tay (máy dev + máy ảo Windows sạch)

1. Cài mới: có loopMIDI / chưa có loopMIDI.
2. 1.8.0 → 1.9.0 qua bộ cài cầu nối.
3. `Setup.exe` đè lên máy có bản cũ (đường 2).
4. 1.9.0 → 1.9.1 **khi đang hát**, tắt, mở lại.
5. Rút điện khi đang có bản chờ.
6. Gỡ cài đặt → dữ liệu còn.
7. Trọn vòng trên một máy khách Cubase qua UltraViewer.

### Phát hành dần

1.9.0 (cầu nối) bắt đầu 10% → theo dõi log → mở rộng.

## 6. Ngoài phạm vi

- Chữ ký số (chừa chỗ trong CI).
- Thay loopMIDI bằng Windows MIDI Services (Windows 11) để bỏ UAC cuối cùng.
- Hướng dẫn có ảnh cho lần cài đầu (làm sau khi giao diện đã chốt).
- Biến thể Heavy (đã tạm bỏ từ 2026-10-04).
