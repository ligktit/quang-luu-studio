# Velopack — Kế hoạch 3/4: Feed cập nhật phía server

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Server `qlstudio.duckdns.org` phát feed Velopack theo từng máy (giữ `is_active` + `rollout_percent`), phục vụ gói `.nupkg`, có link tải cố định `/tai-ve`, và trang admin nhập một bản từ GitHub Release.

**Architecture:** Bảng mới `velopack_releases` (một dòng = một phiên bản, giữ các phần tử `Assets` của chính bản đó lấy từ `releases.win.json`). `app/services/velopack_feed.py` (thuần, test được) dựng feed theo `rollout_bucket(fingerprint)`. `app/services/velopack_import.py` tải tài sản từ GitHub bằng `httpx` (chạy nền qua `BackgroundTasks`), kiểm SHA256/kích thước. Router `updates.py` thêm 2 route feed/file; route `/tai-ve` ở router không prefix. Endpoint cũ `/check` + `/download` giữ nguyên (phục vụ bộ cài cầu nối cho máy 1.8.x).

**Tech Stack:** FastAPI 0.115, SQLAlchemy 2.0, httpx 0.28, Jinja2, pytest (SQLite tạm).

**Spec:** `docs/superpowers/specs/2026-10-12-velopack-installer-design.md` (mục 3 "Phía server", mục 4 đầu).

**Phụ thuộc:** không phụ thuộc Kế hoạch 1–2. Định dạng phần tử `Assets` lấy theo stub `velopack.pyi` (`PackageId, Version, Type, FileName, SHA1, SHA256, Size, NotesMarkdown, NotesHtml`); Kế hoạch 1 Task 3 Step 3 chép một phần tử thật — nếu khác tên trường, sửa test fixture `_asset()` của Task 2/3 cho khớp trước khi deploy.

## Global Constraints

- Test server chạy bằng Python Linux: tạo venv một lần `python3 -m venv ~/.venvs/qls-server && ~/.venvs/qls-server/bin/pip install -r /mnt/d/Projects/quang-luu-studio/server/requirements.txt`; chạy `cd /mnt/d/Projects/quang-luu-studio/server && ~/.venvs/qls-server/bin/python -m pytest -q`.
- Không có migration: bảng mới được tạo bởi `create_all` (`python -m app.cli init-db`) — **không** thêm cột vào bảng cũ.
- Tên tài sản trên GitHub Release (do CI Kế hoạch 4 đặt): `releases.win.json`, `QuangLuuStudio-<ver>-full.nupkg`, `QuangLuuStudio-<ver>-delta.nupkg`, `QuangLuuStudio-CaiDat.exe`. Tag `v<ver>`.
- Repo GitHub mặc định: `ligktit/quang-luu-studio` (public, đọc không cần token).
- Fingerprint hợp lệ: `^[A-Za-z0-9_-]{1,128}$`. Tên file hợp lệ: `^[A-Za-z0-9._-]{1,200}$` và không phải `.`/`..`.
- Bản nhập mới mặc định `is_active=False`, `rollout_percent=0` — người dùng tự bật và chỉnh %.
- Deploy lên VPS là việc ra ngoài: **hỏi người dùng trước** (Task 5).

## Review Focus

- **Fingerprint lạ / rỗng / có ký tự đường dẫn** trong URL feed → 404, không lỗi 500. (Task 2 `test_fingerprint_la_404`.)
- **Tên file yêu cầu không thuộc feed** (đoán tên, `..`) → 404, không đọc file ngoài thư mục velopack. (Task 2 `test_tai_file_khong_thuoc_feed_404`.)
- **Bản giữa bị tắt (rút bản lỗi) giữa hai bản đang bật** → máy cũ vẫn lên được bản mới nhất (delta của bản bị tắt vẫn có trong feed để nối chuỗi, gói full của nó thì không). (Task 2 `test_ban_giua_bi_tat_van_noi_chuoi_delta`.)
- **GitHub trả file hỏng / thiếu / feed chứa tên file độc hại** → bản nhập ở trạng thái `loi` kèm lý do, không để lại file `.part`, không ghi ra ngoài thư mục. (Task 3 `test_sai_sha_bao_loi`, `test_ten_file_doc_hai_bi_tu_choi`.)
- **Worker bị khởi động lại giữa lúc nhập** → dòng kẹt `dang_nhap`; bấm nhập lại cùng phiên bản phải chạy lại được. (Task 4 `test_nhap_lai_cung_phien_ban`.)

---

### Task 1: Model `VelopackRelease` + cấu hình repo

**Files:**
- Modify: `server/app/models.py` (thêm lớp sau `AppVersion`, ~dòng 113)
- Modify: `server/app/config.py` (khối `storage_dir`, ~dòng 66)
- Test: `server/tests/test_velopack_feed.py` (tạo ở Task 2 — Task 1 kiểm bằng test nhỏ dưới)

**Interfaces:**
- Produces: `app.models.VelopackRelease` với cột `id, version (unique), assets_json (Text JSON list), setup_filename (str|None), status ("dang_nhap"|"xong"|"loi"), import_error (str|None), rollout_percent (int, mặc định 0), is_active (bool, mặc định False), published_at`. `settings.github_repo: str`.

- [ ] **Step 1: Viết test thất bại**

```python
# server/tests/test_velopack_model.py
from app.config import settings
from app.db import SessionLocal
from app.models import VelopackRelease


def test_mac_dinh_ban_nhap_moi_chua_phat():
    with SessionLocal() as db:
        db.add(VelopackRelease(version="1.9.0"))
        db.commit()
        row = db.query(VelopackRelease).one()
        assert row.status == "dang_nhap"
        assert row.is_active is False
        assert row.rollout_percent == 0
        assert row.assets_json == "[]"


def test_repo_github_mac_dinh():
    assert settings.github_repo == "ligktit/quang-luu-studio"
```

- [ ] **Step 2: Chạy test, xác nhận thất bại**

Run: `cd /mnt/d/Projects/quang-luu-studio/server && ~/.venvs/qls-server/bin/python -m pytest tests/test_velopack_model.py -q`
Expected: FAIL — `ImportError: cannot import name 'VelopackRelease'`.

- [ ] **Step 3: Viết code**

`server/app/models.py`, ngay sau lớp `AppVersion`:

```python
class VelopackRelease(Base):
    """Một bản Velopack nhập từ GitHub Release — nguồn của feed cập nhật ngầm.

    assets_json: các phần tử "Assets" của releases.win.json CHỈ của bản này
    (gói Full + Delta). Bản nhập mới chưa phát: is_active=False, rollout 0%.
    """
    __tablename__ = "velopack_releases"

    id:              Mapped[int] = mapped_column(Integer, primary_key=True)
    version:         Mapped[str] = mapped_column(String(40), unique=True, index=True)
    assets_json:     Mapped[str] = mapped_column(Text, default="[]")
    setup_filename:  Mapped[str | None] = mapped_column(String(255), nullable=True)
    status:          Mapped[str] = mapped_column(String(20), default="dang_nhap", index=True)
    import_error:    Mapped[str | None] = mapped_column(Text, nullable=True)
    rollout_percent: Mapped[int] = mapped_column(Integer, default=0)
    is_active:       Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    published_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

`server/app/config.py`, ngay sau `max_upload_mb: int = 500`:

```python
    # Repo GitHub chứa Release do CI tạo — nguồn để trang admin nhập bản Velopack.
    github_repo: str = "ligktit/quang-luu-studio"
```

- [ ] **Step 4: Chạy test, xác nhận qua**

Run: lệnh Step 2. Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add server/app/models.py server/app/config.py server/tests/test_velopack_model.py
git commit -m "feat(server): bảng velopack_releases cho feed cập nhật ngầm"
```

---

### Task 2: Dựng feed + route feed / file / `/tai-ve`

**Files:**
- Create: `server/app/services/velopack_feed.py`
- Modify: `server/app/routers/updates.py` (thêm import, `public_router`, 3 route)
- Modify: `server/app/main.py:62` (include `updates.public_router`)
- Test: `server/tests/test_velopack_feed.py`

**Interfaces:**
- Consumes: `VelopackRelease` (Task 1), `app.security.rollout_bucket(fp) -> int`.
- Produces:
  - `velopack_feed.parse_semver(v: str) -> tuple[int, int, int]`
  - `velopack_feed.valid_fingerprint(fp: str) -> bool`, `valid_filename(name: str) -> bool`
  - `velopack_feed.velopack_dir() -> Path` (= `settings.storage_path / "velopack"`, tự tạo)
  - `velopack_feed.file_path(name: str) -> Path | None`
  - `velopack_feed.build_feed(rows: list[VelopackRelease], fingerprint: str) -> dict` → `{"Assets": [...]}`
  - `velopack_feed.served_filenames(rows) -> set[str]`
  - Route: `GET /api/v1/updates/velopack/{fingerprint}/releases.win.json`, `GET /api/v1/updates/velopack/{fingerprint}/{filename}`, `GET /tai-ve`.

- [ ] **Step 1: Viết test thất bại**

```python
# server/tests/test_velopack_feed.py
"""Feed Velopack theo từng máy: chỉ bản đã nhập xong + đang bật + tới lượt rollout."""
import json

import pytest

from app.db import SessionLocal
from app.models import VelopackRelease
from app.security import rollout_bucket
from app.services import velopack_feed


def _asset(version, kind):
    name = f"QuangLuuStudio-{version}-{kind.lower()}.nupkg"
    return {"PackageId": "QuangLuuStudio", "Version": version, "Type": kind, "FileName": name,
            "SHA1": "", "SHA256": "ab" * 32, "Size": 3, "NotesMarkdown": "", "NotesHtml": ""}


def _add(version, active=True, rollout=100, status="xong", delta=True, setup=False):
    assets = [_asset(version, "Full")] + ([_asset(version, "Delta")] if delta else [])
    for a in assets:
        (velopack_feed.velopack_dir() / a["FileName"]).write_bytes(b"pkg")
    setup_name = None
    if setup:
        setup_name = f"{version}_QuangLuuStudio-CaiDat.exe"
        (velopack_feed.velopack_dir() / setup_name).write_bytes(b"MZ" + version.encode())
    with SessionLocal() as db:
        db.add(VelopackRelease(version=version, assets_json=json.dumps(assets), status=status,
                               is_active=active, rollout_percent=rollout, setup_filename=setup_name))
        db.commit()


def _fp(lo, hi):
    return next(f"fp{i}" for i in range(10000) if lo <= rollout_bucket(f"fp{i}") < hi)


def _names(client, fp):
    r = client.get(f"/api/v1/updates/velopack/{fp}/releases.win.json", params={"localVersion": "1.9.0"})
    assert r.status_code == 200
    return sorted(a["FileName"] for a in r.json()["Assets"])


def test_feed_rong_khi_chua_co_ban(client):
    assert _names(client, "fp1") == []


def test_chi_ban_xong_va_dang_bat(client):
    _add("1.9.0")
    _add("1.9.1", active=False)
    _add("1.9.2", status="dang_nhap")
    assert _names(client, "fp1") == ["QuangLuuStudio-1.9.0-delta.nupkg", "QuangLuuStudio-1.9.0-full.nupkg"]


def test_rollout_10_phan_tram(client):
    _add("1.9.0")
    _add("1.9.1", rollout=10)
    trong, ngoai = _fp(0, 10), _fp(10, 100)
    assert "QuangLuuStudio-1.9.1-full.nupkg" in _names(client, trong)
    assert not any("1.9.1" in n for n in _names(client, ngoai))


def test_ban_giua_bi_tat_van_noi_chuoi_delta(client):
    _add("1.9.0")
    _add("1.9.1", active=False)
    _add("1.9.2")
    names = _names(client, "fp1")
    assert "QuangLuuStudio-1.9.1-delta.nupkg" in names
    assert "QuangLuuStudio-1.9.1-full.nupkg" not in names
    assert "QuangLuuStudio-1.9.2-full.nupkg" in names


def test_delta_cua_ban_chua_toi_luot_khong_lo_ra(client):
    _add("1.9.0")
    _add("1.9.1", rollout=10)
    ngoai = _fp(10, 100)
    assert not any("1.9.1" in n for n in _names(client, ngoai))


@pytest.mark.parametrize("fp", ["a b", "..", "x" * 129, "fp%2F..", "ê"])
def test_fingerprint_la_404(client, fp):
    r = client.get(f"/api/v1/updates/velopack/{fp}/releases.win.json")
    assert r.status_code == 404


def test_tai_file_hop_le(client):
    _add("1.9.0")
    r = client.get("/api/v1/updates/velopack/fp1/QuangLuuStudio-1.9.0-full.nupkg")
    assert r.status_code == 200
    assert r.content == b"pkg"


@pytest.mark.parametrize("name", ["QuangLuuStudio-9.9.9-full.nupkg", "..", "app.db", "1.9.0_QuangLuuStudio-CaiDat.exe"])
def test_tai_file_khong_thuoc_feed_404(client, name):
    _add("1.9.0", setup=True)
    r = client.get(f"/api/v1/updates/velopack/fp1/{name}")
    assert r.status_code == 404


def test_tai_ve_ban_100_phan_tram_moi_nhat(client):
    _add("1.9.0", setup=True)
    _add("1.9.1", setup=True)
    _add("1.9.2", setup=True, rollout=50)
    r = client.get("/tai-ve")
    assert r.status_code == 200
    assert r.content == b"MZ1.9.1"
    assert "QuangLuuStudio-CaiDat.exe" in r.headers["content-disposition"]


def test_tai_ve_khi_chua_co_ban_404(client):
    assert client.get("/tai-ve").status_code == 404
```

Thêm vào `server/tests/conftest.py`, cuối file, fixture dọn thư mục velopack giữa các test:

```python
@pytest.fixture(autouse=True)
def _fresh_velopack_storage():
    import shutil
    from app.config import settings
    d = settings.storage_path / "velopack"
    shutil.rmtree(d, ignore_errors=True)
    yield
    shutil.rmtree(d, ignore_errors=True)
```

- [ ] **Step 2: Chạy test, xác nhận thất bại**

Run: `cd /mnt/d/Projects/quang-luu-studio/server && ~/.venvs/qls-server/bin/python -m pytest tests/test_velopack_feed.py -q`
Expected: FAIL — `ImportError: cannot import name 'velopack_feed'`.

- [ ] **Step 3: Viết service**

```python
# server/app/services/velopack_feed.py
"""Feed cập nhật Velopack (releases.win.json) dựng theo từng máy.

Máy chỉ thấy gói Full của các bản đã nhập xong, đang bật và tới lượt rollout.
Gói Delta của mọi bản đã nhập (kể cả bản bị tắt) có tuổi ≤ bản cao nhất máy đó
được nhận vẫn được liệt kê, để chuỗi delta không bị đứt khi rút một bản giữa.
"""
import json
import re
from pathlib import Path

from app.config import settings
from app.security import rollout_bucket

_FP_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,200}$")


def parse_semver(v):
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", (v or "").strip())
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def valid_fingerprint(fp):
    return bool(_FP_RE.match(fp or ""))


def valid_filename(name):
    return bool(_NAME_RE.match(name or "")) and name not in (".", "..")


def velopack_dir():
    p = settings.storage_path / "velopack"
    p.mkdir(parents=True, exist_ok=True)
    return p


def file_path(name):
    if not valid_filename(name):
        return None
    p = velopack_dir() / name
    return p if p.is_file() else None


def _eligible(row, bucket):
    return (row.status == "xong" and row.is_active
            and (row.rollout_percent >= 100 or bucket < row.rollout_percent))


def build_feed(rows, fingerprint):
    bucket = rollout_bucket(fingerprint)
    done = sorted((r for r in rows if r.status == "xong"), key=lambda r: parse_semver(r.version))
    ok = [r for r in done if _eligible(r, bucket)]
    if not ok:
        return {"Assets": []}
    top = max(parse_semver(r.version) for r in ok)
    assets = []
    for r in done:
        items = json.loads(r.assets_json or "[]")
        if r in ok:
            assets.extend(items)
        elif parse_semver(r.version) <= top:
            assets.extend(a for a in items if a.get("Type") == "Delta")
    return {"Assets": assets}


def served_filenames(rows):
    names = set()
    for r in rows:
        if r.status == "xong":
            names.update(a.get("FileName", "") for a in json.loads(r.assets_json or "[]"))
    return names
```

- [ ] **Step 4: Thêm route**

`server/app/routers/updates.py`: đổi dòng import `from fastapi.responses import FileResponse, Response` thành `from fastapi.responses import FileResponse, JSONResponse, Response`; đổi `from app.models import AppVersion` thành `from app.models import AppVersion, VelopackRelease`; thêm `from app.services import storage, velopack_feed` (thay dòng `from app.services import storage`). Ngay sau `router = APIRouter(...)` thêm:

```python
# Route không prefix: link tải cố định cho lần cài đầu.
public_router = APIRouter(tags=["updates"])
```

Cuối file thêm:

```python
# ── Velopack (bản 1.9.0 trở đi) ─────────────────────────────────────────────
# Mã máy nằm trong ĐƯỜNG DẪN vì Velopack nối tên file vào URL gốc của feed.
# Route releases.win.json phải khai báo TRƯỚC route {filename}.
@router.get("/velopack/{fingerprint}/releases.win.json")
def velopack_feed_json(fingerprint: str, db: Session = Depends(get_db)):
    if not velopack_feed.valid_fingerprint(fingerprint):
        return Response(status_code=404)
    rows = db.scalars(select(VelopackRelease)).all()
    return JSONResponse(velopack_feed.build_feed(rows, fingerprint))


@router.get("/velopack/{fingerprint}/{filename}")
def velopack_file(fingerprint: str, filename: str, db: Session = Depends(get_db)):
    if not velopack_feed.valid_fingerprint(fingerprint):
        return Response(status_code=404)
    rows = db.scalars(select(VelopackRelease).where(VelopackRelease.status == "xong")).all()
    if filename not in velopack_feed.served_filenames(rows):
        return Response(status_code=404)
    path = velopack_feed.file_path(filename)
    if path is None:
        return Response(status_code=404)
    return FileResponse(path, media_type="application/octet-stream", filename=filename)


@public_router.get("/tai-ve")
def tai_ve(db: Session = Depends(get_db)):
    """Bộ cài lần đầu: bản ổn định mới nhất đã phát cho 100% máy."""
    rows = db.scalars(
        select(VelopackRelease).where(
            VelopackRelease.status == "xong",
            VelopackRelease.is_active.is_(True),
            VelopackRelease.rollout_percent >= 100,
        )
    ).all()
    rows = [r for r in rows if r.setup_filename]
    if not rows:
        return Response(status_code=404, content="Chưa có bản cài", media_type="text/plain; charset=utf-8")
    best = max(rows, key=lambda r: velopack_feed.parse_semver(r.version))
    path = velopack_feed.file_path(best.setup_filename)
    if path is None:
        return Response(status_code=404, content="Thiếu file bản cài", media_type="text/plain; charset=utf-8")
    return FileResponse(path, media_type="application/octet-stream", filename="QuangLuuStudio-CaiDat.exe")
```

`server/app/main.py`: ngay sau `app.include_router(updates.router)` thêm `app.include_router(updates.public_router)`.

- [ ] **Step 5: Chạy test, xác nhận qua**

Run: `cd /mnt/d/Projects/quang-luu-studio/server && ~/.venvs/qls-server/bin/python -m pytest tests/test_velopack_feed.py tests/test_updates_crash.py -q`
Expected: tất cả PASS.

- [ ] **Step 6: Commit**

```bash
git add server/app/services/velopack_feed.py server/app/routers/updates.py server/app/main.py server/tests/test_velopack_feed.py server/tests/conftest.py
git commit -m "feat(server): feed Velopack theo máy (is_active + rollout), tải gói .nupkg, link /tai-ve"
```

---

### Task 3: Nhập một bản từ GitHub Release

**Files:**
- Create: `server/app/services/velopack_import.py`
- Test: `server/tests/test_velopack_import.py`

**Interfaces:**
- Consumes: `velopack_feed.velopack_dir()`, `valid_filename()`; `settings.github_repo`; `SessionLocal`.
- Produces: `velopack_import.import_release(release_id: int, *, client: httpx.Client | None = None, session_factory=SessionLocal) -> None` — cập nhật dòng thành `xong` (kèm `assets_json`, `setup_filename`) hoặc `loi` (kèm `import_error`). Hằng `FEED_ASSET = "releases.win.json"`, `SETUP_ASSET = "QuangLuuStudio-CaiDat.exe"`.

- [ ] **Step 1: Viết test thất bại**

```python
# server/tests/test_velopack_import.py
"""Nhập bản Velopack từ GitHub Release: chỉ lấy tài sản của đúng bản, kiểm SHA256."""
import hashlib
import json

import httpx

from app.db import SessionLocal
from app.models import VelopackRelease
from app.services import velopack_feed, velopack_import

FULL = b"full-1.9.1"
DELTA = b"delta-1.9.1"
SETUP = b"MZsetup"


def _a(version, kind, data):
    return {"PackageId": "QuangLuuStudio", "Version": version, "Type": kind,
            "FileName": f"QuangLuuStudio-{version}-{kind.lower()}.nupkg", "SHA1": "",
            "SHA256": hashlib.sha256(data).hexdigest(), "Size": len(data),
            "NotesMarkdown": "", "NotesHtml": ""}


def _transport(feed_assets, files):
    base = "https://github.com/dl/"
    release = {"assets": [{"name": n, "browser_download_url": base + n} for n in files]}

    def handler(req):
        url = str(req.url)
        if url.endswith("/releases/tags/v1.9.1"):
            return httpx.Response(200, json=release)
        name = url.rsplit("/", 1)[-1]
        if name == "releases.win.json":
            return httpx.Response(200, json={"Assets": feed_assets})
        if name in files:
            return httpx.Response(200, content=files[name])
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def _new_row():
    with SessionLocal() as db:
        row = VelopackRelease(version="1.9.1")
        db.add(row)
        db.commit()
        return row.id


def _row(rid):
    with SessionLocal() as db:
        return db.get(VelopackRelease, rid)


def test_nhap_thanh_cong(client):
    old = _a("1.9.0", "Full", b"old")
    full, delta = _a("1.9.1", "Full", FULL), _a("1.9.1", "Delta", DELTA)
    files = {"releases.win.json": b"", full["FileName"]: FULL, delta["FileName"]: DELTA,
             "QuangLuuStudio-CaiDat.exe": SETUP}
    rid = _new_row()
    with httpx.Client(transport=_transport([old, full, delta], files)) as c:
        velopack_import.import_release(rid, client=c)
    row = _row(rid)
    assert row.status == "xong", row.import_error
    assert [a["Version"] for a in json.loads(row.assets_json)] == ["1.9.1", "1.9.1"]
    assert (velopack_feed.velopack_dir() / full["FileName"]).read_bytes() == FULL
    assert row.setup_filename == "1.9.1_QuangLuuStudio-CaiDat.exe"
    assert (velopack_feed.velopack_dir() / row.setup_filename).read_bytes() == SETUP
    # bản nhập xong vẫn chưa phát
    assert row.is_active is False and row.rollout_percent == 0


def test_sai_sha_bao_loi(client):
    full = _a("1.9.1", "Full", FULL)
    files = {"releases.win.json": b"", full["FileName"]: b"hong-roi"}
    rid = _new_row()
    with httpx.Client(transport=_transport([full], files)) as c:
        velopack_import.import_release(rid, client=c)
    row = _row(rid)
    assert row.status == "loi"
    assert "SHA256" in row.import_error or "kích thước" in row.import_error
    assert list(velopack_feed.velopack_dir().iterdir()) == []


def test_thieu_feed_bao_loi(client):
    rid = _new_row()
    with httpx.Client(transport=_transport([], {"QuangLuuStudio-CaiDat.exe": SETUP})) as c:
        velopack_import.import_release(rid, client=c)
    row = _row(rid)
    assert row.status == "loi" and "releases.win.json" in row.import_error


def test_ten_file_doc_hai_bi_tu_choi(client):
    bad = _a("1.9.1", "Full", FULL)
    bad["FileName"] = "../../app.db"
    rid = _new_row()
    with httpx.Client(transport=_transport([bad], {"releases.win.json": b"", "../../app.db": FULL})) as c:
        velopack_import.import_release(rid, client=c)
    row = _row(rid)
    assert row.status == "loi"
    assert list(velopack_feed.velopack_dir().iterdir()) == []
```

- [ ] **Step 2: Chạy test, xác nhận thất bại**

Run: `cd /mnt/d/Projects/quang-luu-studio/server && ~/.venvs/qls-server/bin/python -m pytest tests/test_velopack_import.py -q`
Expected: FAIL — `ImportError: cannot import name 'velopack_import'`.

- [ ] **Step 3: Viết service**

```python
# server/app/services/velopack_import.py
"""Nhập một bản Velopack từ GitHub Release về storage_dir/velopack.

Chạy nền (BackgroundTasks) vì gói Full ~500 MB. Chỉ lấy các phần tử Assets
của ĐÚNG phiên bản (releases.win.json của vpk còn liệt kê bản trước), kiểm
kích thước + SHA256 từng gói, ghi qua file .part rồi mới đổi tên.
"""
import hashlib
import json
import logging
import os

import httpx

from app.config import settings
from app.db import SessionLocal
from app.models import VelopackRelease
from app.services import velopack_feed

log = logging.getLogger(__name__)

FEED_ASSET = "releases.win.json"
SETUP_ASSET = "QuangLuuStudio-CaiDat.exe"


def _download(client, url, name, expect_sha256=None, expect_size=None):
    if not velopack_feed.valid_filename(name):
        raise ValueError(f"Tên file không hợp lệ: {name!r}")
    dest = velopack_feed.velopack_dir() / name
    tmp = dest.with_name(dest.name + ".part")
    h = hashlib.sha256()
    size = 0
    try:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in resp.iter_bytes(1024 * 1024):
                    f.write(chunk)
                    h.update(chunk)
                    size += len(chunk)
        if expect_size and size != int(expect_size):
            raise ValueError(f"{name}: sai kích thước ({size} ≠ {expect_size})")
        if expect_sha256 and h.hexdigest().lower() != str(expect_sha256).lower():
            raise ValueError(f"{name}: sai SHA256")
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink()


def _download_all(client, version):
    api = f"https://api.github.com/repos/{settings.github_repo}/releases/tags/v{version}"
    r = client.get(api, headers={"Accept": "application/vnd.github+json"})
    r.raise_for_status()
    urls = {a["name"]: a["browser_download_url"] for a in r.json().get("assets", [])}
    if FEED_ASSET not in urls:
        raise ValueError(f"Release v{version} thiếu {FEED_ASSET}")
    feed = client.get(urls[FEED_ASSET])
    feed.raise_for_status()
    mine = [a for a in feed.json().get("Assets", []) if a.get("Version") == version]
    if not any(a.get("Type") == "Full" for a in mine):
        raise ValueError(f"{FEED_ASSET} không có gói Full của bản {version}")
    for a in mine:
        name = a.get("FileName", "")
        if not velopack_feed.valid_filename(name):
            raise ValueError(f"Tên file không hợp lệ trong feed: {name!r}")
        if name not in urls:
            raise ValueError(f"Release v{version} thiếu {name}")
        _download(client, urls[name], name, a.get("SHA256"), a.get("Size"))
    setup_name = None
    if SETUP_ASSET in urls:
        setup_name = f"{version}_{SETUP_ASSET}"
        _download(client, urls[SETUP_ASSET], setup_name)
    return mine, setup_name


def import_release(release_id, *, client=None, session_factory=SessionLocal):
    own = client is None
    if own:
        client = httpx.Client(timeout=httpx.Timeout(60.0, read=300.0), follow_redirects=True,
                              headers={"User-Agent": "QuangLuuStudio-Server"})
    try:
        with session_factory() as db:
            version = db.get(VelopackRelease, release_id).version
        try:
            assets, setup_name = _download_all(client, version)
            status, error = "xong", None
        except Exception as e:  # mọi lỗi → trạng thái "loi" để admin thấy, không làm chết worker
            log.warning("Nhập Velopack %s lỗi: %s", version, e)
            assets, setup_name, status, error = None, None, "loi", f"{type(e).__name__}: {e}"
        with session_factory() as db:
            row = db.get(VelopackRelease, release_id)
            row.status = status
            row.import_error = error
            if assets is not None:
                row.assets_json = json.dumps(assets, ensure_ascii=False)
                row.setup_filename = setup_name
            db.commit()
    finally:
        if own:
            client.close()
```

Lưu ý `test_sai_sha_bao_loi`: gói Full sai SHA nằm sau khi đã kiểm tên → `_download` xoá `.part`, không có file nào còn lại. `test_ten_file_doc_hai_bi_tu_choi`: lỗi ném trước khi tải.

- [ ] **Step 4: Chạy test, xác nhận qua**

Run: lệnh Step 2. Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add server/app/services/velopack_import.py server/tests/test_velopack_import.py
git commit -m "feat(server): nhập bản Velopack từ GitHub Release (chỉ tài sản của bản đó, kiểm SHA256 + kích thước)"
```

---

### Task 4: Trang admin — nhập, bật/tắt, chỉnh rollout

**Files:**
- Modify: `server/app/routers/admin.py` (import; `versions_page` ~dòng 423; thêm 3 route sau `toggle_version` ~dòng 474)
- Modify: `server/app/templates/versions.html` (thêm khối Velopack ở đầu)
- Test: `server/tests/test_velopack_admin.py`

**Interfaces:**
- Consumes: `VelopackRelease`, `velopack_import.import_release`.
- Produces: `POST /admin/velopack/import` (form `version`), `POST /admin/velopack/{rid}/toggle`, `POST /admin/velopack/{rid}/rollout` (form `rollout_percent`).

- [ ] **Step 1: Viết test thất bại**

```python
# server/tests/test_velopack_admin.py
from unittest.mock import patch

from app.db import SessionLocal
from app.models import VelopackRelease


def _rows():
    with SessionLocal() as db:
        return db.query(VelopackRelease).order_by(VelopackRelease.id).all()


def test_nhap_tao_dong_va_chay_nen(admin_client):
    with patch("app.routers.admin.velopack_import.import_release") as imp:
        r = admin_client.post("/admin/velopack/import", data={"version": "v1.9.1"}, follow_redirects=False)
    assert r.status_code == 303
    rows = _rows()
    assert [(x.version, x.status) for x in rows] == [("1.9.1", "dang_nhap")]
    imp.assert_called_once_with(rows[0].id)


def test_nhap_lai_cung_phien_ban(admin_client):
    with patch("app.routers.admin.velopack_import.import_release") as imp:
        admin_client.post("/admin/velopack/import", data={"version": "1.9.1"})
        with SessionLocal() as db:
            row = db.query(VelopackRelease).one()
            row.status, row.import_error = "loi", "x"
            db.commit()
        admin_client.post("/admin/velopack/import", data={"version": "1.9.1"})
    rows = _rows()
    assert len(rows) == 1 and rows[0].status == "dang_nhap" and rows[0].import_error is None
    assert imp.call_count == 2


def test_phien_ban_sai_dinh_dang_bo_qua(admin_client):
    with patch("app.routers.admin.velopack_import.import_release") as imp:
        admin_client.post("/admin/velopack/import", data={"version": "abc; rm -rf"})
    assert _rows() == []
    imp.assert_not_called()


def test_bat_tat_va_rollout(admin_client):
    with SessionLocal() as db:
        db.add(VelopackRelease(version="1.9.1", status="xong"))
        db.commit()
        rid = db.query(VelopackRelease).one().id
    admin_client.post(f"/admin/velopack/{rid}/toggle")
    admin_client.post(f"/admin/velopack/{rid}/rollout", data={"rollout_percent": "150"})
    row = _rows()[0]
    assert row.is_active is True and row.rollout_percent == 100


def test_trang_phien_ban_hien_bang_velopack(admin_client):
    with SessionLocal() as db:
        db.add(VelopackRelease(version="1.9.1", status="loi", import_error="Release v1.9.1 thiếu releases.win.json"))
        db.commit()
    html = admin_client.get("/admin/versions").text
    assert "1.9.1" in html and "thiếu releases.win.json" in html


def test_can_dang_nhap(client):
    r = client.post("/admin/velopack/import", data={"version": "1.9.1"}, follow_redirects=False)
    assert r.status_code in (302, 303, 401)
    assert _rows() == []
```

- [ ] **Step 2: Chạy test, xác nhận thất bại**

Run: `cd /mnt/d/Projects/quang-luu-studio/server && ~/.venvs/qls-server/bin/python -m pytest tests/test_velopack_admin.py -q`
Expected: FAIL — 404/405 cho `/admin/velopack/import`.

- [ ] **Step 3: Viết code**

`server/app/routers/admin.py`:
- Dòng `from fastapi import APIRouter, Depends, File, Form, Request, UploadFile` → thêm `BackgroundTasks`.
- Thêm `import re` vào khối import chuẩn đầu file.
- Trong `from app.models import (...)` thêm `VelopackRelease`.
- Dòng `from app.services import codegen, storage, tonelib` → `from app.services import codegen, storage, tonelib, velopack_import`.

Thay `versions_page` bằng:

```python
@router.get("/versions", response_class=HTMLResponse)
def versions_page(request: Request, admin: str = Depends(current_admin), db: Session = Depends(get_db)):
    versions = db.scalars(select(AppVersion).order_by(AppVersion.published_at.desc())).all()
    velopack = db.scalars(select(VelopackRelease).order_by(VelopackRelease.published_at.desc())).all()
    return templates.TemplateResponse(request, "versions.html",
                                      {"admin": admin, "versions": versions, "velopack": velopack})
```

Sau `toggle_version` thêm:

```python
# ── Velopack: nhập từ GitHub Release, bật/tắt, chỉnh % phát ──
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(-[A-Za-z0-9.]+)?$")


@router.post("/velopack/import")
def velopack_import_release(
    background: BackgroundTasks,
    version: str = Form(...),
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
):
    v = version.strip().lstrip("v")
    if not _VERSION_RE.match(v):
        return _redirect("/admin/versions")
    row = db.scalar(select(VelopackRelease).where(VelopackRelease.version == v))
    if row is None:
        row = VelopackRelease(version=v)
        db.add(row)
    # Nhập lại được: dòng kẹt "dang_nhap" (worker khởi động lại) hoặc "loi".
    row.status = "dang_nhap"
    row.import_error = None
    db.commit()
    background.add_task(velopack_import.import_release, row.id)
    return _redirect("/admin/versions")


@router.post("/velopack/{rid}/toggle")
def velopack_toggle(rid: int, admin: str = Depends(current_admin), db: Session = Depends(get_db)):
    row = db.get(VelopackRelease, rid)
    if row and row.status == "xong":
        row.is_active = not row.is_active
        db.commit()
    return _redirect("/admin/versions")


@router.post("/velopack/{rid}/rollout")
def velopack_rollout(
    rid: int,
    rollout_percent: int = Form(...),
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
):
    row = db.get(VelopackRelease, rid)
    if row:
        row.rollout_percent = max(0, min(rollout_percent, 100))
        db.commit()
    return _redirect("/admin/versions")
```

`server/app/templates/versions.html`: ngay sau `<h1>Phiên bản</h1>` chèn:

```html
<h2>Velopack (1.9.0 trở đi — cập nhật ngầm)</h2>
<div class="card">
  <form method="post" action="/admin/velopack/import" class="row">
    <div><label>Nhập từ GitHub Release (vd 1.9.1)</label><input name="version" required></div>
    <button type="submit">Nhập</button>
  </form>
  <p>Bản nhập xong <b>chưa phát</b>: bật lên rồi chỉnh % máy nhận. Link cài lần đầu: <code>/tai-ve</code> (bản mới nhất đang phát 100%).</p>
</div>
<table>
  <tr><th>Version</th><th>Trạng thái</th><th>Rollout</th><th>Active</th><th></th></tr>
  {% for r in velopack %}
  <tr>
    <td>{{ r.version }}</td>
    <td>{{ {'dang_nhap': '⏳ đang nhập', 'xong': '✓ xong', 'loi': '✗ lỗi'}.get(r.status, r.status) }}
        {% if r.import_error %}<br><small>{{ r.import_error }}</small>{% endif %}</td>
    <td><form method="post" action="/admin/velopack/{{ r.id }}/rollout" class="row">
          <input name="rollout_percent" type="number" min="0" max="100" value="{{ r.rollout_percent }}" style="width:5em">
          <button class="ghost">Lưu</button></form></td>
    <td>{{ '🟢' if r.is_active else '⚪' }}</td>
    <td>{% if r.status == 'xong' %}<form method="post" action="/admin/velopack/{{ r.id }}/toggle"><button class="ghost">{{ 'Tắt' if r.is_active else 'Bật' }}</button></form>{% endif %}</td>
  </tr>
  {% endfor %}
</table>
<h2>Bộ cài Inno (máy 1.8.x — bộ cài cầu nối)</h2>
```

- [ ] **Step 4: Chạy test, xác nhận qua**

Run: `cd /mnt/d/Projects/quang-luu-studio/server && ~/.venvs/qls-server/bin/python -m pytest -q`
Expected: toàn bộ suite server PASS.

- [ ] **Step 5: Commit**

```bash
git add server/app/routers/admin.py server/app/templates/versions.html server/tests/test_velopack_admin.py
git commit -m "feat(server): trang admin nhập bản Velopack từ GitHub, bật/tắt và chỉnh % phát"
```

---

### Task 5: Triển khai lên VPS (hỏi người dùng trước)

**Files:** không đổi code.

- [ ] **Step 1: Xin phép** — báo người dùng: commit sẽ deploy, việc tạo bảng mới, thời gian gián đoạn dự kiến (`docker compose up -d --build`, ~1 phút). Chờ đồng ý.

- [ ] **Step 2: Làm theo memory `vps-deploy-procedure`**: sao lưu vào `/opt/qls/server/backups/<YYYYmmdd-HHMMSS>-pre-velopack-feed/` (`.env`, `pg_dump`, `app_before.tgz`); so code VPS với commit đã deploy lần trước (`diff -r --strip-trailing-cr`) để chắc không có sửa nóng; `git archive HEAD server/app server/deploy server/tests server/Dockerfile server/docker-compose.yml server/requirements.txt` → scp → `tar xzf` tại `/opt/qls` → `cd server && docker compose up -d --build`.

- [ ] **Step 3: Tạo bảng**

Run (trên VPS): `cd /opt/qls/server && docker compose exec -T api python -m app.cli init-db`
Expected: `Đã tạo bảng.` (chỉ tạo bảng còn thiếu — `velopack_releases`).

- [ ] **Step 4: Kiểm nhanh**

```
curl -s https://qlstudio.duckdns.org/api/v1/updates/velopack/thu-may/releases.win.json   → {"Assets":[]}
curl -s -o /dev/null -w '%{http_code}' https://qlstudio.duckdns.org/tai-ve                → 404
curl -s -o /dev/null -w '%{http_code}' "https://qlstudio.duckdns.org/api/v1/updates/check?version=1.8.0&fingerprint=x"  → 200
```
Và `docker compose logs --tail=25 api` có "Application startup complete".

- [ ] **Step 5: Ghi memory** — thêm một dòng vào `vps-deploy-procedure.md`: ngày deploy, commit, tên thư mục sao lưu, bảng `velopack_releases` đã tạo.
