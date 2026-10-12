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
