# Roadmap cải thiện tính năng — Quang Lưu Studio

> **Ngày lập:** 2026-06-10 · **Phiên bản app:** 1.5.0
> Tổng hợp từ 3 plan chi tiết (mỗi plan có hiện trạng file:line, kiến trúc, phase, rủi ro, tiêu chí nghiệm thu):
>
> 1. [PLAN_SCORING_REAL.md](PLAN_SCORING_REAL.md) — Chấm điểm thật + biểu đồ pitch + lịch sử điểm
> 2. [PLAN_TIMELINE_YOUTUBE.md](PLAN_TIMELINE_YOUTUBE.md) — UI timeline tone, giảm trễ AutoKey, đồng bộ pause/seek + queue, DPAPI cookie
> 3. [PLAN_VOICE_OPS_LICENSING.md](PLAN_VOICE_OPS_LICENSING.md) — Voice control mở rộng, model download, auto-update, crash report, licensing

---

## Phát hiện quan trọng khi khảo sát (cần biết trước khi xếp lịch)

1. **Voice control đang CHẾT trên máy khách:** model Vosk không được đóng gói vào EXE/installer (spec + iss đều thiếu `models/`), path mặc định lại trỏ vào Program Files (read-only). → "Model download-on-first-run" thực chất là **bug fix**, không phải tối ưu — nên làm đầu tiên.
2. **Auto-update đã có ~80% hạ tầng** (check, download resume, verify, dialog) nhưng handoff bị hỏng: `sys.exit(0)` gọi từ thread nền không thoát được app → installer treo. Vá nhỏ, giá trị lớn.
3. **Chấm điểm hiện tại đo bản mix (nhạc + giọng)** nên điểm gần như vô nghĩa; recorder đã thu riêng 2 stream nhưng trộn mất — chỉ cần ghi thêm 1 file mic là mở khoá chấm thật.
4. **Replay timeline đã bám theo player time** (pause/seek phần lớn đã đúng) — chỗ hỏng còn lại là detect video-end bằng `time.sleep(duration)` wall-clock.

## Lộ trình đề xuất (theo sprint, 1 dev)

| Sprint | Việc | Plan | Effort | Lý do thứ tự |
|---|---|---|---|---|
| **1** | Model Vosk download-on-first-run | Voice/Ops F2 | 3 ngày | Bug fix thực tế trên máy khách |
| **1** | Crash reporting "Gửi báo lỗi" | Voice/Ops F4 | 3 ngày | Thu data lỗi sớm cho mọi việc sau |
| **2** | Auto-update hoàn thiện | Voice/Ops F3 | 2.5 ngày | Các bản sau tự lan toả qua update |
| **2** | DPAPI cookie | Timeline F4 | 2–2.5 ngày | Độc lập, đóng lỗ hổng privacy |
| **2** | Lịch sử điểm (storage trước) | Scoring F2.1 | 1 ngày | Bắt đầu tích luỹ data ngay với điểm legacy |
| **3** | Đồng bộ video-end + PlayQueue | Timeline F3 | 3 ngày | Nền tảng position/state cho timeline UI |
| **3** | UI timeline tone + sửa tay | Timeline F1 | 4–5 ngày | Tính năng nhìn thấy được, dữ liệu đã có sẵn |
| **4** | Chấm điểm thật + pitch chart | Scoring F1 | 12.5 ngày | Tính năng "wow", cần nhiều thời gian tinh chỉnh nhất |
| **4** | UI lịch sử điểm + sparkline | Scoring F2.2 | 2.5 ngày | Ghép cùng pitch chart (cùng là QPainter UI) |
| **5** | Voice control mở rộng (tham số, beep, wake word) | Voice/Ops F1 | 7 ngày | Sau khi model download ổn định |
| **5** | Giảm trễ AutoKey | Timeline F2 | 3–3.5 ngày | Cần tinh chỉnh thực địa, tách riêng để đo |
| **6** | Licensing offline (HWID + ký + chống vặn giờ) | Voice/Ops F5.1 | 4 ngày | Trước khi mở bán rộng |
| (sau) | Licensing online (Cloudflare Worker) | Voice/Ops F5.2 | 6–8 ngày | Chỉ khi doanh số đáng kể |

**Tổng (không gồm licensing online): ~48–51 ngày công.**

## Nguyên tắc chung xuyên suốt các plan

- **Không thêm dependency nặng**: tất cả tính năng dùng librosa/scipy/PySide6/pywin32/stdlib đã có; từ chối pyqtgraph, crepe, demucs, requests, sentry-sdk.
- **UI vẽ QPainter thuần** theo pattern `ui/components/painter_*.py` hiện có.
- **JSON persistence** theo pattern `core/songs.py`: module lock + `atomic_write_json` + file trong `DATA_DIR`.
- **Worker thread → UI** luôn qua Qt Signal (pattern `_tone_result_signal`).
- **Fail-soft**: mọi tính năng mới hỏng (mất mạng, thiếu model, CDP rớt) đều fallback về hành vi hiện tại, không crash — người dùng là ca sĩ đang diễn live.

## Việc treo lại chờ quyết định (từ đợt review 2026-06-10)

- **Rewrite git history** (`git filter-repo`): xoá 5 activation code + secret key cũ đã lộ, đồng thời gỡ 51MB model Vosk khỏi history (`.git` hiện 124MB). Cần force-push — ai đã clone phải re-clone. Nên làm **một lần duy nhất**, gộp cả hai mục đích, sau khi model download-on-first-run (Sprint 1) đã chạy.
- **CDP `--remote-allow-origins=*`** trong `tools/_apply_cdp.ps1`: rủi ro bảo mật đã ghi nhận; thử siết origin cần test riêng với CDP monitor.
