# Triển khai QLS Server bằng DuckDNS + HTTPS (KHÔNG cần mua tên miền)

Hướng dẫn dựng server license/update từ số 0 trên **VPS Vietnix (Ubuntu 22.04/24.04)**,
dùng subdomain **DuckDNS miễn phí** để vẫn có HTTPS (Let's Encrypt) và một tên cố định —
nhờ vậy đổi/di chuyển VPS không phải sửa lại cấu hình trên từng máy khách.

> Nếu bạn đã có tên miền thật, dùng [`DEPLOY.md`](DEPLOY.md) thay cho file này.

Trong toàn bộ tài liệu, thay các chỗ giữ chỗ:
- `<TEN>` = tên DuckDNS bạn chọn (vd `quangluu` → host đầy đủ `quangluu.duckdns.org`)
- `<TOKEN>` = token DuckDNS của bạn
- `<IP>` = địa chỉ IP của VPS Vietnix
- `<repo>` = URL git của dự án

---

## 1. Chuẩn bị (làm một lần, miễn phí)

1. Vào https://www.duckdns.org, đăng nhập bằng Google/GitHub.
2. Tạo subdomain `<TEN>` → bấm **add domain**.
3. Copy chuỗi **token** hiển thị ở đầu trang (dùng ở bước 2).
4. Mua/nhận VPS Vietnix — khuyến nghị **2 vCPU / 4 GB RAM / 40 GB+ NVMe SSD**, hệ điều hành
   **Ubuntu 22.04 hoặc 24.04**. Chọn dòng VPS NVMe, ưu tiên băng thông cao (tải installer
   tốn băng thông). Ghi lại **IP** và **mật khẩu root** rồi SSH vào máy:
   ```bash
   ssh root@<IP>
   ```

---

## 2. Trỏ DuckDNS về VPS + tự cập nhật IP

```bash
# Trỏ ngay lần đầu
curl "https://www.duckdns.org/update?domains=<TEN>&token=<TOKEN>&ip=<IP>"
# → in ra "OK" là thành công

# Đặt cron mỗi 5 phút tự cập nhật (phòng khi IP VPS đổi)
mkdir -p ~/duckdns
echo 'curl -k -s "https://www.duckdns.org/update?domains=<TEN>&token=<TOKEN>&ip=" >/dev/null' > ~/duckdns/duck.sh
chmod +x ~/duckdns/duck.sh
( crontab -l 2>/dev/null; echo "*/5 * * * * ~/duckdns/duck.sh" ) | crontab -
```

Kiểm tra tên đã phân giải đúng IP:
```bash
ping -c1 <TEN>.duckdns.org
```

---

## 3. Cài môi trường + mở firewall

```bash
apt update && apt upgrade -y
apt install -y docker.io docker-compose-plugin nginx
systemctl enable --now docker

# Nếu VPS bật ufw, mở SSH + HTTP + HTTPS
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable
```

---

## 4. Lấy code + cấu hình `.env`

```bash
git clone <repo> /opt/qls && cd /opt/qls/server
cp .env.example .env

# Sinh 2 secret ngẫu nhiên
openssl rand -hex 32   # → dán vào LICENSE_SECRET
openssl rand -hex 32   # → dán vào SESSION_SECRET

nano .env
```

Trong `.env` cần đặt:
- `BASE_URL=https://<TEN>.duckdns.org`  ← **quan trọng**, dùng để sinh link tải update
- `POSTGRES_PASSWORD=...` và `DATABASE_URL=postgresql+psycopg2://qls:<mật khẩu vừa đặt>@db:5432/qls`
- `LICENSE_SECRET`, `SESSION_SECRET` = 2 chuỗi vừa sinh
- **Giữ nguyên `CODE_SECRET`** (mặc định trong file) để các mã kích hoạt đã bán vẫn verify được
- `ADMIN_PASSWORD_HASH` — sinh ở dưới

Sinh hash mật khẩu admin rồi dán vào `ADMIN_PASSWORD_HASH`:
```bash
docker compose run --rm api python -m app.cli hash-password 'matkhau_admin'
```

---

## 5. Khởi chạy (Postgres + API qua Docker)

```bash
docker compose up -d --build
docker compose logs -f api          # chờ tới khi init-db chạy xong, không còn lỗi
curl http://127.0.0.1:8000/healthz  # phải trả về OK
```

---

## 6. Nginx reverse proxy + HTTPS

```bash
cp deploy/nginx.conf /etc/nginx/sites-available/qls
nano /etc/nginx/sites-available/qls
```

Trong file, **sửa dòng `server_name`** thành tên DuckDNS của bạn:
```nginx
server_name <TEN>.duckdns.org;
```
(Giữ nguyên `client_max_body_size 600M` để upload installer lớn, và block
`location /api/v1/updates/download/` đã tắt buffering + timeout 600s để tải file lớn,
hỗ trợ resume qua HTTP Range.)

Kích hoạt site và xin chứng chỉ:
```bash
ln -s /etc/nginx/sites-available/qls /etc/nginx/sites-enabled/qls
nginx -t && systemctl reload nginx

apt install -y certbot python3-certbot-nginx
certbot --nginx -d <TEN>.duckdns.org
# Let's Encrypt cấp cert cho *.duckdns.org bình thường; chọn redirect HTTP → HTTPS khi được hỏi
```

Certbot tự thêm block `443` + tự gia hạn cert. Kiểm tra:
```bash
curl https://<TEN>.duckdns.org/healthz   # OK, không cảnh báo cert
```

---

## 7. Tạo admin / sinh mã / import mã cũ

```bash
# Tạo admin trong DB (thay cho .env)
docker compose exec api python -m app.cli create-admin admin 'matkhau'

# Sinh 50 mã mới (in ra màn hình)
docker compose exec api python -m app.cli gen-codes 50

# Import file mã cũ (mỗi dòng 1 mã) nếu có
docker compose cp ../activation_codes.txt api:/tmp/codes.txt
docker compose exec api python -m app.cli import-codes /tmp/codes.txt
```

Quản trị tại: `https://<TEN>.duckdns.org/admin`

---

## 8. Trỏ client về server (ghi sẵn khi build)

Trong repo client, sửa `app_config.json` (key `license_server_url`) **cho khớp chính xác**
`BASE_URL` ở server:
```json
"license_server_url": "https://<TEN>.duckdns.org"
```
Giá trị này được đóng gói vào installer, nên mọi máy khách cài ra đã tự trỏ về server —
người dùng cuối không phải chỉnh gì. Để rỗng `""` = client quay về chế độ kích hoạt offline cũ.

---

## 9. Phát hành bản cập nhật đầu tiên

1. Build `QuangLuuStudio_Setup_x.y.z.exe` bằng Inno Setup như thường lệ.
2. Vào `https://<TEN>.duckdns.org/admin` → **Versions** → **Upload**:
   - `version`: đặt **cao hơn** version client hiện tại (client đang `1.5.1`, ví dụ nhập `1.6.0`)
   - `channel`: `stable`
   - `release_notes`: mô tả thay đổi (hiện trong hộp thoại cập nhật của app)
   - Tùy chọn `mandatory` (bắt buộc cập nhật) và `rollout_percent` (thả dần: đặt `30` để ~30%
     máy nhận trước, sau nâng lên `100`)
   - Chọn file `.exe`
3. Server **tự tính SHA256 + kích thước** khi upload. Xong — lần sau client mở app hoặc bấm
   "Kiểm tra cập nhật" sẽ thấy bản mới, tải về, chạy installer đè và tự khởi động lại.

---

## 10. Cập nhật server & sao lưu

```bash
# Cập nhật code server
cd /opt/qls && git pull && cd server
docker compose up -d --build

# Sao lưu DB
docker compose exec db pg_dump -U qls qls > backup_$(date +%F).sql
# File installer nằm trong volume `releases`
```

---

## Kiểm thử end-to-end

1. **Server sống**: `curl https://<TEN>.duckdns.org/healthz` → OK; đăng nhập được `/admin`.
2. **Check update** (sau khi upload `1.6.0`):
   ```bash
   curl "https://<TEN>.duckdns.org/api/v1/updates/check?version=1.5.1&channel=stable&fingerprint=test"
   ```
   Kỳ vọng JSON: `update_available=true`, `version="1.6.0"`,
   `download_url=".../api/v1/updates/download/1.6.0"`, có `sha256`.
3. **Tải + resume**:
   ```bash
   curl -I "https://<TEN>.duckdns.org/api/v1/updates/download/1.6.0"
   ```
   Kiểm tra header `Accept-Ranges: bytes`; tải thử file `.exe` xem toàn vẹn.
4. **Luồng thật**: build client với `app_config.json` đã trỏ URL, chạy app bản `1.5.1` →
   mục Kiểm tra cập nhật hiện `1.6.0` → tải → cài đè → mở lại thấy version mới.
5. **HTTPS hợp lệ**: mở `https://<TEN>.duckdns.org/admin` trên trình duyệt, không cảnh báo cert.
