# 🛠️ TÀI LIỆU CHI TIẾT CẢI ĐẶT UX/UI: QUANG LƯU STUDIO (V2.0)

## 1. TỔNG QUAN PHONG CÁCH (STYLE GUIDE)
Ứng dụng được định hướng theo phong cách **Professional Studio Dark Mode**, sử dụng hiệu ứng **Glassmorphism** (kính mờ) để tạo chiều sâu và vẻ hiện đại.

### 🎨 Bảng màu (Color Palette)
| Thành phần | Mã Màu (HEX) | Vai trò |
| :--- | :--- | :--- |
| **Background** | `#0F172A` | Nền chính toàn bộ ứng dụng (Deep Navy). |
| **Panel Surface** | `#1E293B` | Nền các khối chức năng (Độ mờ 85%, Blur 10px). |
| **Primary Accent** | `#38BDF8` | Màu cho các nút điều khiển chính (Sky Blue). |
| **Creative Accent**| `#A855F7` | Màu cho các chế độ hát/hiệu ứng (Vivid Purple). |
| **Recording/Alert**| `#EF4444` | Màu nút Record và cảnh báo (Critical Red). |
| **Success Status** | `#10B981` | Màu trạng thái kết nối thành công (Emerald). |
| **Text Primary** | `#F8FAFC` | Chữ chính (Off-white), chống mỏi mắt. |
| **Text Secondary** | `#94A3B8` | Chữ phụ, nhãn chú thích (Slate Gray). |

### 🔡 Phông chữ (Typography)
- **Font Family:** `Be Vietnam Pro`, Sans-serif.
- **Tiêu đề khối:** 18px, Bold, Uppercase nhẹ, Tracking (giãn chữ) +1px.
- **Nhãn nút/Slider:** 14px, Medium.
- **Số liệu (Chỉ số):** 16px, Semi-bold, Font dạng Mono (để số không bị nhảy khi thay đổi).

---

## 📐 2. QUY ĐỊNH KÍCH THƯỚC VÀ BỐ CỤC (LAYOUT SPECS)

### Cấu trúc chung:
- **Border Radius (Bo góc):** Đồng nhất toàn bộ là **12px**.
- **Padding/Margin:** Khoảng cách giữa các khối tối thiểu là **20px**.
- **Giao diện:** Loại bỏ Sidebar, mở rộng không gian cho Mixer và Soundboard.

### Chi tiết từng khối:
1. **Header (60px height):**
   - Logo bên trái.
   - Trạng thái kết nối bên phải (Icon tròn 8px + Text).
2. **Khối Tone & Adjust (30% chiều rộng):**
   - Nút bấm: Cao 40px, Rộng 100%.
   - Nút `+` / `-`: Hình tròn, đường kính 36px.
3. **Khối Mixer Tổng (40% chiều rộng - Trung tâm):**
   - Khoảng cách giữa các thanh trượt: 40px.
   - Track (Thanh chạy): Rộng 6px, bo tròn 2 đầu.
   - Thumb (Nút kéo): Đường kính 20px, có đổ bóng Glow nhẹ cùng màu.
4. **Khối Soundboard & Chế độ (30% chiều rộng):**
   - Dạng Grid 2 cột. Chiều cao nút cố định 60px.

---

## ✨ 3. CHI TIẾT TRẠNG THÁI TƯƠNG TÁC (STATES)

### 🖱️ Nút bấm (Buttons)
- **Normal:** Nền `Surface Color`, Border 1px màu `#334155`.
- **Hover:** Độ sáng tăng 15%, Border chuyển sang màu `Primary Accent`. Con trỏ: `pointer`.
- **Active (Click):** Scale (thu nhỏ) về `0.96`, đổ bóng `Box-shadow: 0 0 15px [Màu nút]`.

### 🎚️ Thanh trượt (Mixer Sliders)
- **Normal:** Thumb màu đặc (Vd: Mic - Cam, Vol - Xanh).
- **Hover:** Thumb mở rộng lên 24px, hiển thị Tooltip giá trị dB phía trên đầu ngón tay kéo.
- **Active:** Track phía dưới Thumb sáng rực màu Neon tương ứng.

### 🔴 Nút Record (Trọng tâm)
- **Normal:** Màu đỏ phẳng, biểu tượng tròn trắng ở giữa.
- **Recording State:** - Đổi biểu tượng sang Hình vuông (Stop).
  - Hiệu ứng **Pulse Animation**: Viền đỏ lan tỏa rộng dần ra rồi mờ đi (chu kỳ 2s).
  - Hiệu ứng **Glow**: Luôn phát sáng nhẹ màu đỏ xung quanh nút.

---

## 🛠️ 4. QUY TRÌNH TRIỂN KHAI (IMPLEMENTATION)

1. **Bước 1:** Thiết lập biến CSS (CSS Variables) dựa trên bảng mã màu trên.
2. **Bước 2:** Xây dựng khung Layout với `Flexbox` hoặc `CSS Grid` (Bỏ Sidebar).
3. **Bước 3:** Tạo linh kiện (Components) cho Button và Slider với đầy đủ các trạng thái Hover/Active.
4. **Bước 4:** Tích hợp logic xử lý Peak Meter (đèn nháy theo nhạc) vào các thanh Mixer.
5. **Bước 5:** Tối ưu hóa phản hồi xúc giác (Visual Feedback) khi người dùng nhấn Record hoặc các phím Soundboard.

---