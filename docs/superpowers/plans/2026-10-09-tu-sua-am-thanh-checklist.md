# Checklist thử tay — Tự sửa âm thanh (máy dev Cubase 13 + mau.cpr; lặp lại trên máy SO)

Chuẩn bị: app bản worktree, Cubase đóng, loopMIDI đang chạy.

1. Cài đặt → Âm thanh: chọn thiết bị ảo. Đóng app.
2. Gây lỗi: tắt loopMIDI; đổi Default playback sang loa thật; mute Chrome trong Volume Mixer;
   bật Release Driver trong Cubase (Studio Setup) rồi thoát Cubase; mute Mic trên app trước khi đóng.
3. Mở app (auto_launch_studio_one = bật). Chờ Cubase mở xong + 10 s.
   Kỳ vọng: dải vàng hiện, TTS đọc một câu; nhật ký `%APPDATA%\QuangLuuStudio\logs\audio_doctor.log` có dòng source=startup.
4. Bấm dải vàng → hộp thoại tự sửa. Kỳ vọng: hỏi đóng Cubase (Release Driver) → Có;
   loopMIDI lên, Cubase mở lại, Mic + Nhạc bật, default playback về thiết bị ảo, Chrome hết mute.
   Kết thúc: "Đã sửa N mục…", không mục đỏ.
5. Hát thử: có tiếng mic + nhạc. Bè/Vang giữ đúng trạng thái trước đó.
6. Trong Cubase tự mute track Mic → nút Mic trên app chuyển sang tắt trong ≤ 1 s (phản hồi QLS_PhanHoi).
7. Studio One: lặp 2–5; kênh Mic/Nhạc báo "đã gửi lệnh bật".
8. Tắt mạng / máy chậm: Cubase mở > 3 phút → dải vàng "chưa mở xong", sau khi Cubase lên thì dải tự ẩn (rerun).

## Kết quả chạy thật — 2026-10-12, máy dev (Cubase 13.0.10, `D:\QLS\mau.cpr`)

Máy dev không có thiết bị ảo (ASIOVADPRO/VB-Cable) nên mục 1 và phần "thiết bị phát mặc định" chỉ
kiểm được nhánh "không tìm thấy". Lỗi gây ra: loopMIDI tắt, Cubase tắt.

- Mục 3 — **đạt**: Cubase tự mở `mau.cpr`; kiểm tra lúc khởi động ghi `source=startup`, bắt đúng
  loopMIDI chưa chạy và hộp «Missing Ports» của Cubase (micro Logitech rút ra — không liên quan
  loopMIDI); dải vàng hiện "loopMIDI chưa chạy … +2 vấn đề khác".
- Mục 4 — **đạt một phần**: bấm dải vàng → bật loopMIDI đủ 2 cổng, nối lại MIDI; «Missing Ports»
  báo cần làm tay (đúng thiết kế). Release Driver chưa gây lỗi được (Cubase đang tắt sẵn mục này).
- Mục 6 — **đạt**: mute track Mic trong Cubase → kênh Mic trên app chuyển MUTED gần như tức thì.
- Mục 8 — **đạt**: sau khi trả lời hộp thoại, Cubase lên → kiểm tra chạy lại, mọi mục ổn, dải vàng tự ẩn.
- Ctrl+Shift+A mở hộp thoại, tự sửa: bật kênh Nhạc khi chưa có phản hồi kênh Nhạc từ Cubase.

Lỗi tìm ra và đã sửa:
- Hộp thoại chữ sáng trên nền sáng mặc định, danh sách bị bóp còn 2 dòng, bị Cubase che khi chạy
  xong → nền tối tường minh, cao tối thiểu 420, `raise_()` khi xong.
- Cửa sổ loopMIDI bật giữa màn hình khi tự bật → mở thu nhỏ, không lấy tiền cảnh.

Ghi nhận, chưa sửa:
- Sau khi mở lại app, kênh Nhạc báo "không rõ" tới khi Cubase gửi phản hồi (Cubase chỉ báo khi đổi).
- Log đồng bộ MIDI vẫn in "Studio One đã sẵn sàng" khi đang dùng Cubase.
- Chạy pytest trong thư mục mã nguồn ghi đè `settings.json` thật của bản chạy từ source (thư mục
  dữ liệu khi chạy từ source = gốc repo).
