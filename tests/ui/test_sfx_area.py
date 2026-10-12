"""Nút SFX bật/tắt: bấm gửi sfx_toggle(id, path), đèn "đang phát", xoá/đổi file
khi đang phát thì phải dừng (không để SFX mồ côi không ai tắt được)."""
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog


@pytest.fixture
def wav(tmp_path):
    p = tmp_path / "a.wav"
    p.write_bytes(b"RIFF")
    return str(p)


@pytest.fixture
def area(qapp, qtbot, wav):
    from ui.components.sfx_button_area import SfxButtonArea
    a = SfxButtonArea(sfx_list=[
        {"id": "sfx_a", "label": "A", "name": "Alpha", "file_path": wav, "color": "#14B8A6"},
        {"id": "sfx_b", "label": "B", "name": "Beta", "file_path": "", "color": "#F97316"},
    ])
    qtbot.addWidget(a)
    a.show()
    qtbot.waitExposed(a)
    return a


def _btn(area, sfx_id):
    return next(b for b in area._btn_widgets if b.data["id"] == sfx_id)


def test_bam_nut_gui_toggle_kem_id_va_file(area, qtbot, wav):
    with qtbot.waitSignal(area.sfx_toggle) as sig:
        qtbot.mouseClick(_btn(area, "sfx_a"), Qt.LeftButton)
    assert sig.args == ["sfx_a", wav]


def test_nut_chua_gan_file_khong_gui(area, qtbot):
    with qtbot.assertNotEmitted(area.sfx_toggle, wait=50):
        qtbot.mouseClick(_btn(area, "sfx_b"), Qt.LeftButton)


def test_den_dang_phat_doi_hinh_va_tooltip(area):
    b = _btn(area, "sfx_a")
    idle = b.grab().toImage()
    area.set_playing("sfx_a", True)
    assert b.is_playing()
    assert "Đang phát" in b.toolTip()
    assert b.grab().toImage() != idle
    area.set_playing("sfx_a", False)
    assert not b.is_playing()
    assert "Đang phát" not in b.toolTip()
    assert b.grab().toImage() == idle


def test_set_playing_id_la_khong_loi(area):
    area.set_playing("khong_co", True)   # SFX vừa bị xoá — bỏ qua


def test_xoa_nut_dang_phat_thi_dung(area, qtbot):
    area.set_playing("sfx_a", True)
    with qtbot.waitSignal(area.sfx_stop) as sig:
        area._on_delete(_btn(area, "sfx_a"))
    assert sig.args == ["sfx_a"]


def test_xoa_nut_khong_phat_khong_gui_stop(area, qtbot):
    with qtbot.assertNotEmitted(area.sfx_stop, wait=50):
        area._on_delete(_btn(area, "sfx_a"))


def _edit_with(area, result):
    with patch("ui.components.sfx_button_area.SfxEditDialog") as Dlg:
        Dlg.return_value.exec.return_value = QDialog.Accepted
        Dlg.return_value.get_result.return_value = result
        area._on_edit(_btn(area, "sfx_a"))


def test_doi_file_khi_dang_phat_thi_dung(area, qtbot, tmp_path):
    area.set_playing("sfx_a", True)
    other = str(tmp_path / "b.wav")
    with qtbot.waitSignal(area.sfx_stop) as sig:
        _edit_with(area, {"label": "A", "name": "Alpha", "file_path": other, "color": "#14B8A6"})
    assert sig.args == ["sfx_a"]


def test_sua_ten_khong_doi_file_thi_van_phat(area, qtbot, wav):
    area.set_playing("sfx_a", True)
    with qtbot.assertNotEmitted(area.sfx_stop, wait=50):
        _edit_with(area, {"label": "A", "name": "Đổi tên", "file_path": wav, "color": "#14B8A6"})
    assert _btn(area, "sfx_a").is_playing()


def test_duong_dan_mac_dinh_cu_trong_thu_muc_tam_duoc_tro_lai(qapp, qtbot, tmp_path):
    """settings.json từng lưu %TEMP%\\_MEIxxxx\\sfx\\sfx_applause.wav — thư mục đó
    mất sau mỗi lần thoát; lần mở sau phải trỏ lại file đóng gói."""
    from ui.components.sfx_button_area import SfxButtonArea
    sfx_dir = tmp_path / "app" / "sfx"
    sfx_dir.mkdir(parents=True)
    (sfx_dir / "sfx_applause.wav").write_bytes(b"RIFF")
    stale = str(tmp_path / "_MEI999" / "sfx" / "sfx_applause.wav")
    user_file = tmp_path / "rieng.wav"
    user_file.write_bytes(b"RIFF")
    a = SfxButtonArea(sfx_list=[
        {"id": "sfx_002", "label": "👏", "name": "Vỗ tay", "file_path": stale, "color": "#14B8A6"},
        {"id": "sfx_001", "label": "😂", "name": "Cười", "file_path": str(user_file), "color": "#F97316"},
    ], app_dir=str(tmp_path / "app"))
    qtbot.addWidget(a)
    paths = {d["id"]: d["file_path"] for d in a.get_sfx_list()}
    assert paths["sfx_002"] == str(sfx_dir / "sfx_applause.wav")
    # file người dùng tự chọn (vẫn tồn tại) giữ nguyên
    assert paths["sfx_001"] == str(user_file)


def test_file_nguoi_dung_mat_khong_bi_doi_sang_mac_dinh(qapp, qtbot, tmp_path):
    from ui.components.sfx_button_area import SfxButtonArea
    sfx_dir = tmp_path / "app" / "sfx"
    sfx_dir.mkdir(parents=True)
    (sfx_dir / "sfx_laugh.wav").write_bytes(b"RIFF")
    gone = str(tmp_path / "nhac_rieng" / "cuoi_to.wav")   # tên KHÁC tên mặc định
    a = SfxButtonArea(sfx_list=[
        {"id": "sfx_001", "label": "😂", "name": "Cười", "file_path": gone, "color": "#F97316"},
    ], app_dir=str(tmp_path / "app"))
    qtbot.addWidget(a)
    assert a.get_sfx_list()[0]["file_path"] == gone
