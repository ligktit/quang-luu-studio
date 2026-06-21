"""Pydantic request/response schemas cho API client-facing."""
from datetime import datetime

from pydantic import BaseModel, Field


# ── Activation ──
class ActivateRequest(BaseModel):
    code:               str
    device_fingerprint: str = Field(min_length=8, max_length=128)
    hostname:           str | None = None
    os:                 str | None = None
    app_version:        str | None = None


class VerifyRequest(BaseModel):
    token:              str | None = None
    code:               str | None = None
    device_fingerprint: str = Field(min_length=8, max_length=128)
    app_version:        str | None = None


class LicenseResponse(BaseModel):
    valid:          bool
    status:         str
    token:          str | None = None
    days_remaining: int | None = None
    expires_at:     datetime | None = None
    message:        str = ""


# ── Updates ──
class UpdateCheckResponse(BaseModel):
    """Giữ shape tương thích với core.updater._version_check.ReleaseInfo."""
    update_available: bool
    version:          str | None = None
    download_url:     str | None = None
    sha256:           str | None = None
    size_bytes:       int = 0
    release_notes:    str = ""
    mandatory:        bool = False
    published_at:     str = ""


# ── Crash ──
class CrashRequest(BaseModel):
    device_fingerprint: str | None = None
    license_code:       str | None = None
    app_version:        str | None = None
    os:                 str | None = None
    traceback:          str = Field(min_length=1, max_length=20000)
    log_excerpt:        str | None = Field(default=None, max_length=20000)


class CrashResponse(BaseModel):
    ok:        bool
    report_id: int | None = None
