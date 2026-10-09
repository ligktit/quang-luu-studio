"""Tự sửa âm thanh — chẩn đoán và sửa lỗi âm thanh thường gặp."""
from core.audio_doctor.checks_bridge import LoopMidiCheck, DawRemoteCheck
from core.audio_doctor.checks_daw import (
    DawRunningCheck, DawDialogCheck, CubaseReleaseDriverCheck, MicChannelCheck, MusicChannelCheck,
)
from core.audio_doctor.checks_windows import WinPlaybackDefaultCheck, WinPlaybackMuteCheck, WinMicCheck
from core.audio_doctor.checks_browser import BrowserSessionCheck, YtPlayerCheck


def default_checks():
    return [
        LoopMidiCheck(), DawRemoteCheck(),
        DawRunningCheck(), DawDialogCheck(), CubaseReleaseDriverCheck(),
        MicChannelCheck(), MusicChannelCheck(),
        WinPlaybackDefaultCheck(), WinPlaybackMuteCheck(), WinMicCheck(),
        BrowserSessionCheck(), YtPlayerCheck(),
    ]
