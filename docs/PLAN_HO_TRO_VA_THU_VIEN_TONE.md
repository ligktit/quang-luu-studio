# Kế hoạch: Hỗ trợ hai chiều + Thư viện tone cộng đồng

## Bối cảnh

Hai nhu cầu mới, cùng dựa trên hạ tầng licensing server đã chạy thật
(`https://qlstudio.duckdns.org`, `server/` FastAPI + Postgres):

1. **Hỗ trợ** — hiện khách gặp sự cố phải gọi/Zalo cho dev. Chỉ có luồng
   *crash report tự động* (`core/crash_reporter.py` → `/api/v1/crash` →
   `/admin/crashes`), tức là dev chỉ thấy được lỗi làm app **sập**. Mọi vấn đề
   "app không sập nhưng sai" (tone lệch, MIDI không ăn, không tải được YouTube)
   đều không tới được dev. Cần một kênh **hai chiều** trong app: khách gửi yêu
   cầu → dev trả lời trên admin web → khách đọc ngay trong app.

2. **Đồng bộ danh sách bài hát** — mỗi máy hiện dò tone độc lập và cache riêng
   trong `tone_cache.json`. Cùng một bài, 50 quán dò 50 lần, mỗi lần tốn ~10–60s
   và có thể ra kết quả khác nhau. Mục tiêu: **hiệu ứng mạng** — máy nào đã dò
   (hoặc đã sửa tay) thì các máy khác dùng lại ngay, tone vừa nhanh vừa chính
   xác dần theo thời gian.

Kết quả mong đợi: dev có hộp thư hỗ trợ khép kín trong sản phẩm; khách mở một
bài phổ biến thì tone hiện **tức thì** thay vì chờ dò, và độ chính xác tăng dần
vì bản do người sửa tay luôn thắng bản máy dò.

## Quyết định đã chốt (theo trả lời của bạn)

| Vấn đề | Chốt |
|---|---|
| Thư viện chung chia sẻ gì | **Chỉ kết quả tone** (song_key + tên bài + timeline). Không đụng danh sách bài riêng, không chia sẻ preset mixer. |
| Ai được đọc/ghi | **Mọi máy đã kích hoạt** đều đọc và ghi được (kể cả Standard). |
| Cách đóng góp | **Tự động nền, không hỏi.** Vẫn có công tắc tắt trong Thiết lập (bắt buộc, để khách khó tính tự tắt được). |
| Hỗ trợ | **Hai chiều** — dev trả lời, khách đọc trong app. |

**Thuật ngữ cần phân biệt rõ trong code và UI** (dễ nhầm chết người):
- *Cloud Sync* = `core/licensing/sync.py` + bảng `sync_blobs` — đồng bộ thư viện
  **riêng tư** của một license giữa các máy của **chính khách đó**. Premium. **Không đổi.**
- *Thư viện tone cộng đồng* = tính năng mới — dữ liệu **dùng chung giữa các
  khách hàng**. Đặt ở module riêng `core/tone_share.py`, bảng riêng, router riêng.
  Tuyệt đối không nhét vào `sync.py`.

---

## PHẦN A — Hỗ trợ hai chiều

### A1. Server: model

Thêm vào `server/app/models.py` (theo đúng phong cách `CrashReport`):

```python
class SupportTicket(Base):        # __tablename__ = "support_tickets"
    id, ticket_code (str16, unique, dạng "HT-000123" sinh từ id)
    license_code, device_fp, hostname, os_info, app_version   # đều nullable
    contact        # SĐT/Zalo khách tự nhập, nullable
    category       # loi | huong_dan | tinh_nang | khac
    subject        # str(200)
    status         # new | open | answered | closed   (index)
    log_excerpt    # Text, nullable — đuôi errors.log gửi kèm
    unread_client  # bool — có trả lời mới khách chưa đọc
    created_at, updated_at

class SupportMessage(Base):       # __tablename__ = "support_messages"
    id, ticket_id (FK cascade), sender ("customer"|"dev"), body (Text), created_at
```

> Không dùng Alembic (dự án chưa có). Bảng **mới** nên `Base.metadata.create_all`
> tạo được an toàn — chạy `python -m app.cli init-db` trên VPS sau khi deploy.

### A2. Server: API client-facing

File mới `server/app/routers/support.py`, prefix `/api/v1/support`, schemas thêm
vào `server/app/schemas.py`:

- `POST /ticket` → tạo ticket + message đầu tiên. Trả `{ok, ticket_code}`.
- `POST /ticket/reply` → `{device_fingerprint, ticket_code, body}` thêm message
  của khách, `status: answered → open`.
- `POST /inbox` → `{device_fingerprint, license_code?}` trả danh sách ticket của
  máy này kèm toàn bộ message + `unread_count`.
- `POST /ticket/read` → xoá cờ `unread_client`.

**Xác thực cố tình lỏng:** chỉ cần `device_fingerprint`; `token`/`code` là tuỳ
chọn và chỉ dùng để gắn ticket vào license. Lý do: người cần hỗ trợ nhất chính
là người **đang không kích hoạt được** — bắt buộc token là tự khoá cửa với họ.
Bù lại bằng rate-limit chặt: thêm `rate_limit_support: str = "6/hour"` vào
`server/app/config.py` và `@limiter.limit(settings.rate_limit_support)` trên
`POST /ticket` (các route đọc dùng `rate_limit_verify`).

Đăng ký router trong `server/app/main.py` (`app.include_router(support.router)`).

### A3. Server: admin web

- `server/app/routers/admin.py`: thêm `/admin/support` (danh sách, lọc theo
  status), `/admin/support/{id}` (hội thoại + ô trả lời),
  `POST /admin/support/{id}/reply` (tạo message `sender="dev"`, set
  `status="answered"`, `unread_client=True`), `POST /admin/support/{id}/status`.
- Template mới `support.html`, `support_detail.html` — copy khuôn từ
  `crashes.html` / `crash_detail.html`, dùng lại class `.card .badge .row` sẵn có.
- `base.html`: thêm `<a href="/admin/support">Hỗ trợ</a>` vào nav.
- `dashboard.html` + hàm `dashboard()` trong `admin.py`: thêm ô thống kê
  **"Hỗ trợ mới"** (`count(SupportTicket.status == "new")`).

### A4. Client

**Module mới `core/support.py`** — sao khuôn `core/crash_reporter.py` (đã có sẵn
mọi thứ cần: `_server_base()`, `_post()`, `_context()`, hàng đợi offline):
- `submit(category, subject, body, contact, include_logs=True) -> dict`
- `inbox() -> dict` / `reply(ticket_code, body)` / `mark_read(ticket_code)`
- `unread_count() -> int` (cache trong RAM, dùng cho huy hiệu)
- Hàng đợi offline `support_queue.json` + `flush_queue()` — dùng lại nguyên
  `_errors_log_tail()` của `crash_reporter` cho phần nhật ký gửi kèm.

**Dialog mới `ui/dialogs/support_dialog.py`** — `QDialog` 2 tab, theo phong cách
`settings_dialog.py` (`QTabWidget` + `PainterButton` + `design_tokens`):
- Tab **"Gửi yêu cầu"**: combo loại, ô tiêu đề, ô mô tả, ô SĐT/Zalo, checkbox
  "Gửi kèm nhật ký lỗi (giúp dev xử lý nhanh hơn)". Gửi trong thread nền, hiện
  mã ticket khi xong; mất mạng thì xếp hàng và báo "sẽ gửi khi có mạng".
- Tab **"Hộp thư"**: danh sách ticket → hội thoại → ô trả lời.

**Điểm vào**: nút mới trong `ui/panels/header.py` cạnh `_settings_btn`
(`dashboard._support_btn`), icon `SVG_HELP` thêm vào `ui/components/svg_icons.py`;
chấm đỏ khi `unread_count() > 0`. Slot `_show_support_dialog()` trong
`frontend_qt.py` cạnh `_show_settings_dialog`. **Ẩn nút khi khoá kiosk**: thêm
vào `frontend_qt.py::_apply_kiosk_visibility` cùng chỗ `_eye_btn` — khách hát
không được gửi ticket lung tung.

**Thăm dò trả lời**: trong `main.py::_background_maintenance` (vòng lặp đã có
sẵn, chạy cùng nhịp check-in license) gọi `support.flush_queue()` +
`support.poll_inbox()`; có trả lời mới thì emit qua notifier
(`_LicenseNotifier` → thêm signal `support_reply = Signal(str)`, đúng khuôn
`license_lost`) để main thread bật chấm đỏ + toast `dashboard._show_message`.

---

## PHẦN B — Thư viện tone cộng đồng

### B0. Mô hình tin cậy (phần quan trọng nhất)

Dữ liệu do máy khách gửi lên là **không đáng tin**. Không được để "ai gửi sau
đè lên người gửi trước" — một máy dò sai một lần là cả mạng lưới hát sai.

Cơ chế: **nhiều biến thể + bỏ phiếu, bản người sửa tay thắng.**

- Mỗi bài (`song_key`) có nhiều **biến thể** (variant), phân biệt bằng
  `payload_hash` = sha256 của timeline đã **chuẩn hoá** (làm tròn `time` về giây,
  chỉ giữ `key_display` + `scale`, bỏ `confidence`/`bpm`). Hai máy dò ra kết quả
  giống nhau → cùng hash → **cộng phiếu** thay vì tạo bản ghi mới.
- Mỗi máy chỉ bỏ được **1 phiếu / biến thể** (bảng phiếu unique theo
  `(payload_hash, device_fp)`).
- Điểm xếp hạng: `score = (3 nếu source="human" else 1) × votes − 2 × reports`.
  Biến thể `pinned` do dev ghim thì luôn thắng tuyệt đối.
- Người dùng sửa tay timeline của một bài lấy từ cộng đồng ⇒ client tự động
  **`report`** biến thể cũ và **`contribute`** bản `human` mới. Đây là vòng
  phản hồi tự chữa lỗi, gần như miễn phí vì UI sửa tone đã tồn tại.

**Chỉ chia sẻ bài có YouTube video_id.** `song_match_key()` fallback về URL
nguyên văn cho file local — mà đường dẫn local là dữ liệu cá nhân và không khớp
được giữa các máy. Client lọc bằng `extract_video_id(url)`; không có id thì
**không gửi, không tra**. Server cũng chặn `song_key` không đúng dạng 11 ký tự
`[A-Za-z0-9_-]`.

### B1. Server: model + API

`server/app/models.py`:

```python
class SharedTone(Base):           # "shared_tones"
    id, song_key (index), payload_hash, title, primary_key,
    timeline (Text, JSON string), source ("auto"|"human"),
    votes (int), reports (int), pinned (bool), status ("ok"|"hidden"),
    first_seen, last_seen
    UniqueConstraint(song_key, payload_hash)

class SharedToneVote(Base):       # "shared_tone_votes"
    id, tone_id (FK cascade), device_fp, kind ("vote"|"report"), created_at
    UniqueConstraint(tone_id, device_fp, kind)
```

File mới `server/app/routers/library.py`, prefix `/api/v1/library`:
- `POST /lookup` — `{token, code, device_fingerprint, keys: [...]}` (≤200 key) →
  `{results: {song_key: {primary_key, title, timeline, source, votes, payload_hash}}}`.
- `POST /contribute` — `{..., items: [{song_key, title, primary_key, timeline, source}]}`
  (≤50 mục, mỗi timeline ≤64KB) → `{accepted, rejected}`.
- `POST /report` — `{..., song_key, payload_hash}` → tăng `reports`.

**Xác thực:** tách hàm `_authorize()` hiện có trong
`server/app/routers/sync.py:32` thành helper dùng chung (đề xuất đặt tại
`server/app/services/licensing.py`) với tham số `require_premium: bool`. `sync.py`
gọi với `True` (giữ nguyên hành vi Premium), `library.py` gọi với `False`.
Đây là bước refactor **duy nhất** chạm vào code đang chạy — phải có test bảo vệ
(`server/tests/test_sync.py` đã có sẵn, chạy lại là đủ để bắt hồi quy).

Thêm `rate_limit_library: str = "60/minute"` vào `server/app/config.py`; đăng ký
router trong `main.py`.

### B2. Server: admin web

`/admin/library` — ô tìm theo `song_key`/tên bài, bảng: bài · biến thể · nguồn ·
phiếu · báo sai · trạng thái. Hành động: **ẩn/hiện**, **ghim**, **xoá** biến thể.
Template `library.html` + link nav trong `base.html`. Đây là van an toàn khi có
dữ liệu rác — không có nó thì không có cách nào sửa từ xa.

### B3. Client: module mới `core/tone_share.py`

Khuôn giống `core/licensing/sync.py` (urllib, timeout 10s, fail-soft, log
`log.info` khi mất mạng) nhưng **không phụ thuộc entitlements**:

- `enabled()` → `settings.json: tone_share.enabled` (mặc định `True`) **và**
  `client.has_online_license()` **và** có `license_server_url`.
- `lookup(url) -> dict | None` — 1 bài. Có memo RAM + **negative cache** (bài
  server không có thì trong 24h không hỏi lại, tránh mỗi lần mở bài lại tốn một
  vòng mạng vô ích).
- `lookup_many(urls) -> dict` — gọi lô, cho nút đồng bộ hàng loạt.
- `contribute(url, title, cache_data, source)` — đẩy vào hàng đợi
  `tone_share_queue.json`, gửi nền, flush trong `_background_maintenance`.
- `report_wrong(url, payload_hash)`.
- Kết quả `lookup` được ghi thẳng vào `ToneCacheManager.save_tone()` kèm cờ
  `"origin": "community"` + `"payload_hash"` → lần sau dùng offline được, và biết
  đường mà `report` khi người dùng sửa tay.

### B4. Client: điểm tích hợp (ít mà đúng chỗ)

| # | Vị trí | Việc |
|---|---|---|
| 1 | `core/engine/_tone.py::_resolve_tone` (dòng ~146) | Sau khi trượt manual + trượt cache local, gọi `tone_share.lookup(url)`; trúng thì trả `('community', data)` và lưu vào cache local. **An toàn về thread**: cả 3 nơi gọi `_resolve_tone` (dòng 356, 450, 535) đều nằm trong `def _detect()` chạy nền — không chặn UI. |
| 2 | `core/engine/_tone.py` dòng ~830 (`auto_detect_youtube_timeline`) và `_save_tone_to_cache` (~226) | Sau khi lưu cache local, `tone_share.contribute(..., source="auto")`. |
| 3 | `core/tone_cache.py::ManualToneTimeline.save_timeline` (nơi gọi ở UI sửa tone) | Với `source="human"`: `contribute(source="human")` + `report_wrong()` nếu bài đó đang mang cờ `origin="community"`. Đặt lời gọi ở **lớp UI** (`ui/dialogs/edit_song.py`), không nhét mạng vào `tone_cache.py` (module này đang thuần I/O file và được test kỹ). |
| 4 | `ui/dialogs/songs_list.py::_build_header` | Nút **"☁ Đồng bộ tone"**: `lookup_many()` cho mọi bài đã lưu chưa có tone/timeline, chạy nền, hiện tiến trình, xong báo "Đã lấy tone cho N/M bài". Đây chính là "Đồng bộ danh sách bài hát" mà người dùng nhìn thấy. |
| 5 | `ui/dialogs/settings_dialog.py::_build_tools_tab` | Thẻ **"Thư viện tone cộng đồng"**: công tắc bật/tắt chia sẻ + dòng giải thích rõ *gửi lên gồm: mã video YouTube, tên bài, chuỗi tone* + nút "Đồng bộ ngay". |
| 6 | `main.py::_background_maintenance` | `tone_share.flush_queue()` mỗi vòng (dùng chung nhịp với check-in license). |

---

## Thứ tự thực hiện

Làm **Phần A trước** — nhỏ hơn, rủi ro thấp hơn, và khi Phần B ra thị trường thì
đã có sẵn kênh để khách báo "tone cộng đồng sai".

1. **A-server** — models + schemas + `routers/support.py` + admin page/template +
   nav + ô thống kê. Test: `server/tests/test_support.py`.
2. **A-client** — `core/support.py` + `support_dialog.py` + nút header + poll nền.
3. **Phát hành 1.8.0** (chỉ Hỗ trợ), chạy `init-db` trên VPS.
4. **B-server** — tách `_authorize`, models, `routers/library.py`, admin
   `/admin/library`. Test: `server/tests/test_library.py` + chạy lại `test_sync.py`.
5. **B-client** — `core/tone_share.py` + 6 điểm tích hợp ở B4.
   Test: `tests/core/test_tone_share.py` (mock urllib), bổ sung
   `tests/core/test_engine.py` cho nhánh `('community', …)`.
6. **Phát hành 1.8.1**. Trước khi mở cho cả mạng lưới: tự chạy
   `tools/batch_detect_tone.py` trên máy dev để **mồi** thư viện vài trăm bài phổ
   biến — thư viện rỗng ngày đầu sẽ khiến khách tưởng tính năng hỏng.

## Kiểm thử

**Server** (`cd server && pytest`) — conftest đã dựng sẵn SQLite tạm + khoá RS256 test:
- `test_support.py`: tạo ticket không token vẫn được; dev trả lời → `inbox` thấy
  `unread_count=1`; `read` xoá cờ; rate-limit chặn ticket thứ 7 trong giờ.
- `test_library.py`: 2 máy gửi cùng timeline → 1 bản ghi, `votes=2`; cùng máy gửi
  2 lần → vẫn `votes=1`; bản `human` 1 phiếu thắng bản `auto` 2 phiếu; `report`
  đủ nhiều thì tụt hạng; `song_key` không phải video_id → từ chối; máy chưa kích
  hoạt gọi `lookup` → 401.
- Hồi quy bắt buộc: `test_sync.py` vẫn xanh sau khi tách `_authorize` (Standard
  vẫn phải bị chặn khỏi `/api/v1/sync`).

**Client** (`pytest tests/`):
- `test_tone_share.py`: mock `urllib.request.urlopen` — tắt công tắc thì không
  gọi mạng; mất mạng thì xếp hàng và không raise; bài không có video_id thì bỏ
  qua; negative cache không hỏi lại trong 24h.
- `test_engine.py`: `_resolve_tone` trả `('community', …)` khi local trượt còn
  server có; và **không** gọi mạng khi cache local đã trúng.

**Chạy thật (end-to-end)** — theo `/run`:
1. `cd server && uvicorn app.main:app --reload`, sửa `app_config.json` trỏ
   `license_server_url` về `http://localhost:8000`.
2. Mở app → nút Hỗ trợ → gửi yêu cầu → mở `http://localhost:8000/admin/support`
   → trả lời → app hiện chấm đỏ + đọc được trả lời.
3. Xoá `tone_cache.json`, dò tone một bài YouTube → kiểm tra `/admin/library`
   có bản ghi. Xoá cache lần nữa, mở lại đúng bài → tone phải hiện **ngay,
   không chạy tiến trình dò**.
4. Sửa tay timeline bài đó → `/admin/library` phải có thêm biến thể `human` và
   biến thể `auto` bị `reports=1`.

## Rủi ro & cách chặn

| Rủi ro | Chặn |
|---|---|
| Dữ liệu tone rác lan ra cả mạng lưới | Bỏ phiếu + ưu tiên `human` + `/admin/library` ẩn/ghim/xoá được từ xa |
| Tra cứu mạng làm chậm lúc mở bài | Chỉ gọi trong thread dò (đã xác minh 3 call site), timeout 10s, negative cache 24h, mọi lỗi đều fail-soft về luồng dò cũ |
| Lộ dữ liệu cá nhân | Chỉ gửi video_id + tên bài + chuỗi tone. Đường dẫn file local **không bao giờ** rời máy |
| Refactor `_authorize` làm thủng cổng Premium của Cloud Sync | Tham số `require_premium` mặc định `True`; `test_sync.py` chạy lại mỗi lần |
| Khách kích hoạt lỗi không gửi được ticket | `POST /ticket` cố tình không bắt buộc token |
| Bảng mới không có trên VPS sau deploy | Ghi rõ bước `python -m app.cli init-db` vào `server/deploy/DEPLOY.md` |

## Việc kèm theo

- Lưu bản kế hoạch này vào `docs/PLAN_HO_TRO_VA_THU_VIEN_TONE.md` (quy ước của
  dự án: plan sống trong `docs/`).
- Cập nhật `docs/SERVER_ARCHITECTURE.md` (thêm 2 router + 4 bảng mới) và
  `docs/manual/` (mục hướng dẫn khách dùng nút Hỗ trợ).
- `sync_version.py` + `core/version.py` khi phát hành 1.8.0 / 1.8.1.

---

## Trạng thái thực hiện (2026-08-24)

Đã hoàn thành cả Phần A và Phần B. Khác biệt so với kế hoạch ban đầu:

1. **`_resolve_tone` trả nhãn `'cache'` thay vì `'community'`.** Ba nơi gọi
   `_resolve_tone` chỉ rẽ nhánh theo `'manual'`/`'cache'`; thêm nhánh thứ ba
   nghĩa là sửa cả ba chỗ mà không được gì. `tone_share` đã ghi kết quả xuống
   `tone_cache.json` rồi, nên với engine đây ĐÚNG là một cú trúng cache và
   `_build_cache_result` xử lý sẵn đúng hình dạng dữ liệu. Nguồn gốc vẫn phân
   biệt được qua cờ `origin: "community"` trong entry cache.
2. **Không đóng góp ngược dữ liệu vừa tải về.** Kế hoạch không nói tới. Gửi lại
   bản vừa tải là tự bơm phiếu cho chính biến thể đó chứ không phải bằng chứng
   độc lập — `contribute()` bỏ qua entry có `origin == "community"` (trừ khi
   người dùng sửa tay, vì lúc đó là dữ liệu mới).
3. **Một máy chỉ giữ một phiếu cho mỗi bài.** Khi máy đóng góp biến thể mới cho
   bài đã từng bỏ phiếu, phiếu cũ bị rút (`_withdraw_other_votes`). Không có
   bước này thì một máy đổi ý ba lần là bơm phiếu cho ba biến thể mâu thuẫn.
4. **Không có test cho rate-limit hỗ trợ.** slowapi đếm theo IP và dùng chung cho
   cả phiên pytest, nên `conftest.py` phải nới hạn mức ra (đúng như đã làm với
   activate/verify/crash). Giới hạn `6/hour` chỉ được xác nhận bằng quan sát thủ
   công, không có test tự động.
5. **Toast báo có trả lời không có nút hành động.** `_show_message` bỏ qua
   `action_text` khi `is_error=False`; chấm đỏ trên nút Hỗ trợ mới là thứ giữ
   thông tin lâu dài.

Kiểm thử: server 99 test xanh (`server/tests/test_support.py` 8,
`test_library.py` 16, phần còn lại không đổi); client thêm
`tests/core/test_support.py` (12), `tests/core/test_tone_share.py` (15) và 5 test
mới trong `tests/core/test_engine.py`.

**Còn lại trước khi phát hành:** chạy thử end-to-end với server local theo mục
Kiểm thử, nâng version, và chạy `python -m app.cli init-db` trên VPS.
