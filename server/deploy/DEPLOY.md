# Triển khai QLS Server lên VPS Việt Nam

Hướng dẫn dựng từ con số 0 trên Ubuntu 22.04/24.04.

## 1. Chuẩn bị VPS

```bash
# Đăng nhập root
apt update && apt upgrade -y
apt install -y docker.io docker-compose-plugin nginx
systemctl enable --now docker
```

Trỏ domain (vd `license.quangluustudio.com`) về IP VPS (bản ghi A).

## 2. Lấy code + cấu hình

```bash
git clone <repo> /opt/qls && cd /opt/qls/server
cp .env.example .env
nano .env
```

Sinh secret:
```bash
openssl rand -hex 32   # dán vào LICENSE_SECRET
openssl rand -hex 32   # dán vào SESSION_SECRET
```

Đặt `POSTGRES_PASSWORD`, `BASE_URL=https://license.quangluustudio.com`.

Sinh hash mật khẩu admin:
```bash
docker compose run --rm api python -m app.cli hash-password 'matkhau_admin'
# dán kết quả vào ADMIN_PASSWORD_HASH
```

## 3. Khởi chạy

```bash
docker compose up -d --build
docker compose logs -f api      # xem log, đảm bảo "init-db" chạy xong
curl http://127.0.0.1:8000/healthz
```

## 4. Nginx + HTTPS

```bash
cp deploy/nginx.conf /etc/nginx/sites-available/qls
ln -s /etc/nginx/sites-available/qls /etc/nginx/sites-enabled/qls
nginx -t && systemctl reload nginx

apt install -y certbot python3-certbot-nginx
certbot --nginx -d license.quangluustudio.com
```

## 5. Tạo admin / mã / import mã cũ

```bash
# Tạo admin trong DB (thay cho .env)
docker compose exec api python -m app.cli create-admin admin 'matkhau'

# Sinh 50 mã mới (in ra màn hình)
docker compose exec api python -m app.cli gen-codes 50

# Import file mã cũ (mỗi dòng 1 mã)
docker compose cp ../activation_codes.txt api:/tmp/codes.txt
docker compose exec api python -m app.cli import-codes /tmp/codes.txt
```

Vào `https://license.quangluustudio.com/admin` để quản trị.

## 6. Cập nhật server

```bash
cd /opt/qls && git pull && cd server
docker compose up -d --build
```

## 7. Sao lưu

```bash
# DB
docker compose exec db pg_dump -U qls qls > backup_$(date +%F).sql
# File installer nằm trong volume `releases` (/var/lib/docker/volumes/...releases)
```

## Cấu hình client trỏ về server

Trong `app_config.json` (cạnh exe) của client, thêm:
```json
{ "license_server_url": "https://license.quangluustudio.com" }
```
Bỏ trống hoặc không có key này → client chạy chế độ kích hoạt offline cũ (fallback).
