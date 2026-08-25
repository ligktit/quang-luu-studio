# Đóng bản test thu âm gửi máy tester

## Context

Khách báo chức năng thu âm phát ra tiếng rè. Đã vá xong trong working tree:
cắt cứng đỉnh sóng → bộ giới hạn đỉnh có nhìn trước, resample mic giữ liên tục
pha, chốt trần residual, thêm chỉ số chẩn đoán `STATS`, và vá lỗi worker chết vì
`UnicodeEncodeError` khi mic tắt. Bằng chứng: bản cũ để lại 15.742 mẫu bẹt ở
±32767 trong 1 giây thu, bản mới 0.

Giờ cần một bản chạy được trên máy thật để tester xác nhận trước khi phát hành.
Anh đã chốt: **chỉ bản Light**, **chỉ exe chạy thẳng, không đóng installer**.

## Đã biết (khảo sát xong, không cần làm lại)

| Điều | Chi tiết |
|---|---|
| Lệnh build Light | `pyinstaller QuangLuuStudio.spec` **không** set `QLS_WEBENGINE` → `dist\QuangLuuStudio.exe`, one-file, windowed |
| Trạng thái | Build đã chạy nền từ trước khi vào plan mode (task `bp87sot2u`), đã qua `sync_version.py` → v1.7.0 |
| Kích hoạt | Exe chạy thẳng vẫn đọc `%APPDATA%\QuangLuuStudio` chung với bản đã cài ⇒ **tester không phải kích hoạt lại** (nhưng settings cũng dùng chung) |
| Log | `%APPDATA%\QuangLuuStudio\logs\app.log`. `core/logger.py:105-109` chuyển `stdout` vào log khi frozen ⇒ dòng `STATS: …` của worker **tự vào log**, không cần sửa thêm |
| Nơi lưu bản thu | `~\Documents\QuangLuuStudio` (`core/config.py:47`) |
| `models/` 280MB | Do installer ship cạnh exe, **không** nằm trong exe (`core/accessibility/tts_piper.py:40-50` tìm cạnh `sys.executable`). Exe chạy thẳng ở thư mục trống sẽ không có Piper/Vosk — không ảnh hưởng test thu âm |

**Lưu ý cần nói với tester:** bản này mang *toàn bộ* thay đổi đang có trong
working tree (kiosk mode, vá licensing kickout, bộ lọc admin, dialog tắt máy /
mở khoá kỹ thuật…), không riêng phần thu âm.

## Việc làm

1. **Chờ build nền xong**, kiểm tra `dist\QuangLuuStudio.exe` (tồn tại, kích
   thước hợp lý, mtime vừa xong). Nếu build lỗi thì đọc
   `tasks/bp87sot2u.output` và chạy lại `python -m PyInstaller QuangLuuStudio.spec`.

2. **Đổi tên bản giao** thành `QuangLuuStudio_v1.7.0_test-thu-am.exe` để tester
   không lẫn với bản production đang cài. One-file nên đổi tên vô hại.

3. **Tính SHA256** ghi cạnh file (theo lệ sẵn có của `installer_output\SHA256SUMS.txt`).

4. **Viết `HUONG_DAN_TEST_THU_AM.txt`** đặt cùng thư mục với exe. Nội dung:
   - Chép exe vào một thư mục trống rồi chạy thẳng, **không cần gỡ bản đang cài**.
   - **Bật mic trước khi test**: ⚙️ Cài đặt → Nguồn thu → chọn micro. Nút Thu âm
     mặc định *tắt* mic (`frontend_qt.py:2282`, `mic_idx = -2`), mà tiếng rè cũ
     chỉ xuất hiện khi trộn nhạc + mic. Nút **Chấm điểm** thì luôn bật mic nên
     là đường nhanh nhất để thử phần trộn tiếng.
   - Ba ca cần thử: (a) nhạc + mic mở to như lúc hát thật; (b) chỉ nhạc, để mặc
     định; (c) mở sẵn Studio One + trình duyệt cho máy nặng rồi thu.
   - Sau mỗi lần: nghe lại file trong `Documents\QuangLuuStudio`, và để ý app có
     hiện dòng cảnh báo vàng sau khi lưu không.
   - Gửi về: file `.wav` + `%APPDATA%\QuangLuuStudio\logs\app.log`.

5. **Chép plan này sang `docs/`** của dự án theo lệ đã thống nhất.

## Kiểm chứng

**Trước khi gửi** (không tự chạy app: nó gửi MIDI, có thể bật kiosk và tự mở
trình duyệt — anh tự smoke test):

```bash
ls -la dist/
sha256sum dist/QuangLuuStudio_v1.7.0_test-thu-am.exe
```

**Sau khi tester gửi kết quả về:**

```bash
grep "STATS:" "%APPDATA%\QuangLuuStudio\logs\app.log"
python tools/rec_test.py analyze "<file tester gửi>.wav"
```

Đọc chỉ số:

| Dấu hiệu | Kết luận |
|---|---|
| `capture` < 0.95 | Máy đói CPU, driver vứt mẫu — chính là ca chỉ inline mới dính |
| `gainmin` < 0.5 | Tiếng vào quá to, limiter phải hạ sâu |
| `drop`/`overrun` > 0 | Nghẽn hàng đợi hoặc driver báo overflow |
| Tool báo "mặt phẳng ≥3 mẫu" > 0 | Vẫn còn cắt đỉnh — bản vá chưa ăn, phải xem lại |

Nếu `capture` thấp lặp lại trên máy tester, đó là bằng chứng để làm tiếp việc
tách worker thu âm ra tiến trình riêng cho bản đóng gói.
