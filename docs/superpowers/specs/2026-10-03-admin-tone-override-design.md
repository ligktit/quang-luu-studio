# Admin đặt tone trên server và phân phối tới client

Ngày: 2026-10-03. Trạng thái: chờ duyệt.

## 1. Vấn đề

Thư viện tone cộng đồng (`server/app/routers/library.py`, `core/tone_share.py`)
đang cho admin **ghim / ẩn / xoá** biến thể có sẵn, nhưng không **tạo hay sửa**
được tone. Khi thuật toán dò sai cả mạng lưới (ví dụ *Lưng Cha Bụng Mẹ*: đáp án
F#m, máy dò ra Bm, xem `docs/NGHIEN_CUU_DO_TONE.md` mục 2026-10-03), admin chỉ
có thể chờ một khách sửa tay rồi ghim bản đó.

Kể cả khi đã ghim đúng, bản sửa **không tới được máy khách**:

- Client chỉ hỏi thư viện khi trong máy **không có gì** (`_resolve_tone` trong
  `core/engine/_tone.py`: manual → tone_cache → tone bài đã lưu → cộng đồng).
- Kết quả tự dò nằm trong `tone_cache.json` 30 ngày. Máy đã dò sai thì hát sai
  tới một tháng, hoặc tới khi khách tự "Dò lại".
- Nút "☁ Đồng bộ tone" ở Danh sách bài hát cũng bỏ qua mọi bài đã có tone.

## 2. Mục tiêu và ngoài phạm vi

Mục tiêu:

1. Admin đặt tone cho một bài (có sẵn hoặc chưa có trong thư viện) ngay trên
   `/admin/library`, không cần client nào đóng góp trước.
2. Bản admin đặt tới được mọi máy đã kích hoạt trong vòng **một chu kỳ bảo trì
   nền** (6 giờ, `main.py::_background_maintenance`) hoặc ngay khi khách bấm
   "☁ Đồng bộ tone", và **đè** tone máy dò / tone cộng đồng đang nằm trong máy.
3. **Không đè** chuỗi tone khách đã sửa tay (quyết định sản phẩm 2026-10-03).

Ngoài phạm vi: sửa thuật toán dò; đẩy realtime (websocket); giao diện client
mới ngoài việc nút "☁ Đồng bộ tone" làm thêm việc; migration DB (không có
alembic, server chỉ `create_all`).

## 3. Thiết kế server

### 3.1 Nguồn `admin`

`tonelib.SOURCES` thêm `"admin"`; `SOURCE_WEIGHT["admin"] = 10`. Biến thể admin
luôn được **ghim** khi tạo nên `best_variant` chọn nó bất kể phiếu; trọng số chỉ
để xếp hạng hiển thị và phòng khi admin bỏ ghim.

`contribute` từ client **không bao giờ** được gửi `source="admin"`: router ép
về `auto` nếu giá trị lạ (đã làm sẵn qua `if item.source.lower() in SOURCES`;
cần sửa thành chỉ nhận `auto|human` để client không tự phong admin).

### 3.2 Form "Đặt tone" trên `/admin/library`

Mỗi nhóm bài trên `library.html` có thêm một form nhỏ; đầu trang có form "Thêm
bài theo mã video" cho bài chưa có trong thư viện.

Trường:

| Trường | Bắt buộc | Kiểu |
|---|---|---|
| `song_key` | có | 11 ký tự YouTube id (`tonelib.valid_song_key`) |
| `title` | không | ≤ 300 ký tự |
| `primary_key` | có | tên tone, qua `tonelib.parse_key` |
| `timeline` | không | mỗi dòng `mm:ss Tone` hoặc `giây Tone`; bỏ trống → một mốc `0 primary_key` |

Route `POST /admin/library/set` (admin đăng nhập):

1. Validate. Lỗi → quay lại trang với thông báo, không ghi gì.
2. Chuẩn hoá timeline (`normalize_timeline`), tính `payload_hash`.
3. Nếu đã có biến thể cùng `(song_key, payload_hash)` → cập nhật nó:
   `source="admin"`, `title` nếu có. Nếu chưa → tạo `SharedTone(source="admin",
   votes=0, reports=0)`.
4. Ghim biến thể này, bỏ ghim mọi anh em (giống `library_pin`).
5. `last_seen = now()` cho biến thể này. **Mọi thay đổi do admin** (`set`,
   `pin`, `hide`, `delete`) đều phải cập nhật `last_seen` của biến thể thắng mới
   của bài đó, vì `last_seen` là mốc mà feed §3.3 dựa vào. Với `delete`/`hide`
   mà sau đó bài không còn biến thể thắng → không có gì để phát; client giữ
   nguyên (chấp nhận, ngoài phạm vi).

Kết quả hiển thị trong bảng như biến thể khác, nguồn ghi "admin".

### 3.3 Feed thay đổi: `POST /api/v1/library/changes`

Request (`LibraryChangesRequest`): `token`, `code?`, `device_fingerprint`,
`cursor: str = ""` (rỗng = lấy từ đầu). Xác thực như `lookup`
(`authorize_device`, không cần Premium). Rate limit dùng `rate_limit_library`.

Response (`LibraryChangesResponse`):

```json
{
  "ok": true,
  "items": [
    {"song_key": "pMPvJE1wwnc", "title": "...", "primary_key": "F#m",
     "source": "admin", "pinned": true, "payload_hash": "...",
     "timeline": [{"time": 0, "key_display": "F#m", "key_index": 6, "scale": "Minor"}]}
  ],
  "next_cursor": "eyJ0cyI6IjIwMjYtMTAtMDNUMTA6MDA6MDAuMTIzNDU2IiwiaWQiOjQyfQ",
  "has_more": false
}
```

**Cursor keyset `(last_seen, id)`, không dùng timestamp đơn thuần.** Lý do:

- `since = server_time` bỏ sót bản ghi commit *sau* lúc truy vấn nhưng có
  `last_seen` *trước* `server_time` (giao dịch kéo dài, hoặc đồng hồ ghi
  `last_seen` lấy trước khi commit). Client lưu `server_time` rồi là mất bản đó
  vĩnh viễn.
- `since = updated_at` của bản cuối trang: nhiều bản ghi cùng `last_seen` (admin
  đặt nhiều bài trong một giây, hoặc độ phân giải thời gian thấp) ở ranh giới
  trang bị cắt mất, vì điều kiện `>` loại cả những bản chưa trả.

Cursor giải quyết cả hai: vị trí trang là *bản ghi cụ thể*, không phải mốc giờ.

Định dạng: chuỗi **opaque** do server phát — base64url của JSON
`{"ts": "<last_seen ISO-8601 đúng như lưu trong DB>", "id": <int>}`. Client
không được đọc hay tự tạo; chỉ lưu nguyên văn và gửi lại. `ts` giữ dạng chuỗi
ISO (không đổi sang epoch float) để so bằng `=` ở vế tie-break không bị lệch
micro giây do làm tròn số thực. Cursor hỏng/không đọc được → server coi như
rỗng (lấy lại từ đầu; ghi đè idempotent nên vô hại) và trả `ok: true`.

Truy vấn:

```sql
WHERE pinned = 1 AND status = 'ok'
  AND (last_seen > :ts OR (last_seen = :ts AND id > :id))
ORDER BY last_seen ASC, id ASC
LIMIT 500
```

`next_cursor` = `(last_seen, id)` của **bản cuối trong trang**; trang rỗng →
trả lại đúng cursor nhận vào. `has_more = true` khi lấy đủ 500 (server hỏi
501 để biết chắc, không đoán theo `== 500`).

Chỉ phát **bản ghim** (admin đặt hoặc admin ghim bản người sửa). Bản thắng do
phiếu không đi qua feed: đó là dữ liệu máy khách, không có người chịu trách
nhiệm, không được phép đè cache của máy khác.

Ràng buộc để feed đúng:

- `last_seen` của bản ghim chỉ được **tăng**, không bao giờ đặt lùi.
- Mọi hành động admin làm bản thắng mới của bài đổi (`set`, `pin`, `hide`,
  `delete` rồi bài có bản thắng khác) đều `last_seen = now()` cho bản thắng
  mới, trong **cùng giao dịch** với thay đổi, giao dịch là một request admin
  ngắn. Rủi ro còn lại (một request admin treo lâu hơn chu kỳ client đọc
  feed) chấp nhận được; nếu sau này cần tuyệt đối thì thêm cột `change_seq`
  tự tăng, cần migration, ngoài phạm vi.
- Nếu về sau `contribute` cũng cập nhật `last_seen` của bản ghim (hiện không),
  bản đó sẽ xuất hiện lại trong feed. Vô hại vì client ghi đè idempotent, chỉ
  tốn băng thông; ghi chú ở `library.py` để ai sửa biết.

### 3.4 Export bộ đáp án

`/admin/library/export` đã lấy bản ghim; thêm `source` admin vào kết quả tự
nhiên. `tools/danh_gia_do_tone.py` không cần đổi.

## 4. Thiết kế client

### 4.1 `core/tone_share.py::pull_overrides()`

Chạy ở luồng nền. Trả `{"applied": n, "skipped_human": m, "fetched": k}`.

1. `if not enabled(): return` (tôn trọng công tắc "Đồng bộ tone cộng đồng").
2. Đọc `cursor` từ file trạng thái `DATA_DIR/tone_overrides_state.json`
   (`{"cursor": str}`); thiếu → `""`.
3. Lặp: `POST /api/v1/library/changes` với `cursor`. Mỗi trang:
   - Áp dụng **hết** item của trang (bước 4).
   - Áp xong mới ghi `cursor = next_cursor` xuống file. Ghi *trước* khi áp
     thì app tắt giữa chừng là mất trang đó.
   - `has_more` → lặp tiếp; tối đa 20 trang một lượt (10 000 bản ghi) để
     vòng bảo trì không kẹt vô hạn nếu server lỗi trả mãi `has_more`.
4. Với mỗi item:
   - `url = f"https://www.youtube.com/watch?v={song_key}"`.
   - Nếu `ManualToneTimeline.get_timeline_source(url) == "human"` → **bỏ qua**
     (khách sửa tay thắng). Đếm `skipped_human`.
   - Ngược lại ghi `ToneCacheManager.save_tone(url, entry)` với entry dạng
     `_to_cache_entry(item)` nhưng `origin="admin"`. Việc này tự tăng
     `data_version` → `_resolve_tone` bỏ đệm RAM, bài đang mở nhận tone mới ở
     lần resolve kế tiếp.
   - Cập nhật cột tone hiển thị ở Danh sách bài hát nếu bài có trong
     `saved_songs.json` (`SongManager.update_song(id, tone=primary_key)`), tra
     theo `song_match_key`.
   - Xoá `_miss_cache`/`_hit_cache` của key đó.
5. Mất mạng hoặc server trả lỗi giữa chừng → dừng, giữ cursor của trang cuối
   đã áp xong; lần sau tiếp từ đó. Áp lại một trang là idempotent.

Thứ tự resolve **không đổi**: entry `origin="admin"` nằm ở nấc tone_cache, đã
đứng trên tone bài đã lưu và cộng đồng, và dưới chuỗi tone thủ công.

### 4.2 Tương tác với dữ liệu khách

- Khách sửa tay **sau** khi nhận bản admin: `edit_song._share_human_timeline`
  thấy `origin != "community"` nên không `report_wrong`, chỉ `contribute(human)`.
  Giữ nguyên; bản admin vẫn ghim trên server.
- Khách bấm "Dò lại": kết quả tự dò ghi đè cache admin (như hiện nay với mọi
  cache). Lần `pull_overrides` kế tiếp (6 giờ) sẽ **không** đặt lại vì cursor
  đã đi qua bản đó. Chấp nhận: khách chủ động dò lại là ý khách. Nếu muốn khác, cần cột
  riêng, ngoài phạm vi.
- TTL 30 ngày của tone_cache vẫn áp cho entry admin. Sau 30 ngày entry mất,
  resolve rơi xuống nấc cộng đồng → `lookup` trả đúng bản ghim. Không mất đúng.

### 4.3 Điểm gọi

- `main.py::_background_maintenance`: ngay sau `tone_share.flush_queue()`,
  gọi `tone_share.pull_overrides()` (bọc try, log debug). Chạy cả ở vòng đầu
  (lúc khởi động) và mỗi 6 giờ.
- `ui/dialogs/songs_list.py::_start_sync_worker`: worker gọi
  `pull_overrides()` trước `lookup_many(urls)`; thông báo cuối gộp số bài cập
  nhật từ admin. Bài đã có tone vẫn không bị tra cộng đồng (giữ luật cũ), chỉ
  nhận bản admin qua feed.
- `ui/dialogs/settings_dialog.py::_on_tone_share_sync` ("Đồng bộ ngay" ở mục
  Thư viện tone, phần Công cụ): chạy `pull_overrides()` ở luồng nền cùng với
  `flush_queue()`.

## 5. Kiểm thử

Server (`server/tests/test_library.py`, `test_admin_library.py` mới):

- Admin đặt tone cho bài chưa có → `lookup` trả đúng, `source="admin"`, ghim.
- Admin đặt tone cho bài đã có biến thể auto thắng → bản admin thắng, anh em
  bị bỏ ghim.
- Timeline nhiều mốc parse đúng `mm:ss`; tone sai cú pháp → không ghi.
- `changes` với cursor rỗng trả bản ghim, không trả bản thắng do phiếu; gửi
  lại `next_cursor` → rỗng; `has_more` và phân trang đúng khi vượt trần.
- Nhiều bản ghi **cùng `last_seen`** nằm vắt qua ranh giới trang → không bản
  nào bị bỏ sót hay lặp lại (test ép `last_seen` bằng nhau, trần trang đặt
  nhỏ qua monkeypatch).
- Cursor hỏng → coi như rỗng, `ok: true`.
- Admin `set`/`pin`/`hide`/`delete` → bản thắng mới xuất hiện trong feed sau
  cursor cũ (`last_seen` được bơm).
- Client gửi `source="admin"` qua `contribute` → bị ép về `auto`.

Client (`tests/core/test_tone_share.py`):

- `pull_overrides` ghi tone_cache với `origin="admin"` và lưu `next_cursor`
  nguyên văn.
- Bài có chuỗi tone thủ công → không ghi, đếm `skipped_human`.
- Mất mạng ở trang 2 → cursor dừng ở trang 1 (đã áp), không nhảy.
- Lặp trang khi `has_more`; dừng ở trần 20 trang.
- `_resolve_tone` với cache `origin="admin"` thắng tone bài đã lưu
  (`tests/core/test_tone_resolve_saved.py`).

UI (`tests/ui`): "☁ Đồng bộ tone" gọi `pull_overrides` rồi `lookup_many`, nút
trở lại bình thường khi xong.

## 6. Triển khai và kiểm chứng thật

1. Deploy server (không có migration; `SOURCES` mới chỉ là dữ liệu).
2. Trên admin: đặt `pMPvJE1wwnc` = F#m.
3. Máy client đang có Bm trong tone_cache: bấm "☁ Đồng bộ tone" → cột tone đổi
   F#m, mở bài → MIDI gửi F#m. Máy có chuỗi tone thủ công cho bài đó → giữ
   nguyên.
