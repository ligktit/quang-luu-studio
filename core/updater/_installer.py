"""Launch the downloaded Inno Setup installer."""
import subprocess
import sys
from pathlib import Path


def run_installer(setup_path: Path, silent: bool = False) -> None:
    """
    Launch the Inno Setup installer detached from the current process.
    The app will exit so the installer can replace the exe.

    Args:
        setup_path: Path to the downloaded .exe installer.
        silent:     If True use /VERYSILENT (no UI at all).
                    If False use /SILENT (progress bar, no wizard pages).
    """
    flags = [
        "/CLOSEAPPLICATIONS",     # Ask running instances to close
        "/RESTARTAPPLICATIONS",   # Restart app after installation
    ]
    if silent:
        flags = ["/VERYSILENT", "/SUPPRESSMSGBOXES"] + flags
    else:
        flags = ["/SILENT"] + flags

    subprocess.Popen(
        [str(setup_path), *flags],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    # Exit so Inno Setup can overwrite the exe
    sys.exit(0)
