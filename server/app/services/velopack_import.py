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
