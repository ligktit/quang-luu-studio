# Thăm dò Cubase: nạp bài, hộp thoại, MIDI Remote, fader

Công cụ cho **kỹ thuật viên**, chạy trên máy đã (hoặc sắp) cài Cubase + loopMIDI. Không cần Python.
Kết quả dùng để trả lời các mục **[cần đo máy thật]** trong `docs/NGHIEN_CUU_HO_TRO_CUBASE.md`
trước khi viết adapter Cubase trong app.

| Tệp | Vai trò |
|---|---|
| `ThamDoCubase.bat` | Bấm đúp để chạy (theo dõi 4 phút). Tham số truyền thẳng cho `.ps1` |
| `ThamDoCubase.ps1` | Khảo sát cài đặt + theo dõi process/cửa sổ/MIDI |
| `..\..\cubase\QuangLuu_QuangLuuMIDI.js` | Script MIDI Remote bản thăm dò, Cubase nạp để trả lời ping và báo trạng thái |

## Công cụ đo gì

| # | Câu hỏi | Đo bằng |
|---|---|---|
| 1 | Cubase cài ở đâu, exe/process tên gì, `.cpr` gắn với lệnh nào, prefs ở đâu | Mục A của báo cáo |
| 2 | Có cờ "Release Driver when Application is in Background" trong prefs không | Mục A3 (grep chữ `release` trong `*.xml`) |
| 3 | Mở `.cpr` bằng bấm đúp có đi thẳng vào bài hay dừng ở Steinberg Hub | Dòng `[CB] THAY STEINBERG HUB` |
| 4 | Tiêu đề và class cửa sổ chính; hộp thoại Save là class gì (có phải `#32770`) | `[CB] Cua so PROJECT dau tien`, `[HOP THOAI]`, bảng "MOI CUA SO DA THAY" |
| 5 | Cubase có nhận script, có **trả lời ping** (CC 49) không, trễ bao lâu | `[PING]` |
| 6 | Lúc nào bài nạp xong tới mức mixer có track (tín hiệu "sẵn sàng") | `[KENH]` — script báo tên kênh qua CC 60–67 |
| 7 | Fader 0 dB của Cubase ứng với giá trị CC nào (Studio One = 76) | `[FADER]` khi kéo fader tay |
| 8 | Plugin ở insert slot kênh Mic có những tham số nào (chỉ số, tên, giá trị hiển thị) | Script gửi SysEx về `QLS_PhanHoi`; nghe bằng `tools/tham_do_cubase/nghe_phan_hoi.py` (hoặc Script Console) |

## Cài đặt (một lần)

1. **Cổng MIDI.** Chạy `setup_midi_ports.ps1` ở gốc repo (hoặc `setup_all.bat` trong thư mục cài đặt).
   Cần đủ hai cổng `QuangLuuMIDI` và `QLS_PhanHoi`. Cổng phải có **trước khi mở Cubase**.
2. **Cubase.** Chưa có thì: cài Steinberg Download Assistant → đăng nhập MySteinberg → trên web
   steinberg.net chọn Cubase Pro "Try now" (**đăng nhập trước rồi mới bấm**, phải xác nhận email newsletter
   thì trial mới vào tài khoản) → trong Download Assistant tải Cubase Pro → mở **Steinberg Activation Manager**,
   tab *Not Activated*, bấm Activate. Trial 60 ngày tính từ lúc bấm trên web. Lưu ý: cài Cubase xong
   nên mở một lần cho nó tạo prefs rồi đóng.
3. **Script MIDI Remote.** `ThamDoCubase.bat -CaiScript` → chép vào
   `Documents\Steinberg\Cubase\MIDI Remote\Driver Scripts\Local\QuangLuu\QuangLuuMIDI\`.
   Trong Cubase: Lower Zone → **MIDI Remote** → biểu tượng bánh răng → **Reload Scripts** (hoặc mở lại Cubase).
   Cubase tự kích hoạt khi thấy đủ hai cổng. Nếu không hiện thiết bị "QuangLuu QuangLuuMIDI":
   Studio Setup → MIDI Port Setup → bỏ `QuangLuuMIDI` khỏi *All MIDI Inputs*.
4. **Bài mẫu `.cpr`.** Tạo project với thứ tự track audio **cố định** (MIDI Remote gán theo chỉ số):

   | Chỉ số | Track | Ghi chú |
   |---|---|---|
   | 0 | Nhạc | |
   | 1 | Mic | Insert slot 1 = plugin Auto-Tune (hoặc plugin pitch dùng thật) |
   | 2 | Vang | |
   | 3 | Bè | |

   Chỉ số tính trong mixer **không kể** input/output channel. Lưu ở đường dẫn ngắn, ví dụ `D:\QLS\mau.cpr`.

## Chạy thử

**Tắt app Quang Lưu Studio trong lúc thử.**

### Kịch bản A — mở Cubase từ file `.cpr` (quan trọng nhất)

1. Đóng Cubase. Bấm đúp `ThamDoCubase.bat`.
2. Trong 10 giây: bấm đúp file `.cpr` bài mẫu.
3. Khi bài hiện đầy đủ: kéo fader kênh **Mic** về đúng **0 dB** (Ctrl+click fader), bấm **Mute** kênh Nhạc rồi bỏ.
4. (Tuỳ chọn) Script Console: chuột phải thanh công cụ của tab MIDI Remote ở lower zone → bật **Scripting Tools** → biểu tượng thứ hai "Open MIDI Remote Script Console". Danh sách log không cuộn được bằng chuột, nên ưu tiên đọc qua SysEx (`nghe_phan_hoi.py`).
5. Sửa gì đó rồi **đóng Cubase** để hiện hộp thoại Save → bấm *Don't Save*.
6. Để script chạy hết hoặc Ctrl+C. Báo cáo ở Desktop: `QLS_ThamDoCubase_<MÁY>_<giờ>.txt`.

### Kịch bản B — Cubase đang mở sẵn

```bat
ThamDoCubase.bat -Seconds 60
```

### Kịch bản C — chỉ khảo sát cài đặt (không cần Cubase chạy)

```bat
ThamDoCubase.bat -ChiKhaoSat
```

### Kịch bản D — mở Cubase bằng `.exe` không tham số

Như A nhưng mở `CubaseN.exe` trực tiếp. Mục đích: xác nhận Hub xuất hiện và tiêu đề/class của nó, để
app biết tránh.

## Đọc kết quả

- `[PING] ... tre N ms` xuất hiện → Cubase nhận script và trả lời. Không có → xem KẾT LUẬN cuối báo cáo.
- `[KENH] Lan dau Cubase bao ten kenh` so với `Cua so PROJECT dau tien` → khoảng cách này thay cho mốc
  hẹn giờ +3/10/25/50 s hiện tại.
- `[FADER] CC 21 = N` lúc fader Mic ở 0 dB → N là hằng số thay cho 76 của Studio One.
- `[HOP THOAI] class=...` → nếu không phải `#32770` thì adapter Cubase phải dùng nhánh UI Automation.
- Mục A3 không thấy chữ `release` → cần mở Studio Setup → Audio System xem cờ *Release Driver* rồi tìm
  lại tên khoá trong prefs (so sánh file trước/sau khi đổi).

Xong việc: `ThamDoCubase.bat -GoScript` nếu muốn gỡ script thăm dò.

## Đọc tham số plugin và quét giá trị (không cần Script Console)

Script gửi về `QLS_PhanHoi` bằng SysEx `F0 7D 'Q' 'L' <loại> <ascii> F7`:

| Loại | Nội dung |
|---|---|
| 1 | `param|i|<tên plugin>|<tên tham số>` — tham số thứ `i` của plugin ở insert đầu tiên kênh Mic |
| 2 | `plugin|tên|hãng|bản` |
| 3 | `page_active` |
| 4 | `disp|i|<giá trị hiển thị>|<đơn vị>` — mỗi khi tham số `i` đổi |
| 5 | `viewer|<tiêu đề>` |

App đặt tham số `i` bằng **CC 80+i** (0–127 ≈ 0–1). Quét để lập bảng giá trị:

```bat
.venv\Scripts\python.exe tools\tham_do_cubase\quet_tham_so.py 86 87
```

(86 = tham số 6, 87 = tham số 7 …). Kết quả là các khoảng CC → giá trị hiển thị, ví dụ với Steinberg Pitch Correct
(Cubase 13.0.10): Key `C 0–5, C# 6–17, D 18–28 … B 122–127`; Scale `Chromatic 0–21, Major 22–63, Minor 64–105, Custom 106–127`.

Antares **Auto-Tune Pro 11** (VST3, máy khách 2026-10-06): tham số 0 Correction Mode, 1 Scale (bảng cổ điển, KHÔNG
phải Scale trên GUI), **2 Key**, 3 Detune, 4 Retune Speed, 5–7 Vibrato, 8 Re-Track ARA, 9 Tracking, 10 Input Type,
11 Use Classic Mode DSP, **162 "Modern Scale"** (= dropdown Scale của GUI). Key: cùng dải như Pitch Correct
(C 0–5 … B 122–127). Modern Scale: Chromatic 0–5, **Major 6–13, Minor 14–22**, Harmonic Minor 23–31 → app bắt
Major = 10, Minor = 18 bằng Cân chỉnh Auto-Tune. Script tự chọn hồ sơ theo tên tham số "Key" (`HO_SO_PLUGIN`).
Không có Python trên máy khách thì đọc bằng Script Console (lọc Log Messages, kéo thanh cuộn xuống cuối).

## Giới hạn API Cubase 13.0.10

`Documents\Steinberg\Cubase\MIDI Remote\Driver Scripts\.api\v1\midiremote_api_v1.d.ts` của bản này **không có**
`makeDirectAccess` / `accessSlotAtIndex` / `setProcessValue` trên HostValue. Chỉ có `makeInsertEffectViewer().excludeEmptySlots()`
+ `mParameterBankZone.makeParameterValue()` (tham số theo thứ tự) và `makeValueBinding`. Script vì vậy gán theo **chỉ số tham số**,
app tự tìm chỉ số của "Key"/"Scale" từ SysEx loại 1.

Kênh NHAC (`viewerNhac`, log `nhac param[i]`/`nhac disp[i]`): Waves SoundShifter Pitch Stereo có 10 tham số, bank lặp chu kỳ 10;
**tham số 4 "PitchSemitones"** nhận 0–127 = −12…+12 bán cung (1:1 với Tone Giọng của app, đo 2026-10-07).
