"""
Test ActivationManager sau khi kích hoạt chuyển sang chế độ chỉ-online.

Không còn checksum cục bộ để test: mã hợp lệ hay không do server trả lời, nên
các test dưới đây giả lập phản hồi server bằng cách patch client._post.
"""
import json
import time

import pytest

from core.activation import ActivationManager
from core.licensing import client as lic
from core.licensing import trial_marker
from tests.core import _fake_license as fake

FP = "0" * 64


@pytest.fixture(autouse=True)
def license_env(tmp_path, monkeypatch):
    """Cache tạm, khoá test, fingerprint cố định, registry giả trong bộ nhớ."""
    act_file = str(tmp_path / "activation.json")
    monkeypatch.setattr("core.activation.ACTIVATION_FILE", act_file)
    monkeypatch.setattr("core.licensing.client.ACTIVATION_FILE", act_file)
    monkeypatch.setattr(lic, "_claims_memo", ("", None))
    monkeypatch.setattr("core.licensing.client.get_fingerprint", lambda: FP)
    fake.use_test_key(monkeypatch)

    registry = {"value": 0.0}
    monkeypatch.setattr(trial_marker, "read", lambda: registry["value"])

    def _write(started_at):
        if not registry["value"] or started_at < registry["value"]:
            registry["value"] = float(started_at)

    monkeypatch.setattr(trial_marker, "write", _write)
    yield act_file, registry


@pytest.fixture
def act_file(license_env):
    return license_env[0]


def _write_cache(path, **fields):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fields, f)


def _server(monkeypatch, status, body):
    """Giả lập một phản hồi HTTP từ server license."""
    monkeypatch.setattr(lic, "_post", lambda path, payload: (status, body))


# --- Kiểm tra format mã (chỉ để bắt lỗi gõ nhầm) ---

def test_validate_code_structure_correct():
    assert ActivationManager._validate_code_structure("A1B2-C3D4-E5F6-G7H8-1A2B") is True


def test_validate_code_structure_missing_segment():
    assert ActivationManager._validate_code_structure("ABCD-EFGH-IJKL-MNOP") is False


def test_validate_code_structure_wrong_length():
    assert ActivationManager._validate_code_structure("ABC-EFGH-IJKL-MNOP-QRST") is False


def test_validate_code_structure_special_char():
    assert ActivationManager._validate_code_structure("ABCD-EFG!-IJKL-MNOP-QRST") is False


# --- Vòng đời license ---

def test_is_activated_no_cache():
    assert ActivationManager.is_activated() is False
    assert ActivationManager.is_expired() is True
    assert ActivationManager.get_days_remaining() == 0


def test_is_activated_with_signed_token(act_file):
    _write_cache(act_file, license_token=fake.make_token(FP))
    assert ActivationManager.is_activated() is True
    assert ActivationManager.is_expired() is False


def test_token_of_another_machine_is_rejected(act_file):
    """Bê activation.json sang máy khác thì token không dùng được."""
    _write_cache(act_file, license_token=fake.make_token("f" * 64))
    assert ActivationManager.is_activated() is False


def test_unsigned_token_is_rejected(act_file):
    """Token tự chế (không chữ ký) — cách bản cũ bị qua mặt."""
    _write_cache(act_file, license_token="eyJhbGciOiJub25lIn0.eyJwbGFuIjoicHJlbWl1bSJ9.")
    assert ActivationManager.is_activated() is False


def test_expired_grace_counts_as_expired(act_file):
    _write_cache(act_file, license_token=fake.make_token(FP, exp_in=-3600))
    assert ActivationManager.is_activated() is True   # token thật, chỉ là hết grace
    assert ActivationManager.is_expired() is True
    assert ActivationManager.needs_activation() is True


def test_days_remaining_reads_license_expiry(act_file):
    _write_cache(act_file, license_token=fake.make_token(FP, lexp_in=100 * 86400))
    assert 99 <= ActivationManager.get_days_remaining() <= 100


def test_activate_rejects_bad_structure_without_network(monkeypatch):
    def _boom(path, payload):
        raise AssertionError("không được gọi server khi mã sai format")

    monkeypatch.setattr(lic, "_post", _boom)
    assert ActivationManager.activate("INVALID-CODE")["success"] is False


def test_activate_success_stores_token(monkeypatch, act_file):
    token = fake.make_token(FP, plan="premium")
    _server(monkeypatch, 200, {"valid": True, "token": token, "plan": "premium",
                               "days_remaining": 365})
    res = ActivationManager.activate("AB12-CD34-EF56-GH78-XY90")
    assert res["success"] is True
    assert ActivationManager.is_activated() is True
    assert json.loads(open(act_file, encoding="utf-8").read())["license_token"] == token


def test_activate_refuses_token_server_cannot_prove(monkeypatch):
    """Server (hoặc kẻ đứng giữa) trả token sai chữ ký → không lưu."""
    _server(monkeypatch, 200, {"valid": True, "token": "aaa.bbb.ccc", "plan": "premium"})
    res = ActivationManager.activate("AB12-CD34-EF56-GH78-XY90")
    assert res["success"] is False
    assert ActivationManager.is_activated() is False


def test_activate_offline_gives_clear_error(monkeypatch):
    _server(monkeypatch, 0, {})
    res = ActivationManager.activate("AB12-CD34-EF56-GH78-XY90")
    assert res["success"] is False
    assert "internet" in res["error"].lower() or "máy chủ" in res["error"].lower()


# --- Dùng thử ---

def test_start_trial_uses_server(monkeypatch, act_file, license_env):
    started = time.time()
    _server(monkeypatch, 200, {"allowed": True, "started_at": started, "days_remaining": 3.0})
    res = ActivationManager.start_trial()
    assert res["success"] is True
    assert res["days_remaining"] == 3.0
    assert ActivationManager.is_trial_active() is True
    # Ghi cả file lẫn registry
    assert json.loads(open(act_file, encoding="utf-8").read())["trial_start"] == pytest.approx(started)
    assert license_env[1]["value"] == pytest.approx(started)


def test_start_trial_refused_when_machine_already_used_it(monkeypatch):
    _server(monkeypatch, 200, {
        "allowed": False,
        "started_at": time.time() - 10 * 86400,
        "message": "Máy này đã dùng hết thời gian dùng thử.",
    })
    res = ActivationManager.start_trial()
    assert res["success"] is False
    assert ActivationManager.is_trial_active() is False


def test_deleting_cache_does_not_reset_trial(act_file, license_env):
    """Xoá activation.json vẫn còn mốc trong registry → hạn không lùi lại."""
    registry = license_env[1]
    registry["value"] = time.time() - 4 * 86400
    assert not __import__("os").path.exists(act_file)
    assert ActivationManager.is_trial_active() is False
    assert ActivationManager.is_trial_expired() is True


def test_trial_uses_earliest_known_start(act_file, license_env):
    """Sửa file để trial bắt đầu 'hôm nay' cũng vô ích nếu registry nhớ mốc cũ."""
    license_env[1]["value"] = time.time() - 5 * 86400
    _write_cache(act_file, trial_start=time.time())
    assert ActivationManager.is_trial_active() is False


def test_trial_days_remaining(act_file):
    _write_cache(act_file, trial_start=time.time() - 86400)
    days = ActivationManager.get_trial_days_remaining()
    assert 1.9 <= days <= 2.1


def test_needs_activation_during_trial(act_file):
    _write_cache(act_file, trial_start=time.time() - 86400)
    assert ActivationManager.needs_activation() is False


def test_needs_activation_after_trial(act_file):
    _write_cache(act_file, trial_start=time.time() - 4 * 86400)
    assert ActivationManager.needs_activation() is True
