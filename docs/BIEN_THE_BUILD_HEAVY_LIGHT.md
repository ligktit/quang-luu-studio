# Phân biệt bản NẶNG (Heavy) và bản NHẸ (Light) — cảnh báo

> Cập nhật 26/08/2026. Liên quan: `core/capabilities.py`,
> `core/updater/_version_check.py`, `tools/chan_doan/QLS_ChanDoan.ps1`.

Bản Heavy có bundle QtWebEngine (màn hình karaoke nhúng), bản Light thì không
(nhẹ hơn ~80 MB). Cùng một mã nguồn, khác nhau ở env `QLS_WEBENGINE=1` lúc build.

---

## ⚠️ Cảnh báo 1 — Build là ONEFILE: cạnh exe KHÔNG có DLL nào

`QuangLuuStudio.spec` dựng theo kiểu **onefile** (`EXE(...)` ôm luôn
`a.binaries` + `a.datas`, không có `COLLECT`). Mọi DLL nằm **bên trong** file
exe, lúc chạy mới giải nén ra `%TEMP%\_MEIxxxxxx`.

Hệ quả: **đừng bao giờ kiểm tra "có `Qt6WebEngineCore.dll` cạnh exe không"** —
thư mục cài đặt chỉ có đúng mỗi `QuangLuuStudio.exe`, nên phép kiểm đó báo THIẾU
kể cả với bản Heavy hoàn toàn lành lặn. Đây là một chẩn đoán sai đã thực sự xảy
ra và làm mất thời gian của cả khách lẫn hỗ trợ.

## ⚠️ Cảnh báo 2 — Đừng đoán biến thể theo kích thước exe

Đo ngày 26/08/2026:

| Bản | Kích thước exe |
|---|---|
| Light | **310 MB** |
| Heavy | **390 MB** |

`tools/chan_doan/QLS_ChanDoan.ps1` trước đây dùng ngưỡng `> 300MB → Heavy`, tức
**gọi nhầm bản Light thành Heavy**. Bản Light chỉ nhẹ hơn ~80 MB chứ không hề
nhỏ, và khoảng cách này còn co lại theo từng bản phát hành.

### Cách đúng: dò tên file trong bảng mục lục của gói

Bảng mục lục PyInstaller ghi tên file ở dạng chữ thường ngay trong exe. Quét
tuần tự tìm chuỗi `Qt6WebEngineCore.dll` — chỉ bản Heavy mới có. Đã kiểm trên cả
hai bản build thật, đúng cả hai, mất ~2 giây mỗi exe.

**Đừng dùng `QtWebEngineProcess.exe` làm dấu hiệu** — chuỗi đó có mặt trong **cả
hai** bản (đo được), nhận nhầm ngay.

## ⚠️ Cảnh báo 3 — "Bản Light" và "bản Heavy nạp hỏng" là hai ca khác nhau

Cả hai đều cho `capabilities.embedded_player_available() == False`, và ô "Màn
hình karaoke nhúng" trong Thiết lập đều mờ đi y hệt nhau. Nhưng:

| Ca | Chữa |
|---|---|
| Bản Light | Cài bộ cài có chữ `heavy` trong tên |
| Bản Heavy mà nạp QtWebEngine hỏng | Cài lại bản Heavy **vô ích** nếu chưa loại trừ thư mục cài đặt **và `%TEMP%`** khỏi phần mềm diệt virus |

Vì onefile giải nén ra `%TEMP%\_MEIxxxxxx`, phần mềm diệt virus cách ly file
**ở đó** cũng đủ làm hỏng, dù thư mục cài đặt sạch.

`core/capabilities.py` giữ lại thông điệp lỗi để tách hai ca:

```python
capabilities.embedded_player_available()   # True/False
capabilities.embedded_player_error()       # "" hoặc "ImportError: DLL load failed..."
capabilities.build_variant()               # "Heavy" / "Light"
capabilities.describe()                    # một dòng cho log
```

`ModuleNotFoundError: No module named 'PySide6.QtWebEngineWidgets'` = bản Light
đúng thiết kế. Bất kỳ lỗi nào khác = bản Heavy hỏng.

`main.py` ghi `describe()` vào `logs/app.log` lúc khởi động, nên nhật ký của
khách tự nói ra ngay. Script chẩn đoán đọc lại đúng dòng đó và đối chiếu với kết
quả quét exe.

### Phải bắt `Exception`, không chỉ `ImportError`

QtWebEngine hỏng trên máy khách có thể ném `OSError` (DLL bị chặn) hay
`RuntimeError` (xung đột phiên bản Qt). Chỉ bắt `ImportError` là để lọt ngoại lệ
ra ngoài — mà `ui/dialogs/settings_dialog.py::_build_karaoke_widgets()` gọi
`from core import capabilities` **không bọc try**, nên nó dựng luôn cả dialog
Thiết lập.

---

## ⚠️ Cảnh báo 4 — Nhận nhầm biến thể làm khách bị hạ cấp vĩnh viễn

`core/updater/_version_check.py` dùng `embedded_player_available()` để chọn file
cài lúc tự cập nhật: Heavy → lấy asset có `heavy` trong tên, không thì lấy asset
Light.

Một máy Heavy nhận nhầm là Light sẽ **tự tải bản Light về cài đè** ở lần cập
nhật kế, và từ đó mất hẳn màn hình karaoke nhúng. Đây là lý do phát hiện sai
biến thể không phải chuyện nhỏ về hiển thị.

---

## ⚠️ Cảnh báo 5 — "Trong log không thấy báo lỗi" KHÔNG phải bằng chứng

Dòng `Biến thể build: ...` chỉ có từ bản 1.7.5. Trên máy khách chạy bản cũ hơn,
nhật ký **không hề có** dòng nào nói về QtWebEngine — kể cả khi nạp hỏng thật.
Và không có lời nhắc nào khác lộ ra biến thể: mọi câu `[PLAYER] ...` chỉ chạy
khi người dùng đã bật màn hình nhúng, mà bản Light thì không bật được.

Nên trên bản cũ, "log sạch" chỉ có nghĩa là không biết gì cả.

### Cách kiểm không cần cập nhật app

`tools/chan_doan/KiemTraManHinhNhung.bat` (+ `.ps1`) — chỉ đọc, không sửa gì, gửi
thẳng cho khách được. Thư mục `tools/chan_doan/` **không** nằm trong bộ cài
(`QuangLuuStudio_Setup.iss` không chép nó), nên đây là công cụ rời: gửi file mới
là dùng được ngay, không đụng tới app đang cài.

Nó ghép hai dấu hiệu:

| Trong gói có `Qt6WebEngineCore.dll`? | `%TEMP%\_MEI*` có file đó? | Kết luận |
|---|---|---|
| Không | — | Bản **Light**, ô mờ là đúng thiết kế |
| Có | Có | Bản **Heavy** bình thường |
| Có | Không (mà có bung `PySide6`) | Bản **Heavy bị diệt virus cách ly** |
| Có | Chưa bung gì | Chưa đủ dữ kiện — mở app lên rồi chạy lại |

Bước `%TEMP%` là chỗ duy nhất tách được ca thứ ba, nên phải **mở app rồi để
nguyên đó** lúc chạy công cụ.

Đã chạy thử trên cả hai bản build thật: `dist/` (310 MB) → "ban NHE", `dist_heavy/`
(390 MB) → "ban NANG".

### Không được tin thư mục `_MEI` bắt được ngoài đường

`%TEMP%\_MEIxxxxxx` **không tự xoá** khi app tắt đột ngột. Quét bừa `%TEMP%` rồi
vớ phải một thư mục cũ là báo "bình thường" oan — đúng kiểu sai đã xảy ra.

Cách đúng: đọc `Process.Modules` của tiến trình `QuangLuuStudio` đang chạy, lấy
thư mục `_MEI` từ đường dẫn module đã nạp. Đó là thư mục của **chính lần chạy
này**. Chỉ khi không bám được vào tiến trình mới lùi về quét `%TEMP%`, và phải
nói rõ ra là kết quả kém tin cậy.

Cũng vì lý do đó, exe đem đi quét phải lấy từ `Process.Path` chứ không phải từ
Program Files: shortcut có thể trỏ tới một bản cài khác hẳn. Công cụ so hai
đường dẫn và cảnh báo khi lệch.

### Thiếu `.pyd` thì DLL còn nguyên cũng vô dụng

`Qt6WebEngineCore.dll` có mặt **không** đủ để Python `import` được. Còn cần
`QtWebEngineWidgets.pyd` và `QtWebEngineCore.pyd`. Công cụ kiểm cả ba, vì thiếu
mỗi `.pyd` là ca "file DLL đủ mà ô vẫn mờ" — nhìn bằng mắt không ra.

### Hai bẫy PowerShell gặp khi viết công cụ này

**1. Biến không phân biệt hoa thường.** Khai `param([string]$Exe)` rồi bên dưới
viết `$exe = $null` là **xoá luôn tham số truyền vào** — script báo "không tìm
thấy exe" dù người dùng đã chỉ đúng đường dẫn. Đặt tên biến cục bộ khác hẳn.

**2. File `.ps1` có chữ tiếng Việt PHẢI có BOM UTF-8.** PowerShell 5.1 đọc file
`.ps1` không BOM theo bảng mã ANSI (Windows-1252). Dấu gạch ngang dài `—` (UTF-8
= `E2 80 94`) khi đó thành ba ký tự, mà `0x94` trong cp1252 là dấu nháy kép cong
`”` — **PowerShell nhận nó là dấu mở/đóng chuỗi**. Kết quả: `The string is
missing the terminator` ở tận cuối file, trỏ vào chỗ chẳng liên quan gì. Rất mất
thời gian truy.

Đã rà toàn bộ `*.ps1`: `tools/_remove_cdp.ps1` cũng dính (có `—`, không BOM) —
đã thêm BOM. Các file `QLS_*.ps1` vốn đã có BOM nên không sao.

---

## Chuyển Light → Heavy: không mất gì

`QuangLuuStudio_Setup.iss` dùng **cùng `AppId`** cho cả hai biến thể (chỉ khác
`OutputBaseFilename` qua `VariantSuffix`) và cùng `DefaultDirName`. Nên chạy bộ
cài Heavy đè lên bản Light là **nâng cấp tại chỗ**: không cần gỡ trước, không
tạo bản thứ hai.

Dữ liệu khách nằm ngoài thư mục cài đặt (`%APPDATA%\QuangLuuStudio` và
`Documents\QuangLuuStudio`), còn `app_config.json` gắn cờ `onlyifdoesntexist`.
Không mất thiết lập, danh sách bài, hay kích hoạt.

**Nhưng app sẽ không bao giờ tự đề xuất.** `core/updater/_version_check.py` chọn
asset theo đúng biến thể hiện tại, nên máy Light chỉ được mời bản Light. Phải gửi
file `Setup_QuangLuuStudio_heavy_v*.exe` thủ công.

Không có cách "bổ sung vài file cho nhẹ" — build là onefile, muốn thêm
QtWebEngine phải đóng gói lại cả exe. (Về lâu dài có thể tách QtWebEngine thành
gói phụ tải lúc chạy như `core/pot_provider.py`, khi đó chỉ tốn ~80 MB — nhưng
chưa khảo sát, và rủi ro khớp phiên bản Qt không nhỏ.)

---

## Kiểm tra tự động

`tests/core/test_capabilities.py` — bốn ca: bản Light, bản Heavy hỏng DLL, ngoại
lệ không phải `ImportError`, và ca nạp được bình thường.
