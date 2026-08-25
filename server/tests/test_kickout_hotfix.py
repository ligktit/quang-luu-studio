"""
Phase 1 của docs/LICENSING_KICKOUT_FIX_PLAN.md — "máy dùng vài ngày bị đá ra".

Hai nhóm bảo đảm, đều nhắm vào việc giữ license cho MÁY ĐANG CHẠY BẢN CŨ ngoài
thị trường (chúng không cập nhật ngay được, nên server phải tự lo):

  1. Token quá hạn grace vẫn check-in được → máy tự lấy token mới thay vì bị đá.
  2. Mọi lỗi TẠM THỜI (429, 5xx) trả JSON có `status` nằm NGOÀI tập trạng thái
     "mất quyền" — client cũ chỉ xoá cache khi thấy revoked/expired/not_activated/
     invalid, nên các giá trị này giữ được license.
"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import License
from app.security import _private_key, limiter
from app.services import codegen

FP = "kickout-device-01"

# Trạng thái khiến client XOÁ license. Lỗi tạm thời tuyệt đối không được rơi vào
# tập này (kể cả "invalid" — bản client cũ dùng nó làm giá trị mặc định).
TERMINAL = {"revoked", "expired", "not_activated", "invalid"}


def _make_license(plan="standard", max_devices=1):
    code = codegen.generate_code()
    with SessionLocal() as db:
        db.add(License(code=code, max_devices=max_devices, status="unused", plan=plan))
        db.commit()
    return code


def _activate(client, code, fp=FP):
    return client.post("/api/v1/activate", json={"code": code, "device_fingerprint": fp}).json()


def _expired_token(code, fp=FP, days_ago=3):
    """Token thật (ký đúng khoá) nhưng đã quá hạn — máy offline lâu ngày."""
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "code": code, "fp": fp, "plan": "standard",
            "iat": int((now - timedelta(days=days_ago + 30)).timestamp()),
            "exp": int((now - timedelta(days=days_ago)).timestamp()),
            "lexp": int((now + timedelta(days=300)).timestamp()),
        },
        _private_key(),
        algorithm="RS256",
    )


# ── 1. Token quá hạn vẫn đổi được token mới ──────────────────────────────────

def test_verify_accepts_expired_token(client):
    """Máy mất mạng quá grace, có mạng lại → phải được cấp token mới, không phải 401."""
    code = _make_license()
    _activate(client, code)

    r = client.post("/api/v1/license/verify", json={
        "token": _expired_token(code), "device_fingerprint": FP,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is True
    # Token mới phải còn hạn thật sự (grace tính lại từ bây giờ).
    claims = jwt.decode(body["token"], _private_key().public_key(), algorithms=["RS256"])
    assert claims["exp"] > datetime.now(timezone.utc).timestamp()


def test_expired_token_of_unknown_device_rejected(client):
    """Token mang danh tính không có trong DB của mã này → không nối được vào đâu."""
    code = _make_license()
    _activate(client, code)
    r = client.post("/api/v1/license/verify", json={
        "token": _expired_token(code, fp="danh-tinh-la-99"), "device_fingerprint": "may-khac-88",
    })
    assert r.status_code == 403
    assert r.json()["status"] == "not_activated"


def test_expired_token_of_revoked_license_rejected(client):
    """Hiệu lực vẫn do DB quyết: mã bị thu hồi thì token quá hạn cũng vô dụng."""
    code = _make_license()
    _activate(client, code)
    with SessionLocal() as db:
        db.query(License).filter_by(code=code).one().status = "revoked"
        db.commit()

    r = client.post("/api/v1/license/verify", json={
        "token": _expired_token(code), "device_fingerprint": FP,
    })
    assert r.status_code == 403
    assert r.json()["status"] == "revoked"


def test_verify_falls_back_to_code_when_token_garbage(client):
    """Token hỏng nhưng còn mã + máy đã ràng → vẫn check-in được."""
    code = _make_license()
    _activate(client, code)
    r = client.post("/api/v1/license/verify", json={
        "token": "khong-phai-jwt", "code": code, "device_fingerprint": FP,
    })
    assert r.status_code == 200, r.text
    assert r.json()["valid"] is True


def test_garbage_token_without_code_still_401(client):
    """Không có gì để đối chiếu thì vẫn từ chối (giữ nguyên hành vi cũ)."""
    _activate(client, _make_license())
    r = client.post("/api/v1/license/verify", json={
        "token": "khong-phai-jwt", "device_fingerprint": FP,
    })
    assert r.status_code == 401


def test_code_fallback_still_requires_registered_device(client):
    """Biết mã thôi không đủ — máy chưa ràng vẫn bị chặn."""
    code = _make_license()
    _activate(client, code)
    r = client.post("/api/v1/license/verify", json={
        "code": code, "device_fingerprint": "may-la-hoac-99",
    })
    assert r.status_code == 403
    assert r.json()["status"] == "not_activated"


# ── 2. Lỗi tạm thời không được giết license ──────────────────────────────────

@app.post("/__test_boom__")
def _boom():  # pragma: no cover - chỉ để kích lỗi 500
    raise RuntimeError("no gon")


@app.post("/__test_ratelimit__")
@limiter.limit("1/minute")
def _probe(request: Request):  # pragma: no cover - thân hàm không quan trọng
    return {"ok": True}


def test_unhandled_error_returns_soft_status():
    """500 phải là JSON có status='server_error', không phải HTML/detail trơ trọi."""
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post("/__test_boom__")
    assert r.status_code == 500
    body = r.json()
    assert body["status"] == "server_error"
    assert body["status"] not in TERMINAL


def test_rate_limit_returns_soft_status(client):
    """429 phải là JSON có status='rate_limited' — client cũ sẽ giữ nguyên cache."""
    assert client.post("/__test_ratelimit__").status_code == 200
    r = client.post("/__test_ratelimit__")
    assert r.status_code == 429
    body = r.json()
    assert body["status"] == "rate_limited"
    assert body["status"] not in TERMINAL
    assert body["valid"] is False


# ── 3. "Reset máy" phải thật sự reset (Phase 2) ──────────────────────────────

def _license_id(code):
    with SessionLocal() as db:
        return db.query(License).filter_by(code=code).one().id


def test_reset_devices_allows_reactivation(admin_client):
    """
    Đúng thao tác hỗ trợ hay dùng nhất: khách kẹt "đủ giới hạn thiết bị" → admin
    bấm Reset máy → khách nhập lại mã. Trước đây bước cuối trả 403 vĩnh viễn vì
    bản ghi revoked vẫn nằm trong DB.
    """
    code = _make_license(max_devices=1)
    assert _activate(admin_client, code)["valid"] is True

    r = admin_client.post(f"/admin/licenses/{_license_id(code)}/reset-devices")
    assert r.status_code in (200, 303)

    again = admin_client.post("/api/v1/activate", json={"code": code, "device_fingerprint": FP})
    assert again.status_code == 200, again.text
    assert again.json()["valid"] is True


def test_reset_devices_frees_the_slot(admin_client):
    """Sau reset, MÁY KHÁC cũng vào được — slot thật sự trống chứ không chỉ ẩn đi."""
    code = _make_license(max_devices=1)
    _activate(admin_client, code)
    admin_client.post(f"/admin/licenses/{_license_id(code)}/reset-devices")

    r = admin_client.post("/api/v1/activate", json={"code": code, "device_fingerprint": "may-thay-the-01"})
    assert r.status_code == 200, r.text


def test_delete_single_device_frees_slot(admin_client):
    """Gỡ đúng một máy (fingerprint cũ do drift) mà không đụng máy còn lại."""
    code = _make_license(max_devices=1)
    _activate(admin_client, code, fp="fingerprint-cu-01")

    with SessionLocal() as db:
        dev_id = db.query(License).filter_by(code=code).one().devices[0].id

    limited = admin_client.post("/api/v1/activate", json={"code": code, "device_fingerprint": "fingerprint-moi-02"})
    assert limited.status_code == 409
    assert "fingerp" in limited.json()["message"]  # có mã máy để hỗ trợ tra

    admin_client.post(f"/admin/devices/{dev_id}/delete")
    ok = admin_client.post("/api/v1/activate", json={"code": code, "device_fingerprint": "fingerprint-moi-02"})
    assert ok.status_code == 200, ok.text


def test_delete_device_requires_admin(client):
    """Endpoint xoá máy không được để lộ cho người chưa đăng nhập."""
    code = _make_license()
    _activate(client, code)
    with SessionLocal() as db:
        dev_id = db.query(License).filter_by(code=code).one().devices[0].id

    r = client.post(f"/admin/devices/{dev_id}/delete", follow_redirects=False)
    assert r.status_code == 303 and "/admin/login" in r.headers["location"]
    with SessionLocal() as db:
        assert db.query(License).filter_by(code=code).one().devices, "không được xoá khi chưa đăng nhập"


def test_manual_revoke_still_blocks(admin_client):
    """Cấm riêng một máy (revoked=True) vẫn phải chặn — reset không được làm yếu điều này."""
    code = _make_license()
    _activate(admin_client, code)
    with SessionLocal() as db:
        lic = db.query(License).filter_by(code=code).one()
        lic.devices[0].revoked = True
        db.commit()

    r = admin_client.post("/api/v1/activate", json={"code": code, "device_fingerprint": FP})
    assert r.status_code == 403
    assert r.json()["status"] == "revoked"


# ── 4. Fingerprint v2: di trú không tốn slot, không né được lệnh cấm ─────────

FP_V1 = "fingerprint-cu-cua-may-nay-0001"
FP_V2 = "fingerprint-v2-cua-may-nay-0001"


def _devices(code):
    with SessionLocal() as db:
        lic = db.query(License).filter_by(code=code).one()
        return [(d.fingerprint, d.revoked) for d in lic.devices]


def test_activate_migrates_legacy_fingerprint(client):
    """
    Máy cập nhật lên bản mới: fingerprint đổi nhưng KHÔNG được tính là máy thứ
    hai. Đây là ca hỏng chết người — làm sai là đá cả đội hình ra cùng lúc.
    """
    code = _make_license(max_devices=1)
    client.post("/api/v1/activate", json={"code": code, "device_fingerprint": FP_V1})

    r = client.post("/api/v1/activate", json={
        "code": code, "device_fingerprint": FP_V2, "legacy_fingerprint": FP_V1,
    })
    assert r.status_code == 200, r.text
    assert _devices(code) == [(FP_V2, False)], "phải đổi tên tại chỗ, không thêm bản ghi"


def test_verify_accepts_token_bound_to_legacy_fp(client):
    """
    Token đang cache mang `fp` cũ. Nếu router không chấp nhận, chính bản cập nhật
    sẽ làm mọi máy bị 403 rồi rơi ra màn hình kích hoạt.
    """
    code = _make_license()
    token = client.post("/api/v1/activate", json={
        "code": code, "device_fingerprint": FP_V1}).json()["token"]

    r = client.post("/api/v1/license/verify", json={
        "token": token, "device_fingerprint": FP_V2, "legacy_fingerprint": FP_V1,
    })
    assert r.status_code == 200, r.text
    assert _devices(code) == [(FP_V2, False)]
    # Token mới phải ràng theo fingerprint MỚI.
    claims = jwt.decode(r.json()["token"], _private_key().public_key(), algorithms=["RS256"])
    assert claims["fp"] == FP_V2


def test_duplicate_rows_merged_on_migration(client):
    """Máy đã lỡ sinh 2 bản ghi (drift) → gộp lại, trả slot về cho khách."""
    code = _make_license(max_devices=2)
    client.post("/api/v1/activate", json={"code": code, "device_fingerprint": FP_V1})
    client.post("/api/v1/activate", json={"code": code, "device_fingerprint": FP_V2})
    assert len(_devices(code)) == 2

    r = client.post("/api/v1/license/verify", json={
        "code": code, "device_fingerprint": FP_V2, "legacy_fingerprint": FP_V1,
    })
    assert r.status_code == 200, r.text
    assert _devices(code) == [(FP_V2, False)]


def test_ban_follows_the_machine_across_migration(client):
    """Máy bị chặn KHÔNG được né lệnh cấm bằng cách cập nhật app."""
    code = _make_license()
    client.post("/api/v1/activate", json={"code": code, "device_fingerprint": FP_V1})
    with SessionLocal() as db:
        db.query(License).filter_by(code=code).one().devices[0].revoked = True
        db.commit()

    r = client.post("/api/v1/activate", json={
        "code": code, "device_fingerprint": FP_V2, "legacy_fingerprint": FP_V1,
    })
    assert r.status_code == 403
    assert r.json()["status"] == "revoked"
    assert _devices(code) == [(FP_V1, True)], "không được di trú bản ghi đang bị chặn"


def test_old_client_drift_rescued_by_token(client):
    """
    CLIENT CŨ (≤1.6.2) bị drift: chỉ gửi token + fingerprint mới, không biết gửi
    legacy_fingerprint. Claim `fp` trong token là chữ ký của server xác nhận danh
    tính cũ → server nối lại, máy không bị đá ra dù chưa cập nhật app.
    """
    code = _make_license(max_devices=1)
    token = client.post("/api/v1/activate", json={
        "code": code, "device_fingerprint": FP_V1}).json()["token"]

    r = client.post("/api/v1/license/verify", json={
        "token": token, "device_fingerprint": FP_V2,   # KHÔNG có legacy_fingerprint
    })
    assert r.status_code == 200, r.text
    assert _devices(code) == [(FP_V2, False)]


def test_new_client_keeps_strict_rule(client):
    """
    CLIENT MỚI (có gửi legacy_fingerprint) chịu quy tắc chặt: token không thuộc
    máy này và cũng không khớp danh tính cũ TỰ TÍNH LẠI ĐƯỢC → từ chối.
    Nhờ vậy lỗ hổng "chép activation.json sang máy khác" tự đóng lại theo từng
    máy khi khách cập nhật app.
    """
    code = _make_license()
    token = client.post("/api/v1/activate", json={
        "code": code, "device_fingerprint": FP_V1}).json()["token"]

    r = client.post("/api/v1/license/verify", json={
        "token": token, "device_fingerprint": FP_V2, "legacy_fingerprint": "danh-tinh-khac-99",
    })
    assert r.status_code == 403
    assert _devices(code) == [(FP_V1, False)], "không được đụng vào bản ghi"


def test_token_of_revoked_device_cannot_migrate(client):
    """Máy bị chặn không né được bằng cách trình token cũ với fingerprint mới."""
    code = _make_license()
    token = client.post("/api/v1/activate", json={
        "code": code, "device_fingerprint": FP_V1}).json()["token"]
    with SessionLocal() as db:
        db.query(License).filter_by(code=code).one().devices[0].revoked = True
        db.commit()

    r = client.post("/api/v1/license/verify", json={"token": token, "device_fingerprint": FP_V2})
    assert r.status_code == 403
    assert r.json()["status"] == "revoked"
    assert _devices(code) == [(FP_V1, True)]


def test_token_without_fp_claim_rejected(client):
    """Lỗ hổng dễ mắc khi nới điều kiện khớp fp: token không ràng máy phải bị chặn."""
    code = _make_license()
    client.post("/api/v1/activate", json={"code": code, "device_fingerprint": FP_V1})
    no_fp = jwt.encode({"code": code, "plan": "premium", "exp": 9999999999},
                       _private_key(), algorithm="RS256")

    r = client.post("/api/v1/license/verify", json={
        "token": no_fp, "device_fingerprint": FP_V2, "legacy_fingerprint": FP_V1,
    })
    assert r.status_code == 403


def test_trial_not_reissued_after_migration(client):
    """Bỏ sót di trú TrialGrant = mọi máy được tặng thêm 3 ngày dùng thử."""
    first = client.post("/api/v1/trial/start", json={"device_fingerprint": FP_V1}).json()
    assert first["allowed"] is True

    again = client.post("/api/v1/trial/start", json={
        "device_fingerprint": FP_V2, "legacy_fingerprint": FP_V1,
    }).json()
    assert again["started_at"] == first["started_at"], "phải nhận lại đúng mốc cũ"


def test_trial_migration_keeps_earliest_start(client):
    """Đã lỡ có 2 suất dùng thử → giữ mốc SỚM NHẤT, không kéo dài hạn."""
    old = client.post("/api/v1/trial/start", json={"device_fingerprint": FP_V1}).json()
    # Giữ mốc ở dạng aware TRƯỚC khi commit: sau commit SQLAlchemy đọc lại từ
    # SQLite ra datetime naive, .timestamp() sẽ hiểu nhầm là giờ địa phương.
    old_start = datetime.now(timezone.utc) - timedelta(days=10)
    with SessionLocal() as db:  # đẩy mốc cũ lùi về quá khứ
        from app.models import TrialGrant
        g = db.scalar(select(TrialGrant).where(TrialGrant.fingerprint == FP_V1))
        g.started_at = old_start
        db.commit()
    client.post("/api/v1/trial/start", json={"device_fingerprint": FP_V2})

    merged = client.post("/api/v1/trial/start", json={
        "device_fingerprint": FP_V2, "legacy_fingerprint": FP_V1,
    }).json()
    assert merged["allowed"] is False, "10 ngày trước là đã hết hạn dùng thử"
    assert merged["started_at"] == pytest.approx(old_start.timestamp(), abs=2)
    assert old["allowed"] is True  # lần đầu vẫn được phép


def test_no_legacy_fingerprint_behaves_as_before(client):
    """Client cũ (không gửi legacy_fingerprint) phải chạy y như trước."""
    code = _make_license(max_devices=1)
    assert client.post("/api/v1/activate", json={
        "code": code, "device_fingerprint": FP_V1}).status_code == 200
    r = client.post("/api/v1/activate", json={"code": code, "device_fingerprint": FP_V2})
    assert r.status_code == 409  # vẫn đếm là máy thứ hai


@pytest.mark.parametrize("path", ["/api/v1/license/verify", "/api/v1/activate"])
def test_real_license_errors_still_pass_through(client, path):
    """Handler mới không được nuốt lỗi nghiệp vụ thật — thu hồi vẫn phải tới nơi."""
    code = _make_license()
    _activate(client, code)
    with SessionLocal() as db:
        db.query(License).filter_by(code=code).one().status = "revoked"
        db.commit()

    r = client.post(path, json={"code": code, "device_fingerprint": FP})
    assert r.status_code == 403
    assert r.json()["status"] == "revoked"
