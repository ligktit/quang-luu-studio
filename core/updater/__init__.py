"""
core.updater — Auto-update via GitHub Releases.

Usage:
    from core.updater import check_and_notify_update
    import threading
    threading.Thread(target=check_and_notify_update, daemon=True).start()
"""
import logging
import weakref

log = logging.getLogger(__name__)

from core.updater._version_check import check_latest_release, is_newer
from core.updater._downloader import download_with_progress
from core.updater._verifier import verify_sha256
from core.updater._installer import run_installer
from core.config import _get_data_dir


def check_and_notify_update(on_update_available=None) -> None:
    """
    Check GitHub for a newer release. If found, call on_update_available(release_info).
    Should run in a background thread — does network I/O.

    Args:
        on_update_available: Callable[[ReleaseInfo], None] — called on the calling thread
                             (caller must marshal to Qt main thread if needed).
    """
    release = check_latest_release()
    if release is None:
        log.info("Update check: no release found or API unreachable")
        return
    if not is_newer(release.version):
        log.info("Update check: already up to date (%s)", release.version)
        return

    log.info("New version available: %s", release.version)

    if on_update_available:
        try:
            on_update_available(release)
        except Exception as e:
            log.warning("on_update_available callback failed: %s", e)


def download_and_install(release, on_progress=None, on_error=None, silent=False) -> None:
    """
    Download the installer for *release*, verify SHA256, then run it.
    Intended to run in a background thread.

    Args:
        release:     ReleaseInfo from check_latest_release()
        on_progress: Callable[[int, int], None] (downloaded, total)
        on_error:    Callable[[str], None] called on failure
        silent:      Pass /VERYSILENT to installer
    """
    import pathlib

    dest = pathlib.Path(_get_data_dir()) / "updates" / f"Setup_{release.version}.exe"

    try:
        log.info("Downloading %s → %s", release.download_url, dest)
        dest = download_with_progress(release.download_url, dest, on_progress=on_progress)
    except Exception as e:
        log.error("Download failed: %s", e)
        if on_error:
            on_error(f"Tải xuống thất bại: {e}")
        return

    if release.sha256:
        if not verify_sha256(dest, release.sha256):
            log.error("SHA256 mismatch for %s", dest)
            dest.unlink(missing_ok=True)
            if on_error:
                on_error("Lỗi kiểm tra tính toàn vẹn file (SHA256 không khớp). Hãy thử lại.")
            return
        log.info("SHA256 verified OK")

    try:
        run_installer(dest, silent=silent)
    except Exception as e:
        log.error("Installer launch failed: %s", e)
        if on_error:
            on_error(f"Không thể khởi chạy installer: {e}")


__all__ = [
    "check_and_notify_update",
    "download_and_install",
    "check_latest_release",
    "is_newer",
]
