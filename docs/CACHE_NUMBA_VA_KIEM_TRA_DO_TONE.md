# Cache numba hỏng làm chết dò tone — và bộ tự kiểm tra trên máy khách

## 1. Triệu chứng

Người dùng bấm Dò Tone, app báo:

> Đã tải được audio nhưng phân tích âm điệu bị lỗi. Vui lòng thử lại sau giây lát.

Thử lại bao nhiêu lần cũng y hệt. Trong `errors.log` là cùng một vết, lặp lại:

```
[DÒ TONE/phân tích audio] invalid load key, '\x00'.
  core\engine\_tone.py  librosa.load(...)
  librosa\util\utils.py:2436   (hàm @vectorize(cache=True))
  numba\core\caching.py:588 _load_index
_pickle.UnpicklingError: invalid load key, '\x00'.
```

Nhật ký ngày 15/09/2026 có 22 lần như vậy trong 8 phút.

## 2. Nguyên nhân

librosa dùng numba với `cache=True`. Lần chạy đầu, numba biên dịch vài hàm rồi
ghi ra đĩa: `.nbi` là mục lục, `.nbc` là mã máy. Nếu máy tắt ngang, mất điện, ổ
đầy hoặc phần mềm diệt virus chen vào đúng lúc đang ghi thì file mục lục còn lại
toàn byte `0x00`.

numba **không tự chữa**: lần sau nó đọc lại file hỏng rồi ném lỗi. Lỗi bật ra
ngay lúc nạp `librosa.util.utils`, tức TRƯỚC khi chạm tới audio — nên không phải
lỗi của bài hát, của mạng hay của YouTube, và đổi bài cũng không cứu được.

## 3. App tự chữa thế nào (từ 1.7.8)

`core/numba_cache.py`, ba lớp:

1. **Cache để riêng** — `activate_private_cache()` đặt `NUMBA_CACHE_DIR` về
   `%APPDATA%\QuangLuuStudio\numba_cache`. Thư mục cài có thể chỉ đọc, còn cache
   chung `%LOCALAPPDATA%\numba` thì app không nên đụng vào; cache riêng là thứ
   app có toàn quyền xoá. Gọi trong `main.py`, TRƯỚC lần nạp numba đầu tiên.
2. **Quét dọn lúc mở app** — `sweep_corrupt()` chạy nền, đọc vài file mục lục
   nhỏ (không nạp numba/librosa nên gần như không tốn gì) và xoá riêng file
   hỏng, giữ phần cache còn lành.
3. **Chữa tại chỗ** — `run_healing()` bọc lời gọi librosa ĐẦU TIÊN của mỗi luồng
   phân tích (`librosa.load` / `librosa.resample`, đúng chỗ numba đọc cache).
   Gặp lỗi cache hỏng thì xoá cache rồi gọi lại **một lần**. Người dùng chỉ thấy
   lần dò tone đó chậm hơn mươi giây, thay vì hỏng vĩnh viễn.

Lỗi thường (video bị chặn, mất mạng…) **không** làm xoá cache — nếu không, mỗi
lần dò tone hụt là một lần bắt máy khách ngồi chờ biên dịch lại.

Cố ý KHÔNG nạp sẵn `librosa.util.utils` lúc khởi động để bắt lỗi sớm: làm vậy là
kéo cả numba/llvmlite vào bộ nhớ ngay từ đầu, trong khi librosa vốn nạp lười.

## 4. Kiểm tra trên máy khách (không cần cài Python)

Máy khách không có Python, nhưng file exe thì có sẵn Python bên trong:

```
kiem_tra_tone.bat              (Start Menu → "Quang Lưu Studio - Kiểm tra dò tone")
kiem_tra_tone.bat --day-du     (nạp thêm librosa THẬT — chậm hơn, kiểm tận gốc)
```

Tương đương: `QuangLuuStudio.exe --tu-kiem-tra [--day-du]`.

8 phép thử mặc định chạy vài giây và dùng **librosa giả** — không nạp librosa
thật, không bắt numba biên dịch. Phép thử số 8 soi cache THẬT trên máy đó: tìm
thấy file hỏng thì xoá luôn, tức là vừa kiểm vừa chữa. Báo cáo in ra màn hình và
lưu tại `%APPDATA%\QuangLuuStudio\logs\tu_kiem_tra.txt` — bảo khách gửi file này
khi có phép thử HỎNG.

Mã thoát: `0` = tất cả đạt, `1` = có phép hỏng.

## 5. Chữa tay (bản cũ, chưa có cơ chế trên)

Tắt app, xoá `%LOCALAPPDATA%\numba\Cache`, mở lại. Lần dò tone đầu tiên sẽ chậm
hơn mươi giây vì numba biên dịch lại.

## 6. Mã nguồn liên quan

| File | Vai trò |
|------|---------|
| `core/numba_cache.py` | Cache riêng, quét dọn, chữa tại chỗ |
| `core/self_check.py` | Bộ tự kiểm tra chạy trong exe (`--tu-kiem-tra`) |
| `kiem_tra_tone.bat` | Lối chạy cho máy khách, cài kèm theo bộ cài |
| `tests/core/test_numba_cache.py` | Bản pytest của chính các phép thử đó |

Mọi test đều dùng librosa giả: nạp librosa thật trong pytest làm abort cả phiên
chạy (numba/llvmlite).
