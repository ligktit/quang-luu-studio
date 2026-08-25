"""Kiểm thử core.so_template — bản mẫu .song của Studio One."""
import pytest

from core import so_template


@pytest.fixture(autouse=True)
def temp_template_dir(tmp_path, monkeypatch):
    """Trỏ thư mục bản mẫu vào tmp_path để không đụng %APPDATA% thật."""
    tpl_dir = tmp_path / "so_template"
    monkeypatch.setattr(so_template, "TEMPLATE_DIR", str(tpl_dir))
    monkeypatch.setattr(so_template, "TEMPLATE_FILE", str(tpl_dir / "template.song"))
    monkeypatch.setattr(so_template, "TEMPLATE_META", str(tpl_dir / "template.json"))
    monkeypatch.setattr(so_template, "REPLACED_FILE", str(tpl_dir / "replaced.song"))
    return tpl_dir


@pytest.fixture
def song(tmp_path):
    path = tmp_path / "BaiMau.song"
    path.write_bytes(b"BAN MAU GOC")
    return path


# ── Chốt bản mẫu ─────────────────────────────────────────────────────────────

def test_chua_chot_thi_khong_co_ban_mau():
    assert so_template.has_template() is False
    assert so_template.info() is None


def test_chot_ban_mau(song):
    result = so_template.snapshot(str(song))
    assert result["ok"] is True
    assert so_template.has_template() is True
    info = so_template.info()
    assert info["source"].endswith("BaiMau.song")
    assert info["sha256"] == result["sha256"]


def test_chot_tu_choi_file_khong_phai_song(tmp_path):
    exe = tmp_path / "StudioOne.exe"
    exe.write_bytes(b"MZ")
    result = so_template.snapshot(str(exe))
    assert result["ok"] is False
    assert ".song" in result["error"]


def test_chot_bao_loi_khi_file_khong_ton_tai(tmp_path):
    result = so_template.snapshot(str(tmp_path / "khong-co.song"))
    assert result["ok"] is False


# ── Phục hồi ─────────────────────────────────────────────────────────────────

def test_phuc_hoi_ghi_de_chinh_sua_cua_khach(song):
    so_template.snapshot(str(song))
    song.write_bytes(b"KHACH DA CHINH LUNG TUNG")

    result = so_template.restore(str(song), so_running=False)

    assert result["restored"] is True
    assert song.read_bytes() == b"BAN MAU GOC"


def test_phuc_hoi_giu_lai_ban_vua_bi_de(song, temp_template_dir):
    so_template.snapshot(str(song))
    song.write_bytes(b"KHACH DA CHINH")
    so_template.restore(str(song), so_running=False)
    assert (temp_template_dir / "replaced.song").read_bytes() == b"KHACH DA CHINH"


def test_khong_phuc_hoi_khi_da_trung_ban_mau(song):
    so_template.snapshot(str(song))
    result = so_template.restore(str(song), so_running=False)
    assert result["restored"] is False
    assert "trùng" in result["reason"]


def test_khong_phuc_hoi_khi_studio_one_dang_chay(song):
    """Ghi đè file .song đang mở là hỏng bài — phải bỏ qua."""
    so_template.snapshot(str(song))
    song.write_bytes(b"KHACH DA CHINH")

    result = so_template.restore(str(song), so_running=True)

    assert result["restored"] is False
    assert song.read_bytes() == b"KHACH DA CHINH"


def test_khong_phuc_hoi_khi_chua_chot_ban_mau(song):
    result = so_template.restore(str(song), so_running=False)
    assert result["restored"] is False
    assert "chưa chốt" in result["reason"]


def test_khong_phuc_hoi_khi_duong_dan_la_exe(tmp_path, song):
    so_template.snapshot(str(song))
    exe = tmp_path / "StudioOne.exe"
    exe.write_bytes(b"MZ")
    result = so_template.restore(str(exe), so_running=False)
    assert result["restored"] is False
    assert exe.read_bytes() == b"MZ"


def test_chot_lai_thi_ban_mau_doi_theo(song):
    so_template.snapshot(str(song))
    song.write_bytes(b"KTV DA TINH CHINH LAI")
    so_template.snapshot(str(song))

    song.write_bytes(b"KHACH PHA")
    so_template.restore(str(song), so_running=False)

    assert song.read_bytes() == b"KTV DA TINH CHINH LAI"


def test_clear_xoa_ban_mau(song):
    so_template.snapshot(str(song))
    so_template.clear()
    assert so_template.has_template() is False
