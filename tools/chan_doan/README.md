# Bộ chẩn đoán & sửa lỗi máy khách — Quang Lưu Studio

Các tệp trong thư mục này chạy được trên **mọi máy Windows 10/11, không cần cài Python**
(dùng Windows PowerShell 5.1 có sẵn trong Windows).

| Tệp | Vai trò |
|---|---|
| `ChanDoan.bat` | Khách bấm đúp để **kiểm tra** — chỉ ĐỌC, không sửa gì |
| `QLS_ChanDoan.ps1` | Toàn bộ phần kiểm tra |
| `SuaLoi.bat` | Khách bấm đúp để **sửa** những lỗi chẩn đoán tìm ra |
| `QLS_SuaLoi.ps1` | Toàn bộ phần sửa lỗi |
| `VaNhanh172.bat` | **Chỉ dùng cho máy đang cài bản 1.7.2** — xem mục dưới |
| `QLS_VaNhanh172.ps1` | Toàn bộ phần vá nhanh 1.7.2 |

> Các tệp phải nằm **cùng một thư mục**. Gửi cho khách dạng file nén rồi bảo giải nén ra Desktop.
> Quy trình chuẩn: chạy `ChanDoan.bat` → gửi báo cáo cho kỹ thuật → chạy `SuaLoi.bat` → chạy lại
> `ChanDoan.bat` để xác nhận đã sạch.

## Cách dùng

**Khách hàng:** bấm đúp `ChanDoan.bat` → chờ ~30 giây → file báo cáo `QLS_ChanDoan_<TÊNMÁY>_<ngày giờ>.txt`
tự mở bằng Notepad và được lưu trên Desktop → gửi file đó cho kỹ thuật.

**Kỹ thuật (dòng lệnh):**

```bat
powershell -ExecutionPolicy Bypass -File QLS_ChanDoan.ps1 [tham số]
```

| Tham số | Ý nghĩa |
|---|---|
| `-Zip` | Gói kèm `app.log`, `errors.log`, `settings.json` thành `.zip` để khách gửi một lần |
| `-Offline` | Bỏ qua các kiểm tra cần Internet |
| `-AppDir "D:\..."` | Chỉ định thư mục cài đặt khi app cài ở nơi lạ |
| `-OutFile "C:\...\bc.txt"` | Đổi nơi lưu báo cáo |
| `-NoOpen` | Không tự mở Notepad sau khi chạy |

Mã thoát: `0` = sạch, `1` = có cảnh báo, `2` = có lỗi nặng (tiện gọi từ script khác).

## Những gì được kiểm tra

1. **Máy** — Windows/bit, RAM, ổ đĩa, màn hình + tỉ lệ hiển thị, thư viện Visual C++, múi giờ.
2. **Bản cài** — vị trí cài, phiên bản exe so với registry, biến thể Nặng/Nhẹ, tệp đi kèm bắt buộc.
3. **`app_config.json`** — cú pháp JSON, **CC trùng nhau**, CC ngoài dải 0–127, lệch giữa
   `mode_config` ↔ `midi_cc`, lệch `scale_values` ↔ `scale_midi_map`, CC mute phụ đè CC chính,
   file bị lưu sai bảng mã (tên chế độ tiếng Việt hỏng).
4. **Dữ liệu người dùng** — mọi tệp JSON trong `%APPDATA%\QuangLuuStudio` còn đọc được không,
   file tạm còn sót (dấu hiệu tắt máy đột ngột), quyền ghi, **vị trí cửa sổ đã lưu nằm ngoài màn hình**,
   chỉ số màn hình phụ không tồn tại, đường dẫn Studio One/trình duyệt đã hỏng, chế độ khách bật mà
   thiếu PIN, bật phục hồi bản mẫu mà chưa chốt bản mẫu nào, Defender chặn ghi vào Documents.
5. **MIDI** — loopMIDI đã cài / đang chạy / tự khởi động, cổng khai báo trong registry, và
   **liệt kê cổng MIDI thật trên máy qua `winmm`** để khẳng định cổng có tồn tại hay không.
6. **Studio One** — đã cài chưa, Surface đã chép vào `User Devices` chưa, Surface trong Studio One
   có **cũ hơn** bản đi kèm app không, và **đối chiếu từng số CC** giữa `app_config.json` với Surface.
7. **Âm thanh** — dịch vụ Windows Audio, danh sách thiết bị phát/thu, **quyền micro** (mục hay chặn
   ứng dụng `.exe`), phần mềm chiếm âm thanh độc quyền (VoiceMeeter/OBS/ASIO4ALL).
8. **FFmpeg, trình duyệt, CDP, yt-dlp** — dò FFmpeg đúng thứ tự như app, Chrome/Edge, cổng 9222,
   shortcut đã gắn cờ `--remote-debugging-port` chưa, và **tuổi của bản yt-dlp** đang dùng
   (trên 120 ngày là báo LỖI — xem mục yt-dlp bên dưới).
9. **Mạng & bản quyền** — máy chủ license, độ trễ, **lệch giờ máy so với máy chủ** (nguyên nhân
   kinh điển làm bản quyền bị coi là hết hạn), DNS, proxy, GitHub, và giải mã token trong
   `activation.json` để xem gói, hạn bản quyền, hạn chạy offline, vân tay máy có khớp không.
10. **Tiến trình & bảo mật** — chạy trùng 2 bản app, RAM app đang dùng, diệt virus của hãng khác.
11. **Nhật ký** — đếm lỗi trong 24 giờ / 7 ngày, gom nhóm lỗi lặp nhiều nhất, đính 60 dòng
    `errors.log` gần nhất vào cuối báo cáo, báo cáo sự cố còn kẹt chưa gửi được.

## Script sửa lỗi (`SuaLoi.bat`)

Chỉ sửa những gì an toàn và hoàn tác được. **Mọi tệp bị sửa đều được sao lưu trước** vào
`%APPDATA%\QuangLuuStudio\backup_sualoi\<ngày giờ>\` — muốn hoàn tác thì chép ngược về.
Mặc định hỏi C/K từng mục.

| Tham số | Ý nghĩa |
|---|---|
| *(không có)* | Hỏi trước từng mục |
| `-Xem` | Chỉ liệt kê sẽ sửa gì, **không đụng vào máy** |
| `-Auto` | Sửa hết, không hỏi |
| `-CookieFile "C:\...\cookies.txt"` | Nạp cookie YouTube (xem bên dưới) |
| `-ChiYtDlp` | **Chỉ** nạp bản yt-dlp mới, các mục khác chỉ xem |
| `-Offline` | Bỏ qua mục cần Internet (cập nhật yt-dlp) |
| `-AppDir "D:\..."` | Thư mục cài đặt khi app cài ở nơi lạ |

Các mục nó xử lý:

1. **Đóng app trước khi sửa** — bắt buộc, vì dashboard ghi đè toàn bộ `settings.json` lúc thoát;
   sửa khi app đang chạy thì thay đổi bị bản trong RAM xoá mất. Đóng nhẹ nhàng trước
   (`CloseMainWindow`), hết 10 giây mới ép tắt.
2. **Tệp JSON hỏng** → đổi tên `.bak-<ngày giờ>` để app tạo lại; **tệp rác `.tmp_*`** → xoá.
3. **`settings.json`**: `browser_path` dính tham số hoặc trỏ trình duyệt đã gỡ → trỏ lại
   Chrome/Edge/Brave có thật; `window_geometry` ngoài màn hình → xoá; `display_monitor_index`
   vượt số màn hình → về 0; `studio_one_path` hỏng → lấy `.song` trong thư mục cài đặt;
   chế độ khách bật mà không có PIN → gỡ khoá.
4. **Cookie YouTube** (lỗi *"Sign in to confirm you're not a bot"*, *403 Forbidden*).
4B. **Nạp bản yt-dlp mới** — xem mục riêng bên dưới.
5. **loopMIDI**: thêm cổng vào registry + khởi động lại loopMIDI để nhận cổng, bật tự khởi động
   cùng Windows, mở `setup_all.bat` nếu chưa cài.
6. **Surface Studio One** thiếu hoặc cũ hơn bản đi kèm app → chép bản mới vào `User Devices`.
7. **Quyền micro** bị Deny → đặt lại Allow (kể cả mục `NonPackaged` dành cho app `.exe`);
   dịch vụ Windows Audio dừng → khởi động; Controlled Folder Access chặn ghi Documents →
   thêm ngoại lệ (cần Admin).

### Về cookie YouTube — mục duy nhất không tự sửa được hoàn toàn

Chrome/Edge/Brave từ bản 127 mã hoá cookie theo kiểu App-Bound; yt-dlp báo
`Failed to decrypt with DPAPI` và **không đọc được, đóng trình duyệt cũng không chữa được**.
Hai lối ra:

1. **Cài Firefox**, đăng nhập YouTube một lần → chạy `SuaLoi.bat`, nó tự đặt
   `youtube_cookie_browser = firefox` (Firefox không khoá tệp cookie, yt-dlp đọc được).
2. **Xuất `cookies.txt`**: trên Chrome cài tiện ích *Get cookies.txt LOCALLY*, mở `youtube.com`
   (đã đăng nhập) → Export → rồi chạy:
   ```bat
   SuaLoi.bat -CookieFile "C:\Users\<tên>\Downloads\cookies.txt"
   ```
   Script kiểm tra tệp đúng định dạng Netscape và có dòng `youtube.com`, chép vào
   `%APPDATA%\QuangLuuStudio\youtube_cookies.txt` rồi đặt `youtube_cookie_file` trong
   `app_config.json`. Cookie sống được vài tháng; lỗi quay lại thì xuất tệp mới.

### Về PO Token — vì sao cookie đúng mà vẫn "Requested format is not available"

Từ 2025 YouTube đòi **GVS PO Token** cho mọi client họ `web`/`tv`. Không có token
thì yt-dlp bỏ hết định dạng → `Requested format is not available`; ép giữ lại
(`formats=missing_pot`) thì tải về dính `403 Forbidden` rồi
`ffmpeg exited with code 3436169992`. Đúng chuỗi lỗi trong nhật ký máy khách.

Cookie **không** chữa được, thậm chí làm hẹp đường: yt-dlp loại các client
`android`, `android_vr`, `tv_simply` khi có cookie (`SUPPORTS_COOKIES = False`),
chỉ còn lại đúng nhóm client cần PO Token.

Lối thoát của bản 1.7.2: **lần thử KHÔNG cookie chạy trước với client
`android`/`android_vr`/`tv_simply`** — nhóm này không cần PO Token. Đo ngày
17/08/2026: 9/9 lần thành công trong ~2,5 giây, không cần cookie nào.

> ⚠️ **Đường đó đã chết ngày 18/08/2026.** YouTube bật SABR-only cho client
> android: nó vẫn *bóc được thông tin* nhưng *không tải nổi* — biểu hiện là
> `403 Forbidden`, `ffmpeg exited with code 3436169992`, hoặc
> `missing a URL ... SABR-only` (yt-dlp #12482). Ba thông báo, một nguyên nhân.

**Bản 1.7.3 sửa tận gốc**: tự sinh PO Token bằng `bgutil-pot.exe` (không cần tài
khoản), gói kèm runtime JavaScript `qjs.exe` và ffmpeg. Xem
`docs/PLAN_YOUTUBE_NO_ACCOUNT.md`.

### Vá nhanh cho máy CHƯA cài lại được — `VaNhanh172.bat`

Dành cho quán đang chạy 1.7.2 cần tải được lại ngay. Script tải ~100 MB rồi đặt
`bgutil-pot.exe` + `deno.exe` vào PATH người dùng, plugin vào thư mục plugin mặc
định của yt-dlp, nạp sẵn script giải n-challenge, và khoá
`youtube_player_clients` trong `app_config.json`.

```
VaNhanh172.bat            # vá
VaNhanh172.bat -GoBo      # gỡ bỏ, trả lại nguyên trạng
VaNhanh172.bat -KhongHoi  # không hỏi, dùng khi triển khai hàng loạt
```

Ba điều phải nói với khách trước khi chạy:

1. Script **tắt tự cập nhật yt-dlp**. Bắt buộc — script giải n-challenge nạp sẵn
   gắn chặt với số hiệu yt-dlp; để nó tự cập nhật thì vài hôm sau hỏng lại âm
   thầm. Đổi lại, máy đó đứng yên ở một bản yt-dlp cũ dần.
2. Nó **ghim cứng một client**. YouTube đổi lần nữa là phải vá lại bằng tay.
3. Đây là **cầu tạm**. Cài 1.7.3 mới là đường chính; khi cài, khoá client tự
   được bỏ qua (nhờ cờ `youtube_player_clients_hotfix`), không phải dọn tay.

Muốn ép client bằng tay trên một máy cụ thể, thêm vào `app_config.json`:

```json
"youtube_player_clients": ["web_safari"]
```

### Về yt-dlp cũ — thủ phạm còn lại khi cookie đã đúng

Triệu chứng: log có `Sign in to confirm you're not a bot` rồi ngay sau đó
`Requested format is not available`. Cookie **đã** qua được cửa chống bot (nếu
không thì lỗi thứ hai đã không xuất hiện), nhưng bản yt-dlp trong app quá cũ nên
không bóc được định dạng nào để tải.

Nguyên nhân gốc: yt-dlp bị đóng băng trong `.exe` từ lúc build, còn YouTube đổi
cơ chế phát video gần như hàng tháng. Ví dụ thật (17/08/2026, cùng một video):

| yt-dlp | Số định dạng lấy được | Có định dạng chỉ-tiếng |
|---|---|---|
| 2026.02.04 (bản build 11/08) | 5 | 0 |
| 2026.07.04 | 27 | 4 |

Cách chữa:

```bat
SuaLoi.bat -ChiYtDlp
```

Script tải wheel yt-dlp mới nhất từ PyPI (~3 MB), **đối chiếu SHA256**, giải nén
vào `%APPDATA%\QuangLuuStudio\ytdlp\yt_dlp\`. App **1.7.1 trở lên** tự ưu tiên bản
này (`core/ytdlp_update.py`) và cũng tự kiểm tra bản mới 24 giờ/lần — tắt bằng
`"ytdlp_auto_update": false` trong `app_config.json`. Bản app cũ hơn **không đọc
được** thư mục này, phải cài lại app mới.

## Ghi chú khi sửa script

- Tệp `.ps1` phải lưu ở dạng **UTF-8 có BOM**, nếu không Windows PowerShell 5.1 đọc sai tiếng Việt
  và báo lỗi cú pháp hàng loạt. Tệp `.bat` giữ **thuần ASCII**.
- Ngược lại, mọi tệp JSON script GHI RA (`settings.json`, `app_config.json`) phải là UTF-8
  **KHÔNG BOM** — app đọc bằng `open(..., encoding="utf-8")`, gặp BOM là `json.load` vỡ.
  Dùng hàm `Save-JsonFile` (đã tự bỏ BOM, trả `\uXXXX` về ký tự thật và parse lại để kiểm tra).
- Hướng thiết bị âm thanh phải đọc từ `InstanceId` (`{0.0.0.…}` = phát, `{0.0.1.…}` = thu),
  **không** đoán theo tên: "Digital Microphone (…)" vẫn là thiết bị phát.
- Đếm số bản app đang chạy phải lọc tiến trình gốc (cha không cùng tên) — bản đóng gói one-file
  luôn sinh 2 tiến trình cùng tên cho mỗi lần mở.
- `BUNDLED_YTDLP_VERSION` trong `core/ytdlp_update.py` phải khớp bản yt-dlp thật sự
  bị gói vào exe — `sync_version.py` tự ghi lại lúc build, đừng sửa tay.
- Các hằng số ở đầu script (`$DEFAULT_SERVER`, `$INNO_APPID`, `$CDP_PORT`, `$DATA_FOLDER`) phải khớp
  với `core/config.py`, `core/version.py` và `QuangLuuStudio_Setup.iss` — đổi bên kia thì sửa cả đây.
- Kiểm tra cú pháp nhanh trước khi phát hành:
  ```powershell
  $e=$null; [System.Management.Automation.Language.Parser]::ParseFile("QLS_ChanDoan.ps1",[ref]$null,[ref]$e); $e
  ```
