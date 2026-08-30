"""
core.cdp_cookies
================
Lấy cookie YouTube từ trình duyệt ĐANG CHẠY qua Chrome DevTools Protocol, rồi
ghi ra file Netscape cho yt-dlp dùng.

Vì sao phải làm đường này thay vì `--cookies-from-browser`:

Từ Chrome 127 (và Edge/Brave cùng nhân) Google bật **App-Bound Encryption**:
khoá giải mã cookie được cột vào chính file chrome.exe, chỉ Chrome tự giải được.
yt-dlp đọc trực tiếp file `Cookies` sẽ luôn dừng ở "Failed to decrypt with
DPAPI" — và điều quan trọng nhất: **đóng trình duyệt KHÔNG cứu được**, vì đây
không phải chuyện file bị khoá mà là chuyện không có khoá giải mã. Lời khuyên
"đóng hẳn Chrome rồi thử lại" trong các bản trước vì thế đẩy người dùng vào vòng
lặp vô ích.

Cách ở đây lật ngược vấn đề: không tự giải mã nữa mà **nhờ chính trình duyệt
giải mã hộ**. Trình duyệt đang mở với cờ `--remote-debugging-port` sẽ trả cookie
đã giải mã sẵn qua lệnh CDP `Storage.getCookies`. Không cần tài khoản, không cần
đóng trình duyệt, không đụng tới file `Cookies`.

Điều kiện cần: trình duyệt đang chạy VỚI cờ `--remote-debugging-port` — đúng thứ
app vẫn gắn vào shortcut cho tính năng theo dõi CDP (tools/_apply_cdp.ps1). Máy
nào chưa bật cờ đó thì hàm trả None và người dùng được chỉ sang Firefox.
"""
import json
import os
import time
import urllib.error
import urllib.request

from core.config import DATA_DIR, CDP_DEBUG_PORT

try:
    import websocket
    _WEBSOCKET_AVAILABLE = True
except ImportError:  # pragma: no cover - môi trường thiếu websocket-client
    _WEBSOCKET_AVAILABLE = False

# Chỉ lấy cookie của các tên miền thật sự cần cho YouTube. Không quét cả kho
# cookie của người dùng: ngân hàng, email, mạng xã hội không liên quan gì ở đây
# và cũng không nên nằm trong một file .txt trên đĩa.
COOKIE_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "google.com",
    "googlevideo.com",
    "ytimg.com",
)

PORT_SCAN_SPAN = 10          # 9222..9232, cùng dải với CDPYouTubeMonitor
_HTTP_TIMEOUT = 0.3
_WS_TIMEOUT = 5.0


def default_output_path():
    return os.path.join(DATA_DIR, "youtube_cookies.txt")


# ── Tìm trình duyệt đang bật CDP ──────────────────────────────────────────────
def find_browser_endpoint(port=None):
    """(ws_url, ten_trinh_duyet) của trình duyệt đầu tiên bật CDP, hoặc (None, None).

    Dùng endpoint cấp TRÌNH DUYỆT (`/json/version`) chứ không phải cấp tab: cookie
    là tài sản của cả profile, và cách này vẫn chạy khi người dùng chưa mở tab
    YouTube nào.
    """
    start = port or CDP_DEBUG_PORT
    for p in range(start, start + PORT_SCAN_SPAN + 1):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{p}/json/version")
            with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, ConnectionRefusedError, TimeoutError, OSError):
            continue
        except Exception:
            continue
        ws_url = data.get("webSocketDebuggerUrl")
        if ws_url:
            return ws_url, data.get("Browser", "?")
    return None, None


def fetch_cookies(port=None, log_prefix="[CDP-COOKIE]"):
    """Danh sách cookie thô từ trình duyệt đang chạy, [] nếu không lấy được."""
    if not _WEBSOCKET_AVAILABLE:
        print(f"{log_prefix} Thieu thu vien websocket-client")
        return []

    ws_url, browser = find_browser_endpoint(port)
    if not ws_url:
        return []

    ws = None
    try:
        # suppress_origin: xem chú thích trong core/cdp_monitor.py — thiếu nó là
        # trình duyệt trả 403 chứ không phải sai địa chỉ.
        ws = websocket.create_connection(ws_url, timeout=_WS_TIMEOUT,
                                         suppress_origin=True)
        ws.settimeout(_WS_TIMEOUT)
        ws.send(json.dumps({"id": 1, "method": "Storage.getCookies", "params": {}}))
        deadline = time.time() + _WS_TIMEOUT
        while time.time() < deadline:
            msg = json.loads(ws.recv())
            if msg.get("id") != 1:
                continue                      # sự kiện lẻ của trình duyệt, bỏ qua
            if "error" in msg:
                print(f"{log_prefix} {browser} tu choi Storage.getCookies: "
                      f"{msg['error'].get('message', '?')}")
                return []
            cookies = msg.get("result", {}).get("cookies", []) or []
            print(f"{log_prefix} Lay duoc {len(cookies)} cookie tu {browser}")
            return cookies
    except Exception as exc:
        print(f"{log_prefix} Loi doc cookie qua CDP: {exc}")
    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
    return []


# ── Ghi ra định dạng Netscape ────────────────────────────────────────────────
def _matches_domain(domain):
    d = (domain or "").lstrip(".").lower()
    return any(d == known or d.endswith("." + known) for known in COOKIE_DOMAINS)


def to_netscape(cookies):
    """Đổi cookie kiểu CDP sang các dòng file cookie Netscape mà yt-dlp đọc được."""
    lines = [
        "# Netscape HTTP Cookie File",
        "# Quang Luu Studio - xuat qua CDP tu trinh duyet dang chay",
        "",
    ]
    for c in cookies:
        domain = c.get("domain") or ""
        if not domain or not _matches_domain(domain):
            continue
        name = c.get("name") or ""
        if not name:
            continue
        # Dấu chấm đầu tên miền = áp cho cả tên miền con; CDP giữ đúng quy ước này.
        include_sub = "TRUE" if domain.startswith(".") else "FALSE"
        path = c.get("path") or "/"
        secure = "TRUE" if c.get("secure") else "FALSE"
        # expires = -1 nghĩa là cookie phiên; Netscape ghi 0 cho loại đó.
        try:
            expires = int(float(c.get("expires", -1)))
        except (TypeError, ValueError):
            expires = -1
        if expires < 0:
            expires = 0
        value = (c.get("value") or "").replace("\t", " ").replace("\n", "")
        # yt-dlp nhận lại cờ HttpOnly qua tiền tố này (chuẩn của curl/wget).
        prefix = "#HttpOnly_" if c.get("httpOnly") else ""
        lines.append("\t".join([
            prefix + domain, include_sub, path, secure, str(expires), name, value,
        ]))
    lines.append("")
    return "\n".join(lines)


def harvest_to_file(output_path=None, port=None, log_prefix="[CDP-COOKIE]"):
    """Lấy cookie qua CDP rồi ghi ra file Netscape. Trả đường dẫn, hoặc None.

    Trả None khi không có trình duyệt nào bật CDP, hoặc profile đó chưa đăng nhập
    YouTube (không cookie nào khớp tên miền) — ghi ra file rỗng chỉ khiến lượt
    thử sau tưởng đã có cookie mà thật ra không có gì.
    """
    cookies = fetch_cookies(port=port, log_prefix=log_prefix)
    if not cookies:
        return None

    body = to_netscape(cookies)
    # Đếm theo dấu TAB chứ không theo "dòng không bắt đầu bằng #": cookie HttpOnly
    # ghi ra với tiền tố `#HttpOnly_`, mà đó lại chính là những cookie đăng nhập
    # quan trọng nhất — đếm nhầm là vứt hết cả mẻ vừa lấy được.
    kept = sum(1 for ln in body.splitlines() if "\t" in ln)
    if kept == 0:
        print(f"{log_prefix} Trinh duyet chua co cookie YouTube nao")
        return None

    path = output_path or default_output_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
    except OSError as exc:
        print(f"{log_prefix} Khong ghi duoc {path}: {exc}")
        return None

    print(f"{log_prefix} Da luu {kept} cookie YouTube vao {path}")
    return path
