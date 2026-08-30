# Cookie trình duyệt & CDP — cảnh báo và cách làm đúng

> Trạng thái: **ĐÃ TRIỂN KHAI** — 26/08/2026.
> Liên quan: `docs/PLAN_YOUTUBE_NO_ACCOUNT.md` (đường không cần cookie),
> `docs/PLAN_TIMELINE_YOUTUBE.md` (CDP theo dõi vị trí phát).

---

## ⚠️ Cảnh báo 1 — "Đóng trình duyệt rồi thử lại" là NGÕ CỤT

**Đừng bao giờ viết lại lời khuyên này vào app, tài liệu hay script.**

Từ Chrome 127 (và Edge/Brave/Opera/Vivaldi cùng nhân Chromium), cookie được mã
hoá bằng **App-Bound Encryption**: khoá giải mã bị cột vào chính file
`chrome.exe`, chỉ trình duyệt tự giải được. Chương trình ngoài — kể cả yt-dlp —
không có cách nào giải.

Đây **không phải** chuyện file `Cookies` bị khoá khi trình duyệt đang chạy. Đóng
trình duyệt không thay đổi gì cả.

### Bằng chứng đo được (26/08/2026, máy dev)

Chrome/Edge/Brave 151, yt-dlp 2026.08.19. Kiểm `os_crypt.app_bound_encrypted_key`
trong `%LOCALAPPDATA%\...\User Data\Local State`:

```
Chrome : app_bound_encrypted_key = CO
Edge   : app_bound_encrypted_key = CO
Brave  : app_bound_encrypted_key = CO
```

Rồi gọi `yt_dlp.cookies.extract_cookies_from_browser`:

```
chrome  -> LOI: Failed to decrypt with DPAPI          ← Chrome ĐANG ĐÓNG
brave   -> LOI: Failed to decrypt with DPAPI          ← Brave  ĐANG ĐÓNG
edge    -> LOI: Could not copy Chrome cookie database ← Edge đang chạy
firefox -> LOI: could not find firefox cookies database (không cài)
```

Chrome và Brave lúc đo **đã đóng hẳn** mà vẫn tịt. Hai thông điệp khác nhau nói
hai chuyện khác nhau:

| Thông điệp | Ý nghĩa thật | Đóng trình duyệt có cứu được? |
|---|---|---|
| `Could not copy ... cookie database` | file đang bị trình duyệt giữ | **Có** — nhưng giải mã xong vẫn tịt vì lý do dưới |
| `Failed to decrypt with DPAPI` | App-Bound Encryption | **Không**, không bao giờ |

Vì bản trước khuyên "đóng hẳn Chrome/Edge/Brave rồi thử lại", khách làm theo,
không bao giờ được, rồi báo lại **"vẫn lỗi cookies"**. Lời khuyên đúng thì ngược
hẳn: phải **MỞ** trình duyệt lên.

### Cách làm đúng: nhờ chính trình duyệt giải mã hộ

`core/cdp_cookies.py` — lật ngược vấn đề. Không tự giải mã nữa mà hỏi trình
duyệt đang chạy qua lệnh CDP `Storage.getCookies`; nó trả cookie đã giải mã sẵn.

- Quét cổng `9222..9232`, dùng endpoint cấp **trình duyệt** (`/json/version`)
  chứ không phải cấp tab — cookie là tài sản của cả profile, và cách này chạy
  được cả khi chưa mở tab YouTube nào.
- Chỉ lấy cookie của `youtube.com`, `youtu.be`, `google.com`, `googlevideo.com`,
  `ytimg.com`. **Không quét cả kho cookie của người dùng** — ngân hàng, email,
  mạng xã hội không liên quan gì ở đây và không nên nằm trong một file `.txt`
  trên đĩa.
- Ghi ra định dạng Netscape cho yt-dlp: cookie phiên (`expires = -1`) ghi hạn
  `0`; cookie HttpOnly ghi tiền tố `#HttpOnly_` (chuẩn của curl/wget).
- `core/ytdlp_support.py::run_with_auth_fallback` tự gọi ở **nấc cứu hộ**: chỉ
  chạy khi vấn đề đúng là cookie (`auth_blocked` hoặc `cookie_db_blocked`). Video
  riêng tư / đã xoá thì không đi quấy trình duyệt đòi cookie làm gì.

Đã chạy thật với Chrome 151: lấy được 7 cookie `.youtube.com`, yt-dlp nạp lại
file đó đọc được — đúng cái mà `--cookies-from-browser` vừa từ chối trên **cùng
một máy**.

### Bẫy đếm dòng

`#HttpOnly_` bắt đầu bằng dấu `#`. Đếm "dòng cookie" bằng `not line.startswith("#")`
sẽ bỏ sót đúng những cookie đăng nhập quan trọng nhất, rồi kết luận "không có
cookie nào" và vứt cả mẻ vừa lấy được. Phải đếm theo dấu **TAB**.

---

## ⚠️ Cảnh báo 2 — Mọi kết nối CDP phải có `suppress_origin=True`

`websocket-client` tự gắn header `Origin: http://127.0.0.1:9222` vào mọi kết
nối. Chrome/Edge từ bản 111 **chặn** WebSocket DevTools có Origin lạ:

```
Handshake status 403 Forbidden
Rejected an incoming WebSocket connection from the http://127.0.0.1:9333 origin.
Use the command line flag --remote-allow-origins=...
```

Đo được ngày 26/08/2026 với Chrome 151. Thêm `suppress_origin=True` là hết.

Trước 26/08/2026 `core/cdp_monitor.py` thiếu cờ này ở cả hai chỗ
`create_connection`. Lỗi bị **che** trong đường đi chính vì khi app tự mở trình
duyệt (`core/engine/_lifecycle.py`, `core/engine/_youtube.py`) nó có thêm
`--remote-allow-origins=*`. Nhưng trình duyệt do khách tự mở bằng shortcut đã vá
cờ (`tools/_apply_cdp.ps1` — script này **không** thêm `--remote-allow-origins`)
thì CDP không bao giờ kết nối được, app âm thầm rơi về WinRT.

Mà WinRT thì mù vị trí phát với player nhúng — xem
`docs/PLAN_TIMELINE_YOUTUBE.md`. Nên một cờ thiếu ở tầng websocket đẻ ra một
triệu chứng ở tận tầng gửi MIDI theo timeline tone.

---

## ⚠️ Cảnh báo 3 — CHƯA XÁC MINH: Chrome ≥136 và profile mặc định

Chrome 136 (05/2025) được cho là **bỏ qua `--remote-debugging-port` khi dùng
thư mục profile mặc định**, chỉ nhận cờ khi có `--user-data-dir` riêng.

**Chưa kiểm được trên máy thật** (bước kiểm phải mở đúng profile thật của người
dùng). Nếu đúng thì trên máy khách dùng Chrome/Edge ≥136:

- CDP monitor không kết nối được → rơi về WinRT;
- đường lấy cookie qua CDP ở Cảnh báo 1 cũng tê liệt.

### Cách kiểm trên một máy khách

```
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
```

Rồi mở `http://127.0.0.1:9222/json/version`. Ra JSON là ổn; không ra là dính.

### ❌ KHÔNG được "chữa" bằng cách thêm `--user-data-dir` riêng

Profile riêng là profile **trắng**: không đăng nhập YouTube, không bookmark,
không lịch sử. Vừa mất sạch cookie — thứ mà cả trang này đang tìm cách lấy — vừa
làm khách hoang mang vì trình duyệt mở ra lạ hoắc. Phản tác dụng hoàn toàn.

Nếu dính thật, lối thoát là: Firefox (không dùng App-Bound Encryption, đọc được
cả khi đang mở), hoặc tiện ích xuất cookie của trình duyệt, hoặc đi hẳn đường
không cần cookie (`docs/PLAN_YOUTUBE_NO_ACCOUNT.md`).

---

## Thứ tự nguồn cookie hiện tại

`core/ytdlp_support.py::_build_auth_attempts` + nấc cứu hộ:

1. **Không cookie** (`player_client` android/android_vr + PO Token) — máy khách
   karaoke phần lớn không đăng nhập YouTube, đây mới là đường chính.
2. `youtube_cookie_file` do người dùng chỉ định trong Thiết lập.
3. `%APPDATA%\QuangLuuStudio\youtube_cookies.txt` — file đã lấy được lần trước.
4. Cookie trình duyệt (`firefox` trước, rồi edge/chrome/brave/opera/vivaldi).
   Với Chromium ≥127 nấc này **luôn hỏng**, giữ lại chỉ vì Firefox và các bản cũ.
5. **Cứu hộ:** xin qua CDP từ trình duyệt đang chạy (Cảnh báo 1).

---

## Nơi lời khuyên sai từng nằm — đã sửa hết 26/08/2026

| File | Đã sửa thành |
|---|---|
| `core/ytdlp_support.py::_build_cookie_db_error_message()` | Nói rõ đóng trình duyệt không giúp gì; hướng dẫn **mở** trình duyệt để đi đường CDP |
| `core/ytdlp_support.py::export_cookies_to_file()` (docstring) | Ghi rõ chỉ còn dùng được với Firefox |
| `ui/dialogs/settings_dialog.py::_action_export_cookies()` | Tự rơi sang CDP khi đọc đĩa tịt; thông báo lỗi không còn bảo đóng trình duyệt |
| `tools/export_youtube_cookies.bat` | Bỏ bước "đã đóng browser chưa? (y/N)"; thêm lựa chọn 1 = lấy qua CDP |

Đã chạy thử `export_youtube_cookies.bat --cdp` với Chrome 151 thật: lấy 7 cookie,
ghi file 941 bytes, cập nhật `app_config.json`, thoát mã 0.

---

## Ba cái bẫy trong script `.bat` (sửa luôn 26/08/2026)

Đều là lỗi có sẵn, chỉ lộ ra khi chạy thử script.

### 1. `.bat` phải là CRLF

CMD đọc file `.bat` chỉ có LF sẽ cắt nhầm dòng và báo những câu vô nghĩa kiểu
`'e' is not recognized as an internal or external command` — rất khó đoán ra
nguyên nhân. Trong cây làm việc có **16 file** `.bat`/`.ps1` đang ở dạng LF; trước
đây chuyện này chỉ chạy được nhờ `core.autocrlf=true` trên máy dev, ai đặt
`autocrlf=false` là sinh ra file hỏng ngay. Đã ghi thẳng luật vào
`.gitattributes`:

```
*.bat text eol=crlf
*.cmd text eol=crlf
*.ps1 text eol=crlf
```

### 2. Dấu `^` **không** nối dòng bên trong chuỗi nháy kép

```bat
:: HỎNG — cmd đẩy thẳng dấu ^ vào mã Python → SyntaxError
python -c ^
    "import sys; ^
     from core import cdp_cookies"
```

Viết `python -c "..."` trên **một dòng duy nhất**.

### 3. Ngoặc đơn trong `echo` nằm trong khối `( ... )` phải escape

```bat
if exist x ( echo (bo qua)  )   :: HỎNG: ")" đóng khối sớm
if exist x ( echo ^(bo qua^) )  :: đúng
```

Triệu chứng: `. was unexpected at this time.`

*(Kèm theo: khối cập nhật `app_config.json` viết `r'%COOKIE_OUT%'` — cú pháp
raw-string của Python lọt vào PowerShell, luôn hỏng. Đã bỏ chữ `r`.)*

---

Kiểm tra tự động: `tests/core/test_cdp_cookies.py` (13 bài) và ba bài trong
`tests/core/test_ytdlp_support.py` — trong đó có một bài khoá thẳng câu chữ
"dong trinh duyet cung khong giup gi" trong thông điệp lỗi, để lời khuyên cũ
không lặng lẽ quay lại.
