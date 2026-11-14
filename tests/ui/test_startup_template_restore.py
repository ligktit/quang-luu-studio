"""Khởi động: Studio One còn sót lại của phiên trước phải bị đóng trước khi
chép bản mẫu .song, nếu không bản mẫu mất tác dụng cả buổi."""
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from frontend_qt import MainDashboard


@contextmanager
def _startup(so_running, has_template=True, song_path=r"C:\bai\mau.song",
             auto_launch=False, close_ok=True, restored=True, restore_tpl=True,
             auto_hide=False):
    """Gọi MainDashboard._auto_launch_apps với mọi thứ bên ngoài đã bị giả lập."""
    self = MagicMock()
    self.settings = {
        "studio_one_path": song_path,
        "auto_launch_studio_one": auto_launch,
        "auto_launch_browser": False,
    }
    self._close_studio_one_for_restore.return_value = close_ok

    with patch("core.daw_visibility.restore_template_enabled", return_value=restore_tpl), \
         patch("core.daw_visibility.auto_hide", return_value=auto_hide), \
         patch("core.so_windows.is_running", return_value=so_running), \
         patch("core.so_windows.hide_all") as hide_all, \
         patch("core.so_windows.hide_when_ready") as hide_when_ready, \
         patch("core.so_template.has_template", return_value=has_template), \
         patch("core.so_template.restore",
               return_value={"restored": restored, "reason": ""}) as restore, \
         patch("os.path.exists", return_value=True):
        MainDashboard._auto_launch_apps(self)
        self.hide_all, self.hide_when_ready = hide_all, hide_when_ready
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


# ── Tự ẩn DAW khi mở app (thay khoá kỹ thuật) ────────────────────────────────

def test_tu_an_bat_thi_an_khi_daw_dang_chay():
    with _startup(so_running=True, restore_tpl=False, auto_hide=True) as (self, _):
        # Tự ẩn (không phải KTV bấm) → để nguyên hộp thoại DAW đang chờ trả lời.
        self.hide_all.assert_called_once_with(keep_dialogs=True)
        self.hide_when_ready.assert_not_called()


def test_tu_an_tat_thi_khong_an():
    with _startup(so_running=True, restore_tpl=False, auto_hide=False) as (self, _):
        self.hide_all.assert_not_called()
        self.hide_when_ready.assert_not_called()


def test_vua_khoi_chay_thi_an_khi_san_sang():
    with _startup(so_running=False, restore_tpl=False, auto_launch=True,
                  auto_hide=True) as (self, _):
        self.engine.launch_app.assert_called_once()
        self.hide_when_ready.assert_called_once()


def test_tat_phuc_hoi_ban_mau_thi_khong_phuc_hoi():
    with _startup(so_running=False, restore_tpl=False) as (self, restore):
        restore.assert_not_called()

