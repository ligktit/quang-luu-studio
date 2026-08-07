"""Test lớp licensing client: fingerprint, xác minh chữ ký token, thu hồi."""
import json
import time

import pytest

from core.config import DEFAULT_LICENSE_SERVER_URL, AppConfig
from core.licensing import client as lic
from core.licensing.device import get_fingerprint
from tests.core import _fake_license as fake

FP = "0" * 64


@pytest.fixture(autouse=True)
def _reset_appconfig():
    AppConfig._data = None
    yield
    AppConfig._data = None


@pytest.fixture
def cache(tmp_path, monkeypatch):
    path = str(tmp_path / "activation.json")
    monkeypatch.setattr("core.licensing.client.ACTIVATION_FILE", path)
    monkeypatch.setattr(lic, "_claims_memo", ("", None))
    monkeypatch.setattr("core.licensing.client.get_fingerprint", lambda: FP)
    fake.use_test_key(monkeypatch)
    return path


def _write(path, **fields):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fields, f)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_fingerprint_stable_and_hex64():
    fp1 = get_fingerprint()
    fp2 = get_fingerprint()
    assert fp1 == fp2
    assert len(fp1) == 64
    assert all(c in "0123456789abcdef" for c in fp1)


def test_blank_config_falls_back_to_builtin_server():
    """Xoá license_server_url khỏi app_config.json không tắt được licensing."""
    AppConfig.load()
    AppConfig._data["license_server_url"] = ""
    assert lic.server_url() == DEFAULT_LICENSE_SERVER_URL.rstrip("/")
    assert lic.server_configured() is True


def test_config_can_still_point_elsewhere():
    AppConfig.load()
    AppConfig._data["license_server_url"] = "http://127.0.0.1:9/"
    assert lic.server_url() == "http://127.0.0.1:9"


# --- Xác minh chữ ký ---

def test_plan_comes_from_signed_claim(cache):
    _write(cache, license_token=fake.make_token(FP, plan="premium"))
    assert lic.current_plan() == "premium"
    assert lic.has_online_license() is True


def test_editing_plan_in_cache_breaks_signature(cache):
    """Sửa tay 'plan' trong activation.json → token hỏng chữ ký → tụt về standard."""
    honest = fake.make_token(FP, plan="standard")
    _write(cache, license_token=fake.tamper_plan(honest, "premium"))
    assert lic.has_online_license() is False
    assert lic.current_plan() == "standard"


def test_grace_fields_in_cache_are_ignored(cache):
    """Bơm grace_until_ts thật xa cũng vô nghĩa: hạn đọc từ claim đã ký."""
    _write(
        cache,
        license_token=fake.make_token(FP, exp_in=-60),
        grace_until_ts=int(time.time()) + 10 * 365 * 86400,
        license_expires_ts=int(time.time()) + 10 * 365 * 86400,
        license_plan="premium",
    )
    assert lic.is_grace_valid() is False
    assert lic.current_plan() == "standard"  # claim thật là standard


def test_grace_valid_within_window(cache):
    _write(cache, license_token=fake.make_token(FP, exp_in=3600))
    assert lic.is_grace_valid() is True


def test_license_expiry_caps_grace(cache):
    """Grace còn hiệu lực nhưng license đã quá hạn → hết quyền."""
    _write(cache, license_token=fake.make_token(FP, exp_in=3600, lexp_in=-86400))
    assert lic.is_grace_valid() is False


# --- Thu hồi ---

def test_revoked_clears_cache_immediately(cache, monkeypatch):
    _write(cache, license_token=fake.make_token(FP, plan="premium"),
           license_code="AB12-CD34-EF56-GH78-XY90")
    monkeypatch.setattr(lic, "_post", lambda path, payload: (
        403, {"valid": False, "status": "revoked", "message": "Mã đã bị thu hồi."}))

    result = lic.verify_online()
    assert result["status"] == "revoked"
    assert lic.has_online_license() is False
    assert lic.current_plan() == "standard"
    assert "license_token" not in _read(cache)


def test_offline_verify_keeps_cache(cache, monkeypatch):
    """Mất mạng KHÔNG được xoá license — đó là lý do có grace."""
    _write(cache, license_token=fake.make_token(FP), license_code="AB12-CD34-EF56-GH78-XY90")
    monkeypatch.setattr(lic, "_post", lambda path, payload: (0, {}))

    result = lic.verify_online()
    assert result["status"] == "offline"
    assert lic.has_online_license() is True


def test_verify_success_refreshes_token(cache, monkeypatch):
    old = fake.make_token(FP, exp_in=60)
    new = fake.make_token(FP, exp_in=7 * 86400)
    _write(cache, license_token=old, license_code="AB12-CD34-EF56-GH78-XY90")
    monkeypatch.setattr(lic, "_post", lambda path, payload: (200, {"valid": True, "token": new}))

    assert lic.verify_online()["success"] is True
    assert _read(cache)["license_token"] == new


# --- Chuyển tiếp từ bản cũ ---

def test_startup_reconcile_swaps_legacy_token(cache, monkeypatch):
    """Token HS256 của bản cũ được đổi lấy token RS256 khi còn mạng."""
    new = fake.make_token(FP)
    _write(cache, license_token="eyJhbGciOiJIUzI1NiJ9.eyJjb2RlIjoiWCJ9.oldsig",
           license_code="AB12-CD34-EF56-GH78-XY90")
    monkeypatch.setattr(lic, "_post", lambda path, payload: (200, {"valid": True, "token": new}))

    lic.startup_reconcile()
    assert _read(cache)["license_token"] == new
    assert lic.has_online_license() is True


def test_startup_reconcile_drops_forged_token(cache, monkeypatch):
    """Token bịa + server từ chối → xoá sạch, buộc kích hoạt lại."""
    _write(cache, license_token="aaa.bbb.ccc", license_code="AB12-CD34-EF56-GH78-XY90")
    monkeypatch.setattr(lic, "_post", lambda path, payload: (
        404, {"valid": False, "status": "invalid", "message": "Mã không tồn tại."}))

    lic.startup_reconcile()
    assert "license_token" not in _read(cache)


def test_startup_reconcile_leaves_valid_token_alone(cache, monkeypatch):
    token = fake.make_token(FP)
    _write(cache, license_token=token)

    def _boom(path, payload):
        raise AssertionError("không cần gọi server khi token còn hợp lệ")

    monkeypatch.setattr(lic, "_post", _boom)
    lic.startup_reconcile()
    assert _read(cache)["license_token"] == token


def test_clear_cache_keeps_trial_marker(cache):
    _write(cache, license_token=fake.make_token(FP), trial_start=12345.0)
    lic.clear_license_cache()
    data = _read(cache)
    assert "license_token" not in data
    assert data["trial_start"] == 12345.0
