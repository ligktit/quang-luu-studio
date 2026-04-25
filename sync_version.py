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

print(f"[sync_version] Finished syncing v{__version__}")
