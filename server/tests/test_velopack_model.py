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
