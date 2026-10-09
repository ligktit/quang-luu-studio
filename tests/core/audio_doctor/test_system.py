import os

from core.audio_doctor.system import SystemProbe


def test_backup_va_ghi_giu_nguyen_byte(tmp_path):
    p = tmp_path / "Defaults.xml"
    raw = '<x name="ReleaseHardware" value="1"/>\r\né'.encode("utf-8")
    p.write_bytes(raw)
    s = SystemProbe()
    text = s.read_text(str(p))
    bak = s.backup(str(p))
    assert os.path.basename(bak).startswith("Defaults.xml.bak-")
    s.write_text(str(p), text.replace('value="1"', 'value="0"'))
    assert p.read_bytes() == raw.replace(b'value="1"', b'value="0"')
    assert open(bak, "rb").read() == raw


def test_sha256_va_copy(tmp_path):
    src = tmp_path / "a.js"
    src.write_text("x", encoding="utf-8")
    dst = tmp_path / "sub" / "dir" / "a.js"
    s = SystemProbe()
    s.copy(str(src), str(dst))
    assert s.sha256(str(src)) == s.sha256(str(dst))
    assert s.sha256(str(tmp_path / "khong_co")) is None
