from core.audio_doctor import default_checks
from core.audio_doctor.runner import Runner


def test_du_12_muc_dung_thu_tu():
    ids = [c.id for c in Runner(default_checks()).checks]
    assert ids == ["loopmidi", "daw_remote", "daw_running", "daw_dialog", "cubase_release_driver",
                   "ch_mic", "ch_music", "win_playback_default", "win_playback_mute", "win_mic",
                   "browser_session", "yt_player"]
