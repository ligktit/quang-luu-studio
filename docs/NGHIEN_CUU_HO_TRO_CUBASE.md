# Nghiên cứu: dùng app với Studio One **và** Cubase

> Trạng thái: **nghiên cứu, chưa sửa code.** Soạn 2026-10-04.
> Phần mã nguồn khảo sát trực tiếp trên repo; phần Cubase lấy từ tài liệu Steinberg
> và diễn đàn chính thức (nguồn ở cuối). Mọi mục đánh dấu **[cần đo máy thật]** chưa
> kiểm chứng vì máy dev không có Cubase (và cũng không có Studio One).

## 0. Hai cách hiểu "đồng thời" — và câu trả lời ngắn

| Cách hiểu | Kết luận |
|---|---|
| **A. App hỗ trợ cả hai DAW**, mỗi máy khách chọn một (Studio One *hoặc* Cubase) | **Khả thi.** Cubase có đủ cơ chế tương đương Control Surface của Studio One (MIDI Remote API, Cubase 12+). Việc chính là tách phần "biết Studio One" trong code ra thành một lớp DAW adapter, viết thêm adapter Cubase, và đo lại bảng giá trị CC. |
| **B. Studio One và Cubase chạy cùng lúc trên một máy**, app điều khiển cả hai | **Không nên làm.** ASIO chỉ cho một ứng dụng giữ driver; tuỳ chọn "Release Driver when Application is in Background" của cả hai DAW đều được cộng đồng ghi nhận là không tin cậy, và app lại **ẩn cửa sổ DAW** (kiosk) → DAW luôn ở "background" → nếu bật tuỳ chọn này DAW sẽ mất tiếng. MIDI thì không vướng (loopMIDI cho 8 app cùng mở một cổng) nhưng hai DAW sẽ cùng nghe một CC, phải tách cổng. Kiến trúc hiện tại cũng chỉ có một `studio_one_path`. |

Phần còn lại của tài liệu đi theo cách hiểu **A**. Mục 6 ghi riêng những gì cần nếu vẫn muốn B.

## 1. App hiện bám vào Studio One ở đâu

Ba đường giao tiếp, mức độ gắn chặt khác nhau:

| Đường | Chỗ trong code | Gắn với Studio One tới mức nào |
|---|---|---|
| **MIDI CC một chiều** qua loopMIDI `QuangLuuMIDI` → Control Surface | `core/midi.py`, `core/engine/_midi.py`, bảng `midi_cc` trong `core/config.py:171-204`, `studio_one/QuangLuuMIDI.surface.xml` | Lớp gửi CC **trung lập**. Chỉ file surface, bộ cài và **giá trị cân chỉnh** là riêng Studio One. |
| **Process / cửa sổ** (psutil, win32, UIAutomation, pyautogui) | `core/so_windows.py` (`PROCESS_KEYWORDS=("studio one",)`, `MAIN_TITLE_KEYWORD`), `core/engine/_lifecycle.py` (`STUDIO_ONE_EXTENSIONS`, `_force_kill_studio_one` với 5 tên exe cứng, hộp thoại "Don't Save") | **Gắn chặt.** Toàn bộ nhận diện bằng chuỗi "Studio One". |
| **Bản mẫu `.song`** chốt rồi chép đè mỗi lần mở (chế độ khách) | `core/so_template.py` (`is_song_file` chỉ nhận `.song`), `frontend_qt.py:1203-1253` | Logic chung, chỉ đuôi file là riêng. |

Ngoài ra:
- Âm thanh: app **không dùng ASIO**, chỉ nghe **WASAPI loopback** của loa mặc định (`core/tone_detector.py`, `_autokey.py`, `recorder_worker.py`, visualizer). DAW nào cũng được, miễn tiếng DAW ra được loa Windows (hoặc qua ASIOVADPRO/VB-Cable như hướng dẫn hiện có ở `settings_dialog.py:1120-1160`).
- Cổng phản hồi `QLS_PhanHoi` và `readyPing` (CC 49) mới có trong script cài + surface, **Python chưa gửi/nghe** (xem `docs/PLAN_SO_READY_HANDSHAKE.md`). `MidiHandler.start_listening()` không nơi nào gọi.
- Chuỗi "Studio One" lộ ra UI/docs: ~115 lần trong `frontend_qt.py`, 30 trong `settings_dialog.py`, nút mắt ở `header.py`, `shutdown_dialog.py`, `docs/manual/index.html`.
- Repo không có một dòng nào nhắc "Cubase" / "Steinberg".

## 2. Ánh xạ từng điểm sang Cubase

### 2.1 Khởi chạy và nạp bài

| Studio One (hiện tại) | Cubase |
|---|---|
| `os.startfile("…/bai.song")` | `os.startfile("…/bai.cpr")`. Windows có association `HKCR\Cubase.Project\shell\open\command` = `"…\CubaseN.exe" "%1"`. Mở bằng file thì Cubase vào thẳng project, không qua Hub **[cần đo máy thật — đặc biệt Cubase 13+ không còn tắt được Hub]**. |
| Mở `.exe` không tham số | Tránh: Cubase mở `.exe` trống sẽ đứng ở **Steinberg Hub**. Luôn cấu hình đường dẫn là `.cpr`. |
| Chờ cửa sổ có "studio one" trong tiêu đề | Tiêu đề project Cubase dạng `Cubase Pro Project - <tên>.cpr` (có cả chữ phiên bản tạo project). Từ khoá `"cubase"` là đủ, nhưng Hub và **Steinberg Activation Manager** cũng chứa chữ Cubase/Steinberg → cần lọc thêm theo class hoặc theo chữ "Project". |

### 2.2 Phát hiện process, ẩn/hiện, đóng không lưu

| Mục | Studio One | Cubase |
|---|---|---|
| Tên process | `Studio One.exe`, `Studio One 7.exe` … | `Cubase14.exe`, `Cubase13.exe`, `Cubase LE AI Elements 14.exe`, `Cubase Artist 14.exe` … Dùng so khớp chuỗi con `"cubase"` như hiện nay là ổn. |
| Ẩn cửa sổ (`SW_HIDE` theo PID) | Đã làm, kể cả cửa sổ plugin mọc muộn (`hide_when_ready` bám 60 s) | Cùng cơ chế vì theo PID. Lưu ý Cubase 14 bật/tắt "menu bar và title bar riêng" theo OS → có thể có nhiều top-level window hơn. |
| Hộp thoại "Save changes?" khi `WM_CLOSE` | Bấm `IDNO` trên class `#32770`, nhãn "Don't Save", fallback UIAutomation | Cubase vẽ dialog bằng toolkit riêng, **không chắc là `#32770`** → nhiều khả năng phải đi đường UIAutomation ngay (code đã có sẵn nhánh này). Nhãn nút là **"Don't Save"** (EN). **[cần đo máy thật]** |
| `taskkill /F /IM` | 5 tên cứng | Thay bằng duyệt psutil theo từ khoá, bỏ danh sách tên cứng. |
| Ctrl+S trước khi đóng | `pyautogui.hotkey` | Cubase cũng Ctrl+S; nhưng chế độ khách phục hồi bản mẫu nên đóng **không lưu** vẫn là mặc định. |

### 2.3 Điều khiển qua MIDI — ba lựa chọn trong Cubase

Studio One: file `surface.xml` cài vào `%APPDATA%\PreSonus\Studio One N\User Devices\`, mỗi control một CC, gán vào tham số **theo bài** bằng Control Link. Cubase có ba cơ chế tương đương, không cái nào giống hoàn toàn:

| | **MIDI Remote API** (script JS) | **Generic Remote (Legacy)** (XML) | **Track Quick Controls** |
|---|---|---|---|
| Có từ | Cubase 12 (2022), **mọi bản** Elements/Artist/Pro | Rất lâu; Cubase 12–15 còn, ghi "will be discontinued" | Rất lâu |
| Vị trí cài | `%USERPROFILE%\Documents\Steinberg\Cubase\MIDI Remote\Driver Scripts\Local\<Vendor>\<Device>\<Vendor>_<Device>.js` (thư mục `Public` bị ghi đè khi Cubase khởi động) | Studio Setup → Add Device → Generic Remote → Import XML (lưu trong prefs người dùng) | Studio Setup → Track Quick Controls (8 CC toàn cục) |
| Tự nhận cổng | `expectInputNameEquals("QuangLuuMIDI")`, `expectOutputNameEquals("QLS_PhanHoi")` → Cubase tự kích hoạt khi thấy cổng | Chọn cổng tay | Chọn cổng tay |
| Gán vào insert plugin | `makeInsertEffectViewer(...).accessSlotAtIndex(n)` + `makeDirectAccess` → đặt theo **tag** tham số (tag ổn định theo plugin) | Chọn trong list "VST Mixer / <kênh> / Ins. N / <param>" | Gán trong Inspector từng track; **chỉ track đang chọn (hoặc đã lock) phản hồi** |
| Gán vào mute/fader | `makeMixerBankZone().makeMixerBankChannel()` → `mValue.mMute / mVolume`; **theo chỉ số kênh**, không theo tên | Theo kênh trong mixer (cũng theo thứ tự) | Theo track đang chọn |
| Phản hồi ngược (cho `readyPing`) | **Có**: `sendMidi` trong `mOnProcessValueChange`; thêm `mOnTitleChange` báo **tên kênh** → biết bài đã nạp. Gotcha đã ghi nhận: callback chỉ chạy khi có một surface element đang bind (dùng nút 0×0 ẩn). | Cờ "Transmit", nhưng có báo cáo không gửi lại cho đúng controller | Không |
| Transport / lệnh | `makeCommandBinding(value, "Transport", "Start")`, `mHostAccess.mTransport` | Có | Không |
| Rủi ro | API mới, đã ổn 3 phiên bản; cần ports có **trước** khi Cubase chạy (loopMIDI đã autostart) | Steinberg ghi rõ sẽ bỏ; Elements xưa không có **[cần kiểm]** | Chỉ 8 CC, theo track chọn → **không đủ** cho ~30 CC trên nhiều track |

**Khuyến nghị:** dùng **MIDI Remote API** làm đường chính (một file `.js` đóng gói trong bộ cài, giống `surface.xml` hiện nay), giữ **Generic Remote XML** làm đường dự phòng cho Cubase ≤ 11 nếu còn khách dùng. Loại Track Quick Controls.

Điểm khác biệt quan trọng so với Studio One: Control Link của Studio One gán **theo bài** (trong `.song`), còn MIDI Remote script gán **theo chỉ số kênh / chỉ số slot insert**, độc lập với project. Hệ quả: bản mẫu `.cpr` phải **cố định thứ tự track và slot insert** (ví dụ: kênh 0 = Nhạc, 1 = Mic, 2 = Vang, 3 = Bè, 4 = PING; Auto-Tune luôn ở insert slot 1 của kênh Mic). Script có thể tự kiểm bằng `mOnTitleChange` (tên kênh phải là "Mic") rồi bắn CC lỗi về `QLS_PhanHoi` nếu sai — app hiển thị cảnh báo. Đây lại là một điểm **tốt hơn** Studio One: handshake ready-ping có cơ chế chính thức, không cần mẹo track PING + Pan.

### 2.4 Bảng giá trị CC phải đo lại

Mọi hằng số dưới đây là **cân chỉnh theo plugin và fader của Studio One**, không mang nguyên sang được:

| Hằng số | Chỗ | Vì sao phải đo lại trên Cubase |
|---|---|---|
| `key_midi_map` (C=0, C#=11, … B=127), `scale_type` Major=13/Minor=18 | `core/config.py` | Nếu khách dùng **cùng plugin Auto-Tune**, giá trị process 0–1 → list param là của plugin nên có thể giữ; nhưng Control Link của Studio One và `setParameterProcessValue` của Cubase có thể làm tròn khác. |
| Fader 0 dB = 76 | `ui/panels/mixer.py:67-75` | Đường cong fader Cubase khác Studio One. |
| `core/so_values.py` (switch/percent/range/list ↔ CC) | | Giả định "tuyến tính" đúng với MIDI Remote (`setProcessValue` nhận 0–1) nhưng điểm ngắt list khác. |
| `tone_music`/`tone_voice` ±12 st → 0–127 | `frontend_qt.py:865-893` | Phụ thuộc plugin pitch-shift được dùng trong Cubase. |

→ Cần **hồ sơ cân chỉnh theo DAW** (`calibration` tách theo `daw_kind`), không ghi đè bộ hiện tại.

### 2.5 Âm thanh

- App nghe loopback loa Windows, DAW xuất ASIO → mô hình giữ nguyên. Hướng dẫn ASIOVADPRO / VB-Cable hiện có áp dụng y nguyên cho Cubase.
- **Phải tắt** `Studio > Studio Setup > Audio System > Release Driver when Application is in Background` trên Cubase của khách (và `Release audio device in background` trên Studio One). Lý do: app ẩn cửa sổ DAW → DAW luôn là background → bật tuỳ chọn này là mất tiếng. Nên thêm vào `tools/chan_doan` (Cubase lưu prefs ở `%APPDATA%\Steinberg\Cubase N_64\` dạng XML).

## 3. Thiết kế đề xuất: lớp DAW adapter

Mục tiêu bước 1 là **không đổi hành vi Studio One**, chỉ dời code "biết Studio One" vào một chỗ.

```
core/daw/
  base.py        DawAdapter: kind, display_name, process_keywords, main_title_keyword,
                 project_extensions, remote_files(), install_remote(), template_ext,
                 close_dialog_strategy (dont_save labels / class), launch(path)
  studio_one.py  giữ y nguyên các hằng từ so_windows/_lifecycle/so_template
  cubase.py      "cubase", (".cpr",), MIDI Remote script, UIAutomation-first dialog
  __init__.py    get_adapter(settings["daw_kind"])
```

Thay đổi kéo theo:

| Việc | File | Ghi chú |
|---|---|---|
| `so_windows` nhận keywords từ adapter thay vì hằng module | `core/so_windows.py:19-20` | Tests `test_so_ready_watcher.py` giữ được. |
| `STUDIO_ONE_EXTENSIONS`, taskkill list, logic dialog → adapter | `core/engine/_lifecycle.py` | Bỏ hẳn tên exe cứng. |
| `is_song_file` → `adapter.is_project_file` | `core/so_template.py` | Cùng thư mục `so_template`, đổi tên sau. |
| Settings: thêm `daw_kind` (`studio_one` mặc định), giữ `studio_one_path` đọc được cũ, ghi mới `daw_project_path` | `core/config.py`, `settings_dialog.py`, wizard `frontend_qt.py:4595-4681` | Migration một chiều. |
| Chuỗi UI: "Studio One" → `adapter.display_name` | ~200 chỗ, chủ yếu `frontend_qt.py`, `settings_dialog.py`, `shutdown_dialog.py`, `header.py` | Làm theo đợt, có `docs/UI_TEXT_AUDIT.md` sẵn. |
| Bộ cài: `setup_all.bat` dò `%APPDATA%\Steinberg\Cubase*` và `Documents\Steinberg\Cubase\MIDI Remote\Driver Scripts\Local\QuangLuu\QuangLuuMIDI\QuangLuu_QuangLuuMIDI.js` | `QuangLuuStudio_Setup.iss`, `setup_all.bat`, thư mục mới `cubase/` | `.spec` thêm `cubase/` như `studio_one/`. |
| Chẩn đoán: kiểm script đã cài, hash, số CC khớp app, cờ Release Driver | `tools/chan_doan/QLS_ChanDoan.ps1` | Song song với phần PreSonus hiện có. |
| Test: `tests/test_cubase_script.py` đọc file `.js`, so danh sách CC với `midi_cc` | mới | Tương tự `tests/test_surface_xml.py`. |

Những gì **dùng lại nguyên**: `core/midi.py`, `_midi.py`, `_sync_midi_states`, toàn bộ dò tone / AutoKey / thu âm / visualizer, kiosk `HideGuard`, `ReadyWatcher` (chỉ đổi từ khoá).

## 4. Lộ trình

| Giai đoạn | Nội dung | Kết quả cần có |
|---|---|---|
| **0 — Thăm dò máy thật** | Script `tools/tham_do_cubase/ThamDoCubase.ps1` (mẫu theo `tham_do_studio_one`): liệt kê process/tiêu đề/class cửa sổ Cubase; đóng có dialog để xem class + nhãn nút; mở `.cpr` từ dòng lệnh xem Hub có hiện; thử script JS tối thiểu nhận `QuangLuuMIDI`, in tag tham số của Auto-Tune, đo fader 0 dB. | Bảng trả lời cho mọi mục **[cần đo máy thật]**; phiên bản Cubase khách đang dùng. |
| **1 — Refactor adapter** | Mục 3, Studio One không đổi hành vi. | Suite tests xanh; Studio One chạy như 1.7.9. |
| **2 — Adapter Cubase + script MIDI Remote** | `cubase/QuangLuu_QuangLuuMIDI.js`, bản mẫu `.cpr` chuẩn thứ tự kênh, bộ cài, chẩn đoán. | Cài trên máy có Cubase, mọi CC trong `midi_cc` tác dụng đúng đích. |
| **3 — Cân chỉnh và handshake** | Hồ sơ `key_midi_map`/fader/tone cho Cubase; dùng `mOnTitleChange` + `sendMidi` làm ready-ping (gộp với `PLAN_SO_READY_HANDSHAKE`). | Studio One và Cubase cùng một UI, lệch trạng thái = 0 sau khi nạp bài. |
| **4 — UI/docs** | Chọn DAW trong wizard, chuỗi hiển thị theo adapter, `docs/manual`, release notes. | Bản phát hành có hai DAW. |

Giai đoạn 0 chặn các giai đoạn sau; giai đoạn 1 có thể làm ngay trên máy dev vì không cần DAW.

## 5. Câu hỏi mở trước khi bắt tay

1. Khách thực tế dùng Cubase **phiên bản/bản nào** (Elements/Artist/Pro, 12–15)? Quyết định có cần Generic Remote dự phòng không.
2. Plugin trên Cubase có **giống** plugin trên Studio One (cùng Auto-Tune, cùng pitch-shift) không? Nếu khác, bảng tone/key phải thiết kế lại chứ không chỉ đo lại.
3. Có chấp nhận ràng buộc **thứ tự track/insert cố định** trong bản mẫu `.cpr` không (bắt buộc với MIDI Remote)?
4. Cubase có bật tiếng ra loa Windows để loopback nghe được không, hay phải thêm ASIOVADPRO như một số máy Studio One hiện nay?

## 6. Nếu vẫn muốn hai DAW chạy cùng lúc (cách hiểu B)

- Cần **hai thiết bị âm thanh** hoặc driver **multi-client** (RME, Focusrite, một số Yamaha/Steinberg UR). Không dựa vào Release Driver.
- Tách cổng MIDI: `QuangLuuMIDI_SO` và `QuangLuuMIDI_CB`, app gửi theo DAW đang "active"; loopMIDI chịu được (8 client/cổng).
- `so_windows` phải quản lý hai nhóm PID, hai `ReadyWatcher`, hai bản mẫu.
- Phần cân chỉnh mục 2.4 nhân đôi. Chi phí lớn, lợi ích chưa rõ → đề nghị không làm ở đợt này.

## 7. Tiến độ dựng máy thử (máy dev METTITECH-DEV, 2026-10-04)

Quyết định: **tự cài Cubase trên máy dev** và tự đo thay vì chờ máy khách.

| Việc | Trạng thái |
|---|---|
| loopMIDI + hai cổng `QuangLuuMIDI`, `QLS_PhanHoi` | **Xong** (chạy `setup_midi_ports.ps1`, loopMIDI 1.0.16, tự khởi động cùng Windows) |
| Steinberg Download Assistant 1.40.1 | **Đã cài** (`C:\Program Files (x86)\Steinberg\Download Assistant`), chữ ký Steinberg hợp lệ |
| Tài khoản MySteinberg + trial Cubase Pro 60 ngày | **Chờ người làm** (đăng nhập web, bấm "Try now" *sau khi* đăng nhập, xác nhận email newsletter, tải trong Download Assistant, Activate trong Steinberg Activation Manager) |
| Script MIDI Remote thăm dò `cubase/QuangLuu_QuangLuuMIDI.js` | **Xong**, đã chép vào `Documents\Steinberg\Cubase\MIDI Remote\Driver Scripts\Local\QuangLuu\QuangLuuMIDI\`; Cubase sẽ tự nhận ở lần mở đầu |
| Công cụ `tools/tham_do_cubase/` (`ThamDoCubase.ps1/.bat`, `HUONG_DAN.md`) | **Xong**, đã chạy thử hai chế độ trên máy này (chưa có Cubase nên chỉ xác nhận không lỗi) |
| Test `tests/test_cubase_script.py` giữ JS khớp `midi_cc` | **Xong** |
| Bài mẫu `.cpr` thứ tự track cố định (Nhạc/Mic/Vang/Bè) | Chờ Cubase |
| Đo 8 câu hỏi trong `tools/tham_do_cubase/HUONG_DAN.md` | Chờ Cubase |

Script thăm dò đồng thời là **bản nháp của adapter thật**: đã có echo ping (CC 49), gán mute/fader
theo chỉ số kênh, báo tên kênh qua CC 60–67 (tín hiệu sẵn sàng), liệt kê tham số plugin ở insert slot
kênh Mic và gán `key_root`/`scale_type` theo tên tham số. Giai đoạn 2 chỉ cần bỏ phần log và
thêm các CC còn lại.

### 7.1 Kết quả đo đợt 1 (Cubase Pro 13.0.10 trial, project trống "Untitled1" đang mở)

| Câu hỏi | Kết quả |
|---|---|
| Cài ở đâu, exe | `C:\Program Files\Steinberg\Cubase 13\Cubase13.exe`; process `Cubase13` |
| Liên kết `.cpr` | `HKCR\.cpr` → `Cubase.Project` → `"…\Cubase13.exe" "%1"` → `os.startfile` dùng được |
| Prefs | `%APPDATA%\Steinberg\Cubase 13_64\`. `Defaults.xml` **chưa có** khi Cubase còn chạy (ghi lúc thoát) → đo cờ Release Driver sau khi đóng |
| Cửa sổ project | Tiêu đề `Cubase Pro Project - <tên>`; class `SteinbergWindowClass` + **2 ký tự Unicode ngẫu nhiên** (U+BEC0 U+47CE lần này) → so khớp **tiền tố**, không so bằng |
| Cửa sổ ứng dụng | class `SmtgMain Cubase13`, tiêu đề `Cubase Pro`, luôn hiện → `main_windows()` phải ưu tiên cửa sổ có chữ "Project" |
| Script MIDI Remote | Cubase **tự nhận** ở lần mở đầu (đã sinh `User Settings\QuangLuu_QuangLuuMIDI_…_globalmappings.json`), **không cần** thao tác trong MIDI Remote Manager |
| Hỏi–đáp ping CC 49 | **Trả lời 39/39**, trễ trung bình 25 ms, lớn nhất 39 ms. Khác hẳn Studio One (chưa chắc có trả lời) |
| Tên kênh (CC 60–67) | Chưa có vì project chưa có track → đo tiếp với bài mẫu |

### 7.2 Kết quả đo đợt 2 (bài mẫu `D:\QLS\mau.cpr`: 4 track Nhac/Mic/Vang/Be, Pitch Correct ở insert 1 của Mic)

Bài mẫu được tạo bằng điều khiển chuột/phím từ xa (pyautogui), không cần thao tác tay.

| Câu hỏi | Kết quả |
|---|---|
| **API MIDI Remote của Cubase 13.0.10** | File `.api/v1/midiremote_api_v1.d.ts` **không có** `makeDirectAccess`, `accessSlotAtIndex`, `HostValue.setProcessValue`. Chỉ có `makeInsertEffectViewer().excludeEmptySlots()` + `mParameterBankZone.makeParameterValue()` (tham số theo thứ tự plugin) và `makeValueBinding`. → Mục 2.3 phải sửa: **gán theo chỉ số tham số**, không theo tag. DirectAccess là API của bản mới hơn, không dựa vào. |
| Gán mute/fader theo chỉ số kênh | Đúng: CC 51 mute đúng track Mic (kênh 1), CC 20 đổi fader Nhac (kênh 0). Bank zone `excludeInputChannels().excludeOutputChannels()` đếm từ track audio đầu tiên. |
| Tên kênh (CC 60–67) | Về đủ 4 kênh ngay khi script nạp (độ dài tên 4/3/4/2), kênh 4–7 báo 0. Dùng làm tín hiệu "bài đã nạp tới mixer". |
| **Fader 0 dB** | process `0.7891` → **CC 100** hiển thị `0.00 dB`; CC 99 = −0.19 dB. (Studio One: 76.) |
| **Tham số Pitch Correct** (thứ tự = chỉ số) | 0 Transpose, 1 Formant, 2 Formant Shift, 3 PitchCorrect (Off/2..100), 4 PitchDetect, 5 MasterTuneOut, **6 Key**, **7 Scale**, 8 PitchShiftTotal, 9 Algorithm, 10 Midi Mode, 11 Bypass, 12–23 ScaleNote0..11, 24 Pitch, 25–31 OutVu. |
| **Bảng Key** (CC 86 → hiển thị) | C 0–5, C# 6–17, D 18–28, D# 29–40, E 41–51, F 52–63, F# 64–75, G 76–86, G# 87–98, A 99–109, A# 110–121, B 122–127. **Trùng `key_midi_map` hiện tại của app** (C=0, C#=11, D=23 … B=127) vì cùng là list 12 bước tuyến tính. |
| **Bảng Scale** (CC 87) | Chromatic 0–21, **Major 22–63**, Minor 64–105, Custom 106–127 → tâm Major=43, Minor=85. Khác `scale_values` (13/18) của Auto-Tune trong Studio One → phải theo DAW/plugin. |
| Phản hồi SysEx | `sendMidi` gửi được SysEx ASCII; app đọc tên tham số/giá trị hiển thị mà không cần Script Console. Công cụ: `tools/tham_do_cubase/nghe_phan_hoi.py`, `quet_tham_so.py`. |
| **Hộp thoại Save khi đóng** | Cửa sổ nhỏ 295×126, **cùng class** `SteinbergWindowClass…`, tiêu đề chỉ `Cubase Pro`, không phải `#32770`. UI Automation thấy `ButtonControl` tên `Save` / `Don't Save` / `Cancel` (class `Button`, lồng trong `SteinbergPluginWrapper`). → Adapter dùng nhánh UIA sẵn có của `so_windows`, so khớp tên nút "Don't Save". |
| **Cờ Release Driver** | `%APPDATA%\Steinberg\Cubase 13_64\Defaults.xml`: `<int name="ReleaseHardware" value="0"/>` (0 = tắt, mặc định). File chỉ được ghi khi Cubase thoát. Chẩn đoán đọc khoá này. |
| Script Console | Chuột phải thanh công cụ tab MIDI Remote → bật *Scripting Tools* → nút thứ 2. Danh sách log không cuộn được bằng chuột/phím trên máy này. |
| Lưu ý thao tác | `Reload Scripts` nạp lại **mọi** script (cả Public) nên log lẫn nhiều dòng `loading script`. Thao tác chuột từ xa bị hụt nếu người dùng đang dùng máy (một lần click rơi vào cửa sổ khác). |

### 7.3 Kịch bản A: mở Cubase từ file `.cpr` khi đang tắt (Cubase 13.0.10, máy dev)

| Mốc | Thời điểm (từ lúc chạy thăm dò) |
|---|---|
| Lệnh `Start-Process D:\QLS\mau.cpr` | ~0 s |
| Process `Cubase13.exe` xuất hiện | 4.3 s |
| Cửa sổ đầu tiên: **`Checking Licenses...`** (cùng class `SteinbergWindowClass…`) | 4.8 s |
| Cửa sổ project `Cubase Pro Project - mau` | 7.9 s |
| Script báo **tên kênh** (CC 60–63) + plugin identity (CC 70) + page/driver active | 8.2–8.3 s (**+0.3 s** sau cửa sổ project) |
| Ping CC 49 được trả lời lần đầu | 9.3 s (+1.3 s), sau đó 64/64, trễ 27 ms |

Kết luận:
- **Không có Steinberg Hub** khi mở bằng file `.cpr` (kể cả Cubase 13 không tắt được Hub). App cứ `os.startfile(.cpr)`.
- Cửa sổ `Checking Licenses...` hiện trước cửa sổ project ~3 s → `main_windows()` phải lọc theo chữ `Project`, không lấy cửa sổ đầu tiên của process.
- Mốc "sẵn sàng" đáng tin: tên kênh/ping về chỉ 0.3–1.3 s sau cửa sổ project trên máy nhanh. Trên máy chậm, dùng chính tín hiệu này thay cho hẹn giờ +3/10/25/50 s.
- `mOnChangePluginIdentity` **có** chạy khi nạp bài thật (không chạy khi chỉ Reload Scripts).

## 8. Trạng thái triển khai (nhánh cubase-adapter, 2026-10-04)

| Task | Đã làm | File chính | Commit |
|---|---|---|---|
| 1 | Gói hồ sơ DAW (Studio One / Cubase), chọn theo `settings["daw_kind"]` | `core/daw/__init__.py`, `core/daw/profiles.py` | f71d09b |
| 2 | `so_windows`: từ khoá process/tiêu đề cửa sổ lấy theo hồ sơ DAW | `core/so_windows.py` | 3257767 |
| 3 | `_lifecycle`: mở/đóng/tắt cứng theo hồ sơ DAW, bỏ danh sách exe cứng | `core/engine/_lifecycle.py` | fc56742 |
| 4 | `so_template`: bản mẫu theo đuôi file của DAW (`.song` / `.cpr`), metadata tách theo DAW | `core/so_template.py` | e0ce091, 087a558 |
| 5 | Mixer: điểm 0 dB của fader theo DAW (Cubase = CC 100) | `ui/panels/mixer.py` | de8f08b |
| 6 | `AppConfig`: bảng scale theo DAW đang chọn, override người dùng vẫn thắng | `core/config.py` | df9daff |
| 7 | Combo "Phần mềm thu âm (DAW)" ở Cài đặt và wizard lần đầu, nhãn theo DAW; đổi DAW làm mới `SCALE_VALUES` và nhắc mở lại app | `ui/dialogs/settings_dialog.py`, `frontend_qt.py`, `ui/panels/header.py` | 52197c2, 625b22f |
| 8 | Script MIDI Remote: CC 33/35/40 → Key/Scale/PitchCorrect của Pitch Correct, CC 80+i → tham số i, SysEx chẩn đoán | `cubase/QuangLuu_QuangLuuMIDI.js`, `tests/test_cubase_script.py` | b51732b |
| 9 | Bộ cài: `setup_all.bat` bước 2b chép script; `.iss`/`.spec` đóng gói `cubase\`; chẩn đoán kiểm hash script và `ReleaseHardware` trong `Defaults.xml` | `setup_all.bat`, `QuangLuuStudio_Setup.iss`, `QuangLuuStudio.spec`, `tools/chan_doan/QLS_ChanDoan.ps1` | 4a3c700 |
| 10 | Cô lập hồ sơ DAW trong test; tài liệu (mục này, `docs/KIOSK_MODE_GUIDE.md`, `docs/manual/index.html`) | `tests/conftest.py`, docs | a234f00, commit docs |

Kế hoạch: [`docs/superpowers/plans/2026-10-04-ho-tro-cubase.md`](superpowers/plans/2026-10-04-ho-tro-cubase.md) (Task 0–10).

### Cách dùng với Cubase

1. Vào **Cài đặt → Phần mềm thu âm (DAW) → Cubase**.
2. Đường dẫn bản mẫu trỏ tới file `.cpr` của bài mẫu: thứ tự track **Nhac / Mic / Vang / Be**, plugin pitch (Pitch Correct) đặt ở **insert đầu tiên của kênh Mic**.
3. Chạy `setup_all.bat` để chép script MIDI Remote vào `Documents\Steinberg\Cubase\MIDI Remote\Driver Scripts\Local\QuangLuu\QuangLuuMIDI\`.
4. Trong Cubase, **tắt** *Release Driver when Application is in Background* (Studio → Studio Setup → Audio System).
5. Bản mẫu chốt là `template.cpr`.
6. Sau khi đổi DAW, nên **mở lại app** để mọi nhãn cập nhật theo DAW mới.

Test: `tests/conftest.py` bind hồ sơ Studio One rỗng trước mỗi test để không đọc `settings.json` thật.

Chạy thử đầu-cuối trên máy dev: **chưa thực hiện** (sẽ cập nhật).

### Ngoài phạm vi

- Override cân chỉnh theo DAW (hiện override người dùng dùng chung cho mọi DAW).
- Thư mục Documents khi có OneDrive redirect: `setup_all.bat` dùng `%USERPROFILE%\Documents`, chẩn đoán dùng `GetFolderPath(MyDocuments)` — cần thống nhất.

## Nguồn

- Steinberg, *Using Several Audio Applications Simultaneously* (Release Driver when Application is in Background): https://archive.steinberg.help/cubase_pro/v10.5/en/cubase_nuendo/topics/setting_up/setting_up_audio_several_audio_applications_simultaneously_using_t.html
- Steinberg forum, Release Driver không tin cậy: https://forums.steinberg.net/t/release-driver-when-application-is-in-background-does-not-work-reliably-an-idea-for-a-solution/1039982
- PreSonus, Release audio device in background: https://answers.presonus.com/20374/studio-one-does-not-release-audio-in-background
- MIDI Remote API docs: https://steinbergmedia.github.io/midiremote_api_doc/ ; API reference: https://steinbergmedia.github.io/midiremote_api_doc/codedoc_api_reference/
- Vị trí script MIDI Remote: https://github.com/steinbergmedia/midiremote-userscripts
- Bind kênh cố định theo chỉ số: https://forums.steinberg.net/t/midi-remote-api-bind-controls-to-fixed-channels/811406
- Direct access tham số insert: https://forums.steinberg.net/t/midi-remote-direct-access-to-insert-parameters/1031922
- Feedback qua `sendMidi` / `mOnTitleChange`, gotcha nút ẩn: https://dredyson.com/how-i-built-a-midi-remote-api-feedback-loop-for-real-time-track-selection-in-cubase-a-quant-developers-complete-step-by-step-guide-to-bridging-external-applications-with-javascript-virtual-midi-p/
- Command bindings: https://steinbergmedia.github.io/midiremote_api_doc/examples/commandbindings/
- Generic Remote (Legacy), Cubase 14: https://forums.steinberg.net/t/cmc-controllers-and-cubase-14-plus-midi-remote/948891 ; https://archive.steinberg.help/cubase_artist/v12/en/cubase_nuendo/topics/remote_control/remote_control_generic_remote_r.html
- MIDI Remote ở mọi bản Cubase 12: https://www.soundonsound.com/techniques/using-midi-remote-cubase-12
- Track Quick Controls: https://audioswiftapp.com/quick-controls-in-cubase/
- Hub không tắt được từ Cubase 13: https://forums.steinberg.net/t/regression-allow-disabling-of-hub-in-cubase-13/877837
- Association `.cpr`: https://forums.steinberg.net/t/project-file-type-cpr-not-associating-with-cubase-pro-14-windows-10/991234
- Tiêu đề cửa sổ Cubase 14: https://forums.steinberg.net/t/project-title-bar-shows-version-14/1028771
- loopMIDI multi-client (8 app/cổng): https://www.tobias-erichsen.de/software.html
