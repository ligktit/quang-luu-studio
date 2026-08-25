# Kế hoạch xử lý: máy đã kích hoạt nhưng vài ngày sau bị đá ra

> **Triệu chứng khách báo:** nhập mã kích hoạt thành công, dùng bình thường vài
> ngày, rồi app hiện *"⚠️ Bản quyền đã hết hạn! Vui lòng nhập mã kích hoạt mới."*
> Nhập lại mã thì chạy tiếp — hoặc tệ hơn, báo *"Mã đã đạt giới hạn 1 thiết bị"* /
> *"Thiết bị này đã bị thu hồi quyền"* và kẹt luôn.
>
> Trạng thái: soạn 2026-08-12.
> **Phase 0** ✅ đã đo trên production 2026-08-12 22:00 (xem mục 7).
> **Phase 1** ✅ **ĐÃ DEPLOY** lên `qlstudio.duckdns.org` 2026-08-12 22:05, đã kiểm chứng trực tiếp.
> **Phase 2** ✅ **ĐÃ DEPLOY** 2026-08-12 22:20 (code). Phần dọn dữ liệu: **chủ ý bỏ qua** — xem ghi chú dưới.
> **Phase 3** ✅ code xong trong worktree `D:\Projects\LiveStudio\qls-hotfix-1.6.3`
> (nhánh `fix/licensing-kickout`, tách từ tag 1.6.2).
> **Phase 4** ✅ server **ĐÃ DEPLOY** 2026-08-12 23:30; client code xong cùng worktree.
> Client: **394/394 xanh** · Server: **78/78 xanh**.
> **Phát hành** ✅ **v1.6.3 ĐÃ LÊN GITHUB** 2026-08-14 — xem mục 8.
> Phase 5 📋 chưa làm.
>
> 📌 **Đổi kế hoạch phát hành:** gộp Phase 3 + 4 vào **một bản 1.6.3** thay vì
> tách 1.6.3/1.6.4. Lý do: đội hình chỉ 55 license / 66 máy, mà 12 bản ghi thừa
> và 23 lần lỗi 409 đều do drift — tách hai đợt nghĩa là khách phải chịu thêm một
> vòng "đủ giới hạn thiết bị" nữa. Phần server của Phase 4 đã lên trước và tương
> thích ngược hoàn toàn (client cũ không gửi `legacy_fingerprint` thì chạy y như
> cũ), nên rủi ro gộp là chấp nhận được.
>
> ⚠️ **Số liệu Phase 0 đã đảo thứ tự ưu tiên**: nguyên nhân A/C (429/5xx) **chưa
> hề xảy ra** trên thực tế (0 lỗi 429/5xx trong toàn bộ log Nginx) — Phase 1 giờ
> là lớp phòng ngừa, không phải chữa cháy. Thủ phạm thật đang cắn là **D
> (thiết bị bị revoked)** và **E (fingerprint drift)**. Xem mục 7.

## 1. Tóm tắt

Không phải một lỗi, mà **năm lỗi độc lập** cùng dẫn tới một triệu chứng. Xếp theo
mức độ gây thiệt hại:

| # | Nguyên nhân | Ai dính | Mất mã? | Ưu tiên |
|---|---|---|---|---|
| A | Lỗi tạm thời (429/502/500) bị client hiểu là "license giả" → xoá sạch cache | Mọi máy, hàng loạt cùng lúc | ✅ Mất | **P0** |
| B | Hết grace 7 ngày là đá ra, không thèm gia hạn dù đang có mạng | Máy mạng yếu / nghỉ vài hôm | ❌ Giữ | **P0** |
| C | Rate-limit tính chung một "xô" cho toàn bộ khách hàng → sinh ra 429 ở mục A | Cả hệ thống | — | **P0** |
| D | "Reset máy" của admin khoá vĩnh viễn chính máy đó | Máy đã gọi hỗ trợ | ✅ Mất | P1 |
| E | Fingerprint tự đổi (MAC/tên máy) → coi như máy khác | Laptop, máy có VPN/Wi-Fi | ✅ Mất | P1 |
| F | Đồng hồ máy chạy nhanh → hết grace sớm | Máy hỏng pin CMOS | ❌ Giữ | P2 |

**Nguyên tắc xuyên suốt bản vá:** *không bao giờ xoá license vì một lỗi mà client
không chắc chắn.* Chỉ xoá khi server **nói rõ ràng** rằng máy này không còn quyền
(`revoked` / `expired` / `not_activated` kèm HTTP 401/403). Mọi thứ khác — mất
mạng, 429, 502, JSON hỏng, token quá hạn — đều phải là "thử lại sau".

## 2. Chi tiết từng nguyên nhân

### A. Client xoá cache khi gặp lỗi mơ hồ  🔴 P0

`core/licensing/client.py:231-234`

```python
result_status = body.get("status", "invalid")   # ← body không có "status" ⇒ "invalid"
if result_status in _TERMINAL_STATUSES:          # "invalid" nằm trong tập này
    clear_license_cache()                        # ← xoá cả license_code
```

Những response **không** có field `status`:

- **429** từ slowapi → `{"error": "Rate limit exceeded: 60 per 1 minute"}`
- **502/503/504** từ Nginx (lúc `docker compose up -d`, restart, OOM) → HTML → parse JSON fail → `{}`
- **500** do DB hiccup → `{"detail": "Internal Server Error"}`
- **401** token quá hạn → có `status="invalid"` → cũng bị xoá (xem mục B)

Mỗi lần deploy server = một cửa sổ 502 vài giây; mọi máy đang check-in trong cửa
sổ đó **mất license vĩnh viễn**. Đây là lời giải thích khớp nhất cho *"nhiều máy"*
cùng bị.

### B. Hết grace là đá ra, không tự gia hạn  🔴 P0

Token có `exp = now + GRACE_DAYS` = **7 ngày** (`server/app/security.py:100`).
Client làm mới token mỗi 6 giờ **chỉ khi app đang mở** (`main.py:198`).

Luồng khởi động hiện tại:

| Bước | Kết quả |
|---|---|
| `startup_reconcile()` (`client.py:250`) | `verified_claims()` **không kiểm `exp`** → token quá hạn vẫn "hợp lệ" → **return sớm, không check-in** |
| `needs_activation()` (`core/activation.py:95`) | `is_activated()`=True, `is_expired()`=True → **True** |
| → | `ActivationDialog(is_expired=True)` |

Máy offline/không mở app 7 ngày sẽ bị đá ra **kể cả khi mạng đang tốt và license
còn 300+ ngày**. App không hề thử xin token mới.

Và khi có mạng trở lại thì còn tệ hơn: client gửi token cũ lên, router dùng
`jwt.decode()` mặc định (bắt buộc `exp` còn hạn) → **401 `status="invalid"`** →
client xoá sạch cache (mục A). `server/app/routers/activation.py:63-69` có sẵn
`payload.code` trong tay nhưng không fallback — đúng tình huống cần cấp token mới
thì lại từ chối.

### C. Rate-limit dùng chung một "xô" cho toàn bộ máy  🔴 P0

`server/app/main.py` không gắn `ProxyHeadersMiddleware`; gunicorn/uvicorn mặc
định chỉ tin `X-Forwarded-For` đến từ `127.0.0.1`
(`.venv/.../uvicorn/config.py:334`). Trong Docker, peer là gateway bridge
(`172.x.0.1`) chứ không phải loopback → `get_remote_address()` trả **cùng một IP
cho mọi khách hàng**.

Hệ quả: `RATE_LIMIT_VERIFY=60/minute` là hạn mức **chung cho cả hệ thống**, không
phải mỗi máy. Các quán mở cửa cùng khung giờ tối → hàng chục máy khởi động trong
một phút → 429 → mục A xoá license hàng loạt. `RATE_LIMIT_ACTIVATE=20/minute` cũng
chung, nên đợt khách đồng loạt nhập lại mã sẽ tự chặn nhau, hiện *"Mã không hợp lệ"*.

### D. "Reset máy" khoá vĩnh viễn chính máy đó  🟠 P1

`server/app/routers/admin.py:208-215` reset bằng `d.revoked = True`, **không xoá
row**. Khi máy đó kích hoạt lại:

```python
device = next((d for d in lic.devices if d.fingerprint == fingerprint), None)  # licensing.py:88
...
if device.revoked:
    raise LicenseError("Thiết bị này đã bị thu hồi quyền.", status="revoked", http_status=403)
```

→ 403 `revoked` → client xoá cache → máy **không bao giờ kích hoạt lại được**. Mà
đây lại đúng là thao tác được hướng dẫn khi khách báo *"đã đạt giới hạn thiết bị"*
(`licensing.py:92-96`).

### E. Fingerprint không ổn định  🟠 P1

`core/licensing/device.py:48-53` băm 4 thành phần, 3 trong đó không ổn định:

| Thành phần | Rủi ro |
|---|---|
| `uuid.getnode()` | Máy nhiều NIC (Wi-Fi + LAN + Bluetooth PAN + VPN/VirtualBox/Hyper-V) → Python chọn MAC khác nhau giữa các lần chạy. Cắm/rút USB Wi-Fi, dock, bật VPN là đổi. Windows 11 bật "địa chỉ phần cứng ngẫu nhiên" cho Wi-Fi cũng đổi. **Không lấy được MAC nào thì trả số ngẫu nhiên mỗi lần chạy.** |
| `platform.node()` | Đổi tên máy / join domain là đổi |
| `PROCESSOR_IDENTIFIER` | Ổn định |
| `MachineGuid` | Ổn định, chỉ đổi khi cài lại Windows — **đủ dùng một mình** |

Fingerprint đổi → `verified_claims()` thấy `fp` lệch → `None` → coi như chưa kích
hoạt → đá ra. Nhập lại mã thì server thấy máy mới, mà `max_devices` mặc định = **1**
(`server/app/models.py:45`) → *"Mã đã đạt giới hạn 1 thiết bị"* → gọi hỗ trợ → dính
tiếp mục D.

### F. Đồng hồ máy chạy nhanh  🟡 P2

`is_grace_valid()` (`client.py:313`) so `time.time()` với `exp`. PC hết pin CMOS
nhảy sai giờ về tương lai là hết grace tức thì.

## 3. Kế hoạch triển khai

Thứ tự bắt buộc: **server trước, client sau**. Lý do: các máy đang chạy ngoài thị
trường vẫn mang client cũ (xoá cache khi thấy body lạ), nên phải sửa server để
**cầm máu ngay** cho đội hình hiện tại, rồi mới thay client.

```
Phase 0  Chẩn đoán           (30 phút, không đổi code)
Phase 1  Server cầm máu      ← P0, deploy ngay, có lợi cho cả client cũ
Phase 2  Server: reset máy   ← P1
Phase 3  Client: không xoá bừa + tự gia hạn   ← P0, phát hành 1.6.3
Phase 4  Fingerprint v2      ← P1, cần server + client đi cùng nhau
Phase 5  Dọn dẹp + phòng thủ ← P2
```

---

### Phase 0 — Chẩn đoán (làm trước, để biết cái nào đang cắn mạnh nhất)

Không sửa code. Mục tiêu: có số liệu để biết vá xong đã hết chưa.

**Trên VPS:**

```bash
cd /opt/qls/server

# E: một máy đăng ký nhiều fingerprint?
docker compose exec db psql -U qls -d qls -c \
 "SELECT license_id, hostname, count(*) n, min(first_seen)::date, max(first_seen)::date
    FROM devices GROUP BY 1,2 HAVING count(*)>1 ORDER BY n DESC LIMIT 20;"

# D: bao nhiêu máy đang bị revoked (tức đang kẹt)?
docker compose exec db psql -U qls -d qls -c \
 "SELECT count(*) FROM devices WHERE revoked;"

# B: bao nhiêu máy quá 7 ngày không check-in (sắp/đang bị đá)?
docker compose exec db psql -U qls -d qls -c \
 "SELECT hostname, app_version, last_check_in::date FROM devices
   WHERE NOT revoked AND last_check_in < now() - interval '7 days'
   ORDER BY last_check_in LIMIT 30;"

# A+C: có 429/5xx trả về client không?
awk '$9 ~ /^(429|50[0-9])$/ {print $9}' /var/log/nginx/access.log | sort | uniq -c
grep -c 'api/v1/license/verify' /var/log/nginx/access.log
```

**Trên một máy khách bị đá** — lấy `%APPDATA%\QuangLuuStudio\logs\`:

| Dòng log | Kết luận |
|---|---|
| `License token thuộc về máy khác` | → **E** fingerprint drift |
| `License không còn hiệu lực (invalid) — xoá cache` | → **A** (429/5xx/token quá hạn) |
| `Không kết nối được máy chủ` rồi im lặng nhiều ngày | → **B** hết grace |
| `Chữ ký license token không hợp lệ` | → sai public key (khác hẳn, xem `LICENSING_HARDENING.md`) |

**Đầu ra:** ghi số liệu vào chính file này, mục "Kết quả đo" ở cuối.

---

### Phase 1 — Server cầm máu ngay  🔴 P0  ✅ ĐÃ CODE, CHỜ DEPLOY

Mục tiêu: **client cũ đang chạy ngoài kia không còn cớ để xoá license.** Mọi lỗi
tạm thời phải trả JSON có field `status` **không nằm trong** tập
`{revoked, expired, not_activated, invalid}`.

> Đã sửa: `server/Dockerfile`, `server/app/main.py`, `server/app/config.py`,
> `server/app/security.py`, `server/app/routers/activation.py`,
> `server/deploy/nginx.conf`, `server/.env.example`.
> Test mới: `server/tests/test_kickout_hotfix.py` (10 test) — toàn bộ 48 test xanh.

#### 1.1 Rate-limit theo IP thật

`server/Dockerfile:18` — thêm cờ vào gunicorn:

```dockerfile
CMD ["sh", "-c", "python -m app.cli init-db && gunicorn app.main:app \
     -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:8000 \
     --forwarded-allow-ips='*'"]
```

An toàn vì cổng 8000 chỉ publish trên `127.0.0.1` (`docker-compose.yml:30`) — chỉ
Nginx tới được, không ai bơm `X-Forwarded-For` giả từ ngoài.

Kèm nới hạn mức trong `.env` (giờ mới đúng nghĩa "mỗi IP"):

```ini
RATE_LIMIT_VERIFY=120/minute      # 1 máy check-in 4 lần/ngày; 120 dư cho quán nhiều máy sau NAT
RATE_LIMIT_ACTIVATE=30/minute
```

#### 1.2 Mọi lỗi tạm thời phải có `status` an toàn

`server/app/main.py` — thay handler mặc định của slowapi + thêm handler 5xx:

```python
from fastapi.responses import JSONResponse

def _soft_error(status: str, message: str, http: int):
    # Client đọc field "status"; giá trị ngoài tập terminal ⇒ client giữ nguyên cache.
    return JSONResponse(status_code=http,
                        content={"valid": False, "status": status, "message": message})

@app.exception_handler(RateLimitExceeded)
async def _ratelimit(request, exc):
    return _soft_error("rate_limited", "Máy chủ đang bận, thử lại sau.", 429)

@app.exception_handler(Exception)
async def _unhandled(request, exc):
    log.exception("Unhandled error on %s", request.url.path)
    return _soft_error("server_error", "Máy chủ gặp sự cố tạm thời.", 500)
```

> ⚠️ Bỏ dòng `app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)`
> ở `main.py:24` khi thêm handler mới.

#### 1.3 Nginx trả JSON thay vì HTML khi upstream chết

`server/deploy/nginx.conf` — trong `location /`:

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    ...
    proxy_intercept_errors on;
    error_page 502 503 504 = @upstream_down;
}

location @upstream_down {
    default_type application/json;
    return 503 '{"valid":false,"status":"server_error","message":"Máy chủ đang bảo trì."}';
}
```

Đây là mảnh vá quan trọng nhất cho **đội hình client cũ**: cửa sổ deploy không còn
giết license nữa.

#### 1.4 Chấp nhận token quá hạn khi check-in

`server/app/security.py` — cho phép bỏ kiểm `exp`:

```python
def decode_license_token(token: str, verify_exp: bool = True) -> dict | None:
    try:
        return jwt.decode(token, _public_key(), algorithms=[_ALGO],
                          options={"verify_exp": verify_exp})
    ...
```

`server/app/routers/activation.py:63-69`:

```python
if payload.token:
    # Token quá hạn CHÍNH LÀ lúc client cần token mới — chỉ dùng nó để biết
    # "mã nào, máy nào"; hiệu lực thật do DB quyết. fp vẫn phải khớp.
    decoded = decode_license_token(payload.token, verify_exp=False)
    if decoded is None:
        code = payload.code            # ← fallback thay vì 401
    elif decoded.get("fp") != payload.device_fingerprint:
        return _error(LicenseError("Token không khớp thiết bị.", status="invalid", http_status=403))
    else:
        code = decoded.get("code")
```

Không nới lỏng bảo mật: kẻ trộm token vẫn phải có đúng fingerprint máy, và device
phải còn trong DB và chưa revoked.

#### 1.5 Nới grace

`.env` trên VPS + `server/.env.example:33` + `server/app/config.py:44`:

```ini
GRACE_DAYS=30
```

7 ngày là quá ngắn cho máy hát ở quán dùng 4G chập chờn. 30 ngày giảm tần suất
dính mục B xuống 1/4, và không hạ thấp khả năng thu hồi (thu hồi vẫn có hiệu lực
ngay ở lần check-in kế tiếp — client xoá cache tức thì).

**Kiểm thử Phase 1** (`server/tests/`):

- `test_verify_accepts_expired_token` — token `exp` đã qua + device hợp lệ → 200 + token mới.
- `test_verify_falls_back_to_code_when_token_garbage` — token rác + code đúng → 200.
- `test_verify_rejects_token_of_other_device` — vẫn 403.
- `test_ratelimit_returns_soft_status` — vượt hạn mức → 429 body có `status == "rate_limited"`.
- `test_unhandled_error_returns_soft_status` — route ném lỗi → 500 body có `status == "server_error"`.

**Nghiệm thu:** với client **1.6.2 cũ không đổi gì**, restart server giữa lúc máy
đang check-in → máy vẫn giữ license.

#### Runbook deploy Phase 1

```bash
cd /opt/qls/server

# 1. Sao lưu (bắt buộc)
B=backups/$(date +%Y%m%d-%H%M%S) && mkdir -p $B
cp .env docker-compose.yml $B/
docker compose exec -T db pg_dump -U qls qls > $B/db.sql
tar czf $B/app-truoc.tar.gz app deploy Dockerfile
echo "Backup: $B"

# 2. Đo trước khi sửa (Phase 0)
git pull                       # lấy code mới
bash deploy/diagnose_kickout.sh | tee $B/diagnose-truoc.txt

# 3. .env — config.py chỉ đổi giá trị MẶC ĐỊNH; .env đang có GRACE_DAYS=7 sẽ đè lên.
sed -i 's/^GRACE_DAYS=.*/GRACE_DAYS=30/' .env
grep -q '^RATE_LIMIT_VERIFY=' .env   || echo 'RATE_LIMIT_VERIFY=120/minute' >> .env
grep -q '^RATE_LIMIT_ACTIVATE=' .env || echo 'RATE_LIMIT_ACTIVATE=30/minute' >> .env
grep -E '^(GRACE_DAYS|RATE_LIMIT)' .env

# 4. Build + khởi động lại API
docker compose up -d --build api
sleep 5 && curl -fsS https://qlstudio.duckdns.org/healthz && echo

# 5. Xác nhận cờ proxy đã có hiệu lực
docker compose exec api sh -c 'ps ax | grep -o -- "--forwarded-allow-ips[^ ]*"'
```

**Nginx** — file trên VPS (`/etc/nginx/sites-available/qls`) đã bị certbot sửa
(thêm block 443), **đừng chép đè** `deploy/nginx.conf`. Thêm tay 4 dòng vào
**block `server` đang nghe 443**:

```nginx
proxy_intercept_errors on;
error_page 502 503 504 = @upstream_down;
location @upstream_down {
    default_type application/json;
    return 503 '{"valid":false,"status":"server_error","message":"May chu dang bao tri, thu lai sau."}';
}
```

```bash
nginx -t && systemctl reload nginx
# Thử thật: tắt API rồi gọi API — phải ra JSON, không phải HTML
docker compose stop api
curl -s -o /dev/null -w '%{http_code} ' https://qlstudio.duckdns.org/api/v1/license/verify
curl -s -X POST https://qlstudio.duckdns.org/api/v1/license/verify   # ← phải thấy "status":"server_error"
docker compose start api
```

**Kiểm tra cuối (quan trọng nhất — mô phỏng đúng máy đang bị đá):**

```bash
# Máy thật đã kích hoạt, token quá hạn grace → phải nhận token mới, KHÔNG 401.
curl -s -X POST https://qlstudio.duckdns.org/api/v1/license/verify \
  -H 'Content-Type: application/json' \
  -d '{"code":"<MÃ THẬT>","device_fingerprint":"<FP THẬT TỪ BẢNG devices>"}' | head -c 300
```

---

### Phase 2 — "Reset máy" phải thật sự reset  🟠 P1  ✅ ĐÃ DEPLOY

> Đã sửa: `admin.py` (reset-devices xoá bản ghi + endpoint `POST
> /admin/devices/{id}/delete`), `templates/licenses.html` (danh sách máy kèm nút
> **Gỡ** và nhãn "đã chặn"), `services/licensing.py` (thông báo lỗi kèm mã máy 8
> ký tự để hỗ trợ tra). Test mới: 5 test, tổng **53/53 xanh**.
> Kiểm chứng trên production: trang admin render 200, 67 nút Gỡ, 21 nhãn "đã
> chặn" khớp đúng số liệu DB; hai route mới trả 405 với GET (đã đăng ký cho POST).
> **Không** chạy smoke-test làm thay đổi dữ liệu khách.

`server/app/routers/admin.py:208-215`:

```python
@router.post("/licenses/{lic_id}/reset-devices")
def reset_devices(lic_id, ...):
    lic = db.get(License, lic_id)
    if lic:
        for d in list(lic.devices):
            db.delete(d)          # ← xoá hẳn, không phải revoked=True
        db.commit()
    return _redirect("/admin/licenses")
```

Giữ nguyên ngữ nghĩa `revoked` cho việc **cấm một máy cụ thể** (hiện chưa có nút
riêng — xem 2.2).

**2.2** Thêm ở `app/templates/licenses.html` (cạnh nút "Reset máy"): danh sách
device kèm nút *"Xoá máy này"* → `POST /admin/devices/{id}/delete`, để hỗ trợ khách
mà không phải reset cả mã.

**2.3** Trong `licensing.activate()`, khi device tồn tại nhưng `revoked`, thông báo
hiện tại quá cụt. Đổi message thành *"Thiết bị này đã bị chặn. Liên hệ hỗ trợ và
đọc mã máy: `<8 ký tự đầu fingerprint>`"* để hỗ trợ tra được đúng row.

**Kiểm thử:** `test_reset_devices_allows_reactivation` — activate → reset → activate
lại cùng fingerprint → 200.

**Việc thủ công kèm theo — ĐÃ QUYẾT ĐỊNH BỎ QUA (2026-08-12).** 11 bản ghi
revoked thuộc license còn hiệu lực được **giữ nguyên** theo yêu cầu: không thể
phân biệt bằng dữ liệu đâu là bấm nhầm "Reset máy", đâu là cấm có chủ đích.

Hệ quả cần biết:

- `XN52-EV80-QW22-SE66-C455` (license **active**, cả 2 máy đều revoked) vẫn
  **không dùng được** cho tới khi có người gỡ tay.
- 5 license còn lại (`CE37…`, `GR96…`, `NA46…`, `UD71…`, `YA96…`) đang chạy bằng
  1 máy sống, nhưng nếu `uuid.getnode()` nhảy về đúng fingerprint cũ đã bị
  revoked thì khách bị khoá đột ngột. Phase 4 mới trị dứt.

Cách xử lý khi khách gọi: vào `/admin/licenses` → cột **Thiết bị** → *chi tiết*
→ bấm **Gỡ** đúng dòng có nhãn "đã chặn". Không cần SQL, không cần reset cả mã.

```bash
# Nếu về sau muốn dọn hàng loạt (chỉ license CÒN hiệu lực, không đụng mã bị cấm):
docker compose exec db psql -U qls -d qls -c \
 "DELETE FROM devices d USING licenses l
   WHERE d.license_id = l.id AND d.revoked AND l.status = 'active';"
```

---

### Phase 3 — Client: không xoá bừa + tự gia hạn  🔴 P0  ✅ CODE XONG, CHỜ PHÁT HÀNH

Phát hành **1.6.3** trên nhánh `fix/licensing-kickout` tách từ tag `1.6.2`
(`202f84b`) — **không** đi kèm phần kiosk đang dở trên `main`.

> Làm trong git worktree riêng: `D:\Projects\LiveStudio\qls-hotfix-1.6.3`.
> Đã sửa: `core/licensing/client.py`, `core/licensing/__init__.py`,
> `core/activation.py`, `main.py`, `frontend_qt.py`, `core/version.py` (1.6.3).
> Test: `tests/core/test_licensing.py` từ 14 → **29 test**; toàn bộ **388/388 xanh**.
> Smoke-test Qt offscreen: cả ba trạng thái dialog (mặc định / hết hạn thật /
> cần gia hạn) dựng đúng, nút Thử lại chạy được cả nhánh thành công lẫn thất bại.
>
> **Build:** worktree không có `.venv` riêng — kích hoạt venv của thư mục chính
> rồi mới chạy `build_installer.bat` trong worktree:
> ```
> D:\Projects\LiveStudio\quang-luu-studio\.venv\Scripts\activate
> cd /d D:\Projects\LiveStudio\qls-hotfix-1.6.3
> build_installer.bat
> ```

#### 3.1 Chỉ xoá cache khi server nói rõ

`core/licensing/client.py`:

```python
# Chỉ ba trạng thái này nghĩa là "máy này thật sự không còn quyền".
# "invalid" bị loại: nó xuất hiện cả khi token quá hạn hoặc body lỗi lạ.
_TERMINAL_STATUSES = frozenset({"revoked", "expired", "not_activated"})

def verify_online() -> dict:
    ...
    if status == 0:
        return {"success": False, "status": "offline", ...}
    if status == 200 and body.get("valid"):
        ...
    result_status = str(body.get("status") or "")
    # Chỉ 401/403 kèm status rõ ràng mới được phép huỷ quyền. 429/5xx/JSON hỏng
    # ⇒ coi như offline, giữ nguyên cache và thử lại lần sau.
    if status in (401, 403) and result_status in _TERMINAL_STATUSES:
        log.warning("License không còn hiệu lực (%s) — xoá token", result_status)
        clear_license_cache(keep_code=True)
        return {"success": False, "status": result_status, "error": body.get("message", "")}
    log.info("Check-in không thành công (HTTP %s, status=%s) — giữ nguyên cache",
             status, result_status or "?")
    return {"success": False, "status": "offline", "error": body.get("message", "")}
```

#### 3.2 `clear_license_cache(keep_code=True)`

Giữ lại `license_code` khi chỉ mất token. Mã không phải nguồn quyền (token mới là),
nên giữ nó vô hại — mà lợi: `verify_online()` vẫn check-in được bằng code, và
`ActivationDialog` điền sẵn mã cho khách khỏi phải gõ lại.

#### 3.3 Tự gia hạn khi hết grace

`core/licensing/client.py::startup_reconcile()`:

```python
def startup_reconcile() -> None:
    cache = _load()
    if not (cache.get("license_token") or cache.get("license_code")):
        return

    claims = verified_claims()
    if claims is not None and is_grace_valid():
        return                              # token còn hạn, không cần làm gì

    # Hai trường hợp phải thử đổi token: (a) token không xác minh được (bản cũ /
    # fingerprint đổi), (b) token thật nhưng quá hạn grace. Cả hai đều KHÔNG phải
    # lý do để đá người dùng ra trước khi hỏi server một câu.
    result = verify_online()
    if result.get("success") or result.get("status") == "offline":
        return                              # offline: giữ cache, lần sau có mạng sẽ tự khỏi
    clear_license_cache(keep_code=True)      # server đã nói rõ: hết quyền
```

#### 3.4 Vòng check-in nền phải chạy cả khi token đã mất

`main.py:219` — `if _lic.has_online_license():` khiến máy vừa mất token thì thôi
không thử lại nữa trong cả phiên. Đổi thành:

```python
if _lic.has_online_license() or _lic.cached_code():
```

(thêm `cached_code()` vào `client.py`). Và `_LICENSE_LOST_STATUSES` ở `main.py:199`
phải đồng bộ với `_TERMINAL_STATUSES` mới (**bỏ `"invalid"`**), nếu không dialog
"Giấy phép không còn hiệu lực" sẽ nhảy ra mỗi lần mạng lỗi.

Thêm: khi check-in thất bại vì offline, **rút ngắn nhịp thử lại** (30 phút thay vì
6 giờ) cho tới khi thành công — máy mạng chập chờn sẽ bắt được cửa sổ có mạng.

#### 3.5 Phân biệt "hết hạn thật" với "cần gia hạn"

`core/activation.py` + `frontend_qt.py::ActivationDialog`:

- Thêm `ActivationManager.needs_renewal()` = có token đúng chữ ký, `lexp` còn hạn,
  nhưng grace đã hết.
- `main.py` truyền trạng thái này vào dialog. Nội dung hiển thị:

  > 🌐 **Cần kết nối internet để gia hạn giấy phép**
  > Giấy phép của bạn vẫn còn hiệu lực đến `<ngày>`, nhưng app đã `<N>` ngày chưa
  > kết nối được máy chủ. Kiểm tra mạng rồi bấm **Thử lại**.

- Thêm nút **"Thử lại"** gọi `verify_online()` → thành công thì `accept()` luôn,
  khách không phải gõ mã.
- Ô nhập mã điền sẵn `license_code` còn trong cache.

Đây là phần khách nhìn thấy trực tiếp: khác biệt giữa *"phần mềm này lởm, tự nhiên
đòi mã"* và *"à, mất mạng"*.

**Kiểm thử Phase 3** (`tests/core/test_licensing.py`):

| Test | Kỳ vọng |
|---|---|
| `test_verify_429_keeps_cache` | HTTP 429 → cache còn nguyên, status `offline` |
| `test_verify_502_html_keeps_cache` | body không phải JSON → cache còn nguyên |
| `test_verify_500_keeps_cache` | `{"detail": ...}` → cache còn nguyên |
| `test_verify_revoked_clears_token_keeps_code` | 403 `revoked` → mất token, còn `license_code` |
| `test_reconcile_renews_expired_grace` | token quá grace + server OK → token mới, không đá ra |
| `test_reconcile_offline_keeps_cache` | token quá grace + mạng chết → cache còn nguyên |
| `test_needs_renewal_vs_expired` | `lexp` còn hạn → `needs_renewal()` True, `is_expired()` không hiện thông báo "hết hạn" |

---

### Phase 4 — Fingerprint v2 (ổn định)  🟠 P1  ✅ SERVER ĐÃ DEPLOY, CLIENT CHỜ PHÁT HÀNH

> Server đã sửa: `schemas.py` (thêm `legacy_fingerprint` cho activate/verify/trial),
> `services/licensing.py` (`find_device()` + `_find_trial_grant()` di trú tại chỗ),
> `routers/activation.py` (`_fp_matches()` chấp nhận token mang fp cũ).
> Client (worktree): `core/licensing/device.py` (v2 = chỉ MachineGuid +
> `legacy_fingerprint()`), `core/licensing/client.py` (gửi kèm `_legacy_fp()`).
> Test mới: 8 server + 6 client.
>
> Kiểm chứng trên production (không đụng dữ liệu khách): request kèm
> `legacy_fingerprint` được chấp nhận (400 vì mã bịa, **không** 422); request
> kiểu client cũ chạy y như trước; token thiếu claim `fp` bị chặn 401.

**Đây là thay đổi dễ gây sự cố diện rộng nhất: làm sai là đá toàn bộ đội hình ra
cùng lúc.** Ba cái bẫy đã xử lý, cả ba đều có test riêng:

1. **Token đang cache mang `fp` cũ.** Router phải chấp nhận cả hai giá trị, nếu
   không thì chính bản cập nhật gây ra đúng sự cố đang chữa
   (`test_verify_accepts_token_bound_to_legacy_fp`).
2. **Suất dùng thử.** Bỏ sót di trú `TrialGrant` = mọi máy được tặng thêm 3 ngày
   (`test_trial_not_reissued_after_migration`); gộp hai bản ghi thì giữ mốc sớm
   nhất (`test_trial_migration_keeps_earliest_start`).
3. **Lệnh cấm phải đi theo máy.** Bản ghi đang `revoked` KHÔNG được di trú, nếu
   không ai bị cấm chỉ cần cập nhật app là né được
   (`test_ban_follows_the_machine_across_migration`).

Ngoài ra token có claim `fp` rỗng luôn bị từ chối — lỗ hổng dễ mắc khi nới điều
kiện so khớp (`test_token_without_fp_claim_rejected`).

#### 4.4 Cứu client CŨ ngay, không chờ 1.6.3 (deploy 2026-08-13)

Vấn đề: 66 máy ngoài thị trường đều là ≤1.6.2, không biết gửi `legacy_fingerprint`.
Chúng vẫn drift và vẫn bị đá ra trong lúc chờ bản vá.

Giải pháp: coi **claim `fp` trong token** là một danh tính cũ hợp lệ. Token do
server ký, nên nó là bằng chứng có chữ ký rằng máy này từng được cấp phép dưới
danh tính đó — và client cũ vẫn gửi token lên mỗi lần check-in.

| Loại client | Nguồn danh tính cũ | Quy tắc |
|---|---|---|
| ≤1.6.2 (không gửi `legacy_fingerprint`) | claim `fp` trong token | Lỏng — token lệch fingerprint ⇒ hiểu là máy vừa drift, nối lại |
| ≥1.6.3 (có gửi `legacy_fingerprint`) | giá trị client **tính lại từ phần cứng** | Chặt — token phải khớp máy này hoặc đúng danh tính cũ |

**Đánh đổi có chủ đích:** với client cũ, ai chép `activation.json` sang máy khác
thì chuyển được giấy phép sang đó (trước đây chép file vô dụng vì fingerprint
không khớp). Chấp nhận vì: (a) thiệt hại thật đang đo được là 23 lần lỗi 409 +
21 thiết bị bị chặn, còn cách lách này chưa ai dùng; (b) nhánh lỏng **tự vô hiệu
theo từng máy** ngay khi máy đó lên 1.6.3, vì `legacy_fingerprint` được tính
sống từ phần cứng nên chép file không giả được.

**Việc phải làm sau:** khi `/admin/devices` không còn bản ≤1.6.2, xoá nhánh lỏng
trong `_legacy_identities()` (chỉ giữ `payload.legacy_fingerprint`) và sửa lại
`test_verify_token_migrates_for_old_clients`.

#### 4.1 Client sinh fingerprint v2

`core/licensing/device.py`:

```python
def get_fingerprint() -> str:
    """v2: chỉ dựa trên MachineGuid — thứ duy nhất ổn định qua đổi NIC/VPN/tên máy.
    Chỉ khi không đọc được MachineGuid mới rơi về công thức cũ."""
    guid = _machine_guid()
    if guid:
        return sha256(f"v2|{guid}")
    return legacy_fingerprint()      # công thức 4 thành phần như cũ

def legacy_fingerprint() -> str:
    """Công thức v1 — chỉ còn dùng để server nhận diện máy cũ khi chuyển đổi."""
```

#### 4.2 Server nhận diện và di trú tại chỗ

`server/app/schemas.py` — thêm `legacy_fingerprint: str | None = None` vào
`ActivateRequest`, `VerifyRequest`, `TrialRequest`.

`server/app/services/licensing.py` — helper dùng chung:

```python
def _find_device(lic, fingerprint, legacy):
    device = next((d for d in lic.devices if d.fingerprint == fingerprint), None)
    if device is None and legacy:
        device = next((d for d in lic.devices if d.fingerprint == legacy), None)
        if device is not None:
            device.fingerprint = fingerprint     # di trú tại chỗ, KHÔNG tốn slot mới
            log.info("Di trú fingerprint v1→v2 cho device %s", device.id)
    return device
```

Áp cho cả `activate()`, `verify()` và `start_trial()` (nếu bỏ sót `start_trial`,
mọi máy sẽ xin được một suất dùng thử mới sau khi cập nhật).

`server/app/routers/activation.py` — nới điều kiện khớp token, **bắt buộc**, nếu
không chính bản cập nhật sẽ đá hết máy ra:

```python
if decoded.get("fp") not in (payload.device_fingerprint, payload.legacy_fingerprint):
    return _error(...)
```

Tương tự cho `server/app/routers/sync.py` (Cloud Sync cũng kiểm device).

#### 4.3 Dọn dẹp

Sau ~3 tháng (khi `devices.fingerprint` không còn row v1 nào): bỏ
`legacy_fingerprint` khỏi schema và client.

**Kiểm thử:** `test_activate_migrates_legacy_fingerprint` (không sinh device mới),
`test_verify_accepts_token_bound_to_legacy_fp`, `test_trial_not_reissued_after_migration`.

**Nghiệm thu:** trên máy thật — kích hoạt bằng 1.6.3, cập nhật lên bản có v2, mở
app → **không** hiện dialog kích hoạt; trong DB `devices` vẫn đúng 1 row, cột
`fingerprint` đã đổi giá trị.

---

### Phase 5 — Phòng thủ & dọn dẹp  🟡 P2

**5.1 Đồng hồ lệch (F).** `is_grace_valid()` nới theo mốc check-in cuối:

```python
grace_ok = now < exp or now < float(cache.get("last_verify_ts", 0)) + _GRACE_FALLBACK_SEC
```

Đánh đổi: `last_verify_ts` sửa tay được → kéo dài offline. Chấp nhận được vì
`plan`/`lexp` vẫn nằm trong token có chữ ký, không giả được.

**5.2 `max_devices` mặc định 1 → 2.** `models.py:45` + `licenses.html:7`. Một máy
hát thường có máy chính + laptop dự phòng; slot thứ hai giảm hẳn số cuộc gọi hỗ trợ.
*(Quyết định kinh doanh — cần bạn duyệt.)*

**5.3 Đo lường.** ✅ **ĐÃ LÀM VÀ DEPLOY** 2026-08-12 — admin UI có bộ lọc theo dõi:

- **Tổng quan** → khối *Sức khoẻ giấy phép*: máy im >7 ngày, đã hết grace (>30
  ngày), thiết bị bị chặn, mã nghi fingerprint đổi, mã đã đủ slot, phiên bản phổ
  biến nhất. Mỗi ô bấm được, dẫn thẳng sang danh sách đã lọc.
- **Thiết bị** (trang mới `/admin/devices`): phân bố phiên bản bấm-để-lọc (theo
  dõi phủ sóng bản vá), lọc theo trạng thái (đang dùng / im lâu / đã chặn), tìm
  theo tên máy / mã máy / mã kích hoạt, nút **Gỡ** ngay trên từng dòng.
- **Mã kích hoạt**: tìm theo mã / tên khách / tên máy, lọc theo trạng thái + gói,
  và 5 cờ chẩn đoán kèm số đếm (`blocked`, `full`, `drift`, `stale`, `unbound`).

Số đếm trên các cờ tính trên tập **chưa lọc cờ**, để bấm vào rồi vẫn theo dõi
được — có test riêng cho điểm này (`test_flag_counts_stay_visible_after_filtering`).

Đối chiếu với SQL của Phase 0 trên chính dữ liệu production: 9 máy im >7 ngày,
21 thiết bị bị chặn, 8 mã nghi drift — **khớp tuyệt đối**. 14 test mới
(`tests/test_admin_filters.py`), tổng **74/74 xanh**.

**5.4 Nhật ký client dễ đọc.** Mỗi lần check-in ghi một dòng gọn:
`license check-in: http=200 status=active grace_left=29.4d` — để hỗ trợ chỉ cần
xin một dòng log là biết chuyện gì.

## 4. Thứ tự phát hành

| Bước | Nội dung | Rủi ro | Ghi chú |
|---|---|---|---|
| 1 | Phase 0 đo đạc | — | Không đổi code |
| 2 | Phase 1 + 2 lên VPS | Thấp | Có lợi ngay cho client 1.6.2 đang chạy |
| 3 | Theo dõi 48h | — | 429/5xx về 0; số máy revoked không tăng |
| 4 | Phase 3 → build **1.6.3**, phát hành | Trung bình | Nhánh `fix/licensing-kickout` từ tag 1.6.2 |
| 5 | Theo dõi 1 tuần | — | Cần ≥80% máy lên 1.6.3 (xem `devices.app_version`) |
| 6 | Phase 4 server → rồi client **1.6.4** | **Cao** | Server phải lên trước |
| 7 | Phase 5 | Thấp | Gộp vào 1.7.0 cùng kiosk |

**Sao lưu trước mỗi lần đụng server** (theo đúng `docs/LICENSING_HARDENING.md`):

```bash
cd /opt/qls/server && B=backups/$(date +%Y%m%d-%H%M%S) && mkdir -p $B
cp .env docker-compose.yml $B/
docker compose exec -T db pg_dump -U qls qls > $B/db.sql
tar czf $B/app-truoc.tar.gz app deploy Dockerfile
```

**Rollback:** `git revert` phần server + `docker compose up -d --build`; client thì
đẩy lại installer bản trước lên GitHub Releases. Không có migration DB phá huỷ nào
trong Phase 1-3 (Phase 4 chỉ **ghi đè** cột `fingerprint`, có thể sống chung với
client cũ vì server vẫn nhận cả hai giá trị).

## 5. Runbook hỗ trợ khách đang kẹt (dùng được ngay hôm nay)

**Khách báo "Bản quyền đã hết hạn" nhưng mã còn hạn:**
1. Hỏi mã kích hoạt → tra `/admin/licenses`, xác nhận `expires_at` còn xa.
2. Bảo khách nhập lại đúng mã cũ. Nếu vào được → là mục A hoặc B, không cần làm gì thêm.

**Khách báo "Mã đã đạt giới hạn N thiết bị":**
```sql
SELECT id, substr(fingerprint,1,12), hostname, first_seen, last_seen
  FROM devices WHERE license_id = (SELECT id FROM licenses WHERE code='XXXX-...');
```
Có nhiều row cùng `hostname` → fingerprint drift. **Xoá các row cũ** (`DELETE FROM
devices WHERE id IN (...)`), **đừng bấm "Reset máy"** cho tới khi Phase 2 lên.

**Khách báo "Thiết bị này đã bị thu hồi quyền":** đã dính mục D →
`DELETE FROM devices WHERE id = <id>;` rồi cho khách nhập lại mã.

## 6. Nghiệm thu tổng thể

- [ ] Restart server giữa giờ cao điểm → không máy nào mất license (kiểm bằng log client).
- [ ] Máy rút mạng 10 ngày rồi cắm lại → tự gia hạn, **không** hiện dialog kích hoạt.
- [ ] Máy rút mạng 40 ngày (quá grace mới) → hiện dialog **"cần kết nối internet"**, bấm *Thử lại* là vào, không phải gõ mã.
- [ ] Thu hồi mã ở admin → máy mất Premium trong ≤6 giờ (không được yếu đi so với hiện tại).
- [ ] Đổi tên máy + bật VPN + rút Wi-Fi USB → vẫn nhận đúng máy cũ (sau Phase 4).
- [ ] Bấm "Reset máy" → máy đó kích hoạt lại được.
- [ ] Số ticket "bị đá ra" trong 30 ngày = 0.

## 7. Kết quả đo

### Baseline — 2026-08-12 22:00 (trước Phase 1)

Quy mô: **55 license, 66 thiết bị**.

| Chỉ số | Giá trị | Đọc là |
|---|---|---|
| HTTP 200 trên endpoint license | 994 | — |
| **HTTP 403** | **156** | 🔴 thiết bị bị thu hồi / chưa ràng — **thủ phạm chính** |
| **HTTP 409** | **23** | 🔴 "đã đạt giới hạn thiết bị" — hệ quả của drift |
| HTTP 401 | 13 | token quá hạn bị từ chối (đã sửa ở Phase 1) |
| **429 / 5xx** | **0** | ✅ nguyên nhân A/C **chưa từng xảy ra** |
| IP khác nhau gọi verify | 106 | rate-limit chung xô nhưng chưa chạm trần |
| Thiết bị đang revoked | **21 / 66 (32%)** | 🔴 nguyên nhân D |
| Bản ghi thừa do fingerprint drift | **12** | 🔴 nguyên nhân E |
| Máy > 7 ngày không check-in | 9 (đều v1.6.1) | nguyên nhân B |
| Máy > 30 ngày không check-in | 0 | grace 30 ngày phủ hết đội hình hiện tại |

**Diễn giải.** Giả thuyết ban đầu (429/5xx xoá license) **sai với thực tế hiện
tại** — chưa có cú 429/5xx nào. Nhưng 156 lần 403 + 21/66 thiết bị revoked thì
không thể là ngẫu nhiên: đó là vòng lặp **drift → đủ giới hạn máy (409) → admin
bấm "Reset máy" → máy cũ bị revoked vĩnh viễn (403)**.

Nguy hiểm nhất: `uuid.getnode()` có thể **nhảy qua lại** giữa hai NIC. Máy từng
bị revoked ở fingerprint A, kích hoạt lại thành B; tuần sau nhảy về A → *"Thiết
bị này đã bị thu hồi quyền"* → client xoá cache → đá ra. Lặp vô hạn. Đây chính
là *"dùng vài ngày lại bị đá ra"* mà khách mô tả.

Phân bố thiết bị revoked theo license:

| Nhóm | Số license | Xử lý |
|---|---|---|
| License `revoked` (cấm có chủ đích) | 8 | ✅ đúng, giữ nguyên |
| License **`active`** nhưng **mọi** máy đều revoked → khách **mất quyền dùng dù còn hạn** | **1** (`XN52-…-C455`) | 🔴 gỡ ngay |
| License `active`, còn 1 máy sống, sót lại bản ghi revoked | 5 | ⚠️ bom hẹn giờ khi fingerprint nhảy lại |

### Sau Phase 1 — 2026-08-12 22:05

| Hạng mục | Kiểm chứng trực tiếp trên production |
|---|---|
| Nginx trả JSON khi API chết | ✅ tắt API → `503 {"status":"server_error"}` (trước là HTML) |
| `--forwarded-allow-ips` | ✅ có trong CMD container đang chạy |
| `grace_days` / rate-limit | ✅ app đọc được `30`, `120/minute`, `30/minute` |
| Token **quá hạn 3 ngày** của máy thật | ✅ 200 + token mới, grace mới đúng 30 ngày (trước: 401 + xoá license) |
| Token quá hạn dùng ở máy khác | ✅ vẫn 403 "Token không khớp thiết bị" |
| Thu hồi vẫn có hiệu lực | ✅ 403 `revoked` đi thẳng ra client |

Backup: `/opt/qls/server/backups/20260812-220111/` (`.env`, `db.sql` 1.5 MB,
`docker-compose.yml`, `Dockerfile`, `app-truoc.tar.gz`).
Nginx cũ: `/etc/nginx/sites-available/qls.bak-20260812-*`.

---

## 8. Phát hành v1.6.3 — 2026-08-14

Nhánh `fix/licensing-kickout` (2 commit: `e3f9e91` code + `6303a03` đồng bộ
installer), tag `v1.6.3`, đã push. Release:
<https://github.com/ligktit/quang-luu-studio/releases/tag/v1.6.3>

| Asset | Kích thước | SHA-256 (đầu) |
|---|---|---|
| `Setup_QuangLuuStudio_v1.6.3.exe` (Nhẹ) | 417.764.396 | `b01c710e…` |
| `Setup_QuangLuuStudio_Heavy_v1.6.3.exe` (Nặng) | 500.692.956 | `3b19e875…` |
| `SHA256SUMS.txt` | 202 | — |

Thông báo cho khách (nguyên văn trong release notes):
**"Fix lỗi ứng dụng yêu cầu kích hoạt lại khi mã kích hoạt còn hiệu lực."**

Kiểm chứng sau khi phát hành: chạy `check_latest_release()` từ mã 1.6.3 → nhận
đúng `v1.6.3`, chọn đúng asset theo biến thể máy, đọc được SHA-256 khớp
`SHA256SUMS.txt`, `is_newer('1.6.3','1.6.2') == True`.

### Bẫy khi build từ worktree (ghi lại cho lần sau)

`git worktree` **không** mang theo file bị `.gitignore`, mà installer lại cần
đúng những thứ đó. Thiếu chúng thì build vẫn **thành công** — spec lọc bỏ data
không tồn tại, `.iss` khai báo `skipifsourcedoesntexist` — nên lỗi chỉ lộ ra
dưới máy khách. Phải copy từ cây chính trước khi build:

    sfx/                 (âm thanh vỗ tay/cười — thiếu thì ISCC báo lỗi, dễ thấy)
    models/piper-vi/     (giọng đọc Piper — thiếu thì im lặng)
    models/vosk-vi-large/(ASR Vosk lớn — thiếu thì im lặng; tải: tools/download_voice_models.py --asr)
    tools/piper/         (binary Piper — thiếu thì im lặng)

Cách phát hiện nhanh: **so kích thước installer với bản trước**. Bản đầu tiên tôi
build ra 368 MB so với 431 MB của 1.6.2 — đúng bằng phần Vosk lớn bị thiếu.
Sau khi bù đủ: 417 MB (Nhẹ) / 500 MB (Nặng), lệch 13 MB so với 1.6.2 ở **cả hai**
biến thể — lệch đều nghĩa là do thư viện trong venv đã cập nhật, không phải
thiếu asset.

### Việc còn lại

1. **Gộp vào `main`.** Chưa làm: cây chính đang dở 1.7.0 (kiosk mode) với nhiều
   file chưa commit, trong đó có `core/version.py` (đã là 1.7.0) và
   `frontend_qt.py` — merge lúc này sẽ đè lên việc đang làm. Commit 1.7.0 trước,
   rồi `git merge fix/licensing-kickout` và xử lý xung đột ở hai file đó.
2. **Theo dõi `/admin/devices`** vài ngày: cột phiên bản phải chuyển dần sang
   1.6.3, số bản ghi drift phải ngừng tăng.
3. Khi không còn máy ≤1.6.2: xoá nhánh lỏng trong `_legacy_identities()` (mục 4.4).
