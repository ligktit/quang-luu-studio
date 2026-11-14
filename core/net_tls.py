"""
Kết nối HTTPS của app (server license/sync/support/crash, PyPI, GitHub).

Hai cái bẫy trên máy khách, đều đã gặp thật (2026-10-14, 2026-10-24):

1. Python chỉ đọc kho chứng chỉ Windows CÓ SẴN, không kích Windows tự tải gốc còn
   thiếu như trình duyệt/SChannel. Máy Windows rút gọn thiếu ISRG Root X1/X2 (gốc
   Let's Encrypt của server) → CERTIFICATE_VERIFY_FAILED "unable to get local issuer".
   → Nạp thêm bộ gốc certifi đóng gói kèm app. Vẫn giữ kho Windows để máy có
   phần mềm diệt virus/proxy công ty chèn gốc riêng không bị gãy.

2. Từ Python 3.12, `urllib.request.urlopen` không truyền context sẽ dùng một opener
   toàn cục với SSL context dựng ở lần gọi đầu — kho Windows được thêm gốc sau đó
   app vẫn không thấy cho tới khi mở lại. → Dựng context mới mỗi lần gọi (vài ms,
   các lệnh gọi đều thưa).
"""
import logging
import ssl
import urllib.request

log = logging.getLogger(__name__)


def https_context() -> ssl.SSLContext:
    """SSL context mới: kho Windows + certifi, vẫn kiểm chứng chỉ và tên máy."""
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(cafile=certifi.where())
    except Exception as e:  # noqa: BLE001 — thiếu certifi thì còn kho Windows
        log.warning("Không nạp được bộ chứng chỉ certifi: %s", e)
    return ctx


def urlopen(req, timeout):
    """Thay cho `urllib.request.urlopen(req, timeout=...)` ở mọi lệnh gọi HTTPS."""
    return urllib.request.urlopen(req, timeout=timeout, context=https_context())
