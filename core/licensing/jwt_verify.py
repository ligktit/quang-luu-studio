"""
Xác minh chữ ký license token (JWT RS256) — thuần Python, KHÔNG thêm dependency.

Vì sao tự viết thay vì dùng PyJWT/cryptography: client đóng gói bằng PyInstaller,
kéo `cryptography` vào làm phình bản cài thêm ~10MB. Xác minh RSA chỉ cần luỹ
thừa modulo — `pow()` của Python đã có sẵn — cộng SHA-256 trong hashlib. Phép
tính này KHÔNG chạm vào bí mật nào (chỉ dùng public key) nên không cần chống
side-channel như khi ký.

Public key nhúng ngay dưới đây. Private key tương ứng CHỈ nằm trong .env của
server (LICENSE_PRIVATE_KEY). Đổi cặp khoá = mọi token đã cấp mất hiệu lực,
client sẽ tự check-in lại để lấy token mới.
"""
import base64
import hashlib
import hmac
import json
import logging

log = logging.getLogger(__name__)

# ── Public key của server license (RSA-2048) ──────────────────────────────────
# Khớp với private key tại /data/keys/license_key.pem trên qlstudio.duckdns.org
# (volume Docker `server_keys`), sinh ngày 2026-08-04.
#
# ⚠ Đổi khoá trên server thì PHẢI thay khối này rồi build lại client. Không khớp
# = app từ chối mọi token server cấp — hỏng rõ ràng chứ không âm thầm bỏ qua
# kiểm tra. Lấy lại khối này bằng:
#     docker compose exec api python -m app.cli show-license-pubkey
# Xem docs/LICENSING_HARDENING.md.
LICENSE_PUBLIC_KEY_N = int(
    "98E7C67C1C9FF11AC60E960BF09762518A32CCDFC3A300EF1A7DD6A387881743"
    "DFDD5A050109D9051F4AAFCF612E9054713DE970EDB2F5E5643DA8BBCC665F6E"
    "0BE06E7BB28C52064FD77C958854CE7E6A75E61D4D2F4F38EFDE658EF0943EBA"
    "96A637DF124813C26BFF5E894965801842AF7D3D8B84F92A8E342FD342DE5324"
    "0196299F2259050EA02D419577EDAE58FA8A58A0591D0D0A07AAA72F42E3C68A"
    "888841ED069C9A1DDABDBC9B789FB6E214C6F54987093596A93DC53FDACC8FFE"
    "FCE14DF6CA63A423BE11F0CAF50F8B4CD9C37744B3AD2741086643EBFE3B327D"
    "DB9A46795A22621563A89C1B0A2B09D982C8592A0764EE790D9EDF787102EFBF",
    16,
)
LICENSE_PUBLIC_KEY_E = 65537

# DigestInfo DER của SHA-256 (RFC 8017, mục 9.2 chú thích 1).
_SHA256_DER_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def _b64url_decode(segment: str) -> bytes:
    """Giải base64url của JWT (phần đệm '=' bị lược bỏ theo chuẩn)."""
    padded = segment + "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _rsa_pkcs1_v15_sha256_verify(message: bytes, signature: bytes) -> bool:
    """Xác minh RSASSA-PKCS1-v1_5 với SHA-256 (RFC 8017 mục 8.2.2)."""
    n, e = LICENSE_PUBLIC_KEY_N, LICENSE_PUBLIC_KEY_E
    k = (n.bit_length() + 7) // 8
    if len(signature) != k:
        return False

    s = int.from_bytes(signature, "big")
    if s >= n:
        return False

    encoded = pow(s, e, n).to_bytes(k, "big")

    # EM = 0x00 || 0x01 || PS (0xFF lặp lại) || 0x00 || DigestInfo
    digest_info = _SHA256_DER_PREFIX + hashlib.sha256(message).digest()
    padding_len = k - 3 - len(digest_info)
    if padding_len < 8:  # PS tối thiểu 8 byte — khoá quá ngắn
        return False
    expected = b"\x00\x01" + b"\xff" * padding_len + b"\x00" + digest_info

    return hmac.compare_digest(encoded, expected)


def verify(token: str) -> dict | None:
    """
    Trả claims nếu chữ ký hợp lệ, None nếu không.

    KHÔNG kiểm exp/lexp ở đây — caller cần phân biệt "token bị giả mạo" với
    "token thật nhưng hết hạn" để xử lý khác nhau.
    """
    if not token or not isinstance(token, str):
        return None

    parts = token.split(".")
    if len(parts) != 3:
        return None

    try:
        header = json.loads(_b64url_decode(parts[0]))
        if header.get("alg") != "RS256":
            # Chặn thẳng alg=none và mọi token HS256 cũ: client không có
            # secret HMAC nên không thể tin chúng.
            log.info("License token có alg không được chấp nhận: %s", header.get("alg"))
            return None

        signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
        if not _rsa_pkcs1_v15_sha256_verify(signing_input, _b64url_decode(parts[2])):
            log.warning("Chữ ký license token không hợp lệ")
            return None

        claims = json.loads(_b64url_decode(parts[1]))
        return claims if isinstance(claims, dict) else None
    except Exception as e:  # base64/JSON hỏng → coi như token rác
        log.info("License token không đọc được: %s", e)
        return None
