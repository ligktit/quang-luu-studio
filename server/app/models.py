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
