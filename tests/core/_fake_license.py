"""
Tiện ích test: ký license token bằng một cặp khoá RSA CHỈ DÙNG CHO TEST.

Ký RSA cũng chỉ là luỹ thừa modulo như lúc xác minh, nên test tự ký được mà
không cần `cryptography` — giữ requirements-test.txt gọn như cũ.

Khoá dưới đây là khoá rác sinh riêng cho test (1024-bit), KHÔNG liên quan gì tới
khoá thật của server.
"""
import base64
import hashlib
import json
import time

from core.licensing import jwt_verify

_TEST_N = int(
    "DB5F2DDE5B0C50E9CD7331F591BE6499AD2741BD67CB5A63039F4487176048CF"
    "EADAAC9E302310BD6B45168B81FB58B82E77D67B606C6EAB068F2BA8551AA029"
    "2E9E15019ACFC014F313AC3C8A8143BE719418AF71C67602C089C415363F3E07"
    "9F8ADAAEE76AF94C072F9771D3ACCC2C6E882F1A55219EBD69809390A48E5995",
    16,
)
_TEST_D = int(
    "133182ABDFBF761CDEB2E37E1EE04FA0FA7B62CF1593BF36C68C5ACC8F090795"
    "D9708485DAA456C49BEC118AE7367C8EB0D21F5BF015CCA0FE13ECB7EFAA42B4"
    "EE3C6B2962E80C6158484D48ED91AE1541AC659C69CAA10DC470EA643C1A25A1"
    "10E314C377B5F3C45783C81CBC88EDFD7E9E2F7054C1437E2433C80DFBD3DF01",
    16,
)


def use_test_key(monkeypatch):
    """Cho client tin khoá test thay vì public key thật nhúng trong app."""
    monkeypatch.setattr(jwt_verify, "LICENSE_PUBLIC_KEY_N", _TEST_N)


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _sign(message: bytes) -> bytes:
    """RSASSA-PKCS1-v1_5 + SHA-256, viết ngược lại quy trình xác minh."""
    k = (_TEST_N.bit_length() + 7) // 8
    digest_info = jwt_verify._SHA256_DER_PREFIX + hashlib.sha256(message).digest()
    padded = b"\x00\x01" + b"\xff" * (k - 3 - len(digest_info)) + b"\x00" + digest_info
    return pow(int.from_bytes(padded, "big"), _TEST_D, _TEST_N).to_bytes(k, "big")


def make_token(fingerprint, plan="standard", exp_in=7 * 86400, lexp_in=365 * 86400,
               code="AB12-CD34-EF56-GH78-XY90"):
    """Token hợp lệ giống hệt cái server thật cấp."""
    now = int(time.time())
    header = _b64u(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64u(json.dumps({
        "code": code,
        "fp": fingerprint,
        "plan": plan,
        "iat": now,
        "exp": now + int(exp_in),
        "lexp": (now + int(lexp_in)) if lexp_in else 0,
    }, separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}".encode("ascii")
    return f"{header}.{payload}.{_b64u(_sign(signing_input))}"


def tamper_plan(token, new_plan="premium"):
    """Sửa claim `plan` mà giữ nguyên chữ ký — mô phỏng user sửa activation.json."""
    header, payload, signature = token.split(".")
    raw = payload + "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(raw))
    claims["plan"] = new_plan
    forged = _b64u(json.dumps(claims, separators=(",", ":")).encode())
    return f"{header}.{forged}.{signature}"
