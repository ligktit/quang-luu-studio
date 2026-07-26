"""GitHub Releases API: check for newer version."""
import json
import logging
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

from core.version import __version__, GITHUB_RELEASES_API

log = logging.getLogger(__name__)


@dataclass
class ReleaseInfo:
    version:      str
    tag_name:     str
    download_url: str
    sha256:       Optional[str]
    body:         str
    published_at: str
    size_bytes:   int


def _parse_semver(v: str) -> tuple:
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", v.strip())
    if not m:
        raise ValueError(f"Cannot parse version: {v!r}")
    return tuple(int(x) for x in m.groups())


def is_newer(remote: str, local: str = __version__) -> bool:
    """Return True if *remote* is strictly newer than *local*."""
    try:
        return _parse_semver(remote) > _parse_semver(local)
    except ValueError:
        return False


def _check_server_release(timeout: int = 10) -> Optional[ReleaseInfo]:
    """
    Hỏi server license/update nội bộ (khi app_config.json có 'license_server_url').
    Server đã so version + tôn trọng rollout %, chỉ trả khi có bản mới hơn.
    """
    try:
        from core.config import AppConfig
        base = str(AppConfig.get("license_server_url", "") or "").rstrip("/")
        if not base:
            return None
        try:
            from core.licensing.device import get_fingerprint
            fp = get_fingerprint()
        except Exception:
            fp = ""

        params = urllib.parse.urlencode({"version": __version__, "channel": "stable", "fingerprint": fp})
        url = f"{base}/api/v1/updates/check?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": f"QuangLuuStudio/{__version__}"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        log.warning("Server update check failed: %s", e)
        return None

    if not data.get("update_available"):
        return None
    return ReleaseInfo(
        version=data["version"],
        tag_name=f"v{data['version']}",
        download_url=data["download_url"],
        sha256=data.get("sha256"),
        body=data.get("release_notes", ""),
        published_at=data.get("published_at", ""),
        size_bytes=data.get("size_bytes", 0),
    )


def check_latest_release(timeout: int = 10) -> Optional[ReleaseInfo]:
    """
    Ưu tiên server nội bộ nếu được cấu hình; ngược lại fallback GitHub Releases.
    Returns ReleaseInfo for the latest release, or None on error / no update.
    """
    server_release = _check_server_release(timeout)
    if server_release is not None:
        return server_release

    req = urllib.request.Request(
        GITHUB_RELEASES_API,
        headers={
            "Accept":     "application/vnd.github+json",
            "User-Agent": f"QuangLuuStudio/{__version__}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        log.warning("Update check failed: %s", e)
        return None

    if data.get("prerelease") or data.get("draft"):
        return None

    # Find .exe asset khớp ĐÚNG biến thể build của máy này.
    # Release có thể chứa cả 2 file (Heavy + Light); chọn nhầm sẽ tải sai bản.
    #   - Build Heavy (có QtWebEngine) → lấy asset có "heavy" trong tên.
    #   - Build Light → lấy asset KHÔNG có "heavy".
    #   - Fallback: release cũ chỉ 1 file → lấy file setup .exe bất kỳ.
    try:
        from core.capabilities import embedded_player_available
        is_heavy = embedded_player_available()
    except Exception:
        is_heavy = False

    setup_exes = [
        a for a in data.get("assets", [])
        if a["name"].lower().endswith(".exe") and "setup" in a["name"].lower()
    ]

    def _is_heavy(a):
        return "heavy" in a["name"].lower()

    if is_heavy:
        exe_asset = next((a for a in setup_exes if _is_heavy(a)), None)
    else:
        exe_asset = next((a for a in setup_exes if not _is_heavy(a)), None)
    if exe_asset is None:  # fallback: release 1 file (không phân biệt biến thể)
        exe_asset = setup_exes[0] if setup_exes else None
    if not exe_asset:
        return None

    # Try to fetch SHA256SUMS.txt
    sha256 = None
    sha_asset = next(
        (a for a in data.get("assets", []) if a["name"] == "SHA256SUMS.txt"),
        None,
    )
    if sha_asset:
        try:
            with urllib.request.urlopen(sha_asset["browser_download_url"], timeout=timeout) as r:
                for line in r.read().decode("utf-8", errors="replace").splitlines():
                    if exe_asset["name"] in line:
                        sha256 = line.split()[0]
                        break
        except Exception:
            pass

    return ReleaseInfo(
        version=data["tag_name"].lstrip("v"),
        tag_name=data["tag_name"],
        download_url=exe_asset["browser_download_url"],
        sha256=sha256,
        body=data.get("body", ""),
        published_at=data.get("published_at", ""),
        size_bytes=exe_asset["size"],
    )
