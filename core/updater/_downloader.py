"""Resumable file downloader with progress callback."""
import urllib.request
from pathlib import Path
from typing import Callable, Optional


def download_with_progress(
    url:         str,
    dest:        Path,
    on_progress: Optional[Callable[[int, int], None]] = None,
    chunk_size:  int = 64 * 1024,
) -> Path:
    """
    Download *url* → *dest*. Supports HTTP Range resume via .part file.

    Args:
        url:         Direct download URL.
        dest:        Final file path.
        on_progress: Called with (downloaded_bytes, total_bytes) after each chunk.
        chunk_size:  Read chunk size in bytes.

    Returns:
        *dest* on success.

    Raises:
        Exception on network error or disk error.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")

    resume_from = part.stat().st_size if part.exists() else 0

    req = urllib.request.Request(url)
    req.add_header("User-Agent", "QuangLuuStudio-Updater/1.0")
    if resume_from:
        req.add_header("Range", f"bytes={resume_from}-")

    with urllib.request.urlopen(req, timeout=60) as resp:
        content_length = int(resp.headers.get("Content-Length", 0))
        total      = content_length + resume_from
        downloaded = resume_from
        mode       = "ab" if resume_from else "wb"

        with open(part, mode) as f:
            while True:
                block = resp.read(chunk_size)
                if not block:
                    break
                f.write(block)
                downloaded += len(block)
                if on_progress:
                    try:
                        on_progress(downloaded, total)
                    except Exception:
                        pass

    # Atomic rename
    if dest.exists():
        dest.unlink()
    part.rename(dest)
    return dest
