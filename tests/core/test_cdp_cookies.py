"""Lấy cookie YouTube qua CDP — thay cho đường đọc thẳng file cookie đã bị
App-Bound Encryption chặn từ Chrome 127.
"""
import os
from unittest.mock import patch

import pytest

from core import cdp_cookies as cc


def _cookie(name, domain, **kw):
    base = {"name": name, "value": "v-" + name, "domain": domain, "path": "/",
            "secure": True, "httpOnly": False, "expires": 1800000000}
    base.update(kw)
    return base


# ── Đổi sang định dạng Netscape ──────────────────────────────────────────────
def test_chi_lay_cookie_cua_youtube_va_google():
    out = cc.to_netscape([
        _cookie("SID", ".youtube.com"),
        _cookie("NID", ".google.com"),
        _cookie("sess", ".mybank.example"),
        _cookie("tok", "facebook.com"),
    ])
    assert "SID" in out and "NID" in out
    # Không được lôi cookie của ngân hàng / mạng xã hội ra file .txt trên đĩa.
    assert "sess" not in out and "tok" not in out


def test_ten_mien_con_van_duoc_nhan():
    out = cc.to_netscape([_cookie("X", "music.youtube.com")])
    assert "music.youtube.com" in out


def test_cookie_phien_ghi_han_bang_0():
    out = cc.to_netscape([_cookie("S", ".youtube.com", expires=-1)])
    line = [ln for ln in out.splitlines() if "\t" in ln][0]
    assert line.split("\t")[4] == "0"


def test_httponly_co_tien_to_chuan():
    out = cc.to_netscape([_cookie("SID", ".youtube.com", httpOnly=True)])
    assert "#HttpOnly_.youtube.com\t" in out


def test_dau_cham_dau_ten_mien_quyet_dinh_co_include_subdomain():
    lines = {}
    for dom in (".youtube.com", "youtube.com"):
        out = cc.to_netscape([_cookie("A", dom)])
        lines[dom] = [ln for ln in out.splitlines() if "\t" in ln][0].split("\t")
    assert lines[".youtube.com"][1] == "TRUE"
    assert lines["youtube.com"][1] == "FALSE"


def test_tab_trong_gia_tri_khong_lam_vo_dinh_dang():
    out = cc.to_netscape([_cookie("A", ".youtube.com", value="x\ty\nz")])
    line = [ln for ln in out.splitlines() if "\t" in ln][0]
    assert len(line.split("\t")) == 7


def test_ytdlp_doc_lai_duoc_file_da_ghi(tmp_path):
    """Bài kiểm tra thật sự có giá trị: chính yt-dlp phải nạp được file này."""
    yt_cookies = pytest.importorskip("yt_dlp.cookies")
    path = tmp_path / "ck.txt"
    path.write_text(cc.to_netscape([
        _cookie("SID", ".youtube.com", httpOnly=True),
        _cookie("PREF", "youtube.com", secure=False, expires=-1),
    ]), encoding="utf-8", newline="\n")

    jar = yt_cookies.YoutubeDLCookieJar(str(path))
    jar.load(ignore_discard=True, ignore_expires=True)
    assert {c.name for c in jar} == {"SID", "PREF"}


# ── harvest_to_file ──────────────────────────────────────────────────────────
def test_khong_co_trinh_duyet_bat_cdp_thi_tra_none(tmp_path):
    with patch.object(cc, "fetch_cookies", return_value=[]):
        assert cc.harvest_to_file(output_path=str(tmp_path / "a.txt")) is None


def test_trinh_duyet_chua_dang_nhap_youtube_thi_khong_ghi_file(tmp_path):
    """Ghi file rỗng còn tệ hơn không ghi: lượt thử sau tưởng đã có cookie."""
    out = tmp_path / "a.txt"
    with patch.object(cc, "fetch_cookies", return_value=[_cookie("s", ".mybank.example")]):
        assert cc.harvest_to_file(output_path=str(out)) is None
    assert not out.exists()


def test_chi_co_cookie_httponly_van_duoc_luu(tmp_path):
    """Cookie đăng nhập của YouTube gần như đều là HttpOnly — đếm nhầm chúng là
    'dòng chú thích' thì vứt mất đúng cái mẻ vừa lấy được."""
    out = tmp_path / "a.txt"
    cookies = [_cookie("SID", ".youtube.com", httpOnly=True),
               _cookie("HSID", ".youtube.com", httpOnly=True)]
    with patch.object(cc, "fetch_cookies", return_value=cookies):
        assert cc.harvest_to_file(output_path=str(out)) == str(out)
    assert "SID" in out.read_text(encoding="utf-8")


def test_ghi_duoc_file_va_tra_dung_duong_dan(tmp_path):
    out = tmp_path / "sub" / "ck.txt"
    with patch.object(cc, "fetch_cookies", return_value=[_cookie("SID", ".youtube.com")]):
        assert cc.harvest_to_file(output_path=str(out)) == str(out)
    assert os.path.exists(out)


# ── Kết nối CDP ──────────────────────────────────────────────────────────────
def test_fetch_cookies_khong_no_khi_khong_tim_thay_trinh_duyet():
    with patch.object(cc, "find_browser_endpoint", return_value=(None, None)):
        assert cc.fetch_cookies() == []


def test_fetch_cookies_nuot_loi_websocket():
    """Không có trình duyệt hợp lệ cũng không được làm sập luồng tải nhạc."""
    with patch.object(cc, "find_browser_endpoint", return_value=("ws://x", "Chrome")), \
         patch.object(cc, "websocket") as ws_mod:
        ws_mod.create_connection.side_effect = OSError("refused")
        assert cc.fetch_cookies() == []
