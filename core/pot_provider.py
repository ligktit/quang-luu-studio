"""
Nạp "PO Token provider" cho yt-dlp để tải YouTube mà KHÔNG cần tài khoản/cookie.

Vì sao cần: từ 2025 YouTube đòi "GVS PO Token" cho các client họ web/tv, và tới
2026 thì cả họ android cũng bị siết (`android_vr` chỉ còn format 18 nếu thiếu
token). Không có PO Token thì yt-dlp bỏ hết định dạng → "Requested format is not
available", ép lấy thì tải về dính 403. PO Token KHÔNG phải cookie: nó chứng minh
"yêu cầu đến từ một trình duyệt thật", không chứng minh "tôi là ai" — nên sinh
được nó mà không cần bất kỳ tài khoản YouTube nào. Đúng thứ máy khách cần.

Cách làm: dùng bgutil POT provider bản viết bằng Rust (1 file .exe, KHÔNG cần
Node.js) chạy ở chế độ CLI — yt-dlp gọi nó mỗi lần cần token, không có tiến trình
nền nên không tranh cổng và không để lại tiến trình mồ côi khi app tắt đột ngột.

Vì sao TẢI LÚC CHẠY chứ không đóng gói vào bộ cài:
  1. Giấy phép: bgutil provider là GPL-3.0. Đóng gói vào bộ cài của một sản phẩm
     thương mại sẽ kéo theo nghĩa vụ GPL. Tải về máy khách rồi gọi như một chương
     trình riêng thì không phát hành lại mã GPL nào.
  2. Dung lượng: binary ~44MB, gói vào sẽ phá yêu cầu "bản Nhẹ phải nhẹ".
  3. Vá được không cần cài lại app (giống cơ chế `core/ytdlp_update.py`).

Thiếu provider = SUY GIẢM ÊM, không phải lỗi: plugin trả
`PoTokenProviderRejectedRequest`, thang client trong `core/ytdlp_support.py` vẫn
chạy tiếp xuống họ android như trước.
"""
import io
import os
import json
import time
import shutil
import hashlib
import logging
import zipfile
import tempfile
import urllib.request

from core.config import AppConfig, DATA_DIR

log = logging.getLogger(__name__)

# ── Phiên bản ghim ───────────────────────────────────────────────────────────
# Ghim cứng cả phiên bản lẫn sha256: máy khách tải binary từ Internet nên phải
# biết chính xác mình mong đợi cái gì. Muốn nâng cấp thì sửa cả 4 hằng số.
POT_VERSION = "0.8.1"
_RELEASE_BASE = (
    "https://github.com/jim60105/bgutil-ytdlp-pot-provider-rs/releases/download/"
    "v" + POT_VERSION
)
BINARY_URL = _RELEASE_BASE + "/bgutil-pot-windows-x86_64.exe"
BINARY_SHA256 = "25d6b05c79176aa792454c3d1727922ca47e56cf11cb1e866615d751819b14a0"
PLUGIN_URL = _RELEASE_BASE + "/bgutil-ytdlp-pot-provider-rs.zip"
PLUGIN_SHA256 = "99fd83b98fa93b193d6a3b69dc74410d76e7a2b889868c54d16121cac9060344"

# ── Đường dẫn ────────────────────────────────────────────────────────────────
POT_DIR = os.path.join(DATA_DIR, "pot")
BINARY_PATH = os.path.join(POT_DIR, "bgutil-pot.exe")
# Thư mục plugin trỏ cho yt-dlp. Lưu ý bố cục: yt-dlp duyệt các THƯ MỤC CON của
# đường dẫn được khai báo rồi mới tìm `yt_dlp_plugins/` bên trong mỗi cái
# (`plugins.candidate_plugin_paths` → `candidate_path.iterdir()`), nên phải có
# một tầng trung gian `bgutil/`, không được đổ thẳng `yt_dlp_plugins/` vào đây.
PLUGIN_DIR = os.path.join(POT_DIR, "plugins")
_PLUGIN_PKG_DIR = os.path.join(PLUGIN_DIR, "bgutil")
STAMP_FILE = os.path.join(DATA_DIR, "pot_provider.json")

RETRY_INTERVAL_SEC = 24 * 3600
_DOWNLOAD_TIMEOUT = 120
_MAX_DOWNLOAD_BYTES = 120 * 1024 * 1024


# ── Trạng thái ───────────────────────────────────────────────────────────────

def is_enabled():
    """Kỹ thuật có thể tắt hẳn cơ chế này trong app_config.json."""
    return bool(AppConfig.get("youtube_pot_enabled", True))


def cli_path():
    """Đường dẫn binary sinh PO Token, hoặc None nếu chưa có."""
    if not is_enabled():
        return None
    return BINARY_PATH if os.path.isfile(BINARY_PATH) else None


def plugin_dir():
    """Thư mục plugin để đưa vào `yt_dlp.globals.plugin_dirs`, hoặc None."""
    if not is_enabled():
        return None
    marker = os.path.join(_PLUGIN_PKG_DIR, "yt_dlp_plugins", "extractor", "getpot_bgutil.py")
    return PLUGIN_DIR if os.path.isfile(marker) else None


def is_available():
    """Đủ cả plugin lẫn binary thì mới thực sự sinh được token."""
    return bool(cli_path() and plugin_dir())


def installed_version():
    return _read_stamp().get("version")


def describe():
    """Một dòng cho log/chẩn đoán."""
    if not is_enabled():
        return "PO Token provider: da tat trong app_config.json"
    if is_available():
        return "PO Token provider: san sang (bgutil %s)" % (installed_version() or "?")
    missing = []
    if not cli_path():
        missing.append("binary")
    if not plugin_dir():
        missing.append("plugin")
    return "PO Token provider: CHUA co (%s) - tam dung client android" % ", ".join(missing)


# ── Tải về ───────────────────────────────────────────────────────────────────

def _download(url, expected_sha256, timeout):
    """Tải và kiểm sha256. Trả bytes, hoặc None nếu hỏng."""
    request = urllib.request.Request(
        url, headers={"User-Agent": "QuangLuuStudio/pot-provider"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read(_MAX_DOWNLOAD_BYTES + 1)
    if len(payload) > _MAX_DOWNLOAD_BYTES:
        log.error("Tệp POT provider lớn bất thường — huỷ")
        return None
    digest = hashlib.sha256(payload).hexdigest()
    if digest != expected_sha256:
        log.error("Sai mã băm sha256 khi tải %s — huỷ (nhận %s)", url, digest[:16])
        return None
    return payload


def _install_binary(payload):
    """Ghi binary theo kiểu nguyên tử: file tạm cùng thư mục rồi os.replace."""
    os.makedirs(POT_DIR, exist_ok=True)
    fd, staging = tempfile.mkstemp(prefix=".bgutil_new_", suffix=".exe", dir=POT_DIR)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        os.replace(staging, BINARY_PATH)
    except Exception:
        try:
            os.remove(staging)
        except OSError:
            pass
        raise


def _install_plugin(payload):
    """Giải nén plugin ra thư mục tạm rồi tráo nguyên tử vào PLUGIN_DIR."""
    os.makedirs(PLUGIN_DIR, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=".bgutil_plugins_", dir=PLUGIN_DIR)
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = [
                name for name in archive.namelist()
                if name.startswith("yt_dlp_plugins/")
                and "__pycache__" not in name
                and not os.path.isabs(name)
                and ".." not in name.split("/")
            ]
            if not members:
                raise RuntimeError("goi plugin khong chua yt_dlp_plugins/")
            archive.extractall(staging, members)

        marker = os.path.join(staging, "yt_dlp_plugins", "extractor", "getpot_bgutil.py")
        if not os.path.isfile(marker):
            raise RuntimeError("goi plugin thieu getpot_bgutil.py")

        retired = _PLUGIN_PKG_DIR + ".old"
        shutil.rmtree(retired, ignore_errors=True)
        if os.path.exists(_PLUGIN_PKG_DIR):
            os.replace(_PLUGIN_PKG_DIR, retired)
        os.replace(staging, _PLUGIN_PKG_DIR)
        staging = None
        shutil.rmtree(retired, ignore_errors=True)
    finally:
        if staging:
            shutil.rmtree(staging, ignore_errors=True)


def install(timeout=_DOWNLOAD_TIMEOUT):
    """Tải + cài PO Token provider. Trả True nếu sau khi chạy xong đã dùng được.

    An toàn khi gọi lại: phần nào đã đúng phiên bản thì bỏ qua.
    """
    if not is_enabled():
        return False

    same_version = installed_version() == POT_VERSION
    need_binary = cli_path() is None or not same_version
    need_plugin = plugin_dir() is None or not same_version
    if not (need_binary or need_plugin):
        return True

    try:
        if need_plugin:
            payload = _download(PLUGIN_URL, PLUGIN_SHA256, timeout)
            if payload is None:
                return is_available()
            _install_plugin(payload)

        if need_binary:
            payload = _download(BINARY_URL, BINARY_SHA256, timeout)
            if payload is None:
                return is_available()
            _install_binary(payload)
    except Exception as exc:
        log.warning("Không cài được PO Token provider: %s", exc)
        return is_available()

    ok = is_available()
    if ok:
        _write_stamp(version=POT_VERSION)
        log.info("Đã cài PO Token provider bgutil %s → %s", POT_VERSION, POT_DIR)
    return ok


# ── Tự động cài lần đầu ──────────────────────────────────────────────────────

def _read_stamp():
    try:
        with open(STAMP_FILE, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {}


def _write_stamp(version=None):
    data = _read_stamp()
    data["last_check"] = int(time.time())
    if version:
        data["version"] = version
    try:
        os.makedirs(os.path.dirname(STAMP_FILE) or ".", exist_ok=True)
        with open(STAMP_FILE, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
    except Exception as exc:
        log.debug("Không ghi được %s: %s", STAMP_FILE, exc)


def should_install_now(now=None):
    """Có nên thử tải không: chưa có/sai phiên bản VÀ đã qua kỳ chờ thử lại."""
    if not is_enabled() or not AppConfig.get("youtube_pot_auto_download", True):
        return False
    stamp = _read_stamp()
    if is_available() and stamp.get("version") == POT_VERSION:
        return False
    last = stamp.get("last_check") or 0
    now = time.time() if now is None else now
    return (now - last) >= RETRY_INTERVAL_SEC


def maybe_auto_install():
    """Cài nếu tới hạn. An toàn khi gọi từ thread nền — nuốt mọi ngoại lệ."""
    try:
        if not should_install_now():
            return False
        _write_stamp()  # đánh dấu TRƯỚC để lỗi mạng không gây thử lại liên tục
        return install()
    except Exception as exc:
        log.debug("Bỏ qua tự cài PO Token provider: %s", exc)
        return False
