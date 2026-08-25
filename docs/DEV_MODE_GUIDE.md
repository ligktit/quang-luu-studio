# Hướng dẫn Dev Mode — Tuỳ biến nút & slider trên Dashboard

> **Ngày viết:** 2026-06-11 · đối chiếu trực tiếp với code hiện tại.
> Dev Mode dành cho **người cài đặt/kỹ thuật viên** khi setup app cho từng phòng thu — tuỳ biến nút bấm, slider và mode mà không cần sửa code.
>
> ⚠️ Dev Mode **không** bị chặn bởi chế độ khách — xem [KIOSK_MODE_GUIDE.md](KIOSK_MODE_GUIDE.md)
> để biết cách khoá Studio One khỏi khách hàng và giới hạn hiện tại của nó.

---

## 1. Bật / tắt Dev Mode

- Nhấn **`Ctrl + Shift + D`** trong cửa sổ chính (shortcut đăng ký tại `frontend_qt.py:234`).
- Thanh thông báo hiện `Dev Mode: ON` / `OFF` và UI tự vẽ lại (`_toggle_dev_mode` → `refresh_ui`, `frontend_qt.py:237-240`).
- Trạng thái **không được lưu** — khởi động lại app là tắt. Đây là chủ ý: khách hàng dùng bình thường sẽ không bao giờ thấy chế độ này.

Khi Dev Mode BẬT, 3 panel sau thay đổi:

| Panel | Thêm gì khi bật Dev Mode |
|---|---|
| **MIXER** (slider Nhạc/Mic/Vang/Giọng) | Chuột phải lên kênh → menu **Sửa / Ẩn**; nút **`+ Thêm`** ở cuối panel |
| **TOOLS** (Chế độ Nhanh, Dò Lại, Auto-Tune, Fix Méo) | Chuột phải lên nút → **Sửa / Ẩn**; nút **`+ Thêm Nút`** |
| **MODE** (Dân Ca, Lofi, Remix, Đa Thể Loại) | Chuột phải lên nút → **Sửa / Ẩn**; nút **`+ Thêm Mode`** |

Khu vực SFX và 2 stepper Tone Nhạc/Tone Giọng **không** thuộc dev mode (SFX có cơ chế tự cấu hình riêng qua `settings.json`).

## 2. Thêm widget mới

Bấm **`+ Thêm`** / **`+ Thêm Nút`** / **`+ Thêm Mode`** → mở dialog **Widget Builder** (`ui/dialogs/widget_builder.py`):

### Trường chung
| Trường | Ý nghĩa |
|---|---|
| **Loại Widget** | `slider` hoặc `button` |
| **Tên (Label)** | Chữ hiển thị trên nút/kênh |
| **Màu sắc** | Mã hex (`#14b8a6`) hoặc bấm "Chọn màu". Cũng nhận tên token màu của app (`teal`, `accent`, `green`…) nếu gõ tay vào file config |
| **MIDI CC** | Số CC (0–127) sẽ gửi đến Studio One qua port `QuangLuuMIDI` |

### Riêng cho `button`
| Trường | Ý nghĩa |
|---|---|
| **On Value / Off Value** | Giá trị CC gửi khi bật / tắt (mặc định 127 / 0) |
| **Là nút Toggle** | ✓ = nút bật/tắt (sáng lên khi active, gửi on↔off luân phiên). ✗ = nút bấm 1 lần (chỉ gửi On Value — xem mục Hạn chế) |

### Riêng cho `slider`
| Trường | Ý nghĩa |
|---|---|
| **Icon** | 1 ký tự hiển thị (♪, ☉, ≡…) |
| **Min / Max** | Dải giá trị UI của slider |
| **Có nút Mute** | Thêm nút tắt âm cho kênh |

Bấm **Lưu** → widget được ghi vào `ui_config.json` với `id` dạng `custom_xxxxxxxx` và UI vẽ lại ngay.

**Nút custom hoạt động thế nào:** widget không có trường `action` (hoặc `action` không khớp method nào của dashboard) sẽ gửi thẳng **MIDI CC số** đã khai báo (`ui/panels/tools.py:144-167`, `ui/panels/mode.py:47-79`). Trong Studio One, vào MIDI Learn trên tham số cần điều khiển rồi bấm nút trong app để map.

## 3. Sửa / Ẩn widget

- **Chuột phải → Sửa**: mở lại Widget Builder với dữ liệu hiện tại. Các field hệ thống (`action`, `desc`…) được bảo toàn khi lưu.
  - **Nút TOOLS/MODE built-in** (Dò Lại, Auto-Tune, Dân Ca…): có thể **ghi đè bằng MIDI CC số**. Chọn một số CC (0–127) ở ô MIDI CC + đặt On/Off Value → nút sẽ **gửi thẳng CC đó và bỏ qua chức năng gốc** (`tools.py` / `mode.py`: `cc` dạng số → override `action`). Để ô ở **"— (không gán)"** (giá trị -1) thì giữ nguyên chức năng built-in.
  - **Slider MIXER built-in**: ô MIDI CC vẫn bị **khoá** (CC dạng tên giữ nguyên) — chỉ label/màu/tham số hiển thị chỉnh được.
- **Chuột phải → Ẩn**: set `"hidden": true` trong config — widget biến mất khỏi UI nhưng **không bị xoá**.
- **Hiện lại widget đã ẩn**: chưa có UI — mở `ui_config.json`, đổi `"hidden": true` → `false`, lưu rồi bấm Ctrl+Shift+D hai lần (hoặc khởi động lại app).

## 4. File cấu hình `ui_config.json`

| Môi trường | Vị trí |
|---|---|
| Chạy dev (python) | Thư mục gốc project — `D:\Projects\LiveStudio\quang-luu-studio\ui_config.json` |
| Bản cài đặt (EXE) | `%APPDATA%\QuangLuuStudio\ui_config.json` |

Cấu trúc 3 mảng `mixer` / `tools` / `mode` (xem `core/config.py:364-398` cho default đầy đủ):

```json
{
    "tools": [
        { "id": "btn_rescan", "type": "button", "label": "Dò Lại",
          "color": "#14b8a6", "action": "force_rescan",
          "desc": "Buộc dò lại tone bài hát đang phát", "hidden": false },

        { "id": "custom_a1b2c3d4", "type": "button", "label": "Vang Hội Trường",
          "color": "#eab308", "cc": 60, "on_value": 127, "off_value": 0,
          "is_toggle": true, "hidden": false }
    ]
}
```

Phân biệt 2 loại entry:
- **Built-in**: có `"action"` (tên method `_on_<action>` trong `frontend_qt.py`, ví dụ `force_rescan`, `tone_auto`, `set_mode_lofi`) và/hoặc `"cc"` là **chuỗi tên** tra trong `app_config.json → midi_cc` (ví dụ `"mix_music"`).
- **Custom** (tạo từ Widget Builder): `"cc"` là **số** CC thô, kèm `on_value/off_value/is_toggle` (button) hoặc `range/icon/has_mute` (slider).

**Reset toàn bộ về mặc định:** xoá file `ui_config.json` → app tự dùng config mặc định trong code (`UiConfigManager._DEFAULT_UI_CONFIG`). File hỏng/JSON sai cú pháp cũng tự rơi về mặc định, không crash.

## 5. Quy trình khuyến nghị khi setup cho khách

1. Map sẵn các CC trong Studio One (External Device `QuangLuuMIDI` + MIDI Learn).
2. Bật app → `Ctrl+Shift+D`.
3. Ẩn các nút khách không dùng; thêm nút custom cho các tham số riêng của phòng thu (chọn CC chưa dùng — tránh trùng các CC built-in trong `app_config.json → midi_cc`).
4. Test từng nút (xem CC về trong Studio One).
5. `Ctrl+Shift+D` tắt dev mode → backup file `ui_config.json` của khách (copy ra ngoài) để cài lại nhanh khi cần.

## 6. ⚠️ Hạn chế đã biết (tính đến 2026-06-11)

1. **Nút momentary (không toggle) chỉ gửi On Value**, không gửi Off khi nhả (ghi chú TODO trong `tools.py`). Tham số dạng trigger trong Studio One vẫn dùng tốt; tham số cần on/off thì dùng Toggle.
2. **Chưa có UI hiện lại widget đã Ẩn** — phải sửa `hidden: false` trong `ui_config.json` (mục 3).
3. **Mute trên slider custom** không có CC mute riêng: app gửi giá trị 0 trên chính CC của kênh khi mute và khôi phục giá trị slider khi bật lại — khác cơ chế mute của 3 kênh built-in (có CC mute riêng `mute_music/mute_mic/mute_reverb`).

> Lịch sử: 3 lỗi từng tồn tại (Sửa built-in làm mất `action`/`cc`; slider custom KeyError không gửi MIDI; nút custom panel MODE crash do thiếu import `lighten`) — **đã sửa ngày 2026-06-11** trong `widget_builder.py`, `mixer.py`, `mode.py`.
>
> Cập nhật 2026-06-12: (a) nút TOOLS/MODE built-in nay **override được bằng CC số** (trước đây bị bỏ qua); (b) nút toggle custom trước đọc nhầm thuộc tính `_is_active` nên **luôn gửi On Value, không gửi Off** — đã sửa sang `_active`; (c) ô MIDI CC dùng giá trị **-1 = "không gán"** để tránh vô tình ghi đè nút built-in về CC 0 khi chỉ mở Sửa rồi Lưu.

---
*Các file liên quan: `frontend_qt.py:232-308` (shortcut + add/edit/hide), `ui/dialogs/widget_builder.py`, `ui/panels/{mixer,tools,mode}.py`, `core/config.py:364-417` (`UiConfigManager`).*
