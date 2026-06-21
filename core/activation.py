"""
Quang Lưu Studio — Activation Manager
Class: ActivationManager
"""
import os
import json
import time
import hashlib

from core.config import ACTIVATION_FILE


def _online():
    """Trả module core.licensing.client nếu server được cấu hình, ngược lại None.

    Import lazy để tránh chi phí/khả năng circular import lúc nạp module.
    Khi app_config.json KHÔNG có 'license_server_url' → trả None → giữ nguyên
    luồng kích hoạt offline cũ (tương thích ngược hoàn toàn).
    """
    try:
        from core.licensing import client
        return client if client.server_configured() else None
    except Exception:
        return None


class ActivationManager:
    """Quản lý activation code, thời hạn sử dụng, và bản dùng thử"""

    # Thời hạn sử dụng: 1 năm (365 ngày)
    LICENSE_DURATION_DAYS = 365
    
    # Thời hạn dùng thử: 3 ngày
    TRIAL_DURATION_DAYS = 3
    
    # Secret key - PHẢI GIỐNG VỚI tools/generate_code.py
    # Key cũ (placeholder) đã bị lộ trên GitHub → đổi key mới làm mọi code
    # đã phát hành trước đó (kể cả code bị leak) mất hiệu lực.
    # Có thể override qua biến môi trường QUANGLUU_STUDIO_SECRET_KEY.
    SECRET_KEY = os.environ.get(
        "QUANGLUU_STUDIO_SECRET_KEY",
        "936c3f6655acc46ba5c41603446addb7e5b25df85c953d003eba554527e267e4"
    )
    
    @staticmethod
    def _validate_code_structure(code):
        """Kiểm tra format của code: XXXX-XXXX-XXXX-XXXX-XXXX"""
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
    def _verify_code_checksum(code):
        """Xác minh checksum của code"""
        parts = code.split('-')
        if len(parts) != 5:
            return False
        
        base_code = '-'.join(parts[:4])
        provided_checksum = parts[4]
        
        # Tính checksum
        checksum_input = base_code + ActivationManager.SECRET_KEY
        calculated_checksum = hashlib.md5(checksum_input.encode()).hexdigest()[:4].upper()
        
        return provided_checksum == calculated_checksum
    
    @staticmethod
    def _validate_code(code):
        """
        Xác thực activation code
        Kiểm tra cả format và checksum
        """
        if not code:
            return False
        
        code = code.strip().upper()
        
        # Kiểm tra format
        if not ActivationManager._validate_code_structure(code):
            return False
        
        # Kiểm tra checksum
        if not ActivationManager._verify_code_checksum(code):
            return False
        
        return True
    
    @staticmethod
    def load_activation():
        """Load thông tin activation từ file"""
        if os.path.exists(ACTIVATION_FILE):
            try:
                with open(ACTIVATION_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
        return None
    
    @staticmethod
    def save_activation(code):
        """Lưu thông tin activation sau khi kích hoạt thành công"""
        activation_data = {
            "activation_code": code.strip().upper(),
            "activation_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "activation_timestamp": time.time()
        }
        try:
            with open(ACTIVATION_FILE, "w", encoding="utf-8") as f:
                json.dump(activation_data, f, indent=4)
            return True
        except Exception as e:
            print(f"Lỗi lưu activation: {e}")
            return False
    
    @staticmethod
    def is_activated():
        """Kiểm tra xem app đã được kích hoạt chưa"""
        # Online mode: đã kích hoạt nếu có license token cache.
        online = _online()
        if online is not None and online.has_online_license():
            return True

        activation = ActivationManager.load_activation()
        if not activation:
            return False

        # Kiểm tra xem có activation_date không
        if "activation_date" not in activation:
            return False

        return True
    
    @staticmethod
    def is_expired():
        """Kiểm tra xem activation đã hết hạn chưa (sau 1 năm)"""
        # Online mode: hết hạn nếu có license nhưng grace đã lapse hoặc license
        # quá hạn theo server. is_grace_valid() bao cả 2 trường hợp.
        online = _online()
        if online is not None and online.has_online_license():
            return not online.is_grace_valid()

        activation = ActivationManager.load_activation()
        if not activation:
            return True  # Chưa kích hoạt = hết hạn
        
        # Lấy timestamp từ activation
        if "activation_timestamp" in activation:
            activation_time = activation["activation_timestamp"]
        elif "activation_date" in activation:
            # Parse date string nếu không có timestamp
            try:
                from datetime import datetime
                activation_time = datetime.strptime(
                    activation["activation_date"], 
                    "%Y-%m-%d %H:%M:%S"
                ).timestamp()
            except Exception:
                return True  # Lỗi parse = hết hạn
        else:
            return True  # Không có thông tin = hết hạn
        
        # Tính số ngày đã trôi qua
        current_time = time.time()
        days_passed = (current_time - activation_time) / (24 * 60 * 60)
        
        # Kiểm tra xem đã vượt quá thời hạn chưa
        return days_passed >= ActivationManager.LICENSE_DURATION_DAYS
    
    @staticmethod
    def get_days_remaining():
        """Lấy số ngày còn lại của license"""
        online = _online()
        if online is not None and online.has_online_license():
            return online.days_remaining()

        activation = ActivationManager.load_activation()
        if not activation:
            return 0
        
        if "activation_timestamp" in activation:
            activation_time = activation["activation_timestamp"]
        elif "activation_date" in activation:
            try:
                from datetime import datetime
                activation_time = datetime.strptime(
                    activation["activation_date"], 
                    "%Y-%m-%d %H:%M:%S"
                ).timestamp()
            except Exception:
                return 0
        else:
            return 0
        
        current_time = time.time()
        days_passed = (current_time - activation_time) / (24 * 60 * 60)
        days_remaining = ActivationManager.LICENSE_DURATION_DAYS - days_passed
        
        return max(0, int(days_remaining))
    
    @staticmethod
    def activate(code):
        """Kích hoạt app với code được cung cấp. Returns dict: {success: bool, error: str}"""
        # Online mode: server là thẩm quyền — kiểm format trước cho phản hồi nhanh,
        # rồi kích hoạt + ràng máy qua server.
        online = _online()
        if online is not None:
            if not ActivationManager._validate_code_structure(code):
                return {"success": False, "error": "Mã kích hoạt không hợp lệ. Vui lòng kiểm tra lại."}
            return online.activate_online(code)

        # Offline mode (server chưa cấu hình): checksum cục bộ như cũ.
        if not ActivationManager._validate_code(code):
            return {"success": False, "error": "Mã kích hoạt không hợp lệ. Vui lòng kiểm tra lại."}

        # Lưu activation
        if ActivationManager.save_activation(code):
            return {"success": True, "error": ""}
        else:
            return {"success": False, "error": "Lỗi khi lưu thông tin kích hoạt."}
    
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
    def start_trial():
        """
        Bắt đầu dùng thử 3 ngày. Lưu timestamp lần đầu mở app.
        Nếu đã có trial trước đó → không reset (chống gian lận).
        Returns: dict {success: bool, days_remaining: int}
        """
        activation = ActivationManager.load_activation() or {}
        
        # Nếu đã có trial_start → không cho bắt đầu lại
        if "trial_start" in activation:
            remaining = ActivationManager.get_trial_days_remaining()
            if remaining > 0:
                return {"success": True, "days_remaining": remaining}
            else:
                return {"success": False, "days_remaining": 0}
        
        # Lần đầu → ghi trial_start
        activation["trial_start"] = time.time()
        try:
            with open(ACTIVATION_FILE, "w", encoding="utf-8") as f:
                json.dump(activation, f, indent=4)
            return {"success": True, "days_remaining": ActivationManager.TRIAL_DURATION_DAYS}
        except Exception as e:
            print(f"Lỗi lưu trial: {e}")
            return {"success": False, "days_remaining": 0}
    
    @staticmethod
    def is_trial_active():
        """Kiểm tra xem đang trong thời gian dùng thử hay không"""
        activation = ActivationManager.load_activation()
        if not activation:
            return False
        
        trial_start = activation.get("trial_start")
        if not trial_start:
            return False
        
        days_passed = (time.time() - trial_start) / (24 * 60 * 60)
        return days_passed < ActivationManager.TRIAL_DURATION_DAYS
    
    @staticmethod
    def get_trial_days_remaining():
        """Lấy số ngày dùng thử còn lại"""
        activation = ActivationManager.load_activation()
        if not activation:
            return 0
        
        trial_start = activation.get("trial_start")
        if not trial_start:
            return 0
        
        days_passed = (time.time() - trial_start) / (24 * 60 * 60)
        remaining = ActivationManager.TRIAL_DURATION_DAYS - days_passed
        return max(0, remaining)
    
    @staticmethod
    def is_trial_expired():
        """Kiểm tra xem trial đã hết hạn chưa"""
        activation = ActivationManager.load_activation()
        if not activation:
            return False  # Chưa bắt đầu trial
        
        trial_start = activation.get("trial_start")
        if not trial_start:
            return False  # Chưa bắt đầu trial
        
        days_passed = (time.time() - trial_start) / (24 * 60 * 60)
        return days_passed >= ActivationManager.TRIAL_DURATION_DAYS
