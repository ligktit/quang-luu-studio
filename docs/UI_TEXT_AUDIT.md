# Rà soát chữ hiển thị cho người dùng — tooltip & thông báo

**Ngày:** 24/08/2026 · **Phạm vi quét:** `frontend_qt.py`, `ui/**`, `core/accessibility/**`
**Trạng thái: ĐÃ ÁP DỤNG toàn bộ đợt 1–3 ngày 24/08/2026** — xem §5. Phụ lục A/B ở cuối file đã sinh lại theo mã SAU khi sửa.

**Cách quét:** phân tích AST, bắt mọi lời gọi `setToolTip` / `setAccessibleName` /
`setAccessibleDescription` / `setPlaceholderText` / `setWindowTitle` / `_show_message` /
`QMessageBox.*`. Phụ lục A và B ở cuối file là danh sách **đầy đủ**, có `file:line` để nhảy thẳng tới.

---

## 1. Tổng quan con số

| Loại chữ | Số lượng | Ghi chú |
|---|---|---|
| `setToolTip` | 43 | Chữ hiện khi rê chuột |
| `setAccessibleDescription` | 25 | Chữ cho trình đọc màn hình / TTS |
| `setAccessibleName` | 41 | Tên điều khiển |
| `setPlaceholderText` | 16 | Chữ mờ trong ô nhập |
| `setWindowTitle` | 18 | Tiêu đề hộp thoại |
| `_show_message` (toast) | 46 chuỗi viết cứng | 37 info (2 giây) + 9 lỗi (panel 8 giây) |
| `QMessageBox` | 9 | Hộp thoại chặn |

---

## 2. Bảy vấn đề làm người dùng bối rối

### 2.1. Ba lớp chữ cùng nói một việc, mỗi lớp một cách nói

Nút `↔` (tone tương đối) là ví dụ rõ nhất — 180 ký tự cho một nút rộng 30px:

| Lớp | Vị trí | Chữ |
|---|---|---|
| Tooltip | `ui/panels/header.py:104` | "Đổi sang tone tương đối (vd C Major ↔ A Minor).\nDùng khi bài là A Minor nhưng app hiện C Major." |
| A11y desc | `ui/panels/header.py:109` | "Chuyển nhanh giữa tone Major và tone Minor tương đối, ví dụ C Major đổi thành A Minor" |
| Toast khi bấm | `frontend_qt.py:657` | "↔ Đổi sang tone tương đối: A Minor" |

Cùng kiểu ở: đèn MIDI (`header.py:33` + `:35`), đèn trình duyệt (`:42` + `:44`),
nút Major/Minor (`header.py:92` + `tone_display.py:188`), ô chọn tone trong Sửa bài
(`edit_song.py:379` + `:381`).

**Cách sửa:** tooltip là câu ngắn; a11y desc chỉ viết khi **thêm** thông tin (vd giải thích màu đèn),
trùng thì xoá hẳn — Qt tự đọc tooltip khi không có description.

### 2.2. Tooltip dài như đoạn hướng dẫn

| Ký tự | Vị trí | Chữ hiện tại |
|---|---|---|
| 131 | `settings_dialog.py:783` | "Lưu file .song hiện tại làm bản gốc. Mỗi lần khởi động app sẽ chép đè bản này lên file đang dùng, xoá sạch mọi chỉnh sửa của khách." |
| 124 | `settings_dialog.py:507` | "Nhạc chạy → mở kênh Vang. Hết nhạc (dừng/chuyển bài) → tắt Vang sau khoảng 3 giây, để nói chuyện giữa các bài không bị vọng." |
| 106 | `header.py:44` | "Hiển thị trạng thái đồng bộ với trình duyệt. Xanh lá là CDP đã kết nối, vàng là WinRT, đỏ là chưa kết nối." |
| 101 | `edit_song.py:381` | "Chọn nốt gốc và thể cho mốc thời gian này. Hậu tố m là thể Thứ (Minor), không có m là Trưởng (Major)." |
| 95 | `header.py:104` | Nút `↔` (xem 2.1) |
| 87 | `header.py:35` | "Hiển thị trạng thái kết nối MIDI với Studio One. Xanh là đã kết nối, đỏ là mất kết nối." |
| 82 | `frontend_qt.py:2308` | "Mở trang Cài đặt âm thanh của Windows để chọn đúng thiết bị đang nghe làm mặc định" |

**Cách sửa:** trong hộp thoại Thiết lập đã có sẵn khuôn *nhãn phụ dưới ô* — chuyển câu giải thích
xuống đó (đọc được ngay, không cần rê chuột), tooltip chỉ giữ một mệnh đề.

### 2.3. Ngược lại: những nút bấm nhiều nhất thì **không có tooltip nào**

`ui/panels/tools.py:233-236` và `ui/panels/mode.py:40-42` tạo nút bằng `PainterButton` và chỉ gọi
`setAccessibleName` + `setAccessibleDescription` — **không gọi `setToolTip`**. Rê chuột không hiện gì:

- Tools: `Chế độ: Nhanh`, `Dò Lại`, `Auto-Tune`, `Fix Méo`, `Bè`, `Tắt Ồn`
- Mode: `Dân Ca`, `Lofi`, `Remix`, `Đa Thể Loại`
- Các nút SFX tự tạo (`ui/components/sfx_button_area.py`)

Chữ mô tả **đã có sẵn** trong `core/config.py:532-537` (trường `desc`, vd "Buộc dò lại tone bài hát
đang phát"). Chỉ thiếu một dòng `btn.setToolTip(desc)`.

### 2.4. Toast info dài quá thời gian nó sống

`frontend_qt.py:2231` — toast info là `QLabel` + `adjustSize()`, **không xuống dòng**, tự xoá sau
**2 giây**. Câu dài vừa đọc không kịp vừa tràn ngang. 9 chỗ đang vượt ~50 ký tự:

| Ký tự | Vị trí | Chữ |
|---|---|---|
| 82 | `songs_list.py:185` | "Chưa ai trong mạng lưới dò N bài này. Bạn dò một lần là cả mạng lưới dùng được." |
| 72 | `settings_dialog.py:1705` | "Đang dùng WinRT Fallback.\n(Không nhảy lời chính xác, hãy sửa bước 1 & 2)" |
| 70 | `frontend_qt.py:1304` | "Chế độ Full: quét cả bài, phát hiện đổi tone theo thời gian (chậm hơn)" |
| 67 | `frontend_qt.py:2207` | "Đã bật Premium. Khởi động lại app để giao diện Premium hiện đầy đủ." |
| 60 | `frontend_qt.py:1817` | "⚠️ Tone gợi ý — chưa chắc. Sai thì bấm Dò Lại hoặc chọn tay." |
| 59 | `frontend_qt.py:1815` | "🎤 Đã dò tone bằng cách nghe từ loa (không tải được YouTube)" |
| 53 | `frontend_qt.py:1153` | "Không phát được trong app — mở bằng trình duyệt ngoài" |
| 52 | `frontend_qt.py:1122` | "Không lấy được luồng trực tiếp — dùng player YouTube" |
| 51 | `frontend_qt.py:1313` | "Chế độ Nhanh: chỉ nghe ~45s đầu, lấy 1 tone (nhanh)" |

**Cách sửa:** rút còn ≤50 ký tự, hoặc chuyển sang `is_error=True` (panel 8 giây, có xuống dòng và
nút ✕). Ba câu 1122/1153/1170 là *thông tin nội bộ về đường tải* — người hát không cần biết, nên bỏ.

### 2.5. Toast bắn từ hộp thoại thì nằm **sau** hộp thoại

`_show_message` tạo QLabel con của cửa sổ chính và đặt ở giữa cửa sổ chính. Nhưng
`SongsListDialog`, `EditSongDialog`, `SettingsDialog`, `CalibrationWizard` đều mở bằng `.exec()`
(modal, cửa sổ riêng đè lên trên). Khoảng **36 thông báo** phát ra từ trong các hộp thoại này
(vd "✅ Đã lưu 5 mốc thời gian!", "Đã lưu mã PIN kỹ thuật", "Đã lưu cookie") rất dễ bị hộp thoại
che kín — người dùng bấm Lưu và tưởng là không có gì xảy ra.

**Cách sửa:** cho `_show_message` nhận widget cha (mặc định là dashboard, nhưng dialog truyền `self`),
hoặc dialog tự có dải thông báo riêng ở đáy hộp thoại.

### 2.6. Emoji trong toast dùng lộn xộn

Toast đã đổi màu theo `is_error` (xanh / đỏ) nên emoji là lớp tín hiệu thừa, và hiện đang không nhất quán:
`⚠️` (13 chỗ), `✅` (4), `❌` (3), `🎤` (4), `📁`, `💾`, `🎚️`, `🙈`, `👁️`, `↔` — trong khi
"Đã lưu thiết lập", "Đã lưu cookie", "Đã huỷ dò tone" thì không có gì.

**Cách sửa:** bỏ hết emoji trong toast, giữ màu. (Emoji trên **nhãn nút** như `👑 Chấm điểm` thì giữ.)

### 2.7. Từ kỹ thuật lọt tới người hát

| Từ đang hiện | Ở đâu | Nói lại thành |
|---|---|---|
| CDP / WinRT / WinRT Fallback | `header.py:42,44`, `settings_dialog.py:1703-1707` | "đồng bộ lời bài hát" / "chế độ dự phòng" |
| pywin32 / psutil chưa được cài đặt | `frontend_qt.py:2511,2536` | "Thiếu thành phần hệ thống — báo kỹ thuật" |
| ASIOLINK | `frontend_qt.py:2574,2578,2598,2615` | "Bảng điều khiển âm thanh" |
| QtWebEngine / bản Heavy | `settings_dialog.py:406` | "Cần bản cài đặt đầy đủ" |
| entry ("Cần ít nhất 1 entry!") | `edit_song.py:398,478` | "mốc thời gian" |
| preset | `songs_list.py:575,579`, `frontend_qt.py:2127` | "thiết lập âm thanh của bài" |
| MM:SS | `edit_song.py:470` | "phút:giây" |
| Vosk model / pyttsx3 / Piper | `core/accessibility/*` | chỉ trong log, **không** cần đổi |

---

## 3. Quy ước đề xuất (áp cho mọi chữ mới)

1. **Tooltip ≤ 40 ký tự, một dòng, bắt đầu bằng động từ.** Không lặp lại nhãn đã in trên nút.
2. **Không có tooltip thì không có `accessibleDescription`.** Chỉ viết description khi nó nói thêm
   điều tooltip không nói (vd ý nghĩa màu đèn).
3. **Phím tắt** để cuối câu, ngăn bằng dấu `·`: `Lưu bài đang phát · Ctrl+S`.
4. **Toast info ≤ 50 ký tự, không emoji, không dấu chấm cuối.** Dài hơn → dùng `is_error=True`.
5. **Toast báo lỗi = 1 câu chuyện gì + 1 việc cần làm.** Không kèm nguyên nhân kỹ thuật.
6. **Không tên riêng kỹ thuật** trong chữ người dùng thấy. Cần thì để trong ngoặc sau cách nói thường.
7. **Một ý — một câu duy nhất trong toàn app.** Hiện đang có 2 bản cho cùng một ý:
   `frontend_qt.py:1762` "Tone đã lưu từ lần trước. Sai? Bấm Dò Lại." (tooltip) và
   `frontend_qt.py:1819` "📁 Tone đã lưu. Sai? Bấm Dò Lại." (toast) → gom về một hằng số dùng chung.

---

## 4. Bảng sửa đề xuất

### 4.1. Thanh trên (header)

| Vị trí | Hiện tại | Đề xuất |
|---|---|---|
| `header.py:33` tooltip đèn MIDI | Trạng thái kết nối MIDI (Studio One/Loopback) | `Kết nối MIDI với Studio One` |
| `header.py:35` a11y | Hiển thị trạng thái kết nối MIDI với Studio One. Xanh là đã kết nối, đỏ là mất kết nối. | `Xanh: đã kết nối. Đỏ: mất kết nối.` |
| `header.py:42` tooltip đèn trình duyệt | Trạng thái đồng bộ trình duyệt (CDP/WinRT) | `Đồng bộ với trình duyệt` |
| `header.py:44` a11y | …CDP… vàng là WinRT… | `Xanh: tốt. Vàng: dự phòng. Đỏ: chưa kết nối.` |
| `header.py:104` tooltip `↔` | 2 dòng, 95 ký tự | `Đổi tone tương đối (C Major ↔ A Minor)` |
| `header.py:109` a11y `↔` | 85 ký tự trùng tooltip | **xoá** |
| `header.py:92` a11y Major/Minor | Nút đổi giữa Major và Minor. Bấm hoặc nhấn phím cách để đổi. | **xoá** (tooltip đã đủ) |
| `header.py:147` a11y Cài đặt | Mở hộp thoại thiết lập hệ thống. Phím tắt Ctrl+Phẩy | tooltip → `Cài đặt · Ctrl+,`, a11y **xoá** |
| `header.py:175` tooltip huy hiệu kỹ thuật | Đang mở khoá kỹ thuật — Ctrl+Alt+Shift+T để khoá lại | `Đang mở khoá · Ctrl+Alt+Shift+T để khoá` |

### 4.2. Thanh dưới (bottom bar)

Tooltip đang là 1 từ (`Lưu`, `Danh sách`, `Thư mục`) còn phím tắt lại giấu trong a11y description —
người sáng mắt không bao giờ thấy. Gộp lại:

| Vị trí | Đề xuất tooltip | a11y desc |
|---|---|---|
| `bottom_bar.py:38,40` | `Lưu bài đang phát · Ctrl+S` | xoá |
| `bottom_bar.py:49,51` | `Danh sách bài hát · Ctrl+O` | xoá |
| `bottom_bar.py:60` (ghi âm) | `Ghi âm · Ctrl+R` | xoá |
| `bottom_bar.py:79,81` | `Chấm điểm · Ctrl+P` | xoá |
| `bottom_bar.py:94,96` | `Mở thư mục bản thu` | xoá |

### 4.3. Tools & Mode — thêm tooltip đang thiếu

Trong `ui/panels/tools.py:236` và `ui/panels/mode.py:42`, thêm `btn.setToolTip(desc)` /
`mbtn.setToolTip(f"Chuyển sang chế độ {mlabel}")`. Đồng thời rút gọn `desc` trong
`core/config.py:532-537`:

| Nút | `desc` hiện tại | Đề xuất |
|---|---|---|
| Chế độ: Nhanh | Chuyển chế độ dò tone giữa Nhanh và Full | `Đổi kiểu dò tone: Nhanh ↔ Full` |
| Dò Lại | Buộc dò lại tone bài hát đang phát | `Dò lại tone bài đang phát` |
| Auto-Tune | Bật tắt Auto-Tune trên Studio One | `Bật/tắt Auto-Tune` |
| Fix Méo | Bật tắt chế độ chống méo giọng | `Bật/tắt chống méo giọng` |
| Bè | Bật tắt hiệu ứng bè giọng | `Bật/tắt bè giọng` |
| Tắt Ồn | Bật tắt bộ khử tiếng ồn nền cho mic | `Bật/tắt khử ồn cho mic` |

### 4.4. Hộp thoại Sửa bài (`edit_song.py`)

| Vị trí | Hiện tại | Đề xuất |
|---|---|---|
| `:169` | Chỉ muốn đổi 1 tone cho cả bài? Chọn ở đây — không cần nhập mốc thời gian. | `Đặt một tone duy nhất cho cả bài` |
| `:187` | Major = Trưởng (tươi sáng) · Minor = Thứ (trầm buồn) | `Major: tươi sáng · Minor: trầm buồn` |
| `:189` a11y | Chọn thể: Major là Trưởng, Minor là Thứ — áp cho toàn bộ bài hát | **xoá** |
| `:302` | Nốt gốc và thể (Trưởng = Major / Thứ = Minor) áp dụng từ mốc thời gian này. | `Tone áp dụng từ mốc này` |
| `:379` | Nốt gốc + thể. Có chữ 'm' = thể Thứ (Minor), không có = Trưởng (Major). | `Có chữ m là Minor, không có là Major` |
| `:381` a11y | 101 ký tự | **xoá** |
| `:398`, `:478` | Phải có ít nhất 1 entry! / Cần ít nhất 1 entry! | `Cần ít nhất 1 mốc thời gian` (dùng chung một câu) |
| `:470` | ⚠️ Vui lòng sửa thời gian không hợp lệ (MM:SS) | `Thời gian phải dạng phút:giây` |

### 4.5. Thiết lập (`settings_dialog.py`)

| Vị trí | Hiện tại | Đề xuất |
|---|---|---|
| `:406` | Cần bản cài đặt đầy đủ (Heavy) có QtWebEngine. | `Cần bản cài đặt đầy đủ` |
| `:507` | 124 ký tự về Vang tự động | tooltip: `Tự mở Vang khi có nhạc, tắt khi hết nhạc` + chuyển phần còn lại xuống nhãn phụ |
| `:783` | 131 ký tự về bản mẫu Studio One | tooltip: `Chốt file .song hiện tại làm bản gốc` + nhãn phụ: "Mỗi lần mở app sẽ khôi phục bản này, xoá mọi chỉnh sửa của khách." |
| `:1654` | 105 ký tự, 4 dòng, lỗi cookie | giữ nội dung nhưng bắt buộc `is_error=True` (đang đúng) — rút dòng đầu còn `Không xuất được cookie từ {trình duyệt}` |
| `:1703-1707` | CDP / WinRT Fallback | `Đã kết nối trình duyệt` / `Đang chạy chế độ dự phòng` / `Chưa kết nối — hãy mở YouTube trên Chrome/Edge` |

### 4.6. Thông báo tone (`frontend_qt.py`)

| Vị trí | Hiện tại | Đề xuất |
|---|---|---|
| `:1122`, `:1153`, `:1170` | 3 câu về luồng tải / nhúng | bỏ toast, chỉ ghi log |
| `:1304`, `:1313` | Mô tả 2 chế độ dò | `Dò Full — Chậm, bám đổi tone` / `Dò Nhanh - Nhanh, tone chính` |
| `:1815` | 🎤 Đã dò tone bằng cách nghe từ loa (không tải được YouTube) | Bỏ |
| `:1817` | ⚠️ Tone gợi ý — chưa chắc. Sai thì bấm Dò Lại hoặc chọn tay. | `Tone gợi ý — sai thì bấm Dò Lại` |
| `:1819` / `:1762` | 2 bản khác nhau của cùng một ý | gom về `Tone đã lưu — sai thì bấm Dò Lại` |
| `:2207` | Đã bật Premium. Khởi động lại app để giao diện Premium hiện đầy đủ. | `is_error=True` (cần đọc kỹ) hoặc `Đã bật Premium — khởi động lại app` |
| `:2511`, `:2536` | ⚠️ pywin32 / psutil chưa được cài đặt | `Thiếu thành phần hệ thống — báo kỹ thuật` |
| `:2574`-`:2615` | ASIOLINK | thay bằng `Bảng điều khiển âm thanh` |

---

## 5. Đã thực hiện (24/08/2026)

| Việc | Kết quả |
|---|---|
| Emoji trong toast | 19 toast bỏ emoji mở đầu; chỉ còn dấu `→` chỉ đường trong một câu |
| Toast info quá dài | 9 → **0** câu vượt 50 ký tự |
| `accessibleDescription` trùng tooltip | 25 → **13** (bỏ 12 câu chép lại tooltip) |
| Tooltip / a11y dài hơn 60 ký tự | 9 → **0** |
| Nút Tools/Mode thiếu tooltip | đã thêm `setToolTip(desc)`; 6 câu `desc` trong `core/config.py` được rút gọn |
| Phím tắt | đưa lên tooltip thanh dưới: `Lưu bài đang phát · Ctrl+S`… (trước đây chỉ nằm trong a11y, người sáng mắt không bao giờ thấy) |
| Từ kỹ thuật | CDP/WinRT, pywin32/psutil, ASIOLINK, QtWebEngine-Heavy, entry, preset, MM:SS đã thay bằng cách nói thường |
| Câu trùng ý | gom về hằng số `TONE_MSG_*` trong `frontend_qt.py`, dùng chung cho tooltip lẫn toast |
| Toast nằm sau hộp thoại | `_show_message` vẽ lên `QApplication.activeModalWidget()` nếu có — một dòng, không phải sửa 36 chỗ gọi |
| Toast info tràn ngang | đã bật word-wrap, rộng tối đa 80% cửa sổ, sống 2s + theo độ dài câu (tối đa 5s) |
| Trình đọc màn hình | `announcer` đọc tooltip khi không có description riêng — bỏ câu trùng mà người mù vẫn nghe đủ |

**Kiểm thử:** `tests/ui` 66/66 pass, trong đó có file mới `tests/ui/test_toast_message.py`
(4 test: toast bám theo hộp thoại modal, câu dài xuống dòng và ở lâu hơn).

**Một đề xuất KHÔNG làm:** §2.4 đề nghị bỏ hẳn toast “Không lấy được luồng trực tiếp”
(`frontend_qt.py:1122`). `tests/ui/test_embedded_stream_errors.py` chốt rằng app **phải nói ra**
vì sao mất luồng trực tiếp, nên câu này được giữ và chỉ rút gọn.

**Chưa làm:** `core/accessibility/announcer.py` vẫn đọc “trưởng/thứ” cho TTS tiếng Việt
(giọng Việt đọc “Major” rất kỳ) — cố ý giữ, đổi được nếu muốn đồng bộ tuyệt đối với nhãn nút.

---
## Phụ lục A: toàn bộ tooltip / a11y / placeholder / tiêu đề

_Tự động sinh bằng AST sau khi đã sửa. `{..}` = đoạn chữ ghép động._

### `frontend_qt.py`

| Dòng | Loại | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 205 | WindowTitle | 16 | Quang Lưu Studio |
| 560 | ToolTip | 40 | Đang ở thể Major. Bấm để đổi sang Minor. |
| 564 | ToolTip | 40 | Đang ở thể Minor. Bấm để đổi sang Major. |
| 2283 | AccessibleName | 13 | Thông báo lỗi |
| 2305 | ToolTip | 14 | Đóng thông báo |
| 2306 | AccessibleName | 14 | Đóng thông báo |
| 2329 | AccessibleDescription | 48 | Chọn thiết bị đang nghe làm mặc định của Windows |
| 2372 | WindowTitle | 13 | 💾 Lưu bài hát |
| 2411 | PlaceholderText | 35 | Tự động lấy từ YouTube nếu để trống |
| 2436 | PlaceholderText | 35 | https://www.youtube.com/watch?v=... |
| 3536 | WindowTitle | 26 | Kích hoạt Quang Lưu Studio |
| 3583 | PlaceholderText | 23 | Nhập activation code... |
| 3727 | WindowTitle | 24 | Cài đặt Quang Lưu Studio |

### `ui/components/hmixer_channel.py`

| Dòng | Loại | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 95 | AccessibleName | 8 | Mức {..} |
| 106 | AccessibleName | 12 | Giá trị {..} |
| 115 | ToolTip | 22 | Tắt âm kênh này (Mute) |
| 116 | AccessibleName | 11 | Tắt âm {..} |
| 245 | ToolTip | 39 | Đang tắt âm — Click để bật lại (Unmute) |
| 260 | ToolTip | 22 | Tắt âm kênh này (Mute) |

### `ui/components/sfx_button_area.py`

| Dòng | Loại | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 208 | AccessibleName | 13 | Hiệu ứng {..} |
| 230 | AccessibleName | 13 | Hiệu ứng {..} |
| 525 | PlaceholderText | 19 | VD: Cười, Vỗ tay... |
| 541 | PlaceholderText | 27 | Chọn file .wav hoặc .mp3... |
| 714 | ToolTip | 16 | Thêm nút SFX mới |
| 715 | AccessibleName | 12 | Thêm nút SFX |

### `ui/components/tone_display.py`

| Dòng | Loại | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 102 | ToolTip | 31 | Tone hiện tại: {..} {..} ({..}) |
| 188 | ToolTip | 38 | Đang ở thể {..}. Bấm để đổi sang {..}. |
| 222 | ToolTip | 33 | Tone kế tiếp và thời gian còn lại |
| 223 | AccessibleName | 12 | Tone kế tiếp |

### `ui/dialogs/calibration.py`

| Dòng | Loại | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 42 | WindowTitle | 19 | Cân chỉnh Auto-Tune |

### `ui/dialogs/edit_song.py`

| Dòng | Loại | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 37 | WindowTitle | 15 | Chỉnh sửa: {..} |
| 169 | ToolTip | 32 | Đặt một tone duy nhất cho cả bài |
| 180 | AccessibleName | 18 | Nốt gốc cho cả bài |
| 181 | AccessibleDescription | 46 | Chọn nốt gốc (C, D, E…) áp cho toàn bộ bài hát |
| 187 | ToolTip | 35 | Major: tươi sáng · Minor: trầm buồn |
| 188 | AccessibleName | 14 | Thể cho cả bài |
| 202 | ToolTip | 54 | Lưu ngay 1 tone duy nhất cho cả bài (xoá các mốc khác) |
| 300 | ToolTip | 33 | Tone áp dụng từ mốc thời gian này |
| 367 | PlaceholderText | 5 | MM:SS |
| 377 | ToolTip | 36 | Có chữ m là Minor, không có là Major |
| 378 | AccessibleName | 21 | Chọn tone cho mốc này |
| 384 | ToolTip | 11 | Xóa mốc này |

### `ui/dialogs/premium_dialog.py`

| Dòng | Loại | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 31 | WindowTitle | 17 | Tính năng Premium |

### `ui/dialogs/progress_dialog.py`

| Dòng | Loại | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 147 | WindowTitle | 22 | Bảng tiến bộ luyện hát |

### `ui/dialogs/scoring_report.py`

| Dòng | Loại | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 42 | WindowTitle | 18 | Ket qua Star Score |

### `ui/dialogs/setlist_dialog.py`

| Dòng | Loại | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 52 | WindowTitle | 25 | Live Setlist / Auto-Pilot |
| 143 | ToolTip | 23 | Chuyển sang bài kế tiếp |

### `ui/dialogs/settings_dialog.py`

| Dòng | Loại | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 34 | WindowTitle | 9 | Thiết lập |
| 357 | PlaceholderText | 53 | VD: D:/Songs/BaiHat.song hoặc C:/.../Studio One 7.exe |
| 359 | PlaceholderText | 45 | VD: C:/Program Files/Google/Chrome/chrome.exe |
| 406 | ToolTip | 22 | Cần bản cài đặt đầy đủ |
| 507 | ToolTip | 40 | Tự mở Vang khi có nhạc, tắt khi hết nhạc |
| 780 | ToolTip | 36 | Chốt file .song hiện tại làm bản gốc |
| 1315 | AccessibleName | 10 | Tốc độ đọc |
| 1403 | AccessibleName | 6 | Cỡ chữ |

### `ui/dialogs/shutdown_dialog.py`

| Dòng | Loại | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 49 | WindowTitle | 20 | Đang đóng Studio One |
| 110 | ToolTip | 41 | Để Studio One chạy tiếp và thoát app ngay |

### `ui/dialogs/songs_list.py`

| Dòng | Loại | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 28 | WindowTitle | 17 | Danh sách bài hát |
| 89 | ToolTip | 38 | Lấy tone bài chưa có từ thư viện chung |
| 92 | AccessibleName | 25 | Đồng bộ tone từ cộng đồng |
| 196 | PlaceholderText | 26 | 🔍  Tìm theo tên bài hát... |
| 209 | ToolTip | 16 | Tạo playlist mới |
| 214 | ToolTip | 26 | Đổi tên playlist đang chọn |
| 219 | ToolTip | 22 | Xóa playlist đang chọn |
| 387 | ToolTip | 4 | Phát |
| 391 | ToolTip | 8 | Tùy chọn |
| 622 | WindowTitle | 24 | ✏️ Sửa thông tin bài hát |

### `ui/dialogs/support_dialog.py`

| Dòng | Loại | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 138 | WindowTitle | 6 | Hỗ trợ |
| 209 | PlaceholderText | 38 | Ví dụ: Không tải được bài trên YouTube |
| 215 | PlaceholderText | 88 | Mô tả càng cụ thể càng nhanh được xử lý: bạn đang làm gì, app báo gì, xảy ra từ khi nào. |
| 224 | PlaceholderText | 31 | Để đội kỹ thuật gọi lại khi cần |
| 294 | PlaceholderText | 27 | Nhắn tiếp cho đội kỹ thuật… |

### `ui/dialogs/update_dialog.py`

| Dòng | Loại | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 33 | WindowTitle | 23 | Có phiên bản mới: v{..} |

### `ui/dialogs/widget_builder.py`

| Dòng | Loại | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 18 | WindowTitle | 11 | {..} - {..} |
| 54 | PlaceholderText | 9 | #HexColor |
| 79 | PlaceholderText | 7 | ♪, ☉, ≡ |
| 177 | ToolTip | 40 | CC built-in: "{..}" — giữ nguyên khi lưu |

### `ui/karaoke_player.py`

| Dòng | Loại | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 130 | WindowTitle | 35 | Quang Lưu Studio — Màn hình karaoke |

### `ui/panels/bottom_bar.py`

| Dòng | Loại | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 38 | ToolTip | 26 | Lưu bài đang phát · Ctrl+S |
| 39 | AccessibleName | 11 | Lưu bài hát |
| 48 | ToolTip | 26 | Danh sách bài hát · Ctrl+O |
| 49 | AccessibleName | 17 | Danh sách bài hát |
| 57 | ToolTip | 15 | Ghi âm · Ctrl+R |
| 58 | AccessibleName | 6 | Ghi âm |
| 75 | ToolTip | 18 | Chấm điểm · Ctrl+P |
| 76 | AccessibleName | 9 | Chấm điểm |
| 78 | ToolTip | 31 | 👑 Chấm điểm — Tính năng Premium |
| 79 | AccessibleName | 19 | Chấm điểm (Premium) |
| 80 | AccessibleDescription | 45 | Tính năng Premium. Nhấn để xem cách nâng cấp. |
| 89 | ToolTip | 18 | Mở thư mục bản thu |
| 90 | AccessibleName | 15 | Thư mục bản ghi |

### `ui/panels/header.py`

| Dòng | Loại | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 15 | AccessibleName | 30 | Thanh tiêu đề Quang Lưu Studio |
| 25 | ToolTip | 17 | Tài khoản Premium |
| 26 | AccessibleName | 16 | Huy hiệu Premium |
| 33 | ToolTip | 27 | Kết nối MIDI với Studio One |
| 34 | AccessibleName | 12 | Đèn báo MIDI |
| 35 | AccessibleDescription | 34 | Xanh: đã kết nối. Đỏ: mất kết nối. |
| 40 | ToolTip | 23 | Đồng bộ với trình duyệt |
| 41 | AccessibleName | 19 | Đèn báo trình duyệt |
| 42 | AccessibleDescription | 51 | Xanh: tốt. Vàng: chế độ dự phòng. Đỏ: chưa kết nối. |
| 50 | AccessibleName | 14 | Bảng thông báo |
| 51 | AccessibleDescription | 48 | Hiển thị tên bài hát và thông tin tone đang phát |
| 66 | AccessibleName | 15 | Đèn báo dò tone |
| 67 | AccessibleDescription | 35 | Xanh: đã dò ra tone. Xám: đang chờ. |
| 80 | AccessibleName | 9 | Chọn tone |
| 81 | AccessibleDescription | 46 | Chọn nốt gốc của bài hát, từ Đô (C) đến Si (B) |
| 89 | AccessibleName | 19 | Đổi thể Major Minor |
| 99 | ToolTip | 38 | Đổi tone tương đối (C Major ↔ A Minor) |
| 102 | AccessibleName | 18 | Đổi tone tương đối |
| 122 | ToolTip | 15 | Hỗ trợ kỹ thuật |
| 123 | AccessibleName | 19 | Mở hộp thoại hỗ trợ |
| 124 | AccessibleDescription | 41 | Gửi yêu cầu và xem trả lời ngay trong app |
| 134 | ToolTip | 16 | Cài đặt · Ctrl+, |
| 135 | AccessibleName | 12 | Mở thiết lập |
| 149 | ToolTip | 27 | Ẩn/Hiện Studio One + Plugin |
| 150 | AccessibleName | 18 | Ẩn hiện Studio One |
| 162 | ToolTip | 39 | Đang mở khoá · Ctrl+Alt+Shift+T để khoá |
| 163 | AccessibleName | 21 | Đang mở khoá kỹ thuật |

### `ui/panels/mixer.py`

| Dòng | Loại | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 148 | AccessibleName | 9 | Kênh {..} |
| 150 | AccessibleName | 13 | Âm lượng {..} |
| 151 | AccessibleDescription | 30 | Mũi tên trái phải để tăng giảm |
| 155 | AccessibleName | 11 | Tắt âm {..} |
| 156 | AccessibleDescription | 35 | Tắt hoặc bật lại âm thanh kênh {..} |

### `ui/panels/mode.py`

| Dòng | Loại | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 41 | ToolTip | 23 | Chuyển sang chế độ {..} |
| 42 | AccessibleName | 11 | Chế độ {..} |

### `ui/panels/tools.py`

| Dòng | Loại | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 24 | PlaceholderText | 34 | Tìm bài hát hoặc dán link YouTube… |
| 101 | ToolTip | 20 | Giảm {..} 1 bán cung |
| 102 | AccessibleName | 9 | Giảm {..} |
| 103 | AccessibleDescription | 22 | Giảm {..} một bán cung |
| 112 | AccessibleName | 12 | Giá trị {..} |
| 118 | ToolTip | 20 | Tăng {..} 1 bán cung |
| 119 | AccessibleName | 9 | Tăng {..} |
| 120 | AccessibleDescription | 22 | Tăng {..} một bán cung |

## Phụ lục B: toàn bộ toast `_show_message`

_`Lỗi` = gọi với `is_error=True` (panel 8 giây, có nút đóng)._
_Toast info: 2 giây + cộng theo độ dài câu, tối đa 5 giây, có xuống dòng._

### `frontend_qt.py`

| Dòng | Kiểu | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 324 | Info | 14 | Dev Mode: {..} |
| 390 | Info | 44 | Chế độ khách chưa bật (Thiết lập → Hệ thống) |
| 398 | Lỗi | 24 | Chưa đặt mã PIN kỹ thuật |
| 416 | Info | 26 | Mở khoá kỹ thuật {..} phút |
| 418 | Info | 49 | Mở khoá kỹ thuật {..} phút — Studio One chưa chạy |
| 664 | Info | 34 | Đổi sang tone tương đối: {..} {..} |
| 881 | Info | 47 | Đội kỹ thuật đã trả lời — mở nút Hỗ trợ để xem. |
| 1129 | Info | 30 | Không lấy được luồng trực tiếp |
| 1155 | Info | 29 | Đang thử lại luồng trực tiếp… |
| 1160 | Info | 25 | Mở bằng trình duyệt ngoài |
| 1177 | Info | 38 | Video không cho nhúng — mở trình duyệt |
| 1311 | Info | 34 | Dò Full: quét cả bài, bám đổi tone |
| 1320 | Info | 26 | Dò Nhanh: nghe 45 giây đầu |
| 1350 | Info | 14 | Đã huỷ dò tone |
| 1373 | Info | 14 | Đang dò lại... |
| 1376 | Info | 24 | Đang quét trình duyệt... |
| 1418 | Lỗi | 78 | Không mở được Cài đặt âm thanh. Hãy chuột phải biểu tượng loa ở khay hệ thống. |
| 1685 | Lỗi | 4 | {..} |
| 2031 | Info | 16 | Đã huỷ chấm điểm |
| 2061 | Info | 17 | Đang chấm điểm... |
| 2134 | Info | 28 | Đã khôi phục thiết lập: {..} |
| 2214 | Info | 34 | Đã bật Premium — khởi động lại app |
| 2455 | Lỗi | 23 | Cần link YouTube hợp lệ |
| 2528 | Lỗi | 43 | Studio One đang khoá — cần mở khoá kỹ thuật |
| 2532 | Lỗi | 40 | Thiếu thành phần hệ thống — báo kỹ thuật |
| 2536 | Lỗi | 35 | Không tìm thấy Studio One đang chạy |
| 2540 | Lỗi | 46 | Studio One đang chạy nhưng không có cửa sổ nào |
| 2545 | Info | 16 | Đã ẩn Studio One |
| 2548 | Info | 18 | Đã hiện Studio One |
| 2557 | Lỗi | 40 | Thiếu thành phần hệ thống — báo kỹ thuật |
| 2595 | Lỗi | 38 | Lỗi tìm bảng điều khiển âm thanh: {..} |
| 2599 | Lỗi | 39 | Không tìm thấy bảng điều khiển âm thanh |
| 2619 | Info | 30 | Đã ẩn bảng điều khiển âm thanh |
| 2636 | Info | 32 | Đã hiện bảng điều khiển âm thanh |
| 2666 | Info | 20 | Đã lưu bản thu: {..} |
| 2675 | Lỗi | 4 | {..} |
| 2679 | Lỗi | 18 | Lưu thất bại: {..} |
| 2682 | Info | 18 | Đã huỷ lưu bản thu |
| 2705 | Lỗi | 22 | Không thể ghi âm: {..} |
| 3145 | Info | 8 | TTS: tắt |
| 3249 | Lỗi | 20 | Không nghe được lệnh |
| 3280 | Lỗi | 30 | Nghe được: "{..}" — không hiểu |
| 3288 | Info | 20 | Đã thực hiện: "{..}" |

### `ui/dialogs/calibration.py`

| Dòng | Kiểu | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 766 | Info | 16 | Đã lưu cân chỉnh |

### `ui/dialogs/edit_song.py`

| Dòng | Kiểu | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 227 | Lỗi | 21 | Bài hát không có URL! |
| 241 | Info | 30 | Đã đặt 1 tone {..} cho cả bài! |
| 246 | Lỗi | 21 | Lỗi khi lưu timeline! |
| 466 | Lỗi | 29 | Thời gian phải dạng phút:giây |
| 471 | Lỗi | 24 | Có 2 mốc trùng thời gian |
| 474 | Lỗi | 27 | Cần ít nhất 1 mốc thời gian |
| 491 | Lỗi | 21 | Bài hát không có URL! |
| 499 | Info | 26 | Đã lưu {..} mốc thời gian! |
| 504 | Lỗi | 21 | Lỗi khi lưu timeline! |

### `ui/dialogs/settings_dialog.py`

| Dòng | Kiểu | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 840 | Lỗi | 26 | Lỗi lưu chế độ khách: {..} |
| 891 | Info | 22 | Đã lưu mã PIN kỹ thuật |
| 898 | Lỗi | 42 | Hãy đóng Studio One trước khi chốt bản mẫu |
| 903 | Info | 26 | Đã chốt bản mẫu Studio One |
| 905 | Lỗi | 22 | Chốt bản mẫu lỗi: {..} |
| 1439 | Lỗi | 13 | Lỗi TTS: {..} |
| 1620 | Info | 16 | Đã lưu thiết lập |
| 1645 | Info | 13 | Đã lưu cookie |
| 1656 | Lỗi | 88 | Không xuất được cookie từ {..}. / Hãy đóng hẳn trình duyệt rồi thử lại, hoặc dùng Firefox. |
| 1669 | Info | 23 | Đã tắt trình duyệt ngầm |
| 1675 | Lỗi | 41 | Thiếu công cụ sửa shortcut — báo kỹ thuật |
| 1683 | Info | 15 | Đã sửa shortcut |
| 1685 | Lỗi | 30 | Bạn đã từ chối cấp quyền Admin |
| 1687 | Lỗi | 9 | Lỗi: {..} |
| 1704 | Info | 22 | Đã kết nối trình duyệt |
| 1706 | Info | 25 | Đang chạy chế độ dự phòng |
| 1708 | Lỗi | 46 | Chưa kết nối — hãy mở YouTube trên Chrome/Edge |

### `ui/dialogs/songs_list.py`

| Dòng | Kiểu | Độ dài | Chữ hiện tại |
|---|---|---|---|
| 111 | Lỗi | 67 | Đồng bộ tone cộng đồng đang tắt. Bật lại trong Thiết lập › Công cụ. |
| 130 | Info | 39 | Mọi bài trong danh sách đều đã có tone. |
| 180 | Info | 29 | Đã lấy tone cho {..}/{..} bài |
| 184 | Info | 39 | Chưa ai trong mạng lưới dò {..} bài này |
| 430 | Lỗi | 33 | Tên playlist rỗng hoặc đã tồn tại |
| 449 | Lỗi | 33 | Tên rỗng hoặc trùng playlist khác |
| 573 | Info | 28 | Đã lưu thiết lập cho bài hát |
| 577 | Lỗi | 24 | Không lưu được thiết lập |
| 596 | Lỗi | 33 | Tên playlist rỗng hoặc đã tồn tại |
| 665 | Lỗi | 31 | Tên bài hát không được để trống |
| 674 | Info | 29 | Đã cập nhật thông tin bài hát |

