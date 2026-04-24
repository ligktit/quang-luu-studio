# Code Review & Kế hoạch Nâng cấp — Quang Lưu Studio

**Ngày:** 2026-04-24
**Phiên bản hiện tại:** v1.4.0 (từ `QuangLuuStudio_Setup.iss`)
**Tổng mã nguồn:** 8,089 dòng (core + main + frontend)

---

## Phần 1: Đánh giá tổng quan

### 1.1 Điểm mạnh

| Hạng mục | Ghi nhận |
|---|---|
| **Kiến trúc phân lớp** | `core/` → backend logic, `ui/` → trình bày, `backend.py` làm facade với lazy loading (PEP 562) |
| **Lazy loading** | Giảm thời gian khởi động activation gate đáng kể |
| **State machine rõ ràng** | `ToneSession` + `ToneState` trong `engine.py` |
| **Data migration installer** | `.iss` đã có migration từ v1.0 → v1.1+ (di chuyển JSON từ `{app}` → `%APPDATA%`) |
| **Memory management** | `MemoryGuard` + `MemoryProfiler` theo dõi và trim RAM chủ động |
| **Singleton AppConfig** | Nguồn config duy nhất |
| **Loại trừ Qt modules nặng** | `.spec` loại bỏ ~250MB (WebEngine, Quick, 3D…) |
| **COM isolation** | `recorder_worker.py` chạy process riêng để tránh xung đột COM |

### 1.2 Vấn đề nghiêm trọng

| # | Vấn đề | Mức độ | Ảnh hưởng |
|---|---|---|---|
| **I-01** | `core/engine.py` = **3070 dòng** (38% core) | 🔴 Cao | Khó test, khó maintain, khó review PR |
| **I-02** | `frontend_qt.py` = **1571 dòng** trong một file | 🔴 Cao | Coupling mạnh UI ↔ engine, khó tách |
| **I-03** | **0 file dùng `logging` module** — toàn `print()` | 🔴 Cao | Không có log level, không có log rotation, không debug được prod |
| **I-04** | **Không có version constant trong Python** — chỉ hardcode trong `.iss` | 🟠 Trung bình | Không thể hiển thị version trong app, không check update được |
| **I-05** | **Không có unit tests** (plan vừa viết là bước đầu) | 🔴 Cao | Regression khi refactor rất nguy hiểm với codebase 8k dòng |
| **I-06** | Activation dùng **MD5** checksum | 🟡 Thấp | OK cho anti-tampering nhẹ, nhưng dễ reverse engineer |
| **I-07** | **Không có crash reporter** / sentry / logging remote | 🟠 Trung bình | Bug user không thể debug |
| **I-08** | `os._exit(0)` ở `main.py:85` — bypass mọi cleanup | 🟡 Thấp | Hợp lý trong context (daemon threads giữ handle), nhưng cần flush log trước |
| **I-09** | **Không có auto-update mechanism** | 🔴 Cao | User phải tự tải, cài thủ công mỗi lần |
| **I-10** | **Installer không code-signed** | 🟠 Trung bình | SmartScreen cảnh báo; mọi download từ GitHub sẽ bị flag |
| **I-11** | URL GitHub trong `.iss` là placeholder (`quang-luu-studio`) | 🟠 Trung bình | Cần confirm repo thật trước khi làm update |
| **I-12** | `app_config.json` vừa read-only trong `{app}` vừa có thể update qua `AppConfig.save()` | 🟡 Thấp | Mâu thuẫn: save sẽ fail nếu không có quyền admin |
| **I-13** | Hardcoded magic strings (MIDI port name, ffmpeg paths) rải rác | 🟡 Thấp | Khó thay đổi khi cần |
| **I-14** | Không có type hints nhất quán | 🟡 Thấp | IDE hỗ trợ kém, mypy không chạy được |
| **I-15** | File `ecc7c44 claude` là commit message không mô tả | 🟡 Thấp | Conventional commits sẽ tốt hơn |

---

## Phần 2: Kế hoạch nâng cấp (sắp xếp theo mức độ ưu tiên)

### Ưu tiên 1 — Foundation (làm trước, bắt buộc cho auto-update)

#### 2.1 Version System (#I-04)

Tạo file `core/version.py`:

```python
__version__ = "1.4.0"
VERSION_TUPLE = (1, 4, 0)
BUILD_DATE = "2026-04-24"
GITHUB_REPO = "your-github-username/quang-luu-studio"   # chỉnh theo thực tế
GITHUB_RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
```

Sync với `.iss` bằng script build:
```python
# build_installer.py — đọc version.py rồi ghi vào .iss
from core.version import __version__
import re, pathlib
iss = pathlib.Path("QuangLuuStudio_Setup.iss")
iss.write_text(re.sub(
    r'#define MyAppVersion "[^"]+"',
    f'#define MyAppVersion "{__version__}"',
    iss.read_text(encoding="utf-8")
), encoding="utf-8")
```

#### 2.2 Logging System (#I-03)

Tạo `core/logger.py`:

```python
import logging, logging.handlers, os
from pathlib import Path

def setup_logging(log_dir: Path, level=logging.INFO):
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S"
    )
    root = logging.getLogger()
    root.setLevel(level)

    # File handler: rotating 5MB x 3 files
    fh = logging.handlers.RotatingFileHandler(
        log_dir / "app.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Console
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    root.addHandler(ch)

    logging.getLogger("librosa").setLevel(logging.WARNING)
    logging.getLogger("yt_dlp").setLevel(logging.WARNING)
```

Rồi thay thế dần: `print(...)` → `log.info(...)`, `log.warning(...)`, `log.error(..., exc_info=True)`.

#### 2.3 Tách `engine.py` thành nhiều file (#I-01)

Đề xuất chia `engine.py` thành **6 module** theo chức năng (mỗi file ~500 dòng):

```
core/engine/
├── __init__.py           (re-export SystemEngine)
├── base.py               (SystemEngine khung + properties)
├── midi_mixin.py         (connect/disconnect/send_midi/trigger_midi_learn)
├── youtube_mixin.py      (open_youtube/detect_youtube_url/watcher)
├── tone_mixin.py         (detect_tone/autokey/resolve_tone)
├── recording_mixin.py    (start/stop_quick_score)
└── lifecycle_mixin.py    (launch_app/kill_app/browser_volume)
```

Dùng **composition** hơn mixin nếu có thể:
```python
class SystemEngine:
    def __init__(self):
        self.midi = MidiController()
        self.youtube = YouTubeSession()
        self.tone = ToneEngine()
        self.recorder = RecordingController()
```

Tách từ từ, mỗi PR một module, dùng `git mv` + test song song để tránh regression.

#### 2.4 Unit Tests (#I-05)

Đã có `TEST_PLAN.md` — triển khai theo 4 sprint:
- Sprint 1 (pure logic): `utils`, `config`, `design_tokens` — **tuần 1**
- Sprint 2 (file I/O): `activation`, `songs`, `tone_cache` — **tuần 2**
- Sprint 3 (mock external): `midi`, `scoring`, `ytdlp_support`, `memory` — **tuần 3**
- Sprint 4 (orchestration): `tone_detector`, `engine`, `detect_youtube` — **tuần 4**

Thêm GitHub Actions `.github/workflows/test.yml` để chạy CI khi mỗi lần push.

---

### Ưu tiên 2 — Auto-Update qua GitHub (chính)

Xem **Phần 3** chi tiết bên dưới.

---

### Ưu tiên 3 — Chất lượng & UX

#### 3.1 Code signing (#I-10)

- Mua certificate từ **Sectigo/DigiCert** (~$100/năm cho EV cert) hoặc dùng **SignPath** (free cho OSS)
- Ký `QuangLuuStudio.exe` + `Setup_QuangLuuStudio_v1.4.0.exe` trong pipeline build
- Thêm bước ký vào `build_installer.bat`:
```bat
signtool sign /tr http://timestamp.sectigo.com /td sha256 /fd sha256 ^
  /a "installer_output\Setup_QuangLuuStudio_v%VERSION%.exe"
```

#### 3.2 Crash reporter (#I-07)

2 lựa chọn:
- **Sentry SDK** (sentry-sdk[python]) — có free tier 5k events/month
- **Tự viết**: catch `sys.excepthook`, POST stacktrace + log lên GitHub Issues qua API

Ví dụ mini crash reporter:
```python
# core/crash_reporter.py
def install_crash_handler(log_path: Path):
    def handle(exc_type, exc, tb):
        import traceback, datetime
        with open(log_path.parent / f"crash-{datetime.datetime.now():%Y%m%d_%H%M%S}.log", "w") as f:
            traceback.print_exception(exc_type, exc, tb, file=f)
        sys.__excepthook__(exc_type, exc, tb)
    sys.excepthook = handle
```

#### 3.3 Hoàn thiện `AppConfig.save()` (#I-12)

Tách rõ:
- `app_config.json` trong `{app}`: **read-only**, chỉ thay đổi qua installer / admin edit
- User overrides lưu trong `%APPDATA%/QuangLuuStudio/user_config.json`
- Khi load: merge `app_config` → `user_config` → runtime

#### 3.4 Type hints + mypy (#I-14)

- Thêm `mypy.ini` với `strict = False` ban đầu
- Incremental: mỗi module pass mypy → ghi vào `mypy.ini` `[mypy-core.utils]` strict = True
- Ưu tiên type cho `core/` trước

#### 3.5 Commit convention (#I-15)

Áp dụng **Conventional Commits**:
```
feat(engine): add autokey segment detection
fix(midi): retry connection on timeout
refactor(engine): split into mixins
chore(deps): bump yt-dlp to 2025.1
docs: update test plan
```

Thêm pre-commit hook kiểm tra commit message format.

---

## Phần 3: Kế hoạch Auto-Update qua GitHub

### 3.1 Tổng quan luồng

```
┌─────────────────┐        ┌──────────────────┐        ┌──────────────┐
│ App khởi động   │ ──POST─▶│ GitHub Releases │ ──JSON─▶│ UpdateChecker│
│ (main.py)       │        │      API         │        └──────┬───────┘
└─────────────────┘        └──────────────────┘               │
                                                               │ if newer
                                                               ▼
                  ┌──────────────────┐        ┌──────────────────────────┐
                  │  Download Setup  │ ──────▶│  Verify SHA256 + signature│
                  │  .exe (resume)   │        └────────┬─────────────────┘
                  └──────────────────┘                 │
                                                       ▼
                  ┌──────────────────────────────────────┐
                  │  Prompt user: "Phiên bản 1.5.0 sẵn   │
                  │  sàng — Cài đặt ngay?"               │
                  └────────────┬─────────────────────────┘
                               │ Yes
                               ▼
                  ┌───────────────────────────┐
                  │ Run Setup.exe             │
                  │ /SILENT /CLOSEAPPLICATIONS│
                  │ /RESTARTAPPLICATIONS      │
                  └───────────────────────────┘
```

### 3.2 Cấu trúc Module

Tạo `core/updater/`:

```
core/updater/
├── __init__.py
├── version_check.py      (so sánh semver, gọi API)
├── downloader.py         (tải installer có progress + resume)
├── verifier.py           (kiểm tra SHA256 và chữ ký số)
└── installer.py          (khởi chạy installer với quyền admin)
```

### 3.3 Specifications

#### 3.3.1 `version_check.py`

```python
from dataclasses import dataclass
from typing import Optional
import urllib.request, json, re, logging
from core.version import __version__, GITHUB_RELEASES_API

log = logging.getLogger(__name__)

@dataclass
class ReleaseInfo:
    version: str                  # "1.5.0"
    tag_name: str                 # "v1.5.0"
    download_url: str             # .exe asset URL
    sha256: Optional[str]         # từ SHA256SUMS.txt asset
    body: str                     # release notes (Markdown)
    published_at: str             # ISO 8601
    size_bytes: int

def _parse_semver(v: str) -> tuple[int, int, int]:
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", v)
    if not m:
        raise ValueError(f"Invalid version: {v}")
    return tuple(int(x) for x in m.groups())

def is_newer(remote: str, local: str = __version__) -> bool:
    return _parse_semver(remote) > _parse_semver(local)

def check_latest_release(timeout: int = 10) -> Optional[ReleaseInfo]:
    """Gọi GitHub API, trả về thông tin release mới nhất, hoặc None nếu lỗi / không có update."""
    req = urllib.request.Request(
        GITHUB_RELEASES_API,
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": f"QuangLuuStudio/{__version__}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        log.warning("Update check failed: %s", e)
        return None

    # Tìm asset là Setup .exe
    exe_asset = next(
        (a for a in data.get("assets", []) if a["name"].endswith(".exe")), None
    )
    if not exe_asset:
        return None

    # Tìm SHA256SUMS (optional)
    sha_asset = next(
        (a for a in data.get("assets", []) if a["name"] == "SHA256SUMS.txt"), None
    )
    sha256 = None
    if sha_asset:
        try:
            with urllib.request.urlopen(sha_asset["browser_download_url"], timeout=timeout) as r:
                for line in r.read().decode().splitlines():
                    if exe_asset["name"] in line:
                        sha256 = line.split()[0]
                        break
        except Exception:
            pass

    return ReleaseInfo(
        version=data["tag_name"].lstrip("v"),
        tag_name=data["tag_name"],
        download_url=exe_asset["browser_download_url"],
        sha256=sha256,
        body=data.get("body", ""),
        published_at=data.get("published_at", ""),
        size_bytes=exe_asset["size"],
    )
```

#### 3.3.2 `downloader.py`

```python
import urllib.request, hashlib, os
from pathlib import Path
from typing import Callable

def download_with_progress(
    url: str,
    dest: Path,
    on_progress: Callable[[int, int], None] | None = None,
    chunk: int = 64 * 1024,
) -> Path:
    """Tải file với progress callback (downloaded_bytes, total_bytes). Resume nếu file dở dang."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")

    resume_from = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(url)
    if resume_from:
        req.add_header("Range", f"bytes={resume_from}-")

    with urllib.request.urlopen(req, timeout=30) as resp:
        total = int(resp.headers.get("Content-Length", 0)) + resume_from
        mode = "ab" if resume_from else "wb"
        downloaded = resume_from
        with open(part, mode) as f:
            while True:
                block = resp.read(chunk)
                if not block:
                    break
                f.write(block)
                downloaded += len(block)
                if on_progress:
                    on_progress(downloaded, total)

    part.rename(dest)   # atomic
    return dest
```

#### 3.3.3 `verifier.py`

```python
import hashlib, subprocess
from pathlib import Path

def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def verify_sha256(path: Path, expected: str) -> bool:
    return sha256_of(path).lower() == expected.lower()

def verify_signature(path: Path) -> bool:
    """Kiểm tra Authenticode signature bằng signtool hoặc PowerShell."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-AuthenticodeSignature '{path}').Status"],
            capture_output=True, text=True, timeout=10
        )
        return out.stdout.strip() == "Valid"
    except Exception:
        return False
```

#### 3.3.4 `installer.py`

```python
import subprocess, sys, os
from pathlib import Path

def run_installer(setup_path: Path, silent: bool = False) -> None:
    """Chạy installer. /SILENT cho update tự động; nếu không sẽ hiện wizard."""
    flags = [
        "/CLOSEAPPLICATIONS",      # Đóng app đang chạy trước khi ghi đè
        "/RESTARTAPPLICATIONS",    # Khởi động lại app sau khi cài
    ]
    if silent:
        flags.insert(0, "/VERYSILENT")
        flags.append("/SUPPRESSMSGBOXES")
    else:
        flags.insert(0, "/SILENT")   # Progress bar, no wizard

    # Detach: spawn rồi thoát app hiện tại (installer cần exe này đóng)
    subprocess.Popen([str(setup_path), *flags], creationflags=subprocess.DETACHED_PROCESS)
    sys.exit(0)
```

### 3.4 UX flow trong app

#### Tại `main.py` sau activation gate:

```python
# Check update in background thread (non-blocking)
from core.updater import check_and_prompt_update
import threading
threading.Thread(target=check_and_prompt_update, daemon=True).start()
```

#### `check_and_prompt_update()` (orchestrator)

```python
# core/updater/__init__.py
import logging
from pathlib import Path
from core.config import _get_data_dir
from .version_check import check_latest_release, is_newer
from .downloader import download_with_progress
from .verifier import verify_sha256
from .installer import run_installer

log = logging.getLogger(__name__)

def check_and_prompt_update(auto_download: bool = True):
    release = check_latest_release()
    if not release:
        log.info("No update available or API unreachable")
        return
    if not is_newer(release.version):
        return

    log.info("New version available: %s", release.version)

    # UI signal — emit qua QApplication.instance() hoặc pyqtSignal để main thread show dialog
    from frontend_qt import show_update_dialog   # lazy import
    show_update_dialog(release, on_accept=lambda: _do_update(release))


def _do_update(release):
    dest = _get_data_dir() / "updates" / f"Setup_{release.version}.exe"
    download_with_progress(release.download_url, dest)
    if release.sha256 and not verify_sha256(dest, release.sha256):
        log.error("SHA256 mismatch — aborting update")
        dest.unlink(missing_ok=True)
        return
    run_installer(dest, silent=False)
```

#### Dialog UI (trong `frontend_qt.py` hoặc `ui/dialogs/update.py`)

Dialog hiển thị:
- Phiên bản hiện tại → phiên bản mới
- Release notes (render Markdown với `QTextBrowser`)
- Dung lượng tải
- Nút: `Cài đặt ngay` | `Để sau` | `Bỏ qua phiên bản này`
- Nếu user chọn **Để sau**: nhắc lại sau 24h
- Nếu user chọn **Bỏ qua**: ghi `skipped_version` vào settings, không hỏi lại version đó

```python
# ui/dialogs/update.py
class UpdateDialog(QDialog):
    def __init__(self, release: ReleaseInfo, parent=None):
        super().__init__(parent)
        self.release = release
        self.setWindowTitle(f"Có phiên bản mới: v{release.version}")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            f"<h3>Phiên bản {self.release.version} đã sẵn sàng</h3>"
            f"<p>Phiên bản hiện tại: {__version__}</p>"
            f"<p>Dung lượng: {self.release.size_bytes / 1e6:.1f} MB</p>"
        ))
        notes = QTextBrowser()
        notes.setMarkdown(self.release.body)
        notes.setMaximumHeight(300)
        layout.addWidget(notes)
        # Buttons
        hb = QHBoxLayout()
        btn_install = QPushButton("Cài đặt ngay"); btn_install.clicked.connect(self.accept)
        btn_later = QPushButton("Để sau"); btn_later.clicked.connect(self.reject)
        btn_skip = QPushButton("Bỏ qua phiên bản này"); btn_skip.clicked.connect(self._on_skip)
        hb.addWidget(btn_install); hb.addWidget(btn_later); hb.addWidget(btn_skip)
        layout.addLayout(hb)
```

### 3.5 Settings để kiểm soát update

Thêm vào `settings.json`:

```json
{
  "update": {
    "auto_check": true,
    "check_interval_hours": 24,
    "last_check_timestamp": 0,
    "skipped_version": "",
    "channel": "stable"
  }
}
```

Settings dialog (`ui/dialogs/settings_dialog.py`) thêm section:
- ☑ Tự động kiểm tra phiên bản mới
- Chu kỳ check: [dropdown: Mỗi khi khởi động / Mỗi 24h / Mỗi 7 ngày]
- Kênh: [Stable / Beta] — tương lai

### 3.6 Release Process (tác giả / CI)

#### `.github/workflows/release.yml`

```yaml
name: Build & Release
on:
  push:
    tags: ['v*.*.*']

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with: { python-version: '3.11' }

      - name: Install deps
        run: |
          python -m pip install -r requirements.txt
          python -m pip install pyinstaller

      - name: Build exe
        run: pyinstaller QuangLuuStudio.spec

      - name: Install Inno Setup
        run: choco install innosetup -y

      - name: Sync version to .iss
        run: python build_installer.py

      - name: Build installer
        run: |
          & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" QuangLuuStudio_Setup.iss

      # (Nếu có code cert)
      - name: Sign installer
        env: { CERT_PWD: ${{ secrets.CERT_PASSWORD }} }
        run: |
          signtool sign /f cert.pfx /p $env:CERT_PWD `
            /tr http://timestamp.sectigo.com /td sha256 /fd sha256 `
            installer_output\Setup_QuangLuuStudio_v*.exe

      - name: Compute SHA256
        run: |
          Get-FileHash installer_output\*.exe -Algorithm SHA256 |
            ForEach-Object { "$($_.Hash.ToLower())  $(Split-Path $_.Path -Leaf)" } |
            Out-File -Encoding ascii SHA256SUMS.txt

      - name: Create Release
        uses: softprops/action-gh-release@v2
        with:
          files: |
            installer_output/Setup_QuangLuuStudio_v*.exe
            SHA256SUMS.txt
          generate_release_notes: true
```

Release notes được GitHub tự sinh từ commit messages (nếu dùng Conventional Commits sẽ đẹp hơn).

### 3.7 Ma trận rủi ro & mitigation

| Rủi ro | Mức độ | Mitigation |
|---|---|---|
| GitHub API rate limit (60 req/giờ unauth) | Thấp | Cache `last_check_timestamp` 24h; dùng ETag |
| Download dang dở do mất mạng | Trung | Resume với HTTP `Range`, file `.part` |
| Installer bị modify giữa đường (MITM) | Trung | Kiểm tra SHA256 + Authenticode signature |
| User đang sử dụng khi update | Cao | `/CLOSEAPPLICATIONS` + `/RESTARTAPPLICATIONS` của Inno Setup |
| Rollback khi update lỗi | Cao | Inno Setup tự tạo uninstaller của version cũ trong `unins000.exe` — user có thể rollback thủ công. Nâng cao: backup exe cũ trước khi chạy installer |
| Breaking changes trong `settings.json` | Trung | Thêm field `settings_version`, migration script khi load |
| User skip update quá nhiều version | Thấp | Nếu version cách nhau > N minor → force prompt |

### 3.8 Timeline triển khai auto-update

| Tuần | Deliverable |
|---|---|
| **Tuần 1** | Foundation: `core/version.py`, `core/logger.py`, sync version script |
| **Tuần 2** | `core/updater/version_check.py` + unit tests + tạo GitHub repo thật, tag v1.4.0 test |
| **Tuần 3** | `downloader.py` + `verifier.py` + `installer.py` + CI workflow release |
| **Tuần 4** | UI dialog + integration với `main.py` + settings |
| **Tuần 5** | Code signing setup + SmartScreen reputation (ký với EV cert đẩy nhanh) |
| **Tuần 6** | Beta test với nhóm nhỏ, fix edge cases, ship v1.5.0 như release đầu có auto-update |

---

## Phần 4: Thứ tự thực thi khuyến nghị

```
Tháng 1: Foundation
  Tuần 1 → 2.1 version.py + 2.2 logger.py + 3.5 commit convention
  Tuần 2 → 2.4 Unit tests Sprint 1-2
  Tuần 3 → 2.4 Unit tests Sprint 3
  Tuần 4 → 2.4 Unit tests Sprint 4

Tháng 2: Refactor & Auto-Update
  Tuần 5 → 2.3 Tách engine.py (MIDI + YouTube mixins)
  Tuần 6 → 2.3 Tách engine.py (Tone + Recording mixins)
  Tuần 7 → 3.3.1-3.3.2 (version_check + downloader)
  Tuần 8 → 3.3.3-3.3.4 (verifier + installer) + UI dialog

Tháng 3: Polish
  Tuần 9  → 3.1 Code signing + CI/CD workflow
  Tuần 10 → 3.2 Crash reporter
  Tuần 11 → 3.3 AppConfig tách user_config + 3.4 type hints
  Tuần 12 → Beta test + ship v1.5.0 (release đầu có auto-update)
```

---

## Phần 5: Phụ thuộc mới cần thêm

```txt
# requirements.txt bổ sung
# (tất cả đã trong stdlib: urllib, hashlib, subprocess)
# Không phát sinh dependency mới cho auto-update

# Dev dependencies:
pytest>=7.0
pytest-mock>=3.12
pytest-qt>=4.3
pytest-cov>=4.0
mypy>=1.8           # optional
```

Auto-update **không yêu cầu thêm package** — dùng thuần stdlib để giữ installer nhỏ gọn.

---

## Phụ lục A: Checklist trước khi ship release đầu tiên có auto-update

- [ ] Tạo GitHub repo (public hoặc private với token)
- [ ] Cập nhật `GITHUB_REPO` trong `core/version.py` cho đúng
- [ ] Setup `secrets.CERT_PASSWORD` trong GitHub repo settings (nếu có cert)
- [ ] Tag `v1.4.0` và ship release thủ công (để client v1.4.0 cũ có gì để so sánh)
- [ ] Ship `v1.5.0` qua CI — đây là release đầu có auto-update
- [ ] User trên v1.4.0 cập nhật bằng tay sang v1.5.0; từ v1.5.0 trở đi sẽ tự động
- [ ] Document cho user trong README cách xử lý khi update fail (thường là chạy lại installer thủ công)

---

*Tài liệu này bổ sung cho `tests/TEST_PLAN.md` — nên đọc song song.*
