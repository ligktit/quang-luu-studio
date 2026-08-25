# Kịch bản test — Chế độ khách & Đóng Studio One an toàn (v1.7.0)

> **Dành cho tester.** Không cần biết lập trình. Làm tuần tự từ trên xuống.
> Mỗi ca test có: **mục tiêu → các bước → kết quả ĐÚNG → dấu hiệu LỖI**.
> Đánh dấu kết quả vào bảng ở [mục 9](#9-bảng-kết-quả).

---

## 1. Tính năng này giải quyết chuyện gì

Phần mềm điều khiển Studio One qua MIDI. Khách hàng phổ thông hay tò mò mở Studio One
ra chỉnh lung tung → sai thông số → phần mềm chạy không đúng nữa. Bản này thêm 3 thứ
**ăn khớp với nhau**:

| # | Tên | Làm gì |
|---|---|---|
| 1 | **Chế độ khách** | Giấu hẳn cửa sổ Studio One khỏi màn hình. Chỉ mở lại được bằng **mã PIN** của kỹ thuật viên |
| 2 | **Bản mẫu .song** | Kỹ thuật viên "chốt" một bản gốc. Mỗi lần mở app, file bài hát bị chép đè lại bằng bản gốc đó → mọi thứ khách chỉnh hôm qua biến mất |
| 3 | **Đóng an toàn** | Lúc thoát app, phần mềm **lưu bài rồi để Studio One tự thoát**, thay vì "giết" nó như bản cũ |

**Vì sao 3 cái này phải đi cùng nhau** (hiểu chỗ này thì test mới đúng trọng tâm):

Bản cũ khi thoát app sẽ ép Studio One tắt bằng lệnh `taskkill` (tắt cứng, như rút điện).
Studio One bị tắt cứng sẽ ghi lại một dấu "lần trước thoát bất thường", nên **lần mở
sau nó hiện cảnh báo đòi phục hồi phiên** và không vào thẳng file đã lưu được.

Bản mới sửa bằng cách bấm **Ctrl+S trước khi đóng**. Bài đã lưu rồi thì Studio One
đóng cái rụp, không hỏi gì → thoát sạch → không còn cảnh báo.

Nhưng nếu chỉ có vậy thì lại lưu luôn cả những thứ khách chỉnh sai. Nên mới cần
**bản mẫu**: dù có lưu gì đi nữa, lần mở app sau file cũng bị chép đè về bản gốc.

---

## 2. Cần chuẩn bị

### 2.1 Máy test

- [ ] Windows 10/11
- [ ] **Đã cài Studio One** (bản 5/6/7 đều được) và đã setup xong như một máy khách thật:
      có External Device `QuangLuuMIDI`, đã MIDI Learn các tham số
- [ ] Có sẵn **một file bài `.song`** dùng làm bài mẫu
- [ ] Bản cài `Setup_QuangLuuStudio_v1.7.0.exe`

### 2.2 ⚠️ SAO LƯU TRƯỚC KHI TEST — bắt buộc

Tính năng "bản mẫu" **chép đè lên file `.song` thật**. Trước khi bắt đầu:

1. Mở thư mục chứa file `.song` của bạn.
2. Copy file đó ra chỗ khác (ví dụ Desktop), đặt tên `BaiHat_BACKUP.song`.

Nếu test hỏng file, lấy bản backup này chép về là xong.

### 2.3 Ba đường dẫn cần nhớ

Mở **File Explorer**, gõ vào thanh địa chỉ:

| Gõ vào thanh địa chỉ | Trong đó có gì |
|---|---|
| `%APPDATA%\QuangLuuStudio` | `settings.json` — toàn bộ thiết lập |
| `%APPDATA%\QuangLuuStudio\logs` | `app.log` — nhật ký chạy, dùng để báo lỗi |
| `%APPDATA%\QuangLuuStudio\so_template` | Bản mẫu `.song` đã chốt (chỉ có sau khi bấm "Chốt bản mẫu") |

### 2.4 Cài đặt ban đầu

1. Chạy `Setup_QuangLuuStudio_v1.7.0.exe`, cài như bình thường.
2. Mở app, kích hoạt (nếu được hỏi).
3. Vào **Cài đặt** (nút bánh răng ⚙ trên thanh tiêu đề) → tab **Hệ thống**:
   - Ô **"Studio One (.song hoặc .exe)"**: bấm nút thư mục 📁, chọn **file `.song`** của bạn.
     > Quan trọng: phải chọn file **`.song`**, không phải `StudioOne.exe`. Chọn `.exe`
     > thì tính năng bản mẫu sẽ không hoạt động (đúng thiết kế).
   - Tích **"Mở Studio One khi khởi động"**
   - Tích **"Đóng Studio One khi thoát"**
4. Bấm **Lưu thiết lập**.

---

## 3. Nhóm A — Mã PIN và bật chế độ khách

### A1. Không đặt được PIN quá ngắn

**Mục tiêu:** PIN phải tối thiểu 4 ký tự.

1. Cài đặt → **Hệ thống** → kéo xuống mục **"Chế độ khách — khoá Studio One"**.
2. Bấm nút **Đặt mã PIN**.
3. Nhập `12` vào cả 2 ô → bấm **Lưu PIN**.

✅ **ĐÚNG:** Hiện chữ đỏ *"Mã PIN phải có ít nhất 4 ký tự"*, hộp thoại **không** đóng.

❌ **LỖI:** Hộp thoại đóng lại / app văng.

---

### A2. Hai lần nhập không khớp thì không lưu

1. Vẫn ở hộp thoại đó, nhập `1234` ở ô trên, `5678` ở ô dưới → **Lưu PIN**.

✅ **ĐÚNG:** Hiện chữ đỏ *"Hai lần nhập không khớp"*, hộp thoại không đóng.

---

### A3. Đặt PIN thành công

1. Nhập `1234` vào **cả hai** ô → **Lưu PIN**.

✅ **ĐÚNG:**
- Hộp thoại đóng lại
- Thanh thông báo dưới màn hình chính hiện *"Đã lưu mã PIN kỹ thuật"*
- Nút vừa bấm giờ đổi chữ thành **"Đổi mã PIN"**

---

### A4. PIN được lưu dạng băm, không lưu thô

**Mục tiêu:** người khác mở file thiết lập cũng không đọc được PIN.

1. Mở File Explorer → gõ `%APPDATA%\QuangLuuStudio` → mở `settings.json` bằng Notepad.
2. Bấm `Ctrl+F`, tìm chữ `tech_lock`.

✅ **ĐÚNG:** Thấy đoạn giống thế này — có `pin_hash` và `pin_salt` là chuỗi ký tự dài
loằng ngoằng, **không thấy số `1234` ở đâu cả**:

```json
"tech_lock": {
    "pin_salt": "a3f9...",
    "pin_hash": "7c21...",
    "iterations": 260000
}
```

❌ **LỖI:** Nhìn thấy `"pin": "1234"` hoặc bất kỳ chỗ nào chứa `1234`.

> Đóng Notepad lại, **đừng sửa gì**.

---

### A5. Bật chế độ khách

1. Quay lại Cài đặt → mục Chế độ khách.
2. Tích ô **"Bật chế độ khách (ẩn hẳn Studio One khỏi giao diện)"**.

✅ **ĐÚNG:**
- Dòng chữ trên cùng của mục đổi từ *"Đang TẮT..."* (xám) thành
  **"Đang KHOÁ — Studio One bị ẩn khỏi khách..."** (màu cam)
- Tất cả các ô tích và nút trong mục này **bị mờ đi, bấm không được**
- Xuất hiện nút cam **"Mở khoá kỹ thuật"**
- Nếu Studio One đang chạy → **cửa sổ Studio One biến mất khỏi màn hình ngay lập tức**

---

### A6. Nút mắt biến mất khỏi thanh tiêu đề

**Bối cảnh:** trên thanh tiêu đề của app có nút hình con mắt 👁 để ẩn/hiện Studio One.
Chế độ khách phải **gỡ hẳn** nút này, không phải chỉ làm mờ.

1. Đóng hộp thoại Cài đặt (nút **Hủy** hoặc **Lưu thiết lập**).
2. Nhìn góc phải thanh tiêu đề app, cạnh nút bánh răng ⚙.

✅ **ĐÚNG:** **Không còn** nút hình con mắt.

3. Bấm phím `Tab` liên tục khoảng 20 lần, quan sát viền sáng chạy quanh các nút.

✅ **ĐÚNG:** Viền sáng **không bao giờ** dừng ở vị trí nút mắt cũ.

❌ **LỖI:** Nút mắt vẫn còn (dù mờ), hoặc bấm Tab vẫn tới được nó.

---

## 4. Nhóm B — Studio One có thật sự bị giấu không

### B1. Ẩn khỏi thanh tác vụ và Alt+Tab

**Chuẩn bị:** Studio One đang chạy, chế độ khách **đang bật** (đã làm A5).

1. Nhìn **thanh tác vụ** (taskbar) dưới cùng màn hình.
2. Giữ `Alt` rồi bấm `Tab` vài lần để xem danh sách cửa sổ.
3. Bấm `Windows + Tab` (chế độ xem tổng quan).

✅ **ĐÚNG:** Studio One **không xuất hiện** ở cả 3 chỗ.

❌ **LỖI:** Còn thấy Studio One ở bất kỳ chỗ nào.

---

### B2. Studio One vẫn chạy và vẫn nhận lệnh MIDI

**Mục tiêu:** giấu cửa sổ chứ không phải tắt chương trình — âm thanh phải vẫn chạy.

1. Bấm `Ctrl + Shift + Esc` mở **Task Manager** → tab **Chi tiết** (Details).
2. Tìm dòng `Studio One.exe`.

✅ **ĐÚNG:** Vẫn còn trong danh sách (chương trình vẫn chạy, chỉ là không thấy cửa sổ).

3. Quay lại app, kéo thanh trượt **Nhạc** / **Mic** / **Vang**, bấm các nút chế độ
   (Dân Ca, Lofi...).

✅ **ĐÚNG:** Âm thanh thay đổi bình thường, đèn MIDI trên thanh tiêu đề vẫn **xanh**.

❌ **LỖI:** Đèn MIDI đỏ, hoặc kéo thanh trượt không có tác dụng gì.

---

### B3. Cửa sổ plugin cũng bị giấu theo

1. Mở khoá kỹ thuật (`Ctrl + Alt + Shift + T`, nhập `1234`).
2. Trong Studio One, mở vài cửa sổ plugin (Auto-Tune, Reverb...) cho nó **nổi riêng ra
   ngoài** (cửa sổ rời, không dính vào cửa sổ chính).
3. Bấm lại `Ctrl + Alt + Shift + T` để khoá.

✅ **ĐÚNG:** **Tất cả** cửa sổ plugin biến mất cùng lúc với cửa sổ chính.

❌ **LỖI:** Cửa sổ chính biến mất nhưng plugin còn nổi lơ lửng trên màn hình.

---

### B4. Giấu ngay từ lúc khởi động

1. Thoát hẳn app (và Studio One nếu còn chạy).
2. Mở lại app.
3. **Bấm đồng hồ**: Studio One nạp bài mất bao lâu, và sau khi cửa sổ nó hiện ra thì
   bao lâu sau nó bị giấu đi.

✅ **ĐÚNG:** Cửa sổ Studio One hiện ra trong lúc nạp bài, rồi **tự biến mất** sau khi
nạp xong. (Việc còn thấy nó trong lúc nạp là **bình thường, không phải lỗi** — xem
[mục 8](#8-những-thứ-không-phải-lỗi).)

4. Chờ thêm 1 phút, xem có cửa sổ Studio One nào tự mọc lại không.

✅ **ĐÚNG:** Không có gì mọc lại.

📋 **Ghi lại:** Studio One nạp mất bao nhiêu giây? Có bị giấu không? _______

---

### B5. Khách tự mở Studio One (tuỳ chọn — mặc định TẮT)

**Bối cảnh:** mặc định app chỉ giấu Studio One do chính nó mở. Nếu khách bấm shortcut
Studio One ngoài desktop thì app **không đụng tới** — trừ khi bật thêm tuỳ chọn.

**Phần 1 — mặc định (không bật tuỳ chọn):**

1. Đang ở chế độ khách. Bấm đúp shortcut Studio One trên desktop / Start Menu.

✅ **ĐÚNG:** Studio One mở ra bình thường và **KHÔNG bị giấu**. Đây là **hành vi đúng
theo thiết kế**, không phải lỗi.

**Phần 2 — bật tuỳ chọn:**

2. Đóng Studio One vừa mở.
3. Mở khoá kỹ thuật → Cài đặt → mục Chế độ khách → tích
   **"Ẩn lại cả khi khách tự mở Studio One (quét nền)"**.
4. Khoá lại (`Ctrl + Alt + Shift + T`).
5. Lại bấm đúp shortcut Studio One trên desktop.

✅ **ĐÚNG:** Studio One vừa hiện lên đã **bị giấu đi trong vòng ~2 giây**.

📋 **Ghi lại:** mất bao lâu để nó bị giấu? _______

---

## 5. Nhóm C — Phiên kỹ thuật

### C1. Mở khoá bằng phím tắt

1. Đang ở chế độ khách (Studio One đang bị giấu).
2. Bấm `Ctrl + Alt + Shift + T`.

✅ **ĐÚNG:** Hiện hộp thoại **"Mở khoá kỹ thuật"** có ô nhập PIN.

3. Nhập `1234` → bấm **Mở khoá** (hoặc phím `Enter`).

✅ **ĐÚNG:**
- Hộp thoại đóng
- **Cửa sổ Studio One hiện lại và nhảy lên trước màn hình**
- Trên thanh tiêu đề app xuất hiện **huy hiệu cam "KỸ THUẬT"**
- Nút mắt 👁 **xuất hiện trở lại**
- Thanh thông báo hiện *"Mở khoá kỹ thuật 20 phút"*

---

### C2. Nhập sai PIN

1. Khoá lại (`Ctrl + Alt + Shift + T`).
2. Bấm `Ctrl + Alt + Shift + T`, nhập `9999` → **Mở khoá**.

✅ **ĐÚNG:** Hiện chữ đỏ *"Mã PIN không đúng"*, ô nhập bị xoá trắng, **không mở khoá**.

---

### C3. Sai 5 lần thì bị chặn tạm

1. Nhập sai PIN thêm 4 lần nữa (tổng cộng 5 lần sai).

✅ **ĐÚNG:** Sau lần thứ 5:
- Ô nhập PIN và nút **Mở khoá** bị mờ, bấm không được
- Hiện dòng đỏ *"Nhập sai quá nhiều — thử lại sau 60 giây"*
- **Số giây đếm lùi mỗi giây**: 60, 59, 58...

2. Chờ hết 60 giây.

✅ **ĐÚNG:** Ô nhập tự sáng lại, nhập `1234` vào mở được bình thường.

📋 **Ghi lại:** đồng hồ có đếm lùi đúng không? _______

---

### C4. Khoá lại bằng phím tắt

1. Đang trong phiên kỹ thuật (có huy hiệu KỸ THUẬT).
2. Bấm `Ctrl + Alt + Shift + T`.

✅ **ĐÚNG:**
- Studio One biến mất ngay
- Huy hiệu **KỸ THUẬT** biến mất
- Nút mắt 👁 biến mất
- Thanh thông báo hiện *"Đã khoá lại — Studio One ẩn khỏi khách"*

---

### C5. Đóng app là khoá lại

**Mục tiêu:** không thể "quên mở khoá qua đêm".

1. Mở khoá kỹ thuật.
2. Thoát app hoàn toàn (chờ nó đóng xong).
3. Mở lại app.

✅ **ĐÚNG:** App khởi động ở trạng thái **đang khoá** — không có huy hiệu KỸ THUẬT,
không có nút mắt, Studio One bị giấu.

---

### C6. Hết giờ thì tự khoá lại (test dài ~21 phút)

> Ca này tốn thời gian, có thể để chạy nền trong lúc làm việc khác.

**Rút ngắn:** mở khoá → Cài đặt → mục Chế độ khách → đổi
**"Phiên kỹ thuật tự khoá lại sau"** thành `10 phút`. Vẫn phải chờ 10 phút.

1. Mở khoá kỹ thuật. Ghi lại giờ bắt đầu: _______
2. Để yên máy (vẫn dùng app bình thường được).
3. Chờ hết thời lượng đã chọn.

✅ **ĐÚNG:** Trong vòng **5 giây** sau khi hết giờ:
- Studio One tự biến mất
- Huy hiệu KỸ THUẬT và nút mắt biến mất
- Thanh thông báo hiện *"Hết phiên kỹ thuật — đã khoá lại Studio One"*

📋 **Ghi lại:** giờ tự khoá thực tế: _______

---

### C7. Nút mở khoá trong Cài đặt

**Mục tiêu:** kỹ thuật viên không nhớ phím tắt vẫn mở được.

1. Đang ở chế độ khách. Vào Cài đặt → **Hệ thống** → mục Chế độ khách.
2. Bấm nút cam **Mở khoá kỹ thuật**, nhập `1234`.

✅ **ĐÚNG:** Các ô tích trong mục sáng trở lại, dòng trạng thái đổi thành
**"Đang MỞ KHOÁ — còn 20 phút rồi tự khoá lại."** (màu xanh lá), nút "Mở khoá kỹ
thuật" biến mất.

---

## 6. Nhóm D — Bản mẫu .song

> Nhắc lại: đảm bảo đã backup file `.song` theo [mục 2.2](#22--sao-lưu-trước-khi-test--bắt-buộc).

### D1. Chốt bản mẫu

1. Mở khoá kỹ thuật.
2. Trong Studio One, chỉnh **một thứ dễ nhận ra** — ví dụ kéo fader kênh Nhạc xuống
   hẳn, hoặc đổi tên một kênh thành `BAN GOC`.
3. Bấm `Ctrl + S` trong Studio One để lưu.
4. **Đóng hẳn Studio One** (bắt buộc — không đóng thì không chốt được).
5. Quay lại app → Cài đặt → mục Chế độ khách → bấm **Chốt bản mẫu .song**.

✅ **ĐÚNG:**
- Thanh thông báo hiện *"Đã chốt bản mẫu Studio One"*
- Dòng chữ nhỏ trong mục đổi thành
  *"Bản mẫu đã chốt lúc 2026-08-11 14:30:00 (xxxx KB) — nguồn: D:\...\BaiHat.song"*

6. Mở File Explorer → gõ `%APPDATA%\QuangLuuStudio\so_template`.

✅ **ĐÚNG:** Có 2 file: `template.song` và `template.json`.

---

### D2. Không chốt được khi Studio One đang mở

1. Mở Studio One lên.
2. Bấm **Chốt bản mẫu .song**.

✅ **ĐÚNG:** Thanh thông báo hiện chữ đỏ *"Hãy đóng Studio One trước khi chốt bản mẫu"*.

---

### D3. ⭐ Chỉnh sai của khách bị xoá khi mở lại app

**Đây là ca test quan trọng nhất của nhóm D.**

1. Mở khoá kỹ thuật (nếu chưa). Studio One đang mở.
2. Đóng vai khách phá bĩnh: **chỉnh loạn lên** — kéo mấy fader lung tung, tắt vài
   plugin, đổi tên kênh `BAN GOC` thành `KHACH DA PHA`.
3. Bấm `Ctrl + S` trong Studio One để **lưu lại** những thứ vừa phá.
4. **Thoát app** (app sẽ tự đóng Studio One — chờ nó xong).
5. **Mở lại app**, chờ Studio One nạp xong bài.
6. Nhìn kỹ Studio One.

✅ **ĐÚNG:** Mọi thứ vừa phá **đã biến mất**. Kênh vẫn tên `BAN GOC`, fader về đúng vị
trí lúc chốt bản mẫu.

❌ **LỖI:** Vẫn thấy `KHACH DA PHA` hoặc fader vẫn ở vị trí đã phá.

7. Mở `%APPDATA%\QuangLuuStudio\logs\app.log` bằng Notepad, bấm `Ctrl+End` để nhảy
   xuống cuối, tìm chữ `bản mẫu`.

✅ **ĐÚNG:** Có dòng chứa `Đã phục hồi bản mẫu .song`.

---

### D4. Có phao cứu sinh khi kỹ thuật viên quên chốt

**Bối cảnh:** kỹ thuật viên chỉnh xong mà quên bấm "Chốt bản mẫu" → lần mở sau công
sức bị chép đè mất. Phần mềm giữ lại một bản của cái vừa bị đè.

1. Vào `%APPDATA%\QuangLuuStudio\so_template`.

✅ **ĐÚNG:** Sau ca D3, có thêm file `replaced.song` — đây chính là bản "đã bị phá" ở
bước D3, còn giữ lại được.

---

### D5. Tắt tính năng phục hồi

1. Mở khoá → Cài đặt → **bỏ tích** *"Phục hồi bản mẫu .song mỗi lần khởi động"*.
2. Lặp lại ca D3 (phá → lưu → thoát app → mở lại).

✅ **ĐÚNG:** Lần này những thứ đã phá **vẫn còn** (vì đã tắt phục hồi).

3. **Tích lại** ô đó sau khi test xong.

---

### D6. Đường dẫn là .exe thì bỏ qua, không gây lỗi

1. Cài đặt → đổi ô **"Studio One (.song hoặc .exe)"** thành file `StudioOne.exe`
   (thường ở `C:\Program Files\PreSonus\Studio One 6\Studio One.exe`) → **Lưu thiết lập**.
2. Bấm **Chốt bản mẫu .song**.

✅ **ĐÚNG:** Báo lỗi nhẹ nhàng *"Chốt bản mẫu lỗi: Đường dẫn Studio One không phải file .song"*.
App **không** văng.

3. Thoát và mở lại app.

✅ **ĐÚNG:** App chạy bình thường, không văng, không báo lỗi gì thêm.

4. **Đổi lại** ô đường dẫn về file `.song` → **Lưu thiết lập**.

---

## 7. Nhóm E — ⭐ Đóng Studio One an toàn (quan trọng nhất)

> Đây là phần sửa lỗi chính của bản này. Test kỹ nhất ở đây.

### E1. So sánh với bản cũ (làm 1 lần để thấy sự khác biệt)

**Mục tiêu:** thấy tận mắt cảnh báo mà bản mới phải làm biến mất.

1. Mở Studio One (qua app hoặc mở tay).
2. Mở **Task Manager** → tab Chi tiết → chuột phải `Studio One.exe` → **End task**
   (đây chính là cách bản cũ tắt Studio One).
3. Mở lại Studio One.

✅ **Quan sát:** Studio One hiện **cảnh báo đòi phục hồi phiên** (đại loại
*"Studio One did not shut down properly"* / hỏi có khôi phục bài không).

📋 **Chụp màn hình cảnh báo này lại.** Đây là thứ bản mới phải làm hết.

4. Bấm qua cảnh báo, đóng Studio One bình thường.

---

### E2. ⭐ Thoát app → Studio One đóng sạch

1. Đảm bảo Cài đặt đã tích **"Đóng Studio One khi thoát"**.
2. Mở app, chờ Studio One nạp xong.
3. Chỉnh vài thứ trong Studio One (để nó có thay đổi chưa lưu).
4. **Thoát app** (bấm dấu ✕ trên cửa sổ app).

✅ **ĐÚNG — quan sát theo thứ tự:**
- Hiện hộp thoại **"Đang đóng Studio One an toàn"** có thanh chạy xanh
- Dòng trạng thái đổi lần lượt:
  `Đang lưu bài trong Studio One...` → `Đã lưu bài` → `Đang đóng Studio One...`
  → `Studio One đã thoát sạch`
- Cửa sổ Studio One nhảy lên trước một lát (bình thường — phần mềm cần đưa nó lên
  để gõ Ctrl+S)
- Hộp thoại tự đóng, app thoát

📋 **Ghi lại:** toàn bộ quá trình mất bao nhiêu giây? _______

5. Mở Task Manager, kiểm tra không còn `Studio One.exe`.

✅ **ĐÚNG:** Không còn.

6. **Mở Studio One lên bằng tay.**

✅ **ĐÚNG:** **KHÔNG hiện cảnh báo phục hồi phiên** ở E1. Vào thẳng bài luôn.

❌ **LỖI NGHIÊM TRỌNG:** Vẫn hiện cảnh báo đó → tính năng chính chưa đạt.
Chụp màn hình + gửi kèm `app.log`.

---

### E3. Không còn tắt cứng khi quá hạn

**Mục tiêu:** nếu Studio One không chịu đóng, phần mềm **để yên** chứ không giết nó.

1. Mở app + Studio One.
2. Trong Studio One, mở một hộp thoại chặn ngang, ví dụ menu **Studio One → Options**
   (hoặc Preferences), **để nguyên hộp thoại đó mở**.
3. Thoát app.

✅ **ĐÚNG:** Sau khoảng 45 giây:
- Dòng trạng thái hiện *"Studio One chưa đóng xong — để nguyên cho an toàn, vui lòng đóng tay"*
- App thoát
- **Studio One VẪN CÒN CHẠY** (kiểm tra Task Manager)

❌ **LỖI:** Studio One bị tắt mất (nghĩa là vẫn còn tắt cứng ở đâu đó).

4. Đóng hộp thoại Options, đóng Studio One bằng tay.

📋 **Ghi lại:** chờ đúng ~45 giây chứ? _______

---

### E4. Nút "Bỏ qua, thoát ngay"

1. Mở app + Studio One. Thoát app.
2. Khi hộp thoại "Đang đóng Studio One an toàn" hiện ra, bấm ngay
   **"Bỏ qua, thoát ngay"**.

✅ **ĐÚNG:** Hộp thoại đóng gần như tức thì, app thoát, Studio One **vẫn chạy tiếp**.

3. Làm lại, nhưng lần này bấm phím `Esc` thay vì bấm nút.

✅ **ĐÚNG:** Kết quả giống hệt.

---

### E5. Đóng an toàn khi Studio One đang bị giấu

**Mục tiêu:** đang ở chế độ khách thì Studio One bị giấu — phần mềm phải hiện nó lên
để gõ Ctrl+S rồi mới đóng được.

1. Bật chế độ khách, khoá lại, Studio One đang bị giấu.
2. Thoát app.

✅ **ĐÚNG:**
- Cửa sổ Studio One **hiện lên trong chốc lát** rồi đóng hẳn
- Hộp thoại chạy đủ các bước như E2
- Mở lại Studio One bằng tay → **không có cảnh báo phục hồi**

---

### E6. Không tích "Đóng Studio One khi thoát" thì không đụng vào

1. Cài đặt → **bỏ tích** *"Đóng Studio One khi thoát"* → **Lưu thiết lập**.
2. Thoát app.

✅ **ĐÚNG:** **Không** hiện hộp thoại nào, app thoát ngay, Studio One chạy tiếp.

3. **Tích lại** ô đó sau khi test xong.

---

## 8. Những thứ KHÔNG phải lỗi

Đừng báo mấy cái này — đều là lựa chọn có chủ đích:

| Hiện tượng | Vì sao không phải lỗi |
|---|---|
| `Ctrl + Shift + D` (Dev Mode) vẫn mở được khi đang khoá | Phạm vi khoá lần này **chỉ gồm nút mắt**, cố ý không chặn Dev Mode |
| Ô đường dẫn Studio One trong Cài đặt không bị khoá | Cùng lý do trên |
| Khách tự mở Studio One từ desktop thì không bị giấu | Đúng, trừ khi bật tuỳ chọn *"Ẩn lại cả khi khách tự mở"* (ca B5) |
| Thấy cửa sổ Studio One trong lúc nó nạp bài lúc khởi động | Phần mềm chỉ giấu được sau khi cửa sổ đã hiện ra. Có khe hở này |
| Cửa sổ Studio One nhảy lên trước một lát khi thoát app | Bắt buộc — phải đưa nó lên trước mới gõ được `Ctrl+S` |
| Quên PIN thì không có cách nào mở | Đúng thiết kế, xem [mục 10](#10-xử-lý-sự-cố) |
| Bản mẫu chỉ chép file `.song`, không chép file thu âm rời | Đúng thiết kế, ghi trong `docs/KIOSK_MODE_GUIDE.md` |

---

## 9. Bảng kết quả

| Ca | Nội dung | Đạt | Không đạt | Ghi chú |
|---|---|:---:|:---:|---|
| A1 | PIN quá ngắn bị từ chối | ☐ | ☐ | |
| A2 | Hai lần nhập không khớp | ☐ | ☐ | |
| A3 | Đặt PIN thành công | ☐ | ☐ | |
| A4 | PIN lưu dạng băm | ☐ | ☐ | |
| A5 | Bật chế độ khách | ☐ | ☐ | |
| A6 | Nút mắt biến mất + Tab không tới | ☐ | ☐ | |
| B1 | Ẩn khỏi taskbar + Alt+Tab | ☐ | ☐ | |
| B2 | Vẫn chạy, MIDI vẫn xanh | ☐ | ☐ | |
| B3 | Plugin cũng bị giấu | ☐ | ☐ | |
| B4 | Giấu ngay từ lúc khởi động | ☐ | ☐ | ..... giây |
| B5 | Watchdog khi khách tự mở | ☐ | ☐ | |
| C1 | Mở khoá bằng phím tắt | ☐ | ☐ | |
| C2 | Nhập sai PIN | ☐ | ☐ | |
| C3 | Sai 5 lần bị chặn 60s | ☐ | ☐ | |
| C4 | Khoá lại bằng phím tắt | ☐ | ☐ | |
| C5 | Đóng app là khoá lại | ☐ | ☐ | |
| C6 | Hết giờ tự khoá | ☐ | ☐ | |
| C7 | Nút mở khoá trong Cài đặt | ☐ | ☐ | |
| D1 | Chốt bản mẫu | ☐ | ☐ | |
| D2 | Không chốt khi SO đang mở | ☐ | ☐ | |
| **D3** | **Chỉnh sai của khách bị xoá** | ☐ | ☐ | |
| D4 | Có file replaced.song | ☐ | ☐ | |
| D5 | Tắt phục hồi được | ☐ | ☐ | |
| D6 | Đường dẫn .exe không gây lỗi | ☐ | ☐ | |
| E1 | (đối chiếu) tắt cứng → có cảnh báo | ☐ | ☐ | |
| **E2** | **Thoát app → SO đóng sạch, mở lại KHÔNG cảnh báo** | ☐ | ☐ | ..... giây |
| E3 | Quá hạn không tắt cứng | ☐ | ☐ | |
| E4 | Nút Bỏ qua / phím Esc | ☐ | ☐ | |
| E5 | Đóng an toàn khi đang bị giấu | ☐ | ☐ | |
| E6 | Không tích thì không đụng vào | ☐ | ☐ | |

**Hai ca in đậm (D3, E2) là mục tiêu chính của bản này — nếu hai ca đó fail thì
coi như bản build chưa đạt.**

---

## 10. Xử lý sự cố

| Tình huống | Cách xử lý |
|---|---|
| **Quên PIN, không mở khoá được** | Thoát app. Mở `%APPDATA%\QuangLuuStudio\settings.json` bằng Notepad, xoá cả cụm `"tech_lock": { ... }` (nhớ xoá cả dấu phẩy thừa), lưu lại. Mở app → chế độ khách tắt hẳn |
| **Studio One bị giấu mà app đã đóng** | Task Manager → End task `Studio One.exe`, rồi mở lại |
| **File .song hỏng sau khi test** | Chép `BaiHat_BACKUP.song` (mục 2.2) đè lại. Hoặc lấy `%APPDATA%\QuangLuuStudio\so_template\replaced.song` |
| **Muốn xoá sạch để test lại từ đầu** | Thoát app → xoá thư mục `%APPDATA%\QuangLuuStudio\so_template` → xoá cụm `"tech_lock"` trong `settings.json` |
| **App văng** | Lấy cả 2 file `app.log` và `errors.log` trong `%APPDATA%\QuangLuuStudio\logs` |

---

## 11. Cách báo lỗi

Copy mẫu này, điền vào, gửi kèm ảnh chụp màn hình và file `app.log`:

```
Mã ca test: (vd E2)
Phiên bản:  1.7.0
Studio One: (vd Studio One 6.5 Professional)
Windows:    (vd Win 11 24H2)

Tôi đã làm:
  1.
  2.
  3.

Kết quả mong đợi (theo tài liệu):

Kết quả thực tế:

Có lặp lại được không:  Có / Không / Thỉnh thoảng  (thử 3 lần)
```

**Cách lấy log:**
1. Thoát app trước (log được ghi xong khi thoát).
2. File Explorer → gõ `%APPDATA%\QuangLuuStudio\logs` → Enter.
3. Copy `app.log` và `errors.log` ra Desktop rồi gửi kèm.

**Các dòng log đáng chú ý** (dùng `Ctrl+F` trong Notepad để tìm):

| Tìm chữ | Ý nghĩa |
|---|---|
| `Đã ẩn ... cửa sổ Studio One` | Đã giấu thành công |
| `Đã phục hồi bản mẫu` | Bản mẫu đã được chép đè |
| `Đã lưu bài` | Ctrl+S lúc thoát đã chạy |
| `Studio One đã thoát sạch` | ✅ Đóng an toàn thành công |
| `Không giành được focus — bỏ qua bước lưu` | ⚠️ Không gõ được Ctrl+S — **báo lỗi kèm log** |
| `Studio One chưa đóng xong` | Quá hạn chờ (ca E3) |
| `Quá hạn chờ — buộc phải tắt cứng` | ⚠️ Không được xuất hiện ở cấu hình mặc định — **báo lỗi** |

---

*Tài liệu kỹ thuật đầy đủ (dành cho lập trình viên): `docs/KIOSK_MODE_GUIDE.md`*
