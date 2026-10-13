"""Đồ giả cho test check: hệ thống, Windows audio, thao tác app."""
from core.audio_doctor.context import DoctorContext
from core.audio_doctor.feedback import DawFeedback
from core.daw import STUDIO_ONE

CC = {"mix_music": 20, "mix_mic": 21, "mix_reverb": 22, "mix_backing": 23,
      "mute_music": 50, "mute_mic": 51, "mute_reverb": 52, "mute_backing": 53}


class FakeSystem:
    def __init__(self):
        self.procs = set()
        self.outs, self.ins = [], []
        self.loopmidi_exe = r"C:\Program Files\Tobias Erichsen\loopMIDI\loopMIDI.exe"
        self.reg = {}                 # (root, key, name) -> value
        self.files = {}               # path -> text
        self.dirs = []
        self.bundle = {}              # rel -> path
        self.running = False
        self.main_window = False
        self.dialogs = []
        self.focused = []
        self.started = []
        self.killed = []
        self.backups = []
        self.on_start = None          # callback khi start_process

    def process_running(self, exe): return exe.lower() in self.procs
    def kill_process(self, exe): self.killed.append(exe); self.procs.discard(exe.lower())

    def start_process(self, path):
        self.started.append(path)
        if self.on_start:
            self.on_start(path)

    def midi_ports(self): return list(self.outs), list(self.ins)
    def find_loopmidi_exe(self): return self.loopmidi_exe
    def reg_get(self, root, key, name): return self.reg.get((root, key, name))
    def reg_set(self, root, key, name, value): self.reg[(root, key, name)] = value
    def reg_names(self, root, key): return [n for (r, k, n) in self.reg if r == root and k == key]
    def appdata(self): return r"C:\U\AppData\Roaming"
    def documents(self): return r"C:\U\Documents"

    def glob_dirs(self, pattern):
        import fnmatch
        return [d for d in self.dirs if fnmatch.fnmatch(d.lower(), pattern.lower())]

    def exists(self, path): return path in self.files
    def read_text(self, path): return self.files[path]
    def write_text(self, path, text): self.files[path] = text
    def sha256(self, path): return None if path not in self.files else str(hash(self.files[path]))
    def copy(self, src, dst): self.files[dst] = self.files[src]

    def backup(self, path):
        self.backups.append(path)
        return path + ".bak"

    def bundled(self, rel): return self.bundle.get(rel)
    def daw_running(self): return self.running
    def daw_main_window(self): return self.main_window
    def wait_daw_main_window(self, timeout): return self.main_window
    def daw_dialogs(self): return list(self.dialogs)
    def focus_window(self, hwnd): self.focused.append(hwnd)


class FakeWin:
    def __init__(self):
        self.ok = True
        self.devices = []
        self.defaults = (None, None)
        self.capture = None
        self.state = {}               # id -> (muted, pct)
        self.sessions = []            # (name, muted, pct)
        self.set_default_calls = []

    def available(self): return self.ok
    def render_devices(self): return list(self.devices)
    def name_of(self, dev_id): return next((d.name for d in self.devices if d.id == dev_id), None)
    def default_render_ids(self): return self.defaults
    def default_capture_id(self): return self.capture

    def set_default_render(self, dev_id):
        self.set_default_calls.append(dev_id)
        self.defaults = (dev_id, dev_id)

    def endpoint_state(self, dev_id): return self.state[dev_id]

    def set_endpoint(self, dev_id, muted=False, volume_pct=None):
        old = self.state.get(dev_id, (False, 100.0))
        self.state[dev_id] = (muted, old[1] if volume_pct is None else volume_pct)

    def browser_sessions(self, names=()): return list(self.sessions)

    def unmute_browser_sessions(self, names=(), volume_pct=100.0):
        self.sessions = [(n, False, volume_pct) for n, _, _ in self.sessions]
        return len(self.sessions)


class FakeActions:
    def __init__(self):
        self.calls = []
        self.launch_ok = True
        self.close_ok = True
        self.mic = (False, 0.0)
        self.music = (False, 80)
        self.player = None
        self.settings_saved = {}
        self.on_launch = None

    def launch_daw(self):
        self.calls.append("launch_daw")
        if self.on_launch:
            self.on_launch()
        return self.launch_ok

    def reconnect_midi(self): self.calls.append("reconnect_midi"); return True
    def sync_midi(self): self.calls.append("sync_midi")
    def close_daw(self): self.calls.append("close_daw"); return self.close_ok
    def app_mic_state(self): return self.mic

    def ensure_app_mic_on(self):
        self.calls.append("ensure_app_mic_on")
        self.mic = (False, self.mic[1] if self.mic[1] > -40 else 0.0)

    def app_music_state(self): return self.music

    def ensure_app_music_on(self):
        self.calls.append("ensure_app_music_on")
        self.music = (False, max(self.music[1], 80))

    def player_state(self): return self.player

    def unmute_player(self):
        self.calls.append("unmute_player")
        if self.player:
            self.player = {"muted": False, "volume": max(self.player.get("volume") or 0, 80)}
        return True

    def save_setting(self, key, value): self.settings_saved[key] = value


def make_ctx(daw=STUDIO_ONE, settings=None, answers=None, **kw):
    system, win, actions = FakeSystem(), FakeWin(), FakeActions()
    sent = []
    asked = []
    answers = list(answers or [])

    def ask(q):
        asked.append(q)
        return answers.pop(0) if answers else False

    ctx = DoctorContext(
        settings=settings if settings is not None else {},
        daw=daw, system=system, win=win, actions=actions,
        feedback=DawFeedback(CC), send_cc=lambda cc, v: sent.append((cc, v)) or True,
        midi_cc=dict(CC), ask=ask, sleep=lambda s: None, **kw)
    ctx.sent, ctx.asked = sent, asked
    return ctx
