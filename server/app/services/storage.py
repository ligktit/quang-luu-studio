"""
Lưu trữ & phục vụ file installer (.exe).

File nằm trong settings.storage_dir. Tên file lưu dạng "{version}_{original}".
"""
import hashlib
import re
import shutil
from pathlib import Path

from app.config import settings


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def save_upload(version: str, original_filename: str, fileobj) -> tuple[str, str, int]:
    """
    Lưu file upload (file-like) vào storage_dir.
    Trả (stored_filename, sha256, size_bytes).
    """
    stored = f"{_safe_name(version)}_{_safe_name(original_filename)}"
    dest = settings.storage_path / stored
    with open(dest, "wb") as out:
        shutil.copyfileobj(fileobj, out, length=1024 * 1024)
    return stored, sha256_of(dest), dest.stat().st_size


def resolve(filename: str) -> Path | None:
    """Trả đường dẫn file trong storage_dir, chặn path traversal."""
    safe = _safe_name(Path(filename).name)
    path = settings.storage_path / safe
    if path.exists() and path.is_file():
        return path
    return None
