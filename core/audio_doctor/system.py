"""Cổng ra hệ thống cho các Check: process, cổng MIDI, registry, file, cửa sổ DAW.

Tách riêng để test check bằng đồ giả; bản thật dưới đây gọi Windows thật.
"""
import glob
import hashlib
import os
import shutil
import subprocess
import time
from typing import Optional

_LOOPMIDI_REL = os.path.join("Tobias Erichsen", "loopMIDI", "loopMIDI.exe")


class SystemProbe:
    # ── process ─────────────────────────────────────────────────────────────
    def process_running(self, exe) -> bool:
        try:
            import psutil
            exe = exe.lower()
            return any((p.info.get("name") or "").lower() == exe
                       for p in psutil.process_iter(["name"]))
        except Exception:
            return False

    def kill_process(self, exe) -> None:
        try:
            import psutil
            for p in psutil.process_iter(["name"]):
                if (p.info.get("name") or "").lower() == exe.lower():
                    p.kill()
        except Exception as e:
            print(f"[AUDIO DOCTOR] Không dừng được {exe}: {e}")

    def start_process(self, path) -> None:
        # Thu nhỏ, không lấy tiền cảnh: cửa sổ loopMIDI bật giữa màn hình sẽ
        # đè lên app trong khi khách đang dùng.
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 7                  # SW_SHOWMINNOACTIVE
        subprocess.Popen([path], close_fds=True, startupinfo=si)

    # ── MIDI ────────────────────────────────────────────────────────────────
    def midi_ports(self):
        try:
            import mido
            return list(mido.get_output_names()), list(mido.get_input_names())
        except Exception:
            return [], []

    def find_loopmidi_exe(self) -> Optional[str]:
        roots = [os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")]
        for r in roots:
            p = os.path.join(r, _LOOPMIDI_REL)
            if r and os.path.isfile(p):
                return p
        return None

    # ── registry ────────────────────────────────────────────────────────────
    @staticmethod
    def _root(root):
        import winreg
        return {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}[root]

    def reg_get(self, root, key, name) -> Optional[str]:
        try:
            import winreg
            with winreg.OpenKey(self._root(root), key) as k:
                return str(winreg.QueryValueEx(k, name)[0])
        except Exception:
            return None

    def reg_set(self, root, key, name, value) -> None:
        import winreg
        with winreg.CreateKeyEx(self._root(root), key, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, str(value))

    def reg_names(self, root, key):
        try:
            import winreg
            out = []
            with winreg.OpenKey(self._root(root), key) as k:
                i = 0
                while True:
                    try:
                        out.append(winreg.EnumValue(k, i)[0])
                    except OSError:
                        break
                    i += 1
            return out
        except Exception:
            return []

    # ── thư mục / file ──────────────────────────────────────────────────────
    def appdata(self) -> str:
        return os.environ.get("APPDATA", os.path.expanduser("~"))

    def documents(self) -> str:
        try:
            from win32com.shell import shell, shellcon
            return shell.SHGetFolderPath(0, shellcon.CSIDL_PERSONAL, None, 0)
        except Exception:
            return os.path.join(os.path.expanduser("~"), "Documents")

    def glob_dirs(self, pattern):
        return sorted(p for p in glob.glob(pattern) if os.path.isdir(p))

    def exists(self, path) -> bool:
        return bool(path) and os.path.exists(path)

    def read_text(self, path) -> str:
        # surrogateescape + newline="" → ghi lại đúng từng byte cũ, chỉ đổi chỗ sửa.
        with open(path, "r", encoding="utf-8", errors="surrogateescape", newline="") as fh:
            return fh.read()

    def write_text(self, path, text) -> None:
        with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="") as fh:
            fh.write(text)

    def sha256(self, path) -> Optional[str]:
        try:
            with open(path, "rb") as fh:
                return hashlib.sha256(fh.read()).hexdigest()
        except OSError:
            return None

    def copy(self, src, dst) -> None:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)

    def backup(self, path) -> str:
        dst = f"{path}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copyfile(path, dst)
        return dst

    def bundled(self, rel) -> Optional[str]:
        from core.config import APP_DIR
        p = os.path.join(APP_DIR, rel)
        return p if os.path.isfile(p) else None

    # ── cửa sổ DAW ──────────────────────────────────────────────────────────
    def daw_running(self) -> bool:
        from core import so_windows
        return so_windows.is_running()

    def daw_main_window(self) -> bool:
        from core import so_windows
        return bool(so_windows.main_windows())

    def wait_daw_main_window(self, timeout) -> bool:
        from core import so_windows
        return so_windows.wait_for_main_window(timeout=timeout) is not None

    def daw_dialogs(self):
        """Cửa sổ ĐANG HIỆN, có tiêu đề, thuộc DAW nhưng không phải cửa sổ chính."""
        from core import so_windows
        mods = so_windows.win32_modules()
        if not mods:
            return []
        win32gui = mods[0]
        mains = set(so_windows.main_windows())
        out = []
        for hwnd in so_windows.all_windows():
            try:
                if hwnd in mains or not win32gui.IsWindowVisible(hwnd):
                    continue
                title = win32gui.GetWindowText(hwnd).strip()
                if title:
                    out.append((hwnd, title))
            except Exception:
                continue
        return out

    def focus_window(self, hwnd) -> None:
        from core import so_windows
        so_windows.force_foreground(hwnd)
