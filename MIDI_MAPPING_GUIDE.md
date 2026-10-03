# 🎵 Hướng dẫn MIDI Mapping - QuangLuuMIDI → Studio One 7

## Yêu cầu

- **loopMIDI** với **hai** port: `QuangLuuMIDI` (app gửi lệnh) và `QLS_PhanHoi`
  (Studio One gửi trả). `setup_all.bat` tạo sẵn cả hai.
- **Studio One 7** Professional
- **Quang Lưu Studio** app

---

## Bước 1: Cài đặt Control Surface

Chạy script install:

```bash
install_surface.bat
```

Hoặc copy thủ công:
```
Từ:  studio_one\QuangLuuMIDI.surface.xml
Đến: %APPDATA%\PreSonus\Studio One 7\User Devices\QuangLuuMIDI\QuangLuuMIDI.surface.xml
```

---

## Bước 2: Thêm Device trong Studio One

1. Mở **Studio One → Options → External Devices**
2. Click **Add...**
3. Chọn **New Control Surface**
4. Đặt tên: `QuangLuuMIDI`
5. **Receive From:** chọn `QuangLuuMIDI` (loopMIDI port)
6. **Send To:** chọn `QLS_PhanHoi` — để app biết Studio One đã nạp bài xong chưa.
   Tuyệt đối **không** chọn `QuangLuuMIDI`: Studio One sẽ nghe lại chính nó, thành vòng vô tận.
7. Click **OK**

---

## Bước 3: Mapping Controls

### Cách 1: MIDI Learn (Nhanh)

1. Click chuột phải vào parameter muốn điều khiển (volume fader, plugin knob...)
2. Chọn **"Assign MIDI Control"** hoặc **"MIDI Learn"**
3. Di chuyển slider/nhấn nút trên app Quang Lưu Studio
4. Done! Parameter đã được gán

### Cách 2: Control Link (Chuyên nghiệp)

1. Mở **Control Link** panel (menu View → Control Link)
2. Bật **MIDI Learn** mode
3. Di chuyển control trên app → Studio One detect CC
4. Click vào parameter trong Studio One
5. Hai bên tự động liên kết

---

## Danh sách MIDI CC Controls

### Tone Controls
| Control | CC | Loại | Range | Chức năng |
|---------|-----|------|-------|-----------|
| Tone Nhạc | 10 | Knob | 0-127 | Pitch shift nhạc (-12 đến +12) |
| Tone Giọng | 11 | Knob | 0-127 | Pitch shift giọng (-12 đến +12) |

### Mixer Controls
| Control | CC | Loại | Range | Chức năng |
|---------|-----|------|-------|-----------|
| Mix Nhạc | 20 | Fader | 0-127 | Volume nhạc (0-100%) |
| Mix Mic | 21 | Fader | 0-127 | Volume mic (0-100%) |
| Mix Vang | 22 | Fader | 0-127 | Reverb level (0-100%) |
| Mix Bè | 23 | Fader | 0-127 | Backing vocal (0-100%) |
| Hiệu Ứng Giọng | 54 | Knob | 0-127 | Thanh "↕ Giọng" ở mixer: chất giọng em bé ↔ robot (-12…+12). Trước bản này thanh gửi nhầm CC 10 (Tone Nhạc) — **phải gán lại** control *Hiệu Ứng Giọng* vào plugin hiệu ứng giọng |

> Bảng dưới khớp với `studio_one/QuangLuuMIDI.surface.xml` và `midi_cc` trong
> `core/config.py` (test `tests/test_surface_xml.py` giữ hai bên đồng bộ). Tên cột
> **Control** là tên hiện trong Studio One khi gán Control Link.

### Tone / Auto-Tune (tone bài)
| Control | CC | Loại | Values | Chức năng |
|---------|-----|------|--------|-----------|
| Key Root | 33 | Knob | 0-127 | Tone gốc cho Auto-Tune (C→B, bảng `key_midi_map`) |
| Scale Type | 35 | Knob | 0-127 | Thể trưởng/thứ (bảng `scale_midi_map`) |
| Key Scale | 34 | Knob | — | **Không dùng nữa** — app gửi thể qua CC 35 |
| Mode (Live Tuner) | 30 | Knob | 0-127 | Tab "Chế độ" của bảng cân chỉnh — **không** phải nút Dân Ca |
| AutoKey | 31 | Button | 0/127 | Bật/tắt AutoKey — **không** phải nút Auto-Tune |
| Score Trigger | 32 | Button | 0/127 | Kích hoạt chấm điểm |
| Tune On/Off | 36 | Button | 0/127 | Control đời cũ — nút Auto-Tune trên app **không** dùng CC này |

### Nút bật/tắt trên app (panel Công cụ)
| Control | CC | Loại | Values mặc định | Chức năng |
|---------|-----|------|--------|-----------|
| Auto-Tune | 40 | Button | 127 = bật, 0 = tắt | Nút Auto-Tune trên app |
| Fix Méo | 45 | Button | BẬT = `mode_midi_map["Fix Méo"]` (127), TẮT = 0 | Chống méo giọng |
| Bè | 47 | Button | 127 = bật, 0 = tắt | Hiệu ứng bè giọng |
| Tắt Ồn | 48 | Button | 127 = bật, 0 = tắt | Khử tiếng ồn nền cho mic |

### Nút MODE (mỗi nút bật/tắt độc lập)
| Control | CC | Loại | Values | Chức năng |
|---------|-----|------|--------|-----------|
| Mode Dân Ca | 46 | Button | 0/127 | Chế độ Dân Ca |
| Mode Lofi | 37 | Button | 0/127 | Chế độ Lofi |
| Mode Remix | 38 | Button | 0/127 | Chế độ Remix |
| Mode Đa Thể Loại | 39 | Button | 0/127 | Chế độ Đa Thể Loại |

### Khác
| Control | CC | Loại | Values | Chức năng |
|---------|-----|------|--------|-----------|
| Mute Multi 1–4 | 41–44 | Button | 0/127 | Tắt Vang phụ trợ (`mute_multi_cc`; mặc định chỉ dùng CC 41 kèm Mute Vang) |
| Ping Sẵn Sàng | 49 | Knob | 0-127 | Hỏi–đáp: app gửi N, Studio One gửi trả N qua `QLS_PhanHoi`. Gán vào một tham số vô hại **trong bài** (vd Pan của track `PING` đã mute), **không** gán Global |

### Gán nút bật/tắt vào plugin — để đèn trên app khớp với Studio One

App hiển thị nút theo lệnh **nó đã gửi** (Studio One chưa gửi trạng thái về), nên cách
gán phải đảm bảo lệnh app gửi ra đúng nghĩa:

1. **Đúng chiều.** Mặc định app hiểu **127 = BẬT**. Nếu gán vào tham số kiểu
   **Bypass** (127 = bỏ qua plugin = TẮT), đánh dấu Bypass cho nút đó:
   bật **Dev Mode** (`Ctrl+Shift+D`) → chuột phải nút → **Sửa** → tích
   **"Gán vào Bypass của plugin"** → **Lưu**. Có hiệu lực ngay, không cần mở lại
   app — app gửi lại trạng thái hiện tại theo chiều mới. Dùng được cho Auto-Tune,
   Fix Méo, Bè, Tắt Ồn, 4 nút MODE và nút tự thêm.
   Cờ được lưu vào `%APPDATA%\QuangLuuStudio\calibration_overrides.json`
   (`toggle_invert` cho nút Công cụ, `mode_config` cho nút MODE) — vẫn sửa tay được:
   ```json
   { "toggle_invert": { "tone_auto": true } }
   ```
2. **Giá trị tuyệt đối.** Studio One phải hiểu 127/0 là BẬT/TẮT, không phải "mỗi
   lần nhận là đảo trạng thái" — app gửi lại trạng thái tối đa 4 lần khi Studio One
   vừa mở; nếu mỗi lần đảo thì kết quả như tung đồng xu. Thử: đóng rồi mở lại Studio
   One khi app đang chạy, theo dõi plugin ~1 phút — không được nhấp nháy.
3. **Gán theo bài** trong bài mẫu, lưu bài; máy chế độ khách thì chốt lại bản mẫu.
4. Chỉ bật/tắt từ app. Bấm thẳng trong Studio One thì app không biết (xem
   `docs/PLAN_SO_READY_HANDSHAKE.md` mục 8).

### Nhập giá trị theo Studio One (Dev Mode)

Khi thêm/sửa nút ở Dev Mode, **không cần tự tính số MIDI**. Chọn **Kiểu tham số**
đúng với control đã gán trong Studio One rồi nhập giá trị y như Studio One hiển thị;
app tự đổi sang MIDI và hiện số MIDI + giá trị Studio One thực nhận ngay bên cạnh:

| Kiểu tham số | Nhập | Ví dụ → MIDI |
|---|---|---|
| Công tắc | Chỉ chọn có phải Bypass hay không | BẬT → On (127) · Bypass: BẬT → Bypass Off (0) |
| Phần trăm | % trên núm (Mix, Dry/Wet, Send…) | 75% → 95 |
| Khoảng số | Dải của núm + giá trị | dải -12…+12 st, đặt +5 → 90 |
| Danh sách lựa chọn | Tên các mục theo thứ tự, chọn mục cho BẬT/TẮT | `Tắt, Nhẹ, Vừa, Mạnh`, chọn Vừa → 85 |
| MIDI thô | 0–127 | cho trường hợp đặc biệt |

"Khoảng số" chỉ chính xác với núm chia đều. Núm kiểu tần số/thời gian (thang log) và
fader âm lượng (dB) của Studio One không tuyến tính — với các control đó dùng MIDI thô.
Nút cũ chỉ có số MIDI: 127/0 tự hiện thành Công tắc, 0/127 thành Công tắc + Bypass,
số khác hiện ở dạng MIDI thô.

### Mixer Mute Toggles (Icon buttons bên dưới thanh cuộn)
| Control | CC | Loại | Values | Chức năng |
|---------|-----|------|--------|-----------|
| Mute Nhạc | 50 | Button | 0/127 | Tắt/mở kênh nhạc |
| Mute Mic | 51 | Button | 0/127 | Tắt/mở kênh mic |
| Mute Vang | 52 | Button | 0/127 | Tắt/mở reverb |
| Mute Bè | 53 | Button | 0/127 | Tắt/mở backing vocal |

---

## Troubleshooting

### Studio One không nhận MIDI?
- Kiểm tra **loopMIDI** đang chạy và có port `QuangLuuMIDI`
- Kiểm tra **External Devices** đã chọn đúng MIDI input port
- Thử restart Studio One sau khi thêm device

### Control không xuất hiện trong danh sách?
- Kiểm tra file `.surface.xml` đã nằm đúng thư mục
- Chạy lại `install_surface.bat`
- Restart Studio One

### App gửi lệnh lúc Studio One chưa nạp xong bài?
- Kiểm tra port `QLS_PhanHoi` có trong loopMIDI (chạy `setup_midi_ports.ps1`)
- Kiểm tra **Send To** của thiết bị QuangLuuMIDI trỏ tới `QLS_PhanHoi`
- Kiểm tra control **Ping Sẵn Sàng** đã gán vào một tham số trong bài mẫu
- Chưa gán thì app tự quay về cách hẹn giờ (bắn lại MIDI ở +3/10/25/50 giây)

### MIDI Learn không hoạt động?
- Đảm bảo app Quang Lưu Studio đang kết nối MIDI (thanh status hiện "Đã kết nối")
- Thử gửi MIDI CC bằng cách di chuyển slider trong app trước khi MIDI Learn
