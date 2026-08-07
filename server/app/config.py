"""
Server configuration — đọc toàn bộ từ biến môi trường (.env).

KHÔNG hard-code secret ở đây. Mọi giá trị nhạy cảm (LICENSE_SECRET, mật khẩu
admin, DB password) chỉ nằm trong .env trên VPS — không commit.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── App ──
    app_name: str = "Quang Lưu Studio Server"
    debug: bool = False
    base_url: str = "http://localhost:8000"  # public URL, dùng sinh download link

    # ── Database ──
    database_url: str = "postgresql+psycopg2://qls:qls@localhost:5432/qls"

    # ── Licensing ──
    # Khoá RSA ký license token (RS256). Client nhúng public key tương ứng trong
    # core/licensing/jwt_verify.py và TỰ XÁC MINH chữ ký, nên private key này là
    # thứ duy nhất ngăn người dùng tự chế token Premium.
    # Ưu tiên PEM dán thẳng vào env, sau đó mới tới file.
    # Sinh bằng: python -m app.cli gen-license-keys
    license_private_key: str = ""
    license_private_key_path: str = "./license_key.pem"
    # LEGACY: secret HMAC của cơ chế HS256 cũ. CHỈ còn dùng để ĐỌC token đã phát
    # trước khi chuyển sang RS256 (client cũ gửi lên lúc check-in). Không bao giờ
    # dùng để ký token mới. Bỏ trống khi mọi máy đã cập nhật.
    license_secret: str = ""
    # Secret tính checksum activation code — dùng chung thuật toán với client cũ.
    # Để rỗng = server tự sinh mã ngẫu nhiên không cần checksum tương thích.
    code_secret: str = "936c3f6655acc46ba5c41603446addb7e5b25df85c953d003eba554527e267e4"
    # Số ngày app được chạy offline sau lần verify online gần nhất (grace).
    grace_days: int = 7
    # Hạn license mặc định khi kích hoạt lần đầu (ngày). 0 = vĩnh viễn.
    license_duration_days: int = 365
    # Số ngày dùng thử, neo theo device fingerprint ở server (không reset được
    # bằng cách xoá file dưới máy người dùng).
    trial_days: int = 3

    # ── Admin ──
    admin_username: str = "admin"
    # Hash bcrypt của mật khẩu admin. Sinh bằng: python -m app.cli hash-password
    admin_password_hash: str = ""
    # Mật khẩu thô (CHỈ dùng dev/lần đầu) — nếu set, ưu tiên hơn hash.
    admin_password: str = ""
    # Secret ký session cookie admin.
    session_secret: str = "CHANGE_ME_session_secret"

    # ── Storage ──
    # Thư mục chứa installer .exe đã upload.
    storage_dir: str = "./storage/releases"
    max_upload_mb: int = 500

    # ── Rate limit ──
    rate_limit_activate: str = "20/minute"
    rate_limit_verify: str = "60/minute"
    rate_limit_crash: str = "30/minute"

    @property
    def storage_path(self) -> Path:
        p = Path(self.storage_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
