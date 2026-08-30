# Tải YouTube không cần tài khoản (v1.7.3)

> Trạng thái: **ĐÃ TRIỂN KHAI** — 18/08/2026.
> Thay thế `docs/POT_PROVIDER_INTEGRATION_PLAN.md` (bản 2026-04-25 đã hoãn vì
> lúc đó bgutil chỉ có mã Node.js, chưa có binary Windows).

## Vấn đề

Máy khách hát karaoke phần lớn **không đăng nhập YouTube**, nên mọi đường dựa vào
cookie đều là ngõ cụt: không có cookie để lấy, hoặc Chrome ≥127 khoá cookie DB
bằng App-Bound Encryption (chi tiết + số liệu đo:
`docs/COOKIE_TRINH_DUYET_VA_CDP.md` — **đóng trình duyệt KHÔNG cứu được**).
Trước 1.7.3 app chống đỡ bằng cách ép
`player_client = android/android_vr/tv_simply` cho lượt không cookie — đo
17/08/2026 được 9/9 lần thành công, nhưng đó là mẹo đang mục:

| Trụ thiếu | Hậu quả |
|---|---|
| **PO Token** | Bảng chính thức của yt-dlp (08/2026): `android`/`ios` nay đòi **cả GVS lẫn Player PO Token**, `tv_simply` đòi GVS, `android_vr` chỉ còn format 18 (yt-dlp #17348, #16150). Thiếu token → "Requested format is not available", ép lấy thì 403. |
| **Runtime JavaScript** | Từ cuối 2025 yt-dlp **bắt buộc** runtime JS ngoài để giải n-sig (yt-dlp #15012). App không gói runtime nào → link tải bị bóp băng thông / 403. |
| **ffmpeg** | Không nằm trong bộ cài; chỉ `setup_all.bat` tải về `%LOCALAPPDATA%`. Máy cài lỗi mạng → mất hẳn chấm điểm + dò tone. |

## Giải pháp

Ba trụ độc lập, thiếu trụ nào cũng chỉ **suy giảm** chứ không sập.

### 1. Runtime JavaScript — `qjs.exe` (QuickJS-ng, ~2 MB, MIT)

- Tải lúc build bởi `tools/fetch_build_binaries.py` (ghim phiên bản + SHA-256)
  → `binaries/qjs.exe` → bộ cài chép vào `{app}\qjs.exe`.
- `core/utils.py::find_js_runtime()` dò: `app_config["js_runtime_path"]` →
  cạnh exe → `{app}\bin\` → PATH.
- `core/ytdlp_support.py::_apply_js_runtimes()` khai báo cho yt-dlp:
  `js_runtimes = {"deno": {}, "quickjs": {"path": ...}}`.
  **Là DICT, không phải list** — khác cú pháp CLI `--js-runtimes deno:/path`;
  truyền list vào là yt-dlp ném `ValueError`. Giữ `deno` ở đầu để máy nào có
  sẵn Deno thì dùng bản tốt hơn.
- Script giải challenge (`yt-dlp-ejs`) đi kèm qua `yt-dlp[default]` trong
  `requirements.txt` + `collect_all('yt_dlp_ejs')` trong `.spec`, nên **không
  phải tải từ npm lúc chạy**. `build_installer*.bat` kiểm tra bước này và
  dừng build nếu thiếu.

Chọn QuickJS-ng thay Deno vì Deno nặng ~40 MB — phá yêu cầu "bản Nhẹ phải nhẹ".

### 2. PO Token — `bgutil-pot.exe` bản Rust (~44 MB, GPL-3.0)

PO Token **không phải cookie**: nó chứng minh "yêu cầu đến từ trình duyệt thật",
không chứng minh "tôi là ai" — nên sinh được mà không cần tài khoản nào.

- `core/pot_provider.py` tải **lúc chạy** (không gói vào bộ cài) vào
  `%APPDATA%\QuangLuuStudio\pot\`, ghim phiên bản + SHA-256, tráo thư mục nguyên
  tử — cùng khuôn với `core/ytdlp_update.py`.
- **Vì sao tải lúc chạy chứ không đóng gói:** bgutil là GPL-3.0; đóng gói vào bộ
  cài của một sản phẩm thương mại sẽ kéo theo nghĩa vụ GPL. Tải về máy khách rồi
  gọi như một chương trình riêng thì không phát hành lại mã GPL nào. Tiện thể
  cũng không làm phình bộ cài và vá được mà không cần cài lại app.
- **Chế độ CLI, không phải HTTP server**: yt-dlp gọi binary mỗi lần cần token.
  Không tiến trình nền → không tranh cổng 4416, không tiến trình mồ côi khi app
  tắt đột ngột.
- Bố cục thư mục plugin **phải** là `pot/plugins/bgutil/yt_dlp_plugins/...`:
  yt-dlp duyệt các thư mục **con** của đường dẫn khai báo rồi mới tìm
  `yt_dlp_plugins/` bên trong (`yt_dlp/plugins.py::candidate_plugin_paths`).
  Đổ thẳng `yt_dlp_plugins/` vào `pot/plugins/` là plugin **không được nạp** mà
  cũng không báo lỗi gì.
- Thư mục plugin được chèn **trước** `"default"` trong
  `yt_dlp.globals.plugin_dirs`, phòng máy khách lỡ có bản bgutil khác cài sẵn
  (trùng tên module `getpot_bgutil*`) sẽ che mất bản của app.
- Tải nền ở `main.py` lúc khởi động (`maybe_auto_install`, thử lại tối đa
  24 h/lần). Thất bại → plugin trả `PoTokenProviderRejectedRequest`, thang client
  lùi về đường android như cũ.

### 3. ffmpeg đi kèm bộ cài

- `tools/fetch_build_binaries.py` tải bản **LGPL shared** của BtbN, chỉ lấy
  `bin/` và bỏ `ffplay.exe` → `binaries/ffmpeg/` (9 file, ~130 MB chưa nén,
  **~35 MB sau nén LZMA** trong bộ cài).
- Bộ cài chép vào `{app}\ffmpeg\`; `core/utils.py::find_ffmpeg()` dò nấc 5.
- Giữ nguyên bước tải ffmpeg trong `setup_all.bat` làm lưới an toàn cho máy cũ.

### 4. Thang client theo *mục đích*

`run_with_auth_fallback(..., purpose=...)` quyết định thứ tự thử ở lượt
**không cookie**. Đo 18/08/2026, có PO Token, không cookie, cùng một video:

| Client | Số định dạng | Progressive | Tối đa | Thời gian |
|---|---|---|---|---|
| mặc định | 37 | 7 | 2160p | 7,9 s |
| `web_safari` | 11 | 7 | 1080p | 11,2 s |
| `mweb` | 34 | 1 | 2160p | 9,3 s |
| `android` | 5 | 1 | 360p | **2,2 s** |
| `tv` | — | — | — | hỏng ("page needs to be reloaded" / "DRM protected") |

- `purpose="audio"` (chấm điểm, dò tone, lấy tiêu đề):
  `android,android_vr` → mặc định → `web_safari,mweb`.
- `purpose="video"` (trình phát nhúng): mặc định → `web_safari,mweb` →
  `android,android_vr`. Cần luồng progressive nét; android bị ghim 360p.
- Không có PO Token: `android,android_vr` → mặc định.
- `app_config["youtube_player_clients"]` và danh sách do caller đặt trong
  `extractor_args` vẫn **thắng tất cả**.

#### ⚠️ `tv_simply` phải nằm ngoài nấc 1

`tv_simply` đòi GVS PO Token. Khi máy đã có bộ sinh token, để nó ở nấc 1 khiến
yt-dlp gọi bgutil ở **mọi lần bóc thông tin** — mà dò tone thì chạy trên từng
bài. Đo trên cùng 3 video, tiến trình lạnh:

| Nấc 1 | Lần 1 | Lần 2 | Lần 3 | Định dạng audio thu được |
|---|---|---|---|---|
| `android, android_vr, tv_simply` | 11,5 s | 12,6 s | 11,4 s | itag 140 @129,5k / 251 @130,9k |
| `android, android_vr` | **2,6 s** | **1,8 s** | **1,9 s** | *y hệt* |

Token **không** được dùng lại giữa các lần gọi (từ 2026 token gắn theo từng
video), nên đây là +9 giây **mỗi bài**, đổi lấy đúng con số 0. Thiếu token thì
`tv_simply` vốn cũng vô dụng; có token thì nấc `web_safari,mweb` đã lo.

### 5. Hai lỗi được vá cùng lúc

1. **Danh sách client của caller bị xoá.** `_apply_player_clients` gọi
   `youtube.pop("player_client")` ở mọi lượt, nên tham số
   `extractor_args={"youtube": {"player_client": [...]}}` mà trình phát nhúng
   truyền vào (`frontend_qt.py`) **chưa bao giờ có hiệu lực** — và danh sách đó
   còn chứa `tv_embedded`, thứ yt-dlp 2026.07 đã bỏ.
2. **Lỗi lạ ở nấc đầu giết cả chuỗi.** `_run_attempts` `raise` ngay với mọi
   `DownloadError` không nhận dạng được. Client `tv` trả "The page needs to be
   reloaded" là mất luôn các nấc sau. Nay chỉ `TERMINAL_MARKERS` (video riêng
   tư, đã gỡ, chặn quốc gia…) mới dừng ngay; lỗi lạ được thử tiếp, nấc cuối mới
   ném.

### 6. Xử lý lỗi 403 / ffmpeg sập / SABR

Ba thông báo tưởng khác nhau nhưng là **cùng một chuyện**: yt-dlp bóc được video
và có danh sách định dạng, nhưng **link tải không dùng được**.

| Thông báo | Thực chất |
|---|---|
| `HTTP Error 403: Forbidden` | link cấp cho client/PO Token khác |
| `ffmpeg exited with code 3436169992` | tải 50 giây đầu (`download_ranges`) giao cho ffmpeg; link rỗng/403 làm ffmpeg sập. **Không phải lỗi ffmpeg** — thử cả 8.0.1 lẫn 9.0.1 sập y hệt |
| `missing a URL … SABR-only streaming experiment` | YouTube trả định dạng **không kèm link** (yt-dlp #12482) |

Đo 18/08/2026: client `android` dính cả ba — nó **vẫn bóc được thông tin nhưng
đã không tải nổi**. Nấc `web_safari,mweb` (cần PO Token) mới tải được.

Xử lý trong `core/ytdlp_support.py`:

1. `STREAM_FORBIDDEN_MARKERS` gom cả ba → nấc sau được thử tiếp, và thông báo
   cuối cùng là `_build_forbidden_error_message()` có hướng dẫn (nêu luôn trạng
   thái bộ sinh PO Token trên máy), thay vì ném thẳng
   `ERROR: ... HTTP Error 403: Forbidden` vô nghĩa cho khách.
2. **Không** kích hoạt lượt `formats=missing_pot` cho nhóm này — nới lọc PO Token
   chính là thứ **đẻ ra** 403, vừa vô ích vừa bắt khách chờ gấp đôi.
3. `_YtdlpLogger` đẩy mọi thông báo của yt-dlp vào nhật ký thay vì stderr. Nấc
   trượt là chuyện bình thường của thang thử, nhưng `quiet=True` **không** chặn
   được lỗi (nó đi qua `trouble()` chứ không qua `to_screen()`), nên trước đây
   khách thấy màn hình đầy chữ `ERROR` đỏ trong lúc app đang chạy đúng.
4. `_short_reason(exc)` in một dòng gọn cho từng nấc trượt — chính nó làm lộ ra
   `ffmpeg exited with code` đứng sau 403.

### 7. Ảnh hưởng tới dò tone (đo 18/08/2026, không cookie, tiến trình lạnh)

| | Bóc thông tin | Tải 50 s + ra WAV | Kết quả |
|---|---|---|---|
| Tắt PO Token (= hành vi 1.7.2) | 2,5 s | 21,7 s | **403 Forbidden — 0 MB, dò tone hỏng** |
| Bật PO Token (1.7.3) | 2,5 s | 22,7 s | **9,15 MB WAV, có tiêu đề** |

Nói cách khác: trên IP thử nghiệm, đường android **vẫn bóc được thông tin nhưng
đã không tải nổi audio nữa** — đúng như dự báo của yt-dlp #17348. PO Token là
thứ cứu bước tải. Thời gian gần như không đổi; bước phân tích cao độ không bị
đụng tới vì file WAV đưa vào là như nhau (cùng itag nguồn).

## Vá nhanh cho máy đang cài 1.7.2

`tools/chan_doan/VaNhanh172.bat` — cho khách tải được lại **ngay**, không phải cài
lại app. Nó dùng những cửa hậu mà 1.7.2 vốn đã có:

| Đặt vào đâu | Cái gì | Vì sao chỗ đó |
|---|---|---|
| `%APPDATA%\yt-dlp\plugins\bgutil\` | plugin bgutil (6 KB) | thư mục plugin **mặc định** của yt-dlp — không cần app biết gì |
| `%LOCALAPPDATA%\QuangLuuStudio\bin\` + PATH người dùng | `bgutil-pot.exe` | plugin tự tìm `bgutil-pot` trên PATH |
| cùng thư mục trên | `deno.exe` (93 MB) | 1.7.2 **chỉ bật `deno`**, không bật quickjs — `qjs.exe` vô dụng với nó |
| bộ nhớ đệm chung của yt-dlp | script giải n-challenge | 1.7.2 không mang theo `yt_dlp_ejs` và cũng không tự tải; nạp một lần bằng `yt-dlp.exe --remote-components ejs:github` |
| `app_config.json` | `youtube_player_clients = ["web_safari"]` | thang của 1.7.2 chỉ thử android → mặc định, **cả hai đều đã hỏng** |

Đo trên bản cài giả 1.7.2 (chặn `yt_dlp_ejs` cho đúng như exe thật):

```
trước khi vá : nấc 1 android FAIL, nấc 2 mặc định FAIL  → không tải được gì
sau khi vá   : ép web_safari  OK 3,9 s, 3,37 MB
```

### Hạn chế — đọc trước khi triển khai hàng loạt

1. **Tải ~100 MB/máy** và **sửa PATH người dùng**.
2. Script **tắt `ytdlp_auto_update`**. Bắt buộc: script giải n-challenge nạp sẵn
   gắn chặt với số hiệu yt-dlp; để nó tự cập nhật 24 h/lần thì vài hôm sau bộ đệm
   lệch phiên bản và **hỏng lại âm thầm**. Đổi lại, máy đó đứng yên ở
   yt-dlp 2026.07.04 — càng để lâu càng rủi ro.
3. Khoá `youtube_player_clients` là **ghim cứng một client**. YouTube đổi lần nữa
   là phải vá lại bằng tay.
4. Bộ cài đánh dấu `app_config.json` là `onlyifdoesntexist`, nên khoá này **sống
   sót** qua lần cài 1.7.3. Vì vậy script ghi kèm cờ
   `youtube_player_clients_hotfix`, và `_configured_player_clients()` của 1.7.3
   thấy cờ đó thì **bỏ qua khoá** để thang client thông minh hoạt động lại.
   Muốn dọn sạch hoàn toàn: `VaNhanh172.bat -GoBo`.

Nói gọn: bản vá là **cầu tạm** cho quán chưa cài lại được ngay. Cài 1.7.3 mới là
đường chính — mọi mảnh ở trên đã nằm sẵn trong đó và được thử tự động.

## Cấu hình

Trong `app_config.json` (mặc định **cũng nằm trong `core/config.py`** — bộ cài
đánh dấu file này `onlyifdoesntexist` nên máy nâng cấp không nhận khoá mới):

```json
"youtube_pot_enabled": true,
"youtube_pot_auto_download": true,
"js_runtime_path": ""
```

## Chẩn đoán

- Nhật ký lúc khởi động: `Ngăn xếp YouTube: yt-dlp <ver> | runtime JS: co |
  PO Token provider: san sang (bgutil 0.8.1)`.
- `ChanDoan.bat` → mục "Tải YouTube không cần tài khoản": báo trạng thái
  `qjs.exe`, `ffmpeg`, PO Token provider.
- `SuaLoi.bat` → mục **3C**: tải/sửa bộ sinh PO Token ngay.
  (`SuaLoi.bat -ChiYtDlp` chạy cả 3B lẫn 3C.)

## Cần biết khi bảo trì

- Nâng phiên bản bgutil: sửa `POT_VERSION` + 2 mã SHA-256 trong
  `core/pot_provider.py`, **và** khối hằng số tương ứng ở đầu mục 3C của
  `tools/chan_doan/QLS_SuaLoi.ps1` (PowerShell không đọc được Python).
- Nâng QuickJS: sửa `QJS_VERSION` + `QJS_SHA256` trong
  `tools/fetch_build_binaries.py`. yt-dlp khuyến nghị quickjs-ng ≥ 0.12.0.
- Asset ffmpeg của BtbN là bản "latest" được build lại liên tục → **không ghim
  SHA-256 được**; script kiểm tra zip hợp lệ + chạy thử `ffmpeg -version` và in
  SHA-256 ra màn hình để ghi vào nhật ký phát hành.
- `sync_version.py` **không** đụng `build_installer_heavy.bat` — dòng tên file
  output ở đó phải sửa tay.

## Nguồn

- [PO Token Guide](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide) ·
  [EJS wiki](https://github.com/yt-dlp/yt-dlp/wiki/EJS)
- [yt-dlp #15012 — bắt buộc runtime JS ngoài](https://github.com/yt-dlp/yt-dlp/issues/15012)
- [yt-dlp #17348](https://github.com/yt-dlp/yt-dlp/issues/17348) ·
  [#16150 — android_vr thất thường](https://github.com/yt-dlp/yt-dlp/issues/16150)
- [bgutil-ytdlp-pot-provider-rs](https://github.com/jim60105/bgutil-ytdlp-pot-provider-rs) ·
  [quickjs-ng](https://github.com/quickjs-ng/quickjs/releases)
