"""Kiểm thử core.kiosk — khoá kỹ thuật (chế độ khách)."""
import pytest

from core import kiosk


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    """Gắn kiosk vào dict trong RAM và chặn mọi lần ghi xuống đĩa thật."""
    live = {}
    kiosk.bind(live)
    kiosk.end_session()
    kiosk.reset_failures()

    def _fake_write(**patch):
        cfg = dict(live.get("tech_lock") or {})
        cfg.update(patch)
        live["tech_lock"] = cfg
        return cfg

    monkeypatch.setattr(kiosk, "_write", _fake_write)
    yield live
    kiosk.bind(None)
    kiosk.end_session()
    kiosk.reset_failures()


# ── PIN ──────────────────────────────────────────────────────────────────────

def test_pin_chua_dat():
    assert kiosk.has_pin() is False
    assert kiosk.verify_pin("1234") is False


def test_dat_pin_va_xac_minh(isolated_settings):
    kiosk.set_pin("2468")
    assert kiosk.has_pin() is True
    assert kiosk.verify_pin("2468") is True
    assert kiosk.verify_pin("2469") is False
    # PIN thô không bao giờ được lưu lại
    assert "2468" not in str(isolated_settings)


def test_pin_qua_ngan_bi_tu_choi():
    with pytest.raises(ValueError):
        kiosk.set_pin("12")
    assert kiosk.has_pin() is False


def test_doi_pin_lam_pin_cu_het_hieu_luc():
    kiosk.set_pin("1111")
    kiosk.set_pin("2222")
    assert kiosk.verify_pin("1111") is False
    assert kiosk.verify_pin("2222") is True


def test_moi_lan_dat_pin_dung_salt_khac(isolated_settings):
    kiosk.set_pin("1234")
    first = dict(isolated_settings["tech_lock"])
    kiosk.set_pin("1234")
    second = isolated_settings["tech_lock"]
    assert first["pin_salt"] != second["pin_salt"]
    assert first["pin_hash"] != second["pin_hash"]


# ── Bật/tắt khoá ─────────────────────────────────────────────────────────────

def test_khong_bat_duoc_khoa_khi_chua_co_pin():
    with pytest.raises(ValueError):
        kiosk.enable()
    assert kiosk.is_enabled() is False


def test_bat_khoa_thi_is_locked():
    kiosk.set_pin("1234")
    kiosk.enable()
    assert kiosk.is_enabled() is True
    assert kiosk.is_locked() is True


def test_tat_khoa_thi_khong_con_locked():
    kiosk.set_pin("1234")
    kiosk.enable()
    kiosk.disable()
    assert kiosk.is_locked() is False


# ── Phiên kỹ thuật ───────────────────────────────────────────────────────────

def test_phien_ky_thuat_mo_khoa_tam_thoi():
    kiosk.set_pin("1234")
    kiosk.enable()
    kiosk.start_session(minutes=5)
    assert kiosk.session_active() is True
    assert kiosk.is_locked() is False
    assert 0 < kiosk.session_remaining() <= 300


def test_het_phien_thi_khoa_lai(monkeypatch):
    kiosk.set_pin("1234")
    kiosk.enable()
    kiosk.start_session(minutes=1)
    # Nhảy thời gian tới sau khi phiên hết hạn
    now = kiosk.time.monotonic()
    monkeypatch.setattr(kiosk.time, "monotonic", lambda: now + 61)
    assert kiosk.session_active() is False
    assert kiosk.is_locked() is True


def test_end_session_khoa_lai_ngay():
    kiosk.set_pin("1234")
    kiosk.enable()
    kiosk.start_session()
    kiosk.end_session()
    assert kiosk.is_locked() is True


def test_bat_khoa_dong_luon_phien_dang_mo():
    kiosk.set_pin("1234")
    kiosk.enable()
    kiosk.start_session()
    kiosk.enable()
    assert kiosk.session_active() is False


# ── Chống dò PIN ─────────────────────────────────────────────────────────────

def test_sai_it_lan_chua_bi_khoa():
    for _ in range(4):
        assert kiosk.register_failure() == 0
    assert kiosk.lockout_remaining() == 0


def test_sai_du_nguong_thi_bi_khoa_tam():
    for _ in range(5):
        cooldown = kiosk.register_failure()
    assert cooldown == 60
    assert kiosk.lockout_remaining() > 0


def test_khoa_tam_tang_gap_doi():
    for _ in range(10):
        cooldown = kiosk.register_failure()
    assert cooldown == 120


def test_mo_phien_thanh_cong_xoa_bo_dem_sai():
    kiosk.set_pin("1234")
    for _ in range(5):
        kiosk.register_failure()
    kiosk.start_session()
    assert kiosk.lockout_remaining() == 0


# ── Tuỳ chọn ─────────────────────────────────────────────────────────────────

def test_mac_dinh_cac_tuy_chon():
    assert kiosk.keep_hidden() is False          # watchdog tắt sẵn
    assert kiosk.restore_template_enabled() is True
    assert kiosk.session_minutes() == 20


def test_luu_tuy_chon():
    kiosk.set_keep_hidden(True)
    kiosk.set_restore_template(False)
    kiosk.set_session_minutes(45)
    assert kiosk.keep_hidden() is True
    assert kiosk.restore_template_enabled() is False
    assert kiosk.session_minutes() == 45


def test_cau_hinh_hong_khong_lam_crash(isolated_settings):
    isolated_settings["tech_lock"] = "không phải dict"
    assert kiosk.is_enabled() is False
    assert kiosk.is_locked() is False
    assert kiosk.has_pin() is False
