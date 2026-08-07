#!/usr/bin/env bash
#
# Nâng cấp server license sang token ký RS256 — chạy TRÊN VPS, trong thư mục
# server/ của repo (vd /opt/qls/server).
#
#     bash deploy/upgrade_rs256.sh
#
# Script idempotent: chạy lại lần hai không sinh khoá mới, không mất dữ liệu.
# Kết thúc, script in ra khối LICENSE_PUBLIC_KEY_N để dán vào client.
set -euo pipefail

cd "$(dirname "$0")/.."
STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="./backups/$STAMP"

say() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

[ -f .env ] || { echo "Không thấy .env trong $(pwd)"; exit 1; }

say "1/7 · Sao lưu .env và cơ sở dữ liệu"
mkdir -p "$BACKUP_DIR"
cp .env "$BACKUP_DIR/.env"
if docker compose ps --status running --services 2>/dev/null | grep -qx db; then
    docker compose exec -T db pg_dump -U "${POSTGRES_USER:-qls}" "${POSTGRES_DB:-qls}" \
        > "$BACKUP_DIR/db.sql"
    echo "   DB dump: $BACKUP_DIR/db.sql ($(wc -c < "$BACKUP_DIR/db.sql") byte)"
else
    echo "   (db chưa chạy — bỏ qua dump)"
fi

say "2/7 · Build image mới"
# PHẢI build trước khi sinh khoá: image cũ chưa có `cryptography`, mà lệnh
# gen-license-keys cần thư viện đó để tạo RSA.
docker compose build api

say "3/7 · Sinh khoá ký nếu chưa có"
# gen-license-keys tự từ chối nếu file đã tồn tại → an toàn khi chạy lại.
docker compose run --rm --no-deps api \
    python -m app.cli gen-license-keys /data/keys/license_key.pem 2>&1 | tee /tmp/qls_keygen.txt || true
if grep -q "đã tồn tại" /tmp/qls_keygen.txt; then
    echo "   Khoá đã có từ trước — giữ nguyên, KHÔNG sinh khoá mới."
fi

say "4/7 · Cập nhật .env"
set_env() {
    local key="$1" value="$2"
    if grep -q "^${key}=" .env; then
        sed -i "s|^${key}=.*|${key}=${value}|" .env
    else
        printf '%s=%s\n' "$key" "$value" >> .env
    fi
    echo "   ${key}=${value}"
}
set_env LICENSE_PRIVATE_KEY_PATH /data/keys/license_key.pem
grep -q "^TRIAL_DAYS=" .env || set_env TRIAL_DAYS 3
# LICENSE_SECRET giữ nguyên: còn dùng để đọc token HS256 của máy chưa cập nhật.
if grep -q "^LICENSE_SECRET=$" .env; then
    echo "   CẢNH BÁO: LICENSE_SECRET rỗng — máy chạy bản cũ sẽ phải kích hoạt lại."
fi

say "5/7 · Khởi động lại (init-db tự tạo bảng trial_grants)"
docker compose up -d

say "6/7 · Kiểm tra sức khoẻ"
for i in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:8000/healthz > /dev/null 2>&1; then
        echo "   healthz OK sau ${i}s"
        break
    fi
    [ "$i" = 30 ] && {
        echo "   LỖI: server không lên. Log:"
        docker compose logs --tail 40 api
        echo "   Khôi phục: cp $BACKUP_DIR/.env .env && docker compose up -d"
        exit 1
    }
    sleep 1
done
docker compose exec -T api python -c "
from app.db import SessionLocal
from app.models import TrialGrant
with SessionLocal() as db:
    db.query(TrialGrant).count()
print('   bảng trial_grants sẵn sàng')
"

say "7/7 · Public key để dán vào client"
docker compose exec -T api python -m app.cli show-license-pubkey

cat <<'EOF'

Việc còn lại (trên máy dev):
  1. Dán khối giữa BEGIN_MODULUS_BLOCK/END_MODULUS_BLOCK vào LICENSE_PUBLIC_KEY_N
     trong core/licensing/jwt_verify.py
  2. Build lại installer, phát hành bản mới
Máy khách bản cũ vẫn chạy bình thường tới lúc đó.
EOF
