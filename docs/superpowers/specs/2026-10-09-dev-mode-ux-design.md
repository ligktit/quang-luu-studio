# Dev Mode UX — quản lý widget, sao lưu/khôi phục, Widget Builder thân thiện

> **Ngày:** 2026-10-09 · **Trạng thái:** chờ duyệt spec
> Liên quan: `docs/DEV_MODE_GUIDE.md`, `frontend_qt.py` (`_on_add_widget` / `_on_edit_widget` /
> `_on_hide_widget` / `_apply_widget_calibration`), `ui/panels/{mixer,tools,mode}.py`,
> `ui/dialogs/widget_builder.py`, `core/config.py` (`UiConfigManager`, `AppConfig.set_calibration`).

## 1. Mục tiêu

Người dùng Dev Mode là **kỹ thuật viên setup máy khách**, không phải khách. Thành công = setup trọn
một máy khách **không phải mở `ui_config.json` bằng tay**:

- hiện lại widget đã ẩn, đổi thứ tự, xoá widget custom;
- Widget Builder khó nhập sai (cảnh báo CC trùng, kiểm tra tức thì, gửi thử);
- xuất/nhập toàn bộ setup Dev Mode của một máy trong app.

**Ngoài phạm vi:** dễ phát hiện Dev Mode / chỉ báo ON thường trực; lưu trạng thái Dev Mode qua lần
khởi động; nút momentary chỉ gửi On Value. Phím `Ctrl+Shift+D` và menu chuột phải Sửa/Ẩn giữ nguyên.

## 2. Ràng buộc từ code hiện tại

- Thứ tự phần tử trong mỗi mảng `mixer`/`tools`/`mode` của `ui_config.json` **là** thứ tự hiển thị.
- `UiConfigManager._merge_new_defaults` nối lại mọi id built-in bị thiếu ⇒ **widget built-in chỉ
  ẩn được, không xoá được.** Chỉ widget custom (id `custom_…`, không có `action`) mới xoá được.
- `calibration_overrides.json` (DATA_DIR) có thể chứa key do công cụ khác ghi (vd. key/scale map
  theo máy khách) — sao lưu phải lấy **nguyên file**, không lọc. Ghi không BOM (`atomic_write_json`).
- Sau khi đổi file calibration phải `AppConfig.reload()` rồi bắn lại trạng thái (như
  `_apply_widget_calibration` đang làm).

## 3. Thiết kế

### 3.1 Hộp "Quản lý giao diện" — `ui/dialogs/widget_manager.py` (mới)

**Mở:** nút **"⚙ Quản lý"** đặt cạnh mỗi nút `+ Thêm` / `+ Thêm Nút` / `+ Thêm Mode` (chỉ khi Dev
Mode bật). Mở đúng tab của panel đó. `MainDashboard._on_manage_widgets(panel_name)`.

**Bố cục:**

```
┌ Quản lý giao diện ──────────────────────┐
│ [Mixer] [Tools] [Mode]                   │
│ ☑ ≡ Nhạc        có sẵn    [Sửa]          │
│ ☐ ≡ Vang        có sẵn    [Sửa]          │
│ ☑ ≡ Vang HT     CC 60     [Sửa] [Xoá]    │
│              [↑] [↓] [+ Thêm]            │
│ [Khôi phục mặc định panel này]           │
├──────────────────────────────────────────┤
│ [Xuất file] [Nhập file]    [Lưu] [Huỷ]   │
└──────────────────────────────────────────┘
```

- Mỗi tab là một `QListWidget` (kéo-thả nội bộ `InternalMove`) + nút ↑/↓ cho hàng đang chọn.
- Checkbox của hàng = `not hidden`. Widget ẩn hiện chữ mờ.
- Nhãn phụ: "có sẵn" (built-in) hoặc "CC n" (custom/override số).
- **Sửa** → mở `WidgetBuilderDialog` như hiện nay, kết quả ghi vào **bản sao làm việc**; calibration
  trả về được gom lại và áp khi Lưu.
- **Xoá** chỉ hiện với widget custom; hỏi xác nhận.
- **+ Thêm** → Widget Builder, thêm vào cuối bản sao.
- **Khôi phục mặc định panel này** → hỏi xác nhận (cảnh báo sẽ mất widget custom của panel), thay
  panel trong bản sao bằng `_DEFAULT_UI_CONFIG[panel]`.
- **Lưu**: `save_ui_config(bản sao)`, áp calibration đã gom, `refresh_ui()` **một lần**.
  **Huỷ** / đóng cửa sổ: bỏ mọi thay đổi (nếu có thay đổi thì hỏi "Bỏ thay đổi?").

Logic thuần (không Qt) tách ra để test: `move(entries, i, delta)`, `set_hidden(entries, id, bool)`,
`delete_custom(entries, id)` (từ chối built-in), `reset_panel(config, panel)`, `is_custom(entry)`.
Đặt trong `core/ui_layout.py` (mới).

### 3.2 Sao lưu / khôi phục — `core/devmode_backup.py` (mới)

**Định dạng file** `quangluu-giaodien-YYYYMMDD-HHMM.json`:

```json
{
  "format": "quangluu-devmode-backup",
  "format_version": 1,
  "app_version": "1.8.0",
  "exported_at": "2026-10-09T14:30:00",
  "ui_config": { "mixer": [...], "tools": [...], "mode": [...] },
  "calibration_overrides": { ... }
}
```

API:
- `build_backup() -> dict` — đọc `ui_config.json` (qua `load_ui_config`) + nguyên
  `calibration_overrides.json` (thiếu → `{}`).
- `export_backup(path)` — ghi `build_backup()` bằng `atomic_write_json`.
- `read_backup(path) -> dict` — kiểm tra: JSON hợp lệ, `format` đúng, `format_version <= 1`,
  `ui_config` là dict có ít nhất một mảng panel, `calibration_overrides` là dict. Sai → ném
  `BackupError(thông điệp tiếng Việt)`.
- `summarize(backup) -> str` — vd. "Mixer: 5 widget (1 ẩn) · Tools: 7 · Mode: 4 · 3 mục cân chỉnh
  MIDI · xuất từ v1.8.0 lúc 09/10/2026 14:30".
- `restore_backup(backup) -> list[str]` — chép 2 file hiện có sang
  `DATA_DIR/backups/<tên>.<timestamp>.bak` (file nào không có thì bỏ qua), rồi ghi cả 2 file atomic,
  rồi `AppConfig.reload()`. Trả về danh sách file .bak. Lỗi ghi giữa chừng → khôi phục từ .bak vừa
  tạo và ném `BackupError`.

**UI (footer hộp Quản lý):**
- **Xuất file** → `QFileDialog.getSaveFileName` (tên gợi ý như trên) → toast "Đã xuất …".
- **Nhập file** → `getOpenFileName` → `read_backup` → hộp xác nhận hiện `summarize(...)` + "Cấu hình
  hiện tại sẽ được sao lưu tự động trước khi ghi đè." → `restore_backup` → đóng hộp Quản lý,
  `refresh_ui()`, bắn lại trạng thái mode/toggle (tái dùng phần gửi lại của
  `_apply_widget_calibration`, tách thành `_resend_calibrated_states(modes, toggles)`).
- Nếu bản sao làm việc đang có thay đổi chưa lưu → hỏi trước khi nhập (thay đổi sẽ bị bỏ).

### 3.3 Widget Builder — `ui/dialogs/widget_builder.py`

1. **Nhãn & bố cục thân thiện**
   - Combo loại hiển thị "Thanh trượt" / "Nút" (data vẫn `slider`/`button`).
   - Ẩn combo loại khi **sửa**; panel `tools`/`mode` chỉ có "Nút" ⇒ cũng ẩn khi thêm.
   - Nhóm trường dưới tiêu đề: **Hiển thị** (tên, màu, icon), **MIDI** (CC, cảnh báo, Gửi thử),
     **Giá trị** (phần slider min/max/mute hoặc phần giá trị Studio One hiện có).
   - Hàng ô màu nhanh từ token `C` trong `ui/design_tokens.py`: primary, creative, accent, green,
     orange, pink, deep_purple, blue; bấm ô → điền hex của token. Giữ ô hex + "Chọn màu".
2. **Cảnh báo CC trùng** — hàm thuần
   `find_cc_conflicts(cc, ui_config, midi_cc, exclude_id) -> list[str]` (đặt trong
   `core/ui_layout.py`): liệt kê widget custom/override khác dùng CC số đó ("Vang HT (Tools)") và
   key built-in trong `app_config.midi_cc` có cùng số ("built-in mix_reverb"). Hiện nhãn vàng dưới ô
   CC; **không chặn Lưu**. CC = -1 → không cảnh báo.
3. **Gửi thử** — nút cạnh ô CC. Bấm: gửi giá trị BẬT, ~300 ms sau gửi giá trị TẮT (slider: gửi
   giữa dải rồi về mức min) qua `parent.engine.send_midi(cc, value)` — chạy được cả Studio One lẫn
   Cubase. Giá trị lấy theo quy đổi `so_values` hiện tại của form. Disable khi CC = -1 hoặc dialog
   không có engine (test/không có parent). Lỗi gửi → hiện ở error label, không crash.
4. **Kiểm tra tức thì** — `_validate() -> str | None` chạy mỗi khi trường đổi: tên rỗng; Min ≥ Max
   (slider); hex màu sai (`#rgb`/`#rrggbb` hoặc tên token hợp lệ); khoảng số Từ = Đến (nút kiểu
   khoảng); danh sách lựa chọn rỗng (nút kiểu danh sách). Có lỗi → disable **Lưu**, hiện lý do ở
   `error_label`. Giữ kiểm tra trong `_on_save` làm chốt chặn cuối.
   Lưu ý geometry: `error_label` dành sẵn chiều cao cố định như `value_note` để tránh cảnh báo
   `setGeometry` khi ẩn/hiện (bài học commit 49a41ab).

### 3.4 Thay đổi panel & dashboard

- `ui/panels/{mixer,tools,mode}.py`: cạnh nút `+ Thêm…` thêm nút "⚙ Quản lý" (cùng kiểu viền đứt)
  → `dashboard._on_manage_widgets(panel)`.
- `frontend_qt.py`: thêm `_on_manage_widgets`; tách `_resend_calibrated_states`; `_on_add_widget` /
  `_on_edit_widget` / `_on_hide_widget` giữ nguyên hành vi.

## 4. Xử lý lỗi

- Ghi `ui_config.json` thất bại (`save_ui_config` trả False) → toast lỗi, không `refresh_ui`, hộp
  Quản lý không đóng.
- Nhập file hỏng / sai định dạng / phiên bản mới hơn → hộp lỗi tiếng Việt, không ghi gì.
- Ghi lỗi giữa khôi phục → tự trả lại từ .bak, báo lỗi kèm đường dẫn .bak.
- Gửi thử khi engine/MIDI port lỗi → thông báo trong dialog.

## 5. Kiểm thử

Chạy bằng Python Windows `.venv` từ WSL (xem memory test-env), numpy<2.3.

- `tests/core/test_ui_layout.py`: move (biên đầu/cuối), set_hidden, delete_custom từ chối built-in,
  reset_panel, find_cc_conflicts (trùng custom, trùng built-in midi_cc, loại trừ chính nó, -1).
- `tests/core/test_devmode_backup.py` (tmp DATA_DIR): round-trip export→read→restore; tạo .bak;
  file sai format/version/JSON hỏng → BackupError và file đích không đổi; calibration giữ nguyên key
  lạ; summarize đếm đúng widget ẩn.
- `tests/ui/test_widget_manager.py`: mở đúng tab; ↑/↓ đổi thứ tự trong bản sao; bỏ tick → hidden;
  nút Xoá không có ở built-in; Huỷ không ghi file; Lưu ghi đúng thứ tự và gọi refresh_ui một lần.
- `tests/ui/test_widget_builder_*`: nhãn combo; combo ẩn khi sửa; Lưu disable + lý do với từng lỗi
  validate; cảnh báo CC trùng hiện/ẩn; Gửi thử gọi `send_midi` on rồi off (QTimer qua `qtbot.wait`),
  disable khi CC = -1; không cảnh báo geometry.
- Test hiện có của Dev Mode (`test_tools_panel`, `test_widget_builder_so_values`,
  `test_pin_and_widget_calibration`, …) phải xanh.

## 6. Tài liệu

Cập nhật `docs/DEV_MODE_GUIDE.md`: mục hộp Quản lý, Xuất/Nhập, cảnh báo CC, Gửi thử; bỏ hạn chế
"chưa có UI hiện lại widget đã Ẩn"; quy trình setup khách (mục 5) dùng Xuất file thay vì copy tay.
