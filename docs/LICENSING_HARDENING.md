# Siết bảo mật licensing — việc phải làm khi triển khai

> **Đọc trước khi deploy.** Bản này đổi cách ký license token. Server sẽ **không
> khởi động được** nếu thiếu khoá ký, và client bản cũ sẽ tự đổi token ở lần
> check-in đầu tiên.

## Tình trạng

| Phần | Trạng thái |
|---|---|
| Server `qlstudio.duckdns.org` | ✅ Đã triển khai 2026-08-04, đã kiểm chứng |
| Khoá ký RSA-2048 | ✅ `/data/keys/license_key.pem` (volume `server_keys`), quyền `0600` |
| `LICENSE_PUBLIC_KEY_N` trong client | ✅ Đã khớp khoá production |
| Bảng `trial_grants` | ✅ Đã tạo |
| `LICENSE_SECRET` (HS256 cũ) | ⏳ Vẫn giữ — xoá sau khi mọi máy lên bản mới |
| Build & phát hành client | ⏳ Chưa làm |

Sao lưu trước khi đổi: `/opt/qls/server/backups/20260804-203353/`
(`.env`, `db.sql` 485 KB, `docker-compose.yml`, `app-truoc.tar.gz`).

Khôi phục toàn bộ nếu cần:

```bash
cd /opt/qls/server
B=backups/20260804-203353
cp $B/.env .env && cp $B/docker-compose.yml . && tar xzf $B/app-truoc.tar.gz
docker compose up -d --build
# Nếu cần cả dữ liệu: docker compose exec -T db psql -U qls -d qls < $B/db.sql
```

Các phần dưới đây giữ lại làm hướng dẫn cho lần dựng mới hoặc lần đổi khoá.

## Đã đổi những gì

| Trước | Sau |
|---|---|
| Token ký HS256, client không kiểm chữ ký | Token ký **RS256**, client xác minh bằng public key nhúng sẵn |
| Quyền đọc từ field thô trong `activation.json` | Quyền đọc từ **claim đã xác minh chữ ký** |
| Kích hoạt offline bằng checksum, 2 secret nằm trong mã nguồn | Bỏ hẳn — mọi kích hoạt qua server, exe không còn secret nào |
| `license_server_url` rỗng ⇒ tắt licensing | URL rỗng ⇒ rơi về hằng số trong code, không tắt được |
| Thu hồi có hiệu lực sau ≤ 7 ngày | Xoá cache ngay khi server báo thu hồi; check-in lại mỗi 6 giờ |
| Dùng thử reset bằng cách xoá 1 file | Neo theo fingerprint ở server + bản sao trong registry |
| Cloud Sync chấp nhận mã thô, không kiểm gói | Bắt buộc token; kiểm lại status + gói + thiết bị trong DB mỗi lần gọi |

## Các bước triển khai (theo đúng thứ tự)

Cả bốn bước server đã được gói vào một script idempotent, chạy trên VPS trong
thư mục `server/`:

```bash
bash deploy/upgrade_rs256.sh
```

Script tự sao lưu `.env` + `pg_dump`, build image, sinh khoá (từ chối nếu đã có),
sửa `.env`, khởi động lại, kiểm tra healthz và bảng `trial_grants`, rồi in khối
modulus. Nếu server không lên trong 30 giây, script in log và lệnh khôi phục.

Phần dưới mô tả từng bước nếu cần làm tay.

### 1. Sinh khoá ký trên VPS

```bash
docker compose run --rm --no-deps api python -m app.cli gen-license-keys /data/keys/license_key.pem
```

Phải `docker compose build api` **trước**, vì image cũ chưa có `cryptography`.
Lệnh in ra khối modulus. **Giữ lại khối đó** cho bước 2. Lấy lại về sau bằng
`docker compose exec api python -m app.cli show-license-pubkey`.

### 2. Dán public key vào client rồi build lại

Mở `core/licensing/jwt_verify.py`, thay giá trị `LICENSE_PUBLIC_KEY_N` bằng khối
vừa in. Giá trị đang có trong repo ứng với cặp khoá test — **không dùng cho
production**. Sai bước này thì app từ chối mọi token server cấp.

Build lại installer như thường lệ (`build_installer.bat`).

### 3. Cập nhật `.env` trên VPS

```ini
LICENSE_PRIVATE_KEY_PATH=/data/keys/license_key.pem
# Giữ nguyên secret HS256 cũ cho tới khi mọi máy đã lên bản mới:
LICENSE_SECRET=<secret HS256 đang chạy>
TRIAL_DAYS=3
```

`LICENSE_SECRET` chỉ còn dùng để **đọc** token của máy chưa cập nhật, không bao
giờ dùng để ký. Xoá dòng đó sau khi tất cả máy đã lên bản mới.

### 4. Tạo bảng mới

Bản này thêm bảng `trial_grants`:

```bash
docker compose run --rm api python -m app.cli init-db
```

### 5. Deploy server rồi mới phát bản client mới

Thứ tự này quan trọng: client mới cần server đã biết ký RS256.

## Chuyện gì xảy ra với máy đang chạy

1. Máy cập nhật lên bản mới, mở app.
2. `startup_reconcile()` thấy token cũ không xác minh được → tự check-in.
3. Server đọc được token cũ (nhờ `LICENSE_SECRET`), cấp token RS256 mới.
4. Người dùng không thấy gì khác thường.

Máy **không có mạng** lúc cập nhật sẽ phải kích hoạt lại khi có mạng. Đây là hệ
quả trực tiếp của việc bỏ kích hoạt offline — không có cách nào vừa giữ được
đường lui offline vừa đóng lỗ hổng tự chế token.

## Đổi khoá về sau

Đổi cặp khoá làm **mọi token đã cấp mất hiệu lực**. Máy có mạng sẽ tự lấy token
mới ở lần mở app; máy offline phải kích hoạt lại. Chỉ đổi khi nghi private key
bị lộ, và nhớ build lại client cùng lúc.

## Còn lại gì không bịt được

- **Vá nhị phân.** Ai sửa được file exe thì bỏ qua được mọi lệnh kiểm tra. Đây là
  giới hạn chung của phần mềm chạy trên máy người dùng, không phải lỗ hổng của
  thiết kế này. Khoá ký chỉ ngăn việc *chế giấy phép*, không ngăn việc *sửa app*.
- **Chia sẻ máy đã kích hoạt.** Fingerprint ràng theo máy, không ràng theo người.
- **Dùng thử với Windows cài lại.** MachineGuid đổi khi cài lại Windows → máy đó
  xin được bản dùng thử mới.
