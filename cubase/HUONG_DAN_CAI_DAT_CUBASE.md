# Quy trình cài đặt Quang Lưu Studio cho máy dùng Cubase

Bản hợp nhất từ ba máy khách đã cài thật (Cubase Pro 15 + Antares Auto-Tune Pro 11, 2026-10-06 → 2026-10-08).
Dành cho kỹ thuật viên (tại chỗ hoặc qua UltraViewer). Tệp này nằm cạnh app: `<thư mục cài>\cubase\`.

## 0. Cần có trước khi bắt đầu

| Thứ | Yêu cầu | Vì sao |
|---|---|---|
| Cubase | 12 trở lên (Elements/Artist/Pro). Đã kiểm: Pro 13, Pro 15 | MIDI Remote API chỉ có từ Cubase 12 |
| Plugin tune trên kênh Mic | Antares Auto-Tune Pro (khách) hoặc Pitch Correct (Cubase sẵn có) | Script nhận ra plugin theo tên và tự chọn chỉ số tham số |
| Bài mẫu `.cpr` | Track 1 = **NHAC**, track 2 = **MIC/GIONG**, plugin tune ở **insert 1** của track 2; các kênh vang đặt tên có chữ *Vang / Delay / Reverb / Echo* (không dấu) | Script gán Nhạc/Mic theo **thứ tự**, nhóm Vang theo **tên** |
| Quyền | Tài khoản Windows của người hát (script chép vào *Documents* của tài khoản đó) | Cubase chỉ quét `Documents\Steinberg\...` của user đang đăng nhập |

## 1. Chạy bộ cài

1. Chạy `Setup_QuangLuuStudio_vX.Y.Z.exe` (bản mới hay nâng cấp đều vậy). Sau khi chép file, bộ cài **tự chạy** `setup_all.bat /auto`
   với quyền của người đang đăng nhập: tạo/kiểm cổng loopMIDI, chép script Cubase (sao lưu bản cũ), không hỏi gì. Toàn bộ màn hình
   ghi ở `%APPDATA%\QuangLuuStudio\logs\setup_all.txt`.
2. Chỉ khi còn việc phải làm bộ cài mới hiện một hộp thoại: thiếu cổng MIDI (máy không có `winget`/mạng → chạy tay `setup_all.bat`
   trong thư mục cài, nó mở trang tải loopMIDI và chờ), chép script lỗi, hoặc **Cubase đang mở → Reload Scripts**. Cài im lặng
   (`/SILENT`) thì không có hộp thoại, xem log.
3. Bộ cài tự ghi `settings.json` lần đầu với **`daw_kind = cubase`** nếu máy có Cubase mà không có Studio One. Máy có cả hai thì vào app đổi tay (mục 4).
4. Ô tích "Chạy lại cài đặt loopMIDI / MIDI có hướng dẫn" ở trang cuối mặc định **không** tích; chỉ dùng khi bước tự động báo thiếu cổng.

## 2. `setup_all.bat` làm gì (chạy lại được bất cứ lúc nào từ thư mục cài; `/auto` = không hỏi, bỏ bước FFmpeg, ghi log)

| Bước | Việc | Kết quả phải thấy |
|---|---|---|
| 1 | Cài loopMIDI, tạo cổng **QuangLuuMIDI** và **QLS_PhanHoi**, đếm lại cổng thật | `[OK]` đủ 2 cổng; loopMIDI tự khởi động cùng Windows |
| 2 | Surface Studio One | `[CANH BAO] Khong tim thay Studio One` là bình thường trên máy Cubase |
| 2b | Chép `QuangLuu_QuangLuuMIDI.js` vào `<Documents>\Steinberg\Cubase\MIDI Remote\Driver Scripts\Local\QuangLuu\QuangLuuMIDI\` | `[OK] Da chep ...` + `[INFO] Phien ban script: YYYY-MM-DD`. Bản cũ trên máy được giữ ở `.js.bak` |
| 3 | FFmpeg | `[OK]` |

Nếu Cubase **đang chạy** lúc chép: `Studio → MIDI Remote Manager → Scripts → Reload Scripts` (hoặc mở lại Cubase). Cubase tự nhận
script khi thấy đủ hai cổng loopMIDI, không phải thêm thiết bị tay.

Mã thoát của `setup_all.bat /auto` (bộ cài đọc để hiện hộp thoại): 0 = xong; cộng dồn 1 = thiếu cổng MIDI, 2 = chép script Cubase lỗi,
4 = Cubase đang chạy. Tệp `.bat` phải giữ xuống dòng **CRLF** (`.gitattributes` đã ép): bản LF có tiếng Việt làm cmd đọc lệch dòng,
báo hàng loạt `'x' is not recognized` (đã gặp 2026-10-08 trên máy dev).

## 3. Thiết lập trong Cubase (mỗi máy làm một lần)

1. **Studio → Studio Setup → Audio System**: **tắt** *Release Driver when Application is in Background*. App ẩn Cubase đi khi hát, bật cờ này là mất tiếng.
2. Mở bài mẫu `.cpr`, kiểm thứ tự track và tên kênh như mục 0. Lưu lại.
3. Kiểm script đã nạp: Lower Zone → **MIDI Remote** phải thấy bề mặt *QuangLuuMIDI*. Muốn xem log: chuột phải thanh công cụ MIDI Remote → bật *Scripting Tools* → *Script Console*, dòng `driver active ... (script YYYY-MM-DD)`.

## 4. Thiết lập trong app

1. **Thiết lập → Phần mềm thu âm (DAW)** = *Cubase*; **bài mẫu** = file `.cpr` ở mục 0. Lưu, mở lại app.
2. **Không cần Cân chỉnh Auto-Tune.** Từ script 2026-10-08, app gửi Scale theo bảng mặc định (Major 43 / Minor 85) và script tự đổi
   sang bảng của plugin đang gắn (Auto-Tune Pro: Major 10 / Minor 18; Pitch Correct: giữ nguyên). Máy nào đã cân chỉnh từ trước
   (10/18) vẫn chạy đúng. Nếu buộc phải ghi tay `%APPDATA%\QuangLuuStudio\calibration_overrides.json` thì **UTF-8 không BOM**,
   app chỉ đọc lúc khởi động.
3. `app_config.json` cạnh exe: giữ CC mặc định (Tone Nhạc 10, Tone Giọng 11, Key 33, Scale 35, Fix Méo 45, Dân Ca 46, Bè 47).
   Một máy khách từng bị đổi `tone_music` thành 55; script hiện nghe cả 10 lẫn 55 nhưng không nên lệ thuộc vào đó.

## 5. Kiểm nghiệm thu (5 phút)

| Thao tác trên app | Phải thấy trên Cubase |
|---|---|
| Dò tone một bài / đổi Key | Auto-Tune: Key đổi theo; Scale = Major/Minor của bài |
| Tone Nhạc −1 / +1 | Key dịch theo **và** SoundShifter (kênh NHAC, insert 1) Semitones = ±1 |
| Tone Giọng ±1 | SoundShifter Semitones cộng dồn với Tone Nhạc (kẹp ±12) |
| Fix Méo bật/tắt | Scale → Chromatic, tắt → về scale bài |
| Dân Ca bật/tắt | Scale → Dorian (Auto-Tune có bộ scale Modern); bản Auto-Tune chỉ có bộ scale cổ điển thì hiện **Minor** (xem mục 6) |
| Bè bật/tắt | Auto-Tune Harmony Player bật/tắt (tham số *HP Bypass*) |
| Fader / tắt tiếng Vang | Cả nhóm kênh tên có *Vang/Delay/Reverb* đi theo |
| Thoát app | Cubase đóng, **không** lưu đè bài mẫu |

Kiểm nhanh không cần nhìn GUI: Script Console phải hiện `disp[2] <Key>`, `disp[162]`/`disp[1] Major|Minor`, `nhac disp[4] ±n`.

## 6. Những gì khác nhau giữa các máy đã gặp

| Máy | Khác biệt | Cách xử lý đã làm |
|---|---|---|
| DESKTOP-U46KFB8 (máy 1) | `app_config.json` bị đổi `tone_music = 55` | Script nghe cả CC 10 và 55 |
| DESKTOP-826077C (máy 2) | Có yêu cầu Bè → Harmony Player; Fix Méo/Dân Ca | Thêm vào hồ sơ Auto-Tune trong script (tham số 155, Scale 2/45) |
| DESKTOP-M21N7VP (máy 3) | Chưa có tệp cân chỉnh → Scale sai; Auto-Tune Pro **11.0.0 (650)** GUI chỉ có 29 scale cổ điển (tham số 1), không có Dorian dù Modern hay Classic | Script ghi cả tham số 1 lẫn 162; Dân Ca lùi về Minor; muốn Dorian thật phải cập nhật Auto-Tune Pro |

Bẫy chung: `Documents` có thể nằm trong OneDrive (`setup_all.bat` đã hỏi Windows đường dẫn thật); Cubase ẩn cửa sổ nổi khi mất
focus; máy khách thường có người đang dùng — qua UltraViewer phải kiểm màn hình yên trước khi thao tác (xem `docs/QUY_TRINH_UV_CUBASE.md`).

## 7. Khi có lỗi

1. Chạy `tools/chan_doan/QLS_ChanDoan.ps1` (kỹ thuật viên): báo cổng loopMIDI, script đúng bản/phiên bản, cờ Release Driver,
   tệp cân chỉnh hỏng/BOM, DAW đã chọn khớp đuôi bài mẫu.
2. Log app: `%APPDATA%\QuangLuuStudio\logs\app.log` — tìm `[MIDI] Key=... Scale=... (cc=35, val=...)`, `[MODE] Dân Ca`, `[FIX MEO]`.
3. Log Cubase: Script Console (mục 3.3). Không thấy `driver active` → thiếu cổng hoặc script chưa nạp.
4. Cập nhật script lẻ (không cài lại): chép `cubase\QuangLuu_QuangLuuMIDI.js` mới vào thư mục mục 2b, Reload Scripts.
   Qua UltraViewer dùng `tools/ultraviewer/cb.sh deploy` theo `docs/QUY_TRINH_UV_CUBASE.md`.
