"""
Script tạo activation code cho Quang Lưu Studio
Sử dụng: python generate_code.py [số lượng code muốn tạo]
"""
import hashlib
import random
import string
import sys

import os

# Secret key - NÊN THAY ĐỔI TRONG MÔI TRƯỜNG THỰC TẾ
SECRET_KEY = os.environ.get("QUANGLUU_STUDIO_SECRET_KEY", "QUANGLUU_STUDIO_2026_SECRET_KEY_CHANGE_THIS")

def generate_activation_code():
    """
    Tạo activation code với format: XXXX-XXXX-XXXX-XXXX
    Bao gồm checksum để validate
    """
    # Tạo 4 nhóm, mỗi nhóm 4 ký tự
    groups = []
    for _ in range(4):
        # Mỗi nhóm: 2 chữ cái + 2 số
        group = ''.join(random.choices(string.ascii_uppercase, k=2))
        group += ''.join(random.choices(string.digits, k=2))
        groups.append(group)
    
    # Tạo code base
    base_code = '-'.join(groups)
    
    # Tính checksum (hash của base_code + secret key)
    checksum_input = base_code + SECRET_KEY
    checksum = hashlib.md5(checksum_input.encode()).hexdigest()[:4].upper()
    
    # Thêm checksum vào cuối code
    full_code = f"{base_code}-{checksum}"
    
    return full_code, base_code, checksum

def validate_code_structure(code):
    """Kiểm tra format của code"""
    # Format: XXXX-XXXX-XXXX-XXXX-XXXX (4 nhóm + 1 checksum)
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

def verify_code_checksum(code):
    """Xác minh checksum của code"""
    parts = code.split('-')
    if len(parts) != 5:
        return False
    
    base_code = '-'.join(parts[:4])
    provided_checksum = parts[4]
    
    # Tính checksum
    checksum_input = base_code + SECRET_KEY
    calculated_checksum = hashlib.md5(checksum_input.encode()).hexdigest()[:4].upper()
    
    return provided_checksum == calculated_checksum

def main():
    """Hàm chính"""
    print("=" * 60)
    print("🔐 QUANG LƯU STUDIO - ACTIVATION CODE GENERATOR")
    print("=" * 60)
    print()
    
    # Số lượng code muốn tạo
    count = 1
    if len(sys.argv) > 1:
        try:
            count = int(sys.argv[1])
        except Exception:
            print("⚠️  Số lượng không hợp lệ, tạo 1 code mặc định")
    
    print(f"📝 Đang tạo {count} activation code(s)...\n")
    
    codes = []
    for i in range(count):
        full_code, base_code, checksum = generate_activation_code()
        codes.append(full_code)
        
        print(f"Code #{i+1}:")
        print(f"  Full Code: {full_code}")
        print(f"  Base:      {base_code}")
        print(f"  Checksum:  {checksum}")
        print()
    
    # Lưu vào file
    output_file = "activation_codes.txt"
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("=" * 60 + "\n")
            f.write("QUANG LƯU STUDIO - ACTIVATION CODES\n")
            f.write("=" * 60 + "\n")
            f.write(f"Generated: {len(codes)} code(s)\n\n")
            for i, code in enumerate(codes, 1):
                f.write(f"{i}. {code}\n")
        
        print(f"✅ Đã lưu {len(codes)} code(s) vào file: {output_file}")
        print()
        print("⚠️  LƯU Ý:")
        print("   - Giữ file này an toàn và bảo mật")
        print("   - Chỉ chia sẻ code cho người dùng hợp lệ")
        print("   - Mỗi code chỉ sử dụng được 1 lần (có thể cải thiện sau)")
    except Exception as e:
        print(f"❌ Lỗi khi lưu file: {e}")
    
    # Test validation
    print()
    print("🧪 Kiểm tra validation:")
    test_code = codes[0]
    print(f"   Code: {test_code}")
    print(f"   Format hợp lệ: {validate_code_structure(test_code)}")
    print(f"   Checksum đúng: {verify_code_checksum(test_code)}")
    print()
    
    print("=" * 60)

if __name__ == "__main__":
    main()
