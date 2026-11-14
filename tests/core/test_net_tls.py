"""core/net_tls.py — HTTPS của app tin cả kho Windows lẫn bộ gốc certifi, dựng mới mỗi lần.

Ca thật (2026-10-14, 2026-10-24): máy Windows thiếu ISRG Root X1/X2 → mọi lệnh gọi
server báo CERTIFICATE_VERIFY_FAILED; sửa kho rồi mà app đang chạy vẫn lỗi vì urllib
giữ SSL context dựng từ lần gọi đầu.
"""
import os
import re
import ssl
import urllib.request

import pytest

from core import net_tls

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _subjects(ctx):
    out = []
    for cert in ctx.get_ca_certs():
        out.append(dict(x[0] for x in cert["subject"]).get("commonName", ""))
    return out


def test_tin_isrg_root_khi_kho_windows_khong_co(monkeypatch):
    # Giả máy Windows rút gọn: kho hệ thống không đóng góp chứng chỉ nào.
    monkeypatch.setattr(ssl.SSLContext, "load_default_certs", lambda self, purpose=None: None)
    names = _subjects(net_tls.https_context())
    assert "ISRG Root X1" in names
    assert "ISRG Root X2" in names


def test_van_kiem_chung_chi_va_ten_may():
    ctx = net_tls.https_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_moi_lan_goi_dung_context_moi(monkeypatch):
    seen = []
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=None, context=None: seen.append(context) or "resp")
    assert net_tls.urlopen("https://example.test/a", timeout=5) == "resp"
    net_tls.urlopen("https://example.test/b", timeout=5)
    assert all(isinstance(c, ssl.SSLContext) for c in seen)
    assert seen[0] is not seen[1], "context phải dựng lại để thấy gốc vừa được thêm vào kho"


def _core_sources():
    for dirpath, _, files in os.walk(os.path.join(ROOT, "core")):
        for name in files:
            if name.endswith(".py"):
                yield os.path.join(dirpath, name)


# Chỉ nói chuyện với http://127.0.0.1 (CDP của trình duyệt) — không có TLS.
_KHONG_TLS = {"cdp_cookies.py", "cdp_monitor.py", "net_tls.py"}


@pytest.mark.parametrize("path", sorted(_core_sources()), ids=lambda p: os.path.relpath(p, ROOT))
def test_khong_goi_thang_urllib_urlopen(path):
    if os.path.basename(path) in _KHONG_TLS:
        pytest.skip("không đi HTTPS")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert not re.search(r"urllib\.request\.urlopen\(", src), \
        "gọi HTTPS qua core.net_tls.urlopen để có certifi + context mới"
