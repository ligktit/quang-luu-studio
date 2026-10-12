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

_FP_RE = re.compile(r"[A-Za-z0-9_-]{1,128}")
_NAME_RE = re.compile(r"[A-Za-z0-9._-]{1,200}")


def parse_semver(v):
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", (v or "").strip())
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def valid_fingerprint(fp):
    return bool(_FP_RE.fullmatch(fp or ""))


def valid_filename(name):
    return bool(_NAME_RE.fullmatch(name or "")) and name not in (".", "..")


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
