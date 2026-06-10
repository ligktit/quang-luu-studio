import pytest
import time
import json
import hashlib
from unittest.mock import patch
from core.activation import ActivationManager

@pytest.fixture
def valid_code():
    base_code = "A1B2-C3D4-E5F6-G7H8"
    checksum_input = base_code + ActivationManager.SECRET_KEY
    calculated_checksum = hashlib.md5(checksum_input.encode()).hexdigest()[:4].upper()
    return f"{base_code}-{calculated_checksum}"

@pytest.fixture(autouse=True)
def mock_activation_file(tmp_path):
    act_file = tmp_path / "activation.json"
    with patch("core.activation.ACTIVATION_FILE", str(act_file)):
        yield act_file

# --- 6.1 Validation code ---

def test_validate_code_structure_correct():
    # A-01
    assert ActivationManager._validate_code_structure("A1B2-C3D4-E5F6-G7H8-1A2B") is True

def test_validate_code_structure_missing_segment():
    # A-02
    assert ActivationManager._validate_code_structure("ABCD-EFGH-IJKL-MNOP") is False

def test_validate_code_structure_wrong_length():
    # A-03
    assert ActivationManager._validate_code_structure("ABC-EFGH-IJKL-MNOP-QRST") is False

def test_validate_code_structure_special_char():
    # A-04
    assert ActivationManager._validate_code_structure("ABCD-EFG!-IJKL-MNOP-QRST") is False

def test_verify_code_checksum_correct(valid_code):
    # A-05
    assert ActivationManager._verify_code_checksum(valid_code) is True

def test_verify_code_checksum_incorrect(valid_code):
    # A-06
    wrong_code = valid_code[:-1] + ("0" if valid_code[-1] != "0" else "1")
    assert ActivationManager._verify_code_checksum(wrong_code) is False

# --- 6.2 Activation lifecycle ---

def test_is_activated_no_file(mock_activation_file):
    # A-07
    assert ActivationManager.is_activated() is False

def test_is_activated_after_activate(valid_code):
    # A-08
    ActivationManager.activate(valid_code)
    assert ActivationManager.is_activated() is True

def test_is_expired_new_license(valid_code):
    # A-09
    ActivationManager.activate(valid_code)
    assert ActivationManager.is_expired() is False

def test_is_expired_old_license(valid_code, mock_activation_file):
    # A-10
    ActivationManager.activate(valid_code)
    # Edit the file to make it 366 days old
    data = json.loads(mock_activation_file.read_text(encoding="utf-8"))
    data["activation_timestamp"] = time.time() - (366 * 86400)
    mock_activation_file.write_text(json.dumps(data), encoding="utf-8")
    assert ActivationManager.is_expired() is True

def test_get_days_remaining(valid_code, mock_activation_file):
    # A-11
    ActivationManager.activate(valid_code)
    data = json.loads(mock_activation_file.read_text(encoding="utf-8"))
    # Make it 265 days old -> 100 days remaining
    data["activation_timestamp"] = time.time() - (265 * 86400)
    mock_activation_file.write_text(json.dumps(data), encoding="utf-8")
    days = ActivationManager.get_days_remaining()
    assert 99 <= days <= 101

def test_activate_valid_code(valid_code):
    # A-12
    res = ActivationManager.activate(valid_code)
    assert res["success"] is True

def test_activate_invalid_code():
    # A-13
    res = ActivationManager.activate("INVALID-CODE")
    assert res["success"] is False

# --- 6.3 Trial period ---

def test_start_trial(mock_activation_file):
    # A-14
    res = ActivationManager.start_trial()
    assert res["success"] is True
    assert res["days_remaining"] == 3
    
    data = json.loads(mock_activation_file.read_text(encoding="utf-8"))
    assert "trial_start" in data

def test_is_trial_active(mock_activation_file):
    # A-15
    ActivationManager.start_trial()
    data = json.loads(mock_activation_file.read_text(encoding="utf-8"))
    data["trial_start"] = time.time() - (2 * 86400) # 2 days ago (còn trong hạn trial 3 ngày)
    mock_activation_file.write_text(json.dumps(data), encoding="utf-8")
    
    assert ActivationManager.is_trial_active() is True

def test_is_trial_expired(mock_activation_file):
    # A-16
    ActivationManager.start_trial()
    data = json.loads(mock_activation_file.read_text(encoding="utf-8"))
    data["trial_start"] = time.time() - (4 * 86400) # 4 days ago
    mock_activation_file.write_text(json.dumps(data), encoding="utf-8")
    
    assert ActivationManager.is_trial_expired() is True

def test_get_trial_days_remaining(mock_activation_file):
    # A-17
    ActivationManager.start_trial()
    data = json.loads(mock_activation_file.read_text(encoding="utf-8"))
    data["trial_start"] = time.time() - (1 * 86400) # 1 day ago
    mock_activation_file.write_text(json.dumps(data), encoding="utf-8")
    
    days = ActivationManager.get_trial_days_remaining()
    assert 1 <= days <= 3  # ~2 days

def test_needs_activation_trial_expired(mock_activation_file):
    # A-18
    ActivationManager.start_trial()
    data = json.loads(mock_activation_file.read_text(encoding="utf-8"))
    data["trial_start"] = time.time() - (4 * 86400) # 4 days ago
    mock_activation_file.write_text(json.dumps(data), encoding="utf-8")
    
    assert ActivationManager.needs_activation() is True

def test_needs_activation_trial_active(mock_activation_file):
    # A-19
    ActivationManager.start_trial()
    data = json.loads(mock_activation_file.read_text(encoding="utf-8"))
    data["trial_start"] = time.time() - (1 * 86400) # 1 day ago
    mock_activation_file.write_text(json.dumps(data), encoding="utf-8")
    
    assert ActivationManager.needs_activation() is False
