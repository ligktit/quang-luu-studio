"""Pytest fixtures — chạy server trên SQLite tạm, không cần Postgres."""
import os
import tempfile

# Phải set env TRƯỚC khi import app.* (config đọc env lúc import).
_TMP_DB = os.path.join(tempfile.gettempdir(), "qls_test.db")
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)
os.environ["DEBUG"] = "true"  # secure-cookie=off để TestClient (http) giữ session admin
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ["LICENSE_SECRET"] = "test_license_secret"
os.environ["SESSION_SECRET"] = "test_session_secret"
os.environ["CODE_SECRET"] = "test_code_secret"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "testpass"
os.environ["GRACE_DAYS"] = "7"
os.environ["STORAGE_DIR"] = os.path.join(tempfile.gettempdir(), "qls_test_releases")

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
