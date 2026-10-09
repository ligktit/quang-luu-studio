"""Trạng thái kênh mà DAW báo về qua cổng phản hồi (QLS_PhanHoi).

Cubase (script MIDI Remote) phát CC 20–23 (fader) và CC 50–53 (mute) mỗi khi
kênh đổi. Studio One không phát gì → get() luôn None.
"""
import threading
import time
from dataclasses import dataclass
from typing import Optional

GROUPS = ("nhac", "mic", "vang", "be")
_FADER_KEYS = {"nhac": "mix_music", "mic": "mix_mic", "vang": "mix_reverb", "be": "mix_backing"}
_MUTE_KEYS = {"nhac": "mute_music", "mic": "mute_mic", "vang": "mute_reverb", "be": "mute_backing"}
_DEFAULTS = {"mix_music": 20, "mix_mic": 21, "mix_reverb": 22, "mix_backing": 23,
             "mute_music": 50, "mute_mic": 51, "mute_reverb": 52, "mute_backing": 53}


@dataclass(frozen=True)
class ChannelState:
    muted: Optional[bool]
    fader: Optional[int]
    ts: float


class DawFeedback:
    def __init__(self, midi_cc, clock=time.monotonic):
        def cc(key):
            return int((midi_cc or {}).get(key, _DEFAULTS[key]))
        self._fader = {cc(_FADER_KEYS[g]): g for g in GROUPS}
        self._mute = {cc(_MUTE_KEYS[g]): g for g in GROUPS}
        self._clock = clock
        self._state = {}
        self._cond = threading.Condition()

    def on_cc(self, cc, value) -> bool:
        cc, value = int(cc), int(value)
        with self._cond:
            if cc in self._mute:
                g = self._mute[cc]
                old = self._state.get(g)
                self._state[g] = ChannelState(value >= 64, old.fader if old else None, self._clock())
            elif cc in self._fader:
                g = self._fader[cc]
                old = self._state.get(g)
                self._state[g] = ChannelState(old.muted if old else None, value, self._clock())
            else:
                return False
            self._cond.notify_all()
            return True

    def get(self, group) -> Optional[ChannelState]:
        with self._cond:
            return self._state.get(group)

    def wait_for(self, group, pred, timeout) -> bool:
        def satisfied():
            st = self._state.get(group)
            return st is not None and bool(pred(st))
        with self._cond:
            return self._cond.wait_for(satisfied, timeout=timeout)
