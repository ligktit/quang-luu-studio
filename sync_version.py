"""
Sync version from core/version.py → QuangLuuStudio_Setup.iss
Run this before building the installer.
"""
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from core.version import __version__

ISS_PATH = Path(__file__).parent / "QuangLuuStudio_Setup.iss"

# 1. Update ISS
content = ISS_PATH.read_text(encoding="utf-8")
updated = re.sub(
    r'(#define MyAppVersion\s+")[^"]+(")',
    rf'\g<1>{__version__}\g<2>',
    content,
)

if updated != content:
    ISS_PATH.write_text(updated, encoding="utf-8")
    print(f"[sync_version] Updated .iss -> v{__version__}")

# 2. Update build_installer.bat
BAT_PATH = Path(__file__).parent / "build_installer.bat"
if BAT_PATH.exists():
    content = BAT_PATH.read_text(encoding="utf-8")
    updated = re.sub(
        r'(Setup_QuangLuuStudio_v)[\d\.]+',
        rf'\g<1>{__version__}',
        content,
    )
    if updated != content:
        BAT_PATH.write_text(updated, encoding="utf-8")
        print(f"[sync_version] Updated build_installer.bat -> v{__version__}")

# 3. Update BUNDLED_YTDLP_VERSION in core/ytdlp_update.py
#    Phải khớp với bản yt-dlp thực sự bị PyInstaller gói vào .exe, nếu không bản
#    yt-dlp nạp ngoài (cũ hơn) sẽ được ưu tiên nhầm sau khi build mới.
YTDLP_UPDATE_PATH = Path(__file__).parent / "core" / "ytdlp_update.py"
try:
    import yt_dlp
    bundled = yt_dlp.version.__version__
except Exception as exc:  # pragma: no cover — chỉ chạy lúc build
    print(f"[sync_version] CANH BAO: khong doc duoc phien ban yt-dlp ({exc})")
else:
    content = YTDLP_UPDATE_PATH.read_text(encoding="utf-8")
    updated = re.sub(
        r'(BUNDLED_YTDLP_VERSION\s*=\s*")[^"]+(")',
        rf'\g<1>{bundled}\g<2>',
        content,
    )
    if updated != content:
        YTDLP_UPDATE_PATH.write_text(updated, encoding="utf-8")
        print(f"[sync_version] Updated BUNDLED_YTDLP_VERSION -> {bundled}")
    else:
        print(f"[sync_version] BUNDLED_YTDLP_VERSION da dung: {bundled}")

# 4. Update so hieu phien ban in tren so tay nguoi dung.
#    Truoc day sua tay nen no dung yen o 1.5.1 suot nhieu ban phat hanh — khach
#    doc so tay tuong minh dang cai ban cu.
MANUAL_PATH = Path(__file__).parent / "docs" / "manual" / "index.html"
if MANUAL_PATH.exists():
    content = MANUAL_PATH.read_text(encoding="utf-8")
    updated = re.sub(r'(Hướng dẫn sử dụng · v)[\d\.]+', rf'\g<1>{__version__}', content)
    updated = re.sub(r'(Phiên bản )[\d\.]+', rf'\g<1>{__version__}', updated)
    if updated != content:
        MANUAL_PATH.write_text(updated, encoding="utf-8")
        print(f"[sync_version] Updated so tay -> v{__version__}")

print(f"[sync_version] Finished syncing v{__version__}")
