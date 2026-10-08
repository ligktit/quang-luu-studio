# Quy trình đẩy & kiểm script Cubase lên máy khách qua UltraViewer (không cần đọc ảnh)

Đúc kết từ hai phiên 2026-10-07 (máy 1 DESKTOP-U46KFB8, máy 2 DESKTOP-826077C). Mục tiêu: một chuỗi lệnh chạy
liên tục từ WSL, mỗi bước tự xác nhận bằng **text** (OCR màn hình khách, kết quả PowerShell trả qua clipboard),
chỉ chụp ảnh để người xem khi có bất thường.

Công cụ: `tools/ultraviewer/cb.sh` (gọi `cb.py` bằng Python Windows trong `.venv`; cần `winrt-Windows.Media.Ocr`,
`winrt-Windows.Graphics.Imaging`, `winrt-Windows.Storage.Streams`, `winrt-Windows.Globalization` — đã cài 2026-10-07).

## 1. Ba nguyên tắc rút ra

1. **Chuột chỉ để mở cửa; việc thật đi qua clipboard.** Mọi đọc/ghi file, đọc log, đọc config, kiểm loopMIDI trên máy khách
   đều làm bằng PowerShell. Mở PowerShell một lần, dán *agent* vào; từ đó `cb.sh rpc "<code>"` gửi lệnh qua clipboard
   (UltraViewer đồng bộ hai chiều) và nhận kết quả về, không cần nhìn màn hình. Hộp Run cắt lệnh ở ~255 ký tự → không dùng.
2. **Bấm theo chữ, không theo toạ độ.** `cb.sh clickt "Reload Scripts"` OCR màn hình rồi bấm vào dòng chữ. Toạ độ tuyệt đối chỉ
   dùng cho nút không có chữ, và luôn tính **lệch so với một dòng chữ gần đó** (`--dx --dy`), vì vị trí thay đổi theo ngôn ngữ
   Windows (menu Win+X tiếng Việt cách dòng 40 px, tiếng Anh 32 px), theo máy và theo cửa sổ đang mở.
3. **Kiểm người đang dùng máy trước khi gửi bất kỳ thao tác nào.** `cb.sh quiet 20` so hai ảnh cách 20 s. Máy khách từng có
   người đang điều khiển máy thứ ba qua UltraViewer lồng (click của mình rơi sang máy thứ ba), và từng có mic đang hát.
   Khi `quiet` báo thay đổi ngoài vùng visualizer của app → dừng, báo người dùng.

## 2. Chuỗi lệnh chuẩn (đã chạy thật trên máy 3 DESKTOP-M21N7VP, 2026-10-07, ~6 phút kể cả kiểm)

```sh
T=tools/ultraviewer/cb.sh
# 0. Máy nào, gốc toạ độ, có rảnh không
$T who                      # tên máy khách + cảnh báo nếu cửa sổ UltraViewer chưa phóng to
$T calib                    # tự đo gốc ảnh khách trong cửa sổ UltraViewer (màn dev 2560 hay 4K đều được) -> calib.txt
$T quiet 20                 # "yen (chi visualizer/dong ho)" -> đi tiếp; "CO n cum thay doi la" -> dừng, báo người dùng

# 1. Mở PowerShell trên máy khách và thả agent (bước DUY NHẤT cần chuột "mù")
$T agent                                        # clipboard = lệnh agent
$T rclick 20 1057 && $T sleep 1                 # menu Win+X (góc dưới trái)
$T clickt "Windows PowerShell" --exact          # --exact để không trúng dòng "(Admin)/(Quản trị)"
$T sleep 3 && $T clickt "PS C:" --right --dx 300 && $T key enter    # chuột phải trong console = dán, Enter chạy agent
$T rpc "'pong ' + \$env:COMPUTERNAME"           # phải trả về "pong <tên máy>"

# 2. Khảo sát (không chuột)
$T info                                         # exe app, CC trong app_config, loopMIDI, script cũ (kích thước/ngày), Cubase, log
$T rpc "Get-Content ([Environment]::GetFolderPath('MyDocuments')+'\Steinberg\Cubase\MIDI Remote\Driver Scripts\Local\QuangLuu\QuangLuuMIDI\QuangLuu_QuangLuuMIDI.js') -Raw" > /tmp/tren_may.js
diff <(tr -d '\r' < /tmp/tren_may.js) <(git show HEAD:cubase/QuangLuu_QuangLuuMIDI.js) | head   # có phần người khác thêm -> gộp trước
$T wins                                         # tiêu đề các cửa sổ đang mở (Cubase Pro Project - ..., Quang Luu Studio, plugin...)

# 3. Ghi script (backup .bak)
$T deploy cubase/QuangLuu_QuangLuuMIDI.js       # "DA GHI <byte> -> <đường dẫn>" ; byte = kích thước local + 1

# 4. Reload + Script Console, tất cả theo chữ (Cubase 15)
$T win "Cubase Pro Project" max                 # phóng to để lower zone đủ chỗ (cuối buổi: win ... restore)
$T find "MixConsole" || { $T click 1861 61; }   # lower zone chưa mở thì bật (icon vùng dưới, góc phải thanh công cụ)
$T clickt "MIDI Remote" --near "MixConsole"
$T find "Scripting Tools" || { $T clickt "Last Touched Control" --right; $T clickt "Scripting Tools"; $T clickt "Set up Toolbar" --dx 180; }
$T find "Scripting Tools" || $T click 1811 61   # thanh vẫn chật -> tắt Left Zone (bật lại cuối buổi)
$T clickt "Scripting Tools" --dx -25 --dy 21    # icon Script Console (icon Reload = --dx -50)
$T clickt "Reload Scripts" && $T sleep 5
$T ocr 700 340 540 320 | grep -i "page active\|ho so plugin\|plugin Nhac\|nhom="   # script nạp, hồ sơ, SoundShifter, nhóm kênh

# 5. Kiểm chức năng bằng log (app lên trước bằng AppActivate, Cubase lên trước bằng win front)
L() { $T ocr 700 340 540 320 | grep -i "disp\[4\]\|disp\[2\]\|Tone Nhac\|155\|Bypass\|chua gan" | tail -4; }
$T activate "Quang L" && $T clickt "Tone Nhac" --dx -39 --dy 25 && $T win "Cubase Pro Project" front && $T sleep 1.5 && L   # nhac disp[4] -1, disp[2] <Key-1>
$T activate "Quang L" && $T clickt "Tone Nhac" --dx  39 --dy 25 && $T win "Cubase Pro Project" front && $T sleep 1.5 && L   # về 0
# Chữ "Bè" quá nhỏ, OCR không đọc; nút Bè nằm ngay dưới nút Auto-Tune (cùng cột, +29 px)
$T activate "Quang L" && $T clickt "Auto-Tune" --near "TOOLS" --dy 29 && $T win "Cubase Pro Project" front && $T sleep 2 && L   # disp[155] Off (Harmony Player bật)
$T activate "Quang L" && $T clickt "Auto-Tune" --near "TOOLS" --dy 29 && $T win "Cubase Pro Project" front && $T sleep 2 && L   # disp[155] On

# 6. Dọn
$T clickt "MIDI Remote Script Console" --dx 511   # nút X của console
$T win "Cubase Pro Project" restore
$T rpc "exit"                                   # tắt agent + đóng PowerShell
```

Khi `clickt` báo `KHONG THAY` → lúc đó mới `cb.sh shot` và xem ảnh. Nguyên nhân hay gặp: cửa sổ nổi của Cubase ẩn khi
Cubase mất focus (`win "Cubase Pro Project" front` trước), app Quang Lưu (luôn nổi) che, OCR đọc lệch chữ (đã có so khớp mờ:
"MIDl" = "MIDI", "Tone Miac" = "Tone Nhạc"; nếu vẫn hụt thì nới `--near` hoặc đổi sang chữ mốc khác).

## 3. Những điểm làm chậm lần trước — và cách tránh

| Mất thời gian vì | Làm thế này |
|---|---|
| Dán lệnh rồi mới biết chưa dán (clipboard chưa đồng bộ) | `sleep 2` sau khi đặt clipboard; dùng `rpc` (tự chờ kết quả, timeout báo rõ). |
| Hộp Run cắt 255 ký tự | Chỉ dùng console PowerShell; dán bằng chuột phải. |
| Click theo toạ độ trúng nhầm Chrome/YouTube vì icon taskbar dịch chỗ | `clickt` theo chữ; không click taskbar theo toạ độ. |
| Menu Win+X đóng trước khi click | Hai thao tác trong **một** tiến trình (`seq "rclick ..; click .."`) hoặc rclick rồi `clickt` ngay. |
| Cubase ẩn cửa sổ nổi khi app/PS được focus | Luôn `clickt "Cubase Pro Project"` trước khi đọc console/plugin. |
| Lật log console để tìm tham số | Không lật: OCR vùng log; muốn lọc theo tên tham số thì dùng bản chẩn đoán (chỉ log dòng khớp regex) hoặc nhớ `objectTitle` = tên plugin, `valueTitle` = tên tham số. Console tự cuộn xuống cuối khi còn dòng mới → đợi hết flood (~5 s) rồi mới cuộn. |
| Không biết app gửi CC nào | `info` đọc thẳng `app_config.json` cạnh exe (máy 1 từng bị đổi tone_music=55). |
| Hai phiên Claude cùng sửa một máy | `info` + diff script trước khi ghi đè; đọc chat/ghi chú khách để lại. |
| `rpc` thỉnh thoảng TIMEOUT một lần (clipboard bị UltraViewer/ứng dụng khác chen) | Gửi lại lệnh; agent vẫn sống (`rpc "'pong'"`). |
| Cửa sổ Cubase nhỏ, không có chỗ cho lower zone | `win "Cubase Pro Project" max` đầu buổi, `restore` cuối buổi (qua agent, không đụng chuột). |
| Taskbar/icon không có chữ để OCR | Không bấm taskbar: `activate "<tiêu đề>"` (AppActivate) hoặc `win <tiêu đề> front`. |

## 4. Đã kiểm / chưa kiểm

Đã chạy thật trọn chuỗi mục 2 trên máy 3 (DESKTOP-M21N7VP, Cubase 15, màn dev 4K): `calib`, `quiet`, mở PowerShell theo chữ,
`agent`/`rpc`/`info`/`deploy`, Reload qua MIDI Remote Manager và qua Script Console, bật Scripting Tools theo chữ, `win max/front`,
`activate`, OCR log. Chưa có: điều khiển khi UltraViewer thu nhỏ ảnh khách (màn dev nhỏ hơn 1920 hoặc khách > 1080p) — `calib` sẽ báo.
Số liệu nhỏ trên app (−1, +0) và trên GUI plugin OCR không đọc được → luôn kiểm bằng log console, không kiểm bằng GUI.

## 5. Gửi CC thẳng vào Cubase để thử script (bỏ qua app)

`cb.sh midi CC VAL [KENH]` gửi Control Change vào cổng QuangLuuMIDI từ chính máy khách (PowerShell + winmm qua agent).
Kênh mặc định 1 = kênh app gửi. Script dùng **kênh 2–3 cho CC giả** của tham số plugin ≥ 48 (tham số i → kênh `2 + (i−48)//100`
tính từ 1, CC `(i−48) % 100`), ví dụ tham số 186 = kênh 3, CC 38. Bài học 2026-10-08 (mất ~1 giờ): hàm gửi được biên dịch
một lần trong phiên agent (`Add-Type`), nếu nướng cứng kênh vào mã C# thì mọi lần gọi sau dùng kênh cũ → CC 35 rơi vào tham số 183,
CC 33 vào 181 "Scale Transpose", trông như "Cubase hỏng". Dấu hiệu nhận biết: log console chỉ hiện `disp[18x]` thay vì `disp[162]`.
Sau khi thử xong, trả lại các tham số đã chạm (`midi 33 64 3` đưa Scale Transpose về 0).

Khi "đổi Scale trên app mà Auto-Tune không đổi": (1) `rpc` đọc log app xem `Scale=... (cc=35, val=?)` — phải là 10/18 (tệp
`calibration_overrides.json` trong `%APPDATA%\QuangLuuStudio`, ghi **UTF-8 không BOM**, app chỉ đọc lúc khởi động); (2) `midi 35 18`
rồi `midi 35 10`, console phải hiện `disp[1]`, `disp[162]` Minor/Major; (3) GUI Auto-Tune: trên máy 3 ô Scale đi theo tham số 1
(bảng cổ điển), script từ 2026-10-08 ghi cả 1 lẫn 162.

`cb.sh midis CC V1 V2 [BƯỚC] [KÊNH]` quét một dải giá trị (250 ms/lần, một lệnh rpc) để đo bảng giá trị rời rạc của một tham số,
đọc `disp[i]` trên console theo từng khúc 16 giá trị (OCR chỉ thấy ~17 dòng cuối). Ví dụ đo bảng Scale cổ điển: `midis 81 0 15 1 1`.

Khi cần nhìn GUI plugin: mở bằng nút **e** cạnh tên insert trong Inspector (`clickt "Auto-Tune Pro"` trong vùng trái, hoặc toạ độ
nút e); **không** `clickt "Auto-Tune" --exact` toàn màn hình vì trúng dòng log console (`"Auto-Tune Pro"`), cú bấm kế tiếp rơi vào
cửa sổ Cubase (2026-10-08 đã mở nhầm hộp thoại Auto Fades, đã Cancel). Cửa sổ plugin che console → đọc log phải Escape đóng plugin
trước. Chụp ảnh ghi ra `C:\Users\<dev>\AppData\Local\Temp\qls_cb\*.png` (Python Windows không ghi được đường dẫn WSL).

Bài học chẩn đoán 2026-10-08 (Dân Ca → Dorian trên máy 3): giả thuyết "GUI theo bảng cổ điển vì bật Classic Mode (tham số 11)" sai —
tắt Classic (`midi 91 0`) GUI vẫn theo tham số 1 và danh sách Scale trên GUI vẫn chỉ 29 scale cổ điển. Trước khi viết logic đổi
chế độ DSP của khách, **mở dropdown trên GUI và nhìn danh sách** (1 cú click + 1 ảnh) rẻ hơn nhiều so với suy luận từ tham số host.
