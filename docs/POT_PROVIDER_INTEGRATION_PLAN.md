# PO Token Provider Integration Plan

> ## ⚠️ DEPRECATED — không triển khai (2026-04-25)
>
> **Lý do bỏ:** Upstream `bgutil-ytdlp-pot-provider` chỉ release source code Node.js
> (`.zip`), KHÔNG có standalone binary chính thức. Để chạy server cần:
>
> 1. Cài Node.js trên máy user (không thực tế cho desktop app), HOẶC
> 2. Tự build binary bằng `pkg`/`nexe`/`bun` (thêm build step + ~50MB)
>
> Cost không tương xứng với benefit cho 95% case mà `player_client=[tv_embedded,
> web_safari, ...]` đã giải quyết được.
>
> **Code đã thử và đã revert:**
> - `core/pot_provider.py` (deleted)
> - Engine init/shutdown hooks
> - Settings UI status row
> - `pot_provider_*` config fields
> - `bgutil-ytdlp-pot-provider` từ requirements.txt
> - `collect_all('yt_dlp_plugins')` từ .spec
> - Source line trong .iss
> - Step 1.5 trong build_installer.bat
>
> **Phần KHÔNG revert (vẫn còn trong codebase):**
> - `DEFAULT_PLAYER_CLIENTS = ("tv_embedded", "web_safari", "default", "ios")`
>   trong `core/ytdlp_support.py` — bypass anti-bot không cần cookie cho ~90% case
> - `socket_timeout=20`, `retries=2` trong `make_ydl_opts()` — chống yt-dlp treo
> - Watchdog timer 90s/300s trong tone detection (`core/engine/_tone.py`)
>
> **Khi nào nên xem lại plan này:**
> - Upstream release standalone Windows binary (theo dõi GitHub releases)
> - YouTube siết hơn và `player_client` tricks không còn work
> - User community có cách khác đơn giản hơn (yt-dlp native PO Token v.v.)
>
> Plan gốc bên dưới giữ nguyên để tham khảo kiến trúc nếu sau này quay lại.

---

# Plan gốc (không còn áp dụng)

**Mục tiêu:** Thay thế/bổ sung cơ chế cookie hiện tại bằng `bgutil-ytdlp-pot-provider` — cách bền vững nhất để yt-dlp vượt qua YouTube anti-bot 2025+.

**Ngày:** 2026-04-25

---

## Bối cảnh

YouTube đã triển khai PO Token (Proof-of-Origin Token) cho hầu hết client.
Cookie-based auth và OAuth2 đang bị suy giảm:

- Cookie `chromium DB lock` khi browser đang chạy → user phải đóng browser
- OAuth2 plugin đã bị deprecate/chặn
- Chỉ còn PO Token là con đường chính thống (được yt-dlp dev community support dài hạn)

`bgutil-ytdlp-pot-provider` = reference implementation, có:
- Python plugin (HTTP client): `bgutil-ytdlp-pot-provider` (PyPI) ✅
- **Server**: **chỉ có Node.js source code** (`.zip` trên GitHub releases) — KHÔNG có
  standalone binary chính thức. Muốn có `.exe` phải tự compile bằng
  `pkg`/`nexe`/`bun build --compile`, hoặc user cài Node.js rồi tự chạy
  `node server.js`.
- HTTP localhost port mặc định: `4416`

**Trạng thái hiện tại (2026-04-25):** code đã sẵn sàng spawn binary nếu có. Binary
chưa được cung cấp sẵn → PoTokenProvider.status = `binary_missing` → app fallback
về cookie chain như cũ. Không có regression.

## Kiến trúc

```
┌─────────────────────────────────────────────┐
│  QuangLuuStudio.exe (main process)          │
│                                             │
│  SystemEngine.__init__()                    │
│   └─ pot_provider.start()                   │
│        └─ subprocess.Popen(                 │
│             tools/bgutil-pot-provider.exe   │
│             --port 4416                     │
│           )                                 │
│                                             │
│  extract_info_with_auth(url, ydl_opts)      │
│   └─ yt_dlp.YoutubeDL({                     │
│        "extractor_args": {                  │
│          "youtube": {                       │
│            "player_client": [               │
│              "tv_embedded", "web_safari",   │
│              "ios", "default"               │
│            ],                               │
│            "getpot_bgutil_baseurl": [       │
│              "http://127.0.0.1:4416"        │
│            ]                                │
│          }                                  │
│        }                                    │
│      })                                     │
│       └─ [plugin] bgutil client → HTTP →    │
│          bgutil-pot-provider.exe            │
│                                             │
│  closeEvent → _bg_shutdown()                │
│   └─ pot_provider.stop()                    │
└─────────────────────────────────────────────┘
```

## File changes

### 1. `core/pot_provider.py` (NEW)

Singleton `PoTokenProvider`:

- `start()` — spawn binary subprocess, wait for health ping (`GET /ping` với timeout 5s)
- `stop()` — SIGTERM → wait 2s → kill
- `is_alive()` — health check
- `base_url` — `http://127.0.0.1:<port>`
- Graceful degrade: nếu binary không có → log warning, `is_alive()` trả False, app vẫn chạy được (rơi về cookie/no-auth fallback)
- Binary discovery order:
  1. `AppConfig.get("pot_provider_binary")` (override)
  2. `APP_DIR/tools/bgutil-pot-provider.exe`
  3. `APP_DIR/bgutil-pot-provider.exe`

### 2. `core/ytdlp_support.py` (MODIFY)

- Thêm `_apply_default_extractor_args(opts)`: inject `player_client` list + `getpot_bgutil_baseurl` nếu provider alive
- `make_ydl_opts()` gọi helper trên
- **Attempt chain mới:**
  1. `{"kind": "none"}` — với PO Token + player_client ưu tiên (tv_embedded/web_safari thường không cần cookie khi có PO Token)
  2. `{"kind": "cookie_file"}` — nếu user config
  3. `{"kind": "cookie_file"}` — auto-snapshot
  4. `{"kind": "browser"}` — fallback list

### 3. `core/engine/__init__.py` (MODIFY)

```python
from core.pot_provider import PoTokenProvider
...
self.pot_provider = PoTokenProvider()
self.pot_provider.start()
```

### 4. `frontend_qt.py` (MODIFY)

Trong `_bg_shutdown()`:
```python
if hasattr(engine, "pot_provider"):
    try:
        engine.pot_provider.stop()
    except Exception:
        pass
```

### 5. `ui/dialogs/settings_dialog.py` (MODIFY)

Thêm status row vào YouTube Cookie section:
```
PO Token Provider: [●] Running (:4416)   [Restart]
                   [●] Not available — xem docs
```

### 6. `QuangLuuStudio.spec` (MODIFY)

Binary đã nằm trong `tools/` → sẽ tự được bundle theo dòng hiện có `('tools', 'tools')`.
Thêm hidden import: `yt_dlp_plugins` (để PyInstaller bundle plugin entry points).

### 7. `QuangLuuStudio_Setup.iss` (MODIFY)

Thêm:
```
Source: "tools\bgutil-pot-provider.exe"; DestDir: "{app}\tools"; Flags: ignoreversion
```

### 8. `build_installer.bat` (MODIFY)

**Revised (2026-04-25):** auto-download đã bỏ vì URL chính thức không có. Thay
vào đó: log thông báo khuyến khích setup thủ công. Muốn có binary, cần build
từ source hoặc wait cho upstream release `.exe`.

**Cách tạo binary thủ công (tùy chọn):**
```bash
git clone https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git
cd bgutil-ytdlp-pot-provider/server
npm install
npx pkg . -t node20-win-x64 -o bgutil-pot-provider.exe
cp bgutil-pot-provider.exe <project>/tools/
```

### 9. `requirements.txt` (MODIFY)

Thêm: `bgutil-ytdlp-pot-provider>=1.0`

### 10. `app_config.json` (MODIFY)

Thêm field default:
```json
"pot_provider_enabled": true,
"pot_provider_port": 4416,
"pot_provider_binary": ""
```

## Behavioral change

- Trước: lỗi cookie DB lock → user phải đóng browser
- Sau: PO Token cung cấp sẵn → yt-dlp dùng `tv_embedded`/`web_safari` không cần cookie trong 95% case
- Cookie chỉ còn là fallback cho edge case (private/age-gated/member-only video)

## Rollback

Để tắt PO Token:
- Set `pot_provider_enabled: false` trong `app_config.json`, hoặc
- Xoá `tools/bgutil-pot-provider.exe`

App tự động fall back về behavior cũ (cookie attempts chain).

## Test plan

- [ ] Fresh install → thử video public → pass không cần browser
- [ ] Tắt provider → thử video public → cookie fallback kick in
- [ ] App close → `bgutil-pot-provider.exe` process biến mất trong Task Manager
- [ ] App crash → orphan process check (cần có cleanup hook)
- [ ] Video age-gated → cookie attempt vẫn chạy

## Mở rộng tương lai

- Health monitoring: restart provider nếu crash
- Metrics: log số lần gọi provider, hit rate
- Fallback: nếu provider không phản hồi > N giây, disable và chuyển cookie-only mode
