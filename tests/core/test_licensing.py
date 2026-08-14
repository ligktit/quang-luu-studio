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


# --- Fingerprint v2: chỉ MachineGuid ---

@pytest.fixture
def fresh_device(monkeypatch):
    """Xoá cache fingerprint trong process để mỗi test tính lại từ đầu."""
    from core.licensing import device as dev
    monkeypatch.setattr(dev, "_cached", None)
    monkeypatch.setattr(dev, "_cached_legacy", None)
    return dev


def test_fingerprint_ignores_mac_and_hostname(fresh_device, monkeypatch):
    """
    Đây là gốc rễ của "vài ngày lại bị đá ra": đổi card mạng/tên máy làm
    fingerprint đổi theo, server tính thành máy khác.
    """
    monkeypatch.setattr(fresh_device, "_machine_guid", lambda: "GUID-CO-DINH-1234")
    monkeypatch.setattr("uuid.getnode", lambda: 0x001122334455)
    monkeypatch.setattr("platform.node", lambda: "MAY-CU")
    first = fresh_device.get_fingerprint()

    # Cắm USB Wi-Fi khác + đổi tên máy + đổi CPU string
    monkeypatch.setattr(fresh_device, "_cached", None)
    monkeypatch.setattr("uuid.getnode", lambda: 0xAABBCCDDEEFF)
    monkeypatch.setattr("platform.node", lambda: "MAY-MOI")
    monkeypatch.setenv("PROCESSOR_IDENTIFIER", "CPU-KHAC")
    assert fresh_device.get_fingerprint() == first


def test_fingerprint_changes_with_machine_guid(fresh_device, monkeypatch):
    """Máy khác (cài lại Windows) vẫn phải ra fingerprint khác."""
    monkeypatch.setattr(fresh_device, "_machine_guid", lambda: "GUID-MAY-A")
    a = fresh_device.get_fingerprint()
    monkeypatch.setattr(fresh_device, "_cached", None)
    monkeypatch.setattr(fresh_device, "_machine_guid", lambda: "GUID-MAY-B")
    assert fresh_device.get_fingerprint() != a


def test_legacy_fingerprint_keeps_old_formula(fresh_device, monkeypatch):
    """Công thức cũ phải giữ NGUYÊN VẸN, nếu không server không nhận ra máy cũ."""
    import hashlib
    monkeypatch.setattr(fresh_device, "_machine_guid", lambda: "GUID-X")
    monkeypatch.setattr("uuid.getnode", lambda: 0x001122334455)
    monkeypatch.setattr("platform.node", lambda: "MAY-CU")
    monkeypatch.setenv("PROCESSOR_IDENTIFIER", "CPU-CU")

    expected = hashlib.sha256(
        "GUID-X|001122334455|MAY-CU|CPU-CU".encode()).hexdigest()
    assert fresh_device.legacy_fingerprint() == expected
    assert fresh_device.get_fingerprint() != expected


def test_falls_back_to_legacy_without_machine_guid(fresh_device, monkeypatch):
    """Không đọc được registry → dùng công thức cũ, KHÔNG được ra hằng số chung."""
    monkeypatch.setattr(fresh_device, "_machine_guid", lambda: "")
    assert fresh_device.get_fingerprint() == fresh_device.legacy_fingerprint()


def test_requests_carry_legacy_fingerprint(cache, monkeypatch):
    """Server cần legacy_fingerprint để nối lại danh tính — thiếu là hỏng cả đợt."""
    sent = {}

    def _capture(path, payload):
        sent[path] = payload
        return 200, {"valid": True, "token": fake.make_token(FP), "allowed": True}

    monkeypatch.setattr(lic, "_post", _capture)
    monkeypatch.setattr(lic, "legacy_fingerprint", lambda: "FINGERPRINT-CU")

    lic.activate_online("AB12-CD34-EF56-GH78-XY90")
    lic.verify_online()
    lic.start_trial_online()

    for path, payload in sent.items():
        assert payload["device_fingerprint"] == FP, path
        assert payload["legacy_fingerprint"] == "FINGERPRINT-CU", path
    assert len(sent) == 3


def test_legacy_omitted_when_identical(cache, monkeypatch):
    """Máy vốn đã dùng công thức cũ → không gửi field thừa."""
    sent = {}
    monkeypatch.setattr(lic, "_post", lambda path, payload: (sent.setdefault(path, payload), (0, {}))[1])
    monkeypatch.setattr(lic, "legacy_fingerprint", lambda: FP)

    lic.activate_online("AB12-CD34-EF56-GH78-XY90")
    assert sent["/api/v1/activate"]["legacy_fingerprint"] is None


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


# ── Lỗi tạm thời KHÔNG được giết license (nguyên nhân A) ─────────────────────

@pytest.mark.parametrize("status,body", [
    (429, {"error": "Rate limit exceeded: 60 per 1 minute"}),  # slowapi
    (502, {}),                                                  # nginx trả HTML → parse fail
    (503, {"valid": False, "status": "server_error"}),          # nginx sau bản vá Phase 1
    (500, {"detail": "Internal Server Error"}),                 # FastAPI mặc định
    (200, {"valid": False}),                                    # body dị dạng
])
def test_transient_errors_keep_license(cache, monkeypatch, status, body):
    """
    429/5xx/JSON hỏng là chuyện của máy chủ, không phải bằng chứng máy này hết
    quyền. Trước bản vá, mọi response thiếu field `status` đều bị quy về
    "invalid" và làm bay license — một cú 502 lúc deploy là đủ.
    """
    _write(cache, license_token=fake.make_token(FP, plan="premium"),
           license_code="AB12-CD34-EF56-GH78-XY90")
    monkeypatch.setattr(lic, "_post", lambda path, payload: (status, body))

    result = lic.verify_online()
    assert result["success"] is False
    assert result["status"] == "offline"
    assert lic.has_online_license() is True, "license phải còn nguyên"
    assert lic.current_plan() == "premium"
    assert lic.cached_code() == "AB12-CD34-EF56-GH78-XY90"


def test_expired_token_response_keeps_license(cache, monkeypatch):
    """Server bản cũ trả 401 'invalid' cho token quá hạn — máy chỉ cần token mới."""
    _write(cache, license_token=fake.make_token(FP, exp_in=-3600),
           license_code="AB12-CD34-EF56-GH78-XY90")
    monkeypatch.setattr(lic, "_post", lambda path, payload: (
        401, {"valid": False, "status": "invalid", "message": "Token hết hạn."}))

    assert lic.verify_online()["status"] == "offline"
    assert lic.cached_code() == "AB12-CD34-EF56-GH78-XY90"


def test_revoked_keeps_code_for_prefill(cache, monkeypatch):
    """Mất quyền thật thì bỏ token, nhưng giữ mã để điền sẵn ô nhập."""
    _write(cache, license_token=fake.make_token(FP), license_code="AB12-CD34-EF56-GH78-XY90")
    monkeypatch.setattr(lic, "_post", lambda path, payload: (
        403, {"valid": False, "status": "revoked", "message": "Mã đã bị thu hồi."}))

    assert lic.verify_online()["status"] == "revoked"
    assert lic.has_online_license() is False
    assert lic.cached_code() == "AB12-CD34-EF56-GH78-XY90"


# ── Hết grace phải tự gia hạn, không đá người dùng ra (nguyên nhân B) ────────

def test_reconcile_renews_when_grace_expired(cache, monkeypatch):
    """
    Token thật nhưng quá grace + máy CÓ mạng → phải tự xin token mới.
    Trước bản vá: verified_claims() không kiểm hạn nên reconcile return sớm và
    người dùng bị đá thẳng ra màn hình "Bản quyền đã hết hạn".
    """
    fresh = fake.make_token(FP, exp_in=30 * 86400)
    _write(cache, license_token=fake.make_token(FP, exp_in=-86400),
           license_code="AB12-CD34-EF56-GH78-XY90")
    monkeypatch.setattr(lic, "_post", lambda path, payload: (200, {"valid": True, "token": fresh}))

    lic.startup_reconcile()
    assert _read(cache)["license_token"] == fresh
    assert lic.is_grace_valid() is True


def test_reconcile_offline_keeps_cache(cache, monkeypatch):
    """Quá grace + mất mạng → giữ nguyên cache để lần sau có mạng tự khỏi."""
    token = fake.make_token(FP, exp_in=-86400)
    _write(cache, license_token=token, license_code="AB12-CD34-EF56-GH78-XY90")
    monkeypatch.setattr(lic, "_post", lambda path, payload: (0, {}))

    lic.startup_reconcile()
    assert _read(cache)["license_token"] == token


def test_reconcile_drops_token_when_revoked(cache, monkeypatch):
    """Quá grace + server nói đã thu hồi → mất quyền thật, bỏ token."""
    _write(cache, license_token=fake.make_token(FP, exp_in=-86400),
           license_code="AB12-CD34-EF56-GH78-XY90")
    monkeypatch.setattr(lic, "_post", lambda path, payload: (
        403, {"valid": False, "status": "revoked", "message": "Mã đã bị thu hồi."}))

    lic.startup_reconcile()
    assert "license_token" not in _read(cache)


def test_reconcile_recovers_from_code_only_cache(cache, monkeypatch):
    """Máy đã mất token (bản cũ xoá mất) nhưng còn mã → check-in lại bằng mã."""
    fresh = fake.make_token(FP)
    _write(cache, license_code="AB12-CD34-EF56-GH78-XY90")
    monkeypatch.setattr(lic, "_post", lambda path, payload: (200, {"valid": True, "token": fresh}))

    lic.startup_reconcile()
    assert lic.has_online_license() is True


# ── Phân biệt "cần gia hạn" với "hết hạn thật" ───────────────────────────────

def test_needs_renewal_vs_expired(cache):
    """Grace hết nhưng license còn hạn → cần gia hạn, KHÔNG phải hết hạn."""
    from core.activation import ActivationManager as AM

    _write(cache, license_token=fake.make_token(FP, exp_in=-3600, lexp_in=300 * 86400))
    assert lic.in_license_term() is True
    assert AM.needs_renewal() is True
    assert AM.is_expired() is True   # cổng kích hoạt vẫn chặn, chỉ đổi lời nhắn


def test_truly_expired_is_not_renewal(cache):
    """Hết hạn thật → không được hiện 'chỉ cần bật mạng'."""
    from core.activation import ActivationManager as AM

    _write(cache, license_token=fake.make_token(FP, exp_in=-3600, lexp_in=-86400))
    assert lic.in_license_term() is False
    assert AM.needs_renewal() is False


def test_no_license_is_not_renewal(cache):
    from core.activation import ActivationManager as AM

    _write(cache)
    assert AM.needs_renewal() is False
