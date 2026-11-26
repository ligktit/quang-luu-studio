"""Cầu nối app ↔ DAW: loopMIDI và bản điều khiển (surface SO / script Cubase)."""
import os

from core import so_surface
from core.audio_doctor.model import Check, ok, loi, khong_ro, da_sua, can_lam_tay

_SO_SURFACE = "studio_one/QuangLuuMIDI.surface.xml"

LOOPMIDI_PORTS_KEY = r"Software\Tobias Erichsen\loopMIDI\Ports"
_LOOPMIDI_EXE = "loopMIDI.exe"


class LoopMidiCheck(Check):
    id, group, title = "loopmidi", "bridge", "Cổng MIDI (loopMIDI)"
    timeout_s = 10.0
    fix_timeout_s = 40.0

    def _missing(self, ctx):
        outs, ins = ctx.system.midi_ports()
        missing = []
        if not any(ctx.midi_port in n for n in outs):
            missing.append(ctx.midi_port)
        if not any(ctx.feedback_port in n for n in ins):
            missing.append(ctx.feedback_port)
        return missing

    def detect(self, ctx):
        missing = self._missing(ctx)
        if not missing:
            return ok("loopMIDI đang chạy, đủ cổng gửi và cổng phản hồi")
        if not ctx.system.find_loopmidi_exe():
            return loi("Máy chưa cài loopMIDI — nút bấm trên app không tới được phần mềm thu âm",
                       fixable=False,
                       guide=("Mở thư mục cài đặt app và chạy setup_all.bat.",
                              "Làm xong thì mở lại app."))
        if not ctx.system.process_running(_LOOPMIDI_EXE):
            return loi("loopMIDI chưa chạy — nút bấm trên app không tới được phần mềm thu âm")
        return loi("loopMIDI thiếu cổng: " + ", ".join(missing))

    def fix(self, ctx):
        s = ctx.system
        exe = s.find_loopmidi_exe()
        if not exe:
            return can_lam_tay("Máy chưa cài loopMIDI",
                               guide=("Chạy setup_all.bat trong thư mục cài đặt app.",))
        names = set(s.reg_names("HKCU", LOOPMIDI_PORTS_KEY))
        added = False
        for port in (ctx.midi_port, ctx.feedback_port):
            if port not in names:
                s.reg_set("HKCU", LOOPMIDI_PORTS_KEY, port, port)
                added = True
        # loopMIDI chỉ đọc danh sách cổng lúc khởi động.
        restarted_under_daw = False
        if added and s.process_running(_LOOPMIDI_EXE):
            if s.daw_running():
                # Tắt loopMIDI là DAW mất cổng tới khi mở lại → hỏi trước.
                if not ctx.ask("Cần khởi động lại loopMIDI để thêm cổng. Phần mềm thu âm sẽ mất kết nối "
                               "MIDI tới khi bạn mở lại nó. Tiếp tục?"):
                    return can_lam_tay("Chưa sửa — loopMIDI thiếu cổng " + ", ".join(self._missing(ctx)),
                                       guide=("Tắt phần mềm thu âm, rồi bấm «Tự sửa lại».",))
                restarted_under_daw = True
            s.kill_process(_LOOPMIDI_EXE)
            ctx.sleep(2)
        if not s.process_running(_LOOPMIDI_EXE):
            s.start_process(exe)
        for _ in range(10):
            if not self._missing(ctx):
                break
            ctx.sleep(1)
        if self._missing(ctx):
            return can_lam_tay("Đã mở loopMIDI nhưng chưa thấy đủ cổng",
                               guide=("Mở loopMIDI, gõ tên cổng QuangLuuMIDI vào ô 'New port-name' rồi bấm +.",
                                      "Làm tương tự với QLS_PhanHoi."))
        ctx.actions.reconnect_midi()
        if restarted_under_daw:
            return can_lam_tay("Đã sửa loopMIDI — Khởi động lại phần mềm thu âm để nhận lại cổng MIDI",
                               guide=("Lưu bài, tắt phần mềm thu âm rồi mở lại.",))
        return da_sua("Đã bật loopMIDI và nối lại MIDI")


class DawRemoteCheck(Check):
    id, group, title = "daw_remote", "bridge", "Bản điều khiển trong phần mềm thu âm"

    def _pairs(self, ctx):
        """[(nguồn đi kèm app, đích trên máy)] cho DAW đang chọn; None = chưa xác định được."""
        s = ctx.system
        if ctx.daw.kind == "cubase":
            dst = os.path.join(s.documents(), "Steinberg", "Cubase", "MIDI Remote", "Driver Scripts",
                               "Local", "QuangLuu", "QuangLuuMIDI", "QuangLuu_QuangLuuMIDI.js")
            return [("cubase/QuangLuu_QuangLuuMIDI.js", dst)]
        dirs = s.glob_dirs(os.path.join(s.appdata(), "PreSonus", "Studio One*"))
        if not dirs:
            return None
        pairs = []
        for d in dirs:
            base = os.path.join(d, "User Devices", "QuangLuuMIDI")
            pairs.append((_SO_SURFACE, os.path.join(base, "QuangLuuMIDI.surface.xml")))
            pairs.append(("studio_one/deviceinfo.xml", os.path.join(base, "deviceinfo.xml")))
        return pairs

    @staticmethod
    def _read(ctx, path):
        try:
            return ctx.system.read_text(path)
        except (OSError, UnicodeError, KeyError):
            return None

    def _stale(self, ctx, pairs):
        s = ctx.system
        out = []
        for rel, dst in pairs:
            src = s.bundled(rel)
            if src is None:
                continue
            if s.exists(dst) and s.sha256(dst) == s.sha256(src):
                continue
            if (rel == _SO_SURFACE and s.exists(dst)
                    and so_surface.covers(self._read(ctx, src), self._read(ctx, dst))):
                # Studio One ghi lại file khi kỹ thuật học control mới → SHA khác nhưng
                # đủ mọi control của app: không cũ (máy 826077C, 2026-11-26).
                continue
            out.append((src, dst))
        return out

    def _install(self, ctx, src, dst):
        """Chép bản đi kèm; riêng surface Studio One thì gộp, giữ control kỹ thuật tự học."""
        s = ctx.system
        merged = None
        if s.exists(dst) and dst.endswith(os.path.basename(_SO_SURFACE)):
            src_text, dst_text = self._read(ctx, src), self._read(ctx, dst)
            if src_text is not None and dst_text is not None:
                merged = so_surface.merge(src_text, dst_text)
        if s.exists(dst):
            s.backup(dst)
        if merged is not None:
            s.write_text(dst, merged)
        else:
            s.copy(src, dst)

    def detect(self, ctx):
        name = ctx.daw.display_name
        pairs = self._pairs(ctx)
        if pairs is None:
            return khong_ro(f"{name} chưa chạy lần nào trên máy này")
        if not any(ctx.system.bundled(rel) for rel, _ in pairs):
            return khong_ro("Không thấy bản điều khiển đi kèm app")
        stale = self._stale(ctx, pairs)
        if any(ctx.system.is_readonly(dst) for _, dst in stale):
            # Thường là kỹ thuật sửa tay rồi khoá lại cho app khỏi chép đè (máy 3, 2026-10-28).
            return loi(f"Bản điều khiển trong {name} khác bản đi kèm app và đang khoá chỉ đọc — app không ghi đè",
                       fixable=False, guide=self._GUIDE_KHOA)
        if stale:
            return loi(f"Bản điều khiển trong {name} chưa cài hoặc đã cũ — nút mới trên app sẽ không ăn")
        return ok(f"Bản điều khiển trong {name} đúng bản đi kèm app")

    _GUIDE_KHOA = ("Nếu kỹ thuật đã sửa riêng bản này cho máy bạn thì giữ nguyên.",
                   "Không chắc thì bấm «Gửi cho kỹ thuật» bên dưới.")

    def fix(self, ctx):
        name = ctx.daw.display_name
        s = ctx.system
        for src, dst in self._stale(ctx, self._pairs(ctx) or []):
            try:
                self._install(ctx, src, dst)
            except OSError as e:
                return can_lam_tay(f"Không ghi được bản điều khiển: {e.strerror or e}",
                                   guide=(f"Tắt {name} rồi bấm «Tự sửa lại».",
                                          "Vẫn không được thì bấm «Gửi cho kỹ thuật» bên dưới."))
        if ctx.system.daw_running():
            return can_lam_tay(f"Đã chép bản mới — Khởi động lại {name} để nạp",
                               guide=(f"Lưu bài rồi tắt {name}, sau đó mở lại.",))
        return da_sua(f"Đã cài bản điều khiển mới cho {name}")
