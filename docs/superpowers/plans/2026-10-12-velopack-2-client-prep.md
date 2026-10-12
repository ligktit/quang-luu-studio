# Velopack — Kế hoạch 2/4: Chuẩn bị phía app (không phụ thuộc Velopack)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** App không còn ghi vào thư mục cài, tự làm các việc sau-cài (thay `[Code]` của Inno) ở lần chạy đầu và dọn được bản cũ trong Program Files — tất cả **chạy được trước khi có Velopack** và nằm im trên bản Inno hiện tại.

**Architecture:** `core/config.py` đọc thêm lớp `app_config_overrides.json` trong DATA_DIR và `save()` chỉ ghi phần khác biệt vào đó. `core/first_run.py` gom logic thuần (không Qt) của bước sau-cài; `ui/dialogs/first_run_dialog.py` chạy chúng trong luồng nền với giao diện tiếng Việt; `main.py` gọi hộp thoại **chỉ khi** app chạy từ bản cài Velopack (có `Update.exe` ở thư mục cha). `tools/don_ban_cu.ps1` dọn bản Inno cũ, dùng chung cho app và bộ cài cầu nối (Kế hoạch 4).

**Tech Stack:** Python 3.13, PySide6, pytest + pytest-qt, PowerShell 5.1, winreg.

**Spec:** `docs/superpowers/specs/2026-10-12-velopack-installer-design.md` (mục 2 "Quy tắc: không ghi gì vào current\", "Lần chạy đầu tiên"; mục 4 "Đường 2").

**Phụ thuộc:** Kế hoạch 1 Task 1 (`core/frozen_paths.py`) đã commit. Không phụ thuộc kết quả spike.

## Global Constraints

- Chạy test client bằng venv Windows: `cmd.exe /c "D:\Projects\quang-luu-studio\.venv\Scripts\python.exe -m pytest <đường dẫn Windows> -q -p no:cacheprovider --rootdir=D:\Projects\quang-luu-studio"`. Sau khi chạy suite: `git checkout app_config.json` và đặt lại `settings.json` (xem memory test-env).
- Mọi chuỗi giao diện bằng tiếng Việt có dấu; tên hàm/biến mới theo kiểu đang dùng trong repo (tiếng Việt không dấu cho hàm nghiệp vụ là chấp nhận được, ví dụ `DawMacDinh` → `default_daw` giữ tiếng Anh như các helper khác trong `core/`).
- JSON ghi ra: UTF-8 **không BOM** (`atomic_write_json`). JSON đọc vào: chấp nhận BOM (`utf-8-sig`) — script PowerShell cũ từng ghi BOM.
- File `.ps1` có ký tự tiếng Việt: lưu UTF-8 **có BOM** (PowerShell 5.1 đọc sai nếu không có) — giống `setup_midi_ports.ps1`.
- AppId cũ: `{B8F3E2A1-5D6C-4E7F-9A0B-1C2D3E4F5A6B}`; khoá gỡ cài đặt cũ: `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{B8F3E2A1-5D6C-4E7F-9A0B-1C2D3E4F5A6B}_is1` (view 64-bit).
- Tên file overrides: `app_config_overrides.json` trong DATA_DIR.
- Mã thoát `setup_all.bat /auto` là tổng bit: 1 thiếu cổng MIDI, 2 chép script Cubase lỗi, 4 Cubase đang chạy.

## Review Focus

- **`app_config_overrides.json` hỏng hoặc có BOM** → app vẫn chạy bằng mặc định + bản đóng gói, ghi cảnh báo log, không mất cấu hình đóng gói. (Task 1, `test_overrides_hong_van_chay`, `test_overrides_co_bom_van_doc`.)
- **Lần chạy đầu bị tắt ngang** (đóng hộp thoại, mất điện) trước khi xong → lần mở sau chạy lại; cờ `first_run_done` chỉ ghi khi đi hết luồng. (Task 6, `test_dong_ngang_khong_danh_dau_xong`.)
- **`setup_all.bat` không chạy được / treo** (thiếu file, winget treo không mạng) → có timeout, hộp thoại báo việc cần làm tay và vẫn cho đi tiếp. (Task 4 `test_setup_all_timeout_tra_am_mot`, Task 6 `test_setup_all_loi_van_cho_tiep_tuc`.)
- **`app_config.json` cũ trong Program Files đã sửa tay, có BOM, chứa cả khoá calibration** (máy khách 1: `midi_cc.tone_music=55`) → `midi_cc` sang overrides, khoá calibration sang `calibration_overrides.json`, không đè giá trị người dùng đã có. (Task 4 `test_migrate_cau_hinh_cu_*`.)
- **Bản cũ do người dùng chọn thư mục cài khác / thư mục sai** → script dọn chỉ xoá thư mục khi thấy `QuangLuuStudio.exe` hoặc `unins000.exe` bên trong; không bao giờ đụng shortcut của bản mới (chỉ xoá trong thư mục shortcut dùng chung, đúng 5 tên cũ). (Task 5 `test_khong_xoa_thu_muc_la`, `test_giu_shortcut_khac`.)

---

### Task 1: `app_config.json` thêm lớp overrides người dùng; `save()` chỉ ghi phần khác biệt

**Files:**
- Modify: `core/config.py` (hằng số đường dẫn ~dòng 76-81; `AppConfig.load` ~dòng 278-307; `AppConfig.save` ~dòng 535-547; docstring đầu file dòng 6-12)
- Modify: `tests/core/test_config.py:84-92` (test save cũ ghi vào app_config.json)
- Modify: `.gitignore` (khối "Data / cache")
- Test: `tests/core/test_config_overrides.py`

**Interfaces:**
- Produces:
  - `core.config.APP_CONFIG_OVERRIDES_FILE: str` = `os.path.join(DATA_DIR, "app_config_overrides.json")`
  - `core.config.read_json_dict(path: str) -> dict` — đọc JSON (chấp nhận BOM); không phải dict → `{}`; lỗi đọc/parse → ném ngoại lệ.
  - `core.config.merge_config(base: dict, extra: dict) -> None` — gộp tại chỗ, dict con gộp nông (`update`).
  - `core.config.config_diff(base: dict, data: dict) -> dict` — phần của `data` khác `base`; dict con chỉ giữ khoá con khác.
  - `AppConfig._load_base() -> dict` — mặc định + `app_config.json` đóng gói (không có lớp người dùng).
  - `AppConfig._get_overrides_path() -> str`

- [ ] **Step 1: Viết test thất bại**

```python
# tests/core/test_config_overrides.py
"""app_config.json cạnh exe chỉ là MẶC ĐỊNH; phần người dùng đổi nằm ở
DATA_DIR/app_config_overrides.json (thư mục cài bị thay mỗi lần cập nhật)."""
import json
from unittest.mock import patch

import pytest

import core.config as cfg
from core.config import AppConfig, config_diff


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    bundled = tmp_path / "app" / "app_config.json"
    bundled.parent.mkdir()
    bundled.write_text(json.dumps({"midi_port_name": "Goc", "midi_cc": {"tone_music": 20}}),
                       encoding="utf-8")
    monkeypatch.setattr(cfg, "APP_CONFIG_OVERRIDES_FILE", str(tmp_path / "ov.json"))
    monkeypatch.setattr(cfg, "ACCESSIBILITY_OVERRIDES_FILE", str(tmp_path / "a11y.json"))
    monkeypatch.setattr(cfg, "CALIBRATION_OVERRIDES_FILE", str(tmp_path / "cal.json"))
    AppConfig._data = None
    with patch.object(AppConfig, "_get_config_path", return_value=str(bundled)):
        yield tmp_path
    AppConfig._data = None


def test_overrides_de_len_ban_dong_goi(_iso):
    (_iso / "ov.json").write_text(json.dumps({"midi_cc": {"tone_music": 55}}), encoding="utf-8")
    data = AppConfig.load()
    assert data["midi_cc"]["tone_music"] == 55
    assert data["midi_port_name"] == "Goc"
    # khoá con khác của midi_cc vẫn lấy từ mặc định
    assert "tone_auto" in data["midi_cc"]


def test_save_chi_ghi_phan_khac_vao_overrides(_iso):
    AppConfig.update("youtube_cookie_browser", "edge")
    AppConfig.update("midi_cc", {"tone_music": 21})
    assert AppConfig.save() is True
    saved = json.loads((_iso / "ov.json").read_text(encoding="utf-8"))
    assert saved == {"youtube_cookie_browser": "edge", "midi_cc": {"tone_music": 21}}
    # bản đóng gói không bị đụng
    bundled = json.loads((_iso / "app" / "app_config.json").read_text(encoding="utf-8"))
    assert bundled == {"midi_port_name": "Goc", "midi_cc": {"tone_music": 20}}


def test_dat_lai_gia_tri_goc_thi_khoa_bien_khoi_overrides(_iso):
    AppConfig.update("youtube_cookie_browser", "edge")
    AppConfig.save()
    AppConfig.update("youtube_cookie_browser", cfg._DEFAULT_APP_CONFIG["youtube_cookie_browser"])
    AppConfig.save()
    saved = json.loads((_iso / "ov.json").read_text(encoding="utf-8"))
    assert "youtube_cookie_browser" not in saved


def test_save_khong_ghi_khoa_calibration(_iso):
    AppConfig.update("scale_midi_map", {"Major": 99})
    AppConfig.save()
    saved = json.loads((_iso / "ov.json").read_text(encoding="utf-8"))
    assert "scale_midi_map" not in saved


def test_overrides_hong_van_chay(_iso):
    (_iso / "ov.json").write_text("{khong phai json", encoding="utf-8")
    data = AppConfig.load()
    assert data["midi_port_name"] == "Goc"
    assert data["midi_cc"]["tone_music"] == 20


def test_overrides_co_bom_van_doc(_iso):
    (_iso / "ov.json").write_bytes(b"\xef\xbb\xbf" + json.dumps({"midi_port_name": "X"}).encode())
    assert AppConfig.load()["midi_port_name"] == "X"


def test_config_diff_dict_long_nhau():
    base = {"a": 1, "d": {"x": 1, "y": 2}, "e": [1]}
    data = {"a": 1, "d": {"x": 1, "y": 3}, "e": [1, 2], "moi": True}
    assert config_diff(base, data) == {"d": {"y": 3}, "e": [1, 2], "moi": True}
```

- [ ] **Step 2: Chạy test, xác nhận thất bại**

Run: `cmd.exe /c "D:\Projects\quang-luu-studio\.venv\Scripts\python.exe -m pytest D:\Projects\quang-luu-studio\tests\core\test_config_overrides.py -q -p no:cacheprovider --rootdir=D:\Projects\quang-luu-studio"`
Expected: FAIL — `ImportError: cannot import name 'config_diff'`.

- [ ] **Step 3: Viết code**

Trong `core/config.py`, ngay sau dòng `CALIBRATION_OVERRIDES_FILE = ...` (dòng 81) thêm:

```python
# Cấu hình người dùng đổi (cookie, cổng MIDI, midi_cc...) → DATA_DIR. app_config.json
# cạnh exe chỉ là MẶC ĐỊNH: bản cài Velopack thay cả thư mục cài mỗi lần cập nhật,
# và trong Program Files thì không ghi được. save() chỉ ghi PHẦN KHÁC so với mặc
# định + bản đóng gói, để bản cập nhật sau đổi mặc định vẫn có tác dụng.
APP_CONFIG_OVERRIDES_FILE = os.path.join(DATA_DIR, "app_config_overrides.json")
```

Ngay **trước** `class AppConfig:` thêm:

```python
_MISSING = object()


def read_json_dict(path):
    """Đọc file JSON là dict. Chấp nhận BOM (script PowerShell cũ từng ghi BOM).
    Không phải dict → {}. Lỗi đọc/parse → ném ngoại lệ cho phía gọi xử lý."""
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def merge_config(base, extra):
    """Gộp extra vào base tại chỗ; dict con gộp nông (giống cách load() vẫn làm)."""
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key].update(value)
        else:
            base[key] = value


def config_diff(base, data):
    """Phần của data khác base. Dict con chỉ giữ các khoá con khác — khớp với
    merge_config (gộp nông), nên merge_config(base, config_diff(base, data)) == data
    trên các khoá của data."""
    out = {}
    for key, value in data.items():
        old = base.get(key, _MISSING)
        if old == value:
            continue
        if isinstance(value, dict) and isinstance(old, dict):
            sub = {k: v for k, v in value.items() if old.get(k, _MISSING) != v}
            if sub:
                out[key] = sub
        else:
            out[key] = value
    return out
```

Trong `class AppConfig`, ngay sau `_get_config_path` thêm:

```python
    @classmethod
    def _get_overrides_path(cls):
        """Phần người dùng đổi — DATA_DIR (ghi được, sống qua các lần cập nhật)."""
        return APP_CONFIG_OVERRIDES_FILE

    @classmethod
    def _load_base(cls):
        """Mặc định + app_config.json đóng gói, CHƯA có lớp người dùng."""
        import logging
        log = logging.getLogger("config")
        data = copy.deepcopy(_DEFAULT_APP_CONFIG)
        config_path = cls._get_config_path()
        if os.path.exists(config_path):
            try:
                merge_config(data, read_json_dict(config_path))
                log.info(f"App config loaded: {config_path}")
            except Exception as e:
                log.warning(f"Lỗi đọc {APP_CONFIG_FILE}: {e} — dùng giá trị mặc định")
        else:
            log.info(f"{APP_CONFIG_FILE} không tìm thấy — dùng giá trị mặc định")
        return data
```

Trong `AppConfig.load`, thay toàn bộ khối từ `cls._data = copy.deepcopy(_DEFAULT_APP_CONFIG)` tới hết nhánh `else: ... không tìm thấy — dùng giá trị mặc định")` (trước comment `# Merge accessibility overrides`) bằng:

```python
            cls._data = cls._load_base()

            # Lớp người dùng: app_config_overrides.json (DATA_DIR). Hỏng thì bỏ qua
            # lớp này, vẫn chạy bằng mặc định + bản đóng gói.
            try:
                ov_path = cls._get_overrides_path()
                if os.path.exists(ov_path):
                    merge_config(cls._data, read_json_dict(ov_path))
            except Exception as e:
                import logging
                logging.getLogger("config").warning(f"Lỗi đọc app_config_overrides.json: {e} — bỏ qua")
```

Thay thân `AppConfig.save` bằng:

```python
    @classmethod
    def save(cls):
        """Ghi PHẦN NGƯỜI DÙNG ĐỔI ra DATA_DIR/app_config_overrides.json.

        Không ghi app_config.json cạnh exe (thư mục cài có thể read-only hoặc bị
        thay khi cập nhật). Khoá calibration có file riêng (set_calibration) nên
        không ghi ở đây — ghi cả hai chỗ thì xoá cân chỉnh sẽ không có tác dụng.
        """
        with cls._lock:
            if cls._data is None:
                return False
            diff = config_diff(cls._load_base(), cls._data)
            for key in CALIBRATION_KEYS:
                diff.pop(key, None)
            path = cls._get_overrides_path()
            try:
                atomic_write_json(path, diff)
                print(f"App config overrides saved: {path}")
                return True
            except Exception as e:
                print(f"Lỗi ghi app_config_overrides.json: {e}")
                return False
```

Sửa docstring đầu file (dòng 6-12) thành:

```python
File path convention:
  - USER DATA (writable): %APPDATA%/QuangLuuStudio/
    → settings.json, saved_songs.json, activation.json,
      tone_cache.json, manual_timelines.json,
      app_config_overrides.json (phần người dùng đổi của app_config)
  - APP CONFIG MẶC ĐỊNH (read-only): next to EXE → app_config.json
  - RECORDINGS: Documents/QuangLuuStudio/
```

Sửa `tests/core/test_config.py:84-92` (`test_appconfig_update_and_save`) thành:

```python
def test_appconfig_update_and_save(tmp_path, monkeypatch):
    # C-11: `update(key, value)` + `save()` — ghi vào overrides, không vào app_config.json
    import core.config as cfg
    config_file = tmp_path / "app_config.json"
    ov_file = tmp_path / "app_config_overrides.json"
    monkeypatch.setattr(cfg, "APP_CONFIG_OVERRIDES_FILE", str(ov_file))
    with patch("core.config.AppConfig._get_config_path", return_value=str(config_file)):
        AppConfig.update("midi_port_name", "NewPort")
        AppConfig.save()

        saved_data = json.loads(ov_file.read_text(encoding="utf-8"))
        assert saved_data["midi_port_name"] == "NewPort"
        assert not config_file.exists()
```

Trong `.gitignore`, khối `# Data / cache (user-specific)`, thêm dòng `app_config_overrides.json` ngay dưới `calibration_overrides.json`.

- [ ] **Step 4: Chạy test, xác nhận qua**

Run: `cmd.exe /c "D:\Projects\quang-luu-studio\.venv\Scripts\python.exe -m pytest D:\Projects\quang-luu-studio\tests\core\test_config_overrides.py D:\Projects\quang-luu-studio\tests\core\test_config.py D:\Projects\quang-luu-studio\tests\core\test_config_daw_calibration.py -q -p no:cacheprovider --rootdir=D:\Projects\quang-luu-studio"`
Expected: tất cả PASS. Sau đó `git checkout app_config.json` nếu `git status` báo đổi.

- [ ] **Step 5: Commit**

```bash
git add core/config.py tests/core/test_config_overrides.py tests/core/test_config.py .gitignore
git commit -m "feat(config): phần người dùng đổi của app_config lưu ở app_config_overrides.json (DATA_DIR), save() chỉ ghi phần khác biệt"
```

---

### Task 2: Các script cookie / sửa PO token ghi vào overrides

**Files:**
- Modify: `configure_youtube_cookies.bat:5-14` và khối `:apply`
- Modify: `tools/export_youtube_cookies.bat:35` và khối `[3/3]` (~dòng 208-221)
- Modify: `tools/chan_doan/QLS_SuaPOToken.ps1` hàm `Set-AppConfigValues` (~dòng 814-860)

**Interfaces:**
- Consumes: định dạng `app_config_overrides.json` của Task 1 (dict JSON phẳng/lồng một cấp, UTF-8 không BOM).

- [ ] **Step 1: `configure_youtube_cookies.bat` — đổi đích và tự tạo file**

Thay dòng 6 và khối kiểm tra tồn tại (dòng 9-14) bằng:

```bat
set "QLS_DATA=%APPDATA%\QuangLuuStudio"
set "APP_CONFIG=%QLS_DATA%\app_config_overrides.json"
set "INTERACTIVE=1"

REM Phan nguoi dung doi cua app_config nam o %APPDATA% (thu muc cai co the
REM read-only va bi thay moi lan cap nhat). Chua co thi tao file rong.
if not exist "%QLS_DATA%" mkdir "%QLS_DATA%"
if not exist "%APP_CONFIG%" (
    powershell -NoProfile -Command "[IO.File]::WriteAllText('%APP_CONFIG%', '{}', (New-Object Text.UTF8Encoding($false)))"
)
```

Trong khối `:apply` đổi `echo [INFO] Dang cap nhat app_config.json...` thành `echo [INFO] Dang cap nhat app_config_overrides.json...` và `echo [ERROR] Cap nhat app_config.json that bai.` thành `echo [ERROR] Cap nhat app_config_overrides.json that bai.`. Lệnh PowerShell giữ nguyên (đã ghi không BOM, đã `Add-Member` khi thiếu khoá — chạy được trên `{}`). Sửa `Get-Content -Raw -LiteralPath $path` thành `[IO.File]::ReadAllText($path).TrimStart([char]0xFEFF)` để chịu được BOM.

- [ ] **Step 2: `tools/export_youtube_cookies.bat`**

Thay dòng 35 bằng `set "APP_CONFIG=%APPDATA_DIR%\app_config_overrides.json"`. Thay `if exist "%APP_CONFIG%" (` ... `) else ( ... bo qua cap nhat config )` (khối `[3/3]`) bằng:

```bat
:: Phan nguoi dung doi cua app_config nam o %APPDATA% - chua co thi tao rong
if not exist "%APP_CONFIG%" powershell -NoProfile -Command "[IO.File]::WriteAllText('%APP_CONFIG%', '{}', (New-Object Text.UTF8Encoding($false)))"
echo [3/3] Cap nhat app_config_overrides.json...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$p = [IO.Path]::GetFullPath('%APP_CONFIG%');" ^
    "$c = [IO.File]::ReadAllText($p).TrimStart([char]0xFEFF) | ConvertFrom-Json;" ^
    "if (-not $c.PSObject.Properties['youtube_cookie_file']) { $c | Add-Member youtube_cookie_file '' };" ^
    "if (-not $c.PSObject.Properties['youtube_cookie_browser']) { $c | Add-Member youtube_cookie_browser 'none' };" ^
    "$c.youtube_cookie_file = '%COOKIE_OUT%';" ^
    "$c.youtube_cookie_browser = 'none';" ^
    "[IO.File]::WriteAllText($p, ($c | ConvertTo-Json -Depth 20) + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)));" ^
    "Write-Host '[OK] app_config_overrides.json da duoc cap nhat'"
```

(`APPDATA_DIR` đã được tạo trước đó trong script vì `COOKIE_OUT` nằm trong nó — kiểm bằng `grep -n "mkdir" tools/export_youtube_cookies.bat`; nếu chưa có `mkdir "%APPDATA_DIR%"` trước bước 3/3 thì thêm ngay trước dòng `if not exist "%APP_CONFIG%"`.)

- [ ] **Step 3: `QLS_SuaPOToken.ps1` — `Set-AppConfigValues`**

Trong hàm `Set-AppConfigValues`: đổi `$cfgPath = Join-Path $AppRoot "app_config.json"` thành `$cfgPath = Join-Path $DataDir "app_config_overrides.json"`; thêm `New-Item -ItemType Directory -Path $DataDir -Force | Out-Null` ngay sau dòng đó. Đổi mọi chuỗi hiển thị `app_config.json` trong hàm thành `app_config_overrides.json` và tên file sao lưu thành `app_config_overrides.json`. Giữ nguyên nhánh `catch [System.UnauthorizedAccessException]` (vô hại; DATA_DIR luôn ghi được). Lưu file giữ BOM (kiểm `head -c3 | xxd -p` = `efbbbf`).

- [ ] **Step 4: Kiểm tay trên máy dev**

```
cmd.exe /c "cd /d D:\Projects\quang-luu-studio && configure_youtube_cookies.bat --edge Default"
powershell.exe -NoProfile -Command 'Get-Content $env:APPDATA\QuangLuuStudio\app_config_overrides.json; Format-Hex -Path $env:APPDATA\QuangLuuStudio\app_config_overrides.json -Count 3'
```
Expected: JSON có `"youtube_cookie_browser": "edge"`, `"youtube_cookie_profile": "Default"`, `"youtube_cookie_file": ""`; 3 byte đầu **không** là `EF BB BF`. Chạy lại lệnh lần hai → vẫn đúng (không nhân đôi khoá). Sau khi kiểm: xoá `%APPDATA%\QuangLuuStudio\app_config_overrides.json` nếu máy dev không dùng nó.

Kiểm `QLS_SuaPOToken.ps1` cú pháp: `powershell.exe -NoProfile -Command '$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile("D:\Projects\quang-luu-studio\tools\chan_doan\QLS_SuaPOToken.ps1",[ref]$null,[ref]$e); $e.Count'` → `0`.

- [ ] **Step 5: Commit**

```bash
git add configure_youtube_cookies.bat tools/export_youtube_cookies.bat tools/chan_doan/QLS_SuaPOToken.ps1
git commit -m "fix(scripts): cấu hình cookie / PO token ghi vào %APPDATA%\\QuangLuuStudio\\app_config_overrides.json thay vì thư mục cài"
```

---

### Task 3: Đường dẫn SFX mặc định không còn trỏ vào thư mục tạm cũ

**Files:**
- Modify: `ui/components/sfx_button_area.py:758-762` (nạp dữ liệu ban đầu) và `:791-799` (`_inject_default_paths`)
- Test: `tests/ui/test_sfx_area.py` (thêm test)

**Interfaces:**
- Produces: `SfxButtonArea._inject_default_paths(items: list) -> list` — điền/đường dẫn lại cho nút mặc định (`sfx_001..003`) khi `file_path` rỗng **hoặc** trỏ tới file không còn tồn tại có đúng tên file mặc định.

- [ ] **Step 1: Viết test thất bại** — thêm cuối `tests/ui/test_sfx_area.py`:

```python
def test_duong_dan_mac_dinh_cu_trong_thu_muc_tam_duoc_tro_lai(qapp, qtbot, tmp_path):
    """settings.json từng lưu %TEMP%\\_MEIxxxx\\sfx\\sfx_applause.wav — thư mục đó
    mất sau mỗi lần thoát; lần mở sau phải trỏ lại file đóng gói."""
    from ui.components.sfx_button_area import SfxButtonArea
    sfx_dir = tmp_path / "app" / "sfx"
    sfx_dir.mkdir(parents=True)
    (sfx_dir / "sfx_applause.wav").write_bytes(b"RIFF")
    stale = str(tmp_path / "_MEI999" / "sfx" / "sfx_applause.wav")
    user_file = tmp_path / "rieng.wav"
    user_file.write_bytes(b"RIFF")
    a = SfxButtonArea(sfx_list=[
        {"id": "sfx_002", "label": "👏", "name": "Vỗ tay", "file_path": stale, "color": "#14B8A6"},
        {"id": "sfx_001", "label": "😂", "name": "Cười", "file_path": str(user_file), "color": "#F97316"},
    ], app_dir=str(tmp_path / "app"))
    qtbot.addWidget(a)
    paths = {d["id"]: d["file_path"] for d in a.get_sfx_list()}
    assert paths["sfx_002"] == str(sfx_dir / "sfx_applause.wav")
    # file người dùng tự chọn (vẫn tồn tại) giữ nguyên
    assert paths["sfx_001"] == str(user_file)


def test_file_nguoi_dung_mat_khong_bi_doi_sang_mac_dinh(qapp, qtbot, tmp_path):
    from ui.components.sfx_button_area import SfxButtonArea
    sfx_dir = tmp_path / "app" / "sfx"
    sfx_dir.mkdir(parents=True)
    (sfx_dir / "sfx_laugh.wav").write_bytes(b"RIFF")
    gone = str(tmp_path / "nhac_rieng" / "cuoi_to.wav")   # tên KHÁC tên mặc định
    a = SfxButtonArea(sfx_list=[
        {"id": "sfx_001", "label": "😂", "name": "Cười", "file_path": gone, "color": "#F97316"},
    ], app_dir=str(tmp_path / "app"))
    qtbot.addWidget(a)
    assert a.get_sfx_list()[0]["file_path"] == gone
```

- [ ] **Step 2: Chạy test, xác nhận thất bại**

Run: `cmd.exe /c "D:\Projects\quang-luu-studio\.venv\Scripts\python.exe -m pytest D:\Projects\quang-luu-studio\tests\ui\test_sfx_area.py -q -p no:cacheprovider --rootdir=D:\Projects\quang-luu-studio"`
Expected: `test_duong_dan_mac_dinh_cu_trong_thu_muc_tam_duoc_tro_lai` FAIL (đường dẫn vẫn là `_MEI999`); test thứ hai PASS.

- [ ] **Step 3: Viết code**

Dòng 758-762 thành:

```python
        # Load initial data — nút mặc định luôn được trỏ lại file đóng gói
        # (settings.json của bản onefile cũ lưu đường dẫn %TEMP%\_MEIxxxx đã mất).
        initial = sfx_list if sfx_list is not None else []
        if not initial:
            initial = list(self._DEFAULT_SFX)
        initial = self._inject_default_paths(initial)
```

Thay `_inject_default_paths` bằng:

```python
    def _inject_default_paths(self, items: list) -> list:
        """Điền file đóng gói cho nút mặc định khi file_path rỗng, hoặc khi nó trỏ
        tới file MẶC ĐỊNH ở chỗ cũ không còn tồn tại (thư mục _MEI tạm của bản
        onefile). File người dùng tự chọn (tên khác) thì không đụng."""
        name_map = {"sfx_001": "sfx_laugh.wav", "sfx_002": "sfx_applause.wav", "sfx_003": "sfx_cheer.wav"}
        out = []
        for item in items:
            item = dict(item)
            default_name = name_map.get(item.get("id"))
            fp = item.get("file_path") or ""
            stale_default = bool(fp) and not os.path.exists(fp) and os.path.basename(fp) == default_name
            if default_name and (not fp or stale_default):
                candidate = os.path.join(self._app_dir, "sfx", default_name)
                if os.path.exists(candidate):
                    item["file_path"] = candidate
            out.append(item)
        return out
```

(`dict(item)` để không sửa ngược list `_DEFAULT_SFX` của lớp.)

- [ ] **Step 4: Chạy test, xác nhận qua**

Run: lệnh Step 2 và thêm `D:\Projects\quang-luu-studio\tests\ui\test_sfx_dashboard.py`. Expected: tất cả PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/components/sfx_button_area.py tests/ui/test_sfx_area.py
git commit -m "fix(sfx): nút SFX mặc định trỏ lại file đóng gói khi settings còn lưu đường dẫn _MEI tạm đã mất"
```

---

### Task 4: `core/first_run.py` — logic thuần của bước sau-cài

**Files:**
- Create: `core/first_run.py`
- Test: `tests/core/test_first_run.py`

**Interfaces:**
- Consumes: `core.config.read_json_dict`, `config_diff`, `merge_config`, `AppConfig._load_base`, `APP_CONFIG_OVERRIDES_FILE`, `CALIBRATION_OVERRIDES_FILE`, `CALIBRATION_KEYS`, `atomic_write_json` (từ `core.utils`).
- Produces (dùng ở Task 6 và Kế hoạch 4):
  - `FIRST_RUN_KEY = "first_run_done"`; `is_done(settings: dict) -> bool`; `mark_done(settings: dict) -> dict`
  - `is_velopack_install(app_dir: str) -> bool` — có `Update.exe` ở thư mục cha của `app_dir`.
  - `default_daw(program_files: str, appdata: str) -> str` — `"cubase"` | `"studio_one"`.
  - `ensure_default_data_files(data_dir: str, daw_kind: str) -> list[str]` — tên file đã tạo.
  - `SETUP_ALL_FAILED = -1`; `run_setup_all(app_dir: str, timeout: float = 300) -> int`
  - `describe_setup_all_code(code: int) -> list[str]`
  - `find_loopmidi(env: dict | None = None) -> str | None`
  - `install_loopmidi_elevated(timeout: float = 600) -> bool`
  - `LEGACY_UNINSTALL_KEY: str`; `find_legacy_install() -> str | None` — `InstallLocation` của bản Inno cũ (chuỗi, có thể rỗng nếu khoá có mà thiếu giá trị); `None` nếu không có khoá.
  - `migrate_legacy_app_config(legacy_dir: str) -> bool`
  - `find_bundled(rel_path: str) -> str | None`
  - `cleanup_legacy_elevated(legacy_dir: str, timeout: float = 300) -> bool`

- [ ] **Step 1: Viết test thất bại**

```python
# tests/core/test_first_run.py
"""Bước sau-cài chạy trong app (thay [Code] của bộ cài Inno)."""
import json
import subprocess
from unittest.mock import patch

import pytest

import core.config as cfg
from core import first_run


# ── cờ + nhận biết bản cài ──
def test_co_first_run():
    s = {}
    assert not first_run.is_done(s)
    assert first_run.is_done(first_run.mark_done(s))


def test_is_velopack_install(tmp_path):
    cur = tmp_path / "QuangLuuStudio" / "current"
    cur.mkdir(parents=True)
    assert not first_run.is_velopack_install(str(cur))
    (tmp_path / "QuangLuuStudio" / "Update.exe").write_bytes(b"MZ")
    assert first_run.is_velopack_install(str(cur))


# ── DAW mặc định (logic DawMacDinh của .iss) ──
@pytest.mark.parametrize("dirs,expected", [
    ([], "studio_one"),
    (["pf/Steinberg/Cubase 13"], "cubase"),
    (["ad/Steinberg/Cubase 12_64"], "cubase"),
    (["pf/Steinberg/Cubase 13", "ad/PreSonus/Studio One 6"], "studio_one"),
    (["pf/Steinberg/Cubase 13", "pf/PreSonus"], "studio_one"),
])
def test_default_daw(tmp_path, dirs, expected):
    for d in dirs:
        (tmp_path / d).mkdir(parents=True)
    assert first_run.default_daw(str(tmp_path / "pf"), str(tmp_path / "ad")) == expected


# ── file mặc định ──
def test_tao_file_mac_dinh_khong_de_file_co_san(tmp_path):
    (tmp_path / "saved_songs.json").write_text('[{"x": 1}]', encoding="utf-8")
    created = first_run.ensure_default_data_files(str(tmp_path), "cubase")
    assert "saved_songs.json" not in created
    assert json.loads((tmp_path / "saved_songs.json").read_text(encoding="utf-8")) == [{"x": 1}]
    settings = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert settings == {"studio_one_path": "", "browser_path": "",
                        "auto_launch_studio_one": False, "daw_kind": "cubase"}
    for name in ("activation.json", "playlists.json", "tone_cache.json", "manual_timelines.json"):
        assert (tmp_path / name).exists()
    assert not (tmp_path / "settings.json").read_bytes().startswith(b"\xef\xbb\xbf")


# ── setup_all.bat ──
def test_setup_all_thieu_file_tra_am_mot(tmp_path):
    assert first_run.run_setup_all(str(tmp_path)) == first_run.SETUP_ALL_FAILED


def test_setup_all_tra_ma_thoat(tmp_path):
    (tmp_path / "setup_all.bat").write_text("@exit /b 5\r\n", encoding="ascii")
    assert first_run.run_setup_all(str(tmp_path)) == 5


def test_setup_all_timeout_tra_am_mot(tmp_path):
    (tmp_path / "setup_all.bat").write_text("@echo x\r\n", encoding="ascii")
    with patch("core.first_run.subprocess.run",
               side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1)):
        assert first_run.run_setup_all(str(tmp_path), timeout=1) == first_run.SETUP_ALL_FAILED


def test_mo_ta_ma_thoat():
    assert first_run.describe_setup_all_code(0) == []
    msgs = first_run.describe_setup_all_code(1 | 4)
    assert len(msgs) == 2 and "loopMIDI" in msgs[0] and "Reload Scripts" in msgs[1]
    assert "setup_all.bat" in first_run.describe_setup_all_code(first_run.SETUP_ALL_FAILED)[0]


# ── loopMIDI ──
def test_find_loopmidi(tmp_path):
    exe = tmp_path / "pf86" / "Tobias Erichsen" / "loopMIDI" / "loopMIDI.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ")
    env = {"ProgramFiles": str(tmp_path / "pf"), "ProgramFiles(x86)": str(tmp_path / "pf86"),
           "LOCALAPPDATA": str(tmp_path / "lad")}
    assert first_run.find_loopmidi(env) == str(exe)
    assert first_run.find_loopmidi({"ProgramFiles": str(tmp_path / "khong")}) is None


def test_cai_loopmidi_khong_co_winget_tra_false():
    with patch("core.first_run.shutil.which", return_value=None):
        assert first_run.install_loopmidi_elevated() is False


# ── bản cũ ──
def test_find_legacy_install_khong_co_khoa():
    with patch("core.first_run._read_uninstall_location", return_value=None):
        assert first_run.find_legacy_install() is None


def test_find_legacy_install_co_khoa():
    with patch("core.first_run._read_uninstall_location", return_value="C:\\Program Files\\QuangLuuStudio\\"):
        assert first_run.find_legacy_install() == "C:\\Program Files\\QuangLuuStudio"


@pytest.fixture
def _cfg_iso(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled.json"
    bundled.write_text(json.dumps({"midi_cc": {"tone_music": 20, "tone_auto": 21}}), encoding="utf-8")
    monkeypatch.setattr(cfg, "APP_CONFIG_OVERRIDES_FILE", str(tmp_path / "ov.json"))
    monkeypatch.setattr(cfg, "CALIBRATION_OVERRIDES_FILE", str(tmp_path / "cal.json"))
    with patch.object(cfg.AppConfig, "_get_config_path", return_value=str(bundled)):
        yield tmp_path


def test_migrate_cau_hinh_cu_midi_cc_va_calibration(_cfg_iso):
    legacy = _cfg_iso / "legacy"
    legacy.mkdir()
    # BOM như bản do script PowerShell cũ ghi
    (legacy / "app_config.json").write_bytes(b"\xef\xbb\xbf" + json.dumps({
        "midi_cc": {"tone_music": 55, "tone_auto": 21},
        "scale_midi_map": {"Major": 10, "Minor": 18},
    }).encode("utf-8"))
    assert first_run.migrate_legacy_app_config(str(legacy)) is True
    ov = json.loads((_cfg_iso / "ov.json").read_text(encoding="utf-8"))
    assert ov == {"midi_cc": {"tone_music": 55}}
    cal = json.loads((_cfg_iso / "cal.json").read_text(encoding="utf-8"))
    # Minor = 18 trùng mặc định → chỉ phần khác (Major) được chuyển; calibration
    # merge nông nên {"Major": 10} là đủ.
    assert cal == {"scale_midi_map": {"Major": 10}}


def test_migrate_cau_hinh_cu_khong_de_gia_tri_da_co(_cfg_iso):
    legacy = _cfg_iso / "legacy"
    legacy.mkdir()
    (legacy / "app_config.json").write_text(json.dumps({"midi_cc": {"tone_music": 55}}), encoding="utf-8")
    (_cfg_iso / "ov.json").write_text(json.dumps({"midi_cc": {"tone_music": 60}}), encoding="utf-8")
    first_run.migrate_legacy_app_config(str(legacy))
    ov = json.loads((_cfg_iso / "ov.json").read_text(encoding="utf-8"))
    assert ov["midi_cc"]["tone_music"] == 60


def test_migrate_cau_hinh_cu_giong_mac_dinh_thi_khong_ghi(_cfg_iso):
    legacy = _cfg_iso / "legacy"
    legacy.mkdir()
    (legacy / "app_config.json").write_text(json.dumps({"midi_cc": {"tone_music": 20}}), encoding="utf-8")
    assert first_run.migrate_legacy_app_config(str(legacy)) is False
    assert not (_cfg_iso / "ov.json").exists()


def test_migrate_cau_hinh_cu_hong_tra_false(_cfg_iso):
    legacy = _cfg_iso / "legacy"
    legacy.mkdir()
    (legacy / "app_config.json").write_text("{hong", encoding="utf-8")
    assert first_run.migrate_legacy_app_config(str(legacy)) is False
```

- [ ] **Step 2: Chạy test, xác nhận thất bại**

Run: `cmd.exe /c "D:\Projects\quang-luu-studio\.venv\Scripts\python.exe -m pytest D:\Projects\quang-luu-studio\tests\core\test_first_run.py -q -p no:cacheprovider --rootdir=D:\Projects\quang-luu-studio"`
Expected: FAIL — `ImportError: cannot import name 'first_run'`.

- [ ] **Step 3: Viết code**

```python
# core/first_run.py
"""Việc phải làm ở lần chạy đầu sau khi cài — thay cho [Code] của bộ cài Inno.

Velopack chỉ cho hook cài đặt 30 giây và không được hiện giao diện, nên các
việc này chạy trong app, sau một hộp thoại (ui/dialogs/first_run_dialog.py).
Module này KHÔNG đụng Qt để test được.
"""
import base64
import glob
import json
import logging
import os
import shutil
import subprocess
import sys

from core import config as _cfg
from core.utils import atomic_write_json

log = logging.getLogger(__name__)

FIRST_RUN_KEY = "first_run_done"
SETUP_ALL_FAILED = -1
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

LEGACY_APP_ID = "{B8F3E2A1-5D6C-4E7F-9A0B-1C2D3E4F5A6B}"
LEGACY_UNINSTALL_KEY = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall" + "\\" + LEGACY_APP_ID + "_is1"
)


# ── Cờ + nhận biết bản cài ───────────────────────────────────────────────────
def is_done(settings):
    return bool((settings or {}).get(FIRST_RUN_KEY))


def mark_done(settings):
    settings[FIRST_RUN_KEY] = True
    return settings


def is_velopack_install(app_dir):
    """Bản cài Velopack: <gốc>\\current\\QuangLuuStudio.exe và <gốc>\\Update.exe."""
    return os.path.isfile(os.path.join(os.path.dirname(os.path.abspath(app_dir)), "Update.exe"))


# ── DAW mặc định + file dữ liệu mặc định ────────────────────────────────────
def _has_dir(pattern):
    return any(os.path.isdir(p) for p in glob.glob(pattern))


def default_daw(program_files, appdata):
    """Máy chỉ có Cubase (không có Studio One) → "cubase"; còn lại "studio_one".
    Cùng logic DawMacDinh của bộ cài Inno (bài học ba máy khách Cubase 2026-10)."""
    has_cubase = (_has_dir(os.path.join(program_files, "Steinberg", "Cubase*"))
                  or _has_dir(os.path.join(appdata, "Steinberg", "Cubase*")))
    has_s1 = (_has_dir(os.path.join(appdata, "PreSonus", "Studio One*"))
              or os.path.isdir(os.path.join(program_files, "PreSonus")))
    return "cubase" if has_cubase and not has_s1 else "studio_one"


def ensure_default_data_files(data_dir, daw_kind):
    """Tạo các file JSON mặc định còn thiếu (không đè file có sẵn). Trả tên file đã tạo."""
    defaults = {
        "activation.json": {"activation_code": "", "activation_date": "", "activation_timestamp": 0},
        "settings.json": {"studio_one_path": "", "browser_path": "",
                          "auto_launch_studio_one": False, "daw_kind": daw_kind},
        "saved_songs.json": [],
        "playlists.json": {},
        "tone_cache.json": {},
        "manual_timelines.json": {},
    }
    os.makedirs(data_dir, exist_ok=True)
    created = []
    for name, value in defaults.items():
        path = os.path.join(data_dir, name)
        if not os.path.exists(path):
            atomic_write_json(path, value)
            created.append(name)
    return created


# ── setup_all.bat /auto ──────────────────────────────────────────────────────
def run_setup_all(app_dir, timeout=300):
    """Chạy setup_all.bat /auto (cổng MIDI, Surface Studio One, script Cubase).
    Trả mã thoát (tổng bit 1/2/4) hoặc SETUP_ALL_FAILED nếu không chạy được/quá giờ."""
    bat = os.path.join(app_dir, "setup_all.bat")
    if not os.path.isfile(bat):
        log.warning("Thiếu %s", bat)
        return SETUP_ALL_FAILED
    try:
        r = subprocess.run(["cmd.exe", "/c", bat, "/auto"], cwd=app_dir, timeout=timeout,
                           creationflags=_NO_WINDOW)
        log.info("setup_all.bat /auto -> %s", r.returncode)
        return r.returncode
    except subprocess.TimeoutExpired:
        log.warning("setup_all.bat /auto quá %ss", timeout)
        return SETUP_ALL_FAILED
    except OSError as e:
        log.warning("Không chạy được setup_all.bat: %s", e)
        return SETUP_ALL_FAILED


def describe_setup_all_code(code):
    """Việc người dùng còn phải làm, theo mã thoát setup_all.bat (rỗng = xong)."""
    if code is None or code == 0:
        return []
    if code < 0:
        return ["Không chạy được bước cài MIDI tự động. Hãy chạy tay setup_all.bat trong thư mục cài đặt."]
    msgs = []
    if code & 1:
        msgs.append("Chưa đủ cổng MIDI ảo (loopMIDI). Chạy setup_all.bat trong thư mục cài đặt để cài có hướng dẫn.")
    if code & 2:
        msgs.append("Chưa chép được script Cubase. Xem log %APPDATA%\\QuangLuuStudio\\logs\\setup_all.txt.")
    if code & 4:
        msgs.append("Cubase đang mở: Studio → MIDI Remote Manager → Scripts → Reload Scripts "
                    "(hoặc mở lại Cubase) để nhận script mới.")
    return msgs


# ── loopMIDI ────────────────────────────────────────────────────────────────
def find_loopmidi(env=None):
    """Đường dẫn loopMIDI.exe (cùng danh sách với setup_midi_ports.ps1) hoặc None."""
    env = os.environ if env is None else env
    cands = []
    for var, sub in (("ProgramFiles", ""), ("ProgramFiles(x86)", ""), ("LOCALAPPDATA", "Programs")):
        base = env.get(var)
        if base:
            cands.append(os.path.join(base, sub, "Tobias Erichsen", "loopMIDI", "loopMIDI.exe"))
    return next((c for c in cands if os.path.isfile(c)), None)


def _run_elevated_ps(inner, timeout):
    """Chạy một lệnh PowerShell có nâng quyền (UAC) và chờ xong. True nếu mã thoát 0.
    Từ chối UAC → Start-Process ném lỗi → mã khác 0."""
    enc = base64.b64encode(inner.encode("utf-16-le")).decode("ascii")
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-EncodedCommand", enc], timeout=timeout, creationflags=_NO_WINDOW)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("Lệnh nâng quyền lỗi: %s", e)
        return False


def install_loopmidi_elevated(timeout=600):
    """Cài loopMIDI bằng winget có nâng quyền (loopMIDI cài cho cả máy). True nếu sau đó tìm thấy."""
    if shutil.which("winget") is None:
        return False
    inner = ("$p = Start-Process winget -Verb RunAs -Wait -PassThru -WindowStyle Hidden -ArgumentList "
             "'install --id TobiasErichsen.loopMIDI --exact --silent "
             "--accept-package-agreements --accept-source-agreements'; exit $p.ExitCode")
    _run_elevated_ps(inner, timeout)
    return find_loopmidi() is not None


# ── Bản cài Inno cũ (Program Files) ─────────────────────────────────────────
def _read_uninstall_location():
    """InstallLocation của bản Inno cũ trong HKLM (view 64 rồi 32), "" nếu khoá có mà thiếu
    giá trị, None nếu không có khoá."""
    try:
        import winreg
    except ImportError:
        return None
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, LEGACY_UNINSTALL_KEY, 0,
                                winreg.KEY_READ | view) as k:
                try:
                    return str(winreg.QueryValueEx(k, "InstallLocation")[0])
                except OSError:
                    return ""
        except OSError:
            continue
    return None


def find_legacy_install():
    loc = _read_uninstall_location()
    if loc is None:
        return None
    return loc.rstrip("\\/")


def migrate_legacy_app_config(legacy_dir):
    """Gộp phần khác biệt của <legacy_dir>\\app_config.json (so với mặc định + bản
    đóng gói hiện tại) vào lớp người dùng: khoá calibration → calibration_overrides.json,
    còn lại → app_config_overrides.json. Giá trị đã có ở đích được GIỮ. True nếu có ghi."""
    path = os.path.join(legacy_dir, "app_config.json")
    if not os.path.isfile(path):
        return False
    try:
        old = _cfg.read_json_dict(path)
    except Exception as e:
        log.warning("app_config.json cũ hỏng, bỏ qua: %s", e)
        return False
    diff = _cfg.config_diff(_cfg.AppConfig._load_base(), old)
    cal = {k: diff.pop(k) for k in list(diff) if k in _cfg.CALIBRATION_KEYS}
    wrote = False
    for part, dest in ((diff, _cfg.APP_CONFIG_OVERRIDES_FILE), (cal, _cfg.CALIBRATION_OVERRIDES_FILE)):
        if not part:
            continue
        existing = {}
        if os.path.exists(dest):
            try:
                existing = _cfg.read_json_dict(dest)
            except Exception:
                existing = {}
        merged = dict(part)
        _cfg.merge_config(merged, existing)   # giá trị đã có ở đích thắng
        atomic_write_json(dest, merged)
        wrote = True
    if wrote:
        _cfg.AppConfig._data = None   # nạp lại lần get() sau
    return wrote


def find_bundled(rel_path):
    """File đóng gói theo app: _MEIPASS (onefile/onedir) rồi thư mục exe/gốc dự án."""
    roots = [getattr(sys, "_MEIPASS", None), _cfg.APP_DIR]
    for root in roots:
        if root:
            p = os.path.join(root, rel_path)
            if os.path.isfile(p):
                return p
    return None


def cleanup_legacy_elevated(legacy_dir, timeout=300):
    """Chạy tools/don_ban_cu.ps1 có nâng quyền để xoá bản Inno cũ. True nếu xong."""
    script = find_bundled(os.path.join("tools", "don_ban_cu.ps1"))
    if script is None:
        log.warning("Thiếu tools/don_ban_cu.ps1")
        return False
    q = lambda s: s.replace("'", "''")  # noqa: E731 — trích dẫn chuỗi PowerShell
    inner = ("$p = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -WindowStyle Hidden "
             "-ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',"
             f"'\"{q(script)}\"','-LegacyDir','\"{q(legacy_dir)}\"'); exit $p.ExitCode")
    return _run_elevated_ps(inner, timeout)
```

- [ ] **Step 4: Chạy test, xác nhận qua**

Run: lệnh Step 2. Expected: tất cả PASS (test `test_setup_all_tra_ma_thoat` chạy `cmd.exe` thật — chỉ chạy được trên Windows, đúng môi trường test client).

- [ ] **Step 5: Commit**

```bash
git add core/first_run.py tests/core/test_first_run.py
git commit -m "feat(first-run): logic sau-cài trong app — file mặc định, DAW mặc định, setup_all, loopMIDI, nhận biết và chuyển cấu hình bản Inno cũ"
```

---

### Task 5: `tools/don_ban_cu.ps1` — dọn bản Inno cũ

**Files:**
- Create: `tools/don_ban_cu.ps1` (UTF-8 có BOM)
- Test: `tests/test_don_ban_cu.py`

**Interfaces:**
- Produces: `powershell -File tools\don_ban_cu.ps1 -LegacyDir <dir> [-UninstallKey <PS registry path>] [-ShortcutDirs "<dir1>;<dir2>"]` — mã thoát 0 khi xong (kể cả khi không còn gì để xoá). Dùng bởi `core.first_run.cleanup_legacy_elevated` và bộ cài cầu nối (Kế hoạch 4).

- [ ] **Step 1: Viết test thất bại**

```python
# tests/test_don_ban_cu.py
"""tools/don_ban_cu.ps1 xoá bản Inno cũ: thư mục cài, khoá gỡ cài đặt, đúng 5
shortcut cũ trong thư mục dùng chung — và KHÔNG gì khác."""
import os
import subprocess
import uuid
import winreg

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "tools", "don_ban_cu.ps1")
OLD_LNKS = ["Quang Luu Studio.lnk", "Gỡ cài đặt Quang Luu Studio.lnk",
            "Quang Luu Studio - Cấu hình YouTube Cookies.lnk",
            "Quang Luu Studio - Kiểm tra dò tone.lnk", "Quang Luu Studio Recordings.lnk"]


@pytest.fixture
def ctx(tmp_path):
    legacy = tmp_path / "Program Files" / "QuangLuuStudio"
    (legacy / "sfx").mkdir(parents=True)
    (legacy / "QuangLuuStudio.exe").write_bytes(b"MZ")
    (legacy / "sfx" / "a.wav").write_bytes(b"RIFF")
    sc = tmp_path / "Public Desktop"
    sc.mkdir()
    for n in OLD_LNKS + ["Trình duyệt khác.lnk"]:
        (sc / n).write_bytes(b"L")
    sub = f"Software\\QLSTest_DonBanCu\\{uuid.uuid4().hex}"
    winreg.CreateKey(winreg.HKEY_CURRENT_USER, sub).Close()
    yield {"legacy": legacy, "sc": sc, "key": "HKCU:\\" + sub, "sub": sub}
    for path in (sub, "Software\\QLSTest_DonBanCu"):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except OSError:
            pass


def _run(legacy, key, sc):
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", SCRIPT,
         "-LegacyDir", str(legacy), "-UninstallKey", key, "-ShortcutDirs", str(sc)],
        capture_output=True, text=True, timeout=60)


def _key_exists(sub):
    try:
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub).Close()
        return True
    except OSError:
        return False


def test_xoa_thu_muc_khoa_va_shortcut_cu(ctx):
    r = _run(ctx["legacy"], ctx["key"], ctx["sc"])
    assert r.returncode == 0, r.stdout + r.stderr
    assert not ctx["legacy"].exists()
    assert not _key_exists(ctx["sub"])
    assert sorted(os.listdir(ctx["sc"])) == ["Trình duyệt khác.lnk"]


def test_giu_shortcut_khac(ctx):
    _run(ctx["legacy"], ctx["key"], ctx["sc"])
    assert (ctx["sc"] / "Trình duyệt khác.lnk").exists()


def test_khong_xoa_thu_muc_la(ctx, tmp_path):
    la = tmp_path / "ThuMucLa"
    la.mkdir()
    (la / "quan_trong.txt").write_text("x", encoding="utf-8")
    r = _run(la, ctx["key"], ctx["sc"])
    assert r.returncode == 0, r.stdout + r.stderr
    assert (la / "quan_trong.txt").exists()


def test_chay_lai_khi_da_sach_van_ma_0(ctx):
    _run(ctx["legacy"], ctx["key"], ctx["sc"])
    r = _run(ctx["legacy"], ctx["key"], ctx["sc"])
    assert r.returncode == 0, r.stdout + r.stderr
```

- [ ] **Step 2: Chạy test, xác nhận thất bại**

Run: `cmd.exe /c "D:\Projects\quang-luu-studio\.venv\Scripts\python.exe -m pytest D:\Projects\quang-luu-studio\tests\test_don_ban_cu.py -q -p no:cacheprovider --rootdir=D:\Projects\quang-luu-studio"`
Expected: FAIL — script không tồn tại (mã thoát ≠ 0).

- [ ] **Step 3: Viết script** (lưu UTF-8 **có BOM**)

```powershell
# tools/don_ban_cu.ps1
# Dọn bản Quang Lưu Studio cài bằng Inno (Program Files, quyền admin) sau khi đã
# có bản Velopack (%LocalAppData%). Dùng chung cho app (core/first_run.py, chạy
# nâng quyền) và bộ cài cầu nối.
#
# KHÔNG gọi unins000.exe cũ: nó hiện hộp "Xoá dữ liệu?" mà /SUPPRESSMSGBOXES
# không chặn được — khách bấm nhầm là mất bài hát. Dữ liệu ở %APPDATA% và
# Documents không bị đụng.
param(
    [Parameter(Mandatory = $true)][string]$LegacyDir,
    [string]$UninstallKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{B8F3E2A1-5D6C-4E7F-9A0B-1C2D3E4F5A6B}_is1",
    [string]$ShortcutDirs = ""
)
$ErrorActionPreference = "Continue"

if (-not $ShortcutDirs) {
    # Inno cài admin → shortcut nằm ở thư mục DÙNG CHUNG. Bản Velopack đặt shortcut
    # ở thư mục của người dùng nên không bị đụng.
    $ShortcutDirs = (Join-Path $env:PUBLIC "Desktop") + ";" +
                    (Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs")
}
$oldShortcuts = @(
    "Quang Luu Studio.lnk",
    "Gỡ cài đặt Quang Luu Studio.lnk",
    "Quang Luu Studio - Cấu hình YouTube Cookies.lnk",
    "Quang Luu Studio - Kiểm tra dò tone.lnk",
    "Quang Luu Studio Recordings.lnk"
)

# 1. Thư mục cài — chỉ xoá khi đúng là thư mục của app (người dùng có thể đã chọn
#    thư mục khác lúc cài; khoá registry có thể trỏ sai).
$dir = $LegacyDir.TrimEnd('\')
if ($dir -and (Test-Path -LiteralPath $dir)) {
    $isApp = (Test-Path -LiteralPath (Join-Path $dir "QuangLuuStudio.exe")) -or
             (Test-Path -LiteralPath (Join-Path $dir "unins000.exe"))
    if ($isApp) {
        Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path -LiteralPath $dir) { Write-Output "[CANH BAO] Chua xoa het $dir (file dang bi khoa?)" }
        else { Write-Output "[OK] Da xoa $dir" }
    } else {
        Write-Output "[BO QUA] $dir khong phai thu muc cai Quang Luu Studio"
    }
}

# 2. Shortcut cũ — đúng 5 tên, chỉ trong các thư mục dùng chung.
foreach ($d in ($ShortcutDirs -split ';')) {
    if (-not $d) { continue }
    foreach ($n in $oldShortcuts) {
        $p = Join-Path $d $n
        if (Test-Path -LiteralPath $p) {
            Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue
            Write-Output "[OK] Da xoa shortcut $p"
        }
    }
}

# 3. Khoá gỡ cài đặt — để "Apps & features" không còn mục bản cũ.
if (Test-Path -LiteralPath $UninstallKey) {
    Remove-Item -LiteralPath $UninstallKey -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $UninstallKey) { Write-Output "[LOI] Khong xoa duoc $UninstallKey"; exit 1 }
    Write-Output "[OK] Da xoa khoa go cai dat cu"
}
exit 0
```

Kiểm BOM: `head -c3 tools/don_ban_cu.ps1 | xxd -p` → `efbbbf` (dùng công cụ Write rồi chạy `printf '\xef\xbb\xbf' | cat - tools/don_ban_cu.ps1 > /tmp/x && mv /tmp/x tools/don_ban_cu.ps1` nếu thiếu — **dùng file tạm trong scratchpad**, không dùng `/tmp`).

- [ ] **Step 4: Chạy test, xác nhận qua**

Run: lệnh Step 2. Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/don_ban_cu.ps1 tests/test_don_ban_cu.py
git commit -m "feat(tools): don_ban_cu.ps1 dọn bản Inno cũ (thư mục cài, 5 shortcut dùng chung, khoá gỡ cài đặt), không gọi unins000"
```

---

### Task 6: Hộp thoại lần chạy đầu + gắn vào `main.py`

**Files:**
- Create: `ui/dialogs/first_run_dialog.py`
- Modify: `main.py` (trong `main()`, ngay sau khối `startup_reconcile`, trước `while True:`)
- Test: `tests/ui/test_first_run_dialog.py`

**Interfaces:**
- Consumes: mọi hàm của Task 4; `core.config.APP_DIR`, `DATA_DIR`, `ConfigManager.load_settings/save_settings`.
- Produces:
  - `FirstRunDialog(app_dir: str, data_dir: str, legacy_dir: str | None, run_setup: bool, parent=None)` — `QDialog`; tự chạy luồng khi hiện; `accept()` khi xong.
  - `run_first_run_if_needed() -> None` — gọi từ `main.py`; không làm gì nếu không phải bản cài Velopack.

- [ ] **Step 1: Viết test thất bại**

```python
# tests/ui/test_first_run_dialog.py
"""Hộp thoại lần chạy đầu: chạy setup_all nền, hỏi cài loopMIDI / dọn bản cũ khi
cần, chỉ đánh dấu xong khi đi hết luồng."""
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture
def saved():
    store = {"settings": {}}
    with patch("ui.dialogs.first_run_dialog.ConfigManager.load_settings",
               side_effect=lambda: dict(store["settings"])), \
         patch("ui.dialogs.first_run_dialog.ConfigManager.save_settings",
               side_effect=lambda s: store.__setitem__("settings", dict(s)) or True), \
         patch("ui.dialogs.first_run_dialog.first_run.ensure_default_data_files", return_value=[]), \
         patch("ui.dialogs.first_run_dialog.first_run.default_daw", return_value="studio_one"):
        yield store


def _make(qtbot, legacy=None, run_setup=True):
    from ui.dialogs.first_run_dialog import FirstRunDialog
    d = FirstRunDialog("C:\\app", "C:\\data", legacy_dir=legacy, run_setup=run_setup)
    qtbot.addWidget(d)
    d.show()
    return d


def test_moi_thu_on_tu_dong_xong(qtbot, saved):
    with patch("ui.dialogs.first_run_dialog.first_run.run_setup_all", return_value=0):
        d = _make(qtbot)
        qtbot.waitUntil(lambda: d.result() == QDialog.Accepted, timeout=5000)
    assert saved["settings"].get("first_run_done") is True


def test_thieu_loopmidi_hoi_cai_roi_chay_lai(qtbot, saved):
    codes = iter([1, 0])
    with patch("ui.dialogs.first_run_dialog.first_run.run_setup_all", side_effect=lambda *_a, **_k: next(codes)), \
         patch("ui.dialogs.first_run_dialog.first_run.find_loopmidi", return_value=None), \
         patch("ui.dialogs.first_run_dialog.first_run.install_loopmidi_elevated", return_value=True) as inst:
        d = _make(qtbot)
        qtbot.waitUntil(lambda: d._btn_loopmidi.isVisible(), timeout=5000)
        qtbot.mouseClick(d._btn_loopmidi, Qt.LeftButton)
        qtbot.waitUntil(lambda: d.result() == QDialog.Accepted, timeout=5000)
    inst.assert_called_once()
    assert saved["settings"].get("first_run_done") is True


def test_setup_all_loi_van_cho_tiep_tuc(qtbot, saved):
    with patch("ui.dialogs.first_run_dialog.first_run.run_setup_all", return_value=-1):
        d = _make(qtbot)
        qtbot.waitUntil(lambda: d._btn_continue.isVisible(), timeout=5000)
        assert "setup_all.bat" in d._lbl_notes.text()
        qtbot.mouseClick(d._btn_continue, Qt.LeftButton)
    assert d.result() == QDialog.Accepted
    assert saved["settings"].get("first_run_done") is True


def test_ban_cu_de_sau_khong_don(qtbot, saved):
    with patch("ui.dialogs.first_run_dialog.first_run.run_setup_all", return_value=0), \
         patch("ui.dialogs.first_run_dialog.first_run.cleanup_legacy_elevated") as clean:
        d = _make(qtbot, legacy="C:\\Program Files\\QuangLuuStudio")
        qtbot.waitUntil(lambda: d._btn_legacy.isVisible(), timeout=5000)
        qtbot.mouseClick(d._btn_later, Qt.LeftButton)
        qtbot.waitUntil(lambda: d.result() == QDialog.Accepted, timeout=5000)
    clean.assert_not_called()


def test_ban_cu_don_thi_chuyen_cau_hinh_roi_don(qtbot, saved):
    with patch("ui.dialogs.first_run_dialog.first_run.run_setup_all", return_value=0), \
         patch("ui.dialogs.first_run_dialog.first_run.migrate_legacy_app_config", return_value=True) as mig, \
         patch("ui.dialogs.first_run_dialog.first_run.cleanup_legacy_elevated", return_value=True) as clean:
        d = _make(qtbot, legacy="C:\\Program Files\\QuangLuuStudio")
        qtbot.waitUntil(lambda: d._btn_legacy.isVisible(), timeout=5000)
        qtbot.mouseClick(d._btn_legacy, Qt.LeftButton)
        qtbot.waitUntil(lambda: d.result() == QDialog.Accepted, timeout=5000)
    mig.assert_called_once_with("C:\\Program Files\\QuangLuuStudio")
    clean.assert_called_once_with("C:\\Program Files\\QuangLuuStudio")


def test_dong_ngang_khong_danh_dau_xong(qtbot, saved):
    with patch("ui.dialogs.first_run_dialog.first_run.run_setup_all", return_value=1), \
         patch("ui.dialogs.first_run_dialog.first_run.find_loopmidi", return_value=None):
        d = _make(qtbot)
        qtbot.waitUntil(lambda: d._btn_loopmidi.isVisible(), timeout=5000)
        d.reject()
    assert "first_run_done" not in saved["settings"]


def test_chi_con_ban_cu_khong_chay_setup(qtbot, saved):
    with patch("ui.dialogs.first_run_dialog.first_run.run_setup_all") as setup:
        d = _make(qtbot, legacy="C:\\Program Files\\QuangLuuStudio", run_setup=False)
        qtbot.waitUntil(lambda: d._btn_legacy.isVisible(), timeout=5000)
        qtbot.mouseClick(d._btn_later, Qt.LeftButton)
    setup.assert_not_called()


def test_run_first_run_if_needed_bo_qua_ban_khong_phai_velopack():
    from ui.dialogs import first_run_dialog as m
    with patch.object(m.first_run, "is_velopack_install", return_value=False), \
         patch.object(m, "FirstRunDialog") as dlg:
        m.run_first_run_if_needed()
    dlg.assert_not_called()


def test_run_first_run_if_needed_bo_qua_khi_xong_va_khong_co_ban_cu():
    from ui.dialogs import first_run_dialog as m
    with patch.object(m.first_run, "is_velopack_install", return_value=True), \
         patch.object(m.ConfigManager, "load_settings", return_value={"first_run_done": True}), \
         patch.object(m.first_run, "find_legacy_install", return_value=None), \
         patch.object(m, "FirstRunDialog") as dlg:
        m.run_first_run_if_needed()
    dlg.assert_not_called()
```

- [ ] **Step 2: Chạy test, xác nhận thất bại**

Run: `cmd.exe /c "D:\Projects\quang-luu-studio\.venv\Scripts\python.exe -m pytest D:\Projects\quang-luu-studio\tests\ui\test_first_run_dialog.py -q -p no:cacheprovider --rootdir=D:\Projects\quang-luu-studio"`
Expected: FAIL — `ModuleNotFoundError: No module named 'ui.dialogs.first_run_dialog'`.

- [ ] **Step 3: Viết hộp thoại**

```python
# ui/dialogs/first_run_dialog.py
"""Quang Lưu Studio — Hộp thoại lần chạy đầu sau khi cài.

Thay cho [Code] của bộ cài Inno: tạo file mặc định, chạy setup_all.bat /auto
(cổng MIDI, Surface Studio One, script Cubase), hỏi cài loopMIDI nếu thiếu,
hỏi dọn bản cũ trong Program Files. Việc nặng chạy trong QThread để cửa sổ
không đơ. Cờ first_run_done CHỈ được ghi khi đi hết luồng — đóng ngang thì
lần mở sau chạy lại.
"""
import os
import sys

from PySide6.QtCore import QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar,
)

from core import first_run
from core.config import APP_DIR, DATA_DIR, ConfigManager
from ui.design_tokens import C, FONT


class _Job(QThread):
    done = Signal(object)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            self.done.emit(self._fn())
        except Exception as e:  # không để luồng chết im lặng
            self.done.emit(e)


class FirstRunDialog(QDialog):
    def __init__(self, app_dir, data_dir, legacy_dir=None, run_setup=True, parent=None):
        super().__init__(parent)
        self._app_dir = app_dir
        self._data_dir = data_dir
        self._legacy_dir = legacy_dir
        self._run_setup = run_setup
        self._code = None
        self._tried_loopmidi = False
        self._notes = []
        self._job = None
        self._started = False

        self.setWindowTitle("Quang Lưu Studio")
        self.setMinimumWidth(460)
        self.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']}; font-family: {FONT};")
        vl = QVBoxLayout(self)
        self._lbl_title = QLabel("Đang chuẩn bị Quang Lưu Studio")
        self._lbl_title.setStyleSheet("font-size:16px; font-weight:600;")
        self._lbl_status = QLabel("")
        self._lbl_status.setWordWrap(True)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)   # chạy vô hạn — không đo được % của setup_all
        self._progress.setTextVisible(False)
        self._lbl_notes = QLabel("")
        self._lbl_notes.setWordWrap(True)
        for w in (self._lbl_title, self._lbl_status, self._progress, self._lbl_notes):
            vl.addWidget(w)

        row = QHBoxLayout()
        row.addStretch(1)
        self._btn_loopmidi = QPushButton("Cài loopMIDI")
        self._btn_legacy = QPushButton("Dọn bản cũ")
        self._btn_later = QPushButton("Để sau")
        self._btn_continue = QPushButton("Tiếp tục")
        for b in (self._btn_loopmidi, self._btn_legacy, self._btn_later, self._btn_continue):
            b.hide()
            row.addWidget(b)
        vl.addLayout(row)

        self._btn_loopmidi.clicked.connect(self._cai_loopmidi)
        self._btn_legacy.clicked.connect(self._don_ban_cu)
        self._btn_later.clicked.connect(self._de_sau)
        self._btn_continue.clicked.connect(self._xong)

    # ── tiện ích ──
    def showEvent(self, event):
        super().showEvent(event)
        if not self._started:
            self._started = True
            QTimer.singleShot(0, self._bat_dau)

    def _buttons(self, *visible):
        for b in (self._btn_loopmidi, self._btn_legacy, self._btn_later, self._btn_continue):
            b.setVisible(b in visible)
        self._progress.setVisible(not visible)

    def _chay(self, status, fn, then):
        self._lbl_status.setText(status)
        self._buttons()
        self._job = _Job(fn, self)
        self._job.done.connect(then)
        self._job.start()

    def _chay_setup_all(self):
        self._chay("Đang tạo cổng MIDI và kết nối với DAW…",
                   lambda: first_run.run_setup_all(self._app_dir), self._sau_setup_all)

    # ── luồng ──
    def _bat_dau(self):
        if not self._run_setup:
            self._buoc_ban_cu()
            return
        pf = os.environ.get("ProgramW6432") or os.environ.get("ProgramFiles", "")
        daw_kind = first_run.default_daw(pf, os.environ.get("APPDATA", ""))
        first_run.ensure_default_data_files(self._data_dir, daw_kind)
        self._chay_setup_all()

    def _sau_setup_all(self, code):
        self._code = code if isinstance(code, int) else first_run.SETUP_ALL_FAILED
        if (self._code > 0 and self._code & 1 and not self._tried_loopmidi
                and first_run.find_loopmidi() is None):
            self._lbl_status.setText(
                "Máy chưa có loopMIDI — phần mềm tạo cổng MIDI ảo để app điều khiển DAW. "
                "Cần cài một lần; Windows sẽ hỏi quyền.")
            self._buttons(self._btn_loopmidi, self._btn_later)
            self._sau_de_sau = self._buoc_ban_cu
            return
        self._buoc_ban_cu()

    def _cai_loopmidi(self):
        self._tried_loopmidi = True
        self._chay("Đang cài loopMIDI…", first_run.install_loopmidi_elevated, self._sau_cai_loopmidi)

    def _sau_cai_loopmidi(self, ok):
        if ok is True:
            self._chay_setup_all()
        else:
            self._notes.append("Chưa cài được loopMIDI. Tải tại https://www.tobias-erichsen.de/software/loopmidi.html "
                               "rồi chạy setup_all.bat trong thư mục cài đặt.")
            self._buoc_ban_cu()

    def _buoc_ban_cu(self):
        if self._legacy_dir is None:
            self._ket_thuc()
            return
        self._lbl_status.setText(
            "Máy còn bản Quang Lưu Studio cũ trong Program Files. Dọn đi để khỏi nhầm biểu tượng? "
            "Windows sẽ hỏi quyền. Dữ liệu bài hát và cài đặt không bị đụng.")
        self._buttons(self._btn_legacy, self._btn_later)
        self._sau_de_sau = self._ket_thuc

    def _don_ban_cu(self):
        legacy = self._legacy_dir

        def work():
            first_run.migrate_legacy_app_config(legacy)
            return first_run.cleanup_legacy_elevated(legacy)
        self._chay("Đang dọn bản cũ…", work, self._sau_don_ban_cu)

    def _sau_don_ban_cu(self, ok):
        if ok is not True:
            self._notes.append("Chưa dọn được bản cũ — app sẽ hỏi lại lần mở sau.")
        self._ket_thuc()

    def _de_sau(self):
        self._sau_de_sau()

    def _ket_thuc(self):
        if self._run_setup:
            settings = ConfigManager.load_settings()
            ConfigManager.save_settings(first_run.mark_done(settings))
        notes = first_run.describe_setup_all_code(self._code) + self._notes
        if not notes:
            self.accept()
            return
        self._lbl_status.setText("Đã xong. Còn vài việc cần làm:")
        self._lbl_notes.setText("\n".join("• " + n for n in notes))
        self._buttons(self._btn_continue)

    def _xong(self):
        self.accept()


def run_first_run_if_needed():
    """Gọi từ main.py trước cổng kích hoạt. Chỉ chạy ở bản cài Velopack."""
    if not first_run.is_velopack_install(APP_DIR):
        return
    settings = ConfigManager.load_settings()
    legacy = first_run.find_legacy_install()
    need_setup = not first_run.is_done(settings)
    if not need_setup and legacy is None:
        return
    if QApplication.instance() is None:
        QApplication(sys.argv)
    FirstRunDialog(APP_DIR, DATA_DIR, legacy_dir=legacy, run_setup=need_setup).exec()
```

(`C['bg']`, `C['text']` là khoá có thật trong `ui/design_tokens.py`, cùng cách `shutdown_dialog.py:67` dùng.)

- [ ] **Step 4: Gắn vào `main.py`**

Trong `main()`, ngay sau khối `try: ... _lic.startup_reconcile() ... except ...` và **trước** `while True:` thêm:

```python
    # Lần chạy đầu sau khi cài (bản Velopack): file mặc định, cổng MIDI,
    # loopMIDI, dọn bản Inno cũ. Bản Inno/dev không có Update.exe → bỏ qua.
    try:
        from ui.dialogs.first_run_dialog import run_first_run_if_needed
        run_first_run_if_needed()
    except Exception:
        log.exception("Bước lần chạy đầu lỗi — vẫn mở app")
```

- [ ] **Step 5: Chạy test, xác nhận qua**

Run: lệnh Step 2. Expected: 9 passed. Chạy thêm `tests\ui\test_main_window_logic.py -k "not slow"` không bắt buộc; bắt buộc chạy `tests\core\test_first_run.py tests\core\test_config_overrides.py` lần nữa cùng lúc để chắc không xung đột fixture. Sau đó `git checkout app_config.json` nếu đổi.

- [ ] **Step 6: Commit**

```bash
git add ui/dialogs/first_run_dialog.py main.py tests/ui/test_first_run_dialog.py
git commit -m "feat(first-run): hộp thoại lần chạy đầu (setup_all nền, cài loopMIDI, dọn bản cũ), chỉ chạy ở bản cài Velopack"
```

---

### Task 7: Chạy toàn bộ suite

- [ ] **Step 1: Chạy suite client (nền, >10 phút)**

Run: `cmd.exe /c "D:\Projects\quang-luu-studio\.venv\Scripts\python.exe -m pytest D:\Projects\quang-luu-studio\tests -q -p no:cacheprovider --rootdir=D:\Projects\quang-luu-studio --ignore=D:\Projects\quang-luu-studio\tests\test_recorder_worker_e2e.py"`
Expected: không có FAIL mới so với `main` (nếu có FAIL, so bằng cách chạy cùng test trên `main` trước khi kết luận). Sau đó `git checkout app_config.json`, đặt lại `daw_kind`, `auto_launch_studio_one`, `studio_one_path` trong `settings.json` (memory test-env).
