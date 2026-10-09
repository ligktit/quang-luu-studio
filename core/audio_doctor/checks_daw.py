"""Phần mềm thu âm: đang chạy chưa, có hộp thoại chặn không, Release Driver, kênh Mic/Nhạc."""
import os
import re

from core.audio_doctor.model import Check, ok, loi, khong_ro, da_sua, can_lam_tay

# Fader ≤ mức này coi như kéo hết. Thấp hơn nữa có thể là khách cố ý để nhỏ
# (Mic -9 dB trên app = CC 10 ở Cubase) — không được báo lỗi.
FADER_LOW_CC = 2
MIC_LOW_DB = -40.0         # thanh Mic trên app thấp hơn mức này coi như tắt
_RELEASE_RE = re.compile(r'(name="ReleaseHardware"\s+value=")(\d)(")')


class DawRunningCheck(Check):
    id, group, title = "daw_running", "daw", "Phần mềm thu âm đang chạy"
    timeout_s = 10.0
    fix_timeout_s = 200.0

    def detect(self, ctx):
        name = ctx.daw.display_name
        s = ctx.system
        if s.daw_main_window():
            return ok(f"{name} đang chạy")
        if s.daw_running():
            return loi(f"{name} đang mở nhưng chưa xong (còn nạp bài hoặc đang chờ hộp thoại)")
        path = (ctx.settings or {}).get("studio_one_path", "")
        if not path or not s.exists(path):
            return loi(f"Chưa mở {name}, và app chưa biết mở file nào",
                       fixable=False,
                       guide=("Bấm ⚙ Cài đặt → mục phần mềm thu âm → chọn file bài mẫu hoặc file .exe.",
                              f"Hoặc tự mở {name}."))
        return loi(f"Chưa mở {name}")

    def fix(self, ctx):
        name = ctx.daw.display_name
        s = ctx.system
        if not s.daw_running():
            if ctx.feedback is not None:
                ctx.feedback.reset()
            if not ctx.actions.launch_daw():
                return can_lam_tay(f"Không mở được {name}",
                                   guide=(f"Tự mở {name} từ biểu tượng trên màn hình.",))
        if not s.wait_daw_main_window(ctx.daw_wait_s):
            return can_lam_tay(f"{name} chưa mở xong sau {int(ctx.daw_wait_s // 60)} phút",
                               guide=(f"Xem {name} có đang hỏi gì không (hộp thoại) và trả lời.",))
        ctx.actions.sync_midi()
        return da_sua(f"Đã mở {name}")


class DawDialogCheck(Check):
    id, group, title = "daw_dialog", "daw", "Hộp thoại đang chờ"

    def detect(self, ctx):
        s = ctx.system
        if not s.daw_running() or s.daw_main_window():
            return ok("Không có hộp thoại nào đang chờ")
        dialogs = s.daw_dialogs()
        if not dialogs:
            return khong_ro(f"{ctx.daw.display_name} đang khởi động")
        title = dialogs[0][1]
        return loi(f"{ctx.daw.display_name} đang hỏi: «{title}» — trả lời hộp thoại này",
                   guide=("Đọc hộp thoại vừa hiện lên và chọn đúng (thường là OK / Đồng ý).",
                          "Không chắc thì bấm «Gửi cho kỹ thuật» bên dưới."))

    def fix(self, ctx):
        dialogs = ctx.system.daw_dialogs()
        if dialogs:
            ctx.system.focus_window(dialogs[0][0])
            return can_lam_tay(f"{ctx.daw.display_name} đang hỏi: «{dialogs[0][1]}» — trả lời hộp thoại này",
                               guide=("Hộp thoại đã được đưa lên trước màn hình.",))
        return da_sua("Hộp thoại đã đóng")


class CubaseReleaseDriverCheck(Check):
    id, group, title = "cubase_release_driver", "daw", "Cubase giữ card âm thanh khi chạy nền"
    # Gồm cả thời gian khách trả lời câu hỏi + đóng Cubase (lưu bài) + mở lại.
    fix_timeout_s = 600.0

    _GUIDE = ("Trong Cubase: Studio → Studio Setup → Audio System.",
              "Bỏ dấu «Release Driver when Application is in Background» rồi bấm OK.")

    def applies(self, ctx):
        return getattr(ctx.daw, "kind", "") == "cubase"

    def _files(self, ctx):
        s = ctx.system
        out = []
        for d in s.glob_dirs(os.path.join(s.appdata(), "Steinberg", "Cubase*")):
            f = os.path.join(d, "Defaults.xml")
            if s.exists(f):
                out.append(f)
        return out

    def _on(self, ctx):
        out = []
        for f in self._files(ctx):
            m = _RELEASE_RE.search(ctx.system.read_text(f))
            if m and m.group(2) == "1":
                out.append(f)
        return out

    def detect(self, ctx):
        if not self._files(ctx):
            return khong_ro("Không đọc được cấu hình Cubase")
        if self._on(ctx):
            return loi("Cubase đang bật «Release Driver when Application is in Background» — "
                       "app ẩn Cubase nên sẽ mất tiếng", guide=self._GUIDE)
        return ok("Cubase giữ card âm thanh cả khi chạy nền")

    def fix(self, ctx):
        s = ctx.system
        was_running = s.daw_running()
        if was_running:
            if not ctx.ask("Cần đóng Cubase để tắt «Release Driver when Application is in Background». "
                           "Đóng Cubase ngay?"):
                return can_lam_tay("Chưa sửa — cần đóng Cubase trước", guide=self._GUIDE)
            if not ctx.actions.close_daw():
                return can_lam_tay("Không đóng được Cubase", guide=self._GUIDE)
            if ctx.feedback is not None:
                ctx.feedback.reset()
        for f in self._on(ctx):
            s.backup(f)
            s.write_text(f, _RELEASE_RE.sub(r"\g<1>0\g<3>", s.read_text(f)))
        if was_running:
            # Chờ Cubase dựng xong rồi đồng bộ — các mục kênh chạy ngay sau đây.
            ctx.actions.launch_daw()
            if s.wait_daw_main_window(ctx.daw_wait_s):
                ctx.actions.sync_midi()
        return da_sua("Đã tắt «Release Driver when Application is in Background»")


class _ChannelCheck(Check):
    group = "daw"
    requires = ("loopmidi", "daw_running")
    fix_when_unknown = True
    fix_timeout_s = 15.0
    fb_group = ""
    label = ""

    def _app_problem(self, ctx):
        return None

    def _send_on(self, ctx):
        raise NotImplementedError

    def detect(self, ctx):
        name = ctx.daw.display_name
        problem = self._app_problem(ctx)
        if problem:
            return loi(problem)
        st = ctx.feedback.get(self.fb_group) if (ctx.feedback and ctx.daw.kind == "cubase") else None
        if st is None or st.muted is None:
            if ctx.daw.kind == "cubase":
                return khong_ro(f"Chưa nhận được trạng thái kênh {self.label} từ Cubase")
            return khong_ro(f"{name} không báo lại trạng thái kênh {self.label}")
        if st.muted:
            return loi(f"Kênh {self.label} đang tắt (mute) trong {name}")
        if st.fader is not None and st.fader <= FADER_LOW_CC:
            return loi(f"Fader kênh {self.label} trong {name} gần như kéo hết")
        return ok(f"Kênh {self.label} đang bật")

    def fix(self, ctx):
        name = ctx.daw.display_name
        self._send_on(ctx)
        if ctx.daw.kind == "cubase" and ctx.feedback is not None:
            if ctx.feedback.wait_for(self.fb_group, lambda s: s.muted is False, timeout=2.0):
                return da_sua(f"Đã bật kênh {self.label}")
            return can_lam_tay(f"Đã gửi lệnh bật kênh {self.label} nhưng Cubase chưa xác nhận",
                               guide=(f"Trong Cubase, xem track {self.label}: bỏ nút M (mute), kéo fader lên.",))
        return da_sua(f"Đã gửi lệnh bật kênh {self.label} ({name} không báo lại — "
                      f"nếu vẫn im, kiểm tra track {self.label} trong {name})")


class MicChannelCheck(_ChannelCheck):
    id, title = "ch_mic", "Kênh Mic"
    fb_group, label = "mic", "Mic"

    def _app_problem(self, ctx):
        st = ctx.actions.app_mic_state()
        if st is None:
            return None
        muted, level = st
        if muted:
            return "Kênh Mic đang tắt trên app"
        if level <= MIC_LOW_DB:
            return "Thanh Mic trên app đang kéo hết"
        return None

    def _send_on(self, ctx):
        ctx.actions.ensure_app_mic_on()
        ctx.send_cc(int(ctx.midi_cc.get("mute_mic", 51)), 0)


class MusicChannelCheck(_ChannelCheck):
    id, title = "ch_music", "Kênh Nhạc"
    fb_group, label = "nhac", "Nhạc"

    def _send_on(self, ctx):
        ctx.send_cc(int(ctx.midi_cc.get("mute_music", 50)), 0)
        ctx.send_cc(int(ctx.midi_cc.get("mix_music", 20)), int(ctx.daw.fader_unity_cc))
