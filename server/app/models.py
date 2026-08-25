"""SQLAlchemy ORM models."""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id:         Mapped[int] = mapped_column(Integer, primary_key=True)
    name:       Mapped[str] = mapped_column(String(200))
    email:      Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone:      Mapped[str | None] = mapped_column(String(50), nullable=True)
    note:       Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    licenses: Mapped[list["License"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class License(Base):
    __tablename__ = "licenses"

    id:           Mapped[int] = mapped_column(Integer, primary_key=True)
    code:         Mapped[str] = mapped_column(String(40), unique=True, index=True)
    user_id:      Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    plan:         Mapped[str] = mapped_column(String(40), default="standard")
    # unused | active | revoked | expired
    status:       Mapped[str] = mapped_column(String(20), default="unused", index=True)
    max_devices:  Mapped[int] = mapped_column(Integer, default=1)
    issued_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user:    Mapped["User | None"] = relationship(back_populates="licenses")
    devices: Mapped[list["Device"]] = relationship(back_populates="license", cascade="all, delete-orphan")

    @property
    def active_devices(self) -> list["Device"]:
        return [d for d in self.devices if not d.revoked]


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("license_id", "fingerprint", name="uq_license_fingerprint"),)

    id:            Mapped[int] = mapped_column(Integer, primary_key=True)
    license_id:    Mapped[int] = mapped_column(ForeignKey("licenses.id", ondelete="CASCADE"), index=True)
    fingerprint:   Mapped[str] = mapped_column(String(128), index=True)
    hostname:      Mapped[str | None] = mapped_column(String(200), nullable=True)
    os:            Mapped[str | None] = mapped_column(String(200), nullable=True)
    app_version:   Mapped[str | None] = mapped_column(String(40), nullable=True)
    revoked:       Mapped[bool] = mapped_column(Boolean, default=False)
    first_seen:    Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen:     Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_check_in: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    license: Mapped["License"] = relationship(back_populates="devices")


class TrialGrant(Base):
    """Bản dùng thử đã cấp cho một máy, neo theo device fingerprint.

    Đây là nguồn chân lý cho hạn dùng thử: xoá activation.json dưới máy người
    dùng không reset được, vì lần xin dùng thử tiếp theo server vẫn trả về
    started_at cũ của chính fingerprint đó.
    """
    __tablename__ = "trial_grants"

    id:          Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    hostname:    Mapped[str | None] = mapped_column(String(200), nullable=True)
    os:          Mapped[str | None] = mapped_column(String(200), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    started_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen:   Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppVersion(Base):
    __tablename__ = "app_versions"

    id:                    Mapped[int] = mapped_column(Integer, primary_key=True)
    version:               Mapped[str] = mapped_column(String(40), index=True)
    channel:               Mapped[str] = mapped_column(String(20), default="stable", index=True)
    filename:              Mapped[str] = mapped_column(String(255))  # tên file trong storage_dir
    sha256:                Mapped[str] = mapped_column(String(64))
    size_bytes:            Mapped[int] = mapped_column(Integer, default=0)
    release_notes:         Mapped[str | None] = mapped_column(Text, nullable=True)
    mandatory:             Mapped[bool] = mapped_column(Boolean, default=False)
    min_supported_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    rollout_percent:       Mapped[int] = mapped_column(Integer, default=100)
    is_active:             Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    published_at:          Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("version", "channel", name="uq_version_channel"),)


class CrashReport(Base):
    __tablename__ = "crash_reports"

    id:              Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint_hash: Mapped[str] = mapped_column(String(64), index=True)  # hash(traceback) để dedupe
    device_fp:       Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    license_code:    Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    app_version:     Mapped[str | None] = mapped_column(String(40), nullable=True)
    os_info:         Mapped[str | None] = mapped_column(String(255), nullable=True)
    traceback:       Mapped[str] = mapped_column(Text)
    log_excerpt:     Mapped[str | None] = mapped_column(Text, nullable=True)
    count:           Mapped[int] = mapped_column(Integer, default=1)
    # new | seen | resolved
    status:          Mapped[str] = mapped_column(String(20), default="new", index=True)
    first_seen:      Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen:       Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SyncBlob(Base):
    """Blob đồng bộ dữ liệu người dùng (Cloud Sync — tính năng Premium).

    Mỗi (license_code, kind) là một bản ghi duy nhất chứa JSON string. Server
    không hiểu nội dung, chỉ lưu/last-write-wins theo updated_at và tăng version
    mỗi lần PUT. kind ∈ {songs, timelines, tones, scores}.
    """
    __tablename__ = "sync_blobs"
    __table_args__ = (UniqueConstraint("license_code", "kind", name="uq_sync_code_kind"),)

    id:           Mapped[int] = mapped_column(Integer, primary_key=True)
    license_code: Mapped[str] = mapped_column(String(40), index=True)
    kind:         Mapped[str] = mapped_column(String(20), index=True)
    data:         Mapped[str] = mapped_column(Text, default="")
    version:      Mapped[int] = mapped_column(Integer, default=1)
    updated_at:   Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AdminUser(Base):
    __tablename__ = "admin_users"

    id:            Mapped[int] = mapped_column(Integer, primary_key=True)
    username:      Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SupportTicket(Base):
    """Yêu cầu hỗ trợ khách gửi từ trong app (kênh HAI CHIỀU).

    Khác CrashReport ở chỗ: crash là tự động, một chiều, gộp theo hash traceback;
    còn ticket là do người viết, có hội thoại qua lại, không bao giờ gộp.

    Mọi trường định danh đều nullable: máy ĐANG KHÔNG KÍCH HOẠT ĐƯỢC chính là
    máy cần hỗ trợ nhất, nên không được đòi license_code mới cho gửi.
    """
    __tablename__ = "support_tickets"

    id:            Mapped[int] = mapped_column(Integer, primary_key=True)
    # Mã người đọc được, dạng HT-000123 — khách đọc qua điện thoại cho dev.
    ticket_code:   Mapped[str] = mapped_column(String(16), unique=True, index=True)
    license_code:  Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    device_fp:     Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    hostname:      Mapped[str | None] = mapped_column(String(200), nullable=True)
    os_info:       Mapped[str | None] = mapped_column(String(255), nullable=True)
    app_version:   Mapped[str | None] = mapped_column(String(40), nullable=True)
    contact:       Mapped[str | None] = mapped_column(String(120), nullable=True)
    # loi | huong_dan | tinh_nang | khac
    category:      Mapped[str] = mapped_column(String(20), default="khac", index=True)
    subject:       Mapped[str] = mapped_column(String(200))
    # new | open | answered | closed
    status:        Mapped[str] = mapped_column(String(20), default="new", index=True)
    log_excerpt:   Mapped[str | None] = mapped_column(Text, nullable=True)
    # True khi dev vừa trả lời mà khách chưa mở hộp thư → app hiện chấm đỏ.
    unread_client: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    messages: Mapped[list["SupportMessage"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="SupportMessage.id",
    )


class SupportMessage(Base):
    """Một lượt trong hội thoại hỗ trợ. sender ∈ {customer, dev}."""
    __tablename__ = "support_messages"

    id:         Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id:  Mapped[int] = mapped_column(ForeignKey("support_tickets.id", ondelete="CASCADE"), index=True)
    sender:     Mapped[str] = mapped_column(String(10), default="customer")
    body:       Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ticket: Mapped["SupportTicket"] = relationship(back_populates="messages")


class SharedTone(Base):
    """Một BIẾN THỂ kết quả dò tone của một bài, dùng chung cho cả mạng lưới.

    Vì sao nhiều biến thể cho một bài chứ không phải một bản duy nhất: dữ liệu do
    máy khách gửi lên là KHÔNG ĐÁNG TIN. Nếu để "ai gửi sau đè lên người trước"
    thì một máy dò sai một lần là cả mạng lưới hát sai. Thay vào đó mỗi kết quả
    khác nhau là một biến thể riêng (phân biệt bằng payload_hash), và biến thể
    thắng là biến thể được nhiều máy xác nhận nhất — bản do NGƯỜI sửa tay được
    nhân trọng số cao hơn hẳn máy dò.

    song_key luôn là YouTube video_id 11 ký tự: đường dẫn file local vừa là dữ
    liệu cá nhân vừa không khớp được giữa các máy nên không bao giờ lên đây.
    """
    __tablename__ = "shared_tones"
    __table_args__ = (UniqueConstraint("song_key", "payload_hash", name="uq_shared_song_variant"),)

    id:           Mapped[int] = mapped_column(Integer, primary_key=True)
    song_key:     Mapped[str] = mapped_column(String(24), index=True)
    # sha256 của timeline đã CHUẨN HOÁ — hai máy dò ra cùng kết quả thì trùng
    # hash và cộng phiếu, thay vì đẻ thêm bản ghi.
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    title:        Mapped[str] = mapped_column(String(300), default="")
    primary_key:  Mapped[str] = mapped_column(String(20), default="")
    timeline:     Mapped[str] = mapped_column(Text, default="[]")  # JSON string
    # auto (máy dò) | human (người sửa tay)
    source:       Mapped[str] = mapped_column(String(10), default="auto", index=True)
    votes:        Mapped[int] = mapped_column(Integer, default=0)
    reports:      Mapped[int] = mapped_column(Integer, default=0)
    # Dev ghim → thắng tuyệt đối, bất kể phiếu. Van an toàn khi có tranh chấp.
    pinned:       Mapped[bool] = mapped_column(Boolean, default=False)
    # ok | hidden (dev ẩn vì rác)
    status:       Mapped[str] = mapped_column(String(10), default="ok", index=True)
    first_seen:   Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen:    Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SharedToneVote(Base):
    """Phiếu của MỘT máy cho MỘT biến thể. Unique để một máy không bỏ phiếu hai lần.

    Không có bảng này thì một máy chạy vòng lặp gửi 1000 lần là tự phong cho
    biến thể của mình thành chân lý.
    """
    __tablename__ = "shared_tone_votes"
    __table_args__ = (UniqueConstraint("tone_id", "device_fp", "kind", name="uq_tone_vote"),)

    id:         Mapped[int] = mapped_column(Integer, primary_key=True)
    tone_id:    Mapped[int] = mapped_column(ForeignKey("shared_tones.id", ondelete="CASCADE"), index=True)
    device_fp:  Mapped[str] = mapped_column(String(128), index=True)
    # vote (xác nhận đúng) | report (báo sai)
    kind:       Mapped[str] = mapped_column(String(10), default="vote")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
