"""Pydantic request/response schemas cho API client-facing."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ── Activation ──
# legacy_fingerprint: fingerprint theo CÔNG THỨC CŨ (MachineGuid + MAC + tên máy
# + CPU) mà client ≤1.6.2 dùng. Client mới gửi kèm để server nhận ra "vẫn là máy
# đó" và đổi tên bản ghi sang fingerprint mới, thay vì tính thành máy thứ hai và
# báo "đã đạt giới hạn thiết bị". Bỏ field này khi không còn bản ghi cũ nào.
class ActivateRequest(BaseModel):
    code:               str
    device_fingerprint: str = Field(min_length=8, max_length=128)
    legacy_fingerprint: str | None = Field(default=None, max_length=128)
    hostname:           str | None = None
    os:                 str | None = None
    app_version:        str | None = None


class VerifyRequest(BaseModel):
    token:              str | None = None
    code:               str | None = None
    device_fingerprint: str = Field(min_length=8, max_length=128)
    legacy_fingerprint: str | None = Field(default=None, max_length=128)
    app_version:        str | None = None


class LicenseResponse(BaseModel):
    valid:          bool
    status:         str
    token:          str | None = None
    plan:           str = "standard"
    days_remaining: int | None = None
    expires_at:     datetime | None = None
    message:        str = ""


# ── Trial (dùng thử, neo theo máy) ──
class TrialRequest(BaseModel):
    device_fingerprint: str = Field(min_length=8, max_length=128)
    legacy_fingerprint: str | None = Field(default=None, max_length=128)
    hostname:           str | None = None
    os:                 str | None = None
    app_version:        str | None = None


class TrialResponse(BaseModel):
    allowed:        bool
    # epoch giây lúc máy này bắt đầu dùng thử (lần đầu tiên, không reset được).
    started_at:     float = 0.0
    days_remaining: float = 0.0
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


# ── Cloud Sync (Premium) ──
class SyncPutRequest(BaseModel):
    token:              str | None = None
    code:               str | None = None
    device_fingerprint: str = Field(min_length=8, max_length=128)
    # data: JSON string của file người dùng (server không parse nội dung).
    data:               str = Field(max_length=8_000_000)
    # updated_at: epoch giây client lúc dữ liệu thay đổi (last-write-wins).
    updated_at:         float | None = None


class SyncGetRequest(BaseModel):
    token:              str | None = None
    code:               str | None = None
    device_fingerprint: str = Field(min_length=8, max_length=128)


class SyncResponse(BaseModel):
    ok:         bool
    kind:       str = ""
    # exists=False ⇒ chưa có blob nào trên server cho (code, kind).
    exists:     bool = False
    data:       str | None = None
    version:    int = 0
    updated_at: datetime | None = None
    # stale=True khi PUT bị bỏ qua vì server có bản mới hơn (last-write-wins).
    stale:      bool = False
    message:    str = ""


# ── Hỗ trợ (kênh hai chiều khách ↔ dev) ──
# Cố tình KHÔNG bắt buộc token/license_code: người cần hỗ trợ nhất thường là
# người đang không kích hoạt được. Chống lạm dụng bằng rate-limit, không bằng
# xác thực. device_fingerprint là thứ duy nhất bắt buộc — nó là "địa chỉ" để
# trả lời về đúng máy.
class SupportTicketRequest(BaseModel):
    device_fingerprint: str = Field(min_length=8, max_length=128)
    license_code:       str | None = Field(default=None, max_length=40)
    hostname:           str | None = Field(default=None, max_length=200)
    os:                 str | None = Field(default=None, max_length=255)
    app_version:        str | None = Field(default=None, max_length=40)
    contact:            str | None = Field(default=None, max_length=120)
    category:           str = Field(default="khac", max_length=20)
    subject:            str = Field(min_length=1, max_length=200)
    body:               str = Field(min_length=1, max_length=8000)
    log_excerpt:        str | None = Field(default=None, max_length=20000)


class SupportReplyRequest(BaseModel):
    device_fingerprint: str = Field(min_length=8, max_length=128)
    ticket_code:        str = Field(min_length=1, max_length=16)
    body:               str = Field(min_length=1, max_length=8000)


class SupportInboxRequest(BaseModel):
    device_fingerprint: str = Field(min_length=8, max_length=128)
    license_code:       str | None = Field(default=None, max_length=40)


class SupportReadRequest(BaseModel):
    device_fingerprint: str = Field(min_length=8, max_length=128)
    ticket_code:        str = Field(min_length=1, max_length=16)


class SupportMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sender:     str
    body:       str
    created_at: datetime | None = None


class SupportTicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticket_code:   str
    subject:       str
    category:      str
    status:        str
    unread_client: bool = False
    created_at:    datetime | None = None
    updated_at:    datetime | None = None
    messages:      list[SupportMessageOut] = []


class SupportResponse(BaseModel):
    ok:          bool
    ticket_code: str = ""
    message:     str = ""


class SupportInboxResponse(BaseModel):
    ok:           bool = True
    unread_count: int = 0
    tickets:      list[SupportTicketOut] = []


# ── Thư viện tone cộng đồng ──
# Khác Cloud Sync (blob RIÊNG TƯ của một license): dữ liệu ở đây DÙNG CHUNG giữa
# các khách hàng, nên chỉ chứa mã video YouTube + tên bài + chuỗi tone. Không có
# gì nhận dạng được người gửi ngoài fingerprint dùng để đếm phiếu.
class ToneEntry(BaseModel):
    time:        float = 0.0
    key_display: str = Field(max_length=20)
    key_index:   int = 0
    scale:       str = Field(default="Major", max_length=20)


class ToneItem(BaseModel):
    song_key:    str = Field(min_length=11, max_length=11)
    title:       str = Field(default="", max_length=300)
    primary_key: str = Field(default="", max_length=20)
    source:      str = Field(default="auto", max_length=10)
    timeline:    list[ToneEntry] = Field(default_factory=list, max_length=300)


class ToneResult(BaseModel):
    song_key:     str
    title:        str = ""
    primary_key:  str = ""
    source:       str = "auto"
    votes:        int = 0
    payload_hash: str = ""
    timeline:     list[ToneEntry] = []


class LibraryLookupRequest(BaseModel):
    token:              str | None = None
    code:               str | None = None
    device_fingerprint: str = Field(min_length=8, max_length=128)
    keys:               list[str] = Field(default_factory=list, max_length=200)


class LibraryLookupResponse(BaseModel):
    ok:      bool = True
    results: dict[str, ToneResult] = {}
    message: str = ""


class LibraryContributeRequest(BaseModel):
    token:              str | None = None
    code:               str | None = None
    device_fingerprint: str = Field(min_length=8, max_length=128)
    items:              list[ToneItem] = Field(default_factory=list, max_length=50)


class LibraryContributeResponse(BaseModel):
    ok:       bool = True
    accepted: int = 0
    rejected: int = 0
    message:  str = ""


class LibraryReportRequest(BaseModel):
    token:              str | None = None
    code:               str | None = None
    device_fingerprint: str = Field(min_length=8, max_length=128)
    song_key:           str = Field(min_length=11, max_length=11)
    payload_hash:       str = Field(default="", max_length=64)


class LibraryReportResponse(BaseModel):
    ok:      bool = True
    message: str = ""
