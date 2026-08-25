# Chế độ khách — khoá Studio One & đóng an toàn

> **Ngày viết:** 2026-08-09 · đối chiếu trực tiếp với code hiện tại.
> Dành cho **nhân viên kỹ thuật** khi setup máy cho phòng thu.

---

## 1. Giải quyết chuyện gì

| Vấn đề | Cách xử lý |
|---|---|
| Khách táy máy chỉnh thông số trong Studio One → phần mềm chạy sai | **Chế độ khách**: ẩn hẳn cửa sổ Studio One, chỉ mở lại được bằng mã PIN |
| Khách đã lỡ chỉnh và lưu đè → sai vĩnh viễn | **Bản mẫu .song**: mỗi lần khởi động app chép đè bản KTV đã chốt lên file đang dùng |
| Thoát app xong, mở Studio One lần sau nó đòi phục hồi phiên, không vào thẳng file đã lưu | **Đóng an toàn**: lưu bài trước rồi để Studio One tự thoát, không còn `taskkill /F` |

Ba phần này ăn khớp với nhau: vì bản mẫu luôn được phục hồi lúc khởi động, app
**được phép** Ctrl+S trước khi đóng — mà đã lưu rồi thì Studio One không hỏi gì,
không hỏi thì không có hộp thoại nào để đoán mò, nên nó thoát sạch.

---

## 2. Bật chế độ khách (làm một lần lúc setup)

**Thiết lập → Hệ thống → "Chế độ khách — khoá Studio One"**

1. Bấm **Đặt mã PIN** → nhập PIN (tối thiểu 4 ký tự) hai lần.
2. Tích **"Bật chế độ khách"** → Studio One bị ẩn ngay lập tức.
3. (Tuỳ chọn) Tích **"Ẩn lại cả khi khách tự mở Studio One"** — bật watchdog nền
   quét mỗi 1.5 giây, ẩn lại cả cửa sổ do khách tự mở từ Start Menu/desktop.
   **Mặc định TẮT.** Bật nếu máy khách có shortcut Studio One ngoài desktop.
4. Chọn thời lượng **phiên kỹ thuật tự khoá lại** (mặc định 20 phút).

Mục này **áp dụng ngay khi bấm**, không cần bấm "Lưu thiết lập" — trạng thái khoá
không được phép nằm lửng lơ giữa RAM và đĩa.

Khi đang khoá:
- Nút mắt 👁 (ẩn/hiện Studio One) **biến mất khỏi header** — không phải làm mờ mà
  ẩn hẳn, nên cũng không bấm Tab tới được và trình đọc màn hình cũng bỏ qua.
- Lệnh ẩn/hiện Studio One bị chặn ở tầng dưới (`_on_toggle_studio_one`), nên nút
  custom / MIDI / lệnh giọng nói cũng không lách qua được.
- Mọi ô cấu hình trong chính mục "Chế độ khách" bị khoá cho tới khi mở khoá.

## 3. Mở khoá / khoá lại

| Thao tác | Cách làm |
|---|---|
| Mở phiên kỹ thuật | **`Ctrl + Alt + Shift + T`** → nhập PIN. Hoặc Thiết lập → nút **Mở khoá kỹ thuật** |
| Khoá lại ngay | Bấm lại **`Ctrl + Alt + Shift + T`** |
| Tự khoá lại | Hết thời lượng phiên, hoặc đóng app |

Trong phiên kỹ thuật, header hiện huy hiệu cam **KỸ THUẬT** để KTV không quên.

Phiên chỉ nằm trong RAM — đóng app là khoá lại, không có kiểu "quên tắt qua đêm".
Nhập sai PIN 5 lần thì bị chặn 60 giây, 5 lần tiếp theo nhân đôi (tối đa 15 phút).

## 4. Bản mẫu .song

Quy trình chuẩn khi setup hoặc khi cần sửa thiết lập trong Studio One:

1. Mở khoá kỹ thuật → tinh chỉnh trong Studio One → **lưu bài (Ctrl+S)**.
2. **Đóng Studio One** (bắt buộc — không ghi đè file đang mở được).
3. Thiết lập → **Chốt bản mẫu .song**.

Từ đó mỗi lần app khởi động, file `.song` được chép đè lại từ bản mẫu **trước khi**
Studio One mở. Khách chỉnh gì cũng chỉ sống trong buổi đó.

Vị trí lưu: `%APPDATA%\QuangLuuStudio\so_template\`

| File | Nội dung |
|---|---|
| `template.song` | Bản mẫu KTV đã chốt |
| `template.json` | Nguồn, sha256, kích thước, thời điểm chốt |
| `replaced.song` | Bản vừa bị chép đè — phao cứu sinh nếu KTV chỉnh xong mà **quên** chốt |

Bỏ qua việc phục hồi (không báo lỗi) khi: chưa chốt bản mẫu, đường dẫn Studio One
trỏ tới `.exe` chứ không phải `.song`, nội dung đã trùng bản mẫu, hoặc Studio One
đang chạy.

> Chỉ chép **file `.song`**. Nếu bài có media rời nằm trong thư mục bài hát
> (bản thu, sample import) thì phần đó không nằm trong bản mẫu.

Tắt tính năng này bằng cách bỏ tích **"Phục hồi bản mẫu .song mỗi lần khởi động"**.

## 5. Đóng Studio One an toàn

Bật ở **Thiết lập → Khởi động / Tắt tự động → "Đóng Studio One khi thoát"**.

Khi thoát app, hiện hộp thoại *"Đang đóng Studio One an toàn"* và chạy tuần tự
(`core/engine/_lifecycle.py` → `close_studio_one_safely`):

1. Giành foreground thật bằng `AttachThreadInput` rồi gửi **Ctrl+S**.
   Cửa sổ đang bị ẩn (chế độ khách) được hiện lại trước — phím chỉ tới được cửa
   sổ đang hiển thị và giữ focus.
2. Hộp thoại nào bật lên trong lúc lưu → Enter (tối đa 2 lần).
3. Gửi **WM_CLOSE** tới cửa sổ chính.
4. Còn hộp thoại nào → giành foreground rồi Enter (tối đa 5 lần, cách nhau 1.2s).
5. Chờ process biến mất, mặc định tối đa 45 giây.

**Hết giờ thì KHÔNG giết process.** App báo *"Studio One chưa đóng xong"* rồi thoát,
để Studio One chạy tiếp — an toàn hơn hẳn việc giết nó giữa lúc đang ghi file.
Nút **"Bỏ qua, thoát ngay"** trong hộp thoại cũng cho kết quả tương tự.

Đây chính là điểm khác cốt lõi so với bản cũ: trước đây hết 5 giây là `taskkill /F`,
mà taskkill để lại cờ "thoát bất thường" → lần mở sau Studio One đòi phục hồi phiên.

## 6. Các khoá trong `settings.json`

Nằm ở `%APPDATA%\QuangLuuStudio\settings.json` (bản cài) hoặc thư mục gốc project
(chạy dev).

```json
{
  "auto_close_studio_one": true,
  "studio_one_close_timeout": 45,
  "force_kill_studio_one": false,
  "tech_lock": {
    "enabled": true,
    "pin_salt": "…", "pin_hash": "…", "iterations": 260000,
    "keep_hidden": false,
    "session_minutes": 20,
    "restore_template": true
  }
}
```

| Khoá | Ý nghĩa |
|---|---|
| `studio_one_close_timeout` | Số giây chờ Studio One thoát (mặc định 45) |
| `force_kill_studio_one` | `true` = hết giờ thì tắt cứng như bản cũ. **Để `false`** trừ khi có máy cá biệt treo hẳn |
| `tech_lock.keep_hidden` | Watchdog nền ẩn lại mọi cửa sổ Studio One |

PIN lưu dạng băm PBKDF2-HMAC-SHA256 260k vòng + salt ngẫu nhiên — đọc file cũng
không lấy lại được PIN.

## 7. Hạn chế đã biết

1. **Không chặn Dev Mode.** `Ctrl+Shift+D` vẫn mở được khi đang khoá, khách vẫn
   sửa/ẩn được nút và MIDI CC. Muốn chặn thì phải gọi `kiosk.is_locked()` trong
   `_toggle_dev_mode` (`frontend_qt.py`).
2. **Ô đường dẫn Studio One trong Thiết lập không bị khoá** — khách vẫn đổi được
   đường dẫn `.song`/`.exe` và các tuỳ chọn tự mở/tự đóng.
3. **Khe hở lúc khởi động.** Studio One nạp bài mất hàng chục giây; app chỉ ẩn
   được sau khi cửa sổ chính hiện ra, rồi bám ẩn thêm 60 giây cho các cửa sổ
   plugin mọc muộn. Trong khoảng nạp đó cửa sổ vẫn thấy trên màn hình.
4. **Khách tự mở Studio One** (Start Menu/desktop) chỉ bị ẩn nếu bật
   `keep_hidden`. Không bật thì app không đụng tới instance đó.
5. **Quên PIN thì không có cửa hậu**: phải xoá mục `"tech_lock"` trong
   `settings.json` bằng tay.
6. **Ctrl+S / Enter cần foreground.** Nếu máy có phần mềm khác giữ cửa sổ
   always-on-top hoặc chặn `SetForegroundWindow`, bước lưu bị bỏ qua (có ghi log)
   và chuỗi đóng rơi về việc bấm Enter trên hộp thoại như trước.

## 8. Xử lý sự cố

| Hiện tượng | Nguyên nhân / cách xử lý |
|---|---|
| Bấm `Ctrl+Alt+Shift+T` báo "Chế độ khách chưa bật" | Chưa tích ô bật trong Thiết lập |
| "Studio One đang khoá — cần mở khoá kỹ thuật" | Đúng như thiết kế: mở phiên kỹ thuật trước |
| Chốt bản mẫu báo "Hãy đóng Studio One trước" | File `.song` đang mở, không ghi đè được |
| Thoát app báo "Studio One chưa đóng xong" | Studio One đang kẹt hộp thoại lạ. Đóng tay, hoặc tăng `studio_one_close_timeout` |
| Mở Studio One vẫn thấy đòi phục hồi phiên | Lần trước thoát bằng tắt cứng (mất điện, Task Manager, hoặc `force_kill_studio_one: true`) |

---

*Các file liên quan: `core/kiosk.py` (trạng thái khoá + PIN), `core/so_windows.py`
(tìm/ẩn/hiện cửa sổ theo PID), `core/so_template.py` (bản mẫu .song),
`core/engine/_lifecycle.py:close_studio_one_safely`, `ui/dialogs/tech_unlock.py`,
`ui/dialogs/shutdown_dialog.py`, `ui/panels/header.py`, `frontend_qt.py`
(`_apply_kiosk_visibility`, `_toggle_tech_session`, `_auto_launch_apps`, `closeEvent`).
Kiểm thử: `tests/core/test_kiosk.py`, `tests/core/test_so_template.py`.*
