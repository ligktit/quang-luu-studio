"""Trình duyệt: Volume Mixer của Windows và trình phát YouTube."""
from core.audio_doctor.model import Check, ok, loi, khong_ro, da_sua, bo_qua
from core.audio_doctor.win_audio import BROWSER_PROCESS_NAMES

LOW_PCT = 5.0


class BrowserSessionCheck(Check):
    id, group, title = "browser_session", "browser", "Trình duyệt trong Volume Mixer"
    requires = ("win_playback_default",)

    def detect(self, ctx):
        if not ctx.win.available():
            return khong_ro("Không đọc được Volume Mixer")
        sessions = ctx.win.browser_sessions(BROWSER_PROCESS_NAMES)
        if not sessions:
            return bo_qua("Trình duyệt chưa phát âm thanh")
        bad = [n for n, muted, pct in sessions if muted or pct < LOW_PCT]
        if bad:
            return loi(f"Trình duyệt ({bad[0]}) bị tắt tiếng trong Volume Mixer của Windows")
        return ok("Trình duyệt mở tiếng trong Volume Mixer")

    def fix(self, ctx):
        ctx.win.unmute_browser_sessions(BROWSER_PROCESS_NAMES, volume_pct=100.0)
        return da_sua("Đã bật tiếng trình duyệt trong Volume Mixer")


class YtPlayerCheck(Check):
    id, group, title = "yt_player", "browser", "Trình phát YouTube"

    def detect(self, ctx):
        player = ctx.actions.player_state()
        if player is None:
            return bo_qua("Chưa có trình phát YouTube")
        app = ctx.actions.app_music_state()
        if app is not None and (app[0] or app[1] < LOW_PCT):
            return loi("Thanh Nhạc trên app đang tắt")
        if player.get("muted") or (player.get("volume") is not None and player["volume"] <= 0):
            return loi("Trình phát YouTube đang tắt tiếng")
        return ok("Trình phát YouTube đang mở tiếng")

    def fix(self, ctx):
        ctx.actions.ensure_app_music_on()
        ctx.actions.unmute_player()
        return da_sua("Đã bật tiếng nhạc YouTube")
