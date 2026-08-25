# Quang Lưu Studio — License/Update/Crash Server

## Context

Client hiện tại (desktop PyQt) có 3 điểm yếu cần một server tập trung khắc phục:

1. **Kích hoạt offline** (`core/activation.py`): mã `XXXX-XXXX-XXXX-XXXX-CHK` chỉ kiểm checksum MD5 ngay trên máy. Không biết ai dùng mã nào, mã không one-time, trial/hạn dùng reset được bằng cách xoá `activation.json`, secret từng bị lộ trên GitHub.
2. **Cập nhật phụ thuộc GitHub Releases** (`core/updater/`): không kiểm soát được rollout, version targeting, kênh beta.
3. **Báo lỗi chỉ log local** (`core/logger.py` → `app.log`, `errors.log`): không gửi về đâu, không biết user gặp lỗi gì.

Server giải quyết: quản lý user + mã kích hoạt (online, khoá theo máy), lưu & phân phối bản cập nhật, nhận crash report tự động.

## Quyết định đã chốt

| Hạng mục | Lựa chọn |
|---|---|
| Hosting | VPS Việt Nam, tự quản (Linux + Docker) |
| Kích hoạt | Online + khoá theo máy (device fingerprint), có **offline grace N ngày** |
| File update | Lưu & phục vụ ngay trên server (HTTP, hỗ trợ Range resume) |
| Báo lỗi | Endpoint tự xây |
| Vị trí code | `server/` trong repo này (secret CHỈ trong `.env`, không commit) |
| Admin | Web UI nội bộ (FastAPI + Jinja2 + HTMX) |

## Stack

- **FastAPI** (Python — đồng bộ ngôn ngữ với client) + Uvicorn/Gunicorn
- **PostgreSQL 16** (qua docker-compose) + **SQLAlchemy 2** + **Alembic** migrations
- **Nginx** reverse proxy + TLS (Certbot/Let's Encrypt)
- **slowapi** rate-limit; **passlib[bcrypt]** hash mật khẩu admin; **itsdangerous/PyJWT** ký license token
- Jinja2 + HTMX cho admin UI

## Cấu trúc thư mục

```
server/
  app/
    main.py              # FastAPI app, mount routers + admin
    config.py            # đọc env: DB_URL, LICENSE_SECRET, ADMIN_*, STORAGE_DIR, GRACE_DAYS
    db.py                # engine + SessionLocal + get_db dependency
    models.py            # SQLAlchemy: User, License, Device, AppVersion, CrashReport,
                         #   SyncBlob, SupportTicket, SupportMessage, SharedTone,
                         #   SharedToneVote, AdminUser
    schemas.py           # Pydantic request/response
    security.py          # HMAC/JWT license token, device binding, admin session auth, rate-limit
    deps.py              # shared dependencies
    routers/
      activation.py      # POST /api/v1/activate, POST /api/v1/license/verify
      updates.py         # GET /api/v1/updates/check, GET /api/v1/updates/download/{version}
      crashes.py         # POST /api/v1/crash
      support.py         # POST /api/v1/support/* — hỗ trợ hai chiều khách ↔ dev
      library.py         # POST /api/v1/library/* — thư viện tone cộng đồng
      sync.py            # POST/PUT /api/v1/sync/* — Cloud Sync riêng tư (Premium)
      admin.py           # /admin/* web UI (login, users, licenses, versions,
                         #   crashes, support, library)
    services/
      codegen.py         # sinh mã + checksum (thuật toán dùng chung với client)
      licensing.py       # logic activate/verify/revoke/expiry/device-limit
                         #   + authorize_device(require_premium=...) dùng chung
                         #     cho sync.py (True) và library.py (False)
      tonelib.py         # chuẩn hoá/băm/xếp hạng biến thể tone cộng đồng
      storage.py         # lưu/đọc .exe, tính sha256, stream + Range
    templates/           # Jinja2 admin
    static/
  alembic/               # migrations
  tests/                 # pytest cho từng router
  requirements.txt
  Dockerfile
  docker-compose.yml     # api + postgres
  .env.example
  deploy/
    nginx.conf
    DEPLOY.md            # hướng dẫn dựng VPS VN từ A→Z
```

## Mô hình dữ liệu

- **users**: id, name, email, phone, note, created_at
- **licenses**: id, code (unique), user_id?, plan, status(`unused|active|revoked|expired`), max_devices(default 1), issued_at, activated_at?, expires_at?, created_at
- **devices**: id, license_id, fingerprint(unique per license), hostname, os, app_version, first_seen, last_seen, last_check_in, revoked
- **app_versions**: id, version, channel(`stable|beta`), filename, sha256, size_bytes, release_notes, mandatory(bool), min_supported_version?, rollout_percent(0-100), is_active, published_at
- **crash_reports**: id, fingerprint_hash(dedupe), license_id?, device_id?, app_version, os_info, traceback, log_excerpt, count, status(`new|seen|resolved`), first_seen, last_seen
- **support_tickets**: id, ticket_code(`HT-000123`), license_code?, device_fp?, hostname?, os_info?, app_version?, contact?, category(`loi|huong_dan|tinh_nang|khac`), subject, status(`new|open|answered|closed`), log_excerpt?, unread_client, created_at, updated_at
- **support_messages**: id, ticket_id, sender(`customer|dev`), body, created_at
- **shared_tones**: id, song_key(YouTube video_id), payload_hash(sha256 timeline đã chuẩn hoá), title, primary_key, timeline(JSON), source(`auto|human`), votes, reports, pinned, status(`ok|hidden`), first_seen, last_seen — unique(song_key, payload_hash)
- **shared_tone_votes**: id, tone_id, device_fp, kind(`vote|report`), created_at — unique(tone_id, device_fp, kind)
- **admin_users**: id, username, password_hash

## API client-facing (`/api/v1`)

- `POST /activate` — body `{code, device_fingerprint, hostname, os, app_version}`.
  Server kiểm format+checksum (reuse thuật toán hiện tại) **và** record DB; ràng device; kiểm `max_devices`; set `activated_at`/`expires_at` nếu lần đầu. Trả **license token** (JWT ký bằng `LICENSE_SECRET`, chứa fingerprint + exp + grace) để client cache.
- `POST /license/verify` — body `{token | code, device_fingerprint}`. Trả `{valid, status, days_remaining, token(refreshed)}`. Cập nhật `last_check_in`. Dùng cho check-in định kỳ.
- `GET /updates/check?version=&channel=&fingerprint=` — trả bản mới nhất áp dụng được (tôn trọng rollout_percent theo hash fingerprint), `{version, download_url, sha256, size, mandatory, notes}` — **giữ nguyên shape `ReleaseInfo`** để client tái dùng.
- `GET /updates/download/{version}` — stream `.exe`, hỗ trợ `Range` (downloader hiện tại đã gửi Range để resume).
- `POST /crash` — body `{fingerprint, app_version, os, traceback, log_excerpt}`. Dedupe theo hash(traceback), rate-limit, tăng `count`.
- `POST /support/ticket` · `/support/ticket/reply` · `/support/inbox` · `/support/ticket/read` —
  kênh hỗ trợ hai chiều. **Không đòi license token**: máy đang không kích hoạt được chính là máy
  cần hỗ trợ nhất. Ràng theo `device_fingerprint` (biết mã ticket thôi không đọc được), chống lạm
  dụng bằng `RATE_LIMIT_SUPPORT` (mặc định 6/giờ).
- `POST /library/lookup` · `/library/contribute` · `/library/report` — thư viện tone cộng đồng.
  Cần license token nhưng **không giới hạn Premium** (khác `/sync`): thư viện sống bằng hiệu ứng
  mạng, chặn Standard đóng góp là tự bóp nguồn dữ liệu. Mỗi máy 1 phiếu/biến thể; bản `human`
  nhân hệ số 3, mỗi lượt báo sai trừ 2; `song_key` chỉ nhận video_id YouTube 11 ký tự.

## Admin Web UI (`/admin`, đăng nhập mật khẩu)

- Đăng nhập (session cookie ký).
- **Users**: tạo/sửa, xem license & device gắn theo user.
- **Licenses**: sinh hàng loạt, gán user, thu hồi (`revoked`), gia hạn (`expires_at`), **reset device** (gỡ ràng máy để user đổi máy).
- **Versions**: upload `.exe` (tự tính sha256, lưu vào `STORAGE_DIR`), đặt channel/rollout/mandatory/min_version, bật/tắt active.
- **Crashes**: danh sách gom theo fingerprint, xem traceback + log, đánh dấu resolved.
- **Support**: hộp thư hỗ trợ, lọc theo trạng thái, xem hội thoại, trả lời (khách đọc trong app), đổi trạng thái.
- **Library**: các biến thể tone của từng bài kèm điểm; ghim / ẩn / xoá biến thể rác — van an toàn duy nhất để sửa dữ liệu cộng đồng từ xa.

## Bảo mật

- HTTPS-only (Nginx + Certbot). HSTS.
- `LICENSE_SECRET`, mật khẩu admin, DB password: **chỉ trong `.env`**, không commit. `.env.example` làm mẫu.
- License token JWT có `exp` ngắn (vd 7 ngày = grace) + nhúng fingerprint → client chạy offline trong hạn, hết hạn phải verify lại.
- Rate-limit `/activate`, `/license/verify`, `/crash`, `/support/*`, `/library/*` (slowapi + nginx).
- Client KHÔNG còn giữ secret kích hoạt (chỉ check format). Thẩm quyền checksum chuyển hẳn về server.

## Thay đổi phía client (`core/`)

- **`core/licensing/`** (mới) hoặc mở rộng `core/activation.py`:
  - `device.py`: sinh device fingerprint ổn định (Windows MachineGuid registry + MAC + CPU → hash). Một ID/máy.
  - `client.py`: `activate_online(code)`, `verify_license()` — gọi server, cache token trong `activation.json`, áp dụng grace offline.
  - Giữ API cũ của `ActivationManager` (`needs_activation`, `is_activated`, `get_days_remaining`) để UI không phải đổi nhiều — backend đổi sang token server + grace.
- **`core/updater/_version_check.py`**: đổi `GITHUB_RELEASES_API` → `{LICENSE_SERVER_URL}/api/v1/updates/check`. Giữ dataclass `ReleaseInfo`. Downloader (`_downloader.py`) đã generic + Range nên dùng lại nguyên.
- **`core/crash_reporter.py`** (mới): cài `sys.excepthook` + Qt hook; khi crash thu traceback + tail `errors.log` + device/version → POST `/api/v1/crash`. Có hàng đợi offline + dedupe + xin phép (tôn trọng accessibility/settings). Hook vào `core/logger.py`.
- **`app_config.json`**: thêm `license_server_url` (AppConfig đã hỗ trợ key tuỳ ý qua `.get` — admin sửa được không cần build lại).

## Tương thích & migrate

- Import các mã đã phát hành hiện có vào bảng `licenses` (status `unused`/`active`), để user cũ không bị khoá.
- Bản client chuyển tiếp: ưu tiên online, nhưng nếu server chưa cấu hình (`license_server_url` rỗng) thì fallback validate offline như cũ → triển khai dần.
- Lần verify online đầu tiên của user cũ sẽ bind máy hiện tại.

## Kiểm thử (verification)

- **Server**: `pytest` cho mỗi router — activate (hợp lệ/sai/đã thu hồi/quá max_devices), verify (token còn hạn/hết hạn/revoked), updates check (rollout %, mandatory), crash dedupe. Chạy local bằng `docker-compose up`, test bằng `curl`/httpie.
- **Client**: unit test fingerprint ổn định, cache token + grace, updater trỏ server (mock). Bổ sung vào `tests/core/`.
- **E2E**: chạy app trỏ server local → kích hoạt → check update → ép 1 crash → thấy report trong `/admin/crashes`.

## Thứ tự triển khai

1. Scaffold `server/` (config, db, models, schemas, security, services).
2. Router activation + licensing + codegen (reuse checksum).
3. Router updates + storage (upload/serve .exe).
4. Router crashes.
5. Admin web UI (login + 4 trang quản lý).
6. Alembic migration + docker-compose + nginx + DEPLOY.md.
7. Server tests.
8. Client: device fingerprint + online activation (giữ API cũ + fallback).
9. Client: updater trỏ server + crash reporter.
10. Client tests + E2E.
