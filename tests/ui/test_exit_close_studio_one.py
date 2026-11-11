"""Thoát app: cửa sổ app biến mất ngay, DAW được đóng ngầm mà KHÔNG lưu.

Bản cũ gõ Ctrl+S trước khi đóng — chỉ là mẹo để Studio One khỏi hỏi, nhưng nó
bắt phải hiện cửa sổ Studio One lên (lộ chế độ khách) và ghi đè bài mẫu bằng
đúng bản khách vừa táy máy. Đây là bộ chốt chặn cho việc đã bỏ hẳn mẹo đó.

Từ 2026-11-10 việc đóng DAW không còn hộp thoại tiến trình trước mặt khách: bấm X
là app tàng hình, tiến trình sống tiếp tới khi DAW thoát (khách thấy tắt tức thì).
"""
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from frontend_qt import MainDashboard


@contextmanager
def _start(has_template=True, song_path=r"C:\bai\mau.song"):
    """Gọi MainDashboard._start_hidden_daw_shutdown với mọi thứ bên ngoài giả lập.

    Trả (self, kwargs, mark) — kwargs là bộ tham số đã truyền cho luồng đóng DAW.
    """
    self = MagicMock()
    self.settings = {
        "studio_one_path": song_path,
        "studio_one_close_timeout": 45,
        "force_kill_studio_one": False,
    }
    self._has_song_template = lambda: MainDashboard._has_song_template(self)

    with patch("ui.dialogs.shutdown_dialog._CloseWorker") as Worker, \
         patch("ui.dialogs.shutdown_dialog.StudioOneShutdownDialog") as Dlg, \
         patch("core.instance_guard.mark_closing") as mark, \
         patch("core.so_template.has_template", return_value=has_template):
        MainDashboard._start_hidden_daw_shutdown(self)
        Dlg.assert_not_called()
        Worker.return_value.start.assert_called_once()
        yield self, Worker.call_args.kwargs, mark


def test_thoat_app_khong_bao_gio_luu():
    with _start() as (_, kwargs, _m):
        assert kwargs["save"] is False


def test_khong_hien_hop_thoai_va_danh_dau_dang_dong():
    # Bản mở lại trong lúc này phải biết mà chờ — xem instance_guard.wait_previous_closing.
    with _start() as (_, _k, mark):
        mark.assert_called_once()


def test_co_ban_mau_thi_mo_nuoc_cuoi_luu_roi_dong():
    # Bản lưu ra đằng nào cũng bị bản mẫu chép đè ở lần khởi động sau → vô hại.
    with _start(has_template=True) as (_, kwargs, _m):
        assert kwargs["fallback_save"] is True


def test_chua_chot_ban_mau_thi_khong_duoc_luu():
    with _start(has_template=False) as (_, kwargs, _m):
        assert kwargs["fallback_save"] is False


def test_duong_dan_exe_thi_khong_duoc_luu():
    # Không phải file .song thì không có bản mẫu nào phục hồi được → lưu là mất
    # vĩnh viễn thiết lập của KTV.
    with _start(song_path=r"C:\PreSonus\Studio One.exe") as (_, kwargs, _m):
        assert kwargs["fallback_save"] is False


@contextmanager
def _done(status, auto_hide=True):
    self = MagicMock()
    self._daw_close_t0 = 0.0
    with patch("core.daw_visibility.auto_hide", return_value=auto_hide), \
         patch("core.so_windows.hide_all") as hide, \
         patch("core.instance_guard.clear_closing") as clear, \
         patch("frontend_qt.QTimer") as timer:
        MainDashboard._on_hidden_daw_shutdown_done(self, {"status": status, "saved": False})
        yield self, hide, clear, timer


def test_khong_dong_duoc_thi_giau_lai_studio_one():
    # Hộp thoại hỏi lưu có thể đã kéo cửa sổ lên; app thoát mà để lộ Studio One
    # là hỏng chế độ khách.
    with _done("no_save_button") as (_, hide, _c, _t):
        hide.assert_called_once()


def test_tu_an_tat_khi_thoat_thi_khong_giau():
    with _done("no_save_button", auto_hide=False) as (_, hide, _c, _t):
        hide.assert_not_called()


def test_dong_sach_thi_khong_dung_toi_cua_so():
    with _done("closed") as (_, hide, _c, _t):
        hide.assert_not_called()


def test_xong_thi_xoa_dau_va_dong_tiep_app():
    with _done("closed") as (self, _h, clear, timer):
        clear.assert_called_once()
        assert self._daw_close_pending is False
        timer.singleShot.assert_called_once_with(0, self.close)


# ── closeEvent: lượt đầu tàng hình + dọn, lượt sau mới thật sự đóng ───────────

def _close_self(needs_daw):
    self = MagicMock()
    self._close_started = False
    self._daw_close_pending = False
    self._needs_studio_one_shutdown.return_value = needs_daw

    def _start():
        self._daw_close_pending = True
    self._start_hidden_daw_shutdown.side_effect = _start
    return self


def test_bam_x_khi_dau_dang_chay_thi_tang_hinh_ngay_va_cho_dau_dong_ngam():
    self = _close_self(needs_daw=True)
    event = MagicMock()
    MainDashboard.closeEvent(self, event)
    self._vanish.assert_called_once()
    self._stop_for_close.assert_called_once()
    self._start_bg_shutdown.assert_called_once()
    self._start_hidden_daw_shutdown.assert_called_once()
    event.ignore.assert_called_once()
    event.accept.assert_not_called()
    self._finish_close.assert_not_called()


def test_tang_hinh_truoc_khi_lam_bat_cu_viec_gi_cham():
    order = []
    self = _close_self(needs_daw=True)
    self._vanish.side_effect = lambda: order.append("vanish")
    self._stop_for_close.side_effect = lambda: order.append("stop")
    MainDashboard.closeEvent(self, MagicMock())
    assert order == ["vanish", "stop"]


def test_dau_khong_chay_thi_dong_luon():
    self = _close_self(needs_daw=False)
    event = MagicMock()
    MainDashboard.closeEvent(self, event)
    self._start_hidden_daw_shutdown.assert_not_called()
    self._finish_close.assert_called_once_with(event)


def test_luot_sau_khi_dau_da_dong_thi_khong_don_lai():
    self = _close_self(needs_daw=True)
    MainDashboard.closeEvent(self, MagicMock())
    self._daw_close_pending = False          # _on_hidden_daw_shutdown_done
    event = MagicMock()
    MainDashboard.closeEvent(self, event)
    self._stop_for_close.assert_called_once()
    self._start_hidden_daw_shutdown.assert_called_once()
    self._finish_close.assert_called_once_with(event)


def test_dang_dong_dau_ma_bi_goi_close_lan_nua_thi_van_cho():
    self = _close_self(needs_daw=True)
    MainDashboard.closeEvent(self, MagicMock())
    event = MagicMock()
    MainDashboard.closeEvent(self, event)
    event.ignore.assert_called()
    self._finish_close.assert_not_called()
