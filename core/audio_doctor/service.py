"""Ghép Runner với vòng chờ khởi động và nhật ký. Không biết gì về Qt."""
import threading
import time

from core.audio_doctor.runner import Runner, append_log
from core.audio_doctor.startup import StartupGate


class AudioDoctorService:
    def __init__(self, ctx_factory, checks, log_path=None):
        self._ctx_factory = ctx_factory
        self.runner = Runner(checks)
        self._log_path = log_path
        self._stop = threading.Event()
        self.last_report = None

    def stop(self):
        self._stop.set()

    def run(self, mode, source, ask=None, on_progress=None):
        ctx = self._ctx_factory(ask=ask)
        report = self.runner.run(ctx, mode, source, on_progress=on_progress)
        self.last_report = report
        if self._log_path:
            append_log(report, self._log_path)
        return report

    def startup_loop(self, on_report, is_daw_ready, wait_s=180.0, poll_s=3.0,
                     now=time.monotonic, sleep=time.sleep, max_s=3600.0):
        start = now()
        gate = StartupGate(wait_s=wait_s, settle_s=10.0, start=start)
        while not self._stop.is_set() and not gate.done and now() - start < max_s:
            try:
                ready = bool(is_daw_ready())
            except Exception:
                ready = False
            action = gate.update(now(), ready)
            if action:
                report = self.run("check", "startup")
                try:
                    on_report(report, action)
                except Exception as e:
                    print(f"[AUDIO DOCTOR] on_report lỗi: {e}")
                if gate.done:
                    break
            sleep(poll_s)

    def start_startup_watch(self, **kwargs):
        t = threading.Thread(target=self.startup_loop, kwargs=kwargs, daemon=True,
                             name="audio-doctor-startup")
        t.start()
        return t
