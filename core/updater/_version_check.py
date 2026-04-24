"""GitHub Releases API: check for newer version."""
import json
import logging
import re
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


def check_latest_release(timeout: int = 10) -> Optional[ReleaseInfo]:
    """
    Query GitHub Releases API.
    Returns ReleaseInfo for the latest release, or None on error / no update.
    """
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

    # Find .exe asset
    exe_asset = next(
        (a for a in data.get("assets", [])
         if a["name"].lower().endswith(".exe") and "setup" in a["name"].lower()),
        None,
    )
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
