"""
Tiện ích dòng lệnh:
  python -m app.cli hash-password <mật_khẩu>     # sinh bcrypt hash cho .env
  python -m app.cli init-db                       # tạo bảng (khi không dùng Alembic)
  python -m app.cli create-admin <user> <pass>    # tạo admin trong DB
  python -m app.cli gen-codes <n> [max_devices]   # sinh mã, in ra màn hình
  python -m app.cli import-codes <file.txt>        # import mã cũ (mỗi dòng 1 mã)
  python -m app.cli gen-license-keys [path.pem]   # sinh khoá RSA ký license
  python -m app.cli show-license-pubkey           # in lại khối public key để dán vào client
"""
import sys
from pathlib import Path

from app.db import Base, SessionLocal, engine
from app.models import AdminUser, License  # noqa: F401 (đăng ký metadata)
from app.security import hash_password
from app.services import codegen


def _gen_license_keys(path: str) -> int:
    """Sinh cặp RSA-2048, ghi private key ra file, in sẵn khối để dán vào client."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    target = Path(path)
    if target.exists():
        print(f"DỪNG: {target} đã tồn tại. Đổi khoá sẽ vô hiệu mọi token đã cấp — "
              "xoá file thủ công nếu thực sự muốn thay.")
        return 1

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    target.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    try:
        target.chmod(0o600)
    except OSError:
        pass  # Windows/dev — quyền file do OS quản

    print(f"Đã ghi private key: {target}")
    print("KHÔNG commit file này. Trỏ LICENSE_PRIVATE_KEY_PATH trong .env tới nó "
          "(hoặc dán nội dung vào LICENSE_PRIVATE_KEY).\n")
    _print_modulus_block(key.public_key().public_numbers().n)
    return 0


def _print_modulus_block(n: int) -> None:
    hex_n = f"{n:X}"
    print("Dán khối dưới đây vào LICENSE_PUBLIC_KEY_N "
          "(core/licensing/jwt_verify.py phía client):\n")
    print("BEGIN_MODULUS_BLOCK")
    for i in range(0, len(hex_n), 64):
        print(f'    "{hex_n[i:i + 64]}"')
    print("END_MODULUS_BLOCK")


def _show_license_pubkey() -> int:
    """In lại khối public key từ khoá đang được cấu hình (dùng khi khoá đã có sẵn)."""
    from app.security import _public_key

    try:
        _print_modulus_block(_public_key().public_numbers().n)
    except Exception as e:
        print(f"Không đọc được khoá ký: {e}")
        return 1
    return 0


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

    if cmd == "gen-license-keys":
        path = sys.argv[2] if len(sys.argv) > 2 else "./license_key.pem"
        return _gen_license_keys(path)

    if cmd == "show-license-pubkey":
        return _show_license_pubkey()

    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
