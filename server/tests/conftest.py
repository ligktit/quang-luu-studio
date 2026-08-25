"""Pytest fixtures — chạy server trên SQLite tạm, không cần Postgres."""
import os
import tempfile

# Phải set env TRƯỚC khi import app.* (config đọc env lúc import).
_TMP_DB = os.path.join(tempfile.gettempdir(), "qls_test.db")
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)
os.environ["DEBUG"] = "true"  # secure-cookie=off để TestClient (http) giữ session admin
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"

# Khoá ký license dùng riêng cho test — sinh mới mỗi lần chạy, không đụng khoá thật.
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

_TEST_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
os.environ["LICENSE_PRIVATE_KEY"] = _TEST_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode("ascii")
# Secret HS256 cũ vẫn set để test được nhánh chấp nhận token legacy.
os.environ["LICENSE_SECRET"] = "test_license_secret"
os.environ["SESSION_SECRET"] = "test_session_secret"
os.environ["CODE_SECRET"] = "test_code_secret"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "testpass"
os.environ["GRACE_DAYS"] = "7"
os.environ["STORAGE_DIR"] = os.path.join(tempfile.gettempdir(), "qls_test_releases")
# Rate limiter đếm theo IP và dùng chung cho cả phiên test — nới ra để giới hạn
# thật (20/phút) không làm hỏng các test không liên quan.
os.environ["RATE_LIMIT_ACTIVATE"] = "10000/minute"
os.environ["RATE_LIMIT_VERIFY"] = "10000/minute"
os.environ["RATE_LIMIT_CRASH"] = "10000/minute"
os.environ["RATE_LIMIT_SUPPORT"] = "10000/minute"
os.environ["RATE_LIMIT_LIBRARY"] = "10000/minute"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def _fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def admin_client(client):
    client.post("/admin/login", data={"username": "admin", "password": "testpass"})
    return client
