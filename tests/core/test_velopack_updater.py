"""Cập nhật ngầm qua Velopack: kiểm → tải sẵn → áp dụng khi tắt app. Manager giả, không mạng."""
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.updater import velopack_updater as vu

FP = "a" * 64
BASE = "https://qlstudio.duckdns.org"


class FakeManager:
    def __init__(self, target=None, pending=None, check_exc=None, download_exc=None):
        self.target, self.pending = target, pending
        self.check_exc, self.download_exc = check_exc, download_exc
        self.downloaded, self.applied = [], []

    def check_for_updates(self):
        if self.check_exc:
            raise self.check_exc
        if self.target is None:
            return None
        return SimpleNamespace(TargetFullRelease=SimpleNamespace(Version=self.target))

    def download_updates(self, info, progress_callback=None):
        if self.download_exc:
            raise self.download_exc
        self.downloaded.append(info.TargetFullRelease.Version)
        self.pending = info.TargetFullRelease.Version

    def get_update_pending_restart(self):
        return None if self.pending is None else SimpleNamespace(Version=self.pending)

    def wait_exit_then_apply_updates(self, asset, silent=False, restart=True, restart_args=None):
        self.applied.append((asset.Version, silent, restart))


def _updater(mgr, auto=True):
    calls = []

    def factory(url, timeout_ms):
        calls.append((url, timeout_ms))
        return mgr
    u = vu.BackgroundUpdater(f"{BASE}/api/v1/updates/velopack/{FP}", lambda: auto,
                             manager_factory=factory, clock=lambda: 1000.0)
    return u, calls


# ── feed_url ──
def test_feed_url_dung_dinh_dang():
    assert vu.feed_url(BASE + "/", FP) == f"{BASE}/api/v1/updates/velopack/{FP}"


@pytest.mark.parametrize("base,fp", [("", FP), ("  ", FP), (BASE, ""), (BASE, "a b"), (BASE, "../x"), (BASE, "a" * 129)])
def test_feed_url_khong_hop_le_tra_none(base, fp):
    assert vu.feed_url(base, fp) is None


# ── check_once ──
def test_co_ban_moi_thi_tai_san():
    mgr = FakeManager(target="1.9.1")
    u, calls = _updater(mgr)
    u.check_once()
    assert mgr.downloaded == ["1.9.1"]
    assert u.state.pending == "1.9.1" and u.state.downloading is None
    assert u.state.checked_at == 1000.0 and u.state.error is False
    # hỏi feed bằng timeout ngắn, tải bằng timeout dài
    assert calls[0][1] == vu.CHECK_TIMEOUT_MS and calls[-1][1] == vu.DOWNLOAD_TIMEOUT_MS


def test_khong_co_ban_moi_khong_tai():
    mgr = FakeManager(target=None)
    u, _ = _updater(mgr)
    u.check_once()
    assert mgr.downloaded == [] and u.state.pending is None and u.state.checked_at == 1000.0


def test_ban_da_tai_san_khong_tai_lai():
    mgr = FakeManager(target="1.9.1", pending="1.9.1")
    u, _ = _updater(mgr)
    u.check_once()
    u.check_once()
    assert mgr.downloaded == [] and u.state.pending == "1.9.1"


def test_loi_mang_danh_dau_va_thu_lai():
    mgr = FakeManager(target="1.9.1", check_exc=OSError("timeout"))
    u, _ = _updater(mgr)
    u.check_once()   # không ném
    assert u.state.error is True and u.state.pending is None
    mgr.check_exc = None
    u.check_once()
    assert u.state.error is False and u.state.pending == "1.9.1"


def test_loi_khi_tai_khong_ghi_pending():
    mgr = FakeManager(target="1.9.1", download_exc=OSError("đứt mạng"))
    u, _ = _updater(mgr)
    u.check_once()
    assert u.state.pending is None and u.state.downloading is None and u.state.error is True


def test_hai_luot_cung_luc_chi_mot_luot_chay():
    mgr = FakeManager(target="1.9.1")
    u, _ = _updater(mgr)
    u._lock.acquire()
    try:
        u.check_once()   # lượt khác đang chạy → bỏ qua ngay, không chờ
    finally:
        u._lock.release()
    assert mgr.downloaded == []


# ── run: lịch 60 s rồi 6 giờ, tôn trọng auto_check ──
def test_lich_kiem_tra_va_auto_check():
    mgr = FakeManager(target=None)
    waits = []
    flags = iter([True, False, True])

    def fake_wait(seconds):
        waits.append(seconds)
        return len(waits) > 3          # dừng sau lần chờ thứ 4

    u = vu.BackgroundUpdater("u", lambda: next(flags), manager_factory=lambda *_: mgr, wait=fake_wait)
    with patch.object(u, "check_once", wraps=u.check_once) as chk:
        u.run()
    assert waits == [vu.CHECK_DELAY_S, vu.CHECK_INTERVAL_S, vu.CHECK_INTERVAL_S, vu.CHECK_INTERVAL_S]
    assert chk.call_count == 2         # lượt 2 bị auto_check=False bỏ qua


# ── apply_on_exit ──
def test_ap_dung_khi_thoat_co_ban_cho():
    mgr = FakeManager(pending="1.9.1")
    u, _ = _updater(mgr)
    assert u.apply_on_exit() is True
    assert mgr.applied == [("1.9.1", True, False)]


def test_ap_dung_khi_thoat_khong_co_ban_cho_khong_lam_gi():
    mgr = FakeManager(pending=None)
    u, _ = _updater(mgr)
    assert u.apply_on_exit() is False and mgr.applied == []


def test_ap_dung_khi_thoat_loi_khong_nem():
    mgr = FakeManager(pending="1.9.1")
    mgr.wait_exit_then_apply_updates = lambda *a, **k: (_ for _ in ()).throw(OSError("x"))
    u, _ = _updater(mgr)
    assert u.apply_on_exit() is False


# ── start_background_updates / apply_pending_on_exit ──
def test_khong_phai_velopack_khong_chay(tmp_path):
    with patch.object(vu, "_updater", None):
        assert vu.start_background_updates(str(tmp_path), BASE, FP, lambda: True,
                                           manager_factory=lambda *_: FakeManager()) is None
        assert vu.get_updater() is None
        assert vu.apply_pending_on_exit() is False


def test_ban_velopack_khoi_dong_luong(tmp_path):
    cur = tmp_path / "QuangLuuStudio" / "current"
    cur.mkdir(parents=True)
    (tmp_path / "QuangLuuStudio" / "Update.exe").write_bytes(b"MZ")
    started = []
    with patch.object(vu, "_updater", None), \
         patch.object(vu.threading, "Thread",
                      side_effect=lambda **kw: SimpleNamespace(start=lambda: started.append(kw["name"]))):
        u = vu.start_background_updates(str(cur), BASE, FP, lambda: True,
                                        manager_factory=lambda *_: FakeManager())
        assert u is vu.get_updater() and u is not None
    assert started == ["velopack-update"]


def test_ban_velopack_thieu_url_khong_chay(tmp_path):
    cur = tmp_path / "QuangLuuStudio" / "current"
    cur.mkdir(parents=True)
    (tmp_path / "QuangLuuStudio" / "Update.exe").write_bytes(b"MZ")
    with patch.object(vu, "_updater", None):
        assert vu.start_background_updates(str(cur), "", FP, lambda: True) is None


# ── status_text ──
def test_status_text_cac_truong_hop():
    assert "không tự cập nhật" in vu.status_text("1.9.0", None)
    u, _ = _updater(FakeManager())
    assert "khoảng 1 phút" in vu.status_text("1.9.0", u)
    u.state.checked_at = 0.0
    assert "đã là bản mới nhất" in vu.status_text("1.9.0", u)
    u.state.error = True
    assert "chưa kết nối được" in vu.status_text("1.9.0", u)
    assert "đang tắt" in vu.status_text("1.9.0", u, auto_check=False)
    u.state.downloading = "1.9.1"
    assert "đang tải bản 1.9.1" in vu.status_text("1.9.0", u)
    u.state.pending = "1.9.1"
    assert vu.status_text("1.9.0", u) == "Đang dùng 1.9.0 — đã tải sẵn 1.9.1, sẽ dùng ở lần mở sau."
