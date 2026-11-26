"""So sánh và gộp file surface Studio One (QuangLuuMIDI.surface.xml) theo từng control.

Khi kỹ thuật học (learn) một control mới trong Studio One, Studio One ghi lại CẢ file
surface: thêm control `controlbXXXX`, đổi định dạng (tab, địa chỉ hex, bỏ thuộc tính gốc),
có khi làm rơi control. So SHA với bản đi kèm app thì lần nào cũng "cũ", và Tự sửa chép đè
làm mất control học tay — máy 826077C (2026-11-26) mất control "Be KG" sáu lần một buổi sáng,
link trong bài còn nhưng trỏ vào control không tồn tại.

Ở đây so theo control: bản trên máy "đủ" khi mọi control của bản đi kèm có mặt với cùng tin MIDI;
control thừa (học tay) không tính là cũ. Gộp = bản đi kèm + các control thừa của bản trên máy.
Hàm nào không đọc được XML thì trả None để bên gọi quay về cách so/chép cả file.
"""
import copy
import xml.etree.ElementTree as ET

_GHI_CHU = "<!-- Control kỹ thuật tự học trong Studio One — Tự sửa âm thanh giữ lại khi cập nhật -->"


def _num(v):
    v = (v or "").strip()
    try:
        return int(v[1:], 16) if v.startswith("#") else int(v)
    except ValueError:
        return v.lower()


def _root(text):
    if not isinstance(text, str):
        return None
    try:
        return ET.fromstring(text.lstrip("﻿"))
    except (ET.ParseError, ValueError, UnicodeError):
        return None


def _signature(ctrl):
    msgs = tuple(sorted(
        (_num(m.get("status")), _num(m.get("channel")), _num(m.get("address")))
        for m in ctrl.iter("MidiMessage")
    ))
    return (ctrl.get("type") or "", msgs)


def controls(text):
    """{tên control: chữ ký (type, tin MIDI)}; None nếu không đọc được XML."""
    root = _root(text)
    if root is None:
        return None
    return {c.get("name"): _signature(c) for c in root.iter("Control") if c.get("name")}


def covers(bundled_text, device_text):
    """True khi bản trên máy có đủ mọi control của bản đi kèm, cùng tin MIDI (control thừa không sao).
    None khi một trong hai file không đọc được XML."""
    b, d = controls(bundled_text), controls(device_text)
    if b is None or d is None or not b:
        return None
    return all(d.get(name) == sig for name, sig in b.items())


def extra_controls(bundled_text, device_text):
    """Các phần tử <Control> có trên máy mà bản đi kèm không có (theo tên); None nếu không đọc được."""
    b = controls(bundled_text)
    root = _root(device_text)
    if b is None or root is None:
        return None
    return [c for c in root.iter("Control") if c.get("name") and c.get("name") not in b]


def merge(bundled_text, device_text):
    """Bản đi kèm + control thừa của bản trên máy, chèn trước </Controls> cuối cùng.
    Giữ nguyên chữ và kiểu xuống dòng của bản đi kèm. None nếu không đọc được / không có </Controls>."""
    extras = extra_controls(bundled_text, device_text)
    if extras is None:
        return None
    if not extras:
        return bundled_text
    end = bundled_text.rfind("</Controls>")
    if end < 0:
        return None
    nl = "\r\n" if "\r\n" in bundled_text else "\n"
    blocks = []
    for c in extras:
        c = copy.deepcopy(c)
        c.tail = None
        ET.indent(c, space="  ", level=2)
        blocks.append("    " + ET.tostring(c, encoding="unicode").replace("\n", nl))
    line_start = bundled_text.rfind("\n", 0, end) + 1
    head = bundled_text[:line_start]
    insert = "    " + _GHI_CHU + nl + nl.join(blocks) + nl + nl
    return head + insert + bundled_text[line_start:]
