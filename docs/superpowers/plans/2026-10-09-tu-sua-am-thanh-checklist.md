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
