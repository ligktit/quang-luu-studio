"""
Quang Luu Studio - Send ALL MIDI Keys
Gui toan bo MIDI CC tu app_config.json qua port QuangLuuMIDI
"""
import json
import os
import time
import sys

# -- Import rtmidi --
try:
    import rtmidi
except ImportError:
    print("[LOI] Chua cai python-rtmidi!")
    print("      Goi: .venv\\Scripts\\pip install python-rtmidi")
    sys.exit(1)

# -- Fallback neu khong doc duoc app_config.json --
_FALLBACK_CC_MAP = {
    "tone_music"   : 10,
    "tone_voice"   : 11,
    "mix_music"    : 20,
    "mix_mic"      : 21,
    "mix_reverb"   : 22,
    "mix_backing"  : 23,
    "mode"         : 30,
    "autokey"      : 31,
    "score_trigger": 32,
    "key_root"     : 33,
    "key_scale"    : 34,
    "scale_type"   : 35,
    "tune_on_off"  : 36,
    "mute_music"   : 50,
    "mute_mic"     : 51,
    "mute_reverb"  : 52,
    "mute_backing" : 53,
    "mix_reverb_ex": 41,
}

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_config.json")


def _load_cc_map():
    """Doc midi_cc tu app_config.json — fallback ve map hardcoded neu loi."""
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
        cc_map = config.get("midi_cc")
        if isinstance(cc_map, dict) and cc_map:
            print(f"[INFO] Da doc {len(cc_map)} MIDI CC tu app_config.json")
            return {name: int(cc) for name, cc in cc_map.items()}
    except Exception as e:
        print(f"[WARN] Khong doc duoc app_config.json ({e}) — dung map mac dinh.")
    return dict(_FALLBACK_CC_MAP)


CC_MAP = _load_cc_map()

PORT_NAME = "QuangLuuMIDI"
CHANNEL   = 0  # MIDI channel 1 (0-indexed)

# -- Mo MIDI Out port --
midiout = rtmidi.MidiOut()
available = midiout.get_ports()

print("[INFO] Cac MIDI port hien co:")
for i, name in enumerate(available):
    print(f"  [{i}] {name}")
print()

port_index = None
for i, name in enumerate(available):
    if PORT_NAME.lower() in name.lower():
        port_index = i
        break

if port_index is None:
    print(f'[LOI] Khong tim thay port "{PORT_NAME}"!')
    print(f'      Vui long mo loopMIDI va tao port ten "{PORT_NAME}" truoc.')
    sys.exit(1)

midiout.open_port(port_index)
print(f"[OK] Da ket noi port [{port_index}]: {available[port_index]}")
print()

# -- Gui tung CC (64 -> 0 de Studio One learn) --
SUCCESS = 0
FAIL    = 0

for name, cc in CC_MAP.items():
    try:
        msg_on  = [0xB0 | CHANNEL, cc, 64]
        msg_off = [0xB0 | CHANNEL, cc,  0]
        midiout.send_message(msg_on)
        time.sleep(0.15)
        midiout.send_message(msg_off)
        time.sleep(0.08)
        print(f"  [OK] {name:<16}  CC={cc:>3}  -> 64, 0")
        SUCCESS += 1
    except Exception as e:
        print(f"  [!!] {name:<16}  CC={cc:>3}  -> LOI: {e}")
        FAIL += 1

# -- Ket qua --
print()
print(f"[XONG] Tong: {SUCCESS} thanh cong, {FAIL} loi.")
midiout.close_port()
del midiout
