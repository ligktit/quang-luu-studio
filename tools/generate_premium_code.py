"""
Sinh activation code PREMIUM *offline* cho Quang Lưu Studio.

Mã Premium dùng checksum tính bằng PREMIUM_SECRET_KEY (KHÁC secret của mã
Standard), nên app kích hoạt được Premium mà KHÔNG cần server.

Secret PHẢI GIỐNG core/activation.py:PREMIUM_SECRET_KEY. Override qua env
QUANGLUU_STUDIO_PREMIUM_SECRET nếu đã đổi.

Dùng: python tools/generate_premium_code.py [số lượng]
"""
import hashlib
import os
import random
import string
import sys

PREMIUM_SECRET_KEY = os.environ.get(
    "QUANGLUU_STUDIO_PREMIUM_SECRET",
    "14476200f1a7736b05c54df0c08909f4cea134cf017543325c32f5b1f64d0a74",
)


def generate_premium_code():
    while True:
        groups = [
            "".join(random.choices(string.ascii_uppercase, k=2))
            + "".join(random.choices(string.digits, k=2))
            for _ in range(4)
        ]
        base = "-".join(groups)
        chk = hashlib.md5((base + PREMIUM_SECRET_KEY).encode()).hexdigest()[:4].upper()
        # Mỗi nhóm (kể cả checksum) phải có cả chữ và số.
        if any(c.isalpha() for c in chk) and any(c.isdigit() for c in chk):
            return f"{base}-{chk}"


def main():
    count = 1
    if len(sys.argv) > 1:
        try:
            count = int(sys.argv[1])
        except ValueError:
            pass
    seen = set()
    while len(seen) < count:
        seen.add(generate_premium_code())
    for code in seen:
        print(code)


if __name__ == "__main__":
    main()
