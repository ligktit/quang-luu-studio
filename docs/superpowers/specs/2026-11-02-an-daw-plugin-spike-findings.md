# Spike: hiện riêng cửa sổ plugin khi cửa sổ DAW chính đang ẩn — kết quả

Ngày: 2026-11-02 · Máy: máy dev (Cubase Pro 13.0.10, bài `D:\QLS\mau.cpr`, plugin Pitch Correct
ở insert 1 kênh Mic) và máy 1 khách (Studio One 5.0.2) — xem cuối.

## Cubase 13 — cách 1 chạy được, không cần dự phòng

Cửa sổ của tiến trình `Cubase13.exe` lúc mở bài, có Channel Settings và cửa sổ plugin đang mở:

| HWND (ví dụ) | Lớp | Tiêu đề | Owner | Hiện lúc đầu | Ghi chú |
|---|---|---|---|---|---|
| 1510476 | `SteinbergWindowClass…` | `Cubase Pro Project - mau` | 0 | có | cửa sổ chính (`main_windows`) |
| 4918398 | `SteinbergWindowClass…` | `Mic: Ins. 1 - Pitch Correct` | **0** | có | plugin, `WS_EX_TOOLWINDOW` |
| 6228888 | `SteinbergWindowClass…` | `Channel Settings : Mic [mono->stereo]` | 0 | có | |
| 1051214 | `SmtgMain Cubase13` | `Cubase Pro` | 0 | có | cửa sổ ứng dụng, rect 0×0 (dùng để quit) |
| 2031902 | `USB Change Listener` | `USB Change Listener` | 0 | **không** | nội bộ |
| 592122 | `SteinbergDevWnd` | *(rỗng)* | 0 | **không** | nội bộ |
| 3214474 / 1575138 | `IME` / `MSCTFIME UI` | `Default IME` / `MSCTFIME UI` | có | **không** | bộ gõ |
| (tạm) | `SteinbergWindowClass…` | *(rỗng)* | 0 | — | tooltip, sống vài giây |

Thử:
1. `hide_all()` → ẩn 4 cửa sổ (project, plugin, Channel Settings, SmtgMain).
2. `ShowWindow(plugin, SW_SHOW)` + `force_foreground` → **chỉ plugin hiện**, cửa sổ project vẫn ẩn.
   Plugin vẽ đầy đủ, **nhận chuột** (bấm Scale Source mở được menu) và nhận phím (Esc đóng menu).
   Plugin là `WS_EX_TOOLWINDOW` nên không lên thanh tác vụ.
3. `SW_HIDE` riêng plugin → ẩn lại, không còn cửa sổ nào hiện.
4. `show_all()` → hiện lại tất cả, Cubase dùng bình thường.

Kết luận: cửa sổ plugin của Cubase **không thuộc (owner=0)** cửa sổ project → cách 1
(`SW_SHOW` riêng HWND) chạy được. **Không làm Task 8** cho Cubase.

## Lỗi phát hiện thêm: `show_all()` hiện cả cửa sổ nội bộ

`show_all()` hiện **mọi** cửa sổ đang ẩn của tiến trình, kể cả những cửa sổ vốn ẩn từ đầu:
`USB Change Listener`, `SteinbergDevWnd`, `IME`, `MSCTFIME UI`, tooltip. Có từ trước (nút mắt
cũng vậy). `USB Change Listener` là một ô 136×39 ở góc trái trên màn hình.

HWND tooltip đã chết chỉ vài giây sau khi quét → đúng ca "HWND chết giữa lúc quét và lúc
bấm" (Review Focus 3).

## Quy tắc lọc chốt cho Task 6

- **Cửa sổ rác** (`_is_internal(hwnd)`): tiêu đề rỗng, hoặc lớp thuộc
  `INTERNAL_WINDOW_CLASSES = ("IME", "MSCTFIME UI", "USB Change Listener", "SteinbergDevWnd")`.
- `show_all()` **bỏ qua cửa sổ rác** (sửa lỗi trên), và nay chỉ hiện lại cửa sổ app đã ẩn (+ cửa sổ chính).
  `hide_all()` giữ nguyên (ẩn mọi thứ đang hiện). Thêm tiêu đề rác `JUCEWindow` (đo trên Studio One).
- `list_windows()` bỏ cửa sổ rác **và** cửa sổ kích thước 0 (`SmtgMain`). Không ai cần bật/tắt
  riêng cửa sổ đó, nhưng `show_all()` vẫn hiện lại nó như cũ.

## Studio One 5 — đo trên máy 1 (DESKTOP-U46KFB8, 2026-11-02/03), cách 1 chạy được

Bài `F:\vp.song`, app build từ nhánh. Cửa sổ tiến trình `Studio One.exe`:

| Lớp | Tiêu đề | Owner | Ghi chú |
|---|---|---|---|
| `CCLWindowClass` | `Studio One - vp` | 0 | cửa sổ chính |
| `CCLShadowWindowClass` | `MIC KG · Inserts · 7 - Auto-Tune Pro 3` | **cửa sổ chính** | plugin — chỉ tồn tại khi đã mở |
| `ASIOLINKCLASS…` | `O Deus ASIO Link Pro 2.4.2.0 - Studio One.exe` | 0 | bảng driver ASIO Link Pro, tạo sẵn ở trạng thái ẩn, **chưa từng mở** |
| `JUCE_…` | `JUCEWindow` | 0 | cửa sổ ngầm 133×38 của plugin JUCE |

- Plugin của Studio One **là cửa sổ owned** của cửa sổ chính, nhưng `SW_SHOW` riêng nó khi cửa sổ chính
  đang ẩn vẫn hiện đúng, vẽ đủ, nhận chuột (mở danh sách Key). Ẩn lại được. → **không cần Task 8**.
- Bài mẫu lúc mở **không có cửa sổ plugin nào**: Studio One không giữ cửa sổ plugin khi nạp bài (hoặc bài lưu
  lúc plugin đã đóng). KTV phải hiện Studio One → mở plugin → ẩn tất cả → bật riêng plugin. Bấm ✕ của plugin
  là **huỷ** cửa sổ (phải mở lại từ Studio One).
- Bảng ASIO Link Pro chưa từng mở thì `SW_SHOW` chỉ ra khung trắng (không có cửa sổ con, tự vẽ) — app không
  mở thay được bảng driver. `show_all` giờ chỉ hiện lại cửa sổ app đã ẩn (+ cửa sổ chính) nên không bật nó.
- Tiêu đề bảng ASIO Link có chữ "Studio One" → trước đây bị nhận là **cửa sổ chính** (cả luồng đóng an toàn).
  `title_is_main` nay đòi tiêu đề **bắt đầu** bằng tên DAW.
- App **ghim trên cùng**: plugin bật từ danh sách nổi trên app (giữ TOPMOST tới khi ẩn). Plugin TOPMOST che
  luôn công tắc trong Cài đặt — kéo plugin sang bên hoặc ẩn bằng "Ẩn Studio One + plugin".
- Vòng bám ẩn 60 s sau khi DAW mở không ẩn lại cửa sổ KTV vừa bật (kiểm: hiện lúc 23:49:47, vẫn hiện lúc 23:55).
- Chuyển cấu hình: `tech_lock` (enabled=false) → `daw_windows {auto_hide: true, restore_template: false}`, `tech_lock` bị xoá.

Exe thử nghiệm đang chạy trên máy 1: `current\QuangLuuStudio.exe` sha CC1D4BE9…; bản gốc (2 mic, c474db9e) và
`settings.json` gốc sao lưu ở `C:\Users\caoqu\QLS_SaoLuu_andaw_20261102`.
