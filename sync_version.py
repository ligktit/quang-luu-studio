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

content = ISS_PATH.read_text(encoding="utf-8")
updated = re.sub(
    r'(#define MyAppVersion\s+")[^"]+(")',
    rf'\g<1>{__version__}\g<2>',
    content,
)

if updated == content:
    print(f"[sync_version] Already at v{__version__} — no changes.")
else:
    ISS_PATH.write_text(updated, encoding="utf-8")
    print(f"[sync_version] Updated .iss → v{__version__}")
