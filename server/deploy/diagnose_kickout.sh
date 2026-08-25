#!/usr/bin/env bash
# Phase 0 của docs/LICENSING_KICKOUT_FIX_PLAN.md — đo xem nguyên nhân nào đang
# làm máy khách bị đá ra màn hình kích hoạt.
#
# Chạy trên VPS, trong thư mục có docker-compose.yml (thường /opt/qls/server):
#     bash deploy/diagnose_kickout.sh
#
# Chỉ ĐỌC, không sửa gì. Chép nguyên output gửi lại để đối chiếu với bảng
# "Kết quả đo" trong plan.
set -u

DB="docker compose exec -T db psql -U ${POSTGRES_USER:-qls} -d ${POSTGRES_DB:-qls} -qAt -c"
NGINX_LOG=${NGINX_LOG:-/var/log/nginx/access.log}

hr() { printf '\n── %s %s\n' "$1" "$(printf '─%.0s' $(seq $((60 - ${#1}))))"; }

hr "0. Bối cảnh"
echo "Thời điểm đo: $(date -Is)"
$DB "SELECT 'licenses=' || count(*) FROM licenses;" 2>/dev/null
$DB "SELECT 'devices=' || count(*) FROM devices;" 2>/dev/null
grep -E '^(GRACE_DAYS|RATE_LIMIT)' .env 2>/dev/null || echo "(.env: chưa đặt GRACE_DAYS/RATE_LIMIT)"

hr "E. Fingerprint drift — một máy đăng ký nhiều lần?"
echo "(cùng hostname trong một license = fingerprint đã đổi; n>1 là dấu hiệu)"
$DB "SELECT hostname || ' | license ' || license_id || ' | ' || count(*) || ' bản ghi | lần đầu '
          || min(first_seen)::date || ' → ' || max(first_seen)::date
       FROM devices WHERE hostname IS NOT NULL
      GROUP BY hostname, license_id HAVING count(*) > 1
      ORDER BY count(*) DESC LIMIT 20;"
echo "--- tổng số máy dư thừa do drift:"
$DB "SELECT coalesce(sum(n - 1), 0) FROM (
       SELECT count(*) n FROM devices WHERE hostname IS NOT NULL
        GROUP BY hostname, license_id HAVING count(*) > 1) s;"

hr "D. Máy đang kẹt vì bị revoked (nút 'Reset máy' khoá vĩnh viễn)"
$DB "SELECT count(*) || ' thiết bị đang revoked' FROM devices WHERE revoked;"
$DB "SELECT l.code || ' | ' || coalesce(d.hostname,'?') || ' | last_seen ' || d.last_seen::date
       FROM devices d JOIN licenses l ON l.id = d.license_id
      WHERE d.revoked ORDER BY d.last_seen DESC LIMIT 20;"

hr "B. Máy quá hạn grace (sắp/đang bị đá ra)"
for n in 7 14 30; do
  $DB "SELECT '> $n ngày không check-in: ' || count(*) FROM devices
        WHERE NOT revoked AND last_check_in < now() - interval '$n days';"
done
$DB "SELECT coalesce(hostname,'?') || ' | v' || coalesce(app_version,'?')
          || ' | check-in cuối ' || coalesce(last_check_in::date::text,'chưa bao giờ')
       FROM devices WHERE NOT revoked
        AND (last_check_in IS NULL OR last_check_in < now() - interval '7 days')
      ORDER BY last_check_in NULLS FIRST LIMIT 30;"

hr "A+C. Lỗi tạm thời trả về cho client (429/5xx) — thủ phạm xoá license"
if [ -r "$NGINX_LOG" ]; then
  echo "Nguồn: $NGINX_LOG"
  echo "--- toàn bộ log, theo mã trạng thái (chỉ endpoint license):"
  grep -E 'api/v1/(license/verify|activate|trial)' "$NGINX_LOG" 2>/dev/null \
    | awk '{print $9}' | sort | uniq -c | sort -rn
  echo "--- 24 giờ gần nhất:"
  grep "$(date -d '-1 day' '+%d/%b/%Y')" "$NGINX_LOG" 2>/dev/null \
    | grep -E 'api/v1/(license|activate|trial)' \
    | awk '$9 ~ /^(429|5[0-9][0-9])$/ {print $9}' | sort | uniq -c
  echo "--- số IP KHÁC NHAU gọi verify (nếu ~1 thì rate-limit đang dùng chung xô):"
  grep 'api/v1/license/verify' "$NGINX_LOG" 2>/dev/null | awk '{print $1}' | sort -u | wc -l
else
  echo "Không đọc được $NGINX_LOG (đặt NGINX_LOG=... nếu để chỗ khác)"
fi

hr "C. Server có thấy IP thật của khách không?"
echo "(Thiếu --forwarded-allow-ips thì mọi khách hàng chung một hạn mức rate-limit)"
CMD=$(docker inspect --format '{{join .Config.Cmd " "}}' "$(docker compose ps -q api)" 2>/dev/null)
case "$CMD" in
  *forwarded-allow-ips*) echo "OK — có --forwarded-allow-ips" ;;
  "")                    echo "? — không đọc được CMD của container api" ;;
  *) echo "→ THIẾU --forwarded-allow-ips: mọi khách hàng đang dùng chung một hạn mức rate-limit" ;;
esac

hr "Xong"
echo "Đối chiếu với mục 7 'Kết quả đo' trong docs/LICENSING_KICKOUT_FIX_PLAN.md"
