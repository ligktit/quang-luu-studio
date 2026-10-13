# Tự sửa âm thanh — Thiết kế

> Ngày: 2026-10-09 · Trạng thái: chờ duyệt · Giai đoạn 1 (bản tới) + phạm vi giai đoạn 2

## 1. Mục tiêu

Khách hay bị mất tiếng vì quên bật mic/nhạc trong Studio One (SO)/Cubase, hoặc chưa mở
DAW, hoặc Windows/card âm thanh đổi trạng thái. Tính năng "Tự sửa âm thanh":

- **Lúc mở app:** chỉ **kiểm tra và báo** (dải cảnh báo trên header + một câu TTS). Không sửa gì.
- **Khi khách bấm nút "Tự sửa âm thanh":** sửa những gì sửa được an toàn, kiểm tra lại,
  phần còn lại hướng dẫn làm tay bằng tiếng Việt.
- Tự sửa chỉ ép **Mic** và **Nhạc** về trạng thái bật. **Bè / Vang** giữ nguyên lựa chọn của khách.

Thành công = các lỗi nhóm A/B phổ biến (DAW chưa mở, kênh Mic/Nhạc tắt, loopMIDI tắt,
thiết bị phát mặc định nhảy sai, mute ở Windows/trình duyệt, Cubase "Release Driver") được
phát hiện lúc khởi động và sửa được bằng một lần bấm, không cần kỹ thuật vào máy.

## 2. Bối cảnh hiện tại (đã khảo sát)

- Đường nhạc trên máy khách: **Trình duyệt → thiết bị ảo (ASIOVADPRO / VB-Cable) → track
  Nhạc trong DAW → ASIO → card**. Mic: card → track Mic (Auto-Tune) → ASIO → card.
- App **chỉ gửi** MIDI sang DAW, không nghe phản hồi:
  - `MidiHandler.start_listening()` (`core/midi.py:122`) không được gọi, và nếu gọi thì mở nhầm
    cổng `QuangLuuMIDI` thay vì `QLS_PhanHoi`.
  - Script Cubase đã phát fader/mute 4 nhóm kênh lên `QLS_PhanHoi`
    (`cubase/QuangLuu_QuangLuuMIDI.js:123-124,174-186`). SO chỉ phát `readyPing` CC 49.
  - Handler phía app đã có: `_on_midi_cc_received` (`frontend_qt.py:1259`).
- DAW vẫn nhận CC 20 (fader Nhạc) và CC 50 (mute Nhạc) ở cả surface SO lẫn script Cubase.
- Lỗi sẵn có:
  - `_sync_midi_states` (`frontend_qt.py:1093`) không gửi lại mute Mic/Bè.
  - Chấm MIDI header (`frontend_qt.py:1192`) xanh cả khi DAW không chạy.
- Logic kiểm tra/sửa đã có nhưng nằm ngoài app: `tools/chan_doan/QLS_ChanDoan.ps1`,
  `QLS_SuaLoi.ps1` (loopMIDI + cổng, surface/script, Release Driver, quyền micro, Audiosrv,
  app chiếm thiết bị).
- Có sẵn để dùng lại: `so_windows.is_running/wait_for_main_window/ReadyWatcher`,
  `launch_app`, `close_studio_one_safely`, `get_browser_volume` (pycaw),
  `set_browser_volume`/CDP, `core/support.py`, `core/accessibility/announcer.py`.

## 3. Danh mục lỗi âm thanh thường gặp (nghiên cứu)

Ký hiệu giai đoạn: **G1** = làm ở giai đoạn 1, **G2** = giai đoạn 2, **HD** = chỉ hướng dẫn.

### A. Phần mềm chưa sẵn sàng
| # | Lỗi | GĐ |
|---|---|---|
| A1 | Chưa mở SO/Cubase | G1 |
| A2 | DAW kẹt ở hộp thoại (chọn driver ASIO, Missing ports, khôi phục project) | G1 (chỉ đưa lên trước + báo) |
| A3 | Kênh Mic/Nhạc trong DAW bị mute / fader ~0 | G1 |
| A4 | loopMIDI không chạy / thiếu cổng | G1 |
| A5 | Surface SO / script Cubase thiếu hoặc cũ | G1 |
| A6 | Player YouTube / tab trình duyệt bị tắt tiếng | G1 |

### B. Windows
| # | Lỗi | GĐ |
|---|---|---|
| B1 | Loa/mic mute hoặc âm lượng 0 ở cấp Windows | G1 |
| B2 | Thiết bị phát mặc định nhảy sai (HDMI, tai nghe, Bluetooth) → nhạc không vào DAW | G1 |
| B3 | Thiết bị bị Disable | G2 (Admin) |
| B4 | Âm lượng trình duyệt trong Volume Mixer bị kéo xuống | G1 |
| B5 | Quyền micro bị chặn (HKCU: G1; HKLM: G2) | G1/G2 |
| B6 | Dịch vụ Audiosrv / AudioEndpointBuilder dừng | G2 (Admin) |
| B7 | Exclusive mode — app khác chiếm card (Zoom, Discord, OBS, Voicemeeter) | G2 phát hiện, HD |
| B8 | Sample rate lệch giữa Windows và ASIO/DAW | G2 |
| B9 | "Listen to this device" / Enhancements gây vọng, đôi giọng | G2 |
| B10 | USB selective suspend làm card rớt giữa buổi | G2 (Admin) |

### C. Card âm thanh / driver / ASIO
| # | Lỗi | GĐ |
|---|---|---|
| C1 | Card USB không nhận / Code 10 — gồm lỗi KB5124008 (08/09/2026, Win 11 24H2/25H2, USB Audio Class 1.0) | G2 (phát hiện + restart device Admin), HD |
| C2 | Windows Update thay driver hãng bằng driver chung → mất ASIO | G2 phát hiện, HD |
| C3 | DAW chọn sai driver ASIO / driver bị app khác giữ | G2 (đọc cấu hình DAW), HD |
| C4 | Cubase bật "Release Driver when Application is in Background" (app ẩn Cubase → mất tiếng) | G1 |
| C5 | Cáp lỏng, phantom, gain về 0 trên card | HD (G2: đo tín hiệu) |

## 4. Kiến trúc

```
core/audio_doctor/
  __init__.py
  model.py           # Check, Finding, Status
  runner.py          # thứ tự phụ thuộc, luồng nền, timeout, chế độ check-only / fix
  context.py         # DoctorContext: engine, settings, daw profile, feedback, win_audio, clock
  feedback.py        # DawFeedback: trạng thái mute/fader 4 nhóm kênh từ QLS_PhanHoi
  win_audio.py       # bọc pycaw/comtypes: endpoint mute/volume, default endpoint (IPolicyConfig), session
  checks_bridge.py   # loopmidi, daw_remote
  checks_daw.py      # daw_running, daw_dialog, cubase_release_driver, ch_mic, ch_music
  checks_windows.py  # win_playback_default, win_playback_mute, win_mic
  checks_browser.py  # browser_session, yt_player
  guides.py          # câu hướng dẫn làm tay tiếng Việt theo mã mục
ui/dialogs/audio_doctor_dialog.py
```

### 4.1 Mô hình

```python
class Status(Enum): OK, LOI, KHONG_RO, BO_QUA, DA_SUA, CAN_LAM_TAY

@dataclass
class Finding:
    status: Status
    message: str            # câu tiếng Việt cho khách
    detail: str = ""        # kỹ thuật, ghi log
    fixable: bool = False
    needs_admin: bool = False   # G1 luôn False

class Check:
    id: str
    group: str              # "bridge" | "daw" | "windows" | "browser"
    requires: tuple[str, ...] = ()
    timeout_s: float = 10
    def detect(self, ctx) -> Finding: ...
    def fix(self, ctx, ask) -> Finding: ...   # ask(question) -> bool, chạy trên UI qua signal
```

- `Check` không import Qt. Các phụ thuộc bên ngoài đi qua `ctx` để có thể mock.
- `fix()` trả về Finding sau khi sửa. Runner luôn gọi lại `detect()` để xác nhận.
- `ask` là callback hỏi khách (đóng Cubase, xác nhận thiết bị ảo). Chế độ check-only không bao giờ gọi `fix()`.

### 4.2 Runner

- Thứ tự cố định theo nhóm: **bridge → daw → windows → browser**. Trong nhóm thì sắp theo `requires`.
- Mục có `requires` đang LOI/BO_QUA → mục này thành `BO_QUA` ("chờ sửa «…» trước").
- Mỗi mục chạy với timeout riêng. Quá giờ → `KHONG_RO` + ghi log, không treo cả lượt.
- Chạy trên `threading.Thread`. Tiến độ đẩy về UI qua Qt signal (adapter mỏng ở tầng UI).
- Chỉ một lượt chạy tại một thời điểm (lock). Bấm nút khi lượt khởi động đang chạy → chờ lượt đó xong rồi chạy lượt sửa.

### 4.3 Kiểm tra lúc mở app

- Không dùng mốc cố định. Chờ **cửa sổ chính DAW sẵn sàng** (`wait_for_main_window`, Cubase:
  tiêu đề có "Project") **+ 10 giây** ổn định, tối đa **180 giây** (settings
  `audio_doctor_startup_wait_s`, mặc định 180) cho máy/mạng yếu (DAW kiểm tra bản quyền qua mạng).
- Hết thời gian mà DAW chưa sẵn sàng → vẫn chạy kiểm tra, `daw_running` báo "chưa mở xong".
- Nếu DAW sẵn sàng muộn hơn → chạy lại kiểm tra **một lần** và gỡ cảnh báo nếu đã ổn.
- `auto_launch_studio_one` tắt và DAW không chạy → vẫn chờ tối đa thời gian trên rồi báo.
- Các mục trình duyệt/YouTube: chưa có player → `BO_QUA`.

### 4.4 Phản hồi từ DAW

- `MidiHandler` thêm cổng vào **`QLS_PhanHoi`** (tên lấy từ config, khai báo cạnh `MIDI_PORT_NAME`),
  mở lúc connect, đóng lúc shutdown, tự mở lại khi reconnect.
- `DawFeedback` lưu `{nhom: (muted, fader_cc, ts)}` cho nhac/mic/vang/be, cập nhật từ CC 20–23 / 50–53.
  Thread-safe.
- Callback vẫn chuyển tiếp vào `_on_midi_cc_received` có sẵn → nút app khớp thao tác tay trong Cubase.
- SO không gửi phản hồi → `ch_mic`/`ch_music` trả `KHONG_RO` lúc kiểm tra. Khi sửa thì gửi lệnh rồi báo
  "đã gửi lệnh bật" (không khẳng định đã xác nhận).
- `fader_unity_cc` và luật fader lấy từ `DawProfile` hiện có.

### 4.5 Lỗi sẵn có sửa cùng G1

1. `_sync_midi_states` gửi lại mute Mic (CC 51) và mute Bè (CC 53) theo `dashboard.mute_states`.
2. Chấm MIDI header chỉ xanh khi `outport` mở **và** `so_windows.is_running()`. Trạng thái thứ ba là
   "cổng mở, DAW chưa chạy": màu vàng + tooltip.

## 5. Các mục kiểm tra giai đoạn 1

| Mã | requires | Phát hiện | Sửa | Khi không sửa được |
|---|---|---|---|---|
| `loopmidi` | — | psutil tìm `loopMIDI.exe`; rtmidi liệt kê cổng có `QuangLuuMIDI` và `QLS_PhanHoi` | Mở `loopMIDI.exe` (Program Files / Program Files (x86)), chờ cổng ≤10 s. Thiếu cổng → ghi registry loopMIDI (HKCU, như `QLS_SuaLoi.ps1:789-853`), khởi động lại loopMIDI. Xong → reconnect MIDI | "Chưa cài loopMIDI — chạy setup_all.bat" |
| `daw_remote` | — | So file surface SO (`%APPDATA%\PreSonus\Studio One *`) / script Cubase (`Documents\Steinberg\Cubase\MIDI Remote\...\QuangLuu\QuangLuuMIDI\`) với bản đi kèm | Chép lại. Nếu DAW đang mở → `CAN_LAM_TAY`: "Khởi động lại Studio One/Cubase để nạp bản mới". Không tự tắt DAW | "Không tìm thấy thư mục cấu hình DAW — mở DAW một lần" |
| `daw_running` | — | `so_windows.is_running()` + có cửa sổ chính | `launch_app(studio_one_path)` → `wait_for_main_window` (≤180 s) → `_sync_midi_states` | "Chưa đặt đường dẫn Studio One/Cubase — vào Cài đặt" |
| `daw_dialog` | — | DAW chạy, không có cửa sổ chính nhưng có cửa sổ con hiện thuộc PID DAW | Không bấm hộ: `force_foreground` hộp thoại → `CAN_LAM_TAY` | "Studio One đang hỏi: «tiêu đề» — trả lời hộp thoại này" |
| `cubase_release_driver` | — (chỉ Cubase) | Đọc prefs Cubase như `QLS_ChanDoan.ps1:938-941` | Cubase đóng → sao lưu + sửa prefs. Cubase đang mở → `ask("Cần đóng Cubase để sửa. Đóng?")` → `close_studio_one_safely` → sửa → mở lại | "Tắt mục Release Driver trong Studio Setup" |
| `ch_mic` | `loopmidi`, `daw_running` | Cubase: `DawFeedback` mic muted hoặc fader ≤ ~−40 dB · SO: `KHONG_RO` | Gửi CC 51=0. Fader: giá trị lưu trên app nếu > −40 dB, không thì 0 dB. Cập nhật `mute_states` + UI. Cubase: chờ phản hồi ≤2 s để xác nhận | "Đã gửi lệnh bật Mic — nếu vẫn im, kiểm tra track Mic trong DAW" |
| `ch_music` | `loopmidi`, `daw_running` | như trên với nhóm nhạc | Gửi CC 50=0 + CC 20 về 0 dB (`fader_unity_cc`) | như trên |
| `win_playback_default` | — | Default render endpoint (eConsole + eMultimedia) ≠ `music_playback_device_id` | IPolicyConfig `SetDefaultEndpoint` cho cả hai role | "Không thấy thiết bị ảo «tên» — đã bị gỡ hoặc tắt" |
| `win_playback_mute` | `win_playback_default` | Endpoint thiết bị ảo mute hoặc <5% | Bỏ mute, đặt 100% | — |
| `win_mic` | — | Endpoint mic (thiết bị capture mặc định) mute; registry quyền micro HKCU `ConsentStore\microphone` (+ `NonPackaged`) = Deny | Bỏ mute; đặt HKCU = Allow. HKLM Deny → `CAN_LAM_TAY` (G2) | "Windows chặn micro toàn máy — cần kỹ thuật" |
| `browser_session` | `win_playback_default` | Session trình duyệt mute hoặc <5% | Bỏ mute, đặt 100% | — |
| `yt_player` | — | Player nhúng / CDP: muted hoặc volume 0; tab muted | Bỏ mute; volume = thanh Nhạc của app | — |

### 5.1 Thiết bị ảo "đúng"

- Khoá settings mới `music_playback_device_id` (endpoint ID, **không** theo số thứ tự).
- Tab Âm thanh trong Cài đặt thêm ô chọn "Thiết bị đưa nhạc vào DAW".
- Chưa có giá trị: lượt sửa đầu tiên đề xuất endpoint có tên khớp
  `ASIOVADPRO|VB-Audio|CABLE|Virtual` và `ask()` xác nhận một lần. Không khớp được thì `CAN_LAM_TAY` +
  mở Cài đặt. Lượt kiểm tra lúc khởi động khi chưa có giá trị → `BO_QUA`.

## 6. Giao diện

- **Dải cảnh báo header**:
  - Màu vàng, tĩnh (không nhấp nháy, khớp "Tắt hiệu ứng bắt mắt"). Ghi lỗi nặng nhất + "+N vấn đề khác".
  - Bấm vào thì mở hộp thoại. Tự ẩn khi lượt kiểm tra sau báo ổn.
  - TTS đọc một câu (`speak` theo đường thông báo tự động hiện có).
- **Nút "Tự sửa âm thanh"**:
  - Đặt ở bottom bar. Phím tắt Ctrl+Shift+A. Lệnh giọng nói "sửa âm thanh" / "sửa tiếng".
  - Chế độ khách (tech_lock) không khoá nút này.
- **Hộp thoại**:
  - Danh sách các mục chia 4 nhóm. Mỗi dòng có biểu tượng trạng thái + câu tiếng Việt.
  - Dòng `CAN_LAM_TAY` có nút "Hướng dẫn" (mở rộng các bước từ `guides.py`) và "Thử lại".
  - Câu hỏi `ask()` hiện ngay trong hộp thoại.
  - Nút "Gửi cho kỹ thuật" đính kết quả vào phiếu hỗ trợ (`core/support.py`).
  - Trợ năng: đổi trạng thái → `announcer.announce_state`, cuối lượt đọc tổng kết.
- **Nhật ký**: mỗi lượt ghi một dòng JSON vào `logs/audio_doctor.log`, gồm thời điểm, nguồn
  (`startup`/`button`/`voice`), DAW, và kết quả từng mục.

## 7. Xử lý lỗi

- Mọi exception trong `detect`/`fix` → `KHONG_RO` + traceback vào log. Không làm hỏng lượt chạy.
- pycaw/comtypes không có hoặc lỗi COM → các mục Windows `KHONG_RO`, không crash.
- Sửa prefs Cubase luôn sao lưu trước (`.bak` cạnh file, có dấu thời gian).
- Không có thao tác nào cần Admin trong G1.

## 8. Test

- `tests/core/audio_doctor/`:
  - Mỗi mục test ba trường hợp (ổn / lỗi → sửa xong / lỗi không sửa được) với `ctx` giả
    (`win_audio`, psutil, cổng MIDI, `DawFeedback`, đồng hồ giả).
  - Thêm ca SO → `KHONG_RO`.
- Runner:
  - thứ tự phụ thuộc → `BO_QUA`;
  - timeout;
  - check-only không gọi `fix()`;
  - chờ DAW sẵn sàng / tối đa 180 s / chạy lại một lần (đồng hồ giả);
  - khoá một lượt.
- `DawFeedback`: dãy CC giống script Cubase → trạng thái đúng + chuyển tiếp handler.
- Lỗi sẵn có:
  - `_sync_midi_states` gửi CC 51/53;
  - chấm MIDI vàng khi DAW không chạy.
- UI (pytest-qt, Python Windows `.venv`): hộp thoại hiện đúng trạng thái/nút; dải cảnh báo hiện/ẩn.
- Thủ công trên máy dev Cubase (và máy có SO):
  - tự mute Mic + Nhạc trong DAW, tắt loopMIDI, đổi default playback sang loa khác,
    mute Chrome trong Volume Mixer, bật Release Driver, đóng DAW;
  - mở app → thấy cảnh báo đúng;
  - bấm Tự sửa → mọi mục ổn, có tiếng nhạc + mic.

## 9. Giai đoạn 2 (ngoài phạm vi G1)

- `elevated.py`: gom các lệnh cần Admin, một lần UAC chạy PowerShell nâng quyền (dựa trên `QLS_SuaLoi.ps1`).
  Dùng cho B3, B5 (HKLM), B6, B10, C1.
- C1: phát hiện thiết bị âm thanh lỗi PnP (Code 10) + đã cài KB5124008 → `pnputil /restart-device`, hướng dẫn gỡ KB.
- B7: phát hiện app chiếm thiết bị (danh sách như ps1:1137) → hướng dẫn.
- B8: so sample rate Windows với cấu hình DAW. C2/C3: đọc cấu hình audio device của SO/Cubase.
- Đo tín hiệu thật: mức loopback thiết bị ảo khi YouTube đang phát, mức mic. Cần nghiên cứu theo
  loại card vì đầu ra ASIO không thu được qua WASAPI.
- Script Cubase điều khiển Monitor Enable của track Nhạc/Mic (MIDI Remote API), nếu cần.
