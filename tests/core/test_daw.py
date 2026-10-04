"""Hồ sơ DAW: chọn đúng hồ sơ theo settings, mặc định là Studio One."""
import pytest

from core import daw


@pytest.fixture(autouse=True)
def _unbind():
    daw.bind(None)
    yield
    daw.bind(None)


def test_thieu_daw_kind_la_studio_one():
    assert daw.active({}).kind == "studio_one"
    assert daw.active({"daw_kind": "khong_co"}).kind == "studio_one"
    assert daw.active({"daw_kind": None}).kind == "studio_one"


def test_chon_cubase():
    p = daw.active({"daw_kind": "cubase"})
    assert p.kind == "cubase"
    assert p.display_name == "Cubase"
    assert p.template_extension == ".cpr"
    assert ".cpr" in p.project_extensions
    assert p.process_keywords == ("cubase",)
    assert p.main_title_requires == ("cubase", "project")
    assert p.fader_unity_cc == 100
    assert p.calibration["scale_midi_map"] == {"Major": 43, "Minor": 85}
    assert p.calibration["scale_values"] == {"major": 43, "minor": 85}
    assert p.quit_window_class_prefix == "SmtgMain"


def test_studio_one_giu_nguyen_hang_cu():
    p = daw.STUDIO_ONE
    assert p.process_keywords == ("studio one",)
    assert p.main_title_requires == ("studio one",)
    assert p.template_extension == ".song"
    assert ".songversion" in p.project_extensions
    assert p.fader_unity_cc == 76
    assert p.calibration == {}
    assert p.quit_window_class_prefix == ""


def test_bind_dung_settings_song():
    live = {"daw_kind": "cubase"}
    daw.bind(live)
    assert daw.active().kind == "cubase"
    live["daw_kind"] = "studio_one"
    assert daw.active().kind == "studio_one"


def test_is_project_file_theo_ho_so():
    assert daw.is_project_file(r"C:\a\b.song", daw.STUDIO_ONE) is True
    assert daw.is_project_file(r"C:\a\b.CPR", daw.CUBASE) is True
    assert daw.is_project_file(r"C:\a\b.cpr", daw.STUDIO_ONE) is False
    assert daw.is_project_file("", daw.CUBASE) is False
    assert daw.is_project_file(None, daw.CUBASE) is False
