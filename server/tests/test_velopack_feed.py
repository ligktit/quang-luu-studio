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
