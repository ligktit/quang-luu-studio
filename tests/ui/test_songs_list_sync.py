"""Nút "☁ Đồng bộ tone" ở Danh sách bài hát — phần nhận kết quả về UI.

Spec 2026-10-03 §5: worker gọi pull_overrides rồi lookup_many; nút trở lại bình
thường khi xong; thông báo gộp số bài lấy từ cộng đồng và số tone admin đặt.
"""
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PySide6.QtWidgets")

from ui.dialogs.songs_list import SongsListDialog

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def _dialog_stub():
    dlg = MagicMock()
    dlg._dashboard = MagicMock()
    return dlg


def _entry(primary):
    return {"primary_key": primary, "key_timeline": [{"time": 0, "key_display": primary}]}


def test_xong_thi_nut_tro_lai_binh_thuong_va_gop_thong_bao():
    dlg = _dialog_stub()
    pending = [{"id": 7, "url": URL, "title": "A"}]
    with patch("backend.SongManager.update_song") as update:
        SongsListDialog._on_sync_done(dlg, {URL: _entry("Am")}, pending, {"applied": 2})

    dlg._sync_btn.setEnabled.assert_called_with(True)
    dlg._sync_btn.setText.assert_called_with("☁ Đồng bộ tone")
    update.assert_called_once_with(7, tone="Am")
    dlg._refresh_data.assert_called_once()
    msg = dlg._dashboard._show_message.call_args.args[0]
    assert "lấy tone cho 1/1 bài" in msg and "nhận 2 tone do quản trị đặt" in msg


def test_chi_co_tone_admin_van_lam_moi_danh_sach():
    dlg = _dialog_stub()
    SongsListDialog._on_sync_done(dlg, {}, [], {"applied": 1})
    dlg._refresh_data.assert_called_once()
    dlg._rebuild_list.assert_called_once()
    assert "nhận 1 tone do quản trị đặt" in dlg._dashboard._show_message.call_args.args[0]


def test_khong_co_gi_moi_va_khong_co_bai_cho():
    dlg = _dialog_stub()
    SongsListDialog._on_sync_done(dlg, {}, [], {"applied": 0})
    dlg._refresh_data.assert_not_called()
    assert dlg._dashboard._show_message.call_args.args[0] == "Không có tone mới."


def test_khong_ai_do_cac_bai_cho():
    dlg = _dialog_stub()
    SongsListDialog._on_sync_done(dlg, {}, [{"id": 1, "url": URL}], None)
    assert "Chưa ai trong mạng lưới dò 1 bài này" in dlg._dashboard._show_message.call_args.args[0]


def test_worker_dung_sync_songs_va_tra_ca_hai_phan(qtbot):
    """Worker phải gọi tone_share.sync_songs (pull_overrides trước lookup_many)
    và đẩy (found, stats) về _on_sync_done."""
    from PySide6.QtWidgets import QDialog

    host = QDialog()
    qtbot.addWidget(host)
    host._sync_worker = None
    got = []
    host._on_sync_done = lambda found, pending, stats: got.append((found, pending, stats))
    pending = [{"id": 1, "url": URL}]

    with patch("core.tone_share.sync_songs", return_value=({URL: _entry("Am")}, {"applied": 1})) as sync:
        SongsListDialog._start_sync_worker(host, pending)
        qtbot.waitUntil(lambda: bool(got), timeout=3000)

    sync.assert_called_once_with([URL])
    assert got == [({URL: _entry("Am")}, pending, {"applied": 1})]
