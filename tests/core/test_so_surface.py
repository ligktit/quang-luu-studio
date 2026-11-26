"""So/gộp surface Studio One theo control (core/so_surface.py)."""
import os
import re
import xml.etree.ElementTree as ET

from core import so_surface

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BUNDLED_PATH = os.path.join(ROOT, "studio_one", "QuangLuuMIDI.surface.xml")


def _bundled():
    with open(BUNDLED_PATH, encoding="utf-8", newline="") as fh:
        return fh.read()


def _studio_one_rewrite(bundled, drop=(), extra=""):
    """Giả lập file Studio One ghi lại khi học control: tab, địa chỉ hex, root không thuộc tính,
    có thể rơi control (máy 826077C rơi toneVoice2) và thêm control học tay."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<ControlSurface>", "\t<Controls>"]
    for c in ET.fromstring(bundled.encode("utf-8")).iter("Control"):
        if c.get("name") in drop:
            continue
        lines.append('\t\t<Control name="%s" title="%s" type="%s" options="%s">'
                     % (c.get("name"), c.get("title"), c.get("type"), c.get("options")))
        for m in c.iter("MidiMessage"):
            lines.append('\t\t\t<MidiMessage status="%s" channel="%s" address="#%X"/>'
                         % (m.get("status"), m.get("channel"), int(m.get("address"))))
        lines.append("\t\t</Control>")
    lines.append(extra)
    lines += ["\t</Controls>", "</ControlSurface>"]
    return "\n".join(lines)


BE_KG = ('\t\t<Control name="controlb003c" title="Be KG" type="button" options="receive public">\n'
         '\t\t\t<MidiMessage status="#B0" channel="0" address="#3C"/>\n'
         '\t\t</Control>')


def test_ban_studio_one_ghi_lai_co_them_control_hoc_tay_van_la_du():
    b = _bundled()
    assert so_surface.covers(b, _studio_one_rewrite(b, extra=BE_KG)) is True


def test_ban_studio_one_lam_roi_control_cua_app_la_thieu():
    b = _bundled()
    assert so_surface.covers(b, _studio_one_rewrite(b, drop={"toneVoice2"}, extra=BE_KG)) is False


def test_doi_tin_midi_cua_control_app_la_cu():
    b = _bundled()
    dev = _studio_one_rewrite(b).replace('channel="1" address="#2F"', 'channel="0" address="#2F"')
    assert so_surface.covers(b, dev) is False


def test_khong_doc_duoc_xml_thi_tra_none():
    assert so_surface.covers(_bundled(), "surf v1") is None
    assert so_surface.merge(_bundled(), "<ControlSurface><Controls>") is None


def test_gop_giu_control_hoc_tay_va_bu_control_bi_roi():
    # Máy 826077C 2026-11-26: Tự sửa chép đè làm mất "Be KG" — gộp phải giữ lại.
    b = _bundled()
    merged = so_surface.merge(b, _studio_one_rewrite(b, drop={"toneVoice2"}, extra=BE_KG))
    ctrls = so_surface.controls(merged)
    assert ctrls["controlb003c"] == ("button", ((0xB0, 0, 0x3C),))
    assert "toneVoice2" in ctrls
    assert set(ctrls) == set(so_surface.controls(b)) | {"controlb003c"}
    assert so_surface.covers(b, merged) is True
    # Giữ nguyên chữ bản đi kèm (chú thích, thuộc tính root, CRLF), chỉ chèn thêm.
    cut = b.rfind("\n", 0, b.rfind("</Controls>")) + 1
    assert merged.startswith(b[:cut]) and merged.endswith(b[cut:])
    if "\r\n" in b:
        assert "\n" not in merged.replace("\r\n", "")
    assert re.search(r'title="Be KG"', merged)


def test_gop_khong_co_control_thua_thi_tra_nguyen_ban_di_kem():
    b = _bundled()
    assert so_surface.merge(b, _studio_one_rewrite(b, drop={"toneVoice2"})) == b


def test_gop_hai_lan_khong_nhan_doi_control():
    b = _bundled()
    once = so_surface.merge(b, _studio_one_rewrite(b, extra=BE_KG))
    twice = so_surface.merge(b, once)
    assert twice == once
