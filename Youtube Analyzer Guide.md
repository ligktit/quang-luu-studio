# Hướng dẫn: Xây dựng chức năng phân tích bài hát từ YouTube

## Mô tả chức năng

Tạo một chức năng tự động phát hiện URL YouTube đang mở trên trình duyệt của người dùng (Windows), tải audio về, và phân tích bài hát để trả về: **Key** (giọng), **Scale** (Major/Minor), **Tempo** (BPM), và **Camelot** (ký hiệu DJ).

---

## Luồng xử lý chính

### Bước 1: Phát hiện YouTube URL từ trình duyệt

- Sử dụng Windows API (`ctypes`) gọi `EnumWindows` để liệt kê tất cả cửa sổ đang mở.
- Lọc cửa sổ có tiêu đề chứa tên trình duyệt phổ biến: `Google Chrome`, `Microsoft Edge`, `Mozilla Firefox`, `Brave`, `Opera`, `Vivaldi`.
- Với mỗi cửa sổ trình duyệt tìm thấy, sử dụng thư viện **`uiautomation`** (Python) để truy cập vào **EditControl** (thanh địa chỉ) và đọc giá trị URL thông qua `GetValuePattern()`.
- Kiểm tra URL có chứa `youtube.com` hoặc `youtu.be` không.

### Bước 2: Làm sạch URL

- Trích xuất Video ID (11 ký tự) bằng regex từ các dạng URL:
  - `youtube.com/watch?v=VIDEO_ID`
  - `youtu.be/VIDEO_ID`
  - `youtube.com/embed/VIDEO_ID`
  - `youtube.com/shorts/VIDEO_ID`
- Xây dựng lại URL sạch: `https://www.youtube.com/watch?v=VIDEO_ID` (bỏ hết các tham số playlist `list=`, `start_radio=`, v.v.) để tránh tải cả playlist.

### Bước 3: Tải audio từ YouTube

- Sử dụng thư viện **`yt-dlp`** (Python) với các tùy chọn:
  - `format`: `bestaudio/best` — chọn chất lượng audio cao nhất
  - `noplaylist`: `True` — chỉ tải 1 video, không tải playlist
  - Nếu có **ffmpeg** trên hệ thống: dùng postprocessor `FFmpegExtractAudio` để chuyển sang `.wav`
  - Nếu không có ffmpeg: tải nguyên định dạng gốc (`.m4a` hoặc `.webm`), librosa vẫn đọc được
- Lưu file audio vào thư mục tạm (`tempfile.TemporaryDirectory`), tự xóa sau khi dùng xong.
- Dùng `static_ffmpeg` (thư viện Python) để cung cấp ffmpeg binary tự động nếu hệ thống chưa cài.

### Bước 4: Phân tích Key, Scale, BPM

Sử dụng thư viện **`librosa`** (Python) để phân tích toàn bộ file audio:

#### 4a. Phát hiện Key & Scale

- Load audio bằng `librosa.load(filepath, sr=22050, mono=True)`.
- Tính **chroma features**: `librosa.feature.chroma_cqt(y, sr, hop_length=512)`.
- Lấy trung bình chroma trên toàn bộ bài (vector 12 phần tử, mỗi phần tử đại diện 1 nốt: C, C#, D, ..., B).
- Với mỗi nốt (0-11), xoay (roll) vector chroma rồi tính **correlation** (hệ số tương quan Pearson) với 2 profile chuẩn **Krumhansl-Kessler**:
  - Major profile: `[6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]`
  - Minor profile: `[6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]`
- Chọn nốt + scale (Major/Minor) có correlation cao nhất.
- Ánh xạ sang tên nốt đúng chuẩn nhạc lý:
  - Major: `["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]`
  - Minor: `["C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B"]`
- **Confidence** = giá trị correlation cao nhất (0.0 - 1.0).

#### 4b. Phát hiện Tempo (BPM)

- Dùng `librosa.beat.tempo(y, sr)` để ước tính số nhịp mỗi phút (BPM).

#### 4c. Camelot Wheel (cho DJ)

- Chuyển Key + Scale sang ký hiệu Camelot:
  - Major: `["8B", "3B", "10B", "5B", "12B", "7B", "2B", "9B", "4B", "11B", "6B", "1B"]`
  - Minor: `["5A", "12A", "7A", "2A", "9A", "4A", "11A", "6A", "1A", "8A", "3A", "10A"]`

### Bước 5: Trả về kết quả

Trả về một object/dict chứa:

```
{
    "key": "Eb",              // Giọng (VD: C, Db, F#, ...)
    "scale": "Minor",         // Thang âm (Major hoặc Minor)
    "bpm": 128.0,             // Nhịp mỗi phút
    "confidence": 0.734,      // Độ tin cậy (0.0 - 1.0)
    "duration": 225.0,        // Thời lượng (giây)
    "camelot": "2A"           // Ký hiệu Camelot Wheel
}
```

---

## Thư viện cần thiết

| Thư viện        | Cài đặt                      | Vai trò                                               |
| --------------- | ---------------------------- | ----------------------------------------------------- |
| `uiautomation`  | `pip install uiautomation`   | Đọc thanh địa chỉ trình duyệt (Windows UI Automation) |
| `yt-dlp`        | `pip install yt-dlp`         | Tải audio từ YouTube                                  |
| `librosa`       | `pip install librosa`        | Phân tích âm nhạc (chroma, tempo)                     |
| `numpy`         | `pip install numpy`          | Tính toán vector, correlation                         |
| `static_ffmpeg` | `pip install static_ffmpeg`  | Tự cung cấp ffmpeg nếu chưa cài                       |
| `ffmpeg`        | `winget install Gyan.FFmpeg` | Chuyển đổi audio (khuyến nghị cài hệ thống)           |

---

## Lưu ý quan trọng

1. **Chỉ chạy trên Windows** — vì sử dụng `ctypes.windll` và Windows UI Automation.
2. **Trình duyệt phải đang mở YouTube** — script đọc URL từ cửa sổ đang hiển thị.
3. **URL playlist sẽ bị bỏ params** — chỉ giữ lại video ID để tải đúng 1 bài.
4. **Phân tích toàn bài** (không phân tích real-time) nên kết quả chính xác hơn so với phân tích real-time từ audio capture.
5. **Confidence < 50%** nghĩa là kết quả key không đáng tin (bài có nhiều chuyển giọng hoặc không có giai điệu rõ ràng).
