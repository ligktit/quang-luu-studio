"""
Client HTTP cho server license (stdlib urllib). Quản lý token cache trong
activation.json + offline grace.

NGUYÊN TẮC: mọi quyền của app đều suy ra từ CLAIMS ĐÃ XÁC MINH CHỮ KÝ của
license token, không bao giờ từ field thô trong activation.json. Sửa tay file
cache chỉ làm token hỏng chữ ký → app coi như chưa kích hoạt.

Cache keys (merge vào activation.json):
  license_code        : mã đã kích hoạt (tiện hiển thị/gửi kèm crash report)
  license_token       : JWT RS256 server cấp — NGUỒN CHÂN LÝ duy nhất
  device_fingerprint  : fingerprint máy lúc kích hoạt (tiện debug)
  last_verify_ts      : epoch — lần verify online gần nhất (chỉ để hiển thị)

Các field cũ (license_plan, grace_until_ts, license_expires_ts) không còn được
đọc: chúng nằm sẵn trong claims của token và ở đó thì không sửa được.
"""
import json
import logging
import time
import urllib.error
import urllib.request

from core.config import DEFAULT_LICENSE_SERVER_URL, ACTIVATION_FILE, AppConfig
from core.licensing import jwt_verify
from core.licensing.device import device_info, get_fingerprint, legacy_fingerprint
from core.version import __version__

log = logging.getLogger(__name__)

_TIMEOUT = 10

# Memo claims theo chuỗi token để khỏi verify chữ ký lại mỗi lần hỏi quyền.
_claims_memo: tuple[str, dict | None] = ("", None)


# ── Cấu hình server ──
def server_url() -> str:
    """
    URL server license.

    app_config.json chỉ được phép TRỎ SANG server khác, không được phép tắt hẳn
    licensing: bỏ trống thì rơi về hằng số biên dịch trong code. Nếu không, chỉ
    cần xoá một dòng trong file cạnh exe là app tụt về chế độ không kiểm tra.
    """
    configured = str(AppConfig.get("license_server_url", "") or "").strip()
    return (configured or DEFAULT_LICENSE_SERVER_URL).rstrip("/")


def server_configured() -> bool:
    return bool(server_url())


# ── Cache (activation.json) ──
def _load() -> dict:
    try:
        with open(ACTIVATION_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(updates: dict) -> None:
    data = _load()
    data.update(updates)
    try:
        with open(ACTIVATION_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        log.warning("Không lưu được license cache: %s", e)


def cached_code() -> str:
    """Mã kích hoạt còn trong cache (rỗng nếu chưa có).

    KHÔNG phải nguồn quyền — quyền luôn đọc từ claims đã xác minh chữ ký. Mã chỉ
    dùng để check-in lại khi token mất, và để điền sẵn ô nhập cho người dùng.
    """
    return str(_load().get("license_code") or "")


def clear_license_cache(keep_code: bool = False) -> None:
    """Xoá phần license khỏi cache — dùng khi bị thu hồi/hết hạn/token hỏng.

    Giữ lại trial_start để việc mất license không mở lại được bản dùng thử.

    keep_code=True: giữ lại `license_code`. Dùng khi máy chỉ MẤT TOKEN chứ chưa
    chắc mất quyền. Mã không cấp thêm quyền gì, nhưng giữ nó thì client còn
    đường check-in lại bằng mã và ô nhập điền sẵn cho khách — thay vì bắt họ đi
    tìm lại tờ giấy ghi mã.
    """
    global _claims_memo
    _claims_memo = ("", None)
    data = _load()
    keys = [
        "license_token", "device_fingerprint", "last_verify_ts",
        # field của các bản cũ — dọn luôn cho sạch
        "license_plan", "grace_until_ts", "license_expires_ts",
        "activation_date", "activation_timestamp", "plan",
    ]
    if not keep_code:
        keys += ["license_code", "activation_code"]
    for key in keys:
        data.pop(key, None)
    try:
        with open(ACTIVATION_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        log.warning("Không xoá được license cache: %s", e)


def verified_claims() -> dict | None:
    """
    Claims của token trong cache, CHỈ khi:
      1. chữ ký RS256 khớp public key nhúng trong app, và
      2. claim `fp` khớp fingerprint của chính máy này.

    Trả None nếu thiếu token, chữ ký sai, hoặc file bị bê từ máy khác sang.
    KHÔNG kiểm hạn ở đây — xem is_grace_valid().
    """
    global _claims_memo
    token = str(_load().get("license_token") or "")
    if not token:
        return None

    memo_token, memo_claims = _claims_memo
    if memo_token == token:
        return memo_claims

    claims = jwt_verify.verify(token)
    if claims is not None and claims.get("fp") != get_fingerprint():
        log.warning("License token thuộc về máy khác — bỏ qua")
        claims = None

    _claims_memo = (token, claims)
    return claims


def _store_from_response(code: str, fingerprint: str, body: dict) -> bool:
    """Lưu token server trả về. Trả False nếu token không tự xác minh được."""
    token = body.get("token") or ""
    claims = jwt_verify.verify(token)
    if claims is None:
        log.error("Server trả token không xác minh được — từ chối lưu")
        return False
    if claims.get("fp") != fingerprint:
        log.error("Server trả token cho máy khác — từ chối lưu")
        return False

    global _claims_memo
    _claims_memo = ("", None)
    _save({
        "license_code": claims.get("code") or code,
        "license_token": token,
        "device_fingerprint": fingerprint,
        "last_verify_ts": int(time.time()),
    })
    return True


# ── HTTP ──
def _legacy_fp() -> str | None:
    """
    Fingerprint theo công thức cũ, gửi kèm mọi request để server nhận ra máy đã
    kích hoạt từ trước. None khi máy vốn đã dùng công thức cũ (không đọc được
    MachineGuid) — lúc đó hai giá trị trùng nhau, gửi thừa không có ý nghĩa gì.
    """
    try:
        legacy = legacy_fingerprint()
        return legacy if legacy != get_fingerprint() else None
    except Exception as e:  # noqa: BLE001 — không được để chặn đường kích hoạt
        log.debug("legacy fingerprint unavailable: %s", e)
        return None


def _post(path: str, payload: dict) -> tuple[int, dict]:
    url = f"{server_url()}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": f"QuangLuuStudio/{__version__}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}
    except Exception as e:  # network down
        log.info("License server unreachable: %s", e)
        return 0, {}


# ── API công khai ──
def activate_online(code: str) -> dict:
    """
    Kích hoạt online + ràng máy. Trả {success, error, days_remaining}.
    """
    code = code.strip().upper()
    fp = get_fingerprint()
    info = device_info()
    status, body = _post("/api/v1/activate", {
        "code": code,
        "device_fingerprint": fp,
        "legacy_fingerprint": _legacy_fp(),
        "hostname": info["hostname"],
        "os": info["os"],
        "app_version": __version__,
    })

    if status == 0:
        return {"success": False, "error":
                "Không kết nối được máy chủ. Lần kích hoạt đầu tiên cần internet — "
                "kiểm tra mạng rồi thử lại."}
    if status == 200 and body.get("valid"):
        if not _store_from_response(code, fp, body):
            return {"success": False, "error":
                    "Máy chủ trả về giấy phép không hợp lệ. Vui lòng liên hệ hỗ trợ."}
        return {"success": True, "error": "", "days_remaining": body.get("days_remaining")}
    return {"success": False, "error": body.get("message", "Mã không hợp lệ.")}


# Trạng thái server trả về nghĩa là "máy này không còn quyền" → xoá token ngay,
# không chờ hết grace.
#
# KHÔNG có "invalid" trong tập này, dù server vẫn dùng trạng thái đó. Lý do:
# "invalid" là thùng rác gom cả token quá hạn, body lỗi lạ, JSON hỏng — tức là
# những tình huống TẠM THỜI. Token thật sự bị giả mạo đã chết ở bước xác minh
# chữ ký dưới máy rồi, không cần server nói mới biết.
_TERMINAL_STATUSES = frozenset({"revoked", "expired", "not_activated"})


def verify_online() -> dict:
    """
    Check-in: xác nhận license còn hiệu lực. Cập nhật token (đẩy grace) nếu OK.
    Trả {success, status, error, http}. status: active|revoked|expired|
    not_activated|offline. `http` là mã HTTP thật (0 = không nối được máy chủ)
    để caller phân biệt "mạng chết" với "server đã trả lời".

    NGUYÊN TẮC: chỉ xoá license khi server NÓI RÕ máy này hết quyền (401/403 kèm
    trạng thái trong _TERMINAL_STATUSES). Mọi thứ khác — mất mạng, 429 quá tải,
    5xx, JSON hỏng — đều coi như offline và GIỮ NGUYÊN cache. Một cú 502 lúc
    deploy server từng đủ để đá hàng loạt máy ra màn hình kích hoạt.
    """
    cache = _load()
    token = cache.get("license_token")
    code = cache.get("license_code")
    fp = get_fingerprint()
    if not (token or code):
        return {"success": False, "status": "not_activated", "http": 0,
                "error": "Chưa kích hoạt online."}

    status, body = _post("/api/v1/license/verify", {
        "token": token,
        "code": code,
        "device_fingerprint": fp,
        "legacy_fingerprint": _legacy_fp(),
        "app_version": __version__,
    })

    if status == 0:
        return {"success": False, "status": "offline", "http": 0,
                "error": "Không kết nối được máy chủ."}
    if status == 200 and body.get("valid"):
        if not _store_from_response(code or "", fp, body):
            # Server sống nhưng trả token không xác minh được (sai khoá ký?).
            # Không phải lỗi của máy này → không xoá gì, để lần sau thử lại.
            log.error("Máy chủ trả giấy phép không xác minh được — giữ nguyên cache")
            return {"success": False, "status": "offline", "http": status,
                    "error": "Máy chủ trả về giấy phép không hợp lệ."}
        return {"success": True, "status": "active", "http": status, "error": ""}

    result_status = str(body.get("status") or "")
    if status in (401, 403) and result_status in _TERMINAL_STATUSES:
        log.warning("Máy này không còn quyền (%s) — xoá token, giữ lại mã", result_status)
        clear_license_cache(keep_code=True)
        return {"success": False, "status": result_status, "http": status,
                "error": body.get("message", "")}

    log.info("Check-in không thành công (http=%s status=%s) — giữ nguyên cache, thử lại sau",
             status, result_status or "?")
    return {"success": False, "status": "offline", "http": status,
            "error": body.get("message", "")}


def startup_reconcile() -> None:
    """
    Chạy MỘT lần lúc khởi động, trước cổng kích hoạt. Hai việc:

    1. Máy nâng cấp từ bản cũ giữ token HS256 mà bản mới không xác minh được →
       đổi lấy token RS256 (server vẫn đọc được token cũ).
    2. Máy có token thật nhưng ĐÃ QUÁ GRACE (mất mạng nhiều ngày, hoặc lâu không
       mở app) → xin token mới. Trước đây bước này bị bỏ qua vì verified_claims()
       không kiểm hạn, nên máy bị đá thẳng ra màn hình kích hoạt DÙ ĐANG CÓ MẠNG
       và license còn hạn cả trăm ngày. Đó là nguồn gốc của "dùng vài ngày lại
       bị đá ra".

    Mất mạng thì GIỮ NGUYÊN cache: cổng kích hoạt vẫn chặn (không có đường lui
    offline), nhưng lần mở app sau có mạng là tự khôi phục, không bắt gõ lại mã.
    """
    cache = _load()
    if not (cache.get("license_token") or cache.get("license_code")):
        return

    claims = verified_claims()
    if claims is not None and is_grace_valid():
        return  # token còn hiệu lực, không cần hỏi server

    if claims is None:
        log.info("Token license không xác minh được — thử đổi token mới từ máy chủ")
    else:
        log.info("Token hết hạn grace — xin gia hạn từ máy chủ")

    result = verify_online()
    if result.get("success"):
        return

    if result.get("http") == 0:
        log.warning("Không kết nối được máy chủ để gia hạn — giữ cache, sẽ thử lại lần sau")
        return

    if result.get("status") in _TERMINAL_STATUSES:
        return  # verify_online đã xoá token, giữ lại mã

    if claims is None:
        # Server đã trả lời mà token vẫn không dùng được, và bản thân token cũng
        # không tự xác minh được → nó vô dụng, bỏ đi cho sạch (vẫn giữ mã).
        log.warning("Máy chủ không nhận token này — xoá token, giữ lại mã")
        clear_license_cache(keep_code=True)


# ── Trial (neo theo máy ở server) ──
def start_trial_online() -> dict:
    """
    Xin/khôi phục bản dùng thử cho máy này. Trả {success, started_at,
    days_remaining, error}.

    Server nhớ fingerprint nên xoá dữ liệu dưới máy không xin lại được lần hai.
    """
    fp = get_fingerprint()
    info = device_info()
    status, body = _post("/api/v1/trial/start", {
        "device_fingerprint": fp,
        "legacy_fingerprint": _legacy_fp(),
        "hostname": info["hostname"],
        "os": info["os"],
        "app_version": __version__,
    })

    if status == 0:
        return {"success": False, "error":
                "Không kết nối được máy chủ. Bản dùng thử cần internet để bắt đầu."}
    if status == 200 and body.get("allowed"):
        return {
            "success": True,
            "started_at": float(body.get("started_at") or time.time()),
            "days_remaining": float(body.get("days_remaining") or 0.0),
            "error": "",
        }
    return {
        "success": False,
        "started_at": float(body.get("started_at") or 0.0),
        "days_remaining": 0.0,
        "error": body.get("message", "Máy này đã dùng hết thời gian dùng thử."),
    }


# ── Trạng thái cho ActivationManager ──
def has_online_license() -> bool:
    """Có license token hợp lệ về mặt chữ ký và đúng máy này."""
    return verified_claims() is not None


def current_plan() -> str:
    """Tier lấy từ claim đã xác minh chữ ký (standard|premium)."""
    claims = verified_claims()
    if not claims:
        return "standard"
    return str(claims.get("plan") or "standard").lower()


def is_grace_valid() -> bool:
    """Còn trong cửa sổ grace (verify online gần đây) và license chưa hết hạn."""
    claims = verified_claims()
    if not claims:
        return False
    now = time.time()
    grace_until = int(claims.get("exp") or 0)
    lic_exp = int(claims.get("lexp") or 0)
    if grace_until and now >= grace_until:
        return False
    if lic_exp and now >= lic_exp:
        return False
    return True


def in_license_term() -> bool:
    """
    License CHƯA tới hạn thật (theo claim đã ký) — kể cả khi grace đã hết.

    Dùng để phân biệt hai chuyện người dùng thấy giống nhau nhưng hoàn toàn khác
    nhau: "giấy phép của bạn đã hết hạn, mua tiếp đi" và "app chưa gọi được máy
    chủ mấy hôm nay, bật mạng lên là xong".
    """
    claims = verified_claims()
    if not claims:
        return False
    lexp = int(claims.get("lexp") or 0)
    return (not lexp) or time.time() < lexp


def days_since_verify() -> float:
    """Số ngày kể từ lần check-in online gần nhất (0 nếu chưa từng)."""
    try:
        ts = float(_load().get("last_verify_ts") or 0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, (time.time() - ts) / 86400) if ts else 0.0


def license_expires_ts() -> int:
    claims = verified_claims()
    return int(claims.get("lexp") or 0) if claims else 0


def days_remaining() -> int:
    exp = license_expires_ts()
    if not exp:
        return 9999  # vĩnh viễn
    return max(0, int((exp - time.time()) / 86400))
