# Kế hoạch: Hiển thị tone theo timeline lúc đang phát

Trạng thái: **P0–P2 ĐÃ LÀM XONG** (2026-08-23) — P4/P5 còn để ngỏ
Ngày: 2026-08-23

**Quyết định đã chốt:**

1. Ô tone lớn thay hẳn combobox; Trưởng/Thứ thành **nút gạt một chạm**.
2. Marquee hiện **tone hiện tại + kế tiếp**, không in cả chuỗi 20 đoạn.
3. Đếm ngược **cả số giây lẫn thanh vơi dần** — chung một con số, chữ cho người
   cần chính xác, thanh cho người chỉ liếc.
4. Chớp sáng khi đổi tone: **bật mặc định** (tự tắt ở chế độ kiosk).

Nhờ quyết định (2), phần P3 (`set_highlight` cho marquee) **không cần làm nữa** —
không còn chuỗi dài để đánh dấu.
Liên quan: `core/engine/_autokey.py` (replay), `frontend_qt.py::_handle_tone_result`,
`ui/panels/header.py`, `ui/components/marquee.py`, `ui/components/waveform_hero.py`

---

## 1. Vấn đề (đã đo, không phải suy đoán)

Dựng UI offscreen rồi bắn đúng loại sự kiện mà vòng replay gửi lên:

| Sự kiện | `tone_combo` | Chữ chạy (marquee) |
|---|---|---|
| Dò xong toàn bài | `G` | `🎵 title ★ G → Em` |
| Chuyển tone lúc phát (`time=18.5`, Em) | `E` ✅ đổi | `🎵 title ★ G → Em` ❌ đứng yên |

Ba khiếm khuyết:

1. **Marquee bị khoá cứng.** `frontend_qt.py:1448` — `if 'time' not in result:` — mọi entry
   replay đều có `time` nên marquee không bao giờ cập nhật. Nó hiện **cả chuỗi tĩnh**
   `G → Em → G → …` suốt bài, không chỉ ra đang ở đoạn nào.
2. **Chỗ duy nhất có đổi lại là chỗ khó thấy nhất.** `tone_combo` là combobox cao 28px ở góc
   phải header (`ui/panels/header.py:72`). Người hát đứng cách màn hình 2m không nhận ra.
3. **Không có "sắp tới".** Người chỉnh cần biết *sắp đổi sang tone gì, còn bao lâu* để chuẩn
   bị, chứ không phải biết sau khi đã đổi rồi.

Lỗi phụ đi kèm:

- `frontend_qt.py:1426` gọi `set_song_info(title, …)` với `title=''` ở sự kiện replay →
  **xoá trắng tên bài** trên waveform hero mỗi lần đổi tone.
- `ui/components/waveform_hero.py:637` in cứng `"2:34 / 4:12"` — thanh thời gian là hàng giả.

---

## 2. Người dùng thật cần gì

| Vai | Khoảng cách nhìn | Cần |
|---|---|---|
| Người hát | 1.5–3m, liếc giữa câu hát | Tone hiện tại, to, đọc trong 1 giây |
| Kỹ thuật viên | ngồi trước máy | Toàn cảnh chuỗi tone + đoạn đang chạy + báo trước khi đổi |
| Chủ quán (kiosk) | không thao tác | Không rối, không nhấp nháy gây khó chịu |

**Nguyên tắc:**

- **Một tiêu điểm.** Tone hiện tại là thứ to nhất; "sắp tới" là phụ; cả chuỗi là nền.
- **Báo trước, không báo sau.** Đếm ngược 5 giây trước điểm đổi.
- **Đổi tone phải *thấy được*** — chuyển động/chớp sáng đúng một lần, không nhấp nháy liên tục.
- **Không phá layout hiện có.** Tận dụng header + marquee sẵn có, không thêm cửa sổ mới.

---

## 3. Kiến trúc: một nguồn sự thật + một nhịp đồng hồ

Hiện UI chỉ là bên nhận sự kiện rời rạc; nó **không giữ timeline lẫn vị trí phát**.
Thêm vào `MainDashboard`:

```python
self._tone_timeline = []      # list entry đã sắp xếp theo time
self._tone_index    = -1      # đoạn đang chạy
self._tone_position = 0.0     # giây, cập nhật theo nhịp
self._tone_duration = 0.0
```

**Nạp timeline** — 3 chỗ, đều đã có sẵn dữ liệu trong tay:

- `frontend_qt.py:1819` và `ui/dialogs/songs_list.py:398` đã đọc `manual_tl` để truyền cho
  engine → gán luôn `dash._tone_timeline = manual_tl`.
- `_handle_tone_result` khi kết quả có `result['timeline']` (dò xong toàn bài).

**Nhịp vị trí** — `QTimer` 250ms, **chỉ chạy khi đang phát** (dừng hẳn khi không, để không tốn
CPU lúc nhàn rỗi). Nguồn vị trí theo đúng thứ tự ưu tiên đã dùng ở `_music_is_playing`
(`frontend_qt.py:1550`):

1. Player nhúng: `KaraokePlayerWindow.time_updated(position, duration)` — `ui/karaoke_player.py:110`
   đã phát signal sẵn, **hiện chưa ai nghe**, chỉ cần nối.
2. `engine.cdp_monitor.current_position` (trình duyệt ngoài có CDP).
3. `engine.media_monitor.current_position` (WinRT SMTC).

Từ `_tone_position` + `_tone_timeline` suy ra: đoạn hiện tại, đoạn kế, **số giây còn lại**.
Việc này không phụ thuộc callback của engine → **UI vẫn đúng cả khi replay của engine im lặng**,
và đó cũng là cách tự chẩn đoán triệu chứng "log có đổi mà UI không đổi".

---

## 4. Ba tầng hiển thị

### T0 — Bảng "NOW / NEXT" ở header (mọi bản, ưu tiên cao nhất)

Cụm `autokey_dot + tone_combo + scale_combo` được nâng thành bảng tone nổi bật; combo vẫn giữ
để chọn tay nhưng lùi về sau.

```
┌──────────────────────────────────────────────────────────────┐
│ ● ●   🎵 Cánh Buồm Chuyển Bến ★ …chữ chạy…    ┌──────────┐   │
│                                               │   Em     │   │  ← 30px, đậm
│                                               │  Mi thứ  │   │  ← tên Việt 11px
│                                               └──────────┘   │
│                                    ▸ kế: G · 0:12   [▾][▾][↔]│
└──────────────────────────────────────────────────────────────┘
```

- Ô tone hiện tại: chữ **30px đậm**, viền theo độ tin cậy (xanh = chắc / cam = chưa chắc) —
  tái dùng đúng bộ màu `C['green']` / `C['orange']` đang có trong `_handle_tone_result`.
- Dòng "kế": `▸ kế: G · 0:12` — đếm ngược thật, cập nhật mỗi 250ms.
- **T-5s**: dòng "kế" chuyển cam + phóng to nhẹ. **T-0**: ô tone chớp sáng một lần (~600ms,
  `QPropertyAnimation` trên độ mờ của viền) rồi đứng yên.
- Kiosk (`core/kiosk.py` đang khoá) → tắt hiệu ứng chớp, chỉ đổi chữ.

### T1 — Marquee: chuỗi tone có đánh dấu đoạn đang chạy

Bỏ chặn `if 'time' not in result`. Khi có timeline và đang phát:

```
🎵 Cánh Buồm Chuyển Bến  ★  G · ▶Em◀ · G · Em · E · Em …  (8/20)
```

`SmoothMarqueeLabel` hiện vẽ **một màu duy nhất** (`ui/components/marquee.py:314`). Thêm API
`set_highlight(substring)` để `paintEvent` vẽ 3 khúc (trước / nhấn / sau): khúc nhấn dùng
`C['green']`, hai khúc còn lại giảm alpha còn ~55%. Thay đổi cục bộ trong `paintEvent`, không
đụng logic cuộn.

Khi **không** có timeline (bài chỉ có 1 tone) → giữ nguyên hành vi cũ.

### T2 — Dải timeline tone trên waveform hero (bản Heavy/Premium)

Ngay trên thanh transport (`waveform_hero.py:520`), thêm dải cao 14px chia theo đoạn:

```
│ G      │ Em   │ G       │Em │E  │Em │ G      │Em│G │Bm│
└────────┴──────┴────▲────┴───┴───┴───┴────────┴──┴──┴──┘   ▲ = vị trí đang phát
 0:00                 1:02                           5:22
```

- Mỗi đoạn một ô, màu theo vòng quãng năm (12 nốt → 12 hue), trưởng đậm / thứ nhạt.
- Ô đang chạy sáng hơn và có nhãn chữ; ô khác chỉ hiện màu.
- Nhân tiện **nối `_tone_position` / `_tone_duration` vào chỗ `"2:34 / 4:12"`** để thanh thời
  gian thành hàng thật; click vào dải = tua (player nhúng đã có `seek()` — `ui/karaoke_player.py:333`).

### T3 — Đọc thành tiếng (tuỳ chọn, dùng lại a11y sẵn có)

`core/accessibility/speaker.py:131` đã có `speak(text, priority)`. Khi bật trợ năng: đọc
`"Sắp đổi Sol trưởng"` tại T-3s. Mặc định **tắt** — đang hát mà máy nói chen vào là phản tác
dụng; chỉ bật qua Cài đặt → Trợ năng.

---

## 5. Giai đoạn triển khai

| GĐ | Nội dung | File đụng tới | Ước lượng |
|---|---|---|---|
| **P0** | Vá 2 lỗi đã xác nhận: bỏ chặn `'time' not in result` cho marquee; giữ `title` cũ khi sự kiện replay không kèm title | `frontend_qt.py` (~10 dòng) | 30 phút |
| **P1** | `_tone_timeline` / `_tone_index` / `_tone_position` + QTimer 250ms + 3 nguồn vị trí; nối `time_updated` của player nhúng | `frontend_qt.py`, `ui/karaoke_player.py` | 2–3 giờ |
| **P2** | Bảng NOW/NEXT ở header + đếm ngược + chớp sáng khi đổi | `ui/panels/header.py`, `frontend_qt.py` | 3–4 giờ |
| **P3** | `set_highlight` cho marquee | `ui/components/marquee.py` | 1–2 giờ |
| **P4** | Dải timeline + thanh thời gian thật trên hero (Heavy) | `ui/components/waveform_hero.py` | 3–4 giờ |
| **P5** | Đọc thành tiếng ở T-3s (mặc định tắt) | `frontend_qt.py`, `core/accessibility/` | 1 giờ |

P0 vá triệu chứng ngay. P1 là nền cho mọi phần còn lại và **gỡ luôn phụ thuộc vào callback
replay của engine** — engine có im thì UI vẫn bám đúng timeline.

---

## 6. Kiểm thử

- **Offscreen (đã có mẫu chạy được):** dựng `MainDashboard` với `QT_QPA_PLATFORM=offscreen`,
  bơm chuỗi entry của bài `lhT25RSHb88` (20 đoạn), kiểm tra `tone_combo`, nhãn NOW/NEXT và
  text marquee sau mỗi mốc.
- **Giả lập vị trí:** thay nguồn vị trí bằng hàm trả số giây tăng dần → chạy hết 322s trong
  vài giây, khẳng định `_tone_index` khớp mốc và đếm ngược không bao giờ âm.
- **Biên:** timeline rỗng; chỉ 1 đoạn; tua ngược (`elapsed` giảm); tua quá cuối bài; bài chưa
  có timeline; đổi bài giữa chừng (timeline cũ phải bị xoá, không rò sang bài mới).
- **Kiosk:** đang khoá → không có hiệu ứng chớp.
- **Thật:** phát bài đã lưu trên trình duyệt ngoài (WinRT) và trên player nhúng, đối chiếu mốc
  đổi trên UI với dòng `[MANUAL REPLAY] t=…` trong console.

---

## 7. Rủi ro

| Rủi ro | Xử lý |
|---|---|
| Timer 250ms tốn CPU trên máy yếu | Chỉ chạy khi đang phát; dừng hẳn khi pause hoặc không có timeline |
| WinRT trả vị trí giật/trễ | Dùng lại đúng ngưỡng chống tua ngược đã có trong replay (`core/engine/_autokey.py:505`), không viết logic mới |
| Header chật khi cửa sổ hẹp | Bảng NOW/NEXT có ngưỡng: dưới ~900px thì bỏ dòng "kế", giữ ô tone |
| Chớp sáng gây khó chịu khi hát | Một lần mỗi lần đổi, ~600ms; tắt được trong Cài đặt và tự tắt ở kiosk |
| UI và engine lệch nhau | UI tự tính từ vị trí + timeline; callback engine chỉ để đồng bộ tức thì, không còn là nguồn duy nhất |

---

## 8. Đã làm (2026-08-23)

**File mới:** `ui/components/tone_display.py` — `ToneDisplay`, `ScaleSwitch`, `NextTonePill`.

`ToneDisplay` và `ScaleSwitch` **kế thừa QComboBox** thay vì QWidget thuần. Lý do: hơn 40 chỗ
trong app (và cả tests) đã gọi `tone_combo.currentText()` / `setCurrentText()` / `findText()` /
`QSignalBlocker(...)`. Giữ lớp cha nghĩa là đổi được hình thức và cách bấm mà **không phải sửa
một chỗ gọi nào** — dữ liệu vẫn là `"C".."B"` và `"Major"/"Minor"`.

**Sửa:**

- `ui/panels/header.py` — dùng widget mới, thêm ô "kế tiếp", nới thanh header 55 → 62px.
- `frontend_qt.py` — trạng thái timeline + nhịp 250ms + `_sync_tone_widgets` (đường đồng bộ
  dùng chung cho cả callback engine lẫn nhịp), `_compose_tone_marquee`, bỏ chặn
  `if 'time' not in result`, giữ `title` cũ cho sự kiện replay.
- `core/engine/_youtube.py` — thêm `total_duration` vào payload dò xong (thiếu nó thì đoạn
  cuối không có mốc kết để đếm ngược).
- `ui/dialogs/songs_list.py` — nạp timeline khi phát bài từ danh sách.

**Hai cạm bẫy gặp phải, ghi lại kẻo quên:**

1. **Marquee không được cập nhật mỗi nhịp.** `setText` làm `SmoothMarqueeLabel` đo lại bề rộng
   và reset vòng chạy chữ → gọi 4 lần/giây thì chữ đứng im tại chỗ. Nên marquee chỉ dựng lại
   khi tone THỰC SỰ đổi; số giây đếm ngược nằm ở `NextTonePill` (vẽ lại thoải mái).
2. **`timer.stop()` không huỷ timeout đã nằm trong hàng đợi Qt.** Khi user chỉnh tay,
   `_tone_ticker_sync()` dừng nhịp nhưng vẫn còn một nhịp nữa nổ ra, đủ để ghi đè lựa chọn.
   `_on_tone_tick()` phải tự chốt `_manual_tone_override` ngay đầu vòng.

**Kiểm thử:** 27 khẳng định offscreen trên đúng 20 đoạn của bài `lhT25RSHb88` (bám tone theo
vị trí, đếm ngược, ngưỡng khẩn 5s, đoạn cuối, tua về đầu, chỉnh tay khoá nhịp, đổi bài xoá
timeline) — tất cả xanh. `tests/ui/` 42/42 pass.

## 9. Còn để ngỏ

- **P4** — dải timeline tone + thanh thời gian thật trên waveform hero (bản Heavy). Chỗ
  `"2:34 / 4:12"` ở `ui/components/waveform_hero.py:637` vẫn đang in cứng.
- **P5** — đọc thành tiếng ở T-3s (mặc định tắt).
- **Nợ kỹ thuật ngoài phạm vi:** `core/ytdlp_support.py:16` gọi `activate_override()` ngay lúc
  import, cài `_OverrideFinder` vào `sys.meta_path`. Khi máy đã có thư mục `ytdlp/` (bản nạp
  ngoài), 5 test trong `tests/core/test_ytdlp_update.py` fail nếu chạy SAU bất kỳ test nào
  import `ytdlp_support` — chạy riêng file đó thì 25/25 pass. Đây là lỗi cách ly test, cần một
  fixture dọn `sys.meta_path`.
