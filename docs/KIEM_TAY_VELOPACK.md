# Kiểm tay trước khi phát hành 1.9.0 (Velopack)

Ghi kết quả (Đạt/Không + ghi chú) vào từng dòng. Mọi mục phải Đạt trước khi bật rollout.

## A. Bản onedir trên máy dev (từ kết quả spike, phần giao diện chưa kiểm)
- [ ] Phát một bài YouTube trọn vẹn; dò tone chạy.
- [ ] Bấm 3 nút SFX — có tiếng.
- [ ] Đọc giọng (piper) một câu.
- [ ] Ghi âm 5 giây → đóng app → mở lại → app chạy (thư mục `current\_internal` còn nguyên).
- [ ] Cài đặt → Cập nhật phần mềm: dòng trạng thái đúng; Cài đặt → Công cụ: Kiểm tra dò tone / Thử tải YouTube mở console, Mở thư mục bản thu đúng chỗ.
- [ ] Có bản chờ → bấm Kiểm tra dò tone / Thử tải YouTube / bấm đúp shortcut khi app đang mở → app đang chạy KHÔNG bị tắt; bản chờ áp dụng khi đóng app (đóng bản cuối cùng).
- [ ] Lần chạy đầu khi loopMIDI chưa chạy (để `setup_all` tự bật nó) + để nguyên console của Kiểm tra dò tone / Thử tải YouTube ở "Press any key" → đóng app → bản chờ VẪN áp dụng được (Update.exe đổi tên được `current`; không tiến trình nào có thư mục làm việc trong thư mục cài). Log: `%LocalAppData%\velopack\velopack_QuangLuuStudio.log` không có "os error 32".

## B. Máy ảo Windows sạch, tên người dùng **có dấu và dấu cách** (ví dụ `Nguyễn Văn A`)
- [ ] Cài `QuangLuuStudio-CaiDat.exe`: SmartScreen một lần, không UAC, app tự mở, có shortcut Desktop + Start Menu.
- [ ] Chưa có loopMIDI: hộp thoại lần đầu xin cài (UAC một lần) → cổng MIDI có.
- [ ] Cập nhật 1.9.0 → 1.9.1 (feed thử trên server, rollout 100% cho máy ảo): bản mới tải ngầm khi app đang chạy, không hộp thoại; đóng app → **quan sát có cửa sổ nào lóe lên**; mở lại = 1.9.1.
- [ ] Đo thời gian áp dụng bản cập nhật thật (gói ~550 MB) khi đóng app; đóng rồi mở lại ngay → app chờ cập nhật xong rồi mở bản mới, không bị tắt ngang; ghi lại số giây chờ (không có giao diện trong lúc chờ — app chỉ hiện sau khi Update.exe xong).
- [ ] Có bản chờ → `taskkill /F` → mở lại: tự áp dụng; **đo thời gian mở** so với mở thường.
- [ ] Mô hình và công cụ nằm dưới `%LocalAppData%` có dấu và dấu cách — kiểm từng thành phần gốc (native): đọc giọng (piper), nhận lệnh giọng nói (vosk), dò tone một bài, ghi âm 5 giây, tải một bài YouTube.
- [ ] Gỡ qua Apps & features → `%APPDATA%\QuangLuuStudio` và `Documents\QuangLuuStudio` còn nguyên.
- [ ] Xoá dữ liệu (Cài đặt → Công cụ) → đóng app → thư mục dữ liệu biến mất; mở lại → màn hình kích hoạt.

## C. Chuyển máy cũ (máy ảo cài sẵn 1.8.0 bằng Inno, `app_config.json` sửa tay `midi_cc.tone_music`)
- [ ] Đường 1: upload bộ cài cầu nối lên server (rollout cho máy ảo) → bộ cập nhật 1.8.0 tải và chạy → UAC một lần → app mới tự mở; `tone_music` giữ giá trị sửa tay; Program Files\QuangLuuStudio, 5 shortcut cũ và khoá `HKLM\...\{B8F3E2A1-...}_is1` đều biến mất; không có hộp "Xoá dữ liệu?".
- [ ] Sau cầu nối, khoá `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{B8F3E2A1-5D6C-4E7F-9A0B-1C2D3E4F5A6B}_is1` đã mất (xem ở bản registry 64-bit) và `C:\Program Files\QuangLuuStudio` không còn tồn tại (kể cả thư mục rỗng).
- [ ] Đường 2: cài `QuangLuuStudio-CaiDat.exe` đè lên máy có 1.8.0 → lần chạy đầu hỏi dọn bản cũ → "Để sau" thì hai bản cùng chạy được, lần mở sau hỏi lại → "Dọn" thì sạch như đường 1.
- [ ] Bộ cài cầu nối khi Setup Velopack hỏng (đổi tên `%LocalAppData%` thành chỉ đọc trước khi chạy): thông báo lỗi, bản 1.8.0 còn nguyên và chạy được.

## D. Máy khách thật
- [ ] Trọn vòng C (đường 1) trên một máy khách Cubase qua UltraViewer, có người trực.

## E. CI lần đầu (lần chạy tag đầu tiên — phần review CI không kiểm chứng được)
- [ ] `vpk` tìm thấy ngay sau `dotnet tool install -g` trong cùng một step (không cần mở shell mới / thêm PATH).
- [ ] `vpk download github --pre` khi chưa có bản phát hành trước nào có `releases.win.json` chỉ cảnh báo, không làm hỏng job.
- [ ] GitHub Release vẫn được tạo dù mẫu `*-delta.nupkg` không khớp tệp nào ở lần phát hành Velopack đầu tiên.
