# Admin đặt tone + phân phối tới client — Kế hoạch triển khai

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admin đặt tone cho một bài trên `/admin/library`; mọi máy khách đã kích hoạt nhận bản đó qua feed cursor và ghi vào tone_cache, không đè chuỗi tone khách sửa tay.

**Architecture:** Server thêm nguồn `admin` cho `SharedTone`, form "Đặt tone" tự ghim, và endpoint `POST /api/v1/library/changes` phân trang keyset theo `(last_seen, id)` với cursor opaque. Client thêm `tone_share.pull_overrides()` ghi `origin="admin"` vào tone_cache (nấc resolve sẵn có, đứng trên tone bài đã lưu và cộng đồng, dưới chuỗi tone thủ công), gọi từ vòng bảo trì nền, nút "☁ Đồng bộ tone" và "Đồng bộ ngay".

**Tech Stack:** Server FastAPI + SQLAlchemy 2 + Pydantic 2 + Jinja2, test bằng `TestClient` trên SQLite (`server/tests/conftest.py`). Client Python 3.11+ thuần (`core/tone_share.py`), test pytest với `monkeypatch`.

**Spec:** `docs/superpowers/specs/2026-10-03-admin-tone-override-design.md`

## Global Constraints

- Không migration DB: server chỉ `Base.metadata.create_all` (`server/app/cli.py`). Không thêm cột. Dùng `SharedTone.last_seen` làm mốc feed.
- Trang feed tối đa **500** bản ghi; server hỏi **501** để biết `has_more`.
- Cursor là chuỗi opaque: base64url không padding của JSON `{"ts": "<last_seen.isoformat()>", "id": <int>}`. `ts` giữ dạng chuỗi ISO, **không** đổi sang epoch float.
- Client áp hết item của một trang rồi mới lưu `next_cursor`; tối đa **20** trang một lượt.
- Bài có `ManualToneTimeline.get_timeline_source(url) == "human"` → **không** ghi đè.
- Client chỉ được gửi `source` là `auto` hoặc `human` qua `contribute`; giá trị khác ép về `auto`.
- Chạy test server: `cd server && python -m pytest tests -q`.
- Chạy test client core (`tests/core/test_tone_share.py`, `test_tone_resolve_saved.py`): Linux hoặc Windows đều được, `python -m pytest tests/core -q`.
- `tests/ui` và `tests/core/test_engine.py` chỉ chạy bằng Python Windows (engine import `ctypes.WINFUNCTYPE`). Từ WSL: `cmd.exe /c "D:\Projects\quang-luu-studio\.venv\Scripts\python.exe -m pytest D:\Projects\quang-luu-studio\tests\ui -q -p no:cacheprovider --rootdir=D:\Projects\quang-luu-studio"`. Sau khi chạy, `git checkout -- app_config.json` (suite ghi đè line-ending file này).
- Commit sau mỗi task, message tiếng Việt theo mẫu repo (`feat(server): ...`, `feat(tone-share): ...`).

## Review Focus

1. Nhiều bản ghim có **cùng `last_seen`** vắt qua ranh giới trang (admin đặt 600 bài trong một giây bằng script) → không bản nào bị sót hay lặp. Test ở Task 3 (ép `CHANGES_PAGE_SIZE = 2`).
2. **Cursor hỏng** (client cũ gửi chuỗi lạ, hoặc file trạng thái bị sửa tay) → server coi như rỗng, `ok: true`, client vẫn nhận đủ. Test ở Task 3.
3. **Mất mạng ở trang 2** → cursor client dừng ở trang 1 đã áp xong, lần sau lấy tiếp trang 2, không mất bản nào. Test ở Task 4.
4. Admin **xoá** bản ghim duy nhất của bài → bài không còn bản thắng; feed không phát gì; client giữ nguyên tone cũ (chấp nhận theo spec §3.2). Admin **ghim bản khác** của cùng bài → bản mới có `last_seen` mới và đi vào feed. Test ở Task 2.
5. Client gửi `source="admin"` qua `contribute` để "tự phong" → bị ép về `auto`, không được trọng số 10. Test ở Task 1.

---

### Task 1: tonelib — nguồn `admin`, parse mốc thời gian, mã hoá cursor

**Files:**
- Modify: `server/app/services/tonelib.py`
- Modify: `server/app/routers/library.py:160-175` (ép nguồn client)
- Test: `server/tests/test_tonelib_admin.py` (mới), `server/tests/test_library.py`

**Interfaces:**
- Produces:
  - `tonelib.SOURCES == ("auto", "human", "admin")`, `tonelib.CLIENT_SOURCES == ("auto", "human")`, `tonelib.SOURCE_WEIGHT["admin"] == 10`
  - `tonelib.key_display(index: int, scale: str) -> str` — `(6, "Minor") → "F#m"`
  - `tonelib.parse_time(text: str) -> float | None` — `"1:35" → 95.0`, `"95" → 95.0`, `"1:02:03" → 3723.0`
  - `tonelib.parse_timeline_text(text: str, primary_key: str) -> list[dict] | None` — trả list entry `{time, key_display, key_index, scale}` đã sắp theo `time`, hoặc `None` nếu một dòng không đọc được
  - `tonelib.encode_cursor(last_seen: datetime, tone_id: int) -> str`
  - `tonelib.decode_cursor(text: str) -> tuple[datetime, int] | None`

- [ ] **Step 1: Viết test đỏ cho tonelib**

Tạo `server/tests/test_tonelib_admin.py`:

```python
"""tonelib: nguồn admin, đọc mốc thời gian từ form, cursor keyset."""
from datetime import datetime, timezone

from app.services import tonelib


def test_nguon_admin_nang_hon_nguoi_sua():
    assert "admin" in tonelib.SOURCES
    assert tonelib.SOURCE_WEIGHT["admin"] > tonelib.SOURCE_WEIGHT["human"]
    assert tonelib.CLIENT_SOURCES == ("auto", "human")


def test_key_display_tu_index_va_the():
    assert tonelib.key_display(6, "Minor") == "F#m"
    assert tonelib.key_display(0, "Major") == "C"
    assert tonelib.key_display(11, "Minor") == "Bm"


def test_parse_time_cac_dang():
    assert tonelib.parse_time("1:35") == 95.0
    assert tonelib.parse_time("95") == 95.0
    assert tonelib.parse_time("1:02:03") == 3723.0
    assert tonelib.parse_time("0:00") == 0.0
    assert tonelib.parse_time("abc") is None
    assert tonelib.parse_time("1:xx") is None
    assert tonelib.parse_time("-5") is None


def test_parse_timeline_text_trong_thi_mot_moc_theo_tone_chinh():
    entries = tonelib.parse_timeline_text("", "F#m")
    assert entries == [{"time": 0.0, "key_display": "F#m", "key_index": 6, "scale": "Minor"}]


def test_parse_timeline_text_nhieu_moc_sap_theo_thoi_gian():
    entries = tonelib.parse_timeline_text("1:35 Bm\n0:00 F#m\n\n3:10 C# Major", "F#m")
    assert [e["time"] for e in entries] == [0.0, 95.0, 190.0]
    assert [e["key_display"] for e in entries] == ["F#m", "Bm", "C#"]
    assert entries[2] == {"time": 190.0, "key_display": "C#", "key_index": 1, "scale": "Major"}


def test_parse_timeline_text_dong_hong_thi_tra_none():
    assert tonelib.parse_timeline_text("0:00 F#m\n1:35", "F#m") is None
    assert tonelib.parse_timeline_text("0:00 Xm", "F#m") is None
    assert tonelib.parse_timeline_text("", "không phải tone") is None


def test_cursor_di_va_ve_giu_nguyen_micro_giay():
    ts = datetime(2026, 10, 3, 10, 0, 0, 123456, tzinfo=timezone.utc)
    text = tonelib.encode_cursor(ts, 42)
    assert isinstance(text, str) and "=" not in text and "{" not in text
    assert tonelib.decode_cursor(text) == (ts, 42)


def test_cursor_hong_tra_none():
    assert tonelib.decode_cursor("") is None
    assert tonelib.decode_cursor("không phải base64!!") is None
    assert tonelib.decode_cursor(tonelib._b64(b'{"ts": 5, "id": "x"}')) is None
    assert tonelib.decode_cursor(tonelib._b64(b'[1,2]')) is None
```

Thêm vào cuối `server/tests/test_library.py`:

```python
def test_client_tu_phong_admin_bi_ep_ve_auto(client):
    """Nguồn 'admin' chỉ do form admin tạo; client gửi lên là tự phong, ép về auto."""
    fp = "may-gia-admin"
    token = _token(client, fp)
    res = _contribute(client, token, fp, _timeline((0, "F#m")), source="admin")
    assert res.json()["accepted"] == 1

    result = _lookup(client, token, fp).json()["results"][SONG]
    assert result["source"] == "auto"
```

- [ ] **Step 2: Chạy test, xác nhận đỏ**

Run: `cd server && python -m pytest tests/test_tonelib_admin.py tests/test_library.py::test_client_tu_phong_admin_bi_ep_ve_auto -q`
Expected: FAIL — `AttributeError: module 'app.services.tonelib' has no attribute 'CLIENT_SOURCES'` (và các hàm mới), test contribute FAIL vì `source == "admin"` được giữ nguyên.

- [ ] **Step 3: Hiện thực trong tonelib**

Trong `server/app/services/tonelib.py`, thay:

```python
SOURCES = ("auto", "human")
```
bằng
```python
# auto: máy dò | human: người dùng sửa tay | admin: dev đặt trên /admin/library.
# CLIENT_SOURCES là tập client ĐƯỢC PHÉP gửi qua /contribute; "admin" chỉ do
# form admin tạo — client gửi "admin" là tự phong, router ép về "auto".
SOURCES = ("auto", "human", "admin")
CLIENT_SOURCES = ("auto", "human")
```

Thay `SOURCE_WEIGHT = {"human": 3, "auto": 1}` bằng:

```python
# admin = 10: bản dev đặt luôn được ghim nên trọng số chỉ để xếp hạng hiển thị
# và phòng khi dev bỏ ghim mà vẫn muốn nó thắng.
SOURCE_WEIGHT = {"admin": 10, "human": 3, "auto": 1}
```

Thêm `import base64` và `from datetime import datetime` ở đầu file. Thêm sau hàm `parse_key`:

```python
def key_display(index: int, scale: str) -> str:
    """(6, 'Minor') → 'F#m' — cùng quy ước sharp của app (ToneDetector.MINOR_KEY_NAMES)."""
    return NOTES_SHARP[int(index) % 12] + ("m" if scale == "Minor" else "")


def parse_time(text) -> float | None:
    """'1:35' → 95.0, '95' → 95.0, '1:02:03' → 3723.0. None nếu không đọc được/âm."""
    parts = str(text or "").strip().split(":")
    if not parts or len(parts) > 3:
        return None
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return None
    if any(n < 0 for n in nums):
        return None
    total = 0.0
    for n in nums:
        total = total * 60 + n
    return total


def parse_timeline_text(text: str, primary_key: str) -> list | None:
    """Ô 'mốc thời gian' trên form admin → list entry chuẩn của thư viện.

    Mỗi dòng: `<mm:ss|giây> <tone>`. Bỏ trống → một mốc 0s theo `primary_key`.
    Một dòng sai là trả None cho CẢ ô: admin sửa lại, không ghi nửa vời.
    """
    lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]
    if not lines:
        parsed = parse_key(primary_key)
        if not parsed:
            return None
        idx, scale = parsed
        return [{"time": 0.0, "key_display": key_display(idx, scale),
                 "key_index": idx, "scale": scale}]

    entries = []
    for line in lines:
        parts = line.split(None, 1)
        if len(parts) != 2:
            return None
        seconds = parse_time(parts[0])
        parsed = parse_key(parts[1])
        if seconds is None or not parsed:
            return None
        idx, scale = parsed
        entries.append({"time": seconds, "key_display": key_display(idx, scale),
                        "key_index": idx, "scale": scale})
    entries.sort(key=lambda e: e["time"])
    return entries


# ── Cursor keyset cho /api/v1/library/changes ──
# Opaque với client: base64url(JSON {"ts": isoformat, "id": int}). `ts` giữ chuỗi
# ISO đúng như last_seen trong DB — đổi sang epoch float là lệch micro giây,
# vế tie-break `last_seen = :ts` không bao giờ khớp nữa.
def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def encode_cursor(last_seen: datetime, tone_id: int) -> str:
    payload = json.dumps({"ts": last_seen.isoformat(), "id": int(tone_id)}, separators=(",", ":"))
    return _b64(payload.encode("utf-8"))


def decode_cursor(text) -> tuple | None:
    """(last_seen, id) hoặc None nếu chuỗi hỏng — caller coi như cursor rỗng."""
    if not text or not isinstance(text, str):
        return None
    try:
        padded = text + "=" * (-len(text) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if not isinstance(data, dict) or not isinstance(data.get("ts"), str):
            return None
        ts = datetime.fromisoformat(data["ts"])
        tone_id = int(data["id"])
    except (ValueError, TypeError, KeyError, AttributeError):
        return None
    return ts, tone_id
```

Trong `server/app/routers/library.py`, hàm `contribute`, thay:

```python
        source = item.source.lower() if item.source.lower() in tonelib.SOURCES else "auto"
```
bằng
```python
        # Chỉ auto|human từ client. "admin" do form /admin/library tạo — client
        # gửi "admin" là tự phong, không được trọng số của dev.
        source = item.source.lower() if item.source.lower() in tonelib.CLIENT_SOURCES else "auto"
```

- [ ] **Step 4: Chạy test, xác nhận xanh**

Run: `cd server && python -m pytest tests -q`
Expected: tất cả PASS (111 cũ + 9 mới).

- [ ] **Step 5: Commit**

```bash
git add server/app/services/tonelib.py server/app/routers/library.py server/tests/test_tonelib_admin.py server/tests/test_library.py
git commit -m "feat(server): tonelib — nguồn admin, parse mốc thời gian form, cursor keyset"
```

---

### Task 2: Admin "Đặt tone" trên `/admin/library` + bơm `last_seen` khi admin đổi bản thắng

**Files:**
- Modify: `server/app/routers/admin.py:583-620` (library_page nhận `msg`), `:777-810` (pin/hide/delete), thêm route `/library/set`
- Modify: `server/app/templates/library.html`
- Test: `server/tests/test_admin_library_set.py` (mới)

**Interfaces:**
- Consumes: `tonelib.parse_key`, `tonelib.parse_timeline_text`, `tonelib.normalize_timeline`, `tonelib.payload_hash`, `tonelib.best_variant`, `tonelib.key_display` (Task 1)
- Produces:
  - `POST /admin/library/set` form fields `song_key`, `title`, `primary_key`, `timeline` → 303 về `/admin/library?q=<song_key>&msg=...`
  - `admin._touch_winner(db, song_key)` — đặt `last_seen = now` cho bản thắng hiện tại của bài (Task 3 dựa vào đây để feed thấy thay đổi)
  - Bản admin tạo: `source="admin"`, `pinned=True`, `status="ok"`, anh em `pinned=False`

- [ ] **Step 1: Viết test đỏ**

Tạo `server/tests/test_admin_library_set.py`:

```python
"""Admin đặt tone trên /admin/library — bản admin thắng, tự ghim, bơm last_seen."""
from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.models import License, SharedTone
from app.services import codegen

SONG = "pMPvJE1wwnc"


def _token(client, fp):
    code = codegen.generate_code()
    with SessionLocal() as db:
        db.add(License(code=code, max_devices=1, status="unused", plan="standard"))
        db.commit()
    return client.post("/api/v1/activate", json={"code": code, "device_fingerprint": fp}).json()["token"]


def _contribute(client, token, fp, key, song=SONG):
    return client.post("/api/v1/library/contribute", json={
        "token": token, "device_fingerprint": fp,
        "items": [{"song_key": song, "title": "Bài test", "primary_key": key, "source": "auto",
                   "timeline": [{"time": 0, "key_display": key, "key_index": 0, "scale": "Minor"}]}],
    })


def _lookup(client, token, fp, song=SONG):
    res = client.post("/api/v1/library/lookup", json={
        "token": token, "device_fingerprint": fp, "keys": [song],
    })
    return res.json()["results"].get(song)


def _set(admin_client, **form):
    data = {"song_key": SONG, "title": "", "primary_key": "", "timeline": ""}
    data.update(form)
    return admin_client.post("/admin/library/set", data=data, follow_redirects=False)


def _variants(song=SONG):
    with SessionLocal() as db:
        return db.query(SharedTone).filter(SharedTone.song_key == song).order_by(SharedTone.id).all()


def test_dat_tone_cho_bai_chua_co(admin_client):
    fp = "may-01"
    token = _token(admin_client, fp)

    res = _set(admin_client, primary_key="F#m", title="Lưng Cha Bụng Mẹ")
    assert res.status_code == 303
    assert "/admin/library?q=" + SONG in res.headers["location"]

    found = _lookup(admin_client, token, fp)
    assert found["primary_key"] == "F#m"
    assert found["source"] == "admin"
    assert found["title"] == "Lưng Cha Bụng Mẹ"
    assert found["timeline"] == [{"time": 0.0, "key_display": "F#m", "key_index": 6, "scale": "Minor"}]
    assert _variants()[0].pinned is True


def test_dat_tone_de_ban_may_do_dang_thang(admin_client):
    fp = "may-02"
    token = _token(admin_client, fp)
    _contribute(admin_client, token, fp, "Bm")
    assert _lookup(admin_client, token, fp)["primary_key"] == "Bm"

    _set(admin_client, primary_key="F#m")

    assert _lookup(admin_client, token, fp)["primary_key"] == "F#m"
    pinned = [v.pinned for v in _variants()]
    assert pinned == [False, True], "chỉ bản admin được ghim, bản máy dò bị bỏ ghim"


def test_dat_tone_nhieu_moc_doc_dung_mm_ss(admin_client):
    fp = "may-03"
    token = _token(admin_client, fp)
    _set(admin_client, primary_key="F#m", timeline="0:00 F#m\n1:35 Bm")

    tl = _lookup(admin_client, token, fp)["timeline"]
    assert [(e["time"], e["key_display"]) for e in tl] == [(0.0, "F#m"), (95.0, "Bm")]


def test_dat_tone_trung_chuoi_voi_ban_cu_thi_nang_ban_cu_len_admin(admin_client):
    fp = "may-04"
    token = _token(admin_client, fp)
    _contribute(admin_client, token, fp, "F#m")  # máy dò ra đúng rồi

    _set(admin_client, primary_key="F#m")

    vs = _variants()
    assert len(vs) == 1, "cùng payload_hash thì không đẻ biến thể mới"
    assert vs[0].source == "admin" and vs[0].pinned is True


def test_tone_sai_cu_phap_thi_khong_ghi_gi(admin_client):
    res = _set(admin_client, primary_key="Xm")
    assert res.status_code == 303
    assert "msg=" in res.headers["location"]
    assert _variants() == []

    res = _set(admin_client, primary_key="F#m", timeline="0:00 F#m\n1:35")
    assert _variants() == []


def test_ma_video_sai_thi_khong_ghi_gi(admin_client):
    res = _set(admin_client, song_key="ngan", primary_key="F#m")
    assert res.status_code == 303
    assert _variants("ngan") == []


def test_dat_tone_can_dang_nhap_admin(client):
    res = client.post("/admin/library/set", data={"song_key": SONG, "primary_key": "F#m"},
                      follow_redirects=False)
    assert res.status_code in (302, 303, 307)
    assert _variants() == []


def test_ghim_ban_khac_thi_ban_do_duoc_bom_last_seen(admin_client):
    """Feed /changes dựa vào last_seen: admin đổi bản thắng thì bản thắng mới phải mới lên."""
    fp = "may-05"
    token = _token(admin_client, fp)
    _contribute(admin_client, token, fp, "Bm")
    _set(admin_client, primary_key="F#m")
    old_id = _variants()[0].id  # bản Bm của máy dò

    cu = datetime(2020, 1, 1, tzinfo=timezone.utc)
    with SessionLocal() as db:
        for v in db.query(SharedTone).all():
            v.last_seen = cu
        db.commit()

    admin_client.post(f"/admin/library/{old_id}/pin")

    vs = {v.id: v for v in _variants()}
    assert vs[old_id].pinned is True
    assert vs[old_id].last_seen.replace(tzinfo=timezone.utc) > cu + timedelta(days=1)


def test_an_ban_ghim_thi_ban_thang_moi_duoc_bom_last_seen(admin_client):
    fp = "may-06"
    token = _token(admin_client, fp)
    _contribute(admin_client, token, fp, "Bm")
    _set(admin_client, primary_key="F#m")
    bm_id, admin_id = [v.id for v in _variants()]

    cu = datetime(2020, 1, 1, tzinfo=timezone.utc)
    with SessionLocal() as db:
        for v in db.query(SharedTone).all():
            v.last_seen = cu
        db.commit()

    admin_client.post(f"/admin/library/{admin_id}/hide")

    vs = {v.id: v for v in _variants()}
    # Bản admin bị ẩn → bản Bm (1 phiếu auto) thắng lại và phải được bơm last_seen.
    assert vs[bm_id].last_seen.replace(tzinfo=timezone.utc) > cu + timedelta(days=1)


def test_trang_thu_vien_hien_thong_bao_va_form(admin_client):
    res = admin_client.get("/admin/library?msg=Xin+ch%C3%A0o")
    assert res.status_code == 200
    assert "Xin chào" in res.text
    assert 'action="/admin/library/set"' in res.text
```

- [ ] **Step 2: Chạy test, xác nhận đỏ**

Run: `cd server && python -m pytest tests/test_admin_library_set.py -q`
Expected: FAIL — `POST /admin/library/set` trả 404/405; `test_ghim_ban_khac...` FAIL vì `last_seen` vẫn là 2020; `test_trang_thu_vien...` FAIL vì không có form.

- [ ] **Step 3: Hiện thực route và helper trong admin.py**

Thêm import ở đầu `server/app/routers/admin.py`:

```python
from urllib.parse import quote
```

Thêm helper ngay sau `_count_segments`:

```python
def _touch_winner(db: Session, song_key: str) -> None:
    """Đặt last_seen = now cho bản THẮNG hiện tại của bài.

    Feed /api/v1/library/changes phân trang theo (last_seen, id) của bản ghim.
    Mọi hành động admin làm bản thắng đổi (đặt, ghim, ẩn, xoá) đều phải đi
    qua đây — trong cùng giao dịch — để máy khách thấy được thay đổi.
    """
    variants = db.scalars(select(SharedTone).where(SharedTone.song_key == song_key)).all()
    best = tonelib.best_variant(variants)
    if best is not None:
        best.last_seen = datetime.now(timezone.utc)


def _library_msg(song_key: str, text: str) -> RedirectResponse:
    return _redirect(f"/admin/library?q={quote(song_key)}&msg={quote(text)}")
```

Sửa `library_page` nhận và truyền `msg`:

```python
@router.get("/library", response_class=HTMLResponse)
def library_page(
    request: Request,
    q: str = "",
    msg: str = "",
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
):
```
và ở cuối hàm:
```python
    return templates.TemplateResponse(
        request, "library.html", {"admin": admin, "groups": groups, "q": term, "msg": msg}
    )
```

Thêm route mới ngay trước `library_pin`:

```python
@router.post("/library/set")
def library_set(
    song_key: str = Form(""),
    title: str = Form(""),
    primary_key: str = Form(""),
    timeline: str = Form(""),
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
):
    """Admin đặt tone cho một bài — không cần máy khách nào đóng góp trước.

    Tạo (hoặc nâng) biến thể source="admin", ghim nó, bỏ ghim anh em, bơm
    last_seen để feed /changes phát tới máy khách. Một trường sai là không
    ghi gì: admin sửa lại chứ không để nửa vời vào thư viện chung.
    """
    song_key = (song_key or "").strip()
    if not tonelib.valid_song_key(song_key):
        return _library_msg(song_key[:24], "Mã video phải là 11 ký tự YouTube id.")

    parsed_primary = tonelib.parse_key(primary_key)
    if not parsed_primary:
        return _library_msg(song_key, f"Không đọc được tone chính “{primary_key.strip()}”.")
    entries = tonelib.parse_timeline_text(timeline, primary_key)
    if not entries:
        return _library_msg(song_key, "Mốc thời gian sai: mỗi dòng dạng “mm:ss Tone”, ví dụ “1:35 Bm”.")

    primary_display = tonelib.key_display(*parsed_primary)
    normalized = tonelib.normalize_timeline(entries)
    digest = tonelib.payload_hash(song_key, normalized)
    now = datetime.now(timezone.utc)

    tone = db.scalar(
        select(SharedTone).where(
            SharedTone.song_key == song_key,
            SharedTone.payload_hash == digest,
        )
    )
    if tone is None:
        tone = SharedTone(
            song_key=song_key,
            payload_hash=digest,
            title=(title or "").strip()[:300],
            primary_key=primary_display,
            timeline=json.dumps(entries, ensure_ascii=False),
            source="admin",
            votes=0,
            reports=0,
        )
        db.add(tone)
        db.flush()
    else:
        tone.source = "admin"
        tone.primary_key = primary_display
        if title.strip():
            tone.title = title.strip()[:300]

    for sibling in db.scalars(select(SharedTone).where(SharedTone.song_key == song_key)).all():
        sibling.pinned = False
    tone.pinned = True
    tone.status = "ok"
    tone.last_seen = now
    db.commit()
    return _library_msg(song_key, f"Đã đặt tone {primary_display} cho {song_key}.")
```

Sửa `library_pin`, `library_hide`, `library_delete` để bơm `last_seen` của bản thắng mới:

```python
@router.post("/library/{tone_id}/pin")
def library_pin(tone_id: int, admin: str = Depends(current_admin), db: Session = Depends(get_db)):
    tone = db.get(SharedTone, tone_id)
    if tone:
        if not tone.pinned:
            # Mỗi bài chỉ một bản ghim — ghim hai bản là mâu thuẫn tự thân.
            for sibling in db.scalars(
                select(SharedTone).where(SharedTone.song_key == tone.song_key)
            ).all():
                sibling.pinned = False
            tone.pinned = True
        else:
            tone.pinned = False
        _touch_winner(db, tone.song_key)
        db.commit()
    return _redirect("/admin/library")


@router.post("/library/{tone_id}/hide")
def library_hide(tone_id: int, admin: str = Depends(current_admin), db: Session = Depends(get_db)):
    tone = db.get(SharedTone, tone_id)
    if tone:
        tone.status = "ok" if tone.status == "hidden" else "hidden"
        _touch_winner(db, tone.song_key)
        db.commit()
    return _redirect("/admin/library")


@router.post("/library/{tone_id}/delete")
def library_delete(tone_id: int, admin: str = Depends(current_admin), db: Session = Depends(get_db)):
    tone = db.get(SharedTone, tone_id)
    if tone:
        song_key = tone.song_key
        db.delete(tone)
        db.flush()
        _touch_winner(db, song_key)
        db.commit()
    return _redirect("/admin/library")
```

- [ ] **Step 4: Thêm form và thông báo vào template**

Trong `server/app/templates/library.html`, ngay sau thẻ `</form>` của ô tìm kiếm (trước `{% for song in groups %}`), thêm:

```html
{% if msg %}<div class="card" style="border-left:4px solid var(--accent, #3b82f6)">{{ msg }}</div>{% endif %}

<div class="card">
  <b>Đặt tone cho bài (theo mã video)</b>
  <div style="color:var(--muted);font-size:13px;margin:6px 0 10px">
    Dùng khi máy dò sai cả mạng lưới và chưa ai sửa tay. Bản này tự <b>ghim</b> và
    được phát tới mọi máy khách ở lần đồng bộ kế (không đè chuỗi tone khách đã sửa tay).
    Mốc thời gian: mỗi dòng <code>mm:ss Tone</code>, ví dụ <code>1:35 Bm</code>; bỏ trống = một tone cả bài.
  </div>
  <form method="post" action="/admin/library/set" class="row" style="gap:8px;flex-wrap:wrap;align-items:flex-start">
    <input type="text" name="song_key" placeholder="Mã video (11 ký tự)" value="{{ q if q|length == 11 else '' }}" required style="width:170px">
    <input type="text" name="title" placeholder="Tên bài (tuỳ chọn)" style="min-width:220px">
    <input type="text" name="primary_key" placeholder="Tone chính, vd F#m" required style="width:140px">
    <textarea name="timeline" placeholder="0:00 F#m&#10;1:35 Bm" rows="2" style="min-width:200px"></textarea>
    <button>Đặt tone</button>
  </form>
</div>
```

Trong bảng biến thể, cột Nguồn hiện `'người sửa' if v.source == 'human' else 'máy dò'` — thay bằng:

```html
      <td>{{ {'human': 'người sửa', 'admin': 'admin đặt'}.get(v.source, 'máy dò') }}</td>
```

Trong mỗi nhóm bài, thêm form đặt nhanh **ngay dưới bảng** (trước `</div>` đóng card của bài):

```html
  <form method="post" action="/admin/library/set" class="row" style="margin-top:8px;gap:8px">
    <input type="hidden" name="song_key" value="{{ song.song_key }}">
    <input type="hidden" name="title" value="{{ song.title }}">
    <input type="text" name="primary_key" placeholder="Đặt tone, vd F#m" required style="width:140px">
    <input type="text" name="timeline" placeholder="mốc (tuỳ chọn): 1:35 Bm" style="min-width:200px">
    <button class="ghost">Đặt tone cho bài này</button>
  </form>
```

- [ ] **Step 5: Chạy test, xác nhận xanh**

Run: `cd server && python -m pytest tests -q`
Expected: tất cả PASS. Nếu `test_ghim_ban_khac...` so `last_seen` lỗi vì SQLite trả naive datetime, test đã `.replace(tzinfo=timezone.utc)` — không sửa code sản phẩm vì SQLite không giữ tz.

- [ ] **Step 6: Commit**

```bash
git add server/app/routers/admin.py server/app/templates/library.html server/tests/test_admin_library_set.py
git commit -m "feat(server): admin đặt tone trên /admin/library, tự ghim + bơm last_seen bản thắng"
```

---

### Task 3: Endpoint `POST /api/v1/library/changes` — feed bản ghim theo cursor keyset

**Files:**
- Modify: `server/app/schemas.py` (sau `LibraryLookupResponse`)
- Modify: `server/app/routers/library.py` (route mới + hằng trang)
- Test: `server/tests/test_library_changes.py` (mới)

**Interfaces:**
- Consumes: `tonelib.encode_cursor`, `tonelib.decode_cursor` (Task 1); `last_seen` được bơm bởi Task 2
- Produces: request `LibraryChangesRequest {token, code, device_fingerprint, cursor: str = ""}`; response `LibraryChangesResponse {ok, items: list[ToneChange], next_cursor: str, has_more: bool, message}`; `ToneChange` = `ToneResult` + `pinned: bool`. Hằng `library.CHANGES_PAGE_SIZE = 500`.

- [ ] **Step 1: Viết test đỏ**

Tạo `server/tests/test_library_changes.py`:

```python
"""Feed bản ghim cho máy khách: cursor keyset (last_seen, id), không sót, không lặp."""
from datetime import datetime, timezone

import pytest

from app.db import SessionLocal
from app.models import License, SharedTone
from app.routers import library as library_router
from app.services import codegen


def _token(client, fp):
    code = codegen.generate_code()
    with SessionLocal() as db:
        db.add(License(code=code, max_devices=1, status="unused", plan="standard"))
        db.commit()
    return client.post("/api/v1/activate", json={"code": code, "device_fingerprint": fp}).json()["token"]


def _set(admin_client, song, key):
    return admin_client.post("/admin/library/set", data={
        "song_key": song, "title": "", "primary_key": key, "timeline": "",
    }, follow_redirects=False)


def _contribute(client, token, fp, song, key):
    return client.post("/api/v1/library/contribute", json={
        "token": token, "device_fingerprint": fp,
        "items": [{"song_key": song, "title": "t", "primary_key": key, "source": "auto",
                   "timeline": [{"time": 0, "key_display": key, "key_index": 0, "scale": "Major"}]}],
    })


def _changes(client, token, fp, cursor=""):
    res = client.post("/api/v1/library/changes", json={
        "token": token, "device_fingerprint": fp, "cursor": cursor,
    })
    assert res.status_code == 200, res.text
    return res.json()


def _song(n):
    return f"SONG{n:07d}"  # 11 ký tự


def test_cursor_rong_tra_ban_ghim_khong_tra_ban_thang_do_phieu(admin_client):
    fp = "may-feed-01"
    token = _token(admin_client, fp)
    _contribute(admin_client, token, fp, _song(1), "C")   # thắng do phiếu, không ghim
    _set(admin_client, _song(2), "F#m")                    # admin đặt → ghim

    body = _changes(admin_client, token, fp)
    assert body["ok"] is True
    assert [it["song_key"] for it in body["items"]] == [_song(2)]
    assert body["items"][0]["pinned"] is True
    assert body["items"][0]["source"] == "admin"
    assert body["items"][0]["timeline"][0]["key_display"] == "F#m"
    assert body["has_more"] is False
    assert body["next_cursor"]


def test_gui_lai_next_cursor_thi_rong_va_cursor_giu_nguyen(admin_client):
    fp = "may-feed-02"
    token = _token(admin_client, fp)
    _set(admin_client, _song(1), "Am")
    first = _changes(admin_client, token, fp)

    again = _changes(admin_client, token, fp, cursor=first["next_cursor"])
    assert again["items"] == []
    assert again["next_cursor"] == first["next_cursor"]
    assert again["has_more"] is False


def test_ban_moi_sau_cursor_xuat_hien(admin_client):
    fp = "may-feed-03"
    token = _token(admin_client, fp)
    _set(admin_client, _song(1), "Am")
    cur = _changes(admin_client, token, fp)["next_cursor"]

    _set(admin_client, _song(2), "Dm")
    body = _changes(admin_client, token, fp, cursor=cur)
    assert [it["song_key"] for it in body["items"]] == [_song(2)]


def test_cung_last_seen_vat_qua_ranh_gioi_trang_khong_sot_khong_lap(admin_client, monkeypatch):
    monkeypatch.setattr(library_router, "CHANGES_PAGE_SIZE", 2)
    fp = "may-feed-04"
    token = _token(admin_client, fp)
    for n in range(1, 6):
        _set(admin_client, _song(n), "Am")
    cung_gio = datetime(2026, 10, 3, 12, 0, 0, 500000)
    with SessionLocal() as db:
        for v in db.query(SharedTone).all():
            v.last_seen = cung_gio
        db.commit()

    seen, cursor, pages = [], "", 0
    while True:
        body = _changes(admin_client, token, fp, cursor=cursor)
        seen += [it["song_key"] for it in body["items"]]
        cursor = body["next_cursor"]
        pages += 1
        if not body["has_more"]:
            break
        assert pages < 10

    assert seen == [_song(n) for n in range(1, 6)]
    assert pages == 3  # 2 + 2 + 1


def test_has_more_dung_khi_vua_du_mot_trang(admin_client, monkeypatch):
    monkeypatch.setattr(library_router, "CHANGES_PAGE_SIZE", 2)
    fp = "may-feed-05"
    token = _token(admin_client, fp)
    _set(admin_client, _song(1), "Am")
    _set(admin_client, _song(2), "Am")

    body = _changes(admin_client, token, fp)
    assert len(body["items"]) == 2
    assert body["has_more"] is False, "đúng 2 bản, trang 2 → không còn gì, không được đoán theo == page size"


def test_cursor_hong_coi_nhu_rong(admin_client):
    fp = "may-feed-06"
    token = _token(admin_client, fp)
    _set(admin_client, _song(1), "Am")

    body = _changes(admin_client, token, fp, cursor="không-phải-cursor")
    assert body["ok"] is True
    assert [it["song_key"] for it in body["items"]] == [_song(1)]


def test_ban_ghim_bi_an_khong_vao_feed(admin_client):
    fp = "may-feed-07"
    token = _token(admin_client, fp)
    _set(admin_client, _song(1), "Am")
    with SessionLocal() as db:
        tone_id = db.query(SharedTone).one().id
    admin_client.post(f"/admin/library/{tone_id}/hide")

    assert _changes(admin_client, token, fp)["items"] == []


def test_feed_can_may_da_kich_hoat(client):
    res = client.post("/api/v1/library/changes", json={
        "token": "tok-gia", "device_fingerprint": "may-la-xx", "cursor": "",
    })
    assert res.status_code in (401, 403)
    assert res.json()["ok"] is False
```

- [ ] **Step 2: Chạy test, xác nhận đỏ**

Run: `cd server && python -m pytest tests/test_library_changes.py -q`
Expected: FAIL — 404 ở `/api/v1/library/changes` (assert `status_code == 200` đỏ), `AttributeError: CHANGES_PAGE_SIZE`.

- [ ] **Step 3: Thêm schema**

Trong `server/app/schemas.py`, sau `class LibraryLookupResponse`:

```python
class ToneChange(ToneResult):
    """Một bản ghim trong feed /library/changes."""
    pinned: bool = True


class LibraryChangesRequest(BaseModel):
    token:              str | None = None
    code:               str | None = None
    device_fingerprint: str = Field(min_length=8, max_length=128)
    # Cursor opaque do server phát (tonelib.encode_cursor). Rỗng = lấy từ đầu.
    cursor:             str = Field(default="", max_length=400)


class LibraryChangesResponse(BaseModel):
    ok:          bool = True
    items:       list[ToneChange] = []
    next_cursor: str = ""
    has_more:    bool = False
    message:     str = ""
```

- [ ] **Step 4: Thêm route**

Trong `server/app/routers/library.py`: thêm `from sqlalchemy import and_, or_, select` (thay dòng `from sqlalchemy import select`), thêm vào import schemas `LibraryChangesRequest, LibraryChangesResponse, ToneChange`, và sau `router = APIRouter(...)`:

```python
# Trang feed /changes. Server hỏi +1 để biết chắc còn hay hết, không đoán theo
# "== page size". Test giảm xuống 2 bằng monkeypatch để ép ranh giới trang.
CHANGES_PAGE_SIZE = 500
```

Thêm helper cạnh `_to_result`:

```python
def _to_change(tone: SharedTone) -> ToneChange:
    base = _to_result(tone)
    return ToneChange(**base.model_dump(), pinned=bool(tone.pinned))
```

Thêm route sau `lookup`:

```python
@router.post("/changes", response_model=LibraryChangesResponse)
@limiter.limit(settings.rate_limit_library)
def changes(request: Request, payload: LibraryChangesRequest, db: Session = Depends(get_db)):
    """Bản GHIM thay đổi từ cursor trở đi — kênh để bản admin đặt tới máy khách.

    Chỉ phát bản ghim (admin đặt, hoặc admin ghim bản người sửa): bản thắng do
    phiếu là dữ liệu máy khách, không có người chịu trách nhiệm, không được đè
    cache của máy khác.

    Phân trang keyset theo (last_seen, id), KHÔNG theo mốc giờ: `since =
    server_time` sót bản commit sau lúc truy vấn mà last_seen nhỏ hơn; `since =
    last_seen bản cuối` cắt mất các bản cùng last_seen ở ranh giới trang.
    Cursor hỏng → coi như rỗng: client ghi đè idempotent nên lấy lại từ đầu vô hại.

    Lưu ý cho ai sửa /contribute sau này: nếu contribute bơm last_seen của bản
    ghim, bản đó xuất hiện lại trong feed — vô hại nhưng tốn băng thông.
    """
    _code, message, status = _authorize(payload, db)
    if message is not None:
        return _error(LibraryChangesResponse, message, status)

    query = select(SharedTone).where(
        SharedTone.pinned.is_(True),
        SharedTone.status == "ok",
    )
    cursor = tonelib.decode_cursor(payload.cursor)
    if cursor is not None:
        ts, last_id = cursor
        query = query.where(
            or_(
                SharedTone.last_seen > ts,
                and_(SharedTone.last_seen == ts, SharedTone.id > last_id),
            )
        )

    rows = db.scalars(
        query.order_by(SharedTone.last_seen.asc(), SharedTone.id.asc())
        .limit(CHANGES_PAGE_SIZE + 1)
    ).all()
    has_more = len(rows) > CHANGES_PAGE_SIZE
    rows = rows[:CHANGES_PAGE_SIZE]

    if rows:
        next_cursor = tonelib.encode_cursor(rows[-1].last_seen, rows[-1].id)
    else:
        next_cursor = payload.cursor if cursor is not None else ""

    return LibraryChangesResponse(
        ok=True,
        items=[_to_change(t) for t in rows],
        next_cursor=next_cursor,
        has_more=has_more,
    )
```

- [ ] **Step 5: Chạy test, xác nhận xanh**

Run: `cd server && python -m pytest tests -q`
Expected: tất cả PASS. Nếu `test_cung_last_seen...` đỏ ở vế `==` do SQLite lưu `last_seen` thiếu micro giây khi gán từ Python, kiểm `tonelib.encode_cursor` dùng `isoformat()` của giá trị **đọc lại từ DB** (đúng như code trên — `rows[-1].last_seen`), không dùng giá trị trước khi ghi.

- [ ] **Step 6: Commit**

```bash
git add server/app/schemas.py server/app/routers/library.py server/tests/test_library_changes.py
git commit -m "feat(server): POST /api/v1/library/changes — feed bản ghim theo cursor keyset (last_seen, id)"
```

---

### Task 4: Client `tone_share.pull_overrides()` — kéo feed, ghi tone_cache `origin="admin"`, giữ cursor

**Files:**
- Modify: `core/tone_share.py`
- Test: `tests/core/test_tone_share.py`

**Interfaces:**
- Consumes: response của Task 3 (`items`, `next_cursor`, `has_more`); `ToneCacheManager.save_tone` (qua `_save_local`), `ManualToneTimeline.get_timeline_source`, `SongManager.find_song_by_url` / `update_song`
- Produces:
  - `tone_share.pull_overrides() -> dict` với khoá `fetched`, `applied`, `skipped_human`, `pages`, `ok` (False khi dừng vì mạng/lỗi server)
  - `tone_share.CHANGES_MAX_PAGES = 20`
  - `tone_share._overrides_state_path() -> str`, `_load_cursor() -> str`, `_save_cursor(str)`
  - `tone_share._apply_override(item: dict) -> str` trả `"applied" | "skipped_human" | "ignored"`
  - `tone_share._update_saved_song_tone(url: str, primary_key: str) -> None`

- [ ] **Step 1: Viết test đỏ**

Thêm vào cuối `tests/core/test_tone_share.py`:

```python
# ── Bản admin đặt: pull_overrides ──
ADMIN_KEY = "pMPvJE1wwnc"
ADMIN_URL = f"https://www.youtube.com/watch?v={ADMIN_KEY}"


def _change(key=ADMIN_KEY, primary="F#m"):
    return {
        "song_key": key, "title": "Lưng Cha Bụng Mẹ", "primary_key": primary,
        "source": "admin", "pinned": True, "votes": 0, "payload_hash": f"hash-{key}",
        "timeline": [{"time": 0, "key_display": primary, "key_index": 6, "scale": "Minor"}],
    }


@pytest.fixture
def overrides_env(tmp_path, monkeypatch):
    """Cô lập file cursor + ghi cache + thiết lập bài; trả dict ghi lại các lần ghi."""
    saved, songs = [], []
    monkeypatch.setattr(tone_share, "_overrides_state_path",
                        lambda: str(tmp_path / "tone_overrides_state.json"))
    monkeypatch.setattr(tone_share, "_save_local", lambda url, entry: saved.append((url, entry)))
    monkeypatch.setattr(tone_share, "_update_saved_song_tone",
                        lambda url, primary: songs.append((url, primary)))
    monkeypatch.setattr("core.tone_cache.ManualToneTimeline.get_timeline_source",
                        staticmethod(lambda url: None))
    return {"saved": saved, "songs": songs}


def _paged_post(pages, calls):
    """pages: {cursor_nhận: (status, body)}. Ghi lại cursor từng lần gọi."""
    def _post(path, payload):
        assert path == "/api/v1/library/changes"
        calls.append(payload.get("cursor", ""))
        return pages[payload.get("cursor", "")]
    return _post


def test_pull_overrides_ghi_cache_origin_admin_va_luu_cursor(monkeypatch, overrides_env):
    calls = []
    monkeypatch.setattr(tone_share, "_post", _paged_post({
        "": (200, {"ok": True, "items": [_change()], "next_cursor": "CUR-1", "has_more": False}),
    }, calls))

    stats = tone_share.pull_overrides()

    assert stats["ok"] is True
    assert stats["applied"] == 1 and stats["fetched"] == 1
    (url, entry), = overrides_env["saved"]
    assert url == ADMIN_URL
    assert entry["origin"] == "admin"
    assert entry["primary_key"] == "F#m"
    assert entry["key_timeline"][0]["key_display"] == "F#m"
    assert entry["payload_hash"] == f"hash-{ADMIN_KEY}"
    assert overrides_env["songs"] == [(ADMIN_URL, "F#m")]
    assert tone_share._load_cursor() == "CUR-1"
    assert calls == [""]


def test_pull_overrides_lan_sau_gui_cursor_da_luu(monkeypatch, overrides_env):
    tone_share._save_cursor("CUR-1")
    calls = []
    monkeypatch.setattr(tone_share, "_post", _paged_post({
        "CUR-1": (200, {"ok": True, "items": [], "next_cursor": "CUR-1", "has_more": False}),
    }, calls))

    stats = tone_share.pull_overrides()
    assert calls == ["CUR-1"]
    assert stats["applied"] == 0
    assert tone_share._load_cursor() == "CUR-1"


def test_pull_overrides_khong_de_chuoi_tone_khach_sua_tay(monkeypatch, overrides_env):
    monkeypatch.setattr("core.tone_cache.ManualToneTimeline.get_timeline_source",
                        staticmethod(lambda url: "human"))
    monkeypatch.setattr(tone_share, "_post", _paged_post({
        "": (200, {"ok": True, "items": [_change()], "next_cursor": "CUR-1", "has_more": False}),
    }, []))

    stats = tone_share.pull_overrides()

    assert stats["skipped_human"] == 1 and stats["applied"] == 0
    assert overrides_env["saved"] == []
    assert overrides_env["songs"] == []
    assert tone_share._load_cursor() == "CUR-1", "bỏ qua là quyết định cuối, không lấy lại bản đó"


def test_pull_overrides_lap_trang_khi_has_more(monkeypatch, overrides_env):
    calls = []
    monkeypatch.setattr(tone_share, "_post", _paged_post({
        "": (200, {"ok": True, "items": [_change("AAAAAAAAAAA")], "next_cursor": "CUR-1", "has_more": True}),
        "CUR-1": (200, {"ok": True, "items": [_change("BBBBBBBBBBB")], "next_cursor": "CUR-2", "has_more": False}),
    }, calls))

    stats = tone_share.pull_overrides()

    assert calls == ["", "CUR-1"]
    assert stats["applied"] == 2 and stats["pages"] == 2
    assert tone_share._load_cursor() == "CUR-2"


def test_pull_overrides_mat_mang_o_trang_hai_giu_cursor_trang_mot(monkeypatch, overrides_env):
    monkeypatch.setattr(tone_share, "_post", _paged_post({
        "": (200, {"ok": True, "items": [_change("AAAAAAAAAAA")], "next_cursor": "CUR-1", "has_more": True}),
        "CUR-1": (0, {}),
    }, []))

    stats = tone_share.pull_overrides()

    assert stats["ok"] is False
    assert stats["applied"] == 1
    assert tone_share._load_cursor() == "CUR-1", "trang 1 đã áp xong thì giữ; trang 2 lấy lại lần sau"


def test_pull_overrides_server_tu_choi_khong_doi_cursor(monkeypatch, overrides_env):
    tone_share._save_cursor("CUR-0")
    monkeypatch.setattr(tone_share, "_post", _paged_post({
        "CUR-0": (403, {"ok": False, "message": "hết hạn"}),
    }, []))

    stats = tone_share.pull_overrides()
    assert stats["ok"] is False
    assert tone_share._load_cursor() == "CUR-0"


def test_pull_overrides_dung_o_tran_trang(monkeypatch, overrides_env):
    monkeypatch.setattr(tone_share, "CHANGES_MAX_PAGES", 3)
    calls = []
    monkeypatch.setattr(tone_share, "_post", lambda path, payload: (
        calls.append(payload["cursor"]) or (200, {
            "ok": True, "items": [_change()], "next_cursor": f"CUR-{len(calls)}", "has_more": True,
        })))

    stats = tone_share.pull_overrides()
    assert stats["pages"] == 3 and len(calls) == 3
    assert tone_share._load_cursor() == "CUR-3"


def test_pull_overrides_bo_qua_item_hong(monkeypatch, overrides_env):
    hong = {"song_key": "ngan", "timeline": []}
    monkeypatch.setattr(tone_share, "_post", _paged_post({
        "": (200, {"ok": True, "items": [hong, _change()], "next_cursor": "CUR-1", "has_more": False}),
    }, []))

    stats = tone_share.pull_overrides()
    assert stats["applied"] == 1 and stats["fetched"] == 2
    assert len(overrides_env["saved"]) == 1


def test_pull_overrides_tat_trong_thiet_lap_thi_khong_goi_mang(monkeypatch, overrides_env):
    monkeypatch.setattr(
        "core.config.ConfigManager.load_settings",
        staticmethod(lambda: {"tone_share": {"enabled": False}}),
    )
    called = []
    monkeypatch.setattr(tone_share, "_post", _fake_post(200, {}, called))

    stats = tone_share.pull_overrides()
    assert stats == {"ok": False, "skipped": "disabled", "fetched": 0, "applied": 0,
                     "skipped_human": 0, "pages": 0}
    assert not called


def test_pull_overrides_xoa_dem_phien_cua_bai_vua_nhan(monkeypatch, overrides_env):
    tone_share._remember_miss(ADMIN_KEY)
    monkeypatch.setattr(tone_share, "_post", _paged_post({
        "": (200, {"ok": True, "items": [_change()], "next_cursor": "CUR-1", "has_more": False}),
    }, []))

    tone_share.pull_overrides()
    assert tone_share._recently_missed(ADMIN_KEY) is False
    with tone_share._cache_lock:
        assert tone_share._hit_cache[ADMIN_KEY]["origin"] == "admin"
```

- [ ] **Step 2: Chạy test, xác nhận đỏ**

Run: `python -m pytest tests/core/test_tone_share.py -q -k overrides`
Expected: FAIL — `AttributeError: module 'core.tone_share' has no attribute '_overrides_state_path'` ở fixture.

- [ ] **Step 3: Hiện thực trong `core/tone_share.py`**

Thêm vào khối hằng số (sau `CONTRIBUTE_BATCH = 50`):

```python
# Feed bản admin đặt (/api/v1/library/changes): tối đa bấy nhiêu trang một lượt
# để vòng bảo trì không kẹt vô hạn nếu server lỗi trả mãi has_more.
CHANGES_MAX_PAGES = 20
_overrides_lock = threading.Lock()
```

Thêm phần mới trước `# ── Hàng đợi (chịu được mất mạng) ──`:

```python
# ── Bản admin đặt trên server → tone_cache local ──
def _overrides_state_path():
    from core.config import _get_data_dir
    import os
    return os.path.join(_get_data_dir(), "tone_overrides_state.json")


def _load_cursor() -> str:
    try:
        with open(_overrides_state_path(), encoding="utf-8") as f:
            data = json.load(f)
        return str(data.get("cursor", "")) if isinstance(data, dict) else ""
    except Exception:
        return ""


def _save_cursor(cursor: str) -> None:
    try:
        path = _overrides_state_path()
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"cursor": str(cursor or "")}, f)
        import os
        os.replace(tmp, path)
    except Exception as e:
        log.debug("Không lưu được cursor thư viện tone: %s", e)


def _update_saved_song_tone(url, primary_key) -> None:
    """Cột tone ở Danh sách bài hát (saved_songs.json) — chỉ để hiển thị khớp."""
    try:
        from core.songs import SongManager
        song = SongManager.find_song_by_url(url)
        if song and song.get("id") is not None and primary_key:
            SongManager.update_song(song["id"], tone=primary_key)
    except Exception as e:
        log.debug("Không cập nhật tone bài đã lưu: %s", e)


def _apply_override(item) -> str:
    """Một bản admin đặt → tone_cache. Trả 'applied' | 'skipped_human' | 'ignored'.

    Không đè chuỗi tone khách đã sửa tay (quyết định sản phẩm 2026-10-03):
    admin đè máy dò và cộng đồng, còn tone khách tự chỉnh là của khách.
    """
    if not isinstance(item, dict):
        return "ignored"
    key = str(item.get("song_key") or "")
    if len(key) != 11 or not item.get("timeline"):
        return "ignored"
    url = f"https://www.youtube.com/watch?v={key}"

    from core.tone_cache import ManualToneTimeline
    if ManualToneTimeline.get_timeline_source(url) == "human":
        return "skipped_human"

    entry = _to_cache_entry(item)
    entry["origin"] = "admin"
    _save_local(url, entry)
    _remember_hit(key, entry)
    _update_saved_song_tone(url, entry.get("primary_key", ""))
    return "applied"


def pull_overrides() -> dict:
    """Kéo bản admin đặt từ cursor đã lưu, ghi vào tone_cache. Gọi từ luồng NỀN.

    Áp hết một trang rồi mới lưu next_cursor: lưu trước mà app tắt giữa chừng
    là mất trang đó. Mất mạng/server từ chối → dừng, giữ cursor của trang cuối
    đã áp xong; áp lại một trang là idempotent.
    """
    stats = {"ok": False, "fetched": 0, "applied": 0, "skipped_human": 0, "pages": 0}
    if not enabled():
        return dict(stats, skipped="disabled")
    auth = _auth_fields()
    if auth is None:
        return dict(stats, skipped="not_activated")
    if not _overrides_lock.acquire(blocking=False):
        return dict(stats, skipped="busy")
    try:
        cursor = _load_cursor()
        while stats["pages"] < CHANGES_MAX_PAGES:
            status, body = _post("/api/v1/library/changes", dict(auth, cursor=cursor))
            if status != 200 or not body.get("ok"):
                if status != 0:
                    log.info("Feed thư viện tone thất bại (%s): %s", status, body.get("message", ""))
                return stats
            stats["pages"] += 1
            for item in body.get("items") or []:
                stats["fetched"] += 1
                outcome = _apply_override(item)
                if outcome == "applied":
                    stats["applied"] += 1
                elif outcome == "skipped_human":
                    stats["skipped_human"] += 1
            next_cursor = str(body.get("next_cursor") or cursor)
            if next_cursor != cursor:
                _save_cursor(next_cursor)
                cursor = next_cursor
            if not body.get("has_more"):
                break
        stats["ok"] = True
        return stats
    finally:
        _overrides_lock.release()
```

- [ ] **Step 4: Chạy test, xác nhận xanh**

Run: `python -m pytest tests/core/test_tone_share.py -q`
Expected: tất cả PASS (test cũ + 10 test mới).

- [ ] **Step 5: Commit**

```bash
git add core/tone_share.py tests/core/test_tone_share.py
git commit -m "feat(tone-share): pull_overrides — kéo bản admin đặt theo cursor, ghi tone_cache origin=admin"
```

---

### Task 5: Nối vào vòng bảo trì nền, nút "☁ Đồng bộ tone" và "Đồng bộ ngay"

**Files:**
- Modify: `main.py:363-369` (vòng `_background_maintenance`)
- Modify: `core/tone_share.py` (thêm `sync_songs`)
- Modify: `ui/dialogs/songs_list.py:139-186`
- Modify: `ui/dialogs/settings_dialog.py:786-805` (`_on_tone_share_sync`)
- Test: `tests/core/test_tone_share.py`, `tests/core/test_tone_resolve_saved.py`

**Interfaces:**
- Consumes: `tone_share.pull_overrides()`, `tone_share.lookup_many(urls)` (Task 4 và sẵn có)
- Produces: `tone_share.sync_songs(urls) -> tuple[dict, dict]` = `(found_by_url, override_stats)`; `SongsListDialog._on_sync_done(found, pending, stats)`

- [ ] **Step 1: Viết test đỏ cho `sync_songs` và cho thứ tự resolve**

Thêm vào `tests/core/test_tone_share.py`:

```python
def test_sync_songs_keo_ban_admin_truoc_roi_tra_cuu_bai_thieu(monkeypatch, overrides_env):
    order = []

    def _post(path, payload):
        order.append(path)
        if path == "/api/v1/library/changes":
            return 200, {"ok": True, "items": [_change()], "next_cursor": "CUR-1", "has_more": False}
        return 200, {"ok": True, "results": {KEY: _result("Am")}}
    monkeypatch.setattr(tone_share, "_post", _post)

    found, stats = tone_share.sync_songs([URL])

    assert order == ["/api/v1/library/changes", "/api/v1/library/lookup"]
    assert found[URL]["primary_key"] == "Am"
    assert stats["applied"] == 1
```

Thêm vào `tests/core/test_tone_resolve_saved.py` (cuối file, dùng fixture `isolated_data` và `engine` sẵn có trong file):

```python
def test_cache_admin_thang_tone_bai_da_luu_nhung_thua_chuoi_thu_cong(isolated_data, engine):
    """R-15: bản admin đặt nằm ở nấc tone_cache → đè tone bài đã lưu, không đè sửa tay."""
    _write_songs(isolated_data["songs"], [{"id": 1, "url": WATCH_URL, "tone": "Bm", "title": "A"}])
    ToneCacheManager.save_tone(WATCH_URL, {
        "primary_key": "F#m", "origin": "admin",
        "key_timeline": [make_timeline_entry("F#m")],
    })

    source, data = engine._resolve_tone(WATCH_URL)
    assert source == "cache"
    assert data["primary_key"] == "F#m"

    ManualToneTimeline.save_timeline(WATCH_URL, "A", [make_timeline_entry("Am")], source="human")
    source, data = engine._resolve_tone(WATCH_URL)
    assert source == "manual"
    assert data["timeline"][0]["key_display"] == "Am"
```

- [ ] **Step 2: Chạy test, xác nhận đỏ**

Run: `python -m pytest tests/core/test_tone_share.py::test_sync_songs_keo_ban_admin_truoc_roi_tra_cuu_bai_thieu tests/core/test_tone_resolve_saved.py -q`
Expected: `sync_songs` FAIL với `AttributeError`; test resolve PASS ngay (ghim hành vi sẵn có — giữ lại làm hàng rào, ghi chú trong docstring đã nói rõ).

- [ ] **Step 3: Thêm `sync_songs` vào `core/tone_share.py`**

Sau `pull_overrides`:

```python
def sync_songs(urls) -> tuple:
    """Nút "☁ Đồng bộ tone": kéo bản admin đặt TRƯỚC, rồi tra cộng đồng cho các
    bài còn thiếu. Trả (found_by_url, override_stats). Gọi từ luồng nền."""
    stats = pull_overrides()
    found = lookup_many(urls)
    return found, stats
```

- [ ] **Step 4: Nối vào vòng bảo trì nền (`main.py`)**

Thay khối:

```python
        # Thư viện tone cộng đồng: đẩy nốt các đóng góp còn kẹt vì mất mạng.
        try:
            from core import tone_share
            tone_share.flush_queue()
        except Exception as e:
            log.debug("tone share flush skipped: %s", e)
```
bằng
```python
        # Thư viện tone cộng đồng: đẩy nốt các đóng góp còn kẹt vì mất mạng, rồi
        # kéo bản admin đặt trên server (đè máy dò/cộng đồng trong cache, không
        # đè chuỗi tone khách sửa tay). Chạy ngay vòng đầu lúc khởi động.
        try:
            from core import tone_share
            tone_share.flush_queue()
            res = tone_share.pull_overrides()
            if res.get("applied"):
                log.info("Nhận %d tone admin đặt (bỏ qua %d bài khách sửa tay)",
                         res["applied"], res.get("skipped_human", 0))
        except Exception as e:
            log.debug("tone share sync skipped: %s", e)
```

- [ ] **Step 5: Nút "☁ Đồng bộ tone" (`ui/dialogs/songs_list.py`)**

Trong `_start_sync_worker`, thay:

```python
            def run(self):
                try:
                    from core import tone_share
                    self.done.emit(tone_share.lookup_many(urls))
                except Exception as e:
                    print(f"[SYNC-TONE] lỗi: {e}")
                    self.done.emit({})
```
bằng
```python
            def run(self):
                try:
                    from core import tone_share
                    self.done.emit(tone_share.sync_songs(urls))
                except Exception as e:
                    print(f"[SYNC-TONE] lỗi: {e}")
                    self.done.emit(({}, {}))
```
và
```python
        worker.done.connect(lambda found: self._on_sync_done(found, pending))
```
bằng
```python
        worker.done.connect(lambda result: self._on_sync_done(result[0], pending, result[1]))
```

Sửa chữ ký và thông báo của `_on_sync_done`:

```python
    def _on_sync_done(self, found, pending, stats=None):
        import backend

        self._sync_btn.setEnabled(True)
        self._sync_btn.setText("☁ Đồng bộ tone")
        stats = stats or {}
        admin_applied = int(stats.get("applied") or 0)
```
và thay khối thông báo cuối hàm:
```python
        if applied or admin_applied:
            self._refresh_data()
            self._rebuild_list()
            parts = []
            if applied:
                parts.append(f"lấy tone cho {applied}/{len(pending)} bài")
            if admin_applied:
                parts.append(f"nhận {admin_applied} tone do quản trị đặt")
            self._dashboard._show_message("Đã " + ", ".join(parts))
        else:
            self._dashboard._show_message(
                f"Chưa ai trong mạng lưới dò {len(pending)} bài này"
            )
```

Trong `_on_sync_tones`, **xoá** khối ba dòng sau (pending rỗng vẫn phải chạy
worker, vì bản admin đặt có thể đè tone máy dò đang có):

```python
        if not pending:
            self._dashboard._show_message("Mọi bài trong danh sách đều đã có tone.")
            return
```

Ba dòng `setEnabled(False)` / `setText("Đang lấy…")` / `_start_sync_worker(pending)`
ngay dưới giữ nguyên. Trong `_on_sync_done`, nhánh `else` cuối hàm đổi thành:

```python
        else:
            self._dashboard._show_message(
                "Không có tone mới." if not pending
                else f"Chưa ai trong mạng lưới dò {len(pending)} bài này"
            )
```

- [ ] **Step 6: "Đồng bộ ngay" mục Thư viện tone (`ui/dialogs/settings_dialog.py`)**

Thay thân `_on_tone_share_sync`:

```python
    def _on_tone_share_sync(self):
        """Đẩy nốt phần còn kẹt trong hàng đợi, quên các lần tra hụt, và kéo bản
        admin đặt trên server. Phần đi mạng chạy nền."""
        try:
            from core import tone_share
            if not tone_share.enabled():
                self._tone_share_status.setText(
                    "Đang tắt hoặc máy chưa kích hoạt — chưa đồng bộ được."
                )
                return
            tone_share.clear_session_cache()
            tone_share.flush_queue()
            import threading
            threading.Thread(target=tone_share.pull_overrides, daemon=True).start()
            self._tone_share_status.setText(
                "Đang gửi phần đóng góp còn tồn và nhận tone quản trị đặt. Mở Danh "
                "sách bài hát rồi bấm “☁ Đồng bộ tone” để lấy tone cho cả danh sách."
            )
        except Exception as e:
            self._tone_share_status.setText(f"Không đồng bộ được: {e}")
```

- [ ] **Step 7: Chạy test**

Run (Linux hoặc Windows): `python -m pytest tests/core -q`
Run (Windows, UI): `.venv\Scripts\python.exe -m pytest tests\ui -q -p no:cacheprovider`
Expected: tất cả PASS. `tests/ui/test_open_song_tone.py` và `tests/ui/test_dialogs.py` không gọi `_on_sync_done` nên không cần đổi.

- [ ] **Step 8: Commit**

```bash
git add main.py core/tone_share.py ui/dialogs/songs_list.py ui/dialogs/settings_dialog.py tests/core/test_tone_share.py tests/core/test_tone_resolve_saved.py
git commit -m "feat(tone-share): nhận tone admin đặt ở vòng nền, nút Đồng bộ tone và Đồng bộ ngay"
```

---

### Task 6: Tài liệu

**Files:**
- Modify: `docs/TONE_FLOWS.md` (đầu file, sau khối ⚠ 1.7.5)
- Modify: `docs/SERVER_ARCHITECTURE.md` (mục thư viện tone, tìm bằng `grep -n "library" docs/SERVER_ARCHITECTURE.md`)
- Modify: `docs/NGHIEN_CUU_DO_TONE.md` (mục 2026-10-03, cuối)

- [ ] **Step 1: TONE_FLOWS.md**

Thêm ngay sau khối ⚠ 1.7.5:

```markdown
> **⚠ Cập nhật 2026-10-03 — tone admin đặt trên server:** `core/tone_share.py::pull_overrides`
> kéo feed `POST /api/v1/library/changes` (chỉ bản **ghim**, cursor keyset
> `(last_seen, id)`) và ghi vào `ToneCache` với `origin="admin"`. Nấc resolve
> **không đổi**: entry này nằm ở `tone_cache` nên **đè** tone bài đã lưu và cộng
> đồng, nhưng **thua** chuỗi tone thủ công (`source="human"`), và
> `pull_overrides` bỏ qua hẳn bài có chuỗi thủ công. Gọi từ vòng bảo trì nền
> (6 giờ, chạy cả lúc khởi động), nút "☁ Đồng bộ tone" (`sync_songs`) và
> "Đồng bộ ngay" mục Thư viện tone. Cursor lưu ở `DATA_DIR/tone_overrides_state.json`.
> Spec: `docs/superpowers/specs/2026-10-03-admin-tone-override-design.md`.
```

- [ ] **Step 2: SERVER_ARCHITECTURE.md**

Trong mục thư viện tone, thêm đoạn:

```markdown
**Admin đặt tone (2026-10-03).** `POST /admin/library/set` tạo biến thể
`source="admin"` (trọng số 10), tự ghim, bỏ ghim anh em, `last_seen = now`.
`pin`/`hide`/`delete` cũng bơm `last_seen` cho bản thắng mới (`_touch_winner`).
`POST /api/v1/library/changes` phát bản ghim từ cursor opaque
(`tonelib.encode_cursor` = base64url của `{"ts": last_seen ISO, "id"}`), trang
500 (+1 để biết `has_more`), sắp `last_seen, id`. Client gửi `source="admin"`
qua `/contribute` bị ép về `auto` (`tonelib.CLIENT_SOURCES`).
```

- [ ] **Step 3: NGHIEN_CUU_DO_TONE.md**

Cuối mục `### 2026-10-03 — Bộ đáp án kiểm chứng tay trong repo…`, thêm:

```markdown
**Đường sửa nhanh ngoài thuật toán:** admin đặt tone trên `/admin/library`,
máy khách nhận qua `pull_overrides` (xem TONE_FLOWS.md). Ca thử đầu tiên:
đặt `pMPvJE1wwnc` = F#m.
```

- [ ] **Step 4: Commit**

```bash
git add docs/TONE_FLOWS.md docs/SERVER_ARCHITECTURE.md docs/NGHIEN_CUU_DO_TONE.md
git commit -m "docs: luồng tone admin đặt + feed cursor"
```

---

## Self-review

- **Spec coverage:** §3.1 nguồn admin + ép client → Task 1. §3.2 form, route `set`, bơm `last_seen` ở `set/pin/hide/delete` → Task 2. §3.3 feed cursor, 500/501, chỉ bản ghim, cursor hỏng → Task 3. §3.4 export không đổi (bản ghim đã vào export). §4.1 `pull_overrides`, cursor file, áp trang rồi lưu, trần 20 trang, bỏ qua human, cập nhật cột tone, xoá đệm → Task 4. §4.2 không đổi code (hành vi sẵn có; test resolve ở Task 5). §4.3 ba điểm gọi → Task 5. §5 test → từng task. §6 kiểm chứng thật → làm tay sau khi deploy, không nằm trong plan.
- **Type consistency:** `pull_overrides()` trả dict với `ok/fetched/applied/skipped_human/pages` dùng nhất quán ở Task 4 và 5; `sync_songs` trả `(found, stats)` khớp `_on_sync_done(found, pending, stats)`; `encode_cursor(last_seen, tone_id)` / `decode_cursor(text)` khớp giữa Task 1 và 3; `CLIENT_SOURCES` dùng ở Task 1 router.
- **Review Focus:** (1) Task 3 `test_cung_last_seen...`; (2) Task 3 `test_cursor_hong...`; (3) Task 4 `test_pull_overrides_mat_mang_o_trang_hai...`; (4) Task 2 `test_ghim_ban_khac...`, `test_an_ban_ghim...`; (5) Task 1 `test_client_tu_phong_admin...`.
