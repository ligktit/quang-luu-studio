"""Đọc/đặt thiết bị âm thanh Windows qua pycaw (Core Audio).

Mọi method tự CoInitialize cho luồng đang gọi: Runner chạy check trên luồng nền.
pycaw/comtypes thiếu → available() False, các check Windows ra KHONG_RO.
"""
import re
from dataclasses import dataclass
from typing import Optional

# Tên tiến trình trình duyệt — cùng danh sách engine dùng cho thanh Nhạc.
BROWSER_PROCESS_NAMES = (
    "chrome.exe", "msedge.exe", "opera.exe", "firefox.exe",
    "brave.exe", "vivaldi.exe", "chromium.exe",
)

# Thứ tự = độ ưu tiên khi đề xuất thiết bị ảo đưa nhạc vào DAW.
_VIRTUAL_PATTERNS = (r"asiovad", r"vb-audio|cable", r"virtual")


@dataclass(frozen=True)
class Device:
    id: str
    name: str


def pick_virtual_device(devices) -> Optional[Device]:
    for pat in _VIRTUAL_PATTERNS:
        for d in devices:
            if re.search(pat, d.name or "", re.IGNORECASE):
                return d
    return None


def _co_init():
    try:
        import comtypes
        comtypes.CoInitialize()
    except Exception:
        pass


class WinAudio:
    def available(self) -> bool:
        try:
            import comtypes  # noqa: F401
            from pycaw.pycaw import AudioUtilities  # noqa: F401
            return True
        except Exception:
            return False

    # ── thiết bị ─────────────────────────────────────────────────────────────
    def _enum(self):
        _co_init()
        from pycaw.pycaw import AudioUtilities
        return AudioUtilities.GetDeviceEnumerator()

    def render_devices(self):
        _co_init()
        from pycaw.pycaw import AudioUtilities
        from pycaw.constants import EDataFlow, DEVICE_STATE
        out = []
        for d in AudioUtilities.GetAllDevices(EDataFlow.eRender.value, DEVICE_STATE.ACTIVE.value):
            if d is not None and d.id:
                out.append(Device(d.id, d.FriendlyName or d.id))
        return out

    def name_of(self, dev_id) -> Optional[str]:
        for d in self.render_devices():
            if d.id == dev_id:
                return d.name
        return None

    def _default_id(self, flow, role):
        try:
            return self._enum().GetDefaultAudioEndpoint(flow, role).GetId()
        except Exception:
            return None

    def default_render_ids(self):
        from pycaw.constants import EDataFlow, ERole
        return (self._default_id(EDataFlow.eRender.value, ERole.eConsole.value),
                self._default_id(EDataFlow.eRender.value, ERole.eMultimedia.value))

    def default_capture_id(self):
        from pycaw.constants import EDataFlow, ERole
        return self._default_id(EDataFlow.eCapture.value, ERole.eConsole.value)

    def set_default_render(self, dev_id) -> None:
        _co_init()
        from pycaw.pycaw import AudioUtilities
        from pycaw.constants import ERole
        AudioUtilities.SetDefaultDevice(dev_id, roles=[ERole.eConsole, ERole.eMultimedia])

    def _volume(self, dev_id):
        from pycaw.pycaw import AudioUtilities
        dev = self._enum().GetDevice(dev_id)
        return AudioUtilities.CreateDevice(dev).EndpointVolume

    def endpoint_state(self, dev_id):
        vol = self._volume(dev_id)
        return bool(vol.GetMute()), float(vol.GetMasterVolumeLevelScalar()) * 100.0

    def set_endpoint(self, dev_id, muted=False, volume_pct=None) -> None:
        vol = self._volume(dev_id)
        vol.SetMute(1 if muted else 0, None)
        if volume_pct is not None:
            vol.SetMasterVolumeLevelScalar(max(0.0, min(100.0, float(volume_pct))) / 100.0, None)

    # ── session trình duyệt (Volume Mixer) ──────────────────────────────────
    def _browser_session_volumes(self, names):
        _co_init()
        from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
        names = {n.lower() for n in names}
        for s in AudioUtilities.GetAllSessions():
            try:
                proc = s.Process
                if proc is None or proc.name().lower() not in names:
                    continue
                yield proc.name(), s._ctl.QueryInterface(ISimpleAudioVolume)
            except Exception:
                continue

    def browser_sessions(self, names=BROWSER_PROCESS_NAMES):
        return [(n, bool(v.GetMute()), float(v.GetMasterVolume()) * 100.0)
                for n, v in self._browser_session_volumes(names)]

    def unmute_browser_sessions(self, names=BROWSER_PROCESS_NAMES, volume_pct=100.0) -> int:
        n = 0
        for _, v in self._browser_session_volumes(names):
            v.SetMute(0, None)
            v.SetMasterVolume(float(volume_pct) / 100.0, None)
            n += 1
        return n
