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
