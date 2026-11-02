"""Kiểm thử core.daw_visibility — tự ẩn DAW khi mở app + phục hồi bản mẫu."""
import pytest

from core import daw_visibility


@pytest.fixture
def isolated_settings(monkeypatch):
    """Gắn module vào dict trong RAM và chặn mọi lần ghi xuống đĩa thật."""
    live = {}
    daw_visibility.bind(live)

    def _fake_write(**patch):
        cfg = live.get("daw_windows")
        cfg = dict(cfg) if isinstance(cfg, dict) else {}
        cfg.update(patch)
        live["daw_windows"] = cfg
        return cfg

    monkeypatch.setattr(daw_visibility, "_write", _fake_write)
    yield live
    daw_visibility.bind(None)


def test_mac_dinh_khi_chua_co_cau_hinh(isolated_settings):
    assert daw_visibility.auto_hide() is True
    assert daw_visibility.restore_template_enabled() is False


def test_ghi_va_doc_lai(isolated_settings):
    daw_visibility.set_auto_hide(False)
    daw_visibility.set_restore_template(True)
    assert daw_visibility.auto_hide() is False
    assert daw_visibility.restore_template_enabled() is True


@pytest.mark.parametrize("old, want_restore", [
    ({"enabled": True, "pin_hash": "ab", "pin_salt": "cd"}, True),
    ({"enabled": True, "restore_template": False}, False),
    ({"enabled": False, "restore_template": True}, False),
    ("không phải dict", False),
])
def test_migrate_tu_tech_lock(old, want_restore):
    s = {"tech_lock": old}
    assert daw_visibility.migrate(s) is True
    assert "tech_lock" not in s
    assert s["daw_windows"] == {"auto_hide": True, "restore_template": want_restore}


def test_migrate_khong_dong_khi_da_co_cau_hinh_moi():
    s = {"daw_windows": {"auto_hide": False, "restore_template": True}}
    assert daw_visibility.migrate(s) is False
    assert s["daw_windows"] == {"auto_hide": False, "restore_template": True}


def test_migrate_co_ca_hai_thi_chi_xoa_tech_lock():
    s = {"daw_windows": {"auto_hide": False, "restore_template": False},
         "tech_lock": {"enabled": True}}
    assert daw_visibility.migrate(s) is True
    assert "tech_lock" not in s
    assert s["daw_windows"] == {"auto_hide": False, "restore_template": False}


def test_migrate_may_moi_khong_co_gi():
    s = {}
    assert daw_visibility.migrate(s) is True
    assert s["daw_windows"] == {"auto_hide": True, "restore_template": False}


def test_daw_windows_hong_thi_dung_mac_dinh(isolated_settings):
    isolated_settings["daw_windows"] = "rác"
    assert daw_visibility.auto_hide() is True
    assert daw_visibility.restore_template_enabled() is False
