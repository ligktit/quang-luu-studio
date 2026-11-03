"""Bộ chẩn đoán đọc cấu hình ẩn cửa sổ DAW (daw_windows) thay cho khoá kỹ thuật cũ."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CD = os.path.join(ROOT, "tools", "chan_doan")


def _src(name):
    with open(os.path.join(CD, name), encoding="utf-8-sig") as f:
        return f.read()


def test_chan_doan_bao_cau_hinh_an_daw():
    src = _src("QLS_ChanDoan.ps1")
    assert 'Prop $s "daw_windows"' in src
    assert '"auto_hide"' in src


def test_chan_doan_ban_mau_theo_daw_dang_chon():
    # Cubase chốt bản mẫu thành template.cpr — kiểm template.song là báo sai.
    src = _src("QLS_ChanDoan.ps1")
    assert 'so_template\\template.song"' not in src
    assert '"so_template\\template." + $tplExt' in src


def test_sua_loi_khoa_ky_thuat_chi_cho_ban_app_cu():
    src = _src("QLS_SuaLoi.ps1")
    i = src.find('Prop $s "tech_lock"')
    assert i != -1
    assert "bản app cũ" in src[src.rfind("\n\n", 0, i):i]
