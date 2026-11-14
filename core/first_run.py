# core/first_run.py
"""Việc phải làm ở lần chạy đầu sau khi cài — thay cho [Code] của bộ cài Inno.

Velopack chỉ cho hook cài đặt 30 giây và không được hiện giao diện, nên các
việc này chạy trong app, sau một hộp thoại (ui/dialogs/first_run_dialog.py).
Module này KHÔNG đụng Qt để test được.
"""
import base64
import glob
import json
import logging
import os
import shutil
import subprocess
import sys

from core import config as _cfg
from core.legacy_app_config_defaults import SHIPPED_SUB_VALUES, SHIPPED_VALUES
from core.utils import atomic_write_json

log = logging.getLogger(__name__)

FIRST_RUN_KEY = "first_run_done"
SETUP_ALL_FAILED = -1
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

LEGACY_APP_ID = "{B8F3E2A1-5D6C-4E7F-9A0B-1C2D3E4F5A6B}"
LEGACY_UNINSTALL_KEY = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall" + "\\" + LEGACY_APP_ID + "_is1"
)


# ── Cờ + nhận biết bản cài ───────────────────────────────────────────────────
def is_done(settings):
    return bool((settings or {}).get(FIRST_RUN_KEY))


def mark_done(settings):
    settings[FIRST_RUN_KEY] = True
    return settings


def is_velopack_install(app_dir):
    """Bản cài Velopack: <gốc>\\current\\QuangLuuStudio.exe và <gốc>\\Update.exe."""
    return os.path.isfile(os.path.join(os.path.dirname(os.path.abspath(app_dir)), "Update.exe"))


# ── DAW mặc định + file dữ liệu mặc định ────────────────────────────────────
def _has_dir(pattern):
    return any(os.path.isdir(p) for p in glob.glob(pattern))


def default_daw(program_files, appdata):
    """Máy chỉ có Cubase (không có Studio One) → "cubase"; còn lại "studio_one".
    Cùng logic DawMacDinh của bộ cài Inno (bài học ba máy khách Cubase 2026-10)."""
    has_cubase = (_has_dir(os.path.join(program_files, "Steinberg", "Cubase*"))
                  or _has_dir(os.path.join(appdata, "Steinberg", "Cubase*")))
    has_s1 = (_has_dir(os.path.join(appdata, "PreSonus", "Studio One*"))
              or os.path.isdir(os.path.join(program_files, "PreSonus")))
    return "cubase" if has_cubase and not has_s1 else "studio_one"


def ensure_default_data_files(data_dir, daw_kind):
    """Tạo các file JSON mặc định còn thiếu (không đè file có sẵn). Trả tên file đã tạo."""
    defaults = {
        "activation.json": {"activation_code": "", "activation_date": "", "activation_timestamp": 0},
        "settings.json": {"studio_one_path": "", "browser_path": "",
                          "auto_launch_studio_one": False, "daw_kind": daw_kind},
        "saved_songs.json": [],
        "playlists.json": {},
        "tone_cache.json": {},
        "manual_timelines.json": {},
    }
    os.makedirs(data_dir, exist_ok=True)
    created = []
    for name, value in defaults.items():
        path = os.path.join(data_dir, name)
        if not os.path.exists(path):
            atomic_write_json(path, value)
            created.append(name)
    return created


# ── setup_all.bat /auto ──────────────────────────────────────────────────────
def run_setup_all(app_dir, timeout=300):
    """Chạy setup_all.bat /auto (cổng MIDI, Surface Studio One, script Cubase).
    Trả mã thoát (tổng bit 1/2/4) hoặc SETUP_ALL_FAILED nếu không chạy được/quá giờ."""
    bat = os.path.join(app_dir, "setup_all.bat")
    if not os.path.isfile(bat):
        log.warning("Thiếu %s", bat)
        return SETUP_ALL_FAILED
    try:
        r = subprocess.run(["cmd.exe", "/c", "setup_all.bat", "/auto"], cwd=app_dir, timeout=timeout,
                           creationflags=_NO_WINDOW)
        log.info("setup_all.bat /auto -> %s", r.returncode)
        return r.returncode
    except subprocess.TimeoutExpired:
        log.warning("setup_all.bat /auto quá %ss", timeout)
        return SETUP_ALL_FAILED
    except OSError as e:
        log.warning("Không chạy được setup_all.bat: %s", e)
        return SETUP_ALL_FAILED


def describe_setup_all_code(code):
    """Việc người dùng còn phải làm, theo mã thoát setup_all.bat (rỗng = xong)."""
    if code is None or code == 0:
        return []
    if code < 0:
        return ["Không chạy được bước cài MIDI tự động. Hãy chạy tay setup_all.bat trong thư mục cài đặt."]
    msgs = []
    if code & 1:
        msgs.append("Chưa đủ cổng MIDI ảo (loopMIDI). Chạy setup_all.bat trong thư mục cài đặt để cài có hướng dẫn.")
    if code & 2:
        msgs.append("Chưa chép được script Cubase. Xem log %APPDATA%\\QuangLuuStudio\\logs\\setup_all.txt.")
    if code & 4:
        msgs.append("Cubase đang mở: Studio → MIDI Remote Manager → Scripts → Reload Scripts "
                    "(hoặc mở lại Cubase) để nhận script mới.")
    return msgs


# ── loopMIDI ────────────────────────────────────────────────────────────────
def find_loopmidi(env=None):
    """Đường dẫn loopMIDI.exe (cùng danh sách với setup_midi_ports.ps1) hoặc None."""
    env = os.environ if env is None else env
    cands = []
    for var, sub in (("ProgramFiles", ""), ("ProgramFiles(x86)", ""), ("LOCALAPPDATA", "Programs")):
        base = env.get(var)
        if base:
            cands.append(os.path.join(base, sub, "Tobias Erichsen", "loopMIDI", "loopMIDI.exe"))
    return next((c for c in cands if os.path.isfile(c)), None)


ELEVATED_FAILED = -1


def _run_elevated_ps_code(inner, timeout):
    """Chạy một lệnh PowerShell có nâng quyền (UAC) và chờ xong. Trả mã thoát,
    ELEVATED_FAILED (-1) nếu không chạy được/quá giờ. Từ chối UAC → Start-Process
    ném lỗi → mã 1."""
    # Start-Process ném lỗi (người dùng từ chối UAC) → $p là $null → `exit $null` = 0:
    # phải ép lỗi dừng và bắt lại để trả mã khác 0.
    script = "$ErrorActionPreference='Stop'; try { " + inner + " } catch { exit 1 }"
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-EncodedCommand", enc], timeout=timeout, creationflags=_NO_WINDOW)
        return r.returncode
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("Lệnh nâng quyền lỗi: %s", e)
        return ELEVATED_FAILED


def _run_elevated_ps(inner, timeout):
    """Như _run_elevated_ps_code nhưng chỉ trả True khi mã thoát 0."""
    return _run_elevated_ps_code(inner, timeout) == 0


def install_loopmidi_elevated(timeout=600):
    """Cài loopMIDI bằng winget có nâng quyền (loopMIDI cài cho cả máy). True nếu sau đó tìm thấy."""
    if shutil.which("winget") is None:
        return False
    inner = ("$p = Start-Process winget -Verb RunAs -Wait -PassThru -WindowStyle Hidden -ArgumentList "
             "'install --id TobiasErichsen.loopMIDI --exact --silent "
             "--accept-package-agreements --accept-source-agreements'; "
             "if ($null -eq $p) { exit 1 }; exit $p.ExitCode")
    _run_elevated_ps(inner, timeout)
    return find_loopmidi() is not None


# ── Bản cài Inno cũ (Program Files) ─────────────────────────────────────────
def _read_uninstall_location():
    """InstallLocation của bản Inno cũ trong HKLM (view 64 rồi 32), "" nếu khoá có mà thiếu
    giá trị, None nếu không có khoá."""
    try:
        import winreg
    except ImportError:
        return None
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, LEGACY_UNINSTALL_KEY, 0,
                                winreg.KEY_READ | view) as k:
                try:
                    return str(winreg.QueryValueEx(k, "InstallLocation")[0])
                except OSError:
                    return ""
        except OSError:
            continue
    return None


def legacy_path_key(path):
    """Dạng chuẩn của đường dẫn bản cũ để ghi nhớ trong settings (không phân biệt
    hoa/thường, gạch chéo, gạch cuối)."""
    return os.path.normcase(os.path.normpath(path))


def find_legacy_install():
    loc = _read_uninstall_location()
    if loc is None:
        return None
    # Gốc ổ ("D:\\") giữ nguyên dấu gạch: "D:" là "thư mục hiện hành trên ổ D", không phải gốc ổ.
    if len(loc.rstrip("\\/")) == 2 and loc[1:2] == ":" and loc[:1].isalpha():
        return loc[:2] + "\\"
    return loc.rstrip("\\/")


# Khoá không bao giờ chuyển từ bản cũ: ytdlp_auto_update do QLS_VaNhanh172 ghi tạm.
_KHONG_CHUYEN = ("ytdlp_auto_update",)


def _was_shipped(shipped, value):
    """value trùng một giá trị từng đóng gói? So dạng JSON để True ≠ 1, 1.0 ≠ 1."""
    dump = json.dumps(value, sort_keys=True)
    return any(json.dumps(v, sort_keys=True) == dump for v in shipped)


def _drop_shipped_defaults(diff):
    """Bỏ khỏi diff các giá trị trùng mặc định từng đóng gói (không phải khách chọn)
    và các khoá trong _KHONG_CHUYEN. Sửa tại chỗ."""
    for key in list(diff):
        value = diff[key]
        if key in _KHONG_CHUYEN:
            del diff[key]
        elif isinstance(value, dict):
            subs = SHIPPED_SUB_VALUES.get(key, {})
            kept = {k: v for k, v in value.items() if not _was_shipped(subs.get(k, ()), v)}
            if kept:
                diff[key] = kept
            else:
                del diff[key]
        elif _was_shipped(SHIPPED_VALUES.get(key, ()), value):
            del diff[key]


def migrate_legacy_app_config(legacy_dir):
    """Gộp phần khác biệt của <legacy_dir>\\app_config.json (so với mặc định + bản
    đóng gói hiện tại, bỏ giá trị trùng mặc định từng đóng gói, bỏ khoá cân chỉnh mà hồ sơ
    DAW đang chọn đã có) vào lớp người dùng: khoá calibration → calibration_overrides.json,
    accessibility → accessibility_overrides.json, còn lại → app_config_overrides.json.
    Giá trị đã có ở đích được GIỮ. True nếu có ghi."""
    path = os.path.join(legacy_dir, "app_config.json")
    if not os.path.isfile(path):
        return False
    try:
        old = _cfg.read_json_dict(path)
    except Exception as e:
        log.warning("app_config.json cũ hỏng, bỏ qua: %s", e)
        return False
    diff = _cfg.config_diff(_cfg.AppConfig._load_base(), old)
    # {app}\app_config.json là bản của LẦN CÀI ĐẦU (Inno onlyifdoesntexist): giá trị trùng
    # mặc định cũ nào đó không phải khách chọn → mặc định hiện tại thắng.
    _drop_shipped_defaults(diff)
    cal = {k: diff.pop(k) for k in list(diff) if k in _cfg.CALIBRATION_KEYS}
    # Bộ cài Inno xếp app_config.json DƯỚI hồ sơ DAW, còn calibration_overrides.json thì
    # TRÊN (AppConfig._daw_calibrated) → khoá hồ sơ DAW đang chọn có định nghĩa thì không chuyển.
    try:
        from core import daw  # import trễ: core.daw import core.config
        profile_cal = daw.active().calibration
    except Exception:
        profile_cal = {}
    for k in list(cal):
        if profile_cal.get(k) is not None:
            log.info("Không chuyển %s từ bản cũ: hồ sơ DAW đang chọn đã có giá trị", k)
            del cal[k]
    # accessibility có file riêng (phẳng: khoá → giá trị), save() không ghi nó vào overrides chung
    acc = diff.pop("accessibility", None)
    acc = acc if isinstance(acc, dict) else {}
    wrote = False
    for part, dest in ((diff, _cfg.APP_CONFIG_OVERRIDES_FILE),
                       (cal, _cfg.CALIBRATION_OVERRIDES_FILE),
                       (acc, _cfg.ACCESSIBILITY_OVERRIDES_FILE)):
        if not part:
            continue
        existing = {}
        if os.path.exists(dest):
            try:
                existing = _cfg.read_json_dict(dest)
            except Exception as e:
                # Sắp ghi đè file không đọc được → giữ bản sao để còn cứu tay.
                bak = dest + ".bak"
                try:
                    shutil.copy2(dest, bak)
                    log.warning("%s hỏng (%s) — đã sao lưu sang %s trước khi ghi đè", dest, e, bak)
                except OSError as e2:
                    log.warning("%s hỏng (%s), không sao lưu được sang %s (%s) — không ghi đè",
                                dest, e, bak, e2)
                    continue
                existing = {}
        merged = dict(part)
        _cfg.merge_config(merged, existing)   # giá trị đã có ở đích thắng
        atomic_write_json(dest, merged)
        wrote = True
    if wrote:
        _cfg.AppConfig._data = None   # nạp lại lần get() sau
    return wrote


def migrate_cli(legacy_dir):
    """`QuangLuuStudio.exe --chuyen-cau-hinh-cu <thư mục cũ>` — bộ cài cầu nối gọi dưới
    quyền người dùng gốc trước khi dọn bản Inno. Ghi cờ legacy_config_migrated để lần
    chạy đầu không chuyển lại. 0 = xong, 1 = lỗi, 2 = thiếu đối số."""
    if not legacy_dir:
        log.error("--chuyen-cau-hinh-cu thiếu thư mục bản cũ")
        return 2
    try:
        wrote = migrate_legacy_app_config(legacy_dir)
        settings = _cfg.ConfigManager.load_settings()
        # Chưa có settings.json: đừng tạo file chỉ có một khoá — main.py coi settings
        # khác rỗng là "đã cài đặt" và bỏ qua màn hình thiết lập.
        if settings:
            settings["legacy_config_migrated"] = legacy_path_key(legacy_dir)
            if not _cfg.ConfigManager.save_settings(settings):
                return 1
        log.info("Chuyển cấu hình bản cũ %s: %s", legacy_dir, "có ghi" if wrote else "không có gì khác")
        return 0
    except Exception:
        log.exception("Chuyển cấu hình bản cũ %s lỗi", legacy_dir)
        return 1


def find_bundled(rel_path):
    """File đóng gói theo app: _MEIPASS (onefile/onedir) rồi thư mục exe/gốc dự án."""
    roots = [getattr(sys, "_MEIPASS", None), _cfg.APP_DIR]
    for root in roots:
        if root:
            p = os.path.join(root, rel_path)
            if os.path.isfile(p):
                return p
    return None


def _quote_arg_tail(path):
    """Gạch ngược cuối đường dẫn đứng trước dấu nháy đóng sẽ "escape" nháy
    ("D:\\" → D:"): nhân đôi để dòng lệnh Windows hiểu đúng."""
    n = len(path) - len(path.rstrip("\\"))
    return path + "\\" * n


# Mã thoát của tools/don_ban_cu.ps1
LEGACY_CLEANUP_OK = 0
LEGACY_CLEANUP_INCOMPLETE = 2   # xoá dở (file bị khoá) — giữ khoá, hỏi lại lần sau
LEGACY_CLEANUP_SKIPPED = 3      # thư mục cài cũ không xoá tự động được — khách gỡ tay


def cleanup_legacy_elevated(legacy_dir, timeout=300):
    """Chạy tools/don_ban_cu.ps1 có nâng quyền để xoá bản Inno cũ. Trả mã thoát của
    script (LEGACY_CLEANUP_*; 1 = từ chối UAC/lỗi) hoặc ELEVATED_FAILED (-1)."""
    script = find_bundled(os.path.join("tools", "don_ban_cu.ps1"))
    if script is None:
        log.warning("Thiếu tools/don_ban_cu.ps1")
        return ELEVATED_FAILED
    q = lambda s: s.replace("'", "''")  # noqa: E731 — trích dẫn chuỗi PowerShell
    # Không bao giờ để script xoá chính thư mục app đang chạy hoặc gốc Velopack (cha của nó).
    protected = _cfg.APP_DIR + ";" + os.path.dirname(os.path.abspath(_cfg.APP_DIR))
    inner = ("$p = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -WindowStyle Hidden "
             "-ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',"
             f"'\"{q(script)}\"','-LegacyDir','\"{q(_quote_arg_tail(legacy_dir))}\"',"
             f"'-ProtectedDirs','\"{q(_quote_arg_tail(protected))}\"'); "
             "if ($null -eq $p) { exit 1 }; exit $p.ExitCode")
    return _run_elevated_ps_code(inner, timeout)
