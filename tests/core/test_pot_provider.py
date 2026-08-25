"""Test cho core/pot_provider.py — bộ sinh PO Token tải lúc chạy.

Không lần nào chạm mạng: mọi lượt tải đều bị thay bằng payload dựng sẵn.
"""
import io
import os
import json
import hashlib
import zipfile

import pytest

from core import pot_provider


def _plugin_zip(include_marker=True):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        if include_marker:
            archive.writestr("yt_dlp_plugins/extractor/getpot_bgutil.py", "# stub\n")
            archive.writestr("yt_dlp_plugins/extractor/getpot_bgutil_cli.py", "# stub\n")
        else:
            archive.writestr("yt_dlp_plugins/extractor/khong_lien_quan.py", "# stub\n")
    return buffer.getvalue()


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Trỏ mọi đường dẫn của module vào thư mục tạm."""
    pot_dir = tmp_path / "pot"
    monkeypatch.setattr(pot_provider, "POT_DIR", str(pot_dir))
    monkeypatch.setattr(pot_provider, "BINARY_PATH", str(pot_dir / "bgutil-pot.exe"))
    monkeypatch.setattr(pot_provider, "PLUGIN_DIR", str(pot_dir / "plugins"))
    monkeypatch.setattr(pot_provider, "_PLUGIN_PKG_DIR", str(pot_dir / "plugins" / "bgutil"))
    monkeypatch.setattr(pot_provider, "STAMP_FILE", str(tmp_path / "pot_provider.json"))
    return tmp_path


def _fake_downloads(monkeypatch, plugin_payload, binary_payload):
    """Thay _download bằng bản trả payload dựng sẵn, VẪN kiểm sha256 thật."""
    def fake(url, expected_sha256, timeout):
        payload = plugin_payload if url == pot_provider.PLUGIN_URL else binary_payload
        digest = hashlib.sha256(payload).hexdigest()
        if digest != expected_sha256:
            return None
        return payload

    monkeypatch.setattr(pot_provider, "_download", fake)


def _pin_hashes(monkeypatch, plugin_payload, binary_payload):
    monkeypatch.setattr(pot_provider, "PLUGIN_SHA256",
                        hashlib.sha256(plugin_payload).hexdigest())
    monkeypatch.setattr(pot_provider, "BINARY_SHA256",
                        hashlib.sha256(binary_payload).hexdigest())


# ── Cài đặt ──────────────────────────────────────────────────────────────────

def test_install_lays_out_dirs_yt_dlp_can_find(sandbox, monkeypatch):
    """Bố cục PHẢI có tầng `bgutil/` trung gian: yt-dlp duyệt thư mục CON của
    đường dẫn plugin rồi mới tìm `yt_dlp_plugins/` bên trong."""
    plugin, binary = _plugin_zip(), b"MZ fake exe"
    _pin_hashes(monkeypatch, plugin, binary)
    _fake_downloads(monkeypatch, plugin, binary)

    assert pot_provider.install() is True
    assert pot_provider.is_available() is True
    assert os.path.isfile(os.path.join(
        pot_provider._PLUGIN_PKG_DIR, "yt_dlp_plugins", "extractor", "getpot_bgutil.py"))
    assert pot_provider.plugin_dir() == pot_provider.PLUGIN_DIR
    assert pot_provider.installed_version() == pot_provider.POT_VERSION


def test_install_is_idempotent(sandbox, monkeypatch):
    plugin, binary = _plugin_zip(), b"MZ fake exe"
    _pin_hashes(monkeypatch, plugin, binary)

    calls = []

    def counting(url, expected_sha256, timeout):
        calls.append(url)
        return plugin if url == pot_provider.PLUGIN_URL else binary

    monkeypatch.setattr(pot_provider, "_download", counting)
    assert pot_provider.install() is True
    assert len(calls) == 2
    assert pot_provider.install() is True
    assert len(calls) == 2      # lần hai không tải lại gì


def test_bad_binary_hash_leaves_nothing_usable(sandbox, monkeypatch):
    """Sai mã băm → tuyệt đối không được ghi binary ra đĩa."""
    plugin, binary = _plugin_zip(), b"MZ fake exe"
    _pin_hashes(monkeypatch, plugin, binary)
    monkeypatch.setattr(pot_provider, "BINARY_SHA256", "0" * 64)
    _fake_downloads(monkeypatch, plugin, binary)

    assert pot_provider.install() is False
    assert pot_provider.cli_path() is None
    assert pot_provider.is_available() is False
    assert pot_provider.installed_version() is None


def test_incomplete_plugin_zip_is_rejected(sandbox, monkeypatch):
    plugin, binary = _plugin_zip(include_marker=False), b"MZ fake exe"
    _pin_hashes(monkeypatch, plugin, binary)
    _fake_downloads(monkeypatch, plugin, binary)

    assert pot_provider.install() is False
    assert pot_provider.plugin_dir() is None


def test_broken_zip_keeps_previous_copy(sandbox, monkeypatch):
    """Bản cũ đang chạy tốt không được mất vì một lần tải hỏng."""
    plugin, binary = _plugin_zip(), b"MZ fake exe"
    _pin_hashes(monkeypatch, plugin, binary)
    _fake_downloads(monkeypatch, plugin, binary)
    assert pot_provider.install() is True

    monkeypatch.setattr(pot_provider, "POT_VERSION", "9.9.9")
    broken = b"khong phai zip"
    _pin_hashes(monkeypatch, broken, binary)
    _fake_downloads(monkeypatch, broken, binary)

    assert pot_provider.install() is True     # vẫn dùng được bản cũ
    assert pot_provider.is_available() is True


# ── Bật/tắt + lịch tự tải ────────────────────────────────────────────────────

def test_disabled_in_config_hides_everything(sandbox, monkeypatch):
    plugin, binary = _plugin_zip(), b"MZ fake exe"
    _pin_hashes(monkeypatch, plugin, binary)
    _fake_downloads(monkeypatch, plugin, binary)
    assert pot_provider.install() is True

    monkeypatch.setattr(pot_provider.AppConfig, "get",
                        staticmethod(lambda key, default=None:
                                     False if key == "youtube_pot_enabled" else default))
    assert pot_provider.cli_path() is None
    assert pot_provider.plugin_dir() is None
    assert pot_provider.is_available() is False
    assert pot_provider.should_install_now() is False


def test_should_install_now_respects_retry_window(sandbox, monkeypatch):
    monkeypatch.setattr(pot_provider.AppConfig, "get",
                        staticmethod(lambda key, default=None: True))
    # Máy mới tinh (chưa có stamp) → cài ngay
    assert pot_provider.should_install_now() is True

    with open(pot_provider.STAMP_FILE, "w", encoding="utf-8") as handle:
        json.dump({"last_check": 1000}, handle)
    assert pot_provider.should_install_now(now=1000 + 60) is False
    assert pot_provider.should_install_now(
        now=1000 + pot_provider.RETRY_INTERVAL_SEC) is True


def test_maybe_auto_install_stamps_before_download(sandbox, monkeypatch):
    """Mạng hỏng không được gây thử lại liên tục mỗi lần mở app."""
    monkeypatch.setattr(pot_provider.AppConfig, "get",
                        staticmethod(lambda key, default=None: True))

    def exploding(timeout=None):
        raise RuntimeError("mat mang")

    monkeypatch.setattr(pot_provider, "install", exploding)
    assert pot_provider.maybe_auto_install() is False
    assert pot_provider._read_stamp().get("last_check")
