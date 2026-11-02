# Spike: hiện riêng cửa sổ plugin khi cửa sổ DAW chính đang ẩn — kết quả

Ngày: 2026-11-02 · Máy: máy dev (Cubase Pro 13.0.10, bài `D:\QLS\mau.cpr`, plugin Pitch Correct
ở insert 1 kênh Mic). **Máy dev không có Studio One** — phần Studio One chưa đo, xem cuối.

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
- `show_all()` **bỏ qua cửa sổ rác** (sửa lỗi trên). `hide_all()` giữ nguyên (ẩn mọi thứ đang hiện).
- `list_windows()` bỏ cửa sổ rác **và** cửa sổ kích thước 0 (`SmtgMain`). Không ai cần bật/tắt
  riêng cửa sổ đó, nhưng `show_all()` vẫn hiện lại nó như cũ.

## Studio One — chưa đo

Máy dev không cài Studio One. Code dùng chung cách 1 cho cả hai DAW. Nếu cửa sổ plugin của
Studio One là cửa sổ owned của cửa sổ chính và không hiện được riêng, triệu chứng sẽ là: gạt công
tắc plugin, công tắc bật lại tắt sau khi quét lại (`IsWindowVisible` vẫn False), và plugin không lên
màn hình. Cần đo trên máy khách Studio One (máy 1/máy 2) trước khi phát hành, bằng chính danh sách
trong Cài đặt của bản build mới.
