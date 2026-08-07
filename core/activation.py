"""
Quang Lưu Studio — Activation Manager
Class: ActivationManager

Kích hoạt CHỈ chạy online: server license là thẩm quyền duy nhất quyết định mã
có thật, thuộc gói nào, còn hạn không, và được cài trên mấy máy. Client không
còn thuật toán checksum cục bộ nào — nghĩa là không còn secret nào nằm trong
file exe để rút ra và tự sinh mã.

Quyền của app đọc từ claims đã xác minh chữ ký của license token
(core/licensing/client.py), không đọc field thô trong activation.json.
"""
import json
import os
import time

from core.config import ACTIVATION_FILE
from core.licensing import client as _lic
from core.licensing import trial_marker


class ActivationManager:
    """Quản lý activation code, thời hạn sử dụng, và bản dùng thử"""

    # Hạn dùng thử. Server mới là nơi chốt (settings.trial_days) — hằng này chỉ
    # dùng để hiển thị và để tính tiếp khi máy đã bắt đầu dùng thử rồi mất mạng.
    TRIAL_DURATION_DAYS = 3

    @staticmethod
    def _validate_code_structure(code):
        """Kiểm tra format của code: XXXX-XXXX-XXXX-XXXX-XXXX

        Chỉ để báo lỗi nhanh cho người gõ nhầm — KHÔNG phải bước bảo mật.
        Việc mã có tồn tại thật hay không do server trả lời.
        """
        if not code:
            return False

        code = code.strip().upper()
        parts = code.split('-')

        if len(parts) != 5:
            return False

        for part in parts:
            if len(part) != 4:
                return False
            # Mỗi phần phải có chữ và số
            if not any(c.isalpha() for c in part) or not any(c.isdigit() for c in part):
                return False

        return True

    @staticmethod
    def load_activation():
        """Load thông tin activation từ file (chỉ còn dùng cho dữ liệu dùng thử)."""
        if os.path.exists(ACTIVATION_FILE):
            try:
                with open(ACTIVATION_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    @staticmethod
    def is_activated():
        """Máy có license token hợp lệ (đúng chữ ký, đúng máy) hay không."""
        return _lic.has_online_license()

    @staticmethod
    def is_expired():
        """License hết hiệu lực: quá hạn thật, hoặc quá lâu không check-in online."""
        if not _lic.has_online_license():
            return True
        return not _lic.is_grace_valid()

    @staticmethod
    def get_days_remaining():
        """Số ngày còn lại của license."""
        if not _lic.has_online_license():
            return 0
        return _lic.days_remaining()

    @staticmethod
    def activate(code):
        """Kích hoạt app với code được cung cấp. Returns dict: {success: bool, error: str}"""
        if not ActivationManager._validate_code_structure(code):
            return {"success": False, "error": "Mã kích hoạt không hợp lệ. Vui lòng kiểm tra lại."}
        return _lic.activate_online(code)

    @staticmethod
    def needs_activation():
        """Kiểm tra xem app có cần kích hoạt không (cho phép trial qua)"""
        # Đã kích hoạt bằng code và chưa hết hạn
        if ActivationManager.is_activated() and not ActivationManager.is_expired():
            return False

        # Đang trong thời gian dùng thử
        if ActivationManager.is_trial_active():
            return False

        return True

    # ── Trial (Dùng thử) ──

    @staticmethod
    def _trial_start_ts():
        """
        Mốc bắt đầu dùng thử của máy này — lấy mốc SỚM NHẤT trong các nguồn đã
        biết (file cache + registry). Xoá một nguồn không đẩy được hạn về sau.
        0.0 nghĩa là máy chưa từng dùng thử.
        """
        candidates = []

        activation = ActivationManager.load_activation() or {}
        try:
            local = float(activation.get("trial_start") or 0)
            if local > 0:
                candidates.append(local)
        except (TypeError, ValueError):
            pass

        registry = trial_marker.read()
        if registry > 0:
            candidates.append(registry)

        return min(candidates) if candidates else 0.0

    @staticmethod
    def _remember_trial_start(started_at):
        """Ghi mốc bắt đầu vào cả file cache lẫn registry."""
        started_at = float(started_at)
        activation = ActivationManager.load_activation() or {}
        existing = 0.0
        try:
            existing = float(activation.get("trial_start") or 0)
        except (TypeError, ValueError):
            existing = 0.0
        # Không cho ghi đè bằng mốc muộn hơn (chống kéo dài hạn).
        if not existing or started_at < existing:
            activation["trial_start"] = started_at
            try:
                with open(ACTIVATION_FILE, "w", encoding="utf-8") as f:
                    json.dump(activation, f, indent=4)
            except Exception as e:
                print(f"Lỗi lưu trial: {e}")
        trial_marker.write(started_at)

    @staticmethod
    def start_trial():
        """
        Bắt đầu dùng thử 3 ngày. Server neo theo fingerprint máy nên xoá dữ liệu
        dưới máy không xin lại được lần hai.
        Returns: dict {success: bool, days_remaining: float, error: str}
        """
        result = _lic.start_trial_online()

        if result.get("success"):
            ActivationManager._remember_trial_start(result["started_at"])
            return {
                "success": True,
                "days_remaining": result.get("days_remaining", ActivationManager.TRIAL_DURATION_DAYS),
                "error": "",
            }

        # Server đã cấp trước đó nhưng hết hạn → ghi lại mốc để lần sau khỏi hỏi.
        started_at = result.get("started_at") or 0.0
        if started_at:
            ActivationManager._remember_trial_start(started_at)

        return {
            "success": False,
            "days_remaining": 0,
            "error": result.get("error", "Thời gian dùng thử đã hết."),
        }

    @staticmethod
    def is_trial_active():
        """Kiểm tra xem đang trong thời gian dùng thử hay không"""
        trial_start = ActivationManager._trial_start_ts()
        if not trial_start:
            return False

        days_passed = (time.time() - trial_start) / (24 * 60 * 60)
        return days_passed < ActivationManager.TRIAL_DURATION_DAYS

    @staticmethod
    def get_trial_days_remaining():
        """Lấy số ngày dùng thử còn lại"""
        trial_start = ActivationManager._trial_start_ts()
        if not trial_start:
            return 0

        days_passed = (time.time() - trial_start) / (24 * 60 * 60)
        remaining = ActivationManager.TRIAL_DURATION_DAYS - days_passed
        return max(0, remaining)

    @staticmethod
    def is_trial_expired():
        """Kiểm tra xem trial đã hết hạn chưa"""
        trial_start = ActivationManager._trial_start_ts()
        if not trial_start:
            return False  # Chưa bắt đầu trial

        days_passed = (time.time() - trial_start) / (24 * 60 * 60)
        return days_passed >= ActivationManager.TRIAL_DURATION_DAYS
