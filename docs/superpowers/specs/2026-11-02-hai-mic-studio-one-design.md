# Hai micro trên Studio One — thiết kế

Ngày: 2026-11-02 · Trạng thái: đã duyệt (2026-11-02)

## 1. Vì sao

Phòng hát của khách không kín:
- **Ban ngày ồn** → khách hát **micro không dây** (kênh `MIC KG` trong bài mẫu).
- **Ban đêm yên** → khách hát **micro có dây P420** (kênh `MIC  P420`).
- Ngoài ra khách thích **đổi gió**: hát xong bài này thì tắt mic này, hát mic kia.
- **Song ca** → mở cả hai mic cùng lúc.

Hai micro là hai micro thật, cắm hai cổng (P420 = Input L, không dây = Input R). Mỗi micro có
chất âm riêng nên có chuỗi chỉnh riêng.

Bài mẫu đề xuất `vp.song` đã có đủ hai kênh, nhưng app hiện chỉ điều khiển được **một** kênh:
mọi Control Link của thiết bị `QuangLuuMIDI` đều trỏ vào `MIC  P420`; `MIC KG` không nhận gì.
Hệ quả: hát mic không dây thì Key/Scale của Auto-Tune không đổi theo bài → lệch tone.

## 2. Hiện trạng `vp.song` (đã đọc file)

| | MIC  P420 `{3D8A0BCF-…}` | MIC KG `{76405767-…}` |
|---|---|---|
| Đầu vào | Input L | Input R |
| Gain | +2.0 dB | +2.5 dB |
| Chuỗi insert | RVox → Aphex → C1 → Pro-Q 2 → MannyM EQ → CLA-2A → Auto-Tune Pro → Tắt Ồn (NS1) | giống hệt thứ tự (Pro-Q "4" chỉ là Pro-Q 2 đổi tên) |
| Khác về cài đặt | | MannyM EQ khác 4 tham số; còn lại (kể cả Auto-Tune) giống hệt |
| Send | Send01 Vang, Send06 Echo, Send07 Hall, Send04 Main, Send02 Vang 2 | Send01 Vang, Send02 Echo, Send03 Hall, Send04 Main, Send05 Vang 2 (tên send khác!) |
| Control Link `QuangLuuMIDI` | muteMic, muteReverb, muteMulti1–4 (mute các send), keyRoot / keyScale / scaleType (Auto-Tune vstp2 / vstp162), be (Auto-Tune vstp155) | không có |

Cả hai track đều record-arm + monitor, không mute → mở bài là cả hai mic cùng kêu.

## 3. Mục tiêu

1. Trên app có **hai kênh mic riêng** trong mixer, mỗi kênh một thanh mức + một nút bật/tắt.
   Ba trạng thái dùng được: chỉ có dây, chỉ không dây, cả hai (song ca).
2. Mọi thứ thuộc về **giọng hát nói chung** đến **cả hai** kênh mic cùng lúc: Key, Scale,
   Auto-Tune, Fix Méo, Bè, Tắt Ồn, Tone Giọng, Hiệu Ứng Giọng, các MODE, mức Vang và mute
   các send. Mic đang tắt cũng luôn đúng tone, bật lên là hát được ngay.
3. Đồng bộ lại toàn bộ khi Studio One mở bài / báo sẵn sàng (như hiện có) phải gồm cả kênh mic 2.

## 4. Không làm (non-goals)

- **Cubase**: chưa làm hai mic cho Cubase. Script Cubase chỉ nghe MIDI channel 1
  (`MIDI_CHANNEL = 0`) nên tin nhắn channel 2 bị bỏ qua, vô hại. Không sửa script.
- Không dồn Auto-Tune về một bus chung: song ca thì hai giọng vào một Auto-Tune sẽ méo.
- Không làm nút "A/B" một chạm: có trạng thái cả hai cùng mở nên hai nút riêng là đủ.
- Không làm 3+ mic.
- Phím tắt trợ năng (to/nhỏ/tắt mic) vẫn chỉ cho mic 1.

## 5. Phản mục tiêu (hỏng dù chạy được)

- Máy đang dùng **một mic** thấy bất kỳ thay đổi nào (thêm thanh trượt, thêm MIDI lạ, đổi hành vi).
  Tính năng tắt mặc định; tắt thì app gửi y như bây giờ.
- Hai mic lệch tone nhau sau khi đổi bài / dò tone / chỉnh tay, kể cả trong các ca race đã sửa
  gần đây (`bb15fa4`, `b0d46b3`).
- Mic khách không dùng vẫn mở sau khi app khởi động lại (mic không dây nằm trên bàn thu tạp âm,
  dễ hú).

## 6. Cách làm đã chốt

### 6.1 Kênh MIDI 2 = micro 2

Micro 2 dùng **cùng số CC** với micro 1 nhưng trên **MIDI channel 2** (status `0xB1`).
Không đụng bảng CC hiện có, không chiếm CC mới.

- Mic 1 = kênh MIDI 1 (như hiện tại). Mic 2 = kênh MIDI 2.
- Gán trong bài mẫu: mic có dây P420 = Mic 1 (giữ nguyên Control Link hiện có), không dây = Mic 2.

### 6.2 Surface XML

`studio_one/QuangLuuMIDI.surface.xml` thêm một bộ control `status="#B1"` (tên có hậu tố `2`,
vd `keyRoot2`, `muteMic2`) cho các CC liên quan tới mic:

- riêng từng mic: `mix_mic` (21), `mute_mic` (51);
- dùng chung (phát đôi): `tone_voice` 11, `mix_reverb` 22, `mode` / mode toggles 30, 37, 38, 39, 46,
  `key_root` 33, `key_scale` 34, `scale_type` 35, `tune_on_off` 36, `tone_auto` 40,
  `mute_multi` 41–44, `fix_meo` 45, `be` 47, `tat_on` 48, `mute_reverb` 52, `voice_fx` 54.

Không có transmit (chỉ `readyPing` kênh 1 có transmit như cũ). `tests/test_surface_xml.py`
phải kiểm cả bộ kênh 2.

**Một file XML chung cho mọi máy** (Claude tự quyết): bộ kênh 2 chỉ là control *thêm vào*,
máy một mic không gán chúng nên không có tác dụng gì. Audio Doctor (`DawRemoteCheck`, so SHA file
surface) sẽ báo máy một mic "surface cũ" và đề nghị chép bản mới — chấp nhận được **với điều kiện**
chép đè file không làm mất Control Link đã gán trong các bài khách đã lưu.

Control Link trong `.song` lưu theo instance thiết bị (`instanceID`) + tên control. Chưa biết chép
đè XML (không gỡ/thêm lại thiết bị) có giữ nguyên instance hay không → **phải kiểm trên máy thật
trước** (mục 7). Không được hướng dẫn KTV gỡ/thêm lại thiết bị nếu việc đó làm mất gán của bài cũ.

### 6.3 App: phát đôi

- Một chỗ duy nhất quyết định phát đôi (lớp gửi MIDI của engine), không rải `if mic2` khắp UI.
  Khi bật hai mic: mỗi CC thuộc danh sách "dùng chung" ở 6.2 gửi trên kênh 1 xong gửi ngay
  cùng giá trị trên kênh 2.
- Cặp Key + Scale (`send_midi_pair`) vẫn phải nguyên tử: cả bốn tin (key/scale × 2 kênh) gửi trong
  một lần giữ khoá, để không thread nào chen giữa (đây là chỗ từng có race đổi bài).
- `mix_mic` / `mute_mic` **không** phát đôi: thanh/nút Mic 1 gửi kênh 1, thanh/nút Mic 2 gửi kênh 2.
- Danh sách CC dùng chung để trong `app_config` (có mặc định) để khi bài mẫu cần thêm/bớt thì
  sửa cấu hình, không sửa code.
- Phần nhận phản hồi từ DAW (`_listen_loop` → `on_cc_received(cc, value)`) hiện bỏ qua kênh.
  Phải không để tin kênh 2 (nếu sau này có) bị hiểu thành kênh 1.

### 6.4 App: giao diện

- Bật tính năng: cài đặt theo máy `settings["mic_count"]` = 1 (mặc định) hoặc 2, có chỗ bật trong
  phần cài đặt dành cho KTV; tên hiển thị hai mic sửa được (mặc định "Mic Dây" / "Mic Không Dây").
- Bật 2 mic → mixer có thêm **phần mở rộng** (chỉ hiện khi bật 2 mic) chứa kênh "Mic 2", cùng kiểu
  kênh "Mic" (−10…+10 dB, có nút tắt). Tắt 2 mic thì phần này không tồn tại — mixer y như bây giờ.
  (Anh chốt: "có phần mở rộng, tùy chọn khi 2 mic".)
- Đồng bộ lại khi Studio One sẵn sàng (`frontend_qt.py` khối "Mute Mic / Vang / Bè", `_sync_mixer_midi`)
  gửi luôn mức + mute của Mic 2.
- Smart Recall (preset theo bài) lưu/áp mức Mic 2 như mức các kênh mixer khác.

### 6.5 Bài mẫu

`vp.song` **chưa gán xong** (anh xác nhận): hiện chỉ có Key/Scale/Bè/Mute Mic/mute các send cho P420;
thanh Mic, Vang, Tone Giọng, Auto-Tune, Fix Méo, Tắt Ồn, các MODE chưa gán vào đâu.
Việc làm bài mẫu:

1. Gán **đủ** mọi control kênh 1 của app vào `MIC  P420` (thanh Mic → fader track, Tắt Ồn → NS1,
   Auto-Tune / Fix Méo / MODE → tham số tương ứng — theo cách các bài mẫu một mic đang gán).
2. Gán bộ control kênh 2 vào **đúng tham số tương ứng** trên `MIC KG` (lưu ý tên send khác:
   Echo = Send02, Hall = Send03, Vang 2 = Send05 bên KG so với Send06/Send07/Send02 bên P420).
3. Tắt sẵn track mic không dùng mặc định.

Phạm vi hiện tại **một máy** → gán tay trong Studio One trên máy khách (qua UltraViewer), có danh sách
kiểm từng control; không viết công cụ sửa `.song`.

Bài mẫu hai mic (mic không dùng tắt sẵn) **chỉ dành cho máy hai mic**; máy một mic giữ bài mẫu
của mình.

## 7. Rủi ro cần kiểm sớm

- **Chép đè surface XML có giữ Control Link của bài cũ không** (xem 6.2). Kiểm trên một máy
  Studio One thật cùng lúc với rủi ro dưới đây, trước khi viết code app.

- **Studio One có nhận control `status="#B1"` trong surface XML không.** Kiểm đầu tiên trên một
  máy Studio One thật (thêm một control kênh 2, gán thử, gửi CC kênh 2). Nếu không nhận:
  phương án lùi là bộ CC riêng cho mic 2 (dải trống ≥ 55, trừ 60–67 script Cubase đang dùng làm
  phản hồi), giữ nguyên mọi phần còn lại của thiết kế.
- Phát đôi làm số tin MIDI tăng gấp đôi lúc đồng bộ toàn bộ — không đáng kể, nhưng phải giữ đúng
  thứ tự Key/Scale.

## 8. Để người làm tự quyết

- Tên biến/khóa cấu hình cụ thể, chỗ đặt ô bật trong giao diện cài đặt.
- Cách hiển thị kênh Mic 2 khi màn hình hẹp (máy 1366×768).
- Cách Audio Doctor xử lý mic 2 (anh chốt: **có** xử lý). Hiện Audio Doctor tự mở `mute_mic` khi kiểm;
  bật 2 mic thì nó phải hiểu cả mic 2 và không báo sai.

## 9. Các lựa chọn do Claude tự quyết (anh kiểm khi đọc)

- Dùng MIDI channel 2 thay vì CC mới (6.1).
- Mặc định có dây = Mic 1, không dây = Mic 2.
- Hai thanh mức + hai nút riêng thay vì một nút A/B.
- Thanh Vang chung cho cả hai mic (mất phần lệch send rất nhỏ giữa hai kênh trong bài mẫu).
- Nhớ trạng thái bật/tắt từng mic qua lần mở app (xem phản mục tiêu ở mục 5).
- Cubase chưa làm.
- Một surface XML chung cho mọi máy (6.2), với điều kiện kiểm được là không mất gán cũ.
- Bài mẫu hai mic chỉ dùng cho máy hai mic.
- Làm trên nhánh tách từ `feat/velopack-installer` (đã có các bản sửa race Tone Nhạc
  `bb15fa4`, `b0d46b3` mà phần phát đôi phải giữ đúng), trong worktree riêng để không đụng
  các thay đổi chưa commit (net_tls…) đang nằm trong thư mục làm việc.
