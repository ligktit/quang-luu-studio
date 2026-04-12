# SFX Custom Buttons — Dynamic User-Linkable Sound Effects

Thay thế cụm 3 nút SFX cố định (😂 👏 🎉) bằng một vùng SFX động, cho phép người dùng tự thêm/xoá/chỉnh sửa/sắp xếp các nút liên kết với bất kỳ file `.wav` nào.

## User Review Required

> [!IMPORTANT]
> Dữ liệu SFX custom buttons sẽ được lưu vào `settings.json` qua `ConfigManager`, cùng nơi các settings khác. Điều này đồng nghĩa khi user reset settings, danh sách SFX buttons cũng bị reset.

> [!IMPORTANT]
> Vùng SFX sẽ nằm **ngay dưới label "SFX"** trong Panel 3 (MODE), thay thế hoàn toàn 3 nút hardcoded hiện tại. Bố cục panel MODE không thay đổi phần Mode buttons phía trên.

## Proposed Changes

### 1. UI Behavior & Layout

**Bố cục vùng SFX (dưới label "SFX" trong Panel MODE):**

```
┌──────────────── MODE PANEL ────────────────┐
│  [Dân Ca] [Lofi] [Remix] [Đa Thể Loại]   │  ← mode buttons (giữ nguyên)
│                                             │
│  ─── SFX ───                                │
│                                             │
│  ┌───────────────────────────────────┐      │
│  │ Scrollable SFX Area               │      │
│  │  [😂 Cười]  [👏 Vỗ tay]  [🎉]   │      │  ← user buttons (drag to reorder)
│  │  [🎵 My SFX]  [+]                │      │  ← [+] = thêm nút mới
│  │                                   │      │
│  │  ── empty state ──                │      │
│  │  "Chưa có SFX. Nhấn + để thêm."  │      │
│  └───────────────────────────────────┘      │
└─────────────────────────────────────────────┘
```

**Interactions:**
- **Thêm nút:** Nhấn nút `[+]` → mở dialog nhỏ chọn emoji + label + file `.wav`/`.mp3`
- **Xoá nút:** Right-click → context menu → "Xoá"
- **Chỉnh sửa:** Right-click → context menu → "Sửa" → dialog sửa label/emoji/file
- **Sắp xếp:** Drag-and-drop các nút để đổi vị trí
- **Phát SFX:** Click nút → phát file sound effect đã liên kết
- **Trạng thái:** Nút hiển thị tooltip với đường dẫn file. Nút thiếu file sẽ có viền đỏ nhấp nháy.

### 2. Data Structure

```json
// Trong settings.json
{
  "sfx_buttons": [
    {
      "id": "sfx_001",
      "label": "😂",
      "name": "Cười",
      "file_path": "D:/My SFX/laugh.wav",
      "color": "#F59E0B"
    },
    {
      "id": "sfx_002",
      "label": "👏",
      "name": "Vỗ tay",
      "file_path": "",
      "color": "#38BDF8"
    }
  ]
}
```

Mặc định khi chưa có `sfx_buttons` trong settings, sẽ khởi tạo 3 nút default (laugh, applause, cheer) trỏ vào thư mục `sfx/` có sẵn.

---

### Component: SFX Button Area Widget

#### [NEW] [sfx_button_area.py](file:///d:/Projects/LiveStudio/quang-luu-studio/ui/components/sfx_button_area.py)

Widget mới `SfxButtonArea` kế thừa `QWidget`, chứa:

1. **FlowLayout** wrap các nút SFX (mỗi nút là `PainterButton`) + 1 nút `[+]`
2. **Empty state** label khi chưa có nút nào
3. **Context menu** cho mỗi nút (Sửa / Xoá)
4. **Drag-and-drop** reorder qua `QDrag`
5. **Add/Edit dialog** (`QDialog`) để chọn emoji, label, file path
6. Signal `sfx_changed` để `frontend_qt.py` lưu settings

Lớp phụ `SfxItemButton(PainterButton)`:
- Override `contextMenuEvent` → menu "Sửa" / "Xoá"
- Override mouse events cho drag-and-drop
- Tooltip hiển thị file path
- Visual indicator cho file missing (viền đỏ)

---

### Component: Frontend Integration

#### [MODIFY] [frontend_qt.py](file:///d:/Projects/LiveStudio/quang-luu-studio/frontend_qt.py)

**Thay đổi 1: Import `SfxButtonArea`** (dòng ~26-32)
```python
from ui.components.sfx_button_area import SfxButtonArea
```

**Thay đổi 2: `_build_panel_mode()`** (dòng 392-443)
- Xoá bỏ `sfx_config`, `self._sfx_buttons` hardcoded, `sfx_row`
- Thay bằng `SfxButtonArea` widget
- Load SFX data từ `self.settings.get("sfx_buttons", [])` 
- Kết nối signal `sfx_changed` → `_on_sfx_config_changed()`
- Kết nối signal `sfx_play` → `_on_sfx_play(path)`

**Thay đổi 3: `_on_sfx_play()`** (dòng 1968-1988)
- Refactor: nhận `file_path` trực tiếp thay vì `sfx_id` lookup
- Bỏ dict `sfx_files` hardcoded

**Thay đổi 4: Thêm `_on_sfx_config_changed()`**
- Lưu danh sách SFX buttons vào settings.json qua `ConfigManager`

---

### Component: Default Migration

Khi `settings.json` chưa có key `sfx_buttons`, tạo 3 entries mặc định trỏ vào `sfx/sfx_laugh.wav`, `sfx/sfx_applause.wav`, `sfx/sfx_cheer.wav` (dùng đường dẫn tương đối qua `_get_app_dir()`).

---

## Verification Plan

### Automated Tests
- Chạy `python main.py` → kiểm tra Panel MODE hiển thị đúng
- Thêm/xoá/sửa nút SFX → verify `settings.json` cập nhật
- Thoát và mở lại app → verify nút SFX được restore

### Manual Verification
- Click nút SFX → phát audio
- Right-click → context menu hoạt động
- Drag-and-drop reorder
- Trạng thái empty state khi xoá hết nút
- Nút với file không tồn tại → hiển thị cảnh báo visual
