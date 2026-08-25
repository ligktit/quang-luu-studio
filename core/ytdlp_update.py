"""
Cho phép app dùng bản yt-dlp MỚI HƠN bản được đóng gói trong .exe.

Vì sao cần: YouTube đổi cơ chế phát video gần như hàng tháng, còn bản yt-dlp nằm
trong .exe thì đứng yên từ lúc build. Chỉ vài tháng sau là client bắt đầu gặp
"Sign in to confirm you're not a bot" rồi "Requested format is not available"
dù cookie hoàn toàn hợp lệ — vì bản yt-dlp cũ không còn bóc được định dạng nào.

Cách làm: nếu trong `%APPDATA%\\QuangLuuStudio\\ytdlp` có một bản yt-dlp mới hơn
bản đóng gói, module này chèn một finder lên đầu `sys.meta_path` để mọi
`import yt_dlp` lấy bản mới đó. Phải dùng meta_path chứ KHÔNG phải `sys.path`:
trong bản PyInstaller, FrozenImporter đứng sẵn ở đầu `sys.meta_path` và sẽ nuốt
mọi `import yt_dlp` trước khi tới lượt `sys.path`.

Bản mới được tải từ PyPI dưới dạng wheel (yt-dlp là gói thuần Python nên chỉ cần
giải nén là chạy) — xem `download_override()`. Máy khách không cần cài Python.
"""
import io
import json
import os
import re
import shutil
import sys
import time
import zipfile
import hashlib
import tempfile
import logging
import urllib.request
from importlib.machinery import PathFinder

from core.config import AppConfig, DATA_DIR

log = logging.getLogger(__name__)

# Phiên bản yt-dlp đang đóng gói trong .exe.
# ⚠️ Bump cùng lúc với `yt-dlp>=...` trong requirements.txt mỗi lần build phát hành:
# bản nạp ngoài chỉ được dùng khi MỚI HƠN hằng số này, nếu không một bản ngoài cũ
# còn sót lại sẽ kéo tụt app sau khi build mới.
BUNDLED_YTDLP_VERSION = "2026.07.04"

# Nơi chứa bản yt-dlp nạp ngoài (giải nén thẳng, bên trong là thư mục `yt_dlp/`)
OVERRIDE_DIR = os.path.join(DATA_DIR, "ytdlp")
# Ghi lại lần kiểm tra cập nhật gần nhất (để trong DATA_DIR chứ không trong
# OVERRIDE_DIR — thư mục đó bị xoá sạch mỗi lần cập nhật)
STAMP_FILE = os.path.join(DATA_DIR, "ytdlp_update.json")

PYPI_JSON_URL = "https://pypi.org/pypi/yt-dlp/json"
AUTO_UPDATE_INTERVAL_SEC = 24 * 3600

# Phiên bản đang thực sự được dùng (None = chưa gọi activate_override())
ACTIVE_VERSION = None

_VERSION_RE = re.compile(r"""__version__\s*=\s*['"]([^'"]+)['"]""")


# ── So sánh phiên bản ────────────────────────────────────────────────────────

def parse_version(text):
    """'2026.07.04' → (2026, 7, 4). Trả tuple rỗng nếu không đọc được."""
    if not text:
        return ()
    parts = []
    for chunk in str(text).strip().split("."):
        match = re.match(r"\d+", chunk)
        if not match:
            break
        parts.append(int(match.group(0)))
    return tuple(parts)


def is_newer(candidate, reference):
    """candidate có mới hơn reference không (phiên bản không đọc được = không)."""
    left, right = parse_version(candidate), parse_version(reference)
    if not left or not right:
        return False
    return left > right


# ── Đọc bản nạp ngoài ────────────────────────────────────────────────────────

def _looks_like_ytdlp(directory):
    """Kiểm tra thư mục có đúng là một cây nguồn yt-dlp dùng được không."""
    required = (
        os.path.join("yt_dlp", "__init__.py"),
        os.path.join("yt_dlp", "version.py"),
        os.path.join("yt_dlp", "YoutubeDL.py"),
        os.path.join("yt_dlp", "extractor", "youtube"),
    )
    return all(os.path.exists(os.path.join(directory, item)) for item in required)


def read_override_version(directory=None):
    """Đọc số hiệu của bản nạp ngoài mà KHÔNG import nó."""
    directory = directory or OVERRIDE_DIR
    version_file = os.path.join(directory, "yt_dlp", "version.py")
    try:
        with open(version_file, "r", encoding="utf-8", errors="replace") as handle:
            match = _VERSION_RE.search(handle.read())
    except OSError:
        return None
    return match.group(1) if match else None


class _OverrideFinder:
    """Finder chỉ nhận `yt_dlp` và mọi module con của nó."""

    def __init__(self, directory):
        self.directory = directory
        self._roots = [directory]

    def find_spec(self, fullname, path=None, target=None):
        if fullname != "yt_dlp" and not fullname.startswith("yt_dlp."):
            return None
        if fullname == "yt_dlp":
            search = self._roots
        else:
            # Module con: đi theo __path__ của gói cha (đã trỏ vào thư mục nạp
            # ngoài) để không trộn lẫn nửa bản mới nửa bản đóng gói.
            parent = sys.modules.get(fullname.rpartition(".")[0])
            search = list(getattr(parent, "__path__", []) or [])
            if not search:
                return None
        return PathFinder.find_spec(fullname, search, target)


def activate_override(directory=None):
    """Ưu tiên bản yt-dlp nạp ngoài nếu có và mới hơn bản đóng gói.

    Trả về số hiệu bản được kích hoạt, hoặc None nếu vẫn dùng bản đóng gói.
    Phải gọi TRƯỚC lần `import yt_dlp` đầu tiên.
    """
    global ACTIVE_VERSION
    ACTIVE_VERSION = BUNDLED_YTDLP_VERSION

    directory = directory or OVERRIDE_DIR
    if not _looks_like_ytdlp(directory):
        return None

    version = read_override_version(directory)
    if not is_newer(version, BUNDLED_YTDLP_VERSION):
        log.debug("Bỏ qua yt-dlp nạp ngoài %s (không mới hơn %s)", version, BUNDLED_YTDLP_VERSION)
        return None

    if "yt_dlp" in sys.modules:
        log.warning("yt_dlp đã được import trước khi kích hoạt bản nạp ngoài — bỏ qua")
        return None

    for finder in sys.meta_path:
        if isinstance(finder, _OverrideFinder) and finder.directory == directory:
            ACTIVE_VERSION = version
            return version

    sys.meta_path.insert(0, _OverrideFinder(directory))
    ACTIVE_VERSION = version
    log.info("Dùng yt-dlp %s nạp ngoài (bản đóng gói: %s)", version, BUNDLED_YTDLP_VERSION)
    return version


def _imported_version():
    """Số hiệu của yt_dlp ĐÃ nạp trong tiến trình này (None nếu chưa import)."""
    module = sys.modules.get("yt_dlp")
    value = getattr(getattr(module, "version", None), "__version__", None)
    return value if isinstance(value, str) else None


def active_version():
    """Số hiệu yt-dlp app đang thực sự dùng.

    Ưu tiên số hiệu đọc được từ module đã nạp — chính xác tuyệt đối; chỉ khi
    chưa import lần nào mới rơi về hằng số khai báo lúc build.
    """
    return _imported_version() or ACTIVE_VERSION or BUNDLED_YTDLP_VERSION


# ── Tải bản mới từ PyPI ──────────────────────────────────────────────────────

def _fetch_pypi_metadata(timeout=20):
    request = urllib.request.Request(
        PYPI_JSON_URL, headers={"User-Agent": "QuangLuuStudio/ytdlp-update"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def latest_version(timeout=20):
    """Số hiệu yt-dlp ổn định mới nhất trên PyPI (None nếu không hỏi được)."""
    try:
        return _fetch_pypi_metadata(timeout).get("info", {}).get("version")
    except Exception as exc:
        log.warning("Không hỏi được phiên bản yt-dlp mới nhất: %s", exc)
        return None


def _python_ok(requires_python):
    """Bản mới có chạy được trên Python đang nhúng trong app không.

    Không kiểm tra thì một ngày nào đó yt-dlp bỏ hỗ trợ Python cũ, app tải về
    bản không import nổi và người dùng mất luôn tính năng tải nhạc.
    """
    if not requires_python:
        return True
    match = re.search(r">=\s*(\d+)\.(\d+)", str(requires_python))
    if not match:
        return True
    return sys.version_info[:2] >= (int(match.group(1)), int(match.group(2)))


def _pick_wheel(metadata):
    for entry in metadata.get("urls", []):
        if entry.get("packagetype") == "bdist_wheel" and entry.get("filename", "").endswith(
            "-py3-none-any.whl"
        ):
            if not _python_ok(entry.get("requires_python")):
                log.warning(
                    "yt-dlp %s cần Python %s — bỏ qua",
                    metadata.get("info", {}).get("version"), entry.get("requires_python"),
                )
                return None
            return entry
    return None


def download_override(directory=None, timeout=60):
    """Tải wheel yt-dlp mới nhất về thư mục nạp ngoài.

    Trả về số hiệu vừa tải, hoặc None nếu đã là mới nhất / tải thất bại.
    Bản vừa tải chỉ có hiệu lực từ LẦN MỞ APP KẾ TIẾP (module cũ đã nằm trong RAM).
    """
    directory = directory or OVERRIDE_DIR
    try:
        metadata = _fetch_pypi_metadata(timeout)
    except Exception as exc:
        log.warning("Không tải được thông tin yt-dlp từ PyPI: %s", exc)
        return None

    version = metadata.get("info", {}).get("version")
    current = read_override_version(directory) or _imported_version() or BUNDLED_YTDLP_VERSION
    if not is_newer(version, current):
        log.info("yt-dlp đã là bản mới nhất (%s)", current)
        return None

    wheel = _pick_wheel(metadata)
    if not wheel:
        log.warning("Không tìm thấy wheel yt-dlp %s trên PyPI", version)
        return None

    try:
        request = urllib.request.Request(
            wheel["url"], headers={"User-Agent": "QuangLuuStudio/ytdlp-update"}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except Exception as exc:
        log.warning("Tải wheel yt-dlp thất bại: %s", exc)
        return None

    expected = (wheel.get("digests") or {}).get("sha256")
    if expected and hashlib.sha256(payload).hexdigest() != expected:
        log.error("Wheel yt-dlp tải về sai mã băm sha256 — huỷ")
        return None

    parent = os.path.dirname(directory) or "."
    os.makedirs(parent, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=".ytdlp_new_", dir=parent)
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = [
                name for name in archive.namelist()
                if name.startswith("yt_dlp/") and not name.startswith("yt_dlp/__pycache__/")
            ]
            if not members:
                log.error("Wheel yt-dlp không chứa gói yt_dlp — huỷ")
                return None
            archive.extractall(staging, members)

        if not _looks_like_ytdlp(staging):
            log.error("Bản yt-dlp giải nén ra không đầy đủ — huỷ")
            return None

        retired = directory + ".old"
        shutil.rmtree(retired, ignore_errors=True)
        if os.path.exists(directory):
            os.replace(directory, retired)
        os.replace(staging, directory)
        staging = None
        shutil.rmtree(retired, ignore_errors=True)
    except Exception as exc:
        log.warning("Không thay được thư mục yt-dlp nạp ngoài: %s", exc)
        return None
    finally:
        if staging:
            shutil.rmtree(staging, ignore_errors=True)

    log.info("Đã tải yt-dlp %s — sẽ dùng từ lần mở app kế tiếp", version)
    _write_stamp(version=version)
    return version


# ── Tự động kiểm tra định kỳ ─────────────────────────────────────────────────

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


def should_check_now(now=None):
    """Đã tới hạn kiểm tra cập nhật chưa (mặc định 24 giờ/lần)."""
    if not AppConfig.get("ytdlp_auto_update", True):
        return False
    last = _read_stamp().get("last_check") or 0
    now = time.time() if now is None else now
    return (now - last) >= AUTO_UPDATE_INTERVAL_SEC


def maybe_auto_update():
    """Kiểm tra + tải bản yt-dlp mới nếu tới hạn. An toàn khi gọi từ thread nền."""
    try:
        if not should_check_now():
            return None
        _write_stamp()  # đánh dấu trước để lỗi mạng không gây thử lại liên tục
        return download_override()
    except Exception as exc:
        log.debug("Bỏ qua tự cập nhật yt-dlp: %s", exc)
        return None
