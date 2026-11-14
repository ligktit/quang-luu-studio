# Velopack — Kế hoạch 1/4: Spike kiểm chứng

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trả lời 6 câu hỏi kiểm chứng của spec (mục 5, "Bước 0") bằng thử nghiệm thật trên máy dev Windows, ghi kết quả thành văn bản; chỉ giữ lại một sửa lỗi an toàn (`_cleanup_mei`).

**Architecture:** Một app thử tối giản (PySide6 + `velopack`) đóng gói onedir → `vpk pack` hai phiên bản → phục vụ bằng `python -m http.server` → cài, cập nhật, quan sát log. Sau đó đóng gói **app thật** dạng onedir để đo. Code thử nằm trong `.venv\spike_velo\` (gitignored) và `spike_onedir.spec` (gitignored theo mẫu `*.spec`); không commit, xoá khi xong.

**Tech Stack:** Python 3.13 `.venv` Windows, PyInstaller 6.22, `velopack==1.2.161` (PyPI), `vpk` (.NET tool) cùng phiên bản, .NET SDK 8, PySide6.

**Spec:** `docs/superpowers/specs/2026-10-12-velopack-installer-design.md`

**Các kế hoạch khác:** 2 — chuẩn bị phía app (không phụ thuộc Velopack); 3 — feed cập nhật phía server; 4 — tích hợp Velopack + CI + cầu nối (viết **sau** khi có kết quả spike này).

## Global Constraints

- Chạy lệnh Windows từ WSL: `cmd.exe /c "cd /d D:\Projects\quang-luu-studio && ..."` hoặc `powershell.exe -NoProfile -Command '...'` (nháy đơn ngoài). Script tạm phải nằm trong `.venv\` vì Windows không đọc được scratchpad WSL.
- numpy ghim `<2.3` (numba 0.68). Không nâng.
- Không push tag, không đụng GitHub Release, không đụng server thật trong spike.
- packId thử: `QLSSpike`; packId thật: `QuangLuuStudio`.
- Mọi file JSON ghi ra: UTF-8 **không BOM**.
- Spike **chỉ commit** Task 1 (sửa `_cleanup_mei`) và file kết quả (Task 6). Không commit thay đổi `main.py` tạm ở Task 4.

## Review Focus

- **App onedir tự xoá chính mình khi thoát**: `_cleanup_mei` xoá `sys._MEIPASS`; ở onedir đó là `current\_internal` → lần mở sau app hỏng. Người dùng mong app mở lại bình thường. (Task 1 có test.)
- **Hook cài đặt không được xử lý**: Setup chạy exe với `--veloapp-install`; nếu app mở giao diện thay vì thoát ngay thì bị giết sau 30 s, cài đặt chậm/hỏng. (Task 3 bước 6, Task 4 bước 3 kiểm.)
- **Tắt ngang khi đã tải bản mới**: người dùng mong lần mở sau tự dùng bản mới. (Task 3 bước 10.)
- **Đường dẫn có dấu tiếng Việt / dấu cách trong tên người dùng Windows**: `%LocalAppData%` có thể chứa ký tự Unicode. (Task 3 bước 5 ghi lại đường dẫn thật; nếu máy dev không có, ghi "chưa kiểm" vào kết quả.)
- **Máy không có mạng khi kiểm cập nhật**: người dùng mong app chạy bình thường, không treo. (Task 3 bước 11.)

---

### Task 1: Chặn `_cleanup_mei` xoá thư mục cài của bản onedir

**Files:**
- Create: `core/frozen_paths.py`
- Modify: `main.py:9-18` (hàm `_cleanup_mei`)
- Test: `tests/core/test_frozen_paths.py`

**Interfaces:**
- Produces: `core.frozen_paths.onefile_extract_dir() -> str | None` — trả `sys._MEIPASS` **chỉ khi** đó là thư mục giải nén tạm của onefile (tên bắt đầu `_MEI`, nằm trực tiếp trong thư mục temp); ngược lại `None`.

- [ ] **Step 1: Viết test thất bại**

```python
# tests/core/test_frozen_paths.py
"""_cleanup_mei chỉ được xoá thư mục giải nén TẠM của onefile.

Bản onedir (Velopack) có sys._MEIPASS = <thư mục cài>\\_internal — xoá nó là
app tự huỷ mỗi lần thoát."""
import os
import sys
import tempfile

from core import frozen_paths


def test_khong_frozen_thi_none(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert frozen_paths.onefile_extract_dir() is None


def test_onefile_trong_temp_thi_tra_duong_dan(monkeypatch):
    mei = os.path.join(tempfile.gettempdir(), "_MEI123456")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", mei, raising=False)
    assert frozen_paths.onefile_extract_dir() == mei


def test_onedir_internal_thi_none(monkeypatch, tmp_path):
    internal = tmp_path / "QuangLuuStudio" / "current" / "_internal"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(internal), raising=False)
    assert frozen_paths.onefile_extract_dir() is None


def test_ten_mei_nhung_khong_nam_trong_temp_thi_none(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "x" / "_MEI99"), raising=False)
    assert frozen_paths.onefile_extract_dir() is None
```

Lưu ý: `tmp_path` của pytest nằm trong thư mục temp nhưng **lồng sâu** (`.../pytest-of-x/pytest-N/test_x0/...`), nên điều kiện "nằm trực tiếp trong temp" phân biệt được.

- [ ] **Step 2: Chạy test, xác nhận thất bại**

Run: `cmd.exe /c "D:\Projects\quang-luu-studio\.venv\Scripts\python.exe -m pytest D:\Projects\quang-luu-studio\tests\core\test_frozen_paths.py -q -p no:cacheprovider --rootdir=D:\Projects\quang-luu-studio"`
Expected: FAIL — `ImportError: cannot import name 'frozen_paths'`.

- [ ] **Step 3: Viết code**

```python
# core/frozen_paths.py
"""Nhận biết kiểu đóng gói PyInstaller đang chạy."""
import os
import sys
import tempfile


def onefile_extract_dir():
    """Thư mục giải nén tạm của bản onefile (``%TEMP%\\_MEIxxxx``), hoặc None.

    Bản onedir cũng có ``sys._MEIPASS`` nhưng trỏ vào ``<thư mục cài>\\_internal``
    — thư mục đó là CHÍNH app, tuyệt đối không được xoá.
    """
    if not getattr(sys, "frozen", False):
        return None
    mei = getattr(sys, "_MEIPASS", None)
    if not mei:
        return None
    mei = os.path.normcase(os.path.abspath(mei))
    temp = os.path.normcase(os.path.abspath(tempfile.gettempdir()))
    if os.path.basename(mei).startswith(os.path.normcase("_MEI")) and os.path.dirname(mei) == temp:
        return getattr(sys, "_MEIPASS")
    return None
```

Lưu ý: `normcase` trên Windows hạ chữ thường → so `startswith(normcase("_MEI"))` là `"_mei"`. Hàm trả về chuỗi **gốc** `sys._MEIPASS` (không phải bản đã hạ chữ) để test so khớp.

Sửa `main.py:9-18` thành:

```python
# ── PyInstaller _MEI cleanup ──────────────────────────────────────────────────
def _cleanup_mei():
    """Xóa thư mục tạm _MEI khi app thoát — CHỈ của bản onefile.

    Bản onedir (cài bằng Velopack) có _MEIPASS = <thư mục cài>\\_internal;
    xoá nó là app tự huỷ, nên onefile_extract_dir() trả None cho trường hợp đó.
    """
    from core.frozen_paths import onefile_extract_dir
    mei_dir = onefile_extract_dir()
    if mei_dir and os.path.isdir(mei_dir):
        shutil.rmtree(mei_dir, ignore_errors=True)

atexit.register(_cleanup_mei)
```

- [ ] **Step 4: Chạy test, xác nhận qua**

Run: lệnh ở Step 2. Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add core/frozen_paths.py main.py tests/core/test_frozen_paths.py
git commit -m "fix(main): _cleanup_mei chỉ xoá thư mục giải nén tạm của onefile, không đụng _internal của bản onedir"
```

---

### Task 2: Dựng công cụ (velopack, .NET SDK, vpk)

**Files:** không đổi file trong repo.

- [ ] **Step 1: Cài gói Python vào `.venv`**

Run: `cmd.exe /c "D:\Projects\quang-luu-studio\.venv\Scripts\python.exe -m pip install velopack==1.2.161"`
Expected: `Successfully installed velopack-1.2.161`.

- [ ] **Step 2: Kiểm API khớp stub đã đọc (App, UpdateManager.wait_exit_then_apply_updates, get_update_pending_restart)**

Run: `cmd.exe /c "D:\Projects\quang-luu-studio\.venv\Scripts\python.exe -c \"import velopack as v; print([n for n in dir(v) if not n.startswith('_')]); print([n for n in dir(v.UpdateManager) if not n.startswith('_')]); print([n for n in dir(v.App) if not n.startswith('_')])\""`
Expected: có `App`, `UpdateManager`, `HttpSource`; `UpdateManager` có `check_for_updates`, `download_updates`, `get_update_pending_restart`, `wait_exit_then_apply_updates`, `get_current_version`; `App` có `run`, `on_first_run`, `on_restarted`, `set_auto_apply_on_startup`. Thiếu tên nào → ghi vào kết quả (Task 6) và dùng tên thật ở các bước sau.

- [ ] **Step 3: Cài .NET SDK 8**

Run: `powershell.exe -NoProfile -Command 'winget install --id Microsoft.DotNet.SDK.8 --exact --silent --accept-package-agreements --accept-source-agreements; dotnet --version'`
Expected: in ra `8.0.x`. (Nếu `dotnet` chưa có trong PATH của phiên hiện tại, mở phiên PowerShell mới.)

- [ ] **Step 4: Cài `vpk` cùng phiên bản**

Run: `powershell.exe -NoProfile -Command 'dotnet tool install -g vpk --version 1.2.161; vpk --version'`
Expected: `1.2.161`. Nếu NuGet báo không có bản này: chạy `dotnet tool search vpk --detail --take 1`, cài phiên bản mới nhất **có cùng major.minor** với gói pip, ghi cặp phiên bản thật dùng vào kết quả (Task 6).

---

### Task 3: App thử tối giản — cài, cập nhật ngầm, áp dụng khi thoát

**Files (tạm, không commit):**
- Create: `.venv\spike_velo\spike_app.py`
- Create: `.venv\spike_velo\VERSION.txt`

- [ ] **Step 1: Viết app thử**

```python
# .venv/spike_velo/spike_app.py
"""App thử Velopack: ghi mọi sự kiện ra %LOCALAPPDATA%\\QLSSpike_log.txt."""
import os
import sys
import threading
import time

LOG = os.path.join(os.environ.get("LOCALAPPDATA", "."), "QLSSpike_log.txt")
FEED = os.environ.get("QLS_SPIKE_FEED", "http://127.0.0.1:8765/")


def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')} pid={os.getpid()} {msg}\n")


log(f"start argv={sys.argv} exe={sys.executable} "
    f"FIRSTRUN={os.environ.get('VELOPACK_FIRSTRUN')} RESTART={os.environ.get('VELOPACK_RESTART')} "
    f"MEIPASS={getattr(sys, '_MEIPASS', None)}")

import velopack  # noqa: E402

(velopack.App()
    .on_first_run(lambda v: log(f"hook first_run {v}"))
    .on_restarted(lambda v: log(f"hook restarted {v}"))
    .on_after_install_fast_callback(lambda v: log(f"hook after_install {v}"))
    .on_after_update_fast_callback(lambda v: log(f"hook after_update {v}"))
    .on_before_update_fast_callback(lambda v: log(f"hook before_update {v}"))
    .on_before_uninstall_fast_callback(lambda v: log(f"hook before_uninstall {v}"))
    .run())
log("App().run() returned — chay giao dien")

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

state = {"um": None, "pending": None}


def updater():
    try:
        um = velopack.UpdateManager(FEED)
        state["um"] = um
        log(f"current={um.get_current_version()} pending_at_start={um.get_update_pending_restart()}")
        info = um.check_for_updates()
        log(f"check -> {info and info.TargetFullRelease.Version} deltas={info and len(info.DeltasToTarget)}")
        if info:
            t0 = time.time()
            um.download_updates(info, lambda p: log(f"progress {p}"))
            state["pending"] = um.get_update_pending_restart()
            log(f"downloaded in {time.time()-t0:.1f}s pending={state['pending'] and state['pending'].Version}")
    except Exception as e:
        log(f"updater error {type(e).__name__}: {e}")


app = QApplication(sys.argv)
here = os.path.dirname(sys.executable)
ver = open(os.path.join(getattr(sys, "_MEIPASS", here), "VERSION.txt"), encoding="utf-8").read().strip()
lbl = QLabel(f"QLSSpike {ver}\n{sys.executable}")
lbl.resize(500, 120)
lbl.show()
threading.Thread(target=updater, daemon=True).start()
code = app.exec()
um, pending = state["um"], state["pending"]
log(f"exiting, pending={pending and pending.Version}")
if um is not None and pending is not None:
    um.wait_exit_then_apply_updates(pending, silent=True, restart=False)
    log("wait_exit_then_apply_updates called")
sys.exit(code)
```

Ghi `1.0.0` vào `.venv\spike_velo\VERSION.txt`.

- [ ] **Step 2: Build onedir 1.0.0 và pack**

```
cmd.exe /c "cd /d D:\Projects\quang-luu-studio\.venv\spike_velo && ..\Scripts\pyinstaller.exe --noconfirm --onedir --noconsole --name QLSSpike --add-data VERSION.txt;. spike_app.py && vpk pack --packId QLSSpike --packVersion 1.0.0 --packDir dist\QLSSpike --mainExe QLSSpike.exe --outputDir releases"
```
Expected: `releases\` có `QLSSpike-1.0.0-full.nupkg`, `QLSSpike-win-Setup.exe`, `releases.win.json`. Ghi lại tên file thật vào kết quả.

- [ ] **Step 3: Build 1.0.1 (đổi VERSION.txt) và pack vào cùng thư mục**

Ghi `1.0.1` vào `VERSION.txt`, chạy lại lệnh Step 2 với `--packVersion 1.0.1`.
Expected: thêm `QLSSpike-1.0.1-full.nupkg` **và** `QLSSpike-1.0.1-delta.nupkg`; `releases.win.json` liệt kê cả hai bản. Mở `releases.win.json`, chép cấu trúc một phần tử `Assets` vào kết quả (Kế hoạch 3 dựa vào định dạng này).

- [ ] **Step 4: Phục vụ feed — ban đầu chỉ có 1.0.0**

Tạo `.venv\spike_velo\feed\` chỉ chứa file 1.0.0 + một `releases.win.json` chỉ có phần tử 1.0.0 (sửa tay từ file ở Step 3). Chạy nền:
`cmd.exe /c "cd /d D:\Projects\quang-luu-studio\.venv\spike_velo && start /b ..\Scripts\python.exe -m http.server 8765 --directory feed"`

- [ ] **Step 5: Cài bằng Setup 1.0.0 — trả lời câu 2 (không UAC)**

Chạy `releases\QLSSpike-win-Setup.exe` **bằng cách nhấp đúp trong Explorer** (để thấy UAC nếu có). Ghi lại: có UAC không; thư mục cài thật (`dir %LOCALAPPDATA%\QLSSpike`); shortcut Desktop/Start Menu nào được tạo; app có tự mở không; thời gian từ lúc bấm tới lúc app hiện.
Expected: không UAC; có `%LOCALAPPDATA%\QLSSpike\current\QLSSpike.exe` và `Update.exe`.

- [ ] **Step 6: Đọc log — trả lời câu 3 (hook + FIRSTRUN)**

Run: `powershell.exe -NoProfile -Command 'Get-Content $env:LOCALAPPDATA\QLSSpike_log.txt'`
Expected: một dòng `start argv=[..., '--veloapp-install', '1.0.0']` kèm `hook after_install 1.0.0` và **không** có "chay giao dien" ở cùng pid (App().run() tự thoát); sau đó lần chạy thường có `FIRSTRUN=` khác rỗng và/hoặc `hook first_run 1.0.0`. Ghi chính xác: biến `VELOPACK_FIRSTRUN` có giá trị gì, callback nhận tham số gì.

- [ ] **Step 7: Đưa 1.0.1 lên feed khi app đang chạy — trả lời câu 4a (tải ngầm)**

App 1.0.0 đang mở. Chép `QLSSpike-1.0.1-full.nupkg`, `QLSSpike-1.0.1-delta.nupkg` và `releases.win.json` đầy đủ (Step 3) vào `feed\`. Đóng app, mở lại từ shortcut (app sẽ kiểm tra lúc mở).
Expected trong log: `check -> 1.0.1 deltas=1`, `downloaded in ...s pending=1.0.1`; cửa sổ vẫn hiện `1.0.0`.

- [ ] **Step 8: Đóng app bình thường — trả lời câu 4b (áp dụng khi thoát, im lặng)**

Đóng cửa sổ. Chờ 10 giây. Mở lại từ shortcut.
Expected: log có `wait_exit_then_apply_updates called`; không có cửa sổ nào hiện khi áp dụng; lần mở sau cửa sổ hiện `1.0.1`, `current=1.0.1`, `RESTART=` rỗng (vì `restart=False`). Ghi lại nếu có hộp thoại/tiến trình nào hiện ra.

- [ ] **Step 9: Delta — trả lời câu 4c**

Trong log Step 7: `deltas=1`. Kiểm `dir %LOCALAPPDATA%\QLSSpike\packages` — ghi file nào được tải (delta hay full) và kích thước.

- [ ] **Step 10: Tắt ngang khi có bản chờ — trả lời câu 4d (tự áp dụng lần mở sau)**

Tạo 1.0.2 (VERSION.txt = `1.0.2`, build + pack như Step 2/3, chép lên `feed\`). Mở app (1.0.1), chờ log có `pending=1.0.2`, rồi **giết** tiến trình: `cmd.exe /c "taskkill /F /IM QLSSpike.exe"`. Mở lại từ shortcut.
Expected: cửa sổ hiện `1.0.2` (Velopack tự áp dụng ở lần mở — mặc định `set_auto_apply_on_startup(True)`). Ghi thời gian mở chậm thêm bao nhiêu.

- [ ] **Step 11: Không có mạng**

Dừng `http.server` (`taskkill /F /IM python.exe` **chỉ khi** không có pytest nào khác đang chạy — xem memory test-env). Mở app.
Expected: cửa sổ hiện bình thường ngay; log có `updater error ...` trong vòng vài giây, không treo. Ghi thời gian tới khi báo lỗi.

- [ ] **Step 12: Mark-of-the-Web — trả lời câu 5**

Run: `powershell.exe -NoProfile -Command 'Get-ChildItem $env:LOCALAPPDATA\QLSSpike\packages | ForEach-Object { $_.Name; Get-Item $_.FullName -Stream Zone.Identifier -ErrorAction SilentlyContinue }'`
Expected: không file nào có stream `Zone.Identifier` → SmartScreen không can thiệp bản cập nhật. Ghi kết quả.

- [ ] **Step 13: Gỡ cài đặt**

Gỡ QLSSpike qua Settings → Apps. Expected: log có `hook before_uninstall`; thư mục `%LOCALAPPDATA%\QLSSpike` biến mất; file log `%LOCALAPPDATA%\QLSSpike_log.txt` (ngoài thư mục cài) còn nguyên.

---

### Task 4: App thật dạng onedir — trả lời câu 1 và 6

**Files (tạm, không commit):**
- Create: `spike_onedir.spec` (gốc repo, đã bị `.gitignore` mẫu `*.spec` chặn)
- Modify tạm: `main.py` (thêm 2 dòng velopack), hoàn tác ở Step 8

- [ ] **Step 1: Sinh spec onedir từ spec thật**

Tạo `.venv\spike_velo\make_spec.py`:

```python
"""Sinh spike_onedir.spec: EXE không nhúng binaries/datas + COLLECT."""
import re
src = open(r"D:\Projects\quang-luu-studio\QuangLuuStudio.spec", encoding="utf-8").read()
old = "exe = EXE(\n    pyz,\n    a.scripts,\n    a.binaries,\n    a.datas,\n    [],\n"
assert old in src, "Khối EXE trong QuangLuuStudio.spec đã đổi — sửa make_spec.py"
src = src.replace(old, "exe = EXE(\n    pyz,\n    a.scripts,\n    [],\n    exclude_binaries=True,\n")
src += (
    "\ncoll = COLLECT(\n    exe,\n    a.binaries,\n    a.datas,\n    strip=False,\n"
    "    upx=True,\n    upx_exclude=[],\n    name='QuangLuuStudio',\n)\n"
)
open(r"D:\Projects\quang-luu-studio\spike_onedir.spec", "w", encoding="utf-8").write(src)
print("ok")
```

Run: `cmd.exe /c "D:\Projects\quang-luu-studio\.venv\Scripts\python.exe D:\Projects\quang-luu-studio\.venv\spike_velo\make_spec.py"` → `ok`.

- [ ] **Step 2: Thêm tạm velopack vào đầu `main.py`**

Chèn **ngay sau** dòng `import logging` (dòng 7) và **trước** khối `_cleanup_mei`:

```python
# SPIKE — KHÔNG COMMIT
import velopack
velopack.App().run()
```

- [ ] **Step 3: Build onedir + pack 1.9.0-spike**

```
cmd.exe /c "cd /d D:\Projects\quang-luu-studio && call .venv\Scripts\activate.bat && set PYTHONIOENCODING=utf-8&& pyinstaller --noconfirm spike_onedir.spec && vpk pack --packId QuangLuuStudio --packVersion 1.9.0-spike --packDir dist\QuangLuuStudio --mainExe QuangLuuStudio.exe --icon app_icon.ico --outputDir .venv\spike_velo\real_releases"
```
Expected: `dist\QuangLuuStudio\QuangLuuStudio.exe` + `dist\QuangLuuStudio\_internal\`. Ghi: tổng kích thước `dist\QuangLuuStudio`, kích thước `*-full.nupkg`, `*-Setup.exe`, thời gian build. Chép ffmpeg/qjs/models/tools\piper cạnh exe **giống `.iss` đang làm** trước khi pack: `binaries\qjs.exe` → `dist\QuangLuuStudio\`, `binaries\ffmpeg\*` → `dist\QuangLuuStudio\ffmpeg\`, `models\*` → `dist\QuangLuuStudio\models\`, `tools\piper\*` → `dist\QuangLuuStudio\tools\piper\`, cùng các `.bat`/`.ps1`, `studio_one\`, `cubase\`, `app_config.json` — rồi pack lại. Ghi danh sách lệnh chép thật dùng vào kết quả (Kế hoạch 4 sẽ đưa vào CI).

- [ ] **Step 4: Cài và đo**

Gỡ QLSSpike nếu còn. Chạy `.venv\spike_velo\real_releases\QuangLuuStudio-win-Setup.exe` (nhấp đúp). Ghi: UAC (mong không), thời gian cài, đường dẫn cài, app tự mở không.
Ghi thời gian khởi động tới khi cửa sổ chính hiện: bản onedir vs bản onefile hiện có (`installer_output` hoặc bản đang cài) — đo 3 lần mỗi bản, lấy trung vị.

- [ ] **Step 5: Kiểm chức năng — câu 1**

Trên bản đã cài:
1. `"%LOCALAPPDATA%\QuangLuuStudio\current\QuangLuuStudio.exe" --tu-kiem-tra` → mã thoát `0` (`echo %errorlevel%`).
2. `... --thu-tai` → mã thoát `0` (cần mạng).
3. Mở app: phát một bài YouTube, bấm SFX "Vỗ tay" (có tiếng), bật đọc giọng nói (piper) nếu có model, ghi âm 5 giây (ffmpeg).
4. Đóng app, kiểm `%LOCALAPPDATA%\QuangLuuStudio\current\_internal` **vẫn còn** (Task 1). Mở lại được.
Ghi từng mục OK/lỗi kèm log `%APPDATA%\QuangLuuStudio\logs\`.

- [ ] **Step 6: Defender — câu 6**

Run: `powershell.exe -NoProfile -Command '& "$env:ProgramFiles\Windows Defender\MpCmdRun.exe" -Scan -ScanType 3 -File "$env:LOCALAPPDATA\QuangLuuStudio" -DisableRemediation'`
Expected: `found no threats`. Ghi kết quả; thêm `Get-MpThreatDetection | Select -First 5` nếu có phát hiện.

- [ ] **Step 7: Gỡ bản spike**

Gỡ "QuangLuuStudio" qua Settings → Apps. Kiểm `%APPDATA%\QuangLuuStudio` (dữ liệu) **còn nguyên**.

- [ ] **Step 8: Hoàn tác thay đổi tạm**

Run: `git checkout main.py && git status --short`
Expected: không còn thay đổi `main.py`; Task 1 đã commit nên vẫn còn. `spike_onedir.spec`, `dist\`, `.venv\spike_velo\` không hiện (gitignored).

---

### Task 5: Quyết định đi tiếp hay dừng

- [ ] **Step 1: Đối chiếu câu 1–4**

Nếu **bất kỳ** câu nào trong 1–4 có kết quả "không" (onedir hỏng chức năng không sửa được trong 1 giờ; Setup đòi UAC; hook/FIRSTRUN không nhận; tải ngầm / áp dụng khi thoát / tự áp dụng lần mở sau không chạy): **DỪNG**, viết Task 6 với kết luận "chặn", báo người dùng, không viết Kế hoạch 4.

---

### Task 6: Ghi kết quả

**Files:**
- Create: `docs/superpowers/specs/2026-10-12-velopack-spike-findings.md`

- [ ] **Step 1: Viết file kết quả theo khung**

```markdown
# Kết quả spike Velopack (2026-10-12)

| # | Câu hỏi | Kết quả | Bằng chứng |
|---|---------|---------|-----------|
| 1 | Onedir app thật chạy đủ (audio, numba, ffmpeg, piper, ghi âm, SFX) | <OK/lỗi> | <log, mã thoát> |
| 2 | Setup cài %LocalAppData% không UAC | | |
| 3 | Hook --veloapp-* + VELOPACK_FIRSTRUN | | <giá trị biến, tham số callback> |
| 4a | Tải ngầm khi app chạy | | |
| 4b | wait_exit_then_apply_updates im lặng khi thoát | | |
| 4c | Delta | | <kích thước delta vs full> |
| 4d | Tắt ngang → tự áp dụng lần mở sau | | <thời gian chậm thêm> |
| 5 | Gói tự tải không có Zone.Identifier | | |
| 6 | Defender | | |

## Số đo
- Phiên bản thật: velopack (pip) = …, vpk = …, .NET SDK = …
- Kích thước: dist onedir …, full.nupkg …, Setup.exe …
- Khởi động (trung vị 3 lần): onefile … s, onedir … s
- Mạng mất: báo lỗi sau … s

## Định dạng releases.win.json (một phần tử Assets thật)
<dán JSON>

## Tên file vpk sinh ra
<danh sách>

## Lệnh chép tài nguyên cạnh exe trước khi pack
<danh sách>

## Kết luận
<ĐI TIẾP / CHẶN> — <lý do; các điều chỉnh cần đưa vào Kế hoạch 4>
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-10-12-velopack-spike-findings.md
git commit -m "docs(spike): kết quả kiểm chứng Velopack với app onedir"
```

- [ ] **Step 3: Dọn dẹp**

Xoá `.venv\spike_velo\`, `spike_onedir.spec`, `dist\QuangLuuStudio\`, `build\` (thư mục làm việc PyInstaller) và `%LOCALAPPDATA%\QLSSpike_log.txt`. Không xoá `%APPDATA%\QuangLuuStudio`.
