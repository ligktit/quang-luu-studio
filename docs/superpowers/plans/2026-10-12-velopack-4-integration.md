# Velopack — Kế hoạch 4/4: Tích hợp Velopack, đóng gói, CI, bộ cài cầu nối

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** App 1.9.0 cài bằng Velopack: cập nhật ngầm từ feed của server và áp dụng khi tắt app, build onedir + `vpk pack` trên CI (GitHub Release dạng prerelease), và một bộ cài cầu nối Inno đưa các máy ≤ 1.8.x sang bản mới.

**Architecture:** `main.py` gọi `velopack.App().run()` trước mọi import nặng. `core/updater/velopack_updater.py` (không đụng Qt) chạy một luồng nền: chờ 60 s rồi cứ 6 giờ hỏi feed `<license_server_url>/api/v1/updates/velopack/<fingerprint>` và tải sẵn bản mới; `main.py` gọi `apply_pending_on_exit()` trước `os._exit`. Bộ cập nhật cũ (`core/updater/_*.py`, `ui/dialogs/update_dialog.py`) bị bỏ; Cài đặt chỉ còn dòng trạng thái. `tools/build_velopack.ps1` chép tài nguyên cạnh exe onedir rồi `vpk pack` (dùng chung cho CI và máy dev). `QuangLuuStudio_Bridge.iss` (cùng AppId bản Inno cũ) bọc `QuangLuuStudio-CaiDat.exe`, cài nó dưới quyền người dùng gốc, chuyển cấu hình bằng exe mới (`--chuyen-cau-hinh-cu`) rồi dọn bản cũ bằng `tools/don_ban_cu.ps1`. Kèm ba việc treo từ Kế hoạch 2/3 và các nút trong app thay shortcut `.bat`.

**Tech Stack:** Python 3.13 (dev) / 3.11 (CI), PySide6, velopack (pip) 1.2.161, vpk (.NET tool) 1.2.161, PyInstaller onedir, Inno Setup 6, PowerShell 5.1, GitHub Actions, FastAPI (server).

**Spec:** `docs/superpowers/specs/2026-10-12-velopack-installer-design.md` (mục 2 Gỡ cài đặt; mục 3 toàn bộ phía client; mục 4 đường 1 + công cụ chẩn đoán; mục 5 CI + kiểm thử). Kết quả spike: `docs/superpowers/specs/2026-10-12-velopack-spike-findings.md` (mục "Điều chỉnh cần đưa vào Kế hoạch 4").

**Phụ thuộc:** Kế hoạch 1–3 đã merge vào `feat/velopack-installer` (636f9af, ed4c1dd); server đã deploy bảng `velopack_releases`. Làm trực tiếp trên nhánh `feat/velopack-installer` (thư mục chính của repo).

## Global Constraints

- Phiên bản Velopack: pip `velopack==1.2.161` và `vpk` **1.2.161** (`dotnet tool install -g vpk --version 1.2.161`) — luôn cùng số.
- `vpk pack`: `--packId QuangLuuStudio`, `--packTitle "Quang Lưu Studio"`, `--mainExe QuangLuuStudio.exe`, `--icon app_icon.ico`, `--packDir dist\QuangLuuStudio`.
- Tên file phát hành: Setup Velopack đổi thành **`QuangLuuStudio-CaiDat.exe`** (không chứa "setup"); bộ cài cầu nối **`Setup_QuangLuuStudio_v<ver>.exe`**. GitHub Release đánh dấu **prerelease**; `vpk download github` dùng `--pre`.
- Feed: `<license_server_url>/api/v1/updates/velopack/<fingerprint>` (Velopack tự nối `/releases.win.json` và tên gói). Fingerprint phải khớp `^[A-Za-z0-9_-]{1,128}$` (giống `valid_fingerprint` của server).
- Lịch kiểm tra: lần đầu **60 s** sau khi mở app, sau đó **mỗi 6 giờ**; tôn trọng `settings["update"]["auto_check"]` (mặc định `True`). Áp dụng: `wait_exit_then_apply_updates(asset, silent=True, restart=False)` khi tắt bình thường. Không hộp thoại cập nhật nào.
- Không ghi gì vào `current\` (thư mục exe của bản Velopack).
- AppId bản Inno cũ: `{B8F3E2A1-5D6C-4E7F-9A0B-1C2D3E4F5A6B}`.
- File `.ps1` có ký tự tiếng Việt: UTF-8 **có BOM**. JSON ghi ra: UTF-8 không BOM. PowerShell gọi từ code: bọc `$ErrorActionPreference='Stop'; try { … } catch { exit 1 }` (không thì `$null` → `exit 0`).
- Chạy test client bằng venv Windows: `cmd.exe /c "cd /d D:\Projects\quang-luu-studio && .venv\Scripts\python.exe -m pytest <đường dẫn Windows> -q -p no:cacheprovider"`. Sau khi chạy cả suite: `git checkout app_config.json` và đặt lại `settings.json` (memory test-env). Test server: `cd server && ~/.venvs/qls-server/bin/python -m pytest <file> -q`.
- Lệnh `.bat` chạy từ code: `["cmd.exe", "/c", "<tên.bat>"]` với `cwd=<thư mục>` — không bao giờ ghép đường dẫn tuyệt đối vào dòng lệnh cmd (vỡ khi có `( ) &`).
- **Không** merge vào `main`, **không** tag, **không** deploy server khi chưa hỏi người dùng.

## Review Focus

- **App không phải bản cài Velopack** (chạy từ mã nguồn, hoặc bản Inno 1.8 còn trên máy) → không tạo luồng cập nhật, không ném lỗi, khởi động không chậm thêm; Cài đặt ghi rõ "không tự cập nhật". (Task 3 `test_khong_phai_velopack_khong_chay`, Task 4 `test_trang_thai_cap_nhat_ban_khong_velopack`.)
- **Máy chủ không trả lời / mạng treo / `license_server_url` rỗng / fingerprint lạ** → lượt đó bỏ qua, ghi log, lần sau thử lại; không bao giờ rơi về GitHub. (Task 3 `test_loi_mang_danh_dau_va_thu_lai`, `test_feed_url_*`.)
- **Tắt app khi đang tải dở** → không gọi áp dụng (chỉ áp dụng khi `get_update_pending_restart()` có bản), không chặn việc thoát. (Task 3 `test_ap_dung_khi_thoat_*`.)
- **Đường dẫn có `'`, dấu cách, `( ) &`, chữ có dấu** trong lệnh xoá dữ liệu, chạy `.bat`, bộ cài cầu nối → lệnh vẫn trỏ đúng thư mục. (Task 5 `test_lenh_xoa_du_lieu_duong_dan_co_nhay_don`, `test_chay_bat_dung_cwd`; Task 8 kiểm tĩnh `PsLit`.)
- **"Xoá dữ liệu" khi DATA_DIR không phải `%APPDATA%\QuangLuuStudio`** (chạy từ mã nguồn → DATA_DIR = gốc repo) → từ chối, không xoá gì. (Task 5 `test_khong_xoa_khi_chay_tu_ma_nguon`, `test_khong_xoa_thu_muc_ten_la`.)

---

### Task 1: Server — mỗi lượt nhập tải vào thư mục tạm riêng; nginx cho upload bộ cài cầu nối lớn

Việc treo từ Kế hoạch 3: lượt nhập cũ (kẹt > 30 phút rồi bị thay) có thể xoá file mà lượt mới đang phục vụ, vì cả hai cùng ghi thẳng vào `velopack/` và lượt cũ dọn "file mình tạo" khi token không khớp. Sửa: mỗi lượt tải vào `velopack/.staging-<hex>/`; chỉ khi token còn khớp mới `os.replace` từng file sang `velopack/` (nội dung cùng tên đã kiểm SHA256 nên ghi đè là vô hại); mọi nhánh khác chỉ xoá thư mục staging của chính lượt đó.

**Files:**
- Modify: `server/app/services/velopack_import.py`
- Modify: `server/tests/test_velopack_import.py` (thay `test_ten_part_rieng_moi_lan_tai`, thêm 2 test)
- Modify: `server/deploy/nginx.conf:7`

**Interfaces:**
- Consumes: `velopack_feed.velopack_dir()`, `velopack_feed.valid_filename(name)`.
- Produces: `import_release(release_id, token=None, *, client=None, session_factory=SessionLocal)` (chữ ký không đổi). Thư mục `velopack/.staging-*` không bao giờ được phục vụ (`valid_filename` của tên gói không chứa `/`).

- [ ] **Step 1: Viết test hỏng**

Trong `server/tests/test_velopack_import.py`, xoá nguyên hàm `test_ten_part_rieng_moi_lan_tai` và thêm:

```python
def test_moi_luot_tai_vao_thu_muc_staging_rieng(client):
    full, files = _full_files()
    rid = _new_row()
    seen = []
    real = velopack_import.os.replace

    def spy(src, dst):
        seen.append(str(src))
        return real(src, dst)

    with patch.object(velopack_import.os, "replace", spy), \
            httpx.Client(transport=_transport([full], files)) as c:
        velopack_import.import_release(rid, client=c)
        velopack_import.import_release(rid, client=c)
    staging = {os.path.basename(os.path.dirname(s)) for s in seen}
    assert len(staging) == 2 and all(re.fullmatch(r"\.staging-[0-9a-f]{32}", s) for s in staging)
    # chỉ còn gói thật, không sót thư mục staging
    assert sorted(p.name for p in velopack_feed.velopack_dir().iterdir()) == [full["FileName"]]


def test_luot_cu_bi_thay_khong_xoa_file_luot_moi_dang_phuc_vu(client):
    """Lượt mới (token khớp) đã nhập xong; lượt cũ chạy xong sau với token cũ →
    file đang phục vụ phải còn nguyên."""
    full, files = _full_files()
    rid = _new_row()
    with SessionLocal() as db:
        db.get(VelopackRelease, rid).import_token = "moi" * 10 + "ab"
        db.commit()
    with httpx.Client(transport=_transport([full], files)) as c:
        velopack_import.import_release(rid, "moi" * 10 + "ab", client=c)   # lượt mới xong trước
        velopack_import.import_release(rid, "cu" * 16, client=c)           # lượt cũ xong sau
    assert _row(rid).status == "xong"
    assert (velopack_feed.velopack_dir() / full["FileName"]).read_bytes() == FULL


def test_loi_khong_dung_file_da_phuc_vu_cua_ban_khac(client):
    """Bản 1.9.1 lỗi giữa chừng không được xoá gói trùng tên đã có sẵn trong velopack/."""
    full = _a("1.9.1", "Full", FULL)
    delta = _a("1.9.1", "Delta", DELTA)
    (velopack_feed.velopack_dir() / full["FileName"]).write_bytes(FULL)
    files = {"releases.win.json": b"", full["FileName"]: FULL, delta["FileName"]: b"X" * len(DELTA)}
    rid = _new_row()
    with httpx.Client(transport=_transport([full, delta], files)) as c:
        velopack_import.import_release(rid, client=c)
    assert _row(rid).status == "loi"
    assert sorted(p.name for p in velopack_feed.velopack_dir().iterdir()) == [full["FileName"]]
```

Sửa `test_dong_bi_xoa_trong_luc_tai_don_file` theo chữ ký mới của `_download_all` (thêm tham số `staging`):

```python
    def download_then_delete(c, version, staging):
        out = real(c, version, staging)
```

Thêm `import os` vào khối import đầu file (sau `import json`).

- [ ] **Step 2: Chạy, thấy hỏng**

Run: `cd server && ~/.venvs/qls-server/bin/python -m pytest tests/test_velopack_import.py -q`
Expected: FAIL ở `test_moi_luot_tai_vao_thu_muc_staging_rieng` (tên `.part-xxxxxxxx`, không có thư mục staging) và `test_luot_cu_bi_thay_khong_xoa_file_luot_moi_dang_phuc_vu` (file bị xoá).

- [ ] **Step 3: Viết lại phần tải trong `velopack_import.py`**

Thay docstring đầu file, `_download`, `_download_all`, `_download_all_into`, `_remove` và `import_release` bằng:

```python
"""Nhập một bản Velopack từ GitHub Release về storage_dir/velopack.

Chạy nền (BackgroundTasks) vì gói Full ~500 MB. Chỉ lấy các phần tử Assets
của ĐÚNG phiên bản (releases.win.json của vpk còn liệt kê bản trước), kiểm
kích thước + SHA256 từng gói. Mỗi lượt tải vào velopack/.staging-<hex>/ riêng;
chỉ lượt còn giữ đúng import_token mới chuyển file sang velopack/. Lượt bị thay,
bị xoá dòng hay lỗi chỉ dọn thư mục staging của chính nó — không bao giờ đụng
file đang phục vụ.
"""
import hashlib
import json
import logging
import os
import shutil
import uuid

import httpx

from app.config import settings
from app.db import SessionLocal
from app.models import VelopackRelease
from app.services import velopack_feed

log = logging.getLogger(__name__)

FEED_ASSET = "releases.win.json"
SETUP_ASSET = "QuangLuuStudio-CaiDat.exe"


def _download(client, url, name, staging, expect_sha256=None, expect_size=None):
    if not velopack_feed.valid_filename(name):
        raise ValueError(f"Tên file không hợp lệ: {name!r}")
    dest = staging / name
    h = hashlib.sha256()
    size = 0
    with client.stream("GET", url) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_bytes(1024 * 1024):
                f.write(chunk)
                h.update(chunk)
                size += len(chunk)
    if expect_size and size != int(expect_size):
        raise ValueError(f"{name}: sai kích thước ({size} ≠ {expect_size})")
    if expect_sha256 and h.hexdigest().lower() != str(expect_sha256).lower():
        raise ValueError(f"{name}: sai SHA256")


def _download_all(client, version, staging):
    """Tải mọi tài sản của bản `version` vào `staging`. Trả (assets, tên setup, các tên file)."""
    api = f"https://api.github.com/repos/{settings.github_repo}/releases/tags/v{version}"
    r = client.get(api, headers={"Accept": "application/vnd.github+json"})
    r.raise_for_status()
    gh = {a["name"]: a for a in r.json().get("assets", [])}
    urls = {n: a["browser_download_url"] for n, a in gh.items()}
    if FEED_ASSET not in urls:
        raise ValueError(f"Release v{version} thiếu {FEED_ASSET}")
    feed = client.get(urls[FEED_ASSET])
    feed.raise_for_status()
    mine = [a for a in feed.json().get("Assets", []) if a.get("Version") == version]
    if not any(a.get("Type") == "Full" for a in mine):
        raise ValueError(f"{FEED_ASSET} không có gói Full của bản {version}")
    names = []
    for a in mine:
        name = a.get("FileName", "")
        if not velopack_feed.valid_filename(name):
            raise ValueError(f"Tên file không hợp lệ trong feed: {name!r}")
        if name not in urls:
            raise ValueError(f"Release v{version} thiếu {name}")
        _download(client, urls[name], name, staging, a.get("SHA256"), a.get("Size"))
        names.append(name)
    setup_name = None
    if SETUP_ASSET in urls:
        setup_name = f"{version}_{SETUP_ASSET}"
        meta = gh[SETUP_ASSET]  # GitHub ghi sẵn size (và digest "sha256:<hex>" ở bản mới)
        digest = str(meta.get("digest") or "")
        sha = digest[len("sha256:"):] if digest.lower().startswith("sha256:") else None
        _download(client, urls[SETUP_ASSET], setup_name, staging, sha, meta.get("size"))
        names.append(setup_name)
    return mine, setup_name, names


def import_release(release_id, token=None, *, client=None, session_factory=SessionLocal):
    own = client is None
    if own:
        client = httpx.Client(timeout=httpx.Timeout(60.0, read=300.0), follow_redirects=True,
                              headers={"User-Agent": "QuangLuuStudio-Server"})
    staging = velopack_feed.velopack_dir() / f".staging-{uuid.uuid4().hex}"
    try:
        with session_factory() as db:
            row = db.get(VelopackRelease, release_id)
            version = row.version if row is not None else None
        if version is None:
            log.warning("Nhập Velopack: dòng %s đã bị xoá, bỏ qua", release_id)
            return
        staging.mkdir(parents=True)
        names = []
        try:
            assets, setup_name, names = _download_all(client, version, staging)
            status, error = "xong", None
        except Exception as e:  # mọi lỗi → trạng thái "loi" để admin thấy, không làm chết worker
            log.warning("Nhập Velopack %s lỗi: %s", version, e)
            assets, setup_name, status, error = None, None, "loi", f"{type(e).__name__}: {e}"
        with session_factory() as db:
            row = db.get(VelopackRelease, release_id)
            if row is None or row.import_token != token:
                # Dòng đã bị xoá, hoặc có lần nhập mới hơn thay thế: bỏ kết quả (staging dọn ở finally).
                log.warning("Nhập Velopack %s: kết quả bị bỏ (dòng đã xoá hoặc lần nhập đã bị thay)", version)
                return
            if assets is not None:
                dest = velopack_feed.velopack_dir()
                for name in names:  # cùng tên = cùng nội dung (đã kiểm SHA256) → ghi đè vô hại
                    os.replace(staging / name, dest / name)
                row.assets_json = json.dumps(assets, ensure_ascii=False)
                row.setup_filename = setup_name
            row.status = status
            row.import_error = error
            db.commit()
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        if own:
            client.close()
```

- [ ] **Step 4: Chạy lại cả file + toàn bộ test server**

Run: `cd server && ~/.venvs/qls-server/bin/python -m pytest -q`
Expected: tất cả PASS (237 − 1 + 3 = 239). Các test cũ `test_loi_giua_chung_don_file_da_tai`, `test_token_bi_thay_khong_ghi_trang_thai`, `test_dong_bi_xoa_*` vẫn qua vì staging bị xoá và không có gì được chuyển sang `velopack/`.

- [ ] **Step 5: nginx cho upload bộ cài cầu nối**

Bộ cài cầu nối bọc `QuangLuuStudio-CaiDat.exe` (~561 MB) nên sát giới hạn 600M hiện tại. Trong `server/deploy/nginx.conf` dòng 7 đổi:

```
    client_max_body_size 1024M;  # bộ cài cầu nối Inno bọc Setup Velopack (~565 MB)
```

(Áp lên VPS ở Task 10, sau khi hỏi người dùng.)

- [ ] **Step 6: Commit**

```bash
git add server/app/services/velopack_import.py server/tests/test_velopack_import.py server/deploy/nginx.conf
git commit -m "fix(server): mỗi lượt nhập Velopack tải vào thư mục staging riêng — lượt cũ bị thay không còn xoá được file lượt mới đang phục vụ; nginx nhận upload 1 GB cho bộ cài cầu nối"
```

---

### Task 2: Lần chạy đầu — chuyển cấu hình lỗi thì không cho dọn; lệnh `--chuyen-cau-hinh-cu` cho bộ cài cầu nối

Hai việc treo từ Kế hoạch 2: (a) chuyển cấu hình bản cũ lỗi (ví dụ OSError khi ghi) mà khách vẫn bấm dọn thì giá trị cũ mất hẳn → khi lỗi chỉ hiện "Để sau" kèm ghi chú; (b) hai test hộp thoại gọi `migrate_legacy_app_config` thật trên máy dev → fixture `saved` patch mặc định. Thêm `first_run.migrate_cli(legacy_dir)` mà Task 4 nối vào `main.py` và Task 8 gọi từ bộ cài cầu nối.

**Files:**
- Modify: `ui/dialogs/first_run_dialog.py` (`_sau_chuyen_cau_hinh`)
- Modify: `core/first_run.py` (thêm `migrate_cli` sau `migrate_legacy_app_config`)
- Test: `tests/ui/test_first_run_dialog.py`, `tests/core/test_first_run.py`

**Interfaces:**
- Consumes: `first_run.migrate_legacy_app_config(legacy_dir) -> bool`, `first_run.legacy_path_key(path) -> str`, `core.config.ConfigManager.load_settings() -> dict` (trả `{}` khi chưa có file), `ConfigManager.save_settings(dict) -> bool`.
- Produces: `first_run.migrate_cli(legacy_dir: str) -> int` — 0 xong (kể cả không có gì để chuyển), 1 lỗi, 2 thiếu đối số.

- [ ] **Step 1: Test hộp thoại hỏng**

Trong `tests/ui/test_first_run_dialog.py`, fixture `saved`: thêm một dòng patch vào khối `with` (sau dòng patch `default_daw`):

```python
         patch("ui.dialogs.first_run_dialog.first_run.migrate_legacy_app_config", return_value=False), \
```

(Các test tự patch lại hàm này bằng `with patch(...)` lồng bên trong vẫn thắng.) Thêm test cuối file:

```python
def test_chuyen_cau_hinh_loi_chi_cho_de_sau(qtbot, saved):
    """Chuyển cấu hình cũ lỗi → không được dọn bản cũ (giá trị cũ còn nằm ở đó)."""
    with patch("ui.dialogs.first_run_dialog.first_run.run_setup_all", return_value=0), \
         patch("ui.dialogs.first_run_dialog.first_run.migrate_legacy_app_config",
               side_effect=OSError("đĩa đầy")), \
         patch("ui.dialogs.first_run_dialog.first_run.cleanup_legacy_elevated") as clean:
        d = _make(qtbot, legacy=LEGACY)
        qtbot.waitUntil(lambda: d._btn_continue.isVisible(), timeout=5000)
        assert not d._btn_legacy.isVisible()
        assert "chuyển cấu hình" in d._lbl_notes.text().lower()
        qtbot.mouseClick(d._btn_continue, Qt.LeftButton)
    clean.assert_not_called()
    assert "legacy_config_migrated" not in saved["settings"]
    assert saved["settings"].get("first_run_done") is True
```

- [ ] **Step 2: Test `migrate_cli` hỏng**

Cuối `tests/core/test_first_run.py`:

```python
def _settings_iso(tmp_path, monkeypatch, content):
    p = tmp_path / "settings.json"
    if content is not None:
        p.write_text(json.dumps(content), encoding="utf-8")
    monkeypatch.setattr(cfg, "SETTINGS_FILE", str(p))
    return p


def test_migrate_cli_ghi_co_da_chuyen(_cfg_iso, monkeypatch):
    legacy = _cfg_iso / "legacy"
    legacy.mkdir()
    (legacy / "app_config.json").write_text(json.dumps({"midi_cc": {"tone_music": 55}}), encoding="utf-8")
    s = _settings_iso(_cfg_iso, monkeypatch, {"daw_kind": "cubase"})
    assert first_run.migrate_cli(str(legacy)) == 0
    saved = json.loads(s.read_text(encoding="utf-8"))
    assert saved["legacy_config_migrated"] == first_run.legacy_path_key(str(legacy))
    assert saved["daw_kind"] == "cubase"
    assert json.loads((_cfg_iso / "ov.json").read_text(encoding="utf-8")) == {"midi_cc": {"tone_music": 55}}


def test_migrate_cli_chua_co_settings_khong_tao_file(_cfg_iso, monkeypatch):
    """settings.json rỗng mà ghi một khoá thì app tưởng đã cài đặt xong → bỏ qua màn hình Setup."""
    s = _settings_iso(_cfg_iso, monkeypatch, None)
    assert first_run.migrate_cli(str(_cfg_iso / "khong_co")) == 0
    assert not s.exists()


def test_migrate_cli_thieu_doi_so():
    assert first_run.migrate_cli("") == 2


def test_migrate_cli_loi_tra_1(_cfg_iso, monkeypatch):
    _settings_iso(_cfg_iso, monkeypatch, {"daw_kind": "cubase"})
    with patch.object(first_run, "migrate_legacy_app_config", side_effect=OSError("x")):
        assert first_run.migrate_cli(str(_cfg_iso)) == 1
```

- [ ] **Step 3: Chạy, thấy hỏng**

Run: `cmd.exe /c "cd /d D:\Projects\quang-luu-studio && .venv\Scripts\python.exe -m pytest tests\ui\test_first_run_dialog.py tests\core\test_first_run.py -q -p no:cacheprovider"`
Expected: FAIL — `test_chuyen_cau_hinh_loi_chi_cho_de_sau` (nút dọn vẫn hiện), các `test_migrate_cli_*` (`AttributeError: ... migrate_cli`).

- [ ] **Step 4: Sửa `_sau_chuyen_cau_hinh`**

Trong `ui/dialogs/first_run_dialog.py` thay nguyên hàm:

```python
    def _sau_chuyen_cau_hinh(self, wrote):
        if isinstance(wrote, Exception):
            # Giá trị cũ chưa sang được lớp người dùng → KHÔNG cho dọn bản cũ lúc này
            # (dọn là mất hẳn). Lần mở sau thử chuyển lại rồi mới hỏi dọn.
            log.error("Chuyển cấu hình bản cũ lỗi: %s", wrote)
            self._notes.append("Chưa chuyển cấu hình từ bản cũ được (lỗi ghi file) — "
                               "app sẽ thử lại và hỏi dọn bản cũ ở lần mở sau.")
            self._ket_thuc()
            return
        settings = ConfigManager.load_settings()
        settings["legacy_config_migrated"] = first_run.legacy_path_key(self._legacy_dir)
        ConfigManager.save_settings(settings)
        if wrote:
            # MIDI_CC… của giao diện được đọc lúc import → cần mở lại app.
            self._notes.append("Đã chuyển cấu hình từ bản cũ — hãy đóng và mở lại app để áp dụng.")
        self._hoi_don_ban_cu()
```

- [ ] **Step 5: Thêm `migrate_cli` vào `core/first_run.py`** (ngay sau `migrate_legacy_app_config`)

```python
def migrate_cli(legacy_dir):
    """`QuangLuuStudio.exe --chuyen-cau-hinh-cu <thư mục cũ>` — bộ cài cầu nối gọi dưới
    quyền người dùng gốc trước khi dọn bản Inno. Ghi cờ legacy_config_migrated để lần
    chạy đầu không chuyển lại. 0 = xong, 1 = lỗi, 2 = thiếu đối số."""
    if not legacy_dir:
        log.error("--chuyen-cau-hinh-cu thiếu thư mục bản cũ")
        return 2
    try:
        wrote = migrate_legacy_app_config(legacy_dir)
        settings = _cfg.ConfigManager.load_settings()
        # Chưa có settings.json: đừng tạo file chỉ có một khoá — main.py coi settings
        # khác rỗng là "đã cài đặt" và bỏ qua màn hình thiết lập.
        if settings:
            settings["legacy_config_migrated"] = legacy_path_key(legacy_dir)
            if not _cfg.ConfigManager.save_settings(settings):
                return 1
        log.info("Chuyển cấu hình bản cũ %s: %s", legacy_dir, "có ghi" if wrote else "không có gì khác")
        return 0
    except Exception:
        log.exception("Chuyển cấu hình bản cũ %s lỗi", legacy_dir)
        return 1
```

- [ ] **Step 6: Chạy lại**

Run: lệnh Step 3.
Expected: tất cả PASS.

- [ ] **Step 7: Commit**

```bash
git add ui/dialogs/first_run_dialog.py core/first_run.py tests/ui/test_first_run_dialog.py tests/core/test_first_run.py
git commit -m "fix(first-run): chuyển cấu hình cũ lỗi thì không cho dọn bản cũ; test hộp thoại không gọi migrate thật; migrate_cli cho bộ cài cầu nối"
```

---

### Task 3: `core/updater/velopack_updater.py` — kiểm, tải sẵn, áp dụng khi thoát

Module thuần (không Qt, import `velopack` trễ) để test bằng manager giả.

**Files:**
- Create: `core/updater/velopack_updater.py`
- Test: `tests/core/test_velopack_updater.py`

**Interfaces:**
- Consumes: `core.first_run.is_velopack_install(app_dir) -> bool`.
- Produces (Task 4, 5 dùng):
  - `CHECK_DELAY_S = 60`, `CHECK_INTERVAL_S = 21600`
  - `feed_url(base: str, fingerprint: str) -> str | None`
  - `make_manager(url: str, timeout_ms: int)` → `velopack.UpdateManager`
  - `class UpdateState` (dataclass: `pending: str|None`, `downloading: str|None`, `checked_at: float|None`, `error: bool`)
  - `class BackgroundUpdater(url, auto_check: Callable[[], bool], manager_factory=make_manager, clock=time.time, wait=None)` với `.state`, `.check_once()`, `.run()`, `.stop()`, `.apply_on_exit() -> bool`
  - `start_background_updates(app_dir, base_url, fingerprint, auto_check, manager_factory=make_manager, start_thread=True) -> BackgroundUpdater | None`
  - `get_updater() -> BackgroundUpdater | None`
  - `apply_pending_on_exit() -> bool`
  - `status_text(version: str, updater, auto_check: bool = True) -> str`

- [ ] **Step 1: Viết test**

`tests/core/test_velopack_updater.py`:

```python
"""Cập nhật ngầm qua Velopack: kiểm → tải sẵn → áp dụng khi tắt app. Manager giả, không mạng."""
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.updater import velopack_updater as vu

FP = "a" * 64
BASE = "https://qlstudio.duckdns.org"


class FakeManager:
    def __init__(self, target=None, pending=None, check_exc=None, download_exc=None):
        self.target, self.pending = target, pending
        self.check_exc, self.download_exc = check_exc, download_exc
        self.downloaded, self.applied = [], []

    def check_for_updates(self):
        if self.check_exc:
            raise self.check_exc
        if self.target is None:
            return None
        return SimpleNamespace(TargetFullRelease=SimpleNamespace(Version=self.target))

    def download_updates(self, info, progress_callback=None):
        if self.download_exc:
            raise self.download_exc
        self.downloaded.append(info.TargetFullRelease.Version)
        self.pending = info.TargetFullRelease.Version

    def get_update_pending_restart(self):
        return None if self.pending is None else SimpleNamespace(Version=self.pending)

    def wait_exit_then_apply_updates(self, asset, silent=False, restart=True, restart_args=None):
        self.applied.append((asset.Version, silent, restart))


def _updater(mgr, auto=True):
    calls = []

    def factory(url, timeout_ms):
        calls.append((url, timeout_ms))
        return mgr
    u = vu.BackgroundUpdater(f"{BASE}/api/v1/updates/velopack/{FP}", lambda: auto,
                             manager_factory=factory, clock=lambda: 1000.0)
    return u, calls


# ── feed_url ──
def test_feed_url_dung_dinh_dang():
    assert vu.feed_url(BASE + "/", FP) == f"{BASE}/api/v1/updates/velopack/{FP}"


@pytest.mark.parametrize("base,fp", [("", FP), ("  ", FP), (BASE, ""), (BASE, "a b"), (BASE, "../x"), (BASE, "a" * 129)])
def test_feed_url_khong_hop_le_tra_none(base, fp):
    assert vu.feed_url(base, fp) is None


# ── check_once ──
def test_co_ban_moi_thi_tai_san():
    mgr = FakeManager(target="1.9.1")
    u, calls = _updater(mgr)
    u.check_once()
    assert mgr.downloaded == ["1.9.1"]
    assert u.state.pending == "1.9.1" and u.state.downloading is None
    assert u.state.checked_at == 1000.0 and u.state.error is False
    # hỏi feed bằng timeout ngắn, tải bằng timeout dài
    assert calls[0][1] == vu.CHECK_TIMEOUT_MS and calls[-1][1] == vu.DOWNLOAD_TIMEOUT_MS


def test_khong_co_ban_moi_khong_tai():
    mgr = FakeManager(target=None)
    u, _ = _updater(mgr)
    u.check_once()
    assert mgr.downloaded == [] and u.state.pending is None and u.state.checked_at == 1000.0


def test_ban_da_tai_san_khong_tai_lai():
    mgr = FakeManager(target="1.9.1", pending="1.9.1")
    u, _ = _updater(mgr)
    u.check_once()
    u.check_once()
    assert mgr.downloaded == [] and u.state.pending == "1.9.1"


def test_loi_mang_danh_dau_va_thu_lai():
    mgr = FakeManager(target="1.9.1", check_exc=OSError("timeout"))
    u, _ = _updater(mgr)
    u.check_once()   # không ném
    assert u.state.error is True and u.state.pending is None
    mgr.check_exc = None
    u.check_once()
    assert u.state.error is False and u.state.pending == "1.9.1"


def test_loi_khi_tai_khong_ghi_pending():
    mgr = FakeManager(target="1.9.1", download_exc=OSError("đứt mạng"))
    u, _ = _updater(mgr)
    u.check_once()
    assert u.state.pending is None and u.state.downloading is None and u.state.error is True


def test_hai_luot_cung_luc_chi_mot_luot_chay():
    mgr = FakeManager(target="1.9.1")
    u, _ = _updater(mgr)
    u._lock.acquire()
    try:
        u.check_once()   # lượt khác đang chạy → bỏ qua ngay, không chờ
    finally:
        u._lock.release()
    assert mgr.downloaded == []


# ── run: lịch 60 s rồi 6 giờ, tôn trọng auto_check ──
def test_lich_kiem_tra_va_auto_check():
    mgr = FakeManager(target=None)
    waits = []
    flags = iter([True, False, True])

    def fake_wait(seconds):
        waits.append(seconds)
        return len(waits) > 3          # dừng sau lần chờ thứ 4

    u = vu.BackgroundUpdater("u", lambda: next(flags), manager_factory=lambda *_: mgr, wait=fake_wait)
    with patch.object(u, "check_once", wraps=u.check_once) as chk:
        u.run()
    assert waits == [vu.CHECK_DELAY_S, vu.CHECK_INTERVAL_S, vu.CHECK_INTERVAL_S, vu.CHECK_INTERVAL_S]
    assert chk.call_count == 2         # lượt 2 bị auto_check=False bỏ qua


# ── apply_on_exit ──
def test_ap_dung_khi_thoat_co_ban_cho():
    mgr = FakeManager(pending="1.9.1")
    u, _ = _updater(mgr)
    assert u.apply_on_exit() is True
    assert mgr.applied == [("1.9.1", True, False)]


def test_ap_dung_khi_thoat_khong_co_ban_cho_khong_lam_gi():
    mgr = FakeManager(pending=None)
    u, _ = _updater(mgr)
    assert u.apply_on_exit() is False and mgr.applied == []


def test_ap_dung_khi_thoat_loi_khong_nem():
    mgr = FakeManager(pending="1.9.1")
    mgr.wait_exit_then_apply_updates = lambda *a, **k: (_ for _ in ()).throw(OSError("x"))
    u, _ = _updater(mgr)
    assert u.apply_on_exit() is False


# ── start_background_updates / apply_pending_on_exit ──
def test_khong_phai_velopack_khong_chay(tmp_path):
    with patch.object(vu, "_updater", None):
        assert vu.start_background_updates(str(tmp_path), BASE, FP, lambda: True,
                                           manager_factory=lambda *_: FakeManager()) is None
        assert vu.get_updater() is None
        assert vu.apply_pending_on_exit() is False


def test_ban_velopack_khoi_dong_luong(tmp_path):
    cur = tmp_path / "QuangLuuStudio" / "current"
    cur.mkdir(parents=True)
    (tmp_path / "QuangLuuStudio" / "Update.exe").write_bytes(b"MZ")
    started = []
    with patch.object(vu, "_updater", None), \
         patch.object(vu.threading, "Thread",
                      side_effect=lambda **kw: SimpleNamespace(start=lambda: started.append(kw["name"]))):
        u = vu.start_background_updates(str(cur), BASE, FP, lambda: True,
                                        manager_factory=lambda *_: FakeManager())
        assert u is vu.get_updater() and u is not None
    assert started == ["velopack-update"]


def test_ban_velopack_thieu_url_khong_chay(tmp_path):
    cur = tmp_path / "QuangLuuStudio" / "current"
    cur.mkdir(parents=True)
    (tmp_path / "QuangLuuStudio" / "Update.exe").write_bytes(b"MZ")
    with patch.object(vu, "_updater", None):
        assert vu.start_background_updates(str(cur), "", FP, lambda: True) is None


# ── status_text ──
def test_status_text_cac_truong_hop():
    assert "không tự cập nhật" in vu.status_text("1.9.0", None)
    u, _ = _updater(FakeManager())
    assert "khoảng 1 phút" in vu.status_text("1.9.0", u)
    u.state.checked_at = 0.0
    assert "đã là bản mới nhất" in vu.status_text("1.9.0", u)
    u.state.error = True
    assert "chưa kết nối được" in vu.status_text("1.9.0", u)
    assert "đang tắt" in vu.status_text("1.9.0", u, auto_check=False)
    u.state.downloading = "1.9.1"
    assert "đang tải bản 1.9.1" in vu.status_text("1.9.0", u)
    u.state.pending = "1.9.1"
    assert vu.status_text("1.9.0", u) == "Đang dùng 1.9.0 — đã tải sẵn 1.9.1, sẽ dùng ở lần mở sau."
```

- [ ] **Step 2: Chạy, thấy hỏng**

Run: `cmd.exe /c "cd /d D:\Projects\quang-luu-studio && .venv\Scripts\python.exe -m pytest tests\core\test_velopack_updater.py -q -p no:cacheprovider"`
Expected: FAIL — `ImportError: cannot import name 'velopack_updater'`.

- [ ] **Step 3: Viết module**

`core/updater/velopack_updater.py`:

```python
"""Cập nhật ngầm qua Velopack: kiểm → tải sẵn → áp dụng khi tắt app.

Chỉ chạy trên bản cài Velopack (%LocalAppData%\\QuangLuuStudio\\current, có
Update.exe ở thư mục cha). Nguồn duy nhất là feed của server — server quyết định
máy nào nhận bản nào (is_active, rollout_percent); KHÔNG có đường dự phòng GitHub.
Không hộp thoại: bản mới chỉ được tải sẵn, áp dụng khi app tắt bình thường
(hoặc Velopack tự áp dụng ở lần mở sau nếu app bị tắt ngang).
"""
import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

CHECK_DELAY_S = 60                       # chờ app mở xong rồi mới kiểm lần đầu
CHECK_INTERVAL_S = 6 * 3600              # máy hát mở liên tục nhiều ngày
CHECK_TIMEOUT_MS = 30_000                # hỏi feed: mạng treo thì bỏ, lần sau thử lại
DOWNLOAD_TIMEOUT_MS = 3 * 3600 * 1000    # gói Full ~550 MB qua 4G chập chờn
_FP_RE = re.compile(r"[A-Za-z0-9_-]{1,128}")   # khớp valid_fingerprint của server

_updater = None


def feed_url(base, fingerprint):
    base = str(base or "").strip().rstrip("/")
    if not base or not _FP_RE.fullmatch(fingerprint or ""):
        return None
    return f"{base}/api/v1/updates/velopack/{fingerprint}"


def make_manager(url, timeout_ms):
    import velopack   # import trễ: test và bản chạy từ mã nguồn không cần
    return velopack.UpdateManager(velopack.HttpSource(url, velopack.HttpOptions([], timeout_ms)))


@dataclass
class UpdateState:
    pending: Optional[str] = None       # đã tải sẵn, dùng ở lần mở sau
    downloading: Optional[str] = None
    checked_at: Optional[float] = None  # lần hỏi feed thành công gần nhất
    error: bool = False                 # lượt gần nhất lỗi (mạng, server, tải)


class BackgroundUpdater:
    def __init__(self, url, auto_check, manager_factory=make_manager, clock=time.time, wait=None):
        self._url = url
        self._auto_check = auto_check
        self._factory = manager_factory
        self._clock = clock
        self._stop = threading.Event()
        self._wait = wait or self._stop.wait   # trả True khi được yêu cầu dừng
        self._lock = threading.Lock()          # một lượt kiểm/tải tại một thời điểm
        self.state = UpdateState()

    def check_once(self):
        """Một lượt: hỏi feed, có bản mới thì tải sẵn. Không bao giờ ném lỗi."""
        if not self._lock.acquire(blocking=False):
            return
        try:
            mgr = self._factory(self._url, CHECK_TIMEOUT_MS)
            if self.state.pending is None:
                waiting = mgr.get_update_pending_restart()   # tải từ phiên trước, chưa áp dụng
                if waiting is not None:
                    self.state.pending = waiting.Version
            info = mgr.check_for_updates()
            self.state.checked_at = self._clock()
            self.state.error = False
            if info is None:
                return
            target = info.TargetFullRelease.Version
            if target == self.state.pending:
                return
            self.state.downloading = target
            log.info("Có bản %s — tải ngầm", target)
            self._factory(self._url, DOWNLOAD_TIMEOUT_MS).download_updates(info)
            self.state.pending = target
            log.info("Đã tải sẵn bản %s — sẽ dùng ở lần mở sau", target)
        except Exception as e:
            self.state.error = True
            log.warning("Kiểm tra/tải bản cập nhật lỗi (sẽ thử lại): %s", e)
        finally:
            self.state.downloading = None
            self._lock.release()

    def run(self):
        """Thân luồng nền: chờ CHECK_DELAY_S, rồi cứ CHECK_INTERVAL_S một lượt."""
        if self._wait(CHECK_DELAY_S):
            return
        while True:
            try:
                enabled = self._auto_check()
            except Exception:
                enabled = True
            if enabled:
                self.check_once()
            if self._wait(CHECK_INTERVAL_S):
                return

    def stop(self):
        self._stop.set()

    def apply_on_exit(self):
        """App tắt bình thường: có bản đã tải xong → Update.exe áp dụng im lặng sau khi
        tiến trình này thoát, không mở lại app. True nếu đã giao việc áp dụng."""
        try:
            mgr = self._factory(self._url, CHECK_TIMEOUT_MS)
            asset = mgr.get_update_pending_restart()
            if asset is None:
                return False
            mgr.wait_exit_then_apply_updates(asset, silent=True, restart=False)
            log.info("Sẽ áp dụng bản %s sau khi app thoát", asset.Version)
            return True
        except Exception as e:
            log.warning("Không giao được việc áp dụng bản cập nhật: %s", e)
            return False


def start_background_updates(app_dir, base_url, fingerprint, auto_check,
                             manager_factory=make_manager, start_thread=True):
    """Khởi động luồng cập nhật nền nếu đây là bản cài Velopack. Trả updater hoặc None."""
    global _updater
    from core import first_run
    if not first_run.is_velopack_install(app_dir):
        log.info("Không phải bản cài Velopack — không tự cập nhật")
        return None
    url = feed_url(base_url, fingerprint)
    if url is None:
        log.warning("Thiếu license_server_url hoặc mã máy không hợp lệ — không tự cập nhật")
        return None
    _updater = BackgroundUpdater(url, auto_check, manager_factory)
    if start_thread:
        threading.Thread(target=_updater.run, daemon=True, name="velopack-update").start()
    return _updater


def get_updater():
    return _updater


def apply_pending_on_exit():
    u = _updater
    return u.apply_on_exit() if u is not None else False


def status_text(version, updater, auto_check=True):
    head = f"Đang dùng {version}"
    if updater is None:
        return f"{head} — bản này không tự cập nhật (chạy từ mã nguồn hoặc bản cài cũ)."
    s = updater.state
    if s.pending:
        return f"{head} — đã tải sẵn {s.pending}, sẽ dùng ở lần mở sau."
    if s.downloading:
        return f"{head} — đang tải bản {s.downloading}…"
    if not auto_check:
        return f"{head} — tự cập nhật đang tắt."
    if s.error:
        return f"{head} — chưa kết nối được máy chủ cập nhật, sẽ thử lại sau."
    if s.checked_at is not None:
        when = time.strftime("%H:%M %d/%m", time.localtime(s.checked_at))
        return f"{head} — đã là bản mới nhất (kiểm lúc {when})."
    return f"{head} — sẽ kiểm tra bản mới khoảng 1 phút sau khi mở app."
```

- [ ] **Step 4: Chạy lại**

Run: lệnh Step 2.
Expected: tất cả PASS (module `core/updater/__init__.py` cũ vẫn import được `_version_check` … — chưa đụng ở task này).

- [ ] **Step 5: Commit**

```bash
git add core/updater/velopack_updater.py tests/core/test_velopack_updater.py
git commit -m "feat(updater): cập nhật ngầm qua Velopack — kiểm 60 s sau khi mở rồi mỗi 6 giờ, tải sẵn, áp dụng khi tắt app"
```

---

### Task 4: Nối Velopack vào app; bỏ bộ cập nhật cũ và hộp thoại cập nhật

**Files:**
- Modify: `main.py` (đầu file; khối `--thu-tai` ~dòng 108-116; khối "Update check" ~dòng 193-252; `main()` ~dòng 440-450; `finally` cuối file)
- Modify: `core/updater/__init__.py` (viết lại)
- Delete: `core/updater/_downloader.py`, `core/updater/_installer.py`, `core/updater/_verifier.py`, `core/updater/_version_check.py`, `ui/dialogs/update_dialog.py`
- Modify: `ui/dialogs/settings_dialog.py` (`_build_update_tools` ~dòng 1337-1379; xoá `_format_last_update_check`, `_action_check_for_updates`, `_on_update_check_done` ~dòng 1380-1471)
- Modify: `QuangLuuStudio.spec` (hiddenimports: thay `'ui.dialogs.update_dialog'`)
- Modify: `requirements.txt`
- Modify: comment nhắc `_version_check.py` trong `main.py` (~dòng 167-170) và `core/capabilities.py:18`
- Test: `tests/test_main_velopack.py` (mới), `tests/ui/test_settings_update_status.py` (mới)

**Interfaces:**
- Consumes: Task 3 `start_background_updates`, `get_updater`, `apply_pending_on_exit`, `status_text`; Task 2 `first_run.migrate_cli`; `core.config.APP_DIR`, `AppConfig.get("license_server_url")`, `core.licensing.device.get_fingerprint()`.
- Produces: `core.updater` export `start_background_updates, get_updater, apply_pending_on_exit, status_text`. Cờ dòng lệnh `--chuyen-cau-hinh-cu <thư mục>` (Task 8 dùng). `SettingsDialog._update_status_lbl` (QLabel trạng thái).

- [ ] **Step 1: Test tĩnh cho `main.py` + test giao diện trạng thái**

`tests/test_main_velopack.py`:

```python
"""main.py: Velopack phải xử lý hook --veloapp-* trước mọi import nặng; không còn bộ cập nhật cũ."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _main():
    with open(os.path.join(ROOT, "main.py"), encoding="utf-8") as f:
        return f.read()


def test_velopack_chay_truoc_import_nang():
    src = _main()
    i = src.index("velopack.App().run()")
    for heavy in ("from PySide6", "import backend", "from core.logger", "import frontend_qt"):
        assert i < src.index(heavy), heavy


def test_co_lenh_chuyen_cau_hinh_cu_truoc_qt():
    src = _main()
    assert src.index('"--chuyen-cau-hinh-cu"') < src.index("import backend")
    assert "migrate_cli" in src


def test_ap_dung_ban_cho_truoc_khi_thoat():
    src = _main()
    tail = src[src.index('if __name__ == "__main__":'):]
    assert tail.index("apply_pending_on_exit()") < tail.index("os._exit(0)")


def test_khong_con_bo_cap_nhat_cu():
    src = _main()
    for old in ("UpdateDialog", "check_and_notify_update", "_schedule_update_check", "last_check_timestamp"):
        assert old not in src, old
    for f in ("_downloader.py", "_installer.py", "_verifier.py", "_version_check.py"):
        assert not os.path.exists(os.path.join(ROOT, "core", "updater", f)), f
    assert not os.path.exists(os.path.join(ROOT, "ui", "dialogs", "update_dialog.py"))


def test_requirements_ghim_velopack_cung_so_voi_vpk():
    with open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8") as f:
        assert "velopack==1.2.161" in f.read()
```

`tests/ui/test_settings_update_status.py`:

```python
"""Cài đặt → Cập nhật phần mềm: chỉ còn dòng trạng thái, không còn nút/hộp thoại cập nhật."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PySide6.QtWidgets")

from frontend_qt import MainDashboard
from ui.dialogs.settings_dialog import SettingsDialog
from core.updater import velopack_updater as vu

A11Y_CFG = {
    "tts_enabled": False, "tts_engine": "sapi", "tts_voice": "", "tts_rate": 170,
    "voice_command_enabled": False, "voice_model": "small",
    "high_contrast": False, "focus_ring_thick": False, "font_scale": 1.0,
    "announce_focus": True, "announce_state": True,
}


@pytest.fixture(autouse=True)
def _khong_ghi_settings_that():
    with patch("frontend_qt.backend.ConfigManager.save_settings"):
        yield


@pytest.fixture
def mock_engine():
    with patch("frontend_qt.backend.SystemEngine") as mock_eng:
        eng = mock_eng.return_value
        eng.current_youtube_url = "http://yt.com"
        eng.tone_detection_active = False
        eng.autokey_active = False
        eng._youtube_watcher_active = False
        eng._tone_session = MagicMock()
        eng._tone_session.is_active = False
        yield eng


def _open(qtbot, updater):
    with patch("frontend_qt.backend.SongManager.load_songs", return_value=[]), \
         patch("frontend_qt.backend.ActivationManager.is_activated", return_value=True), \
         patch("frontend_qt.backend.ActivationManager.needs_activation", return_value=False), \
         patch("core.entitlements.is_premium", return_value=True), \
         patch("frontend_qt.QTimer.start"):
        dashboard = MainDashboard({"studio_one_path": "", "auto_close_studio_one": False})
        qtbot.addWidget(dashboard)
        if dashboard._so_ready_watcher is not None:
            dashboard._so_ready_watcher.stop()
    with patch("core.entitlements.is_premium", return_value=True), \
         patch("frontend_qt.backend.AppConfig.get_accessibility", return_value=dict(A11Y_CFG)), \
         patch("core.updater.velopack_updater._updater", updater):
        dlg = SettingsDialog(dashboard)
    qtbot.addWidget(dlg)
    return dlg


def test_trang_thai_cap_nhat_ban_cho(qtbot, mock_engine):
    u = vu.BackgroundUpdater("u", lambda: True, manager_factory=lambda *_: None)
    u.state.pending = "9.9.9"
    dlg = _open(qtbot, u)
    assert "đã tải sẵn 9.9.9, sẽ dùng ở lần mở sau" in dlg._update_status_lbl.text()
    assert not hasattr(dlg, "_update_check_btn")


def test_trang_thai_cap_nhat_ban_khong_velopack(qtbot, mock_engine):
    dlg = _open(qtbot, None)
    assert "không tự cập nhật" in dlg._update_status_lbl.text()
```

- [ ] **Step 2: Chạy, thấy hỏng**

Run: `cmd.exe /c "cd /d D:\Projects\quang-luu-studio && .venv\Scripts\python.exe -m pytest tests\test_main_velopack.py tests\ui\test_settings_update_status.py -q -p no:cacheprovider"`
Expected: FAIL — `velopack.App().run()` không có trong main.py; `_update_status_lbl` rỗng/không chứa chuỗi; `_update_check_btn` còn.

- [ ] **Step 3: `requirements.txt`**

Thêm sau khối numpy:

```
# Cài/cập nhật theo người dùng (%LocalAppData%). PHẢI cùng số với vpk trong
# .github/workflows/release.yml và trên máy build (dotnet tool vpk).
velopack==1.2.161
```

- [ ] **Step 4: `main.py` — đầu file**

Ngay sau khối import đầu (`import logging`), trước `# ── PyInstaller _MEI cleanup`, thêm:

```python
# ── Velopack — PHẢI chạy trước mọi import nặng ────────────────────────────────
# Setup.exe/Update.exe gọi exe với --veloapp-install/--veloapp-updated/... (hook chỉ
# có 30 giây, không được hiện giao diện): App().run() xử lý rồi tự thoát trước khi
# nạp Qt/numba. Có bản đã tải sẵn mà lần trước app bị tắt ngang → nó áp dụng luôn
# rồi mở lại app (VELOPACK_RESTART=true — không phải lần chạy đầu, không làm gì thêm).
# Chạy từ mã nguồn / bản Inno cũ: không có gì để làm, bỏ qua lỗi.
try:
    import velopack
    velopack.App().run()
except Exception:
    pass
```

- [ ] **Step 5: `main.py` — lệnh `--chuyen-cau-hinh-cu`**

Ngay sau khối `if "--thu-tai" in sys.argv: ...`, thêm:

```python
# Bộ cài cầu nối (máy 1.8.x → bản Velopack) gọi exe MỚI với cờ này, dưới quyền người
# dùng gốc, để chuyển app_config.json của bản Program Files sang lớp người dùng
# trước khi xoá bản cũ. Xem QuangLuuStudio_Bridge.iss.
if "--chuyen-cau-hinh-cu" in sys.argv:
    from core.first_run import migrate_cli
    _i = sys.argv.index("--chuyen-cau-hinh-cu")
    _ma_thoat = migrate_cli(sys.argv[_i + 1] if _i + 1 < len(sys.argv) else "")
    flush_logs()
    logging.shutdown()
    _cleanup_mei()
    os._exit(_ma_thoat)
```

- [ ] **Step 6: `main.py` — thay khối kiểm tra cập nhật cũ**

Xoá từ dòng `# ── Update check ──` tới hết hàm `_schedule_update_check` (gồm `class _UpdateNotifier`, `_show_update_dialog`, `_schedule_update_check`), giữ lại dòng `from PySide6.QtCore import QObject, Signal` (còn dùng cho `_LicenseNotifier`). Thay bằng:

```python
from PySide6.QtCore import QObject, Signal


# ── Cập nhật ngầm (Velopack) ──────────────────────────────────────────────────

def _auto_check_enabled():
    settings = backend.ConfigManager.load_settings() or {}
    return bool((settings.get("update") or {}).get("auto_check", True))


def _start_updates():
    """Luồng nền kiểm/tải bản mới — chỉ trên bản cài Velopack (core/updater)."""
    try:
        from core.config import APP_DIR, AppConfig
        from core.licensing.device import get_fingerprint
        from core.updater import start_background_updates
        start_background_updates(APP_DIR, AppConfig.get("license_server_url", ""),
                                 get_fingerprint(), _auto_check_enabled)
    except Exception:
        log.exception("Không khởi động được cập nhật ngầm")
```

Trong `main()`, thay đoạn

```python
            dashboard = frontend_qt.MainDashboard(settings)
            notifier = _UpdateNotifier()
            notifier.update_available.connect(_show_update_dialog)
            threading.Thread(
                target=_schedule_update_check, args=(notifier,), daemon=True
            ).start()
```

bằng

```python
            dashboard = frontend_qt.MainDashboard(settings)
            _start_updates()
```

và sửa comment phía trên ("Tạo dashboard TRƯỚC (đảm bảo QApplication tồn tại) rồi mới tạo notifier + thread check update…") thành `# Tạo dashboard TRƯỚC (đảm bảo QApplication tồn tại) rồi mới chạy các luồng nền.`

Trong comment khối "Biến thể build" (~dòng 165-170) bỏ vế "lại còn quyết định app tự tải file cài nào khi cập nhật (core/updater/_version_check.py)", câu kết thúc ở "…mà hai ca đó chữa khác hẳn nhau."

- [ ] **Step 7: `main.py` — áp dụng khi thoát**

Trong khối `finally` cuối file, trước `log.info("App exiting — log dir: %s", _LOG_DIR)`:

```python
        # Bản mới đã tải sẵn → Update.exe áp dụng im lặng sau khi tiến trình này thoát.
        try:
            from core.updater import apply_pending_on_exit
            apply_pending_on_exit()
        except Exception:
            log.exception("Không giao được việc áp dụng bản cập nhật")
```

- [ ] **Step 8: `core/updater/__init__.py` + xoá file cũ**

Viết lại `core/updater/__init__.py`:

```python
"""core.updater — cập nhật ngầm qua Velopack (xem velopack_updater.py)."""
from core.updater.velopack_updater import (  # noqa: F401
    apply_pending_on_exit,
    get_updater,
    start_background_updates,
    status_text,
)

__all__ = ["start_background_updates", "get_updater", "apply_pending_on_exit", "status_text"]
```

```bash
git rm core/updater/_downloader.py core/updater/_installer.py core/updater/_verifier.py core/updater/_version_check.py ui/dialogs/update_dialog.py
```

`core/capabilities.py:18`: đổi tham chiếu `core/updater/_version_check.py` trong docstring thành "bộ cập nhật cũ (≤ 1.8, đã bỏ ở 1.9.0)" — giữ nguyên ý còn lại của câu.

- [ ] **Step 9: Cài đặt — dòng trạng thái**

Trong `ui/dialogs/settings_dialog.py` thay nguyên `_build_update_tools` bằng:

```python
    def _build_update_tools(self, vl):
        from core.version import __version__
        from core.updater import get_updater, status_text

        version_lbl = QLabel(f"Phiên bản hiện tại: <b>{__version__}</b>")
        version_lbl.setStyleSheet(self._field_label_qss(size=12, weight=600))
        version_lbl.setTextFormat(Qt.RichText)
        vl.addWidget(version_lbl)

        # Cập nhật chạy ngầm (core/updater): không nút, không hộp thoại — chỉ báo trạng thái.
        auto = bool((self._dashboard.settings or {}).get("update", {}).get("auto_check", True))
        self._update_status_lbl = QLabel(status_text(__version__, get_updater(), auto_check=auto))
        self._update_status_lbl.setStyleSheet(self._field_label_qss(size=11, weight=500, italic=True))
        self._update_status_lbl.setWordWrap(True)
        vl.addWidget(self._update_status_lbl)
```

Xoá hẳn ba hàm `_format_last_update_check`, `_action_check_for_updates`, `_on_update_check_done`. Nếu `SVG_SEARCH` không còn chỗ nào dùng trong file thì bỏ khỏi khối import (kiểm bằng `grep -n SVG_SEARCH ui/dialogs/settings_dialog.py`).

- [ ] **Step 10: `QuangLuuStudio.spec`**

Trong `hiddenimports` thay `'ui.dialogs.update_dialog',` bằng:

```python
    'ui.dialogs.first_run_dialog',
    # Velopack: import trong khối try ở đầu main.py + import trễ trong core/updater
    'velopack',
    'core.updater.velopack_updater',
```

- [ ] **Step 11: Chạy test của task + các test đụng tới settings/main**

Run: `cmd.exe /c "cd /d D:\Projects\quang-luu-studio && .venv\Scripts\python.exe -m pytest tests\test_main_velopack.py tests\ui\test_settings_update_status.py tests\core\test_velopack_updater.py tests\ui\test_settings_daw_kind.py tests\core\test_capabilities.py -q -p no:cacheprovider"`
Expected: tất cả PASS. Thêm: `git grep -n "update_dialog\|_version_check\|check_latest_release\|download_and_install" -- '*.py'` → không còn kết quả.

- [ ] **Step 12: Commit**

```bash
git add main.py core/updater/__init__.py core/capabilities.py ui/dialogs/settings_dialog.py QuangLuuStudio.spec requirements.txt tests/test_main_velopack.py tests/ui/test_settings_update_status.py
git commit -m "feat(app): Velopack App().run() đầu main.py, cập nhật ngầm + áp dụng khi tắt app, lệnh --chuyen-cau-hinh-cu; bỏ bộ cập nhật cũ (GitHub, hộp thoại, UAC) — Cài đặt chỉ còn dòng trạng thái"
```

---

### Task 5: Nút trong app thay shortcut `.bat`; "Xoá dữ liệu"

Velopack chỉ tạo shortcut cho exe chính, nên ba shortcut Start Menu cũ (Kiểm tra dò tone, Cấu hình YouTube Cookies, thư mục Recordings) chuyển thành nút trong Cài đặt → Công cụ. Cookie đã có sẵn thẻ "YouTube Cookie". Gỡ cài đặt giữ dữ liệu, nên thêm "Xoá dữ liệu" cho ai cần: xoá `%APPDATA%\QuangLuuStudio` (và tuỳ chọn `Documents\QuangLuuStudio`) **sau khi app thoát** — lúc đang chạy thì log và các file đang mở khoá thư mục.

**Files:**
- Create: `core/app_tools.py`
- Modify: `ui/dialogs/settings_dialog.py` (`_build_tools_tab` cột trái; thêm `_build_diag_tools`, `_action_wipe_data`, hàm module `_ask_wipe`)
- Test: `tests/core/test_app_tools.py`, `tests/ui/test_settings_tools_card.py`

**Interfaces:**
- Consumes: `core.config.APP_DIR`, `core.config.DATA_DIR`, `core.config._get_recordings_dir()`.
- Produces:
  - `app_tools.launch_bat(app_dir: str, name: str, popen=subprocess.Popen) -> bool`
  - `app_tools.open_folder(path: str, opener=None) -> bool`
  - `app_tools.wipe_targets(data_dir: str, recordings_dir: str, include_recordings: bool, frozen: bool) -> list[str]`
  - `app_tools.build_wipe_command(pid: int, targets: list[str]) -> list[str]`
  - `app_tools.schedule_wipe_after_exit(targets: list[str], popen=subprocess.Popen, pid=None) -> bool`

- [ ] **Step 1: Test lõi**

`tests/core/test_app_tools.py`:

```python
"""Công cụ trong app thay shortcut .bat + xoá dữ liệu sau khi app thoát."""
import base64
import os

import pytest

from core import app_tools


def test_chay_bat_dung_cwd(tmp_path):
    app = tmp_path / "Nguyễn (A) & B"
    app.mkdir()
    (app / "kiem_tra_tone.bat").write_text("@echo off", encoding="ascii")
    calls = []
    assert app_tools.launch_bat(str(app), "kiem_tra_tone.bat",
                                popen=lambda args, **kw: calls.append((args, kw))) is True
    args, kw = calls[0]
    # tên .bat đứng một mình, thư mục qua cwd → ký tự ( ) & trong đường dẫn không vỡ lệnh cmd
    assert args == ["cmd.exe", "/c", "kiem_tra_tone.bat"]
    assert kw["cwd"] == str(app)


def test_chay_bat_thieu_file(tmp_path):
    assert app_tools.launch_bat(str(tmp_path), "khong_co.bat", popen=lambda *a, **k: None) is False


def test_mo_thu_muc(tmp_path):
    opened = []
    assert app_tools.open_folder(str(tmp_path), opener=opened.append) is True
    assert opened == [str(tmp_path)]
    assert app_tools.open_folder(str(tmp_path / "khong_co"), opener=opened.append) is False


def _dirs(tmp_path):
    data = tmp_path / "Roaming" / "QuangLuuStudio"
    rec = tmp_path / "Documents" / "QuangLuuStudio"
    data.mkdir(parents=True)
    rec.mkdir(parents=True)
    return str(data), str(rec)


def test_dich_xoa_mac_dinh_chi_du_lieu(tmp_path):
    data, rec = _dirs(tmp_path)
    assert app_tools.wipe_targets(data, rec, False, frozen=True) == [os.path.abspath(data)]
    assert app_tools.wipe_targets(data, rec, True, frozen=True) == [os.path.abspath(data), os.path.abspath(rec)]


def test_khong_xoa_khi_chay_tu_ma_nguon(tmp_path):
    data, rec = _dirs(tmp_path)
    assert app_tools.wipe_targets(data, rec, True, frozen=False) == []


@pytest.mark.parametrize("name", ["quang-luu-studio", "AppData", ""])
def test_khong_xoa_thu_muc_ten_la(tmp_path, name):
    d = tmp_path / name if name else tmp_path
    assert app_tools.wipe_targets(str(d), str(d), True, frozen=True) == []


def test_lenh_xoa_du_lieu_duong_dan_co_nhay_don():
    targets = [r"C:\Users\O'Brien Văn\AppData\Roaming\QuangLuuStudio"]
    cmd = app_tools.build_wipe_command(4242, targets)
    assert cmd[:4] == ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden"]
    assert cmd[4] == "-EncodedCommand"
    script = base64.b64decode(cmd[5]).decode("utf-16-le")
    assert "Wait-Process -Id 4242" in script
    assert r"Remove-Item -LiteralPath 'C:\Users\O''Brien Văn\AppData\Roaming\QuangLuuStudio' -Recurse -Force" in script


def test_hen_xoa_sau_khi_thoat(tmp_path):
    data, rec = _dirs(tmp_path)
    calls = []
    assert app_tools.schedule_wipe_after_exit([data], popen=lambda a, **k: calls.append((a, k)), pid=7) is True
    assert calls[0][0][0] == "powershell.exe"
    assert app_tools.schedule_wipe_after_exit([], popen=lambda a, **k: calls.append(a)) is False
```

- [ ] **Step 2: Chạy, thấy hỏng**

Run: `cmd.exe /c "cd /d D:\Projects\quang-luu-studio && .venv\Scripts\python.exe -m pytest tests\core\test_app_tools.py -q -p no:cacheprovider"`
Expected: FAIL — `ImportError: cannot import name 'app_tools'`.

- [ ] **Step 3: Viết `core/app_tools.py`**

```python
"""Công cụ mở từ Cài đặt → Công cụ.

Thay các shortcut Start Menu của bộ cài Inno cũ (Velopack chỉ tạo shortcut cho exe
chính) và thêm "Xoá dữ liệu" — gỡ cài đặt Velopack cố ý GIỮ %APPDATA% và Documents.
Không đụng Qt để test được.
"""
import base64
import logging
import os
import subprocess

log = logging.getLogger(__name__)

DATA_FOLDER_NAME = "QuangLuuStudio"
_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
_DETACHED = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


def launch_bat(app_dir, name, popen=subprocess.Popen):
    """Mở <app_dir>\\<name> trong cửa sổ console riêng (.bat tự `pause` ở cuối)."""
    if not os.path.isfile(os.path.join(app_dir, name)):
        log.warning("Thiếu %s trong %s", name, app_dir)
        return False
    # Tên .bat đứng riêng + cwd: đường dẫn có ( ) & không làm vỡ dòng lệnh cmd.
    popen(["cmd.exe", "/c", name], cwd=app_dir, creationflags=_NEW_CONSOLE)
    return True


def open_folder(path, opener=None):
    if not os.path.isdir(path):
        return False
    (opener or os.startfile)(path)
    return True


def wipe_targets(data_dir, recordings_dir, include_recordings, frozen):
    """Thư mục sẽ xoá. Chỉ bản đóng gói (chạy từ mã nguồn DATA_DIR = gốc repo!), và chỉ
    thư mục tên đúng "QuangLuuStudio" — không bao giờ một thư mục cha/gốc ổ."""
    if not frozen:
        return []
    out = []
    for d in [data_dir] + ([recordings_dir] if include_recordings else []):
        p = os.path.abspath(d or "")
        if os.path.basename(p.rstrip("\\/")) == DATA_FOLDER_NAME and os.path.isdir(p):
            out.append(p)
    return out


def build_wipe_command(pid, targets):
    """PowerShell (ẩn): chờ tiến trình `pid` thoát rồi xoá từng thư mục."""
    lit = lambda s: "'" + s.replace("'", "''") + "'"  # noqa: E731 — chuỗi PowerShell nháy đơn
    lines = [f"Wait-Process -Id {int(pid)} -ErrorAction SilentlyContinue"]
    lines += [f"Remove-Item -LiteralPath {lit(t)} -Recurse -Force -ErrorAction SilentlyContinue"
              for t in targets]
    enc = base64.b64encode("; ".join(lines).encode("utf-16-le")).decode("ascii")
    return ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-EncodedCommand", enc]


def schedule_wipe_after_exit(targets, popen=subprocess.Popen, pid=None):
    if not targets:
        return False
    popen(build_wipe_command(pid or os.getpid(), targets), creationflags=_DETACHED, close_fds=True)
    log.warning("Đã hẹn xoá dữ liệu sau khi app thoát: %s", targets)
    return True
```

- [ ] **Step 4: Chạy lại**

Run: lệnh Step 2. Expected: PASS.

- [ ] **Step 5: Test thẻ Công cụ chẩn đoán**

`tests/ui/test_settings_tools_card.py`:

```python
"""Cài đặt → Công cụ: nút chẩn đoán gọi đúng .bat; Xoá dữ liệu chỉ hẹn xoá khi khách đồng ý."""
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt

pytest.importorskip("PySide6.QtWidgets")

from frontend_qt import MainDashboard
from ui.dialogs.settings_dialog import SettingsDialog

A11Y_CFG = {
    "tts_enabled": False, "tts_engine": "sapi", "tts_voice": "", "tts_rate": 170,
    "voice_command_enabled": False, "voice_model": "small",
    "high_contrast": False, "focus_ring_thick": False, "font_scale": 1.0,
    "announce_focus": True, "announce_state": True,
}


@pytest.fixture(autouse=True)
def _khong_ghi_settings_that():
    with patch("frontend_qt.backend.ConfigManager.save_settings"):
        yield


@pytest.fixture
def dlg(qtbot):
    with patch("frontend_qt.backend.SystemEngine") as mock_eng:
        eng = mock_eng.return_value
        eng.current_youtube_url = "http://yt.com"
        eng.tone_detection_active = False
        eng.autokey_active = False
        eng._youtube_watcher_active = False
        eng._tone_session = MagicMock()
        eng._tone_session.is_active = False
        with patch("frontend_qt.backend.SongManager.load_songs", return_value=[]), \
             patch("frontend_qt.backend.ActivationManager.is_activated", return_value=True), \
             patch("frontend_qt.backend.ActivationManager.needs_activation", return_value=False), \
             patch("core.entitlements.is_premium", return_value=True), \
             patch("frontend_qt.QTimer.start"):
            dashboard = MainDashboard({"studio_one_path": "", "auto_close_studio_one": False})
            qtbot.addWidget(dashboard)
            if dashboard._so_ready_watcher is not None:
                dashboard._so_ready_watcher.stop()
        with patch("core.entitlements.is_premium", return_value=True), \
             patch("frontend_qt.backend.AppConfig.get_accessibility", return_value=dict(A11Y_CFG)):
            d = SettingsDialog(dashboard)
        qtbot.addWidget(d)
        yield d


@pytest.mark.parametrize("attr,bat", [("_btn_kiem_tra_tone", "kiem_tra_tone.bat"),
                                      ("_btn_thu_tai", "thu_tai_youtube.bat")])
def test_nut_chan_doan_chay_dung_bat(dlg, attr, bat):
    with patch("core.app_tools.launch_bat", return_value=True) as launch:
        qtbot_click(getattr(dlg, attr))
    assert launch.call_args.args[1] == bat


def test_xoa_du_lieu_khong_dong_y_thi_khong_hen(dlg):
    with patch("ui.dialogs.settings_dialog._ask_wipe", return_value=(False, False)), \
         patch("core.app_tools.schedule_wipe_after_exit") as sched:
        qtbot_click(dlg._btn_xoa_du_lieu)
    sched.assert_not_called()


def test_xoa_du_lieu_dong_y_thi_hen_xoa(dlg):
    with patch("ui.dialogs.settings_dialog._ask_wipe", return_value=(True, True)), \
         patch("core.app_tools.wipe_targets", return_value=["X:\\QuangLuuStudio"]) as tg, \
         patch("core.app_tools.schedule_wipe_after_exit", return_value=True) as sched:
        qtbot_click(dlg._btn_xoa_du_lieu)
    assert tg.call_args.args[2] is True          # có tích "cả bản thu"
    sched.assert_called_once_with(["X:\\QuangLuuStudio"])
    assert "đóng app" in dlg._lbl_xoa_du_lieu.text()


def qtbot_click(btn):
    btn.click()
```

- [ ] **Step 6: Chạy, thấy hỏng**

Run: `cmd.exe /c "cd /d D:\Projects\quang-luu-studio && .venv\Scripts\python.exe -m pytest tests\ui\test_settings_tools_card.py -q -p no:cacheprovider"`
Expected: FAIL — `AttributeError: 'SettingsDialog' object has no attribute '_btn_kiem_tra_tone'`.

- [ ] **Step 7: Thẻ "Công cụ chẩn đoán" trong Cài đặt**

Trong `ui/dialogs/settings_dialog.py`:

(a) Thêm `QMessageBox` vào khối `from PySide6.QtWidgets import (...)`; thêm `SVG_TRASH,` vào khối `from ui.components.svg_icons import (...)`.

(b) Trong `_build_tools_tab`, cột trái, sau hai dòng "Thư viện tone cộng đồng" và trước `left.addStretch()`:

```python
        left.addWidget(self._section_header(SVG_WRENCH, "Công cụ chẩn đoán"))
        left.addWidget(self._section_card(self._build_diag_tools))
```

(c) Thêm các method (đặt ngay sau `_build_update_tools`):

```python
    def _build_diag_tools(self, vl):
        """Thay shortcut Start Menu của bộ cài cũ: Velopack chỉ tạo shortcut cho exe chính."""
        from core import app_tools
        from core.config import APP_DIR, _get_recordings_dir

        def _btn(text, color, slot):
            b = QPushButton(text)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(36)
            b.setStyleSheet(pill_btn_qss(color, _lighten(color, 0.1), 12, 12))
            b.clicked.connect(slot)
            return b

        row = QHBoxLayout()
        row.setSpacing(10)
        self._btn_kiem_tra_tone = _btn("Kiểm tra dò tone", C["blue"],
                                       lambda: app_tools.launch_bat(APP_DIR, "kiem_tra_tone.bat"))
        self._btn_thu_tai = _btn("Thử tải YouTube", C["blue"],
                                 lambda: app_tools.launch_bat(APP_DIR, "thu_tai_youtube.bat"))
        row.addWidget(self._btn_kiem_tra_tone)
        row.addWidget(self._btn_thu_tai)
        vl.addLayout(row)

        self._btn_mo_ban_thu = _btn("Mở thư mục bản thu", C["teal"],
                                    lambda: app_tools.open_folder(_get_recordings_dir()))
        vl.addWidget(self._btn_mo_ban_thu)

        self._btn_xoa_du_lieu = _btn("Xoá dữ liệu…", C["accent"], self._action_wipe_data)
        self._btn_xoa_du_lieu.setIcon(self._svg_icon(SVG_TRASH, "white", 16))
        vl.addWidget(self._btn_xoa_du_lieu)
        self._lbl_xoa_du_lieu = QLabel("")
        self._lbl_xoa_du_lieu.setWordWrap(True)
        self._lbl_xoa_du_lieu.setStyleSheet(self._field_label_qss(size=11, weight=500, italic=True))
        vl.addWidget(self._lbl_xoa_du_lieu)

    def _action_wipe_data(self):
        import sys
        from core import app_tools
        from core.config import DATA_DIR, _get_recordings_dir
        ok, include_recordings = _ask_wipe(self)
        if not ok:
            return
        targets = app_tools.wipe_targets(DATA_DIR, _get_recordings_dir(), include_recordings,
                                         frozen=getattr(sys, "frozen", False))
        if not targets or not app_tools.schedule_wipe_after_exit(targets):
            self._lbl_xoa_du_lieu.setText("Không xoá được: bản chạy từ mã nguồn hoặc thư mục dữ liệu lạ.")
            return
        self._lbl_xoa_du_lieu.setText("Dữ liệu sẽ bị xoá ngay sau khi bạn đóng app.")
```

(d) Hàm cấp module (cuối file):

```python
def _ask_wipe(parent):
    """Hỏi xác nhận xoá dữ liệu. Trả (đồng ý, xoá cả bản thu)."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle("Xoá dữ liệu")
    box.setText("Xoá toàn bộ bài hát đã lưu, cài đặt, kích hoạt và bộ nhớ đệm của Quang Lưu Studio?")
    box.setInformativeText("Việc xoá diễn ra ngay sau khi bạn đóng app và KHÔNG khôi phục được. "
                           "Sau đó app cần kích hoạt lại.")
    cb = QCheckBox("Xoá cả các bản thu âm trong Documents\\QuangLuuStudio")
    box.setCheckBox(cb)
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    box.setDefaultButton(QMessageBox.No)
    return box.exec() == QMessageBox.Yes, cb.isChecked()
```

Ghi chú test: `dlg._lbl_xoa_du_lieu.text()` phải chứa "đóng app" — chuỗi ở (c) là "…sau khi bạn đóng app." ✔.

- [ ] **Step 8: Chạy lại + test cảnh báo Qt**

Run: `cmd.exe /c "cd /d D:\Projects\quang-luu-studio && .venv\Scripts\python.exe -m pytest tests\core\test_app_tools.py tests\ui\test_settings_tools_card.py tests\ui\test_qt_warnings.py -q -p no:cacheprovider"`
Expected: PASS (thẻ mới không sinh cảnh báo QWindowsWindow/QFont).

- [ ] **Step 9: Commit**

```bash
git add core/app_tools.py ui/dialogs/settings_dialog.py tests/core/test_app_tools.py tests/ui/test_settings_tools_card.py
git commit -m "feat(settings): thẻ Công cụ chẩn đoán thay shortcut .bat (dò tone, thử tải, thư mục bản thu) + Xoá dữ liệu sau khi đóng app"
```

---

### Task 6: Script chẩn đoán tìm bản Velopack; loại trừ Defender trỏ gốc Velopack

**Files:**
- Modify: `tools/chan_doan/QLS_ChanDoan.ps1` (~dòng 314-320), `QLS_SuaLoi.ps1` (~dòng 197-201), `QLS_SuaManHinhNhung.ps1` (~dòng 184-186 và ~dòng 471-478), `QLS_SuaPOToken.ps1` (~dòng 341-343), `KiemTraManHinhNhung.ps1` (~dòng 57-61)
- Test: `tests/test_chan_doan_velopack.py`

**Interfaces:**
- Consumes: bố cục `%LOCALAPPDATA%\QuangLuuStudio\{current\QuangLuuStudio.exe, Update.exe}`.
- Produces: không có (script độc lập).

Nguyên tắc: đường bản Velopack đứng **trước** Program Files trong danh sách dò (máy có thể còn cả bản Inno cũ; bản mới là bản đang dùng), nhưng **sau** đường của tiến trình đang chạy (vẫn được `Insert(0, …)` sau cùng). Không bao giờ thêm `%LOCALAPPDATA%\QuangLuuStudio` (gốc) làm ứng viên — ở đó có exe mồi cùng tên.

- [ ] **Step 1: Test tĩnh**

`tests/test_chan_doan_velopack.py`:

```python
"""Bộ chẩn đoán phải tìm thấy bản cài Velopack (%LocalAppData%\\QuangLuuStudio\\current)."""
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CD = os.path.join(ROOT, "tools", "chan_doan")
SCRIPTS = ["QLS_ChanDoan.ps1", "QLS_SuaLoi.ps1", "QLS_SuaManHinhNhung.ps1",
           "QLS_SuaPOToken.ps1", "KiemTraManHinhNhung.ps1"]


def _read(name):
    with open(os.path.join(CD, name), "rb") as f:
        raw = f.read()
    return raw, raw.decode("utf-8-sig")


@pytest.mark.parametrize("name", SCRIPTS)
def test_do_duong_dan_velopack_truoc_program_files(name):
    _, src = _read(name)
    i = src.find("QuangLuuStudio\\current")
    assert i != -1, "thiếu %LOCALAPPDATA%\\QuangLuuStudio\\current"
    j = src.find("ProgramFiles", src.rfind("\n", 0, i))
    assert i < j, "bản Velopack phải được dò trước Program Files"


@pytest.mark.parametrize("name", SCRIPTS)
def test_giu_bom_utf8(name):
    raw, src = _read(name)
    if re.search(r"[^\x00-\x7f]", src):
        assert raw.startswith(b"\xef\xbb\xbf")


def test_loai_tru_defender_tro_goc_velopack():
    _, src = _read("QLS_SuaManHinhNhung.ps1")
    assert "$exclRoot" in src and "Update.exe" in src
    assert "Add-MpPreference -ExclusionPath '\" + $exclRoot.Replace(" in src
```

- [ ] **Step 2: Chạy, thấy hỏng**

Run: `cmd.exe /c "cd /d D:\Projects\quang-luu-studio && .venv\Scripts\python.exe -m pytest tests\test_chan_doan_velopack.py -q -p no:cacheprovider"`
Expected: FAIL ở `test_do_duong_dan_velopack_truoc_program_files` (5 script) và `test_loai_tru_defender_tro_goc_velopack`.

- [ ] **Step 3: Sửa từng script** (giữ nguyên BOM + CRLF — dùng công cụ sửa file giữ nguyên mã hoá; kiểm lại bằng `head -c3 <file> | xxd` → `efbbbf`)

`QLS_ChanDoan.ps1` — ngay trước dòng `[void]$candidates.Add((JP $env:ProgramFiles "QuangLuuStudio"))`:

```powershell
    # Bản cài Velopack (từ 1.9.0) — dò TRƯỚC Program Files: máy có thể còn cả bản Inno cũ.
    [void]$candidates.Add((JP $env:LOCALAPPDATA "QuangLuuStudio\current"))
```

`QLS_SuaLoi.ps1` — ngay trước dòng `[void]$candidates.Add((JP $env:ProgramFiles "QuangLuuStudio"))`:

```powershell
# Bản cài Velopack (từ 1.9.0) — dò TRƯỚC Program Files: máy có thể còn cả bản Inno cũ.
[void]$candidates.Add((JP $env:LOCALAPPDATA "QuangLuuStudio\current"))
```

`QLS_SuaManHinhNhung.ps1` và `QLS_SuaPOToken.ps1` — ngay trước dòng `foreach ($c in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, (Join-Path $env:LOCALAPPDATA "Programs"))) {` (biến danh sách lần lượt là `$cands` và `$candidates`):

```powershell
# Bản cài Velopack (từ 1.9.0) — dò TRƯỚC Program Files: máy có thể còn cả bản Inno cũ.
[void]$cands.Add((Join-Path $env:LOCALAPPDATA "QuangLuuStudio\current"))
```

(trong `QLS_SuaPOToken.ps1` dùng `$candidates` thay cho `$cands`).

`KiemTraManHinhNhung.ps1` — trong mảng `foreach ($p in @( ... ))`, thêm phần tử đầu tiên:

```powershell
    "$env:LOCALAPPDATA\QuangLuuStudio\current\QuangLuuStudio.exe",
```

`QLS_SuaManHinhNhung.ps1` — loại trừ Defender: ngay trước dòng `$cmds = @(` (khối `if ($defenderOn) {`), thêm:

```powershell
            # Bản Velopack: current\ bị THAY TOÀN BỘ mỗi lần cập nhật → loại trừ cả gốc
            # %LocalAppData%\QuangLuuStudio (có Update.exe, packages\) cho bền qua các bản.
            $exclRoot = $appRoot
            $velRoot = Split-Path $appRoot -Parent
            if ((Split-Path $appRoot -Leaf) -eq "current" -and (Test-Path -LiteralPath (Join-Path $velRoot "Update.exe"))) {
                $exclRoot = $velRoot
            }
```

và trong `$cmds` đổi `"Add-MpPreference -ExclusionPath '" + $appRoot.Replace("'", "''") + "'",` thành `"Add-MpPreference -ExclusionPath '" + $exclRoot.Replace("'", "''") + "'",`. Trong khối `$thirdAv` phía trên đổi `Say-Info ("  " + $appRoot)` thành `Say-Info ("  " + $(if ((Split-Path $appRoot -Leaf) -eq "current") { Split-Path $appRoot -Parent } else { $appRoot }))`.

- [ ] **Step 4: Chạy lại + kiểm cú pháp PowerShell**

Run: lệnh Step 2 → PASS. Rồi kiểm từng script parse được:
`powershell.exe -NoProfile -Command '$e=$null; foreach($f in "QLS_ChanDoan","QLS_SuaLoi","QLS_SuaManHinhNhung","QLS_SuaPOToken","KiemTraManHinhNhung"){ [System.Management.Automation.Language.Parser]::ParseFile("D:\Projects\quang-luu-studio\tools\chan_doan\$f.ps1",[ref]$null,[ref]$e) | Out-Null; "$f : $($e.Count) loi" }'`
Expected: cả 5 dòng `… : 0 loi`.

- [ ] **Step 5: Commit**

```bash
git add tools/chan_doan/*.ps1 tests/test_chan_doan_velopack.py
git commit -m "feat(chan-doan): dò bản cài Velopack %LocalAppData%\QuangLuuStudio\current trước Program Files; loại trừ Defender trỏ gốc Velopack"
```

---

### Task 7: Đóng gói onedir + `vpk pack` (máy dev và CI dùng chung script)

**Files:**
- Modify: `QuangLuuStudio.spec` (khối `exe = EXE(...)` cuối file)
- Create: `tools/build_velopack.ps1` (UTF-8 có BOM)
- Modify: `build_installer.bat` (viết lại); Delete: `build_installer_heavy.bat`, `QuangLuuStudio_Setup.iss`
- Modify: `tests/test_packaging_cubase.py` (hai test đọc `.iss`)
- Modify: `.gitignore`
- Test: `tests/test_packaging_velopack.py`

**Interfaces:**
- Consumes: kết quả PyInstaller `dist\QuangLuuStudio\QuangLuuStudio.exe` (+ `_internal\`).
- Produces: `tools\build_velopack.ps1 -Version <x.y.z> [-OutputDir releases] [-GithubToken <t>] [-NoDelta]` → `<OutputDir>\{QuangLuuStudio-<ver>-full.nupkg, [-delta.nupkg], releases.win.json, QuangLuuStudio-CaiDat.exe}`. Task 8 và Task 9 dùng `releases\QuangLuuStudio-CaiDat.exe`.

- [ ] **Step 1: Test tĩnh**

`tests/test_packaging_velopack.py`:

```python
"""Đóng gói Velopack: spec onedir, script pack chép đủ tài nguyên cạnh exe."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*p):
    with open(os.path.join(ROOT, *p), "rb") as f:
        return f.read().decode("utf-8-sig")


def test_spec_onedir_co_collect():
    spec = _read("QuangLuuStudio.spec")
    assert re.search(r"exe = EXE\(\s*pyz,\s*a\.scripts,\s*\[\],\s*exclude_binaries=True,", spec)
    assert "coll = COLLECT(" in spec and "name='QuangLuuStudio'" in spec


def test_build_velopack_chep_du_tai_nguyen_nhu_bo_cai_cu():
    ps = _read("tools", "build_velopack.ps1")
    for f in ["app_icon.ico", "setup_all.bat", "setup_midi_ports.ps1", "configure_youtube_cookies.bat",
              "kiem_tra_tone.bat", "thu_tai_youtube.bat", "app_config.json", "binaries\\qjs.exe"]:
        assert f'"{f}"' in ps, f
    for src, dst in [("studio_one", "studio_one"), ("cubase", "cubase"), ("sfx", "sfx"),
                     ("models", "models"), ("tools\\piper", "tools\\piper"), ("binaries\\ffmpeg", "ffmpeg")]:
        assert f'@("{src}", "{dst}")' in ps, src


def test_build_velopack_dung_ten_va_co():
    ps = _read("tools", "build_velopack.ps1")
    assert "--packId QuangLuuStudio" in ps and '--packTitle "Quang Lưu Studio"' in ps
    assert "--mainExe QuangLuuStudio.exe" in ps and "--pre" in ps
    assert "QuangLuuStudio-CaiDat.exe" in ps


def test_build_velopack_co_bom():
    with open(os.path.join(ROOT, "tools", "build_velopack.ps1"), "rb") as f:
        assert f.read(3) == b"\xef\xbb\xbf"


def test_khong_con_bo_cai_inno_chinh():
    assert not os.path.exists(os.path.join(ROOT, "QuangLuuStudio_Setup.iss"))
    assert not os.path.exists(os.path.join(ROOT, "build_installer_heavy.bat"))
```

Trong `tests/test_packaging_cubase.py`: xoá `test_iss_chep_script_cubase` và `test_iss_chon_san_daw_cubase_khi_may_chi_co_cubase` (logic chọn DAW nay ở `core/first_run.default_daw`, đã có `tests/core/test_first_run.py::test_default_daw`; thư mục `cubase` được chép bởi `build_velopack.ps1`, đã có test ở trên). Thêm vào cuối file:

```python
def test_huong_dan_cubase_di_kem_ban_cai():
    # Quy trình cài đặt đi kèm bản cài (build_velopack.ps1 chép cả thư mục cubase\).
    assert os.path.exists(os.path.join(ROOT, "cubase", "HUONG_DAN_CAI_DAT_CUBASE.md"))
```

- [ ] **Step 2: Chạy, thấy hỏng**

Run: `cmd.exe /c "cd /d D:\Projects\quang-luu-studio && .venv\Scripts\python.exe -m pytest tests\test_packaging_velopack.py tests\test_packaging_cubase.py -q -p no:cacheprovider"`
Expected: FAIL — spec chưa onedir, thiếu `tools\build_velopack.ps1`, `.iss` còn.

- [ ] **Step 3: Spec onedir**

Thay nguyên khối `exe = EXE(...)` cuối `QuangLuuStudio.spec` bằng:

```python
# ONEDIR (bản cài Velopack): exe + thư mục _internal\ cạnh nhau, không giải nén ra
# %TEMP%\_MEI mỗi lần mở (onefile 7,9 s → onedir 1,4 s, đo ở spike 2026-10-12).
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='QuangLuuStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['app_icon.ico'] if os.path.exists('app_icon.ico') else [],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='QuangLuuStudio',
)
```

- [ ] **Step 4: `tools/build_velopack.ps1`** (lưu UTF-8 **có BOM**, CRLF)

```powershell
# tools/build_velopack.ps1
# Đóng gói bản onedir (dist\QuangLuuStudio) thành bộ cài Velopack. Dùng chung cho
# máy dev (build_installer.bat) và CI (.github/workflows/release.yml).
#   1. chép tài nguyên cạnh exe (thay [Files] của bộ cài Inno cũ);
#   2. tải gói bản trước từ GitHub Release (prerelease) để vpk sinh gói delta;
#   3. vpk pack;
#   4. đổi tên Setup → QuangLuuStudio-CaiDat.exe (tên KHÔNG chứa "setup": bộ cập
#      nhật cũ ≤ 1.8 lấy file .exe đầu tiên có chữ "setup" trong release).
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$OutputDir = "releases",
    [string]$GithubToken = "",
    [switch]$NoDelta
)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$pack = Join-Path $root "dist\QuangLuuStudio"
if (-not (Test-Path (Join-Path $pack "QuangLuuStudio.exe"))) {
    throw "Thiếu dist\QuangLuuStudio\QuangLuuStudio.exe — chạy PyInstaller QuangLuuStudio.spec trước"
}

# 1. Tài nguyên cạnh exe
$files = @("app_icon.ico", "setup_all.bat", "setup_midi_ports.ps1", "configure_youtube_cookies.bat",
           "kiem_tra_tone.bat", "thu_tai_youtube.bat", "app_config.json", "binaries\qjs.exe")
$dirs = @(
    @("studio_one", "studio_one"),
    @("cubase", "cubase"),
    @("sfx", "sfx"),
    @("models", "models"),
    @("tools\piper", "tools\piper"),
    @("binaries\ffmpeg", "ffmpeg")
)
$missing = @($files | Where-Object { -not (Test-Path $_) }) + @($dirs | ForEach-Object { $_[0] } | Where-Object { -not (Test-Path $_) })
if ($missing.Count -gt 0) { throw ("Thiếu tài nguyên đóng gói: " + ($missing -join ", ")) }
foreach ($f in $files) { Copy-Item -LiteralPath $f -Destination $pack -Force }
foreach ($d in $dirs) {
    $dst = Join-Path $pack $d[1]
    if (Test-Path $dst) { Remove-Item -LiteralPath $dst -Recurse -Force }
    New-Item -ItemType Directory -Force (Split-Path $dst -Parent) | Out-Null
    Copy-Item -LiteralPath $d[0] -Destination $dst -Recurse -Force
}

# 2. Gói bản trước (delta). Bản đầu tiên chưa có gì để tải → chỉ có gói Full.
New-Item -ItemType Directory -Force $OutputDir | Out-Null
if (-not $NoDelta) {
    $dl = @("download", "github", "--repoUrl", "https://github.com/ligktit/quang-luu-studio", "--pre", "-o", $OutputDir)
    if ($GithubToken) { $dl += @("--token", $GithubToken) }
    & vpk @dl
    if ($LASTEXITCODE -ne 0) { Write-Host "[!] Không tải được bản trước — chỉ tạo gói Full" }
}

# 3. Pack
Remove-Item -LiteralPath (Join-Path $OutputDir "QuangLuuStudio-CaiDat.exe") -Force -ErrorAction SilentlyContinue
& vpk pack --packId QuangLuuStudio --packVersion $Version --packTitle "Quang Lưu Studio" `
    --packDir $pack --mainExe QuangLuuStudio.exe --icon app_icon.ico --outputDir $OutputDir --noPortable
if ($LASTEXITCODE -ne 0) { throw "vpk pack lỗi (mã $LASTEXITCODE)" }

# 4. Đổi tên Setup
Move-Item -LiteralPath (Join-Path $OutputDir "QuangLuuStudio-win-Setup.exe") `
          -Destination (Join-Path $OutputDir "QuangLuuStudio-CaiDat.exe") -Force
Get-ChildItem $OutputDir | Format-Table Name, Length
```

Trước khi chạy lần đầu: `powershell.exe -NoProfile -Command 'vpk pack --help' | grep -i portable` — nếu vpk 1.2.161 **không** có `--noPortable`, bỏ cờ đó và thêm sau bước 3 dòng `Remove-Item -LiteralPath (Join-Path $OutputDir "QuangLuuStudio-win-Portable.zip") -Force -ErrorAction SilentlyContinue`; ghi ruling vào ledger.

- [ ] **Step 5: `build_installer.bat` viết lại; xoá bộ cài Inno cũ**

```bash
git rm QuangLuuStudio_Setup.iss build_installer_heavy.bat
```

Thay toàn bộ `build_installer.bat` (giữ phần dò ISCC và các bước yt-dlp/fetch_build_binaries/sync_version hiện có ở đầu file; thay từ dòng `if exist build rd /s /q build` tới cuối) bằng:

```bat
if exist build rd /s /q build
if exist dist rd /s /q dist
PyInstaller QuangLuuStudio.spec --noconfirm
if %errorlevel% neq 0 (
    echo [LOI] PyInstaller that bai
    pause
    exit /b 1
)
if not exist "dist\QuangLuuStudio\QuangLuuStudio.exe" (
    echo [LOI] Khong thay dist\QuangLuuStudio\QuangLuuStudio.exe
    pause
    exit /b 1
)
for /f "delims=" %%V in ('python -c "from core.version import __version__;print(__version__)"') do set "QLS_VER=%%V"
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_velopack.ps1 -Version %QLS_VER% -OutputDir releases
if %errorlevel% neq 0 (
    echo [LOI] Dong goi Velopack that bai
    pause
    exit /b 1
)
"%ISCC_PATH%" /DVelopackDir=releases QuangLuuStudio_Bridge.iss
if %errorlevel% neq 0 (
    echo [LOI] Build bo cai cau noi that bai
    pause
    exit /b 1
)
echo.
echo [OK] releases\QuangLuuStudio-CaiDat.exe  (cai moi)
echo [OK] installer_output\Setup_QuangLuuStudio_v%QLS_VER%.exe  (cau noi cho may 1.8.x)
pause
```

(Bước ISCC trỏ tới `QuangLuuStudio_Bridge.iss` của Task 8 — chạy `build_installer.bat` trọn vẹn sau Task 8.) Xoá khối kiểm thư mục `installer_output\*` con nếu nó tham chiếu Heavy; giữ nguyên nếu chỉ kiểm thư mục rỗng.

`.gitignore`: thêm dòng `releases/` cạnh dòng `installer_output/`.

- [ ] **Step 6: Chạy test + build thử trên máy dev (không cài)**

Run: lệnh Step 2 → PASS.

Build thử (≈ 5 phút; `vpk` đã cài từ spike — kiểm `powershell.exe -NoProfile -Command 'vpk --version'` ra `1.2.161`, sai thì `dotnet tool update -g vpk --version 1.2.161`):

```
cmd.exe /c "cd /d D:\Projects\quang-luu-studio && call .venv\Scripts\activate.bat && pip install velopack==1.2.161 && set PYTHONIOENCODING=utf-8&& PyInstaller QuangLuuStudio.spec --noconfirm && powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_velopack.ps1 -Version 1.9.0 -OutputDir releases -NoDelta"
```

Expected: `releases\` có `QuangLuuStudio-1.9.0-full.nupkg` (~550 MB), `releases.win.json`, `QuangLuuStudio-CaiDat.exe` (~560 MB); không có `*-Portable.zip`. Rồi `cmd.exe /c "D:\Projects\quang-luu-studio\dist\QuangLuuStudio\QuangLuuStudio.exe --tu-kiem-tra"` → mã thoát 0. (Không chạy `QuangLuuStudio-CaiDat.exe` ở task này — cài thử nằm trong danh sách kiểm tay, Task 10.)

- [ ] **Step 7: Commit**

```bash
git add QuangLuuStudio.spec tools/build_velopack.ps1 build_installer.bat .gitignore tests/test_packaging_velopack.py tests/test_packaging_cubase.py
git commit -m "build: PyInstaller onedir + tools/build_velopack.ps1 (chép tài nguyên, delta từ bản trước, vpk pack, đổi tên QuangLuuStudio-CaiDat.exe); bỏ bộ cài Inno chính"
```

---

### Task 8: Bộ cài cầu nối `QuangLuuStudio_Bridge.iss`

Máy ≤ 1.8.x nhận file này qua bộ cập nhật cũ (`/api/v1/updates/check` → `/download` trên server, theo `rollout_percent`), được chạy với `/SILENT /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS` và quyền admin (UAC — lần cuối). Toàn bộ việc làm trong `PrepareToInstall` để lỗi ở bước cài Velopack **dừng hẳn** với thông báo, bản cũ còn nguyên.

Chênh so với spec mục 4: spec ghi `CloseApplications=force`; cầu nối không chép file nào vào `{app}` nên Restart Manager không thấy app cũ đang dùng gì — thay bằng dừng thẳng tiến trình `QuangLuuStudio.exe` nằm trong `{app}` (cùng mục đích: app cũ không tự thoát được do lỗi luồng nền).

**Files:**
- Create: `QuangLuuStudio_Bridge.iss` (UTF-8 có BOM)
- Modify: `sync_version.py`
- Test: `tests/test_bridge_iss.py`

**Interfaces:**
- Consumes: `releases\QuangLuuStudio-CaiDat.exe` (Task 7), `tools\don_ban_cu.ps1` (`-LegacyDir`, `-ProtectedDirs`; mã 0/1/2/3), cờ exe `--chuyen-cau-hinh-cu <dir>` (Task 4; 0 = xong), Setup Velopack nhận `--silent`.
- Produces: `installer_output\Setup_QuangLuuStudio_v<ver>.exe`; define ISCC `VelopackDir` (mặc định `releases`).

- [ ] **Step 1: Test tĩnh**

`tests/test_bridge_iss.py`:

```python
"""Bộ cài cầu nối 1.8.x → Velopack: các bảo đảm an toàn đọc được từ script."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _iss():
    with open(os.path.join(ROOT, "QuangLuuStudio_Bridge.iss"), "rb") as f:
        raw = f.read()
    assert raw.startswith(b"\xef\xbb\xbf"), "Inno đọc tiếng Việt cần UTF-8 có BOM"
    return raw.decode("utf-8-sig")


def test_cung_appid_ban_cu_va_khong_tu_ghi_khoa_go_cai():
    iss = _iss()
    assert "AppId={{B8F3E2A1-5D6C-4E7F-9A0B-1C2D3E4F5A6B}" in iss
    assert re.search(r"^Uninstallable=no", iss, re.M)
    assert re.search(r"^PrivilegesRequired=admin", iss, re.M)
    assert "OutputBaseFilename=Setup_QuangLuuStudio_v{#MyAppVersion}" in iss


def test_cai_velopack_duoi_quyen_nguoi_dung_goc():
    iss = _iss()
    assert "ExecAsOriginalUser(CaiDat, '--silent'" in iss
    assert "--chuyen-cau-hinh-cu" in iss


def test_khong_goi_unins000_cu():
    # chỉ được nhắc trong chú thích, không bao giờ được chạy
    assert not re.search(r"Exec\w*\([^;]*unins000", _iss(), re.I)


def test_chi_don_khi_chuyen_cau_hinh_xong():
    iss = _iss()
    code = iss.index("[Code]")
    mig = iss.index("--chuyen-cau-hinh-cu", code)
    don = iss.index("don_ban_cu.ps1", code)
    assert mig < don
    assert "and (Code = 0) then" in iss[mig:don]


def test_chuoi_powershell_nhay_don_duoc_nhan_doi():
    iss = _iss()
    assert "StringChangeEx(S, '''', '''''', True);" in iss


def test_sync_version_cap_nhat_cau_noi():
    with open(os.path.join(ROOT, "sync_version.py"), encoding="utf-8") as f:
        src = f.read()
    assert "QuangLuuStudio_Bridge.iss" in src and "QuangLuuStudio_Setup.iss" not in src
```

- [ ] **Step 2: Chạy, thấy hỏng**

Run: `cmd.exe /c "cd /d D:\Projects\quang-luu-studio && .venv\Scripts\python.exe -m pytest tests\test_bridge_iss.py -q -p no:cacheprovider"`
Expected: FAIL — `FileNotFoundError: QuangLuuStudio_Bridge.iss`.

- [ ] **Step 3: Viết `QuangLuuStudio_Bridge.iss`** (UTF-8 có BOM)

```pascal
; ============================================================
; Quang Lưu Studio — BỘ CÀI CẦU NỐI (máy ≤ 1.8.x cài bằng Inno → bản Velopack)
; ============================================================
; Máy cũ nhận file này qua bộ cập nhật cũ (server /api/v1/updates/check → /download,
; theo rollout_percent). Toàn bộ việc nằm trong PrepareToInstall:
;   1. dừng app cũ đang chạy trong {app} (bộ cập nhật cũ không tự thoát được);
;   2. cài Velopack (QuangLuuStudio-CaiDat.exe --silent) dưới quyền NGƯỜI DÙNG GỐC
;      → vào %LocalAppData% của người hát, không phải của tài khoản admin;
;      hỏng → dừng hẳn, bản cũ còn nguyên;
;   3. dừng app mới nếu Setup Velopack đã tự mở nó;
;   4. chuyển app_config.json cũ sang lớp người dùng (exe mới --chuyen-cau-hinh-cu);
;   5. CHỈ KHI bước 4 xong: dọn bản cũ bằng tools\don_ban_cu.ps1 (KHÔNG gọi
;      unins000.exe — nó hỏi "Xoá dữ liệu?" mà /SUPPRESSMSGBOXES không chặn);
;      bước 4 hỏng → giữ bản cũ, app mới tự chuyển + hỏi dọn ở lần chạy đầu;
;   6. mở app mới dưới quyền người dùng gốc.
; Build: ISCC.exe /DVelopackDir=releases QuangLuuStudio_Bridge.iss
; Log: %TEMP%\Setup Log *.txt (SetupLogging).
; ============================================================

#define MyAppName "Quang Luu Studio"
#define MyAppVersion "1.9.0"
#define MyAppPublisher "Quang Luu"
#ifndef VelopackDir
  #define VelopackDir "releases"
#endif

[Setup]
AppId={{B8F3E2A1-5D6C-4E7F-9A0B-1C2D3E4F5A6B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\QuangLuuStudio
UsePreviousAppDir=yes
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableFinishedPage=yes
PrivilegesRequired=admin
; Không tạo/sửa mục gỡ cài đặt: bản Velopack có mục gỡ riêng (HKCU).
Uninstallable=no
CloseApplications=no
RestartApplications=no
SetupLogging=yes
OutputDir=installer_output
OutputBaseFilename=Setup_QuangLuuStudio_v{#MyAppVersion}
SetupIconFile=app_icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#VelopackDir}\QuangLuuStudio-CaiDat.exe"; Flags: dontcopy
Source: "tools\don_ban_cu.ps1"; Flags: dontcopy

[Code]
const
  NewExeRel = 'QuangLuuStudio\current\QuangLuuStudio.exe';

{ Chuỗi PowerShell trong nháy đơn: ' → '' }
function PsLit(S: String): String;
begin
  StringChangeEx(S, '''', '''''', True);
  Result := '''' + S + '''';
end;

{ Chạy một lệnh PowerShell (chỉ dùng nháy đơn bên trong). try/catch để lỗi ra mã 1 —
  không thì $null/ngoại lệ vẫn thoát 0. }
function RunPs(Cmd: String; AsOriginalUser: Boolean; var Code: Integer): Boolean;
var
  Params: String;
begin
  Params := '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "$ErrorActionPreference=''Stop''; try { ' + Cmd + ' } catch { exit 1 }"';
  if AsOriginalUser then
    Result := ExecAsOriginalUser('powershell.exe', Params, '', SW_HIDE, ewWaitUntilTerminated, Code)
  else
    Result := Exec('powershell.exe', Params, '', SW_HIDE, ewWaitUntilTerminated, Code);
  Log('PS rc=' + IntToStr(Code) + ': ' + Cmd);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  AppDir, CaiDat, Script: String;
  Code: Integer;
begin
  Result := '';
  AppDir := ExpandConstant('{app}');

  { 1. App cũ trong {app} }
  RunPs('Get-Process QuangLuuStudio -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith(' +
        PsLit(AddBackslash(AppDir)) + ', [StringComparison]::OrdinalIgnoreCase) } | Stop-Process -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 1; exit 0',
        False, Code);

  { 2. Cài Velopack dưới quyền người dùng gốc }
  ExtractTemporaryFile('QuangLuuStudio-CaiDat.exe');
  CaiDat := ExpandConstant('{tmp}\QuangLuuStudio-CaiDat.exe');
  if (not ExecAsOriginalUser(CaiDat, '--silent', '', SW_HIDE, ewWaitUntilTerminated, Code)) or (Code <> 0) then
  begin
    Result := 'Chưa cài được bản mới (mã ' + IntToStr(Code) + '). Bản cũ vẫn dùng bình thường. ' +
              'Tải bộ cài tại https://qlstudio.duckdns.org/tai-ve hoặc liên hệ kỹ thuật viên.';
    exit;
  end;
  if (not RunPs('if (Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA ' + PsLit(NewExeRel) + ')) { exit 0 } else { exit 2 }', True, Code)) or (Code <> 0) then
  begin
    Result := 'Đã chạy bộ cài mới nhưng không thấy app trong %LocalAppData%\QuangLuuStudio. ' +
              'Bản cũ vẫn dùng bình thường — liên hệ kỹ thuật viên.';
    exit;
  end;

  { 3. Setup Velopack có thể đã tự mở app mới — đóng lại trước khi chuyển cấu hình/dọn }
  RunPs('Get-Process QuangLuuStudio -ErrorAction SilentlyContinue | Where-Object { $_.Path -like ''*\QuangLuuStudio\current\QuangLuuStudio.exe'' } | Stop-Process -Force -ErrorAction SilentlyContinue; exit 0',
        False, Code);

  { 4. Chuyển cấu hình (exe GUI → Start-Process -Wait để lấy mã thoát). \" là nháy kép
    thật sau khi Windows tách tham số: đường dẫn có dấu cách đi nguyên một đối số. }
  if RunPs('$p = Start-Process -FilePath (Join-Path $env:LOCALAPPDATA ' + PsLit(NewExeRel) +
           ') -ArgumentList @(''--chuyen-cau-hinh-cu'', ' + PsLit('\"' + AppDir + '\"') +
           ') -Wait -PassThru; if ($null -eq $p) { exit 1 }; exit $p.ExitCode', True, Code) and (Code = 0) then
  begin
    { 5. Dọn bản cũ (đang chạy quyền admin). Không xoá được hết → mã 2/3, app mới hỏi lại. }
    ExtractTemporaryFile('don_ban_cu.ps1');
    Script := ExpandConstant('{tmp}\don_ban_cu.ps1');
    Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + Script +
         '" -LegacyDir "' + AppDir + '" -ProtectedDirs "' + ExpandConstant('{localappdata}') + '\QuangLuuStudio"',
         '', SW_HIDE, ewWaitUntilTerminated, Code);
    Log('don_ban_cu.ps1 rc=' + IntToStr(Code));
  end
  else
    Log('Chuyển cấu hình cũ lỗi (rc=' + IntToStr(Code) + ') — giữ bản cũ, app mới tự xử lý ở lần chạy đầu');

  { 6. Mở app mới }
  RunPs('Start-Process -FilePath (Join-Path $env:LOCALAPPDATA ' + PsLit(NewExeRel) + '); exit 0', True, Code);
end;
```

- [ ] **Step 4: `sync_version.py`**

Thay khối "# 1. Update ISS" bằng:

```python
# 1. Update bộ cài cầu nối (máy 1.8.x → Velopack). Bản cài chính là Velopack:
#    số phiên bản lấy thẳng từ core/version.py (tools/build_velopack.ps1 -Version).
ISS_PATH = Path(__file__).parent / "QuangLuuStudio_Bridge.iss"
content = ISS_PATH.read_text(encoding="utf-8-sig")
updated = re.sub(
    r'(#define MyAppVersion\s+")[^"]+(")',
    rf'\g<1>{__version__}\g<2>',
    content,
)

if updated != content:
    ISS_PATH.write_text(updated, encoding="utf-8-sig")
    print(f"[sync_version] Updated QuangLuuStudio_Bridge.iss -> v{__version__}")
```

Sửa docstring đầu file thành `Sync version from core/version.py → QuangLuuStudio_Bridge.iss, build_installer.bat, ...`. Trong khối "# 2. Update build_installer.bat": xoá phần `HEAVY_PATH` (file đã bỏ). Phần regex `Setup_QuangLuuStudio_v` trong `build_installer.bat` giờ không còn khớp gì (bat dùng `%QLS_VER%`) — xoá luôn khối 2.

- [ ] **Step 5: Chạy test + biên dịch thử**

Run: lệnh Step 2 → PASS.

Biên dịch (cần `releases\QuangLuuStudio-CaiDat.exe` từ Task 7 Step 6):
`cmd.exe /c "cd /d D:\Projects\quang-luu-studio && "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" /DVelopackDir=releases QuangLuuStudio_Bridge.iss"`
Expected: `Successful compile`, có `installer_output\Setup_QuangLuuStudio_v1.9.0.exe` (~565 MB). Nếu ISCC báo lỗi cú pháp Pascal → sửa đúng chỗ, giữ nguyên thứ tự 6 bước và các chuỗi mà test tĩnh kiểm. (Không chạy file này trên máy dev — máy dev còn bản 1.8.0 thật trong Program Files; chạy thử nằm trong danh sách kiểm tay, trên máy ảo.)

- [ ] **Step 6: Commit**

```bash
git add QuangLuuStudio_Bridge.iss sync_version.py tests/test_bridge_iss.py
git commit -m "feat(installer): bộ cài cầu nối 1.8.x → Velopack — cài dưới quyền người dùng gốc, chuyển cấu hình bằng exe mới, chỉ dọn bản cũ khi chuyển xong"
```

---

### Task 9: CI — onedir, vpk, prerelease, bộ cài cầu nối

**Files:**
- Modify: `.github/workflows/release.yml` (bước 5–8, 10, 12, 13)
- Test: `tests/test_release_workflow.py`

**Interfaces:**
- Consumes: `tools/build_velopack.ps1` (Task 7), `QuangLuuStudio_Bridge.iss` (Task 8), `sync_version.py`.
- Produces: GitHub Release **prerelease** với `releases.win.json`, `QuangLuuStudio-<ver>-full.nupkg`, `QuangLuuStudio-<ver>-delta.nupkg` (từ bản thứ hai), `QuangLuuStudio-CaiDat.exe`, `Setup_QuangLuuStudio_v<ver>.exe`, `SHA256SUMS.txt` — đúng tên mà `server/app/services/velopack_import.py` đọc.

- [ ] **Step 1: Test tĩnh**

`tests/test_release_workflow.py`:

```python
"""release.yml: bản Velopack phát hành dạng prerelease, vpk cùng số với pip velopack."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _yml():
    with open(os.path.join(ROOT, ".github", "workflows", "release.yml"), encoding="utf-8") as f:
        return f.read()


def test_prerelease():
    assert re.search(r"^\s+prerelease: true$", _yml(), re.M)


def test_vpk_cung_so_voi_velopack():
    with open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8") as f:
        pip_ver = re.search(r"velopack==([\d.]+)", f.read()).group(1)
    assert f"dotnet tool install -g vpk --version {pip_ver}" in _yml()


def test_dinh_kem_dung_ten_server_doc():
    y = _yml()
    for name in ["releases/releases.win.json", "releases/QuangLuuStudio-*-full.nupkg",
                 "releases/QuangLuuStudio-*-delta.nupkg", "releases/QuangLuuStudio-CaiDat.exe",
                 "installer_output/Setup_QuangLuuStudio_v*.exe"]:
        assert name in y, name


def test_dung_script_build_chung_va_cau_noi():
    y = _yml()
    assert "tools\\build_velopack.ps1" in y and "QuangLuuStudio_Bridge.iss" in y
    assert "QuangLuuStudio_Setup.iss" not in y
```

- [ ] **Step 2: Chạy, thấy hỏng**

Run: `cmd.exe /c "cd /d D:\Projects\quang-luu-studio && .venv\Scripts\python.exe -m pytest tests\test_release_workflow.py -q -p no:cacheprovider"`
Expected: FAIL (`prerelease: false`, chưa có vpk).

- [ ] **Step 3: Sửa `release.yml`**

(a) Bước 5 đổi tên + lệnh kiểm:

```yaml
      - name: Sync version
        shell: pwsh
        run: |
          python sync_version.py
          if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
          Select-String -Path QuangLuuStudio_Bridge.iss -Pattern '#define MyAppVersion'
```

(giữ nguyên khối comment dài phía trên về việc phải chạy như script thật).

(b) Bước 6 "Build executable" thay phần `run:` bằng:

```yaml
        run: |
          if (Test-Path build) { Remove-Item build -Recurse -Force }
          pyinstaller QuangLuuStudio.spec --noconfirm
          if (-not (Test-Path "dist\QuangLuuStudio\QuangLuuStudio.exe")) {
            Write-Host "ERROR: Khong thay dist\QuangLuuStudio\QuangLuuStudio.exe (onedir)"
            Get-ChildItem dist\
            exit 1
          }
          # So ĐÚNG tên file .dll trong thư mục onedir (PKG-00.toc chỉ có ở onefile).
          $hit = Get-ChildItem dist\QuangLuuStudio -Recurse -Filter 'Qt6WebEngineCore.dll' -ErrorAction SilentlyContinue
          if ($hit) {
            Write-Host "ERROR: Goi lai co Qt6WebEngineCore.dll - ban nay khong duoc kem QtWebEngine"
            $hit | Select-Object -First 5 | ForEach-Object { Write-Host "  $($_.FullName)" }
            exit 1
          }
          Write-Host "OK: build onedir khong kem QtWebEngine"
```

(c) Chèn bước mới sau bước 6:

```yaml
      # ── 6b. Đóng gói Velopack ─────────────────────────────────────────────────
      # vpk PHẢI cùng số với pip velopack trong requirements.txt. Bản trước được tải
      # (prerelease, --pre) để sinh gói delta; bản đầu tiên chỉ có gói Full.
      - name: Set up .NET (vpk)
        uses: actions/setup-dotnet@v4
        with:
          dotnet-version: "8.0.x"

      - name: Pack Velopack
        shell: pwsh
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          dotnet tool install -g vpk --version 1.2.161
          $ver = "${{ github.ref_name }}".TrimStart('v')
          & .\tools\build_velopack.ps1 -Version $ver -OutputDir releases -GithubToken $env:GITHUB_TOKEN
          if (-not (Test-Path releases\QuangLuuStudio-CaiDat.exe)) { exit 1 }
```

(d) Bước 8 "Build installer" thay `& $iscc QuangLuuStudio_Setup.iss` bằng `& $iscc /DVelopackDir=releases QuangLuuStudio_Bridge.iss`, đổi tên bước thành `Build bridge installer (máy 1.8.x)`.

(e) Bước 9 (ký số, đang comment): thêm dòng comment cuối khối: `#     (vpk pack: thêm --signParams "/f cert.pfx /p ... /tr http://timestamp.sectigo.com /td sha256 /fd sha256" trong tools/build_velopack.ps1)`.

(f) Bước 10 SHA256SUMS: đổi `$exes = @(Get-ChildItem installer_output\*.exe)` thành `$exes = @(Get-ChildItem installer_output\*.exe) + @(Get-ChildItem releases\QuangLuuStudio-CaiDat.exe)`.

(g) Bước 12:

```yaml
      # Prerelease: bộ cập nhật cũ (≤ 1.8) đọc GitHub releases/latest — bỏ qua prerelease,
      # nên máy cũ chỉ nhận bộ cài cầu nối qua server (giữ được rollout_percent).
      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          name: "Quang Lưu Studio ${{ github.ref_name }}"
          body_path: RELEASE_NOTES.md
          draft: false
          prerelease: true
          files: |
            releases/releases.win.json
            releases/QuangLuuStudio-*-full.nupkg
            releases/QuangLuuStudio-*-delta.nupkg
            releases/QuangLuuStudio-CaiDat.exe
            installer_output/Setup_QuangLuuStudio_v*.exe
            installer_output/SHA256SUMS.txt
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

`files:` có mẫu không khớp (delta ở bản đầu) thì action chỉ cảnh báo — chấp nhận. Gói Full của **bản trước** cũng nằm trong `releases\` (do `vpk download`) và khớp mẫu `*-full.nupkg`: đổi mẫu Full thành `releases/QuangLuuStudio-${{ github.ref_name }}-full.nupkg` **không dùng được** (tag có chữ `v`) — thay bằng bước trước đó xoá gói của bản cũ:

```yaml
      - name: Drop previous-version packages
        shell: pwsh
        run: |
          $ver = "${{ github.ref_name }}".TrimStart('v')
          Get-ChildItem releases\*.nupkg | Where-Object { $_.Name -notlike "QuangLuuStudio-$ver-*" } | Remove-Item -Force
          Get-ChildItem releases
```

(đặt ngay trước bước 12; `releases.win.json` vẫn liệt kê bản trước — server lọc theo `Version`, đã làm ở Kế hoạch 3).

(h) Bước 13 artifact: `path:` thành hai dòng `installer_output/` và `releases/`.

- [ ] **Step 4: Chạy lại**

Run: lệnh Step 2 → PASS. Kiểm YAML hợp lệ: `cmd.exe /c "cd /d D:\Projects\quang-luu-studio && .venv\Scripts\python.exe -c "import yaml;yaml.safe_load(open('.github/workflows/release.yml',encoding='utf-8'));print('OK')""` → `OK` (không có pyyaml thì `pip install pyyaml` vào .venv).

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/release.yml tests/test_release_workflow.py
git commit -m "ci(release): build onedir + vpk 1.2.161 (delta từ bản trước), GitHub Release dạng prerelease, kèm bộ cài cầu nối"
```

---

### Task 10: Suite, tài liệu phát hành, danh sách kiểm tay, deploy server (hỏi trước)

**Files:**
- Create: `docs/QUY_TRINH_PHAT_HANH.md`, `docs/KIEM_TAY_VELOPACK.md`
- Modify: `tools/chan_doan/README.md` (đoạn đầu: thêm câu về bản Velopack)

**Interfaces:** không.

- [ ] **Step 1: Cả suite**

Run (chạy nền, > 10 phút):
`cmd.exe /c "cd /d D:\Projects\quang-luu-studio && .venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider --ignore=tests\test_recorder_worker_e2e.py" > <workspace>\suite.log 2>&1`; sau đó `git checkout app_config.json` và đặt lại `settings.json`. Server: `cd server && ~/.venvs/qls-server/bin/python -m pytest -q`.
Expected: client xanh trừ cảnh báo có từ trước `core/memory.py:234`; server 239 passed.

- [ ] **Step 2: `docs/QUY_TRINH_PHAT_HANH.md`**

```markdown
# Quy trình phát hành (từ 1.9.0 — Velopack)

1. Sửa `core/version.py` (`__version__`, `VERSION_TUPLE`, `BUILD_DATE`) → `python sync_version.py`
   (cập nhật `QuangLuuStudio_Bridge.iss`, sổ tay, `BUNDLED_YTDLP_VERSION`).
2. Viết `docs/release_notes/vX.Y.Z.md` (giọng cho ca sĩ/kỹ thuật viên).
3. Suite xanh → commit lên `main` → `git tag -a vX.Y.Z -m ...` → `git push origin vX.Y.Z`.
   CI build onedir, `vpk pack` (delta từ bản trước), bộ cài cầu nối, tạo GitHub Release **prerelease**.
4. Kiểm: `gh release view vX.Y.Z --json assets,isPrerelease` → `isPrerelease: true`, có
   `releases.win.json`, `QuangLuuStudio-X.Y.Z-full.nupkg`, `QuangLuuStudio-CaiDat.exe`,
   `Setup_QuangLuuStudio_vX.Y.Z.exe`.
5. Trang admin → Phiên bản → **Nhập từ GitHub** `X.Y.Z` → chờ trạng thái "xong" → bật, đặt
   rollout 10% → theo dõi log → mở rộng. `/tai-ve` chỉ trỏ bản này khi rollout 100%.
6. Máy còn 1.8.x: tải `Setup_QuangLuuStudio_vX.Y.Z.exe` từ GitHub Release rồi **upload qua
   `/admin/versions/upload`** như trước (đường `/api/v1/updates/check`). Làm ở mọi bản cho tới
   khi log server không còn máy 1.8.x.
7. Rút bản lỗi: tắt (`is_active`) trên admin để dừng phát tán; máy đã nhận thì phát hành bản vá số cao hơn.

Build tại máy dev (không tag): `build_installer.bat` → `releases\QuangLuuStudio-CaiDat.exe` +
`installer_output\Setup_QuangLuuStudio_v<ver>.exe`. Cần `vpk` 1.2.161 (`dotnet tool install -g vpk --version 1.2.161`).
```

- [ ] **Step 3: `docs/KIEM_TAY_VELOPACK.md`**

```markdown
# Kiểm tay trước khi phát hành 1.9.0 (Velopack)

Ghi kết quả (Đạt/Không + ghi chú) vào từng dòng. Mọi mục phải Đạt trước khi bật rollout.

## A. Bản onedir trên máy dev (từ kết quả spike, phần giao diện chưa kiểm)
- [ ] Phát một bài YouTube trọn vẹn; dò tone chạy.
- [ ] Bấm 3 nút SFX — có tiếng.
- [ ] Đọc giọng (piper) một câu.
- [ ] Ghi âm 5 giây → đóng app → mở lại → app chạy (thư mục `current\_internal` còn nguyên).
- [ ] Cài đặt → Cập nhật phần mềm: dòng trạng thái đúng; Cài đặt → Công cụ: Kiểm tra dò tone / Thử tải YouTube mở console, Mở thư mục bản thu đúng chỗ.

## B. Máy ảo Windows sạch, tên người dùng **có dấu và dấu cách** (ví dụ `Nguyễn Văn A`)
- [ ] Cài `QuangLuuStudio-CaiDat.exe`: SmartScreen một lần, không UAC, app tự mở, có shortcut Desktop + Start Menu.
- [ ] Chưa có loopMIDI: hộp thoại lần đầu xin cài (UAC một lần) → cổng MIDI có.
- [ ] Cập nhật 1.9.0 → 1.9.1 (feed thử trên server, rollout 100% cho máy ảo): bản mới tải ngầm khi app đang chạy, không hộp thoại; đóng app → **quan sát có cửa sổ nào lóe lên**; mở lại = 1.9.1.
- [ ] Có bản chờ → `taskkill /F` → mở lại: tự áp dụng; **đo thời gian mở** so với mở thường.
- [ ] Gỡ qua Apps & features → `%APPDATA%\QuangLuuStudio` và `Documents\QuangLuuStudio` còn nguyên.
- [ ] Xoá dữ liệu (Cài đặt → Công cụ) → đóng app → thư mục dữ liệu biến mất; mở lại → màn hình kích hoạt.

## C. Chuyển máy cũ (máy ảo cài sẵn 1.8.0 bằng Inno, `app_config.json` sửa tay `midi_cc.tone_music`)
- [ ] Đường 1: upload bộ cài cầu nối lên server (rollout cho máy ảo) → bộ cập nhật 1.8.0 tải và chạy → UAC một lần → app mới tự mở; `tone_music` giữ giá trị sửa tay; Program Files\QuangLuuStudio, 5 shortcut cũ và khoá `HKLM\...\{B8F3E2A1-...}_is1` đều biến mất; không có hộp "Xoá dữ liệu?".
- [ ] Đường 2: cài `QuangLuuStudio-CaiDat.exe` đè lên máy có 1.8.0 → lần chạy đầu hỏi dọn bản cũ → "Để sau" thì hai bản cùng chạy được, lần mở sau hỏi lại → "Dọn" thì sạch như đường 1.
- [ ] Bộ cài cầu nối khi Setup Velopack hỏng (đổi tên `%LocalAppData%` thành chỉ đọc trước khi chạy): thông báo lỗi, bản 1.8.0 còn nguyên và chạy được.

## D. Máy khách thật
- [ ] Trọn vòng C (đường 1) trên một máy khách Cubase qua UltraViewer, có người trực.
```

- [ ] **Step 4: `tools/chan_doan/README.md`**

Sau đoạn mở đầu ("Các tệp trong thư mục này chạy được …"), thêm:

```markdown
Từ 1.9.0 app cài ở `%LocalAppData%\QuangLuuStudio\current` (Velopack, không cần admin); các
script dò đường này trước Program Files. Máy còn bản cũ trong Program Files vẫn được nhận.
```

- [ ] **Step 5: Commit**

```bash
git add docs/QUY_TRINH_PHAT_HANH.md docs/KIEM_TAY_VELOPACK.md tools/chan_doan/README.md
git commit -m "docs: quy trình phát hành Velopack, danh sách kiểm tay 1.9.0, README chẩn đoán"
```

- [ ] **Step 6: Deploy server — HỎI NGƯỜI DÙNG TRƯỚC**

Báo người dùng: commit sẽ deploy (Task 1: thư mục staging khi nhập + nginx 1024M), không tạo bảng mới, gián đoạn ~1 phút. Khi được đồng ý, làm theo memory `vps-deploy-procedure`: sao lưu `/opt/qls/server/backups/<ts>-pre-velopack-staging/` (`.env`, `pg_dump`, `app_before.tgz`, `nginx_qls.conf`); so code VPS với lần deploy trước (`diff -r --strip-trailing-cr`); `git archive HEAD server/app server/deploy server/tests server/Dockerfile server/docker-compose.yml server/requirements.txt` → scp → `tar xzf` → `docker compose up -d --build`; trên VPS **chỉ sửa dòng** `client_max_body_size` trong `/etc/nginx/sites-available/qls` (file trên VPS khác bản repo ở server_name + khối Certbot — không chép đè) → `nginx -t && systemctl reload nginx`. Kiểm: `curl -s https://qlstudio.duckdns.org/api/v1/updates/velopack/thu-may/releases.win.json` → `{"Assets":[]}`; `docker compose logs --tail=25 api` có "Application startup complete". Ghi một dòng vào memory `vps-deploy-procedure`.

- [ ] **Step 7: Bàn giao**

Cập nhật memory `velopack-migration` (Kế hoạch 4 xong, còn: kiểm tay `docs/KIEM_TAY_VELOPACK.md`, merge vào `main`, tag `v1.9.0`) và `release-procedure` (trỏ `docs/QUY_TRINH_PHAT_HANH.md`; GitHub Release prerelease; bước nhập trên admin). Không merge/tag khi chưa hỏi người dùng.
