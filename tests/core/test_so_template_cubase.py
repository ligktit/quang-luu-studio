"""Bản mẫu .cpr khi chọn Cubase; đường dẫn .cpr không phải bài của Studio One."""
import pytest

from core import daw, so_template


@pytest.fixture(autouse=True)
def temp_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(so_template, "TEMPLATE_DIR", str(tmp_path / "so_template"))
    monkeypatch.setattr(so_template, "TEMPLATE_FILE", str(tmp_path / "so_template" / "template.song"))
    monkeypatch.setattr(so_template, "TEMPLATE_META", str(tmp_path / "so_template" / "template.json"))
    monkeypatch.setattr(so_template, "REPLACED_FILE", str(tmp_path / "so_template" / "replaced.song"))
    daw.bind(None)
    yield
    daw.bind(None)


def test_cpr_khong_phai_bai_studio_one():
    daw.bind({})
    assert so_template.is_song_file(r"D:\QLS\mau.cpr") is False
    r = so_template.snapshot(r"D:\QLS\mau.cpr")
    assert r["ok"] is False


def test_chot_va_phuc_hoi_cpr(tmp_path):
    daw.bind({"daw_kind": "cubase"})
    cpr = tmp_path / "mau.cpr"
    cpr.write_bytes(b"GOC")
    assert so_template.is_song_file(str(cpr)) is True
    assert so_template.snapshot(str(cpr))["ok"] is True
    assert so_template.template_file().endswith("template.cpr")
    assert so_template.has_template() is True
    cpr.write_bytes(b"KHACH SUA")
    r = so_template.restore(str(cpr), so_running=False)
    assert r["restored"] is True
    assert cpr.read_bytes() == b"GOC"
    assert so_template.replaced_file().endswith("replaced.cpr")


def test_ban_mau_hai_daw_khong_de_nhau(tmp_path):
    song = tmp_path / "a.song"; song.write_bytes(b"S1")
    cpr = tmp_path / "b.cpr"; cpr.write_bytes(b"CB")
    daw.bind({})
    assert so_template.snapshot(str(song))["ok"]
    daw.bind({"daw_kind": "cubase"})
    assert so_template.has_template() is False
    assert so_template.snapshot(str(cpr))["ok"]
    daw.bind({})
    assert so_template.has_template() is True


def test_info_theo_dung_daw(tmp_path):
    song = tmp_path / "a.song"; song.write_bytes(b"S1")
    cpr = tmp_path / "b.cpr"; cpr.write_bytes(b"CB")
    daw.bind({})
    assert so_template.snapshot(str(song))["ok"]
    daw.bind({"daw_kind": "cubase"})
    assert so_template.snapshot(str(cpr))["ok"]
    assert so_template.info()["source"].endswith("b.cpr")
    daw.bind({})
    assert so_template.info()["source"].endswith("a.song")
    daw.bind({"daw_kind": "cubase"})
    so_template.clear()
    assert so_template.has_template() is False
    daw.bind({})
    assert so_template.has_template() is True
