"""Windows: thiết bị phát mặc định, mute thiết bị ảo, mic + quyền micro."""
from core.audio_doctor.model import Check, ok, loi, khong_ro, da_sua, can_lam_tay
from core.audio_doctor.win_audio import pick_virtual_device

MIC_CONSENT_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"
LOW_PCT = 5.0
_PICK_GUIDE = ("Bấm ⚙ Cài đặt → tab Âm thanh → «Thiết bị đưa nhạc vào DAW» → chọn thiết bị ảo "
               "(ASIOVADPRO / VB-Cable) mà track Nhạc trong phần mềm thu âm đang nhận.",)


def _target(ctx):
    s = ctx.settings or {}
    return s.get("music_playback_device_id") or None, s.get("music_playback_device_name") or ""


class WinPlaybackDefaultCheck(Check):
    id, group, title = "win_playback_default", "windows", "Thiết bị phát mặc định"
    fix_when_unknown = True

    def detect(self, ctx):
        if not ctx.win.available():
            return khong_ro("Không đọc được thiết bị âm thanh Windows")
        target, saved_name = _target(ctx)
        if not target:
            return khong_ro("Chưa chọn thiết bị đưa nhạc vào DAW")
        devices = ctx.win.render_devices()
        names = {d.id: d.name for d in devices}
        if target not in names:
            return loi(f"Không thấy thiết bị «{saved_name or target}» — card ảo bị gỡ hoặc đang tắt",
                       fixable=False,
                       guide=("Mở Control Panel → Sound → tab Playback, chuột phải → «Show Disabled Devices», "
                              "bật lại thiết bị ảo.", "Không thấy thì cài lại ASIOVADPRO / VB-Cable."))
        cur = ctx.win.default_render_ids()
        if all(c == target for c in cur):
            return ok(f"Nhạc đang phát ra «{names[target]}»")
        cur_name = names.get(cur[1] or cur[0] or "", "thiết bị khác")
        return loi(f"Windows đang phát ra «{cur_name}» thay vì «{names[target]}» — nhạc không vào DAW")

    def fix(self, ctx):
        target, _ = _target(ctx)
        if not target:
            cand = pick_virtual_device(ctx.win.render_devices())
            if cand is None:
                return can_lam_tay("Không tìm thấy thiết bị ảo đưa nhạc vào DAW", guide=_PICK_GUIDE)
            if not ctx.ask(f"Nhạc YouTube đi vào phần mềm thu âm qua thiết bị «{cand.name}» phải không?"):
                return can_lam_tay("Chưa chọn thiết bị đưa nhạc vào DAW", guide=_PICK_GUIDE)
            ctx.actions.save_setting("music_playback_device_id", cand.id)
            ctx.actions.save_setting("music_playback_device_name", cand.name)
            ctx.settings["music_playback_device_id"] = cand.id
            ctx.settings["music_playback_device_name"] = cand.name
            target = cand.id
        ctx.win.set_default_render(target)
        return da_sua(f"Đã đặt «{ctx.win.name_of(target) or target}» làm thiết bị phát mặc định")


class WinPlaybackMuteCheck(Check):
    id, group, title = "win_playback_mute", "windows", "Âm lượng thiết bị phát"
    requires = ("win_playback_default",)

    def _dev(self, ctx):
        target, _ = _target(ctx)
        if target:
            return target
        cur = ctx.win.default_render_ids()
        return cur[1] or cur[0]

    def detect(self, ctx):
        if not ctx.win.available():
            return khong_ro("Không đọc được thiết bị âm thanh Windows")
        dev = self._dev(ctx)
        if not dev:
            return khong_ro("Không có thiết bị phát mặc định")
        muted, pct = ctx.win.endpoint_state(dev)
        name = ctx.win.name_of(dev) or "thiết bị phát"
        if muted:
            return loi(f"«{name}» đang bị tắt tiếng trong Windows")
        if pct < LOW_PCT:
            return loi(f"Âm lượng «{name}» trong Windows gần như bằng 0")
        return ok(f"«{name}» đang mở tiếng ({pct:.0f}%)")

    def fix(self, ctx):
        dev = self._dev(ctx)
        ctx.win.set_endpoint(dev, muted=False, volume_pct=100.0)
        return da_sua(f"Đã bật tiếng «{ctx.win.name_of(dev) or 'thiết bị phát'}» lên 100%")


class WinMicCheck(Check):
    id, group, title = "win_mic", "windows", "Micro trong Windows"

    _KEYS = (MIC_CONSENT_KEY, MIC_CONSENT_KEY + r"\NonPackaged")

    def detect(self, ctx):
        s = ctx.system
        if s.reg_get("HKLM", MIC_CONSENT_KEY, "Value") == "Deny":
            return loi("Windows đang chặn micro cho toàn máy — cần kỹ thuật mở", fixable=False,
                       guide=("Bấm «Gửi cho kỹ thuật» bên dưới.",))
        problems = []
        if any(s.reg_get("HKCU", k, "Value") == "Deny" for k in self._KEYS):
            problems.append("Windows đang chặn quyền dùng micro")
        if ctx.win.available():
            cap = ctx.win.default_capture_id()
            if cap and ctx.win.endpoint_state(cap)[0]:
                problems.append("Micro bị tắt tiếng trong Windows")
        if problems:
            return loi("; ".join(problems))
        return ok("Micro không bị Windows chặn")

    def fix(self, ctx):
        for k in self._KEYS:
            if ctx.system.reg_get("HKCU", k, "Value") == "Deny":
                ctx.system.reg_set("HKCU", k, "Value", "Allow")
        if ctx.win.available():
            cap = ctx.win.default_capture_id()
            if cap:
                ctx.win.set_endpoint(cap, muted=False)
        return da_sua("Đã mở quyền micro và bật tiếng micro trong Windows")
