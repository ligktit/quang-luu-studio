# Ẩn DAW khỏi khách, bản mẫu & đóng an toàn

> **Ngày viết:** 2026-08-09 · **cập nhật 2026-11-02:** bỏ khoá kỹ thuật (PIN), thay bằng
> tự ẩn DAW khi mở app + nút hiện/ẩn trong Cài đặt.
> Dành cho **nhân viên kỹ thuật** khi setup máy cho phòng thu.

---

## 1. Giải quyết chuyện gì

| Vấn đề | Cách xử lý |
|---|---|
| Khách táy máy chỉnh thông số trong Studio One/Cubase → phần mềm chạy sai | **Tự ẩn DAW**: mỗi lần mở app, mọi cửa sổ DAW (kể cả plugin) bị ẩn. Hiện lại chỉ ở **Cài đặt → Cửa sổ {DAW}** |
| Khách đã lỡ chỉnh và lưu đè → sai vĩnh viễn | **Bản mẫu .song/.cpr**: mỗi lần khởi động app chép đè bản KTV đã chốt lên file đang dùng |
| Thoát app xong, mở Studio One lần sau nó đòi phục hồi phiên, không vào thẳng file đã lưu | **Đóng an toàn**: để Studio One tự thoát, không còn `taskkill /F` |

App **không lưu** khi đóng: hộp thoại "lưu hay không" được trả lời bằng đúng nút
**"Don't Save"**, bấm qua `BM_CLICK` nên cửa sổ DAW đang ẩn vẫn đóng được — không
phải hiện lên chỉ để gõ Ctrl+S. Chỉnh sửa của khách chết theo phiên, đúng ý đồ của
bản mẫu.

> Bản cũ (đến 1.9.0) dùng **khoá kỹ thuật**: mã PIN + `Ctrl+Alt+Shift+T` + phiên 20
> phút. KTV phải thử nhiều lần mới mở được nên đã bỏ. Máy cũ được chuyển tự động lần
> đầu chạy bản mới: máy đang bật chế độ khách giữ việc phục hồi bản mẫu; dữ liệu PIN
> (`tech_lock`) bị xoá.

---

## 2. Cài đặt → "Cửa sổ {DAW}"

Mục này **áp dụng ngay khi bấm**, không cần bấm "Lưu thiết lập".

| Thành phần | Tác dụng |
|---|---|
| **Tự ẩn {DAW} khi mở app** | Mặc định **bật**. Ẩn DAW lúc mở app, khi Tự sửa âm thanh mở/mở lại DAW giữa buổi, và khi thoát app mà DAW còn ở lại |
| **Hiện / Ẩn {DAW} + plugin** | Hiện hoặc ẩn mọi cửa sổ của DAW. Hiện rồi thì DAW cứ hiện tới lần mở app sau |
| **Danh sách cửa sổ** | Bật/tắt riêng từng cửa sổ (Auto-Tune, bảng ASIO…) mà không hiện cả DAW — xem mục 3 |
| **Phục hồi bản mẫu mỗi lần khởi động** | Xem mục 4 |
| **Chốt bản mẫu** | Xem mục 4 |

Header **không còn nút mắt** — khách hát không bấm nhầm được. Nút **Hỗ trợ kỹ thuật**
luôn hiện.

## 3. Mở riêng một cửa sổ plugin

Cửa sổ plugin (Auto-Tune…) và bảng ASIO phải **để mở sẵn trong bài mẫu** — app chỉ
ẩn/hiện được cửa sổ đã có, không tự mở plugin được.

Cài đặt → Cửa sổ {DAW} → gạt công tắc của cửa sổ cần chỉnh → cửa sổ đó hiện lên
trên cùng, DAW chính vẫn ẩn. Chỉnh xong gạt tắt (hoặc để vậy — lần mở app sau tự ẩn).
Bấm **Làm mới** nếu vừa mở thêm cửa sổ. Danh sách có cả công cụ ASIO chạy riêng
(ASIO Link Pro, ASIOVADPRO…) — những cửa sổ này không bị tự ẩn khi mở app.

## 4. Bản mẫu .song

Quy trình chuẩn khi setup hoặc khi cần sửa thiết lập trong Studio One:

1. Cài đặt → Cửa sổ {DAW} → **Hiện** → tinh chỉnh trong DAW → **lưu bài (Ctrl+S)**.
2. **Đóng Studio One** (bắt buộc — không ghi đè file đang mở được).
3. Thiết lập → **Chốt bản mẫu .song**.

Từ đó mỗi lần app khởi động, file `.song` được chép đè lại từ bản mẫu **trước khi**
Studio One mở. Khách chỉnh gì cũng chỉ sống trong buổi đó.

Vị trí lưu: `%APPDATA%\QuangLuuStudio\so_template\`

| File | Nội dung |
|---|---|
| `template.song` | Bản mẫu KTV đã chốt |
| `template.json` | Nguồn, sha256, kích thước, thời điểm chốt |
| `replaced.song` | Bản vừa bị chép đè — phao cứu sinh nếu KTV chỉnh xong mà **quên** chốt |

Bỏ qua việc phục hồi (không báo lỗi) khi: chưa chốt bản mẫu, đường dẫn Studio One
trỏ tới `.exe` chứ không phải `.song`, hoặc nội dung đã trùng bản mẫu.

**Studio One còn chạy lúc app khởi động** (phiên trước thoát bị quá hạn chờ, hoặc
KTV bấm *"Bỏ qua, thoát ngay"*): không ghi đè lên file đang mở được, mà bỏ qua
luôn thì bản mẫu mất tác dụng cả buổi. Nên
app hiện hộp thoại *"Đang chuẩn bị bản mẫu"*, **đóng Studio One mà không lưu**,
chép bản mẫu, rồi mở Studio One lên lại — kể cả khi tắt "Tự mở Studio One". Bấm
*"Bỏ qua, dùng bản hiện tại"* thì giữ nguyên bài đang mở, phiên đó không phục hồi.

Ở luồng này app **không bao giờ nhấn Enter** vào hộp thoại hỏi lưu — nút mặc định
là *Yes* (lưu). Studio One hỏi bằng MessageBox chuẩn Windows: tiêu đề *"Studio
One"*, ba nút **Yes – No – Cancel**; **No** chính là "không lưu". App tìm và bấm
đúng nút đó qua ba lớp:

1. **Control ID `IDNO` (7)** của hộp thoại chuẩn (`#32770`) — nút No luôn mang ID
   này bất kể Windows đang chạy ngôn ngữ gì. Đây là lớp ăn trong thực tế.
2. Nút Win32 có **nhãn** khớp (`No`, `Don't Save`, `Discard`, `Không lưu`…).
3. **UI Automation** — dự phòng cho hộp thoại do Studio One tự vẽ.

Không bấm được nút đó thì app **huỷ luôn việc đóng** (Escape), để Studio One chạy
tiếp và bỏ qua phục hồi phiên đó — thà mất một phiên còn hơn lưu đè bản khách đã
chỉnh lên bài gốc. Log ghi `[DAW-HIDE] Không đóng được Studio One (no_save_button)`.

Cùng cơ chế bấm "Don't Save" đó cũng được dùng ở **luồng thoát app** (mục 5), chỉ
khác nước cuối khi hụt nút — xem bên dưới.

> Chỉ chép **file `.song`**. Nếu bài có media rời nằm trong thư mục bài hát
> (bản thu, sample import) thì phần đó không nằm trong bản mẫu.

Tắt tính năng này bằng cách bỏ tích **"Phục hồi bản mẫu .song mỗi lần khởi động"**.

### Dùng với Cubase

App điều khiển được Studio One hoặc Cubase. Khi máy dùng Cubase, kỹ thuật viên làm:

1. Vào **Cài đặt → Phần mềm thu âm (DAW) → Cubase**.
2. Đường dẫn bản mẫu trỏ tới file `.cpr` của bài mẫu: thứ tự track **Nhac / Mic / Vang / Be**,
   plugin pitch (Pitch Correct) đặt ở **insert đầu tiên của kênh Mic**.
3. Chạy `setup_all.bat` để chép script MIDI Remote `QuangLuu_QuangLuuMIDI.js` vào
   `Documents\Steinberg\Cubase\MIDI Remote\Driver Scripts\Local\QuangLuu\QuangLuuMIDI\`.
4. Trong Cubase, **tắt** *Release Driver when Application is in Background*
   (Studio → Studio Setup → Audio System).
5. Bản mẫu chốt là `template.cpr` (cơ chế phục hồi bản mẫu ở trên áp dụng cho file `.cpr`).
6. Sau khi đổi DAW, **mở lại app** để mọi nhãn cập nhật theo DAW mới.

## 5. Đóng Studio One an toàn

Bật ở **Thiết lập → Khởi động / Tắt tự động → "Đóng Studio One khi thoát"**.

Khi thoát app, hiện hộp thoại *"Đang đóng Studio One an toàn"* và chạy tuần tự
(`core/engine/_lifecycle.py` → `close_studio_one_safely`, gọi với `save=False`):

1. Gửi **WM_CLOSE** tới cửa sổ chính. **Không Ctrl+S** — xem "Vì sao không lưu"
   ngay dưới.
2. Hộp thoại hỏi lưu bật lên → bấm đúng nút **"Don't Save"** qua ba lớp giống hệt
   mục 4 (IDNO → nhãn → UI Automation). Bấm bằng `BM_CLICK` nên **không cần
   foreground**: cửa sổ Studio One đang ẩn vẫn đóng được, không phải hiện lên.
3. Hộp thoại khác (không phải hỏi lưu) → giành foreground rồi Enter (tối đa 5
   lần, cách nhau 1.2s).
4. Chờ process biến mất, mặc định tối đa 45 giây.

**Vì sao không lưu.** Bản cũ gõ Ctrl+S trước khi đóng, nhưng đó chỉ là *mẹo* để
Studio One khỏi hỏi — không phải nhu cầu giữ dữ liệu, vì bản mẫu chép đè hết ở
lần khởi động sau. Cái giá của mẹo đó quá đắt: phải **hiện cửa sổ Studio One lên**
để gõ phím (lộ DAW cho khách), chậm, và ghi đè bài mẫu bằng đúng bản khách vừa táy
máy. Trả lời thẳng hộp thoại bằng "Don't Save" bỏ được cả ba.

**Nước cuối khi hụt nút "Don't Save"** (`fallback_save`): nếu **đã chốt bản mẫu
`.song`** thì app nhấn Enter (= Save) cho Studio One thoát sạch — bản lưu ra đằng
nào cũng bị bản mẫu chép đè ở lần khởi động sau nên vô hại. **Chưa chốt bản mẫu**
thì huỷ đóng, để Studio One chạy tiếp (`no_save_button`), tuyệt đối không ghi đè.
Luồng khởi động ở mục 4 **luôn tắt** nước cuối này: ở đó lưu là phá đúng file mà
bản mẫu sắp phục hồi.

**Hết giờ thì KHÔNG giết process.** App báo *"Studio One chưa đóng xong"* rồi thoát,
để Studio One chạy tiếp — an toàn hơn hẳn việc giết nó giữa lúc đang ghi file.
Nút **"Bỏ qua, thoát ngay"** trong hộp thoại cũng cho kết quả tương tự.

Đây chính là điểm khác cốt lõi so với bản cũ: trước đây hết 5 giây là `taskkill /F`,
mà taskkill để lại cờ "thoát bất thường" → lần mở sau Studio One đòi phục hồi phiên.

## 6. Các khoá trong `settings.json`

Nằm ở `%APPDATA%\QuangLuuStudio\settings.json` (bản cài) hoặc thư mục gốc project
(chạy dev).

```json
{
  "auto_close_studio_one": true,
  "studio_one_close_timeout": 45,
  "force_kill_studio_one": false,
  "daw_windows": {
    "auto_hide": true,
    "restore_template": true
  }
}
```

| Khoá | Ý nghĩa |
|---|---|
| `studio_one_close_timeout` | Số giây chờ Studio One thoát (mặc định 45) |
| `force_kill_studio_one` | `true` = hết giờ thì tắt cứng như bản cũ. **Để `false`** trừ khi có máy cá biệt treo hẳn |
| `daw_windows.auto_hide` | Tự ẩn DAW khi mở app (mặc định `true`) |
| `daw_windows.restore_template` | Phục hồi bản mẫu mỗi lần khởi động (mặc định `false`; máy cũ bật chế độ khách → `true`) |

## 7. Hạn chế đã biết

1. **Không có mật khẩu.** Rào chắn duy nhất là phải mở Cài đặt; khách mò vào Cài
   đặt vẫn hiện được DAW. Dev Mode (`Ctrl+Shift+D`) cũng không bị chặn.
2. **Khe hở lúc khởi động.** DAW nạp bài mất hàng chục giây; app chỉ ẩn được sau
   khi cửa sổ chính hiện ra, rồi bám ẩn thêm 60 giây cho các cửa sổ plugin mọc
   muộn. Trong khoảng nạp đó cửa sổ vẫn thấy trên màn hình.
3. **Khách tự mở DAW** (Start Menu/desktop) sau khi app đã chạy thì không bị ẩn.
4. **Chỉnh sửa của khách không được giữ lại.** Thoát app là đóng Studio One
   **không lưu** — cố ý, để bài mẫu không bị bản khách đè lên. KTV muốn giữ
   thay đổi thì phải tự Ctrl+S trong Studio One **trước khi** thoát app, rồi
   chốt lại bản mẫu.

## 8. Xử lý sự cố

| Hiện tượng | Nguyên nhân / cách xử lý |
|---|---|
| Không thấy cửa sổ Auto-Tune trong danh sách | Plugin chưa mở sẵn trong bài mẫu, hoặc vừa mở — bấm **Làm mới** |
| Chốt bản mẫu báo "Hãy đóng Studio One trước" | File `.song` đang mở, không ghi đè được |
| Thoát app báo "Studio One chưa đóng xong" | Studio One đang kẹt hộp thoại lạ. Đóng tay, hoặc tăng `studio_one_close_timeout` |
| Thoát app báo "Đã huỷ đóng Studio One để không lưu nhầm" | Không bấm được nút "Don't Save" và **chưa chốt bản mẫu** nên app không dám lưu. Chốt bản mẫu (mục 4) là lần sau app tự lưu-rồi-đóng được |
| KTV chỉnh trong Studio One xong, thoát app, buổi sau mất hết | Đúng thiết kế (mục 7.6). Phải Ctrl+S trong Studio One rồi **chốt bản mẫu** trước khi thoát |
| Mở Studio One vẫn thấy đòi phục hồi phiên | Lần trước thoát bằng tắt cứng (mất điện, Task Manager, hoặc `force_kill_studio_one: true`) |
| Mở app trước Studio One → mode/vang không ăn | Đã có cơ chế tự bắn lại (mục 9). Nếu vẫn lệch: Studio One chưa MIDI Learn CC đó, hoặc bài đang mở không phải bản mẫu |

## 9. Đồng bộ MIDI khi Studio One sẵn sàng

**Vấn đề.** Cổng MIDI ảo `QuangLuuMIDI` (loopMIDI) tồn tại **độc lập với Studio
One** — nó mở được ngay cả khi Studio One chưa chạy. Nên `is_midi_connected()`
bật `True` từ giây đầu, app tưởng "đã thông" và bắn hết trạng thái khởi tạo
(mode, vang, auto-tune, khử ồn, tone, mức trộn) trong khi Studio One còn đang nạp
bài. Lệnh rơi vào khoảng không: cả buổi Studio One lệch trạng thái với giao diện,
mà DAW lại đang ẩn nên không ai thấy để sửa.

**Cách xử lý** (`core/so_windows.py` → `ReadySchedule` / `ReadyWatcher`):

1. Một vòng nền bám theo Studio One, mốc quan sát được là lúc nó dựng xong **cửa
   sổ chính** (`main_windows()`).
2. Từ mốc đó, app bắn lại **toàn bộ** trạng thái ở các thời điểm **+3s, +10s,
   +25s, +50s** (`DEFAULT_RESEND_DELAYS`). Bắn nhiều lần vì cửa sổ chính hiện ra
   **sớm hơn** lúc bài nạp xong — mà MIDI map nằm trong bài, và thời gian nạp thì
   tuỳ máy, tuỳ số plugin. Không có cách nào hỏi Studio One "xong chưa".
3. CC là lệnh **idempotent** nên gửi thừa hoàn toàn vô hại. Rẻ hơn nhiều so với
   đoán trượt một lần rồi lệch cả buổi.
4. Studio One **tắt rồi mở lại** giữa phiên (KTV hoặc Tự sửa âm thanh) → lịch nạp lại
   từ đầu: cửa sổ mới nghĩa là bài mới nạp, phải đồng bộ lại.

Mỗi lượt bắn gọi `frontend_qt.py:_sync_midi_states`, đẩy 6 nhóm: Auto-Tune, MODE
(từng nút), Tắt Ồn, Tắt Vang (kèm multi-CC), tone + thể, và **mức mọi thanh trượt
mixer**. Nhóm cuối quan trọng không kém nhóm Tắt Vang: thiếu nó thì Studio One
giữ mức của bản mẫu `.song` trong khi giao diện hiển thị mức khác.

Giá trị lấy từ trạng thái **sống** của giao diện chứ không phải trạng thái lúc
khởi động — khách bấm gì trong lúc Studio One nạp bài thì lượt sau chốt đúng cái
họ đang thấy.

> Nhịp quét đổi theo trạng thái: dày (2s) khi còn mốc chưa bắn, thưa (6s) khi
> đang chờ Studio One xuất hiện hoặc đã bắn hết — mỗi vòng quét đều duyệt process
> list nên không quét dày mãi.

---

*Các file liên quan: `core/daw_visibility.py` (cấu hình tự ẩn + chuyển từ khoá cũ),
`core/so_windows.py` (tìm/ẩn/hiện cửa sổ theo PID, từng cửa sổ, công cụ ASIO),
`core/so_template.py` (bản mẫu), `core/engine/_lifecycle.py:close_studio_one_safely`,
`ui/dialogs/settings_dialog.py` (`_build_daw_windows`), `ui/dialogs/shutdown_dialog.py`,
`ui/audio_doctor_bridge.py` (`launch_daw`), `frontend_qt.py` (`_auto_launch_apps`,
`_on_toggle_studio_one`, `_start_so_ready_watcher`, `_sync_midi_states`, `closeEvent`).
Kiểm thử: `tests/core/test_daw_visibility.py`, `tests/core/test_so_windows_daw.py`,
`tests/core/test_so_template.py`, `tests/core/test_close_studio_one_no_save.py`,
`tests/core/test_so_ready_watcher.py`, `tests/ui/test_settings_daw_windows.py`,
`tests/ui/test_exit_close_studio_one.py`, `tests/ui/test_startup_template_restore.py`,
`tests/ui/test_midi_resync_on_so_ready.py`.*
