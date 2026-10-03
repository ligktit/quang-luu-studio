# Thăm dò: Studio One nạp bài xong lúc nào, có trả lời MIDI không

Công cụ cho **kỹ thuật viên**, chạy trên máy đã cài Studio One + loopMIDI. Không cần Python
(dùng Windows PowerShell 5.1 có sẵn). Kết quả dùng để quyết định cách làm tính năng
"chỉ đồng bộ MIDI khi Studio One thật sự sẵn sàng" — xem `docs/PLAN_SO_READY_HANDSHAKE.md`.

| Tệp | Vai trò |
|---|---|
| `ThamDoStudioOne.bat` | Bấm đúp để chạy (mặc định 4 phút) |
| `ThamDoStudioOne.ps1` | Toàn bộ phần thăm dò |

## Công cụ đo gì

Script gửi **Ping** (CC 49, giá trị đổi liên tục) vào cổng `QuangLuuMIDI` mỗi giây, nghe cổng
về `QLS_PhanHoi`, đồng thời ghi lại tiến trình, cửa sổ, CPU của Studio One. Nó trả lời 3 câu:

1. Studio One có **gửi trả** giá trị vừa nhận không (nhiều DAW chặn vòng này).
2. Lúc nạp bài Studio One có **tự gửi** giá trị các control ra không.
3. Studio One trả lời ping **sau cửa sổ chính bao lâu** — tức cơ chế hẹn giờ hiện tại (+3/10/25/50s)
   đoán trúng hay trượt.

Kịch bản A–C chỉ gửi CC 49. Bài chưa gán gì cho CC 49 thì Studio One bỏ qua, không ảnh hưởng âm
thanh. **Kịch bản D** khác: nó bật/tắt thật 12 nút trong bài và tạm sửa file thiết bị — xem mục riêng.

## Cài đặt (một lần)

1. **Cổng MIDI.** Chạy `setup_all.bat` (hoặc riêng `setup_midi_ports.ps1`) trong thư mục cài
   đặt: nó tạo cả `QuangLuuMIDI` lẫn `QLS_PhanHoi`, rồi đếm lại xem cổng đã thật sự hiện ra
   chưa. Tên cổng phản hồi **không được chứa** chữ `QuangLuuMIDI` — app dò cổng gửi theo kiểu
   "tên có chứa", để trùng thì app mở nhầm.
2. **File thiết bị.** Bản cài 1.7.7 trở đi đã có sẵn control `Ping San Sang` (CC 49) — chạy
   `setup_all.bat` trong thư mục cài đặt là nó chép sang
   `%APPDATA%\PreSonus\Studio One 7\User Devices\QuangLuuMIDI\`.
   Máy còn bản cũ hơn thì chép tay `studio_one\QuangLuuMIDI.surface.xml` của bản mới vào đó.
3. **Mở Studio One** → Options → External Devices → chọn **QuangLuuMIDI** → Edit:
   - Receive From: `QuangLuuMIDI` (giữ nguyên như đang dùng)
   - **Send To: `QLS_PhanHoi`** — tuyệt đối không chọn `QuangLuuMIDI` (thành vòng phản hồi vô tận)

   Đóng Studio One rồi mở lại để nó nạp file thiết bị mới.
4. **Mở bài mẫu** → tạo một track Audio trống tên `PING`, không input, bấm **Mute**.
   Dùng Control Link (như lúc gán Lofi/Remix) gán control **Ping San Sang** vào **Pan** của track `PING`.
   Gán **theo bài**, KHÔNG gán Global — gán Global thì Studio One trả lời ping trước cả khi bài nạp
   xong, kết quả sai hoàn toàn.
5. **Lưu bài** (Ctrl+S). Máy bật chế độ khách + phục hồi bản mẫu thì phải **chốt bản mẫu**
   (`docs/KIOSK_MODE_GUIDE.md` mục 4), nếu không lần mở app sau bản mẫu cũ chép đè mất track `PING`.

## Chạy thử

**Tắt app Quang Lưu Studio trong suốt lúc thử** — app cũng gửi MIDI vào cổng này, lẫn vào kết quả.

### Kịch bản A — Studio One mở SAU (quan trọng nhất)

1. Đóng Studio One.
2. Bấm đúp `ThamDoStudioOne.bat`.
3. Trong vòng 10 giây: bấm đúp file `.song` bài mẫu để mở Studio One.
4. Chờ bài hiện đầy đủ, **đợi thêm ~10 giây**, rồi dùng chuột kéo Pan track `PING` qua lại **một lần**
   (để phân biệt "Studio One không trả lời" với "chưa gán").
5. Để script chạy hết 4 phút. Báo cáo tự lưu ra Desktop: `QLS_ThamDoSO_<MÁY>_<giờ>.txt`.

### Kịch bản B — Studio One đã mở sẵn

Bài mẫu đang mở, chạy từ dòng lệnh trong thư mục này:

```bat
ThamDoStudioOne.bat -Seconds 60
```

### Kịch bản C — máy yếu / bài nặng (nếu tiện)

Như kịch bản A, trên máy chậm nhất hoặc bài nhiều plugin nhất. Cho biết khoảng cách thực tế
giữa "thấy cửa sổ" và "trả lời ping" trong trường hợp xấu nhất.

### Kịch bản D — Studio One có báo lại trạng thái nút không

Trả lời câu hỏi: nút MODE / Auto-Tune / Fix Méo / Bè / Tắt Ồn / Mute và dải "ĐANG BẬT" của
app có thể hiển thị **đúng trạng thái thật trong Studio One** không. Hiện app chỉ hiển thị lệnh
**nó đã gửi**; muốn hiển thị trạng thái thật thì Studio One phải gửi trả giá trị của từng nút.

Bản phát hành chỉ bật `transmit` cho `Ping San Sang`, nên phải tạm bật cho 12 nút kia:

1. Làm xong phần **Cài đặt** ở trên (cổng `QLS_PhanHoi`, Send To). Không cần track `PING`.
2. Chạy `ThamDoStudioOne.bat -BatTransmit` — sửa file thiết bị đã cài, **có sao lưu** cạnh file
   (`QuangLuuMIDI.surface.xml.thamdo_goc`).
3. **Đóng Studio One rồi mở lại**, mở bài mẫu (bài đã gán Lofi/Remix/... như lúc dùng thật).
4. Chạy `ThamDoStudioOne.bat -KiemTraNut`. Script lần lượt gửi **BẬT rồi TẮT** cho từng nút
   và ghi Studio One có gửi trả không, giá trị bao nhiêu, trễ bao lâu.
5. Khi script báo **BAM TAY**: trong 30 giây, dùng chuột bật/tắt vài nút **ngay trong Studio One**
   (tham số đã gán Lofi, Remix, Mute Vang...). Phần này cho biết Studio One có tự báo khi thay
   đổi đến từ phía nó không.
6. Cuối cùng script trả 12 nút về **TẮT**. Chạy `ThamDoStudioOne.bat -KhoiPhucSurface`, rồi mở lại
   Studio One và app — app sẽ đồng bộ lại trạng thái của nó.

Đọc kết luận (mục `TOM TAT KICH BAN D`):

| Kết luận | Ý nghĩa |
|---|---|
| `XAC NHAN TRANG THAI DUNG DUOC` | Studio One trả lại đúng từng lệnh → app chỉ coi nút là BẬT khi có phản hồi |
| `Chi MOT PHAN nut tra lai` | Nút không trả thường là nút chưa gán vào tham số nào trong bài |
| `KHONG tra lai lenh cua app, nhung CO bao khi bam trong Studio One` | Chỉ đồng bộ ngược được (Studio One → app), không xác nhận được lệnh |
| `Khong nhan duoc gi` | Chưa `-BatTransmit` + mở lại Studio One, sai Send To, hoặc nút chưa gán |

Gửi lại **các file `.txt`** cho kỹ thuật.

## Đọc nhanh kết quả (cuối báo cáo, mục KẾT LUẬN)

| Kết luận | Ý nghĩa |
|---|---|
| `HOI-DAP MIDI DUNG DUOC` | Làm được cách hỏi–đáp. Mốc "trả lời ping lần đầu" = lúc thật sự sẵn sàng |
| `CO gui ve nhung KHONG tra loi ping` + có dòng `KHONG khop` lúc kéo tay | Studio One chặn gửi trả giá trị vừa nhận → phải dùng phương án dự phòng |
| `CO gui ve nhung KHONG tra loi ping`, không có dòng `KHONG khop` | Ping chưa được gán đúng, xem lại bước 4 |
| `Khong nhan duoc gi tu Studio One` | Sai Send To, chưa chép file thiết bị, hoặc chưa mở lại Studio One |
| `Tin la tren cong chinh` | App đang chạy, hoặc Send To trỏ nhầm về `QuangLuuMIDI` |

## Tham số dòng lệnh

| Tham số | Mặc định | Ý nghĩa |
|---|---|---|
| `-Seconds` | 240 | Chạy bao lâu. Ctrl+C dừng sớm, báo cáo vẫn được ghi |
| `-OutPort` | `QuangLuuMIDI` | Cổng gửi Ping |
| `-BackPort` | `QLS_PhanHoi` | Cổng nghe Studio One trả về |
| `-PingCC` | 49 | CC của control Ping |
| `-PingMs` | 1000 | Nhịp gửi Ping (ms) |
| `-OutFile` | Desktop | Nơi lưu báo cáo |
| `-NoOpen` / `-NoPause` | | Không mở Notepad / không chờ Enter |
| `-BatTransmit` | | Kịch bản D: tạm bật `transmit` cho 12 nút trong file thiết bị đã cài (có sao lưu) |
| `-KhoiPhucSurface` | | Trả file thiết bị về bản gốc từ bản sao lưu |
| `-KiemTraNut` | | Kịch bản D: gửi BẬT/TẮT từng nút, ghi Studio One có báo lại không |
| `-ChoMs` | 1500 | Kịch bản D: chờ phản hồi sau mỗi lệnh (ms) |
| `-BamTaySeconds` | 30 | Kịch bản D: thời gian bấm tay trong Studio One |

## Hoàn tác sau khi thử

- Không phải hoàn tác gì về file thiết bị: `Ping San Sang` nằm sẵn trong bản phát hành.
  **Riêng kịch bản D** đã sửa file thiết bị → phải chạy `-KhoiPhucSurface` rồi mở lại Studio One.
- Track `PING` và cổng `QLS_PhanHoi` giữ lại được — tính năng hoàn chỉnh sẽ dùng đúng hai thứ này.

## Ghi chú khi sửa script

- `.ps1` lưu **UTF-8 có BOM**, nội dung giữ ASCII (không dấu) như bộ `tools/chan_doan`. `.bat` thuần ASCII.
- Callback MIDI của winmm chạy trên thread riêng, không có runspace PowerShell — phải để trong
  phần C#, chỉ đẩy tin vào hàng đợi.
- Kiểm tra cú pháp trước khi gửi đi:
  ```powershell
  $e=$null; [System.Management.Automation.Language.Parser]::ParseFile("ThamDoStudioOne.ps1",[ref]$null,[ref]$e); $e
  ```
