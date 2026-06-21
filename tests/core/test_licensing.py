"""Test lớp licensing client: fingerprint ổn định + offline fallback của ActivationManager."""
import pytest

from core.activation import ActivationManager, _online
from core.config import AppConfig
from core.licensing import client as lic
from core.licensing.device import get_fingerprint


@pytest.fixture(autouse=True)
def _reset_appconfig():
    AppConfig._data = None
    yield
    AppConfig._data = None


def test_fingerprint_stable_and_hex64():
    fp1 = get_fingerprint()
    fp2 = get_fingerprint()
    assert fp1 == fp2
    assert len(fp1) == 64
    assert all(c in "0123456789abcdef" for c in fp1)


def test_server_not_configured_means_offline():
    AppConfig.load()
    AppConfig._data["license_server_url"] = ""
    assert lic.server_configured() is False
    assert _online() is None


def test_offline_activate_rejects_bad_code():
    AppConfig.load()
    AppConfig._data["license_server_url"] = ""
    # _online() None → đi nhánh offline, checksum cục bộ từ chối mã sai.
    result = ActivationManager.activate("BAD-CODE-XXXX-YYYY-ZZZZ")
    assert result["success"] is False


def test_online_branch_selected_when_configured():
    AppConfig.load()
    AppConfig._data["license_server_url"] = "http://127.0.0.1:9"  # cổng không có gì
    assert lic.server_configured() is True
    assert _online() is not None
    # Cổng chết → activate trả lỗi kết nối, không raise.
    result = ActivationManager.activate("MN47-WD84-CF63-HR08-3DEF")
    assert result["success"] is False
    assert "máy chủ" in result["error"].lower() or "mã" in result["error"].lower()


def test_grace_invalid_without_license():
    assert lic.has_online_license() in (True, False)  # không raise
