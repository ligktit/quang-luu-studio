# tests/ui/test_first_run_dialog.py
"""Hộp thoại lần chạy đầu: chạy setup_all nền, hỏi cài loopMIDI / dọn bản cũ khi
cần, chỉ đánh dấu xong khi đi hết luồng."""
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture
def saved():
    store = {"settings": {}}
    with patch("ui.dialogs.first_run_dialog.ConfigManager.load_settings",
               side_effect=lambda: dict(store["settings"])), \
         patch("ui.dialogs.first_run_dialog.ConfigManager.save_settings",
               side_effect=lambda s: store.__setitem__("settings", dict(s)) or True), \
         patch("ui.dialogs.first_run_dialog.first_run.ensure_default_data_files", return_value=[]), \
         patch("ui.dialogs.first_run_dialog.first_run.default_daw", return_value="studio_one"):
        yield store


def _make(qtbot, legacy=None, run_setup=True):
    from ui.dialogs.first_run_dialog import FirstRunDialog
    d = FirstRunDialog("C:\\app", "C:\\data", legacy_dir=legacy, run_setup=run_setup)
    qtbot.addWidget(d)
    d.show()
    return d


def test_moi_thu_on_tu_dong_xong(qtbot, saved):
    with patch("ui.dialogs.first_run_dialog.first_run.run_setup_all", return_value=0):
        d = _make(qtbot)
        qtbot.waitUntil(lambda: d.result() == QDialog.Accepted, timeout=5000)
    assert saved["settings"].get("first_run_done") is True


def test_thieu_loopmidi_hoi_cai_roi_chay_lai(qtbot, saved):
    codes = iter([1, 0])
    with patch("ui.dialogs.first_run_dialog.first_run.run_setup_all", side_effect=lambda *_a, **_k: next(codes)), \
         patch("ui.dialogs.first_run_dialog.first_run.find_loopmidi", return_value=None), \
         patch("ui.dialogs.first_run_dialog.first_run.install_loopmidi_elevated", return_value=True) as inst:
        d = _make(qtbot)
        qtbot.waitUntil(lambda: d._btn_loopmidi.isVisible(), timeout=5000)
        qtbot.mouseClick(d._btn_loopmidi, Qt.LeftButton)
        qtbot.waitUntil(lambda: d.result() == QDialog.Accepted, timeout=5000)
    inst.assert_called_once()
    assert saved["settings"].get("first_run_done") is True


def test_setup_all_loi_van_cho_tiep_tuc(qtbot, saved):
    with patch("ui.dialogs.first_run_dialog.first_run.run_setup_all", return_value=-1):
        d = _make(qtbot)
        qtbot.waitUntil(lambda: d._btn_continue.isVisible(), timeout=5000)
        assert "setup_all.bat" in d._lbl_notes.text()
        qtbot.mouseClick(d._btn_continue, Qt.LeftButton)
    assert d.result() == QDialog.Accepted
    assert saved["settings"].get("first_run_done") is True


def test_ban_cu_de_sau_khong_don(qtbot, saved):
    with patch("ui.dialogs.first_run_dialog.first_run.run_setup_all", return_value=0), \
         patch("ui.dialogs.first_run_dialog.first_run.cleanup_legacy_elevated") as clean:
        d = _make(qtbot, legacy="C:\\Program Files\\QuangLuuStudio")
        qtbot.waitUntil(lambda: d._btn_legacy.isVisible(), timeout=5000)
        qtbot.mouseClick(d._btn_later, Qt.LeftButton)
        qtbot.waitUntil(lambda: d.result() == QDialog.Accepted, timeout=5000)
    clean.assert_not_called()


def test_ban_cu_don_thi_chuyen_cau_hinh_roi_don(qtbot, saved):
    with patch("ui.dialogs.first_run_dialog.first_run.run_setup_all", return_value=0), \
         patch("ui.dialogs.first_run_dialog.first_run.migrate_legacy_app_config", return_value=True) as mig, \
         patch("ui.dialogs.first_run_dialog.first_run.cleanup_legacy_elevated", return_value=0) as clean:
        d = _make(qtbot, legacy="C:\\Program Files\\QuangLuuStudio")
        qtbot.waitUntil(lambda: d._btn_legacy.isVisible(), timeout=5000)
        qtbot.mouseClick(d._btn_legacy, Qt.LeftButton)
        qtbot.waitUntil(lambda: d.result() == QDialog.Accepted, timeout=5000)
    mig.assert_called_once_with("C:\\Program Files\\QuangLuuStudio")
    clean.assert_called_once_with("C:\\Program Files\\QuangLuuStudio")


LEGACY = "C:\\Program Files\\QuangLuuStudio"


def _don_ban_cu_voi_ma(qtbot, code):
    with patch("ui.dialogs.first_run_dialog.first_run.run_setup_all", return_value=0), \
         patch("ui.dialogs.first_run_dialog.first_run.migrate_legacy_app_config", return_value=False), \
         patch("ui.dialogs.first_run_dialog.first_run.cleanup_legacy_elevated", return_value=code):
        d = _make(qtbot, legacy=LEGACY)
        qtbot.waitUntil(lambda: d._btn_legacy.isVisible(), timeout=5000)
        qtbot.mouseClick(d._btn_legacy, Qt.LeftButton)
        qtbot.waitUntil(lambda: d._btn_continue.isVisible() or d.result() == QDialog.Accepted, timeout=5000)
    return d


def test_don_ban_cu_ma_0_xong_khong_ghi_chu(qtbot, saved):
    d = _don_ban_cu_voi_ma(qtbot, 0)
    assert d.result() == QDialog.Accepted
    assert "legacy_cleanup_skipped" not in saved["settings"]


def test_don_ban_cu_ma_3_ghi_nho_va_huong_dan_go_tay(qtbot, saved):
    from core import first_run
    d = _don_ban_cu_voi_ma(qtbot, 3)
    assert d._btn_continue.isVisible()
    notes = d._lbl_notes.text()
    assert "Gỡ cài đặt" in notes and "KHÔNG" in notes
    assert "hỏi lại" not in notes
    assert saved["settings"]["legacy_cleanup_skipped"] == first_run.legacy_path_key(LEGACY)


@pytest.mark.parametrize("code", [2, 1, -1])
def test_don_ban_cu_ma_khac_hoi_lai_lan_sau(qtbot, saved, code):
    d = _don_ban_cu_voi_ma(qtbot, code)
    assert d._btn_continue.isVisible()
    assert "hỏi lại" in d._lbl_notes.text()
    assert "legacy_cleanup_skipped" not in saved["settings"]


def test_run_first_run_if_needed_bo_qua_ban_cu_da_danh_dau_go_tay():
    from ui.dialogs import first_run_dialog as m
    settings = {"first_run_done": True,
                "legacy_cleanup_skipped": m.first_run.legacy_path_key(LEGACY.upper() + "\\")}
    with patch.object(m.first_run, "is_velopack_install", return_value=True), \
         patch.object(m.ConfigManager, "load_settings", return_value=settings), \
         patch.object(m.first_run, "find_legacy_install", return_value=LEGACY), \
         patch.object(m, "FirstRunDialog") as dlg:
        m.run_first_run_if_needed()
    dlg.assert_not_called()


def test_dong_ngang_khong_danh_dau_xong(qtbot, saved):
    with patch("ui.dialogs.first_run_dialog.first_run.run_setup_all", return_value=1), \
         patch("ui.dialogs.first_run_dialog.first_run.find_loopmidi", return_value=None):
        d = _make(qtbot)
        qtbot.waitUntil(lambda: d._btn_loopmidi.isVisible(), timeout=5000)
        d.reject()
    assert "first_run_done" not in saved["settings"]


def test_chi_con_ban_cu_khong_chay_setup(qtbot, saved):
    with patch("ui.dialogs.first_run_dialog.first_run.run_setup_all") as setup:
        d = _make(qtbot, legacy="C:\\Program Files\\QuangLuuStudio", run_setup=False)
        qtbot.waitUntil(lambda: d._btn_legacy.isVisible(), timeout=5000)
        qtbot.mouseClick(d._btn_later, Qt.LeftButton)
    setup.assert_not_called()
    assert d.result() == QDialog.Accepted
    assert "first_run_done" not in saved["settings"]


def test_run_first_run_if_needed_bo_qua_ban_khong_phai_velopack():
    from ui.dialogs import first_run_dialog as m
    with patch.object(m.first_run, "is_velopack_install", return_value=False), \
         patch.object(m, "FirstRunDialog") as dlg:
        m.run_first_run_if_needed()
    dlg.assert_not_called()


def test_run_first_run_if_needed_bo_qua_khi_xong_va_khong_co_ban_cu():
    from ui.dialogs import first_run_dialog as m
    with patch.object(m.first_run, "is_velopack_install", return_value=True), \
         patch.object(m.ConfigManager, "load_settings", return_value={"first_run_done": True}), \
         patch.object(m.first_run, "find_legacy_install", return_value=None), \
         patch.object(m, "FirstRunDialog") as dlg:
        m.run_first_run_if_needed()
    dlg.assert_not_called()


def test_run_first_run_if_needed_bo_qua_khoa_cu_khong_co_duong_dan():
    from ui.dialogs import first_run_dialog as m
    with patch.object(m.first_run, "is_velopack_install", return_value=True), \
         patch.object(m.ConfigManager, "load_settings", return_value={"first_run_done": True}), \
         patch.object(m.first_run, "find_legacy_install", return_value=""), \
         patch.object(m, "FirstRunDialog") as dlg:
        m.run_first_run_if_needed()
    dlg.assert_not_called()


def _chay_voi_ban_cu(tmp_path, legacy_of):
    from ui.dialogs import first_run_dialog as m
    app_dir = tmp_path / "QuangLuuStudio" / "current"
    app_dir.mkdir(parents=True)
    with patch.object(m, "APP_DIR", str(app_dir)), \
         patch.object(m.first_run, "is_velopack_install", return_value=True), \
         patch.object(m.ConfigManager, "load_settings", return_value={"first_run_done": True}), \
         patch.object(m.first_run, "find_legacy_install", return_value=legacy_of(app_dir)), \
         patch.object(m, "FirstRunDialog") as dlg:
        m.run_first_run_if_needed()
    return dlg


def test_ban_cu_trung_thu_muc_app_khong_hoi(tmp_path):
    dlg = _chay_voi_ban_cu(tmp_path, lambda app: str(app))
    dlg.assert_not_called()


def test_ban_cu_la_goc_velopack_khong_hoi(tmp_path):
    dlg = _chay_voi_ban_cu(tmp_path, lambda app: str(app.parent))
    dlg.assert_not_called()


def test_ban_cu_la_cha_cua_app_khong_hoi(tmp_path):
    dlg = _chay_voi_ban_cu(tmp_path, lambda app: str(app.parent.parent))
    dlg.assert_not_called()


def test_ban_cu_thu_muc_khac_van_hoi(tmp_path):
    other = tmp_path / "Program Files" / "QuangLuuStudio"
    other.mkdir(parents=True)
    dlg = _chay_voi_ban_cu(tmp_path, lambda app: str(other))
    dlg.assert_called_once()
