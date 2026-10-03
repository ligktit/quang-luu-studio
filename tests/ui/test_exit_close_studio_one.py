"""Thoát app: đóng Studio One mà KHÔNG lưu.

Bản cũ gõ Ctrl+S trước khi đóng — chỉ là mẹo để Studio One khỏi hỏi, nhưng nó
bắt phải hiện cửa sổ Studio One lên (lộ chế độ khách) và ghi đè bài mẫu bằng
đúng bản khách vừa táy máy. Đây là bộ chốt chặn cho việc đã bỏ hẳn mẹo đó.
"""
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from frontend_qt import MainDashboard


@contextmanager
def _shutdown(has_template=True, song_path=r"C:\bai\mau.song", status="closed"):
    """Gọi MainDashboard._run_studio_one_shutdown với mọi thứ bên ngoài giả lập.

    Trả (self, kwargs) — kwargs là bộ tham số đã truyền cho hộp thoại đóng.
    """
    self = MagicMock()
    self.settings = {
        "studio_one_path": song_path,
        "studio_one_close_timeout": 45,
        "force_kill_studio_one": False,
    }
    self._has_song_template = lambda: MainDashboard._has_song_template(self)

    dlg = MagicMock()
    dlg.result_data = {"status": status, "saved": False}

    with patch("ui.dialogs.shutdown_dialog.StudioOneShutdownDialog",
               return_value=dlg) as Dlg, \
         patch("core.so_template.has_template", return_value=has_template), \
         patch("core.kiosk.is_locked", return_value=False), \
         patch("frontend_qt.QTimer"):
        MainDashboard._run_studio_one_shutdown(self)
        yield self, Dlg.call_args.kwargs


def test_thoat_app_khong_bao_gio_luu():
    with _shutdown() as (_, kwargs):
        assert kwargs["save"] is False


def test_co_ban_mau_thi_mo_nuoc_cuoi_luu_roi_dong():
    # Bản lưu ra đằng nào cũng bị bản mẫu chép đè ở lần khởi động sau → vô hại.
    with _shutdown(has_template=True) as (_, kwargs):
        assert kwargs["fallback_save"] is True


def test_chua_chot_ban_mau_thi_khong_duoc_luu():
    with _shutdown(has_template=False) as (_, kwargs):
        assert kwargs["fallback_save"] is False


def test_duong_dan_exe_thi_khong_duoc_luu():
    # Không phải file .song thì không có bản mẫu nào phục hồi được → lưu là mất
    # vĩnh viễn thiết lập của KTV.
    with _shutdown(song_path=r"C:\PreSonus\Studio One.exe") as (_, kwargs):
        assert kwargs["fallback_save"] is False


def test_khong_dong_duoc_thi_giau_lai_studio_one():
    # Hộp thoại hỏi lưu có thể đã kéo cửa sổ lên; app thoát mà để lộ Studio One
    # là hỏng chế độ khách.
    self = MagicMock()
    self.settings = {"studio_one_path": r"C:\bai\mau.song"}
    self._has_song_template = lambda: True
    dlg = MagicMock()
    dlg.result_data = {"status": "no_save_button", "saved": False}

    with patch("ui.dialogs.shutdown_dialog.StudioOneShutdownDialog", return_value=dlg), \
         patch("core.kiosk.is_locked", return_value=True), \
         patch("core.so_windows.hide_all") as hide, \
         patch("frontend_qt.QTimer"):
        MainDashboard._run_studio_one_shutdown(self)

    hide.assert_called_once()


def test_dong_sach_thi_khong_dung_toi_cua_so():
    self = MagicMock()
    self.settings = {"studio_one_path": r"C:\bai\mau.song"}
    self._has_song_template = lambda: True
    dlg = MagicMock()
    dlg.result_data = {"status": "closed", "saved": False}

    with patch("ui.dialogs.shutdown_dialog.StudioOneShutdownDialog", return_value=dlg), \
         patch("core.kiosk.is_locked", return_value=True), \
         patch("core.so_windows.hide_all") as hide, \
         patch("frontend_qt.QTimer"):
        MainDashboard._run_studio_one_shutdown(self)

    hide.assert_not_called()
