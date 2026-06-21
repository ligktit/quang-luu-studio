"""
Tiện ích dòng lệnh:
  python -m app.cli hash-password <mật_khẩu>     # sinh bcrypt hash cho .env
  python -m app.cli init-db                       # tạo bảng (khi không dùng Alembic)
  python -m app.cli create-admin <user> <pass>    # tạo admin trong DB
  python -m app.cli gen-codes <n> [max_devices]   # sinh mã, in ra màn hình
  python -m app.cli import-codes <file.txt>        # import mã cũ (mỗi dòng 1 mã)
"""
import sys

from app.db import Base, SessionLocal, engine
from app.models import AdminUser, License  # noqa: F401 (đăng ký metadata)
from app.security import hash_password
from app.services import codegen


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]

    if cmd == "hash-password":
        print(hash_password(sys.argv[2]))
        return 0

    if cmd == "init-db":
        Base.metadata.create_all(bind=engine)
        print("Đã tạo bảng.")
        return 0

    if cmd == "create-admin":
        username, password = sys.argv[2], sys.argv[3]
        with SessionLocal() as db:
            existing = db.query(AdminUser).filter_by(username=username).first()
            if existing:
                existing.password_hash = hash_password(password)
            else:
                db.add(AdminUser(username=username, password_hash=hash_password(password)))
            db.commit()
        print(f"Admin '{username}' đã sẵn sàng.")
        return 0

    if cmd == "gen-codes":
        n = int(sys.argv[2])
        max_devices = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        with SessionLocal() as db:
            for code in codegen.generate_codes(n):
                db.add(License(code=code, max_devices=max_devices, status="unused"))
                print(code)
            db.commit()
        return 0

    if cmd == "import-codes":
        with open(sys.argv[2], encoding="utf-8") as f:
            codes = [line.strip().upper() for line in f if line.strip() and "-" in line]
        added = 0
        with SessionLocal() as db:
            for code in codes:
                if not codegen.validate_structure(code):
                    continue
                if db.query(License).filter_by(code=code).first():
                    continue
                db.add(License(code=code, max_devices=1, status="unused"))
                added += 1
            db.commit()
        print(f"Đã import {added} mã.")
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
