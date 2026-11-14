# Bỏ khoá kỹ thuật · Thông báo Tự sửa âm thanh trong cửa sổ riêng · Ẩn/hiện từng cửa sổ plugin — thiết kế

Ngày: 2026-11-02 · Trạng thái: đã duyệt (2026-11-02)

Ba thay đổi cho bản phát hành kế tiếp. Ba phần độc lập về code, chung một bản phát hành.
Ký hiệu **[quyết định của Claude]** đánh dấu những chỗ người viết spec tự chốt, chủ dự án chưa
trực tiếp chọn.

---

## Phần 1 — Bỏ khoá kỹ thuật, thay bằng tự ẩn DAW khi mở app

### Vì sao

KTV có khi phải thử tới **10 lần** mới mở được khoá kỹ thuật (PIN + phím tắt
Ctrl+Alt+Shift+T) để hiện lại Studio One/Cubase. Mục đích thật của khoá chỉ là để khách hát
không nhìn thấy và không chạm nhầm vào DAW. Mục đích đó đạt được bằng cách ẩn DAW mỗi lần mở
app và đặt nút hiện DAW ở chỗ cần thêm thao tác.

### Hiện trạng (đã đọc code)

- `core/kiosk.py`: cấu hình ở `settings.json → tech_lock` gồm `enabled`, PIN băm PBKDF2,
  `keep_hidden` (watchdog `so_windows.HideGuard`), `session_minutes`, `restore_template`.
  Phiên kỹ thuật chỉ sống trong RAM. Nhập sai PIN thì bị khoá tạm.
- `ui/dialogs/tech_unlock.py`: hộp thoại nhập PIN và đặt PIN.
- `frontend_qt.py`:
  - `_apply_kiosk_visibility`: khi khoá thì giấu nút mắt, giấu nút Hỗ trợ (Báo lỗi), giấu
    huy hiệu phiên, chạy watchdog và đồng hồ tự khoá lại.
  - `_toggle_tech_session` (Ctrl+Alt+Shift+T), `_lock_studio_one`, `_kiosk_session_tick`.
  - `_auto_launch_apps`: chỉ phục hồi bản mẫu khi `kiosk.is_enabled() and restore_template`.
    Chỉ ẩn DAW lúc khởi động khi đang khoá (`hide_when_ready` nếu vừa mở DAW, `hide_all` nếu
    DAW đã chạy sẵn).
  - `_on_toggle_studio_one` chặn khi đang khoá. Khi thoát app mà DAW chưa đóng xong thì
    `hide_all()` nếu đang khoá (khoảng dòng 4341).
- `ui/panels/header.py`: nút mắt `_eye_btn` (ẩn/hiện DAW + plugin), nút `_support_btn`
  (Hỗ trợ kỹ thuật).
- `ui/dialogs/settings_dialog.py → _build_kiosk`: mục "Chế độ khách" gồm các ô tick, chọn
  thời lượng phiên, nút Mở khoá / Đặt PIN / Chốt bản mẫu.
- Nút Báo lỗi bị giấu khi khoá là **có chủ đích** ("khách hát không phải người gửi ticket").
  Đã kiểm tra theo yêu cầu: đúng như vậy.

### Thay đổi

1. **Bỏ hẳn** PIN, phím tắt Ctrl+Alt+Shift+T, phiên kỹ thuật, đồng hồ tự khoá, huy hiệu phiên,
   hộp thoại `tech_unlock.py`, tuỳ chọn "canh ẩn liên tục" (`keep_hidden`/`HideGuard`) và
   khái niệm "đang khoá". Xoá `core/kiosk.py` hoặc thu gọn nó thành module cấu hình mới, tuỳ
   builder. Không còn chỗ nào hỏi `is_locked()`.
2. **Tự ẩn DAW khi mở app**: dùng đúng cơ chế đang chạy lúc khoá. Vừa khởi chạy DAW thì
   `hide_when_ready()`. DAW đã chạy sẵn thì `hide_all()`. Ẩn mọi cửa sổ của tiến trình DAW,
   kể cả plugin.
   - **[quyết định của Claude]** Thêm ô tick "Tự ẩn {DAW} khi mở app", **mặc định bật** trên
     mọi máy, kể cả máy trước đây không bật chế độ khách. Lý do: máy dev hoặc máy KTV cần tắt
     được.
   - Khi thoát app mà DAW còn ở lại (đoạn khoảng dòng 4341): `hide_all()` nếu ô này bật.
   - **[quyết định của Claude]** Mọi lần **app** khởi chạy DAW giữa phiên cũng tự ẩn khi ô này
     bật. Gồm `DashboardDoctorActions.launch_daw` (`ui/audio_doctor_bridge.py`), được gọi khi
     Tự sửa âm thanh mở DAW đang tắt hoặc đóng/mở lại Cubase để nhả driver. Cách làm: gọi
     `hide_when_ready()` sau khi khởi chạy. Lý do: khách giờ tự bấm Tự sửa từ cửa sổ cảnh báo (Phần 2),
     DAW bật lên trước mặt khách là hỏng mục đích. Ngoại lệ được chấp nhận: DAW do người mở
     **bằng tay** sau khi app đã chạy thì không bị ẩn.
3. **Nút mắt rời header, vào Cài đặt**: trong Cài đặt có nút "Hiện {DAW} + plugin" /
   "Ẩn {DAW} + plugin". Chữ trên nút đổi theo trạng thái thật (`so_windows.any_visible()`).
   Header không còn nút mắt. Mọi chỗ tham chiếu `_eye_btn` phải chịu được giá trị `None`
   (ví dụ vòng lặp phóng chữ khoảng dòng 3862).
4. **Không tự ẩn lại**: KTV bấm hiện thì DAW cứ hiện cho tới lần mở app kế tiếp.
5. **Nút Báo lỗi (Hỗ trợ) luôn hiện** ở header.
6. **Phục hồi bản mẫu** tách khỏi chế độ khách, thành ô tick riêng "Phục hồi bản mẫu
   {.song/.cpr} mỗi lần khởi động". Giữ nguyên nút "Chốt bản mẫu" và dòng mô tả bản mẫu.
7. **Chuyển cấu hình cũ**: lần đầu chạy bản mới, nếu `settings.json` chưa có cấu hình mới thì:
   - `restore_template` mới = `tech_lock.enabled AND tech_lock.restore_template` (mặc định
     `restore_template` cũ là `true`). Máy đang khoá vẫn được phục hồi bản mẫu, máy không khoá
     thì vẫn không.
   - Tự ẩn khi mở app = bật (như mục 2).
   - Bỏ qua dữ liệu PIN. **[quyết định của Claude]** Xoá key `tech_lock` khỏi settings sau khi
     chuyển xong để không còn PIN băm nằm lại.
   - Tên key mới: builder tự chọn.
8. Mục Cài đặt cũ "Chế độ khách (khoá kỹ thuật)" đổi thành mục **"Cửa sổ {DAW}"**. Mục này
   chứa: ô tick tự ẩn, nút Hiện/Ẩn tất cả, danh sách cửa sổ (Phần 3), ô tick phục hồi bản mẫu,
   nút Chốt bản mẫu. Các thay đổi trong mục này áp dụng ngay khi bấm, giống mục cũ.

### Không làm

- Không thêm mật khẩu hay bước xác thực nào khác. Rào chắn duy nhất là phải mở Cài đặt.
  Chủ dự án chấp nhận rằng khách mò vào Cài đặt thì vẫn bấm được.
- Không đụng `so_windows.hide_when_ready`, `wait_for_main_window` hay luồng đóng DAW an toàn,
  trừ phần bỏ điều kiện `is_locked()`.

---

## Phần 2 — Thông báo Tự sửa âm thanh hiển thị trong cửa sổ riêng

### Vì sao

Người ngồi trước máy khi có lỗi là **khách hát**. Họ cần **biết lỗi gì** và **bấm được Tự sửa**.
Hiện nay app chèn một dải viền cam (`_audio_warn_btn`, `ui/panels/header.py`) vào header, bên
trái marquee. Dải này chiếm chỗ nên tên bài và tone bị đẩy hẹp. Trên màn 1366×768, chính câu
cảnh báo cũng bị cắt. Các lỗi còn lại chỉ xem được qua tooltip.

### Hiện trạng (đã đọc code)

- `_on_audio_doctor_report(report, action)` (`frontend_qt.py`) đặt chữ và hiện/ẩn dải cam.
  Nó được gọi từ hai chỗ:
  - lượt kiểm tra lúc mở app (`service.startup_loop`, qua `_audio_doctor_report_signal`);
  - hộp thoại `AudioDoctorDialog._on_finished` (action `"button"`).
- Giọng đọc (TTS) chỉ đọc ở lượt `"run"` đầu tiên.
- `_open_audio_doctor()` mở `AudioDoctorDialog(auto_fix=True)`: mở ra là chạy sửa ngay.

### Thay đổi

Chủ dự án chọn **cửa sổ riêng** thay cho marquee vì đó là cách an toàn nhất. Marquee **không đổi
gì**.

1. **Bỏ dải cam `_audio_warn_btn`.** Marquee luôn có đủ chỗ.
2. **Cửa sổ cảnh báo**: khi lượt kiểm tra lúc mở app (`action == "run"`, cũng như lượt chạy lại
   của `StartupGate` nếu có) thấy lỗi (`report.problems()` khác rỗng), app mở một **cửa sổ
   riêng** nhỏ, nổi trên app:
   - Tiêu đề kiểu "Phát hiện N vấn đề âm thanh".
   - Danh sách từng lỗi (`finding.message`), chữ to, đủ đọc từ xa, không cắt cụt.
   - Nút lớn **"Tự sửa"**: đóng cửa sổ cảnh báo, rồi gọi `_open_audio_doctor()` (hộp thoại
     Tự sửa âm thanh hiện có, `auto_fix=True`).
   - Nút **"Để sau"** (hoặc ✕): đóng cửa sổ.
   - **[quyết định của Claude]** Đây là cửa sổ mới, gọn, dành cho khách. Không mở thẳng
     `AudioDoctorDialog`, vì hộp thoại đó tự sửa ngay khi mở và liệt kê mọi mục kiểm tra kiểu
     kỹ thuật.
   - Cửa sổ không chặn app (non-modal) và được đưa lên trước (`raise_`/`activateWindow`). Lượt
     kiểm tra chỉ chạy sau khi DAW đã sẵn sàng, nhưng DAW có thể giành tiền cảnh. Builder kiểm
     tra để cửa sổ vẫn nổi trên DAW, kể cả khi app đang "Ghim trên cùng" hoặc không ghim.
   - Mỗi lượt kiểm tra chỉ bật **một** cửa sổ. Nếu cửa sổ đang mở thì cập nhật nội dung, không
     mở thêm cái thứ hai.
3. **Nút "Tự sửa âm thanh" ở thanh dưới** (`ui/panels/bottom_bar.py`) có viền hoặc nền cam khi
   lượt kiểm tra gần nhất còn lỗi. Khách bấm "Để sau" thì vẫn còn chỗ này để bấm. Viền cam tắt
   khi `_on_audio_doctor_report` nhận báo cáo không còn lỗi, ví dụ sau khi sửa trong hộp thoại.
4. Hộp thoại Tự sửa âm thanh khi sửa xong vẫn gọi `_on_audio_doctor_report(report, "button")`
   như hiện nay. Lời gọi đó chỉ cập nhật viền cam, **không** bật lại cửa sổ cảnh báo, vì kết
   quả đã hiện ngay trong hộp thoại.
5. Không kiểm tra định kỳ: cửa sổ do người dùng đóng nên không có cảnh báo nào treo lơ lửng.
6. TTS giữ như cũ, chỉ đọc một lần ở lượt kiểm tra đầu. Cửa sổ cảnh báo có `accessibleName`
   và `accessibleDescription` mang nội dung lỗi.
7. Không đổi: marquee, các toast `_show_message`, nội dung kiểm tra và sửa của Tự sửa âm thanh.

---

## Phần 3 — Chọn riêng từng cửa sổ plugin để ẩn/hiện

### Vì sao

KTV cần **mở Auto-Tune để chỉnh**, hoặc **mở bảng điều khiển ASIO**, mà **không hiện cả DAW**.
Hiện nay chỉ có ẩn/hiện tất cả các cửa sổ một lượt.

### Điều kiện đã xác nhận

Các cửa sổ này **đã mở sẵn trong bài mẫu** và chỉ đang bị ẩn. App không cần mở plugin, chỉ cần
bật hoặc tắt hiển thị đúng cửa sổ (HWND) đã có.

### Thay đổi

1. Trong mục "Cửa sổ {DAW}" (Phần 1, mục 8) có **danh sách cửa sổ** đang có của tiến trình DAW
   (`so_windows.all_windows()`):
   - Mỗi dòng gồm tên cửa sổ (`GetWindowText`) và một công tắc Hiện/Ẩn phản ánh
     `IsWindowVisible` thật.
   - Cửa sổ chính (`main_windows()`) đứng đầu, ghi rõ "(cửa sổ chính)".
   - Lọc bỏ các cửa sổ không có tiêu đề và các cửa sổ phụ vô nghĩa (cửa sổ ẩn nội bộ,
     tooltip…). Quy tắc lọc cụ thể cho Studio One và Cubase do builder chốt sau khi liệt kê
     cửa sổ thật trên máy dev.
   - Có nút **"Làm mới"** để quét lại. Danh sách cũng quét lại mỗi lần mở mục này.
2. **Bật một cửa sổ** thì chỉ cửa sổ đó hiện lên và được đưa lên trước (`force_foreground`).
   Cửa sổ chính DAW vẫn ẩn. **Tắt** thì `SW_HIDE` riêng cửa sổ đó.
3. Nút "Hiện/Ẩn tất cả" (Phần 1) tác động mọi cửa sổ **của tiến trình DAW**, không động tới
   công cụ ASIO tiến trình riêng (mục 4). Chữ trên nút cũng chỉ tính cửa sổ DAW. Sau khi bấm thì
   danh sách cập nhật theo. **[quyết định của Claude]**
4. **ASIO**:
   - Nếu bảng ASIO là cửa sổ của tiến trình DAW (bảng driver mở từ DAW, ASIO4ALL…) thì nó tự
     nằm trong danh sách.
   - **[quyết định của Claude]** Danh sách cũng liệt kê cửa sổ của các công cụ ASIO chạy tiến
     trình riêng (ASIO Link Pro, ASIOVADPRO…). Dùng lại danh sách tên tiến trình và từ khoá
     tiêu đề trong `_on_toggle_asiolink` (`frontend_qt.py`, hiện là code chết, không còn ai
     gọi). Những cửa sổ này không bị tự ẩn khi mở app; danh sách chỉ cho bật/tắt chúng.
     `_on_toggle_asiolink` gộp vào cơ chế mới rồi xoá.
5. **Không ghi nhớ** lựa chọn: mỗi lần mở app vẫn ẩn tất cả như Phần 1.
6. Hộp thoại Cài đặt là modal của app, nhưng cửa sổ plugin thuộc tiến trình khác nên KTV vẫn
   thao tác được trên plugin. Nếu app đang bật "Ghim trên cùng" mà plugin bị che: builder kiểm
   tra và xử lý, ví dụ đưa plugin lên với cờ topmost tạm thời hoặc nhắc trong giao diện.

### Rủi ro cần thử trước (spike trên máy dev, cả Studio One và Cubase 13)

Phần 3 **đi cùng bản phát hành này**, không để lại bản sau. Thử trên máy dev trước, rồi làm
theo phương án chạy được: cách 1 nếu được, không thì cách 2.

Cửa sổ plugin có thể là cửa sổ **được sở hữu (owned)** bởi cửa sổ DAW chính. Windows có thể
không hiện, hoặc hiện sai, một cửa sổ owned khi cửa sổ chủ đang `SW_HIDE`. Phải thử thật:

1. Ẩn tất cả, rồi chỉ `SW_SHOW` cửa sổ Auto-Tune. Kiểm tra: plugin có hiện không, có nhận chuột
   và bàn phím không, cửa sổ chính có tự hiện theo không.
2. Nếu không được, phương án dự phòng: hiện cửa sổ chính nhưng dời ra ngoài vùng màn hình
   (hoặc thu nhỏ hay trong suốt), bỏ khỏi thanh tác vụ, rồi trả về vị trí cũ khi ẩn lại.
   Phương án dự phòng phải xử lý: cửa sổ chính đang hiện nhưng nằm ngoài màn hình thì vẫn tính
   là "ẩn" với nút Hiện/Ẩn tất cả, công tắc trong danh sách và bước ẩn khi thoát app. Kiểm tra
   DAW có lưu vị trí ngoài màn hình vào bài hoặc layout không. Có thể mỗi DAW một phương án.
   Chọn phương án nào thì ghi lại kết quả spike vào
   `docs/superpowers/specs/2026-11-02-an-daw-plugin-spike-findings.md`.

---

## Ràng buộc chung

- Làm trên nhánh mới tách từ `feat/velopack-installer`. Nhánh này đã có 1.9.0 chưa phát hành và
  phần 2 micro; cây làm việc hiện có thay đổi chưa commit (net_tls…), nên dùng worktree riêng.
  Số phiên bản quyết định lúc phát hành, theo quy trình phát hành.
- Chạy test bằng Python Windows `.venv` qua `cmd.exe` (xem bộ nhớ dự án). Test cần sửa theo:
  - `tests/core/test_kiosk.py`: xoá hoặc thay bằng test cấu hình mới và test chuyển cấu hình cũ;
  - `tests/ui/test_exit_close_studio_one.py`, `test_settings_daw_kind.py`,
    `test_startup_template_restore.py`: đang patch `core.kiosk.*`.
- Mọi chữ hiển thị tiếng Việt có dấu. Tên DAW lấy từ `daw.active().display_name`.
- Chạy được cả Studio One lẫn Cubase. Mọi chỗ trước đây phân biệt theo `daw.active()` vẫn giữ.

## Để builder tự quyết

- Tên key settings mới, tên module thay `core/kiosk.py`.
- Bố cục và câu chữ cụ thể của cửa sổ cảnh báo (Phần 2).
- Bố cục cụ thể của mục "Cửa sổ {DAW}" trong Cài đặt.
- Quy tắc lọc cửa sổ của Phần 3, sau khi liệt kê thật.
