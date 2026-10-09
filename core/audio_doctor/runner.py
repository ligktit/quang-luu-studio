"""Chạy các Check theo thứ tự phụ thuộc, ở chế độ chỉ kiểm tra hoặc sửa."""
import json
import os
import threading
import time
import traceback
from dataclasses import dataclass, field, replace

from core.audio_doctor.model import (
    BLOCKING, GROUP_ORDER, Finding, Status, bo_qua, khong_ro,
)


def _order(checks):
    ordered = sorted(checks, key=lambda c: GROUP_ORDER.index(c.group))
    seen = set()
    for c in ordered:
        missing = [r for r in c.requires if r not in seen]
        if missing:
            raise ValueError(f"Check {c.id!r} cần {missing} chạy trước")
        seen.add(c.id)
    return ordered


def _call_with_timeout(fn, timeout):
    box = {}

    def target():
        try:
            box["v"] = fn()
        except BaseException as e:  # noqa: BLE001 — chuyển nguyên về luồng gọi
            box["e"] = e

    t = threading.Thread(target=target, daemon=True, name="audio-doctor-call")
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise TimeoutError(f"quá {timeout:.0f} s")
    if "e" in box:
        raise box["e"]
    return box["v"]


@dataclass
class RunReport:
    source: str
    mode: str
    started: float
    checks: list = field(default_factory=list)
    results: dict = field(default_factory=dict)

    def problems(self):
        return [(c, self.results[c.id]) for c in self.checks
                if c.id in self.results
                and self.results[c.id].status in (Status.LOI, Status.CAN_LAM_TAY)]

    def summary(self) -> str:
        lines = []
        for c in self.checks:
            f = self.results.get(c.id)
            if f is not None:
                lines.append(f"[{f.status.value}] {c.title}: {f.message}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.started)),
            "source": self.source,
            "mode": self.mode,
            "results": {cid: {"status": f.status.value, "message": f.message, "detail": f.detail}
                        for cid, f in self.results.items()},
        }


def append_log(report, path):
    try:
        os.makedirs(os.path.dirname(str(path)), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(report.to_dict(), ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[AUDIO DOCTOR] Không ghi được nhật ký: {e}")


class Runner:
    def __init__(self, checks):
        self._checks = _order(list(checks))
        # Một lượt tại một thời điểm: bấm Tự sửa giữa lúc lượt khởi động đang
        # chạy thì chờ lượt kia xong, không để hai lượt cùng mở loopMIDI/DAW.
        self._lock = threading.Lock()

    @property
    def checks(self):
        return list(self._checks)

    def run(self, ctx, mode, source, on_progress=None) -> RunReport:
        assert mode in ("check", "fix")
        with self._lock:
            return self._run(ctx, mode, source, on_progress)

    def _emit(self, on_progress, check, finding):
        if on_progress is None:
            return
        try:
            on_progress(check, finding)
        except Exception as e:
            print(f"[AUDIO DOCTOR] on_progress lỗi: {e}")

    def _safe(self, fn, timeout, what):
        try:
            result = _call_with_timeout(fn, timeout)
            if not isinstance(result, Finding):
                return khong_ro("Không kiểm tra được", detail=f"{what} trả {result!r}")
            return result
        except TimeoutError as e:
            return khong_ro("Kiểm tra quá lâu, bỏ qua", detail=f"{what}: {e}")
        except Exception:
            return khong_ro("Không kiểm tra được", detail=traceback.format_exc())

    def _run(self, ctx, mode, source, on_progress):
        report = RunReport(source=source, mode=mode, started=time.time())
        titles = {c.id: c.title for c in self._checks}
        for c in self._checks:
            try:
                if not c.applies(ctx):
                    continue
            except Exception:
                continue
            report.checks.append(c)
            blocked = [r for r in c.requires
                       if r in report.results and report.results[r].status in BLOCKING]
            if blocked:
                f = bo_qua("Chờ sửa «" + "», «".join(titles[r] for r in blocked) + "» trước")
                report.results[c.id] = f
                self._emit(on_progress, c, f)
                continue
            self._emit(on_progress, c, None)
            f = self._safe(lambda: c.detect(ctx), c.timeout_s, f"{c.id}.detect")
            if mode == "fix":
                f = self._fix(c, ctx, f)
            report.results[c.id] = f
            self._emit(on_progress, c, f)
        return report

    def _fix(self, c, ctx, f):
        wants = ((f.status is Status.LOI and f.fixable)
                 or (f.status is Status.KHONG_RO and c.fix_when_unknown))
        if not wants:
            if f.status is Status.LOI:
                return replace(f, status=Status.CAN_LAM_TAY)
            return f
        fixed = self._safe(lambda: c.fix(ctx), c.fix_timeout_s, f"{c.id}.fix")
        if fixed.status is Status.CAN_LAM_TAY:
            return fixed
        again = self._safe(lambda: c.detect(ctx), c.timeout_s, f"{c.id}.detect")
        if again.status is Status.OK:
            msg = fixed.message if fixed.status is Status.DA_SUA else again.message
            return Finding(Status.DA_SUA, msg)
        if again.status is Status.KHONG_RO and fixed.status is Status.DA_SUA:
            return fixed
        guide = again.guide or f.guide or fixed.guide
        detail = "\n".join(x for x in (fixed.detail, again.detail) if x)
        return Finding(Status.CAN_LAM_TAY, again.message, detail=detail, guide=guide)
