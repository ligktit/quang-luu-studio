# Kế hoạch chống hỏng Dò Tone

*Soạn 16/09/2026, sau hai sự cố liên tiếp trên máy khách (15/09 cache numba hỏng, 16/09 tải audio treo).*

Dò tone là lý do app tồn tại: nó là mắt xích duy nhất biến "bài trên YouTube" thành "Studio One
đổi tone". Hỏng nó là app mất giá trị, dù mọi thứ khác chạy tốt. Tài liệu này không bàn về một
lỗi cụ thể — nó bàn về việc **làm sao để lần hỏng sau rẻ hơn lần hỏng trước**.

Tài liệu nền: [TONE_FLOWS.md](TONE_FLOWS.md) mô tả luồng chạy; file này chỉ nói về độ bền.

---

## 1. Bài học từ lịch sử

Nhịp hỏng thật của tầng YouTube, đọc từ git:

| Thời điểm | Hỏng gì | Phải làm gì để cứu |
|---|---|---|
| 24/04/2026 | YouTube bật anti-bot; lỗi "Could not copy Chrome cookie database" | Sửa mã + thêm timeout dò tone |
| 25/08/2026 | yt-dlp đóng gói bị cũ; YouTube đòi PO Token | Sửa mã + cơ chế tự cập nhật yt-dlp |
| 30/08/2026 | Chrome ≥127 mã hoá cookie (App-Bound Encryption) | Sửa mã + xin cookie qua CDP |
| 15/09/2026 | File cache numba hỏng → phân tích chết vĩnh viễn | Sửa mã + phát hành + cài lại từng máy |
| 16/09/2026 | Khâu tải treo quá 90 giây, dự phòng không kịp chạy | Đang xử lý |

**Khoảng hai tháng một lần**, và lần nào cũng cùng một quy trình đắt đỏ: khách gọi → xin log →
đoán → sửa mã → build 500 MB → cài lại từng máy. Sự cố 16/09 tốn nửa ngày mà **phần lớn thời gian
là để nhìn thấy lỗi**, không phải để sửa.

Giả định nền của kế hoạch: **tầng YouTube sẽ còn hỏng nữa, không thể ngăn**. Việc của ta là rút
ngắn quãng "khách hỏng → ta biết → ta chữa" từ vài ngày xuống vài giờ, và giữ cho khách vẫn dò
được tone trong lúc chờ.

---

## 2. Hai điểm yếu cấu trúc

### 2.1. Ta không nhìn thấy lỗi

| Sự thật | Tham chiếu |
|---|---|
| Logger `yt_dlp` bị ghim mức ERROR, mà `_YtdlpLogger` lại đổ **cả `error()`** vào `log.debug` → tiếng nói của yt-dlp không vào file log nào | `core/logger.py:112-113`, `core/ytdlp_support.py:155-184` |
| Lỗi tải bị nuốt trắng, không một ký tự | `core/engine/_tone.py:662-663`, `core/scoring.py:130-131`, `:191-193` |
| `ToneDetector` **không dùng `logging`** — toàn bộ là `print`/`traceback.print` | `core/tone_detector.py:377-381`, `:594-598`, `:906-910` |
| Crash reporter chỉ bắt exception làm **sập app**; dò tone hỏng thì không bao giờ tự về server | `main.py:64-77`, `core/crash_reporter.py:150` |
| Ticket hỗ trợ và crash report chỉ đính **120 dòng cuối `errors.log`** — trong khi dấu vết dò tone nằm ở `app.log` (do `print` → logger `stdout` mức INFO) | `core/crash_reporter.py:54-63`, `core/support.py:93-99`, `core/logger.py:105-109` |
| Không có endpoint telemetry, không có bất kỳ số liệu nào về tỉ lệ dò tone thành công | toàn bộ `server/app/routers/` |

Hệ quả đo được: nhật ký 16/09 có **90 giây im lặng tuyệt đối** rồi watchdog nổ. Sự im lặng đó
không phải "không có gì xảy ra" mà là "ta bị bịt mắt".

### 2.2. Ta không chịu nổi lỗi

Chuỗi dự phòng thực ra khá sâu — đệm phiên → timeline thủ công → tone_cache → tone bài đã lưu →
thư viện cộng đồng → tải YouTube → nghe loa 12 giây → nhập tay (`core/engine/_tone.py:149-196`).
Nhưng đường đi thực tế cắt mất phần lớn:

| Chỗ thủng | Hậu quả | Tham chiếu |
|---|---|---|
| Watchdog **không huỷ được gì**: chỉ báo lỗi cho UI, không đóng socket, không giết tiến trình con | Thang xác thực vẫn chạy ngầm; bấm Dò Lại là chồng thêm một thang nữa (đo được +282 MB trong log khách) | `core/engine/_tone.py:80-106`, không có điểm `_cancelled()` nào bên trong lời gọi tải `:661` |
| Nghe loa dự phòng **chỉ chạy khi `audio_path` rỗng** | Tải treo tới lúc watchdog nổ → dự phòng không bao giờ tới lượt. Đúng cảnh 16/09 | `:701-715` nằm ở nhánh `else` của `:670` |
| Tải được audio nhưng phân tích hỏng → **cũng không rơi xuống nghe loa** | Đúng cảnh 15/09 | `:670-699` |
| `skip_resolve=True` ở **cả nút Dò Lại lẫn lần thử 2, 3** | Bỏ qua cả 5 lớp cache đúng lúc mạng đang hỏng | `frontend_qt.py:1609`, `core/engine/_youtube.py:703-704` |
| `detect_tone_from_browser` **không `stop()` phiên trong `finally`** (ba hàm dò còn lại đều có) | Phiên kẹt ở SCANNING → mọi bài sau chỉ vào hàng chờ, **không bao giờ được dò nữa** cho tới khi khởi động lại app | `:763-764` so với `:988-989` |
| `_send_tone_midi` **bỏ qua kết quả gửi** rồi vẫn in thành công | Studio One không đổi tone mà app báo xong — hỏng đúng mục đích tồn tại, im lặng | `:406-409` |
| Thang xác thực có thể tới **17-21 phiên YoutubeDL**, và `core/scoring.py:126-131` nuốt lỗi rồi chạy lại **toàn bộ thang** lần hai | Không deadline nội bộ nào; một lượt "tải 45 giây" về lý thuyết kéo hàng chục phút | `core/ytdlp_support.py:384-459`, `:641-681` |
| Thử lại 3 lần × watchdog 90 s | Khách chờ **276 giây** (dò nhanh) hoặc **906 giây** (dò toàn bài) trước khi nghe câu trả lời cuối cùng | `core/engine/_youtube.py:32-33`, `:668-708` |

Đo trên máy dev: sáu nấc cookie chỉ tốn 0,04-0,64 giây mỗi nấc, và một lượt tải khoẻ mạnh mất
**2,1 giây**. Nghĩa là chi phí thang không nằm ở cookie mà ở các thao tác mạng, và hạn 45 giây cho
khâu tải là rộng rãi chứ không hà khắc.

---

## 3. Bốn lớp phòng thủ

### Lớp 1 — Khách không bao giờ tay trắng

Nguyên tắc: **thà một tone cũ hoặc tone nghe từ loa, còn hơn một thông báo lỗi.**

1. **Hạn theo từng chặng thay cho một watchdog tổng.** Tìm URL 10 s · tra cache/thư viện 5 s ·
   tải audio 45 s · phân tích 30 s. Watchdog 90 s giữ nguyên làm chốt chặn cuối.
2. **Huỷ phải huỷ thật.** Gắn `progress_hooks` của yt-dlp vào cờ huỷ để bỏ ngang việc tải khi quá
   hạn (đã dùng đúng cơ chế này trong `core/download_check.py:174-190`), và chạy khâu tải trong
   luồng có thể bỏ rơi. Không còn thang chạy ngầm chồng lên nhau.
3. **Mọi kiểu thất bại đều rơi xuống nghe loa**, không riêng ca "không tải được": tải quá hạn,
   phân tích hỏng, phân tích không ra tone.
4. **Dò lại thất bại thì trả về tone cũ** thay vì báo lỗi trắng (`skip_resolve` chỉ bỏ cache ở
   lượt đầu; hỏng rồi thì lấy cache ra dùng và nói rõ "tone đã lưu").
5. **`finally` luôn `stop()` phiên** trong `detect_tone_from_browser` — vá lỗi kẹt SCANNING.
6. **Kiểm kết quả gửi MIDI**; gửi hụt thì báo "Đã dò được tone nhưng không gửi được sang Studio
   One" kèm gợi ý kiểm tra cổng MIDI.
7. **Lối thoát trong giao diện**: bảng lỗi kèm hai nút — "Nghe từ loa ngay" và "Nhập tone bằng tay".

### Lớp 2 — Nhìn thấy lỗi ngay tại máy khách

1. **Một dòng ERROR cho mỗi lần dò tone thất bại**, có mã chặng, ví dụ:
   `[DÒ TONE] THẤT BẠI | chặng=TẢI | mã=YT_TIMEOUT | 45.2s | yt-dlp=2026.08.19 | ffmpeg=có`.
   Đây là điều kiện cần để `errors.log` tự nó đủ chẩn đoán — vì crash report và ticket hỗ trợ chỉ
   đính kèm file đó.
2. **Trả lại tiếng nói cho yt-dlp**: `_YtdlpLogger.warning/error` → `log.warning/log.error`
   (`core/ytdlp_support.py:177-181`), bỏ ghim `yt_dlp` ở mức ERROR (`core/logger.py:112-113`).
3. **Dẹp hai chỗ nuốt trắng**: `core/engine/_tone.py:662-663` và `core/scoring.py:130-131`.
4. **Ghi cấu hình khởi động sau khi logging sẵn sàng**: ffmpeg ở đâu, qjs có không, PO Token có
   không — hiện dòng `FFmpeg found` phát ra trước `setup_logging()` nên mất hẳn (`core/config.py:485`
   so với `main.py:52`).
5. **Công cụ cho khách đã có** — giữ và mở rộng: `kiem_tra_tone.bat` (`--tu-kiem-tra`),
   `thu_tai_youtube.bat` (`--thu-tai`), `chua_loi_do_tone.bat`, và bộ `tools/chan_doan/*.ps1`.
   Bộ chẩn đoán PowerShell **chưa hề nằm trong bộ cài** — đưa vào.

### Lớp 3 — Nhìn thấy lỗi từ xa, không cần khách gọi

1. **Đính kèm `app.log` vào ticket hỗ trợ** (hiện chỉ có `errors.log`) — sửa một chỗ,
   `core/support.py:93-99`. Rẻ nhất, lợi nhất trong cả kế hoạch.
2. **Nút "Gửi báo cáo lỗi" trong Thiết lập**: gói `app.log` + `errors.log` + `tu_kiem_tra.txt` +
   `thu_tai.txt` thành một ticket. Khách bấm một nút thay vì đi tìm file.
3. **Endpoint sự kiện** `POST /api/v1/event` (server hiện **không có** kênh nào như vậy):
   `{fingerprint, app_version, loại, chặng, mã_lỗi, số_giây, yt_dlp_version, có_ffmpeg, có_pot}`.
   Gửi cả **thành công lẫn thất bại** — không có mẫu số thì không thấy được hồi quy. Hàng đợi
   offline như `crash_queue.json`, công tắc tắt trong Thiết lập, tuyệt đối không gửi nội dung bài hát.
4. **Trang admin**: tỉ lệ dò tone thành công theo phiên bản và theo chặng, 7 ngày gần nhất. Bảng
   `devices` đã có sẵn `app_version` + `last_check_in` để ghép.

> Đây chính là cái biến "khách gọi điện" thành "ta biết trước": một đợt YouTube đổi cơ chế sẽ hiện
> ra dưới dạng tỉ lệ thành công của cả đội máy rơi trong vài giờ.

### Lớp 4 — Biết trước và chữa không cần phát hành

1. **Cấu hình từ xa** gắn vào phản hồi `/api/v1/license/verify` (client đã gọi ≤6 giờ một lần,
   `main.py:295-298`): hạn từng chặng, `youtube_player_clients`, bật/tắt PO Token, ngưỡng tuổi
   yt-dlp, và một dòng `notice` hiển thị cho khách. Chỉ nhận **danh sách khoá định sẵn**, kiểm kiểu
   và khoảng giá trị, không bao giờ nhận mã.
   Việc này quan trọng gấp đôi vì bộ cài dùng cờ `onlyifdoesntexist` cho `app_config.json`
   (`QuangLuuStudio_Setup.iss:109`) — máy nâng cấp **giữ nguyên cấu hình cũ**, nên hôm nay muốn đổi
   một tham số ở máy khách là phải cài lại hoặc sửa tay từng máy.
2. **Canary hàng ngày**: tải + dò tone thật trên 3-5 video công khai. Chạy trên máy dev bằng Task
   Scheduler (nguồn tin cậy), CI chỉ chạy tham khảo — IP của GitHub runner hay bị YouTube chặn nên
   dễ báo động giả. Canary hỏng hai ngày liên tiếp = đi kiểm tra ngay.
3. **Chuông báo yt-dlp cũ**: bản đang dùng quá 45 ngày mà tự cập nhật chưa thành công → ghi ERROR
   và gửi sự kiện. Bộ chẩn đoán PowerShell đã có ngưỡng 60/120 ngày
   (`tools/chan_doan/QLS_ChanDoan.ps1:1179-1240`) — đưa cùng luật đó vào app.
4. **Cổng kiểm thử khi phát hành**: `release.yml` hiện **không chạy test nào**; `test.yml` lại lọc
   đường dẫn nên sửa `frontend_qt.py`/`ui/**` không kích hoạt test, dùng `-x` nên dừng ở lỗi đầu, và
   thiếu `pytest-qt` trong khi 7 file test UI cần `qtbot`. Vá cả bốn.
5. **Bộ đối chiếu vàng cho độ chính xác**: hiện **không tồn tại** (chữ "golden" chỉ nằm trong một
   docstring ở `tests/core/test_tone_detector.py:683`). Cách rẻ và sạch bản quyền: **tự tổng hợp
   audio** — dựng vòng hoà thanh I-IV-V-I cho đủ 24 tone bằng sóng hài, chạy qua librosa **thật**
   trong một job CI riêng (tách khỏi bộ test chính vì librosa thật làm abort pytest). Đây là thứ duy
   nhất cho phép sửa thuật toán mà biết chắc không làm tệ đi.
6. **Khói sau khi build**: chạy `--tu-kiem-tra` (và `--thu-tai` khi có mạng) trên exe vừa dựng,
   ngay trong `build_installer.bat` và trong CI.

---

## 4. Thứ tự làm

### P0 — tuần này (chữa đúng vết đang chảy máu)

| # | Việc | Chỗ sửa |
|---|---|---|
| 1 | Hạn 45 s cho khâu tải + huỷ thật + rơi xuống nghe loa ở **mọi** kiểu thất bại | `core/engine/_tone.py:661-715`, `core/scoring.py` |
| 2 | Một dòng ERROR có mã chặng cho mỗi lần thất bại | `core/engine/_tone.py` |
| 3 | Trả tiếng nói cho yt-dlp + dẹp hai chỗ nuốt trắng | `core/ytdlp_support.py:177-181`, `core/logger.py:112`, `core/scoring.py:130` |
| 4 | `finally` gọi `stop()`; kiểm kết quả gửi MIDI | `core/engine/_tone.py:763`, `:406` |
| 5 | Ticket hỗ trợ đính kèm `app.log` | `core/support.py:93-99` |

### P1 — hai tuần tới

| # | Việc |
|---|---|
| 6 | Endpoint sự kiện + hàng đợi client + đếm thành công/thất bại trên trang admin |
| 7 | Cấu hình từ xa qua `/license/verify` (danh sách khoá định sẵn) |
| 8 | Nút "Gửi báo cáo lỗi"; đưa `tools/chan_doan/*` vào bộ cài |
| 9 | Ghi nguyên tử nốt các hàng đợi còn lại (`tone_share.py:327`, `support.py:120`, `crash_reporter.py:106`) — trên máy dev đang có sẵn một `tone_share_queue.json` cụt 69 byte từ 10/09 |

### P2 — trong tháng

| # | Việc |
|---|---|
| 10 | Vá CI: chạy test khi phát hành, thêm `pytest-qt`, bỏ lọc đường dẫn, bỏ `-x` |
| 11 | Bộ đối chiếu vàng bằng audio tự tổng hợp + job librosa thật |
| 12 | Canary hàng ngày trên máy dev |
| 13 | Chuông báo yt-dlp cũ trong app |
| 14 | `tools/batch_detect_tone.py` đang ghi kết quả máy dò với `source="human"` vào `manual_timelines.json` — lớp cache ưu tiên CAO NHẤT. Sửa thành `auto` |

---

## 5. Sổ tay xử lý khi khách báo lỗi

| Khách thấy gì | Nghi phạm | Làm ngay | Vá gốc |
|---|---|---|---|
| "Dò tone quá lâu… nên đã dừng" | Khâu tải treo | `thu_tai_youtube.bat` → xem chặng nào chậm | P0-1 |
| "Đã tải được audio nhưng phân tích âm điệu bị lỗi" | Cache numba hỏng | `kiem_tra_tone.bat`; máy bản cũ thì `chua_loi_do_tone.bat` | Đã vá 1.7.8 |
| "Không tải được audio… và phương án nghe loa cũng thất bại" | Mạng + loa không phải mặc định | `thu_tai_youtube.bat`; kiểm loa mặc định Windows | P0-1 |
| "Không tìm thấy YouTube đang mở trên trình duyệt" | Watcher/CDP | Kiểm cờ `--remote-debugging-port` trên shortcut | — |
| App hiện tone đúng nhưng Studio One không đổi | MIDI không tới | `tools/chan_doan/ChanDoan.bat` mục 5 | P0-4 (hiện app **không** phát hiện được) |
| Dò tone im lặng, không bao giờ chạy nữa | Phiên kẹt SCANNING | Khởi động lại app | P0-4 |
| Cả loạt máy cùng hỏng một ngày | YouTube đổi cơ chế | Xem tỉ lệ thành công trên admin; đẩy cấu hình từ xa | P1-6, P1-7 |

---

## 6. Thế nào là xong

Đo được, không cảm tính:

1. Mọi lần dò tone thất bại để lại **đúng một dòng ERROR có mã chặng** trong `errors.log`.
2. **95% lượt dò tone xong dưới 20 giây**, không lượt nào vượt 60 giây (đo bằng sự kiện gửi về).
3. **Không lượt nào kết thúc bằng tay trắng**: luôn có tone từ cache, cộng đồng, nghe loa, hoặc một
   lời mời nhập tay.
4. Sự cố diện rộng được phát hiện **trong vòng 24 giờ mà không cần khách gọi**.
5. Sửa được tham số tầng YouTube **không cần phát hành bản mới**.
6. Đổi thuật toán dò tone mà **biết chắc độ chính xác không tụt**, nhờ bộ đối chiếu vàng.

---

## 7. Đánh đổi phải chấp nhận

- **Quyền riêng tư**: sự kiện gửi về chỉ mang mã lỗi và số đo, không mang tên bài hay đường dẫn;
  phải có công tắc tắt trong Thiết lập, mặc định bật, nói rõ với khách.
- **Cấu hình từ xa là con dao hai lưỡi**: đặt sai một giá trị là hỏng cả đội máy. Chỉ nhận khoá
  định sẵn, kiểm khoảng giá trị, và luôn có đường lùi về mặc định khi server im.
- **Nghe loa dự phòng đòi bài phải đang phát qua loa mặc định** — không đúng với mọi dàn máy quán.
  Nó cứu được nhiều ca, không phải mọi ca.
- **Canary trên CI sẽ có báo động giả** vì YouTube hay chặn IP trung tâm dữ liệu. Nguồn tin cậy là
  số liệu từ máy khách thật; canary chỉ là tuyến phụ.
- **Mỗi lớp phòng thủ là thêm mã phải nuôi.** Ưu tiên P0 là những thứ vừa ít mã vừa chặn đúng hai
  cảnh đã xảy ra thật; P1 trở đi mới là đầu tư dài hạn.
