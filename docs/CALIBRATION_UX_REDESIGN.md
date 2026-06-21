# Calibration UX/UI Redesign

Ngày: 2026-06-13 · File: `ui/dialogs/calibration.py`

## Bối cảnh
Wizard cân chỉnh Auto-Tune map MIDI CC (0–127) cho Scale / Key / Mode.
Bản cũ: auto-scan tăng giá trị mỗi 300ms, người dùng phải canh bấm đúng lúc.

## 3 điểm đau được nhắm tới
1. Scan quá nhanh, hay lỡ → phải reset quét lại.
2. Không biết tab nào đã xong.
3. Bố cục rối/chật (manual spinbox lặp trong từng tab).

## Giải pháp đã làm
### 1. "Live tuner" dùng chung thay cho auto-scan
- **Slider 0–127 kéo tay**, gửi MIDI trực tiếp khi kéo → không còn áp lực thời gian.
- Giá trị bắt = đúng số đang gửi (`current_value`), **hết off-by-one** (`-1`).
- Nút nhích nhanh `−10 / −1 / +1 / +10` + ô nhập số chính xác.
- **Auto-sweep tùy chọn** (▶/⏸) với tốc độ chọn được: Chậm 450ms / Vừa 280ms / Nhanh 140ms.
- `_set_value()` là single source of truth: clamp → sync slider+spin (blockSignals) → gửi MIDI.

### 2. Hiện tiến độ
- Chip tiến độ ở header: `Scale x/2`, `Key x/12`, `Chế độ x/1`, đổi xanh + ✓ khi xong.
- Tiêu đề tab cập nhật: `Kiểu Scale ✓`, `Nốt gốc (5/12)`, `Chế độ`.

### 3. Gọn bố cục
- Bỏ toàn bộ spinbox lặp trong từng tab (tuner chung lo việc nhập).
- Mỗi tab chỉ còn nút "bắt giá trị" + badge kết quả.
- Lưới 12 phím cao 54px, hiển thị `C\n42` ngay trên nút, đổi xanh khi đã bắt.

## Giữ nguyên
- Logic `_save_calibration` + enharmonic mapping + backend AppConfig.
- Token màu/`pill_btn_qss`/`add_shadow`.

## Còn có thể làm tiếp
- "MIDI Learn" thật (lắng nghe CC từ plugin) thay vì người dùng tự canh.
- Mode tab hiện chỉ có "Fix Méo"; mở rộng nếu cần nhiều chế độ.
