"""Integrity verification: SHA256 and Authenticode signature."""
import hashlib
import subprocess
from pathlib import Path


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_sha256(path: Path, expected: str) -> bool:
    return sha256_of(path).lower() == expected.lower()


def verify_signature(path: Path) -> bool:
    """
    Check Authenticode signature via PowerShell Get-AuthenticodeSignature.
    Returns True if signature is valid, False otherwise (including when not signed).
    """
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-NonInteractive", "-Command",
                f"(Get-AuthenticodeSignature '{path}').Status",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.stdout.strip() == "Valid"
    except Exception:
        return False
