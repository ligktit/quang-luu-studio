"""Khởi động: Studio One còn sót lại của phiên trước phải bị đóng trước khi
chép bản mẫu .song, nếu không bản mẫu mất tác dụng cả buổi."""
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from frontend_qt import MainDashboard


@contextmanager
def _startup(so_running, has_template=True, song_path=r"C:\bai\mau.song",
             auto_launch=False, close_ok=True, restored=True):
    """Gọi MainDashboard._auto_launch_apps với mọi thứ bên ngoài đã bị giả lập."""
    self = MagicMock()
    self.settings = {
        "studio_one_path": song_path,
        "auto_launch_studio_one": auto_launch,
        "auto_launch_browser": False,
    }
    self._close_studio_one_for_restore.return_value = close_ok

    with patch("core.kiosk.is_enabled", return_value=True), \
         patch("core.kiosk.restore_template_enabled", return_value=True), \
         patch("core.kiosk.is_locked", return_value=False), \
         patch("core.so_windows.is_running", return_value=so_running), \
         patch("core.so_template.has_template", return_value=has_template), \
         patch("core.so_template.restore",
               return_value={"restored": restored, "reason": ""}) as restore, \
         patch("os.path.exists", return_value=True):
        MainDashboard._auto_launch_apps(self)
        yield self, restore


def test_studio_one_con_chay_thi_dong_truoc_roi_phuc_hoi():
    with _startup(so_running=True) as (self, restore):
        self._close_studio_one_for_restore.assert_called_once()
        restore.assert_called_once()


def test_dong_xong_thi_mo_lai_du_tat_auto_launch():
    with _startup(so_running=True, auto_launch=False) as (self, _):
        self.engine.launch_app.assert_called_once_with(r"C:\bai\mau.song")


def test_khong_dong_duoc_thi_khong_mo_lai():
    with _startup(so_running=True, auto_launch=False, close_ok=False) as (self, _):
        self.engine.launch_app.assert_not_called()


def test_studio_one_khong_chay_thi_khong_dong_gi_ca():
    with _startup(so_running=False) as (self, restore):
        self._close_studio_one_for_restore.assert_not_called()
        restore.assert_called_once()


def test_duong_dan_exe_thi_khong_dong_studio_one():
    with _startup(so_running=True, song_path=r"C:\PreSonus\Studio One.exe") as (self, _):
        self._close_studio_one_for_restore.assert_not_called()


def test_chua_chot_ban_mau_thi_khong_dong_studio_one():
    with _startup(so_running=True, has_template=False) as (self, _):
        self._close_studio_one_for_restore.assert_not_called()
