import os
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMessageBox

def register_shortcuts(dashboard):
    """
    Đăng ký bộ phím tắt trợ năng (QShortcut) toàn hệ thống cho MainDashboard.
    Bao gồm các phím điều khiển tone, mixer, chấm điểm, ghi âm.
    """
    
    # F1 -> Help / Hướng dẫn
    def show_help():
        dashboard._show_message("Phím tắt: F1: Hướng dẫn | F2: Đọc trạng thái | [, ]: Tone nhạc | ;, ': Tone giọng | Ctrl+D: Auto-tune | Ctrl+R: Ghi âm | Ctrl+S: Lưu")
    QShortcut(QKeySequence("F1"), dashboard).activated.connect(show_help)

    # F2 -> State reading
    def read_state():
        state_str = f"Tone Nhạc {dashboard.tone_music_value}, Tone Giọng {dashboard.tone_voice_value}, Scale {dashboard.current_scale}"
        dashboard._show_message(state_str)
    QShortcut(QKeySequence("F2"), dashboard).activated.connect(read_state)

    # Ctrl+D -> Auto-tune
    QShortcut(QKeySequence("Ctrl+D"), dashboard).activated.connect(dashboard._on_tone_auto)
    
    # Ctrl+R -> Record
    QShortcut(QKeySequence("Ctrl+R"), dashboard).activated.connect(dashboard._on_record)

    # Ctrl+S -> Save
    QShortcut(QKeySequence("Ctrl+S"), dashboard).activated.connect(dashboard._on_save)

    # Ctrl+O -> Open List
    QShortcut(QKeySequence("Ctrl+O"), dashboard).activated.connect(dashboard._show_songs_list)

    # Ctrl+P -> Score
    QShortcut(QKeySequence("Ctrl+P"), dashboard).activated.connect(dashboard._on_score)

    # Ctrl+, -> Settings
    QShortcut(QKeySequence("Ctrl+,"), dashboard).activated.connect(dashboard._show_settings_dialog)

    # [ / ] -> Tone Nhạc -1 / +1
    def change_tone_music(delta):
        old_val = dashboard.tone_music_value
        new_val = max(-12, min(12, old_val + delta))
        if new_val != old_val:
            dashboard.tone_music_value = new_val
            # Giả định tools panel sẽ listen tới biến này, nhưng ta tạm update qua MIDI
            dashboard.engine.send_midi(dashboard.MIDI_CC.get("tone_music", 33), int(((new_val + 12) / 24) * 127))
            dashboard._show_message(f"Tone Nhạc {new_val}")
    QShortcut(QKeySequence("["), dashboard).activated.connect(lambda: change_tone_music(-1))
    QShortcut(QKeySequence("]"), dashboard).activated.connect(lambda: change_tone_music(1))

    # ; / ' -> Tone Giọng -1 / +1
    def change_tone_voice(delta):
        old_val = dashboard.tone_voice_value
        new_val = max(-12, min(12, old_val + delta))
        if new_val != old_val:
            dashboard.tone_voice_value = new_val
            dashboard.engine.send_midi(dashboard.MIDI_CC.get("tone_voice", 32), int(((new_val + 12) / 24) * 127))
            dashboard._show_message(f"Tone Giọng {new_val}")
    QShortcut(QKeySequence(";"), dashboard).activated.connect(lambda: change_tone_voice(-1))
    QShortcut(QKeySequence("'"), dashboard).activated.connect(lambda: change_tone_voice(1))

    # Mute channels (Ctrl+1, 2, 3, 4)
    def toggle_mute(key):
        if key in dashboard._mixer_channels:
            channel = dashboard._mixer_channels[key]
            current_mute = dashboard.mute_states.get(key, False)
            if hasattr(channel, 'mute_btn'):
                channel.mute_btn.click()
            else:
                channel.set_muted(not current_mute)
    QShortcut(QKeySequence("Ctrl+1"), dashboard).activated.connect(lambda: toggle_mute("mix_music"))
    QShortcut(QKeySequence("Ctrl+2"), dashboard).activated.connect(lambda: toggle_mute("mix_mic"))
    QShortcut(QKeySequence("Ctrl+3"), dashboard).activated.connect(lambda: toggle_mute("mix_reverb"))
    QShortcut(QKeySequence("Ctrl+4"), dashboard).activated.connect(lambda: toggle_mute("mix_backing"))
