"""Xuất/nhập toàn bộ cấu hình Dev Mode của một máy khách.

Một file gồm ui_config.json (widget, thứ tự, ẩn) và NGUYÊN calibration_overrides.json
(Bypass, mode_config và các key cân chỉnh riêng của máy — không lọc). Khôi phục
luôn chép hai file hiện có sang thư mục backups/ trước khi ghi đè.
"""
import json
import os
import shutil
from datetime import datetime

import core.config as cfg
from core.ui_layout import PANEL_TITLES
from core.utils import atomic_write_json
from core.version import __version__

FORMAT = "quangluu-devmode-backup"
FORMAT_VERSION = 1


class BackupError(Exception):
    """Lỗi xuất/nhập — thông điệp hiện thẳng cho kỹ thuật viên."""


def default_filename(now=None):
    now = now or datetime.now()
    return f"quangluu-giaodien-{now:%Y%m%d-%H%M}.json"


def _read_json(path):
    # utf-8-sig: file mở/lưu bằng Notepad có BOM vẫn đọc được.
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def build_backup():
    calibration = {}
    path = cfg.CALIBRATION_OVERRIDES_FILE
    if os.path.exists(path):
        try:
            data = _read_json(path)
            if isinstance(data, dict):
                calibration = data
        except (OSError, ValueError):
            calibration = {}
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "app_version": __version__,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "ui_config": cfg.UiConfigManager.load_ui_config(),
        "calibration_overrides": calibration,
    }


def export_backup(path):
    atomic_write_json(path, build_backup())


def read_backup(path):
    try:
        data = _read_json(path)
    except (OSError, ValueError) as e:
        raise BackupError(f"Không đọc được file: {e}") from e
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise BackupError("File này không phải bản sao lưu giao diện của Quang Lưu Studio.")
    version = data.get("format_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise BackupError("File sao lưu thiếu phiên bản định dạng.")
    if version > FORMAT_VERSION:
        raise BackupError("File được tạo bởi bản app mới hơn — hãy cập nhật app rồi nhập lại.")
    ui = data.get("ui_config")
    if not isinstance(ui, dict) or not any(isinstance(ui.get(p), list) for p in PANEL_TITLES):
        raise BackupError("File sao lưu không có cấu hình giao diện (mixer/tools/mode).")
    if not isinstance(data.get("calibration_overrides", {}), dict):
        raise BackupError("Phần cân chỉnh MIDI trong file bị hỏng.")
    data.setdefault("calibration_overrides", {})
    return data


def summarize(backup):
    ui = backup.get("ui_config") or {}
    parts = []
    for panel, title in PANEL_TITLES.items():
        entries = ui.get(panel)
        if not isinstance(entries, list):
            continue
        entries = [e for e in entries if isinstance(e, dict)]
        hidden = sum(1 for e in entries if e.get("hidden"))
        parts.append(f"{title}: {len(entries)} widget" + (f" ({hidden} ẩn)" if hidden else ""))
    parts.append(f"{len(backup.get('calibration_overrides') or {})} mục cân chỉnh MIDI")
    when = backup.get("exported_at") or ""
    try:
        when = datetime.fromisoformat(when).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        pass
    origin = f"Xuất từ v{backup.get('app_version', '?')}" + (f" lúc {when}" if when else "")
    return " · ".join(parts) + "\n" + origin


def _backup_dir():
    return os.path.join(os.path.dirname(os.path.abspath(cfg.UI_CONFIG_FILE)), "backups")


def restore_backup(backup):
    """Ghi đè ui_config.json + calibration_overrides.json từ `backup` (đã qua
    read_backup). Chép file hiện có sang backups/ trước; ghi lỗi giữa chừng thì
    trả lại từ bản chép. Trả danh sách file .bak đã tạo."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    targets = (
        (cfg.UI_CONFIG_FILE, backup["ui_config"]),
        (cfg.CALIBRATION_OVERRIDES_FILE, backup.get("calibration_overrides") or {}),
    )
    saved = []
    try:
        os.makedirs(_backup_dir(), exist_ok=True)
        for target, _ in targets:
            bak = None
            if os.path.exists(target):
                bak = os.path.join(_backup_dir(), f"{os.path.basename(target)}.{stamp}.bak")
                shutil.copy2(target, bak)
            saved.append((target, bak))
    except OSError as e:
        raise BackupError(f"Không sao lưu được cấu hình hiện tại, chưa ghi gì: {e}") from e

    try:
        for target, data in targets:
            atomic_write_json(target, data)
    except Exception as e:
        for target, bak in saved:
            try:
                if bak:
                    shutil.copy2(bak, target)
                elif os.path.exists(target):
                    os.remove(target)
            except OSError:
                pass
        raise BackupError(
            f"Ghi cấu hình lỗi, đã trả lại như cũ (bản sao lưu ở {_backup_dir()}): {e}") from e

    cfg.AppConfig.reload()
    return [bak for _, bak in saved if bak]
