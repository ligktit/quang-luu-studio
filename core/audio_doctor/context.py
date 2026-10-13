"""Mọi thứ một Check được phép chạm tới — gom vào một chỗ để test bằng đồ giả."""
import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class DoctorContext:
    """
    actions — đối tượng thao tác trên app (tầng UI cài đặt, xem
    ui/audio_doctor_bridge.DashboardDoctorActions). Các method:
        launch_daw() -> bool
        reconnect_midi() -> bool
        sync_midi() -> None
        close_daw() -> bool
        app_mic_state() -> Optional[tuple[bool, float]]     # (muted, mức dB)
        ensure_app_mic_on() -> None
        app_music_state() -> Optional[tuple[bool, int]]     # (muted, % âm lượng)
        ensure_app_music_on() -> None
        player_state() -> Optional[dict]   # {"muted": bool|None, "volume": int|None}; None = không có player
        unmute_player() -> bool
        save_setting(key, value) -> None
    """
    settings: dict
    daw: Any                      # core.daw.DawProfile
    system: Any                   # core.audio_doctor.system.SystemProbe
    win: Any                      # core.audio_doctor.win_audio.WinAudio
    actions: Any
    feedback: Any = None          # core.audio_doctor.feedback.DawFeedback
    send_cc: Callable[[int, int], bool] = lambda cc, value: False
    midi_cc: dict = field(default_factory=dict)
    midi_port: str = "QuangLuuMIDI"
    feedback_port: str = "QLS_PhanHoi"
    ask: Callable[[str], bool] = lambda question: False
    sleep: Callable[[float], None] = time.sleep
    daw_wait_s: float = 180.0
