# Plan: xác định Studio One đã nạp bài xong và sẵn sàng nhận MIDI

> Trạng thái: **Giai đoạn 0 — đang thăm dò trên máy thật.** Chưa sửa logic app.
>
> Phần hạ tầng đã làm trước để máy khách có sẵn đồ khi tính năng lên: control `readyPing`
> (CC 49) trong `studio_one/QuangLuuMIDI.surface.xml`, khoá `ready_ping` trong
> `core/config.py` + `app_config.json`, và `setup_midi_ports.ps1` — bộ cài tự tạo cổng
> `QuangLuuMIDI` + `QLS_PhanHoi` rồi **đếm lại** để chắc chắn cổng đã hiện ra.
>
> Công cụ thăm dò: `tools/tham_do_studio_one/` (hướng dẫn trong `HUONG_DAN.md`).

## 1. Vấn đề

App đẩy trạng thái (Auto-Tune, MODE, Tắt Ồn, Tắt Vang, tone, mixer) sang Studio One qua
`_sync_midi_states`, nhưng không có cách nào biết Studio One đã nghe được hay chưa:

| Lượt gửi | Chỗ gọi | Thực tế |
|---|---|---|
| Khởi động, nếu cổng đã mở | `frontend_qt.py:266` → `_update_midi_status` | Trước cả lệnh mở Studio One |
| Ngay sau lệnh mở Studio One | `frontend_qt.py:325` | `os.startfile` trả về ngay (`core/engine/_lifecycle.py:100`), Studio One chưa nạp gì |
| Theo giờ, từ lúc thấy cửa sổ "Studio One" | `core/so_windows.py` `ReadySchedule`, mốc +3/10/25/50s | Đoán mò — cửa sổ hiện ra trước lúc bài nạp xong |

Hệ quả: bài nạp chậm hơn ~50s sau khi cửa sổ hiện (máy yếu, nhiều plugin) thì cả 4 lượt đều trượt,
Studio One lệch trạng thái với giao diện cả buổi, mà chế độ khách giấu cửa sổ nên không ai thấy.

Nguyên nhân gốc: cổng loopMIDI `QuangLuuMIDI` tồn tại độc lập với Studio One, nên
`is_midi_connected()` (= `outport is not None`, `core/engine/_midi.py:25`) không nói lên gì.

## 2. Hiện trạng liên quan

- `studio_one/QuangLuuMIDI.surface.xml`: trước đây mọi control đều `options="receive public"`
  → Studio One **không gửi gì ngược lại**. Nay `readyPing` là control duy nhất có `transmit`.
- `core/midi.py:start_listening` có sẵn nhưng **không nơi nào gọi** → `_on_midi_cc_received`
  (`frontend_qt.py:930`) thực tế chưa bao giờ chạy — kéo theo mục 8.
- App dò cổng theo kiểu "tên **có chứa** `QuangLuuMIDI`" (`core/midi.py:49`, `:135`).
- loopMIDI trả lại mọi tin gửi vào cho mọi người đang nghe cổng đó → app **không thể** nghe phản
  hồi trên chính `QuangLuuMIDI` (sẽ nghe lại tiếng mình).
- Studio One hỗ trợ gửi ngược: `options="transmit receive public"` + mục **Send To** của thiết bị
  ([ví dụ surface.xml](https://github.com/Sian-Lee-SA/StudioOne-LaunchKey-Mini-MK3/blob/master/LaunchKeyMKIII_basic.surface.xml),
  [PreSonus KB](https://support.presonus.com/hc/en-us/articles/29973355204237-Studio-One-Pro-7-Basic-Midi-Setup-New-Keyboard-Control-Surface-Instrument-Faderport)).

## 3. Giải pháp đã chọn: hỏi–đáp MIDI (ping/pong)

1. Control mới `readyPing` (CC 49 — dải trống) trong surface.xml, `transmit receive public`.
2. Cổng loopMIDI thứ hai `QLS_PhanHoi` làm **Send To** của thiết bị. Tên cố ý không chứa `QuangLuuMIDI`.
3. Bản mẫu `.song` có track `PING` (mute), Pan gán vào `readyPing` **theo bài** (không Global).
4. App gửi CC 49 = N (đổi liên tục), chờ Studio One trả CC 49 ≈ N trên `QLS_PhanHoi`.
   Nhận đúng = bảng MIDI của bài đã chạy = **sẵn sàng thật**, lúc đó mới `_sync_midi_states`.

## 4. Giai đoạn 0 — thăm dò (đang làm)

Chưa kiểm chứng được trên máy dev (không có Studio One). `ThamDoStudioOne.ps1` đo:

| Câu hỏi | Nếu KHÔNG | Hướng xử lý |
|---|---|---|
| Studio One có gửi trả giá trị vừa nhận không? | Chặn vòng echo | Phương án B dưới đây |
| Lúc nạp bài có tự gửi giá trị control ra không? | — | Nếu CÓ: đó cũng là tín hiệu sẵn sàng, không cần ping |
| Trả lời sau cửa sổ chính bao lâu (máy nhanh / chậm)? | — | Chọn timeout + nhịp ping |
| Giá trị trả về có bị làm tròn không? | — | Độ lệch cho phép khi so khớp (đang để ±2) |

Mở rộng — **kịch bản D** (`-BatTransmit` → mở lại Studio One → `-KiemTraNut` →
`-KhoiPhucSurface`), xem mục 8:

| Câu hỏi | Nếu KHÔNG | Hướng xử lý |
|---|---|---|
| App gửi BẬT/TẮT nút → Studio One có gửi trả đúng CC đó không? | Không xác nhận được lệnh | Chỉ còn đồng bộ ngược, hoặc dùng ping làm bằng chứng "đã nghe" |
| Giá trị trả về có đúng 127/0 (≥64 / <64) không? | — | Chỉnh ngưỡng đọc |
| Bấm nút ngay trong Studio One → Studio One có tự báo ra không? | Không đồng bộ ngược được | App vẫn chỉ biết lệnh của chính nó |

**Phương án B** (nếu Studio One chặn echo): ping bằng hai control — gửi vào `readyPingIn`, gán
`readyPingIn` và `readyPingOut` (transmit) vào **cùng** một tham số; Studio One đổi tham số theo
control vào và báo ra qua control kia. Cần thăm dò thêm một vòng.

**Phương án C** (nếu cả hai không được): giữ lịch giờ hiện tại, bổ sung dò tiêu đề cửa sổ chứa tên
bài (dữ liệu tiêu đề đã được `ThamDoStudioOne.ps1` ghi lại sẵn).

## 5. Thiết kế dự kiến (sau khi thăm dò xác nhận)

- **Config** — ĐÃ LÀM: `midi_cc.ready_ping = 49` trong `core/config.py` + `app_config.json`.
  Còn lại: `midi_feedback_port` (rỗng = tắt, dùng lịch giờ cũ).
- **surface.xml** — ĐÃ LÀM: control `readyPing` (`transmit receive public`);
  `tests/test_surface_xml.py` giữ nó đồng bộ với config.
- **Bộ cài** — ĐÃ LÀM: `setup_midi_ports.ps1` (tạo 2 cổng + kiểm chứng + tự cài loopMIDI qua
  winget), `setup_all.bat` gọi ở bước 1, `.iss` ship file này; hướng dẫn Send To trong
  `MIDI_MAPPING_GUIDE.md` và `install_surface.bat`.
- **`core/midi.py`**: `start_feedback_listener(port)` — khớp tên chính xác trước, rồi mới "có
  chứa"; đồng thời cho `connect()`/`start_listening()` **loại trừ** tên cổng phản hồi.
- **Máy trạng thái thuần** (`core/so_windows.py`, cạnh `ReadySchedule`, test bằng thời gian giả):
  - `CHO` (không có cửa sổ Studio One) → `DO` (có cửa sổ: ping mỗi 1s, giá trị đổi) →
    `SAN_SANG` (pong khớp) → bắn `_sync_midi_states` **một lần**.
  - Ở `SAN_SANG` vẫn ping thưa (~10s). Mất pong liên tiếp N lần (bài bị nạp lại / đổi bài) → về
    `DO`, có pong lại thì đồng bộ lại.
  - Mất cửa sổ → về `CHO`.
  - Không mở được cổng phản hồi → dùng `ReadySchedule` cũ (+3/10/25/50s), ghi log một lần.
- **`frontend_qt.py`**: `ReadyWatcher` giữ nguyên giao diện `on_ready` → `_so_ready_signal`;
  bỏ/giữ lượt gửi dòng 266/325 (vô hại, CC idempotent). Pong CC 49 không đi vào `_on_midi_cc_received`.
- **Tài liệu / hỗ trợ**: `docs/KIOSK_MODE_GUIDE.md` mục 9; `tools/chan_doan/QLS_ChanDoan.ps1`
  kiểm có cổng `QLS_PhanHoi` và Send To; hướng dẫn dựng bản mẫu có track `PING`.

## 6. Rủi ro

| Rủi ro | Chặn bằng |
|---|---|
| Send To trỏ nhầm về `QuangLuuMIDI` → vòng phản hồi vô tận | Hướng dẫn + chẩn đoán phát hiện tin lạ trên cổng chính |
| Gán Ping kiểu Global → trả lời trước khi bài nạp | Hướng dẫn ghi rõ; thăm dò kịch bản A sẽ lộ (pong trước cả cửa sổ) |
| Bản mẫu cũ không có track `PING` | Không bao giờ có pong → hết thời gian chờ thì lùi về lịch giờ |
| Tên cổng phản hồi chứa `QuangLuuMIDI` | Loại trừ trong code + cảnh báo |
| Giá trị Pan bị làm tròn | So khớp theo khoảng, giá trị ping cách nhau xa |

## 7. Kiểm thử

- Unit: máy trạng thái hỏi–đáp với đồng hồ giả + MIDI giả (pong đúng / sai / trễ / mất / không có cổng).
- UI: `tests/ui/test_midi_resync_on_so_ready.py` — chỉ đồng bộ khi có pong; lùi về lịch giờ khi tắt.
- Máy thật: lặp lại kịch bản A/B/C của `HUONG_DAN.md` với app thật, đối chiếu log `[MIDI SYNC]`.

## 8. Mở rộng: nút hiển thị đúng trạng thái THẬT trong Studio One

### Hiện trạng (đã xác nhận trong code, 2026-09-27)

Nút MODE / Auto-Tune / Fix Méo / Bè / Tắt Ồn / Mute chỉ phản ánh **lệnh app
đã gửi**, không phải trạng thái trong Studio One:

- `start_listening()` không nơi nào gọi → `_on_midi_cc_received` (`frontend_qt.py:930`), dù đã
  viết sẵn phần cập nhật nút theo CC, **chưa bao giờ chạy**.
- Nếu có gọi thì nó nghe `QuangLuuMIDI` — cổng loopMIDI trả lại chính tin app gửi, tức nghe
  tiếng vọng của mình chứ không phải Studio One.
- surface.xml: 12 nút này chỉ `receive` — Studio One không gửi trạng thái chúng ra.
- `_set_mode` (`frontend_qt.py:3182`) ghi trạng thái **trước** khi gửi và không xét kết quả
  `send_midi` → MIDI rớt thì nút + dải vẫn báo BẬT. Tương tự các nút Công cụ.

Quyết định sản phẩm liên quan: **không** hiện cảnh báo "chưa chắc" cho khách — nếu lệnh không
được xác nhận thì xử lý NGẦM (gửi lại), không báo.

### Thiết kế dự kiến (chỉ làm nếu kịch bản D cho kết quả `XAC NHAN TRANG THAI DUNG DUOC`)

- surface.xml: bật `transmit` cho 12 nút (Send To = `QLS_PhanHoi` đã là điều kiện của hỏi–đáp).
- App nghe `QLS_PhanHoi` (dùng chung listener của hỏi–đáp ở mục 5), CC của 12 nút đi vào
  `_on_midi_cc_received` (đã có sẵn logic cập nhật nút theo CC); CC 49 đi vào máy trạng thái ping.
- Mỗi nút có hai trạng thái: **muốn** (người dùng bấm) và **đã xác nhận** (Studio One trả về).
  Đèn nút theo trạng thái **đã xác nhận**. Không có phản hồi trong ~1s → gửi lại
  ngầm vài lần; vẫn không có → giữ theo trạng thái muốn (hành vi như hiện nay), ghi log.
- Studio One tự báo khi bấm trong DAW → cập nhật nút trong app (đồng bộ ngược).
- Không mở được `QLS_PhanHoi` (máy cũ chưa có cổng) → giữ nguyên hành vi hiện tại.
- Rủi ro vòng lặp: app nhận CC từ Studio One KHÔNG được gửi lại CC đó (`_on_midi_cc_received`
  đã dùng `QSignalBlocker`, cần kiểm lại cho 12 nút).
