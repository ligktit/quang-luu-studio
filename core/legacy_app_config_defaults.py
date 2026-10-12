r"""Mọi giá trị app_config.json từng đóng gói, theo khoá / khoá con (DỮ LIỆU SINH TỰ ĐỘNG).

Bộ cài Inno cài app_config.json với `onlyifdoesntexist`, nên {app}\app_config.json
trên máy khách là bản của LẦN CÀI ĐẦU, không phải bản mới nhất. Khi chuyển cấu hình
bản cũ sang lớp người dùng (core.first_run.migrate_legacy_app_config), giá trị trùng
BẤT KỲ mặc định nào từng đóng gói không phải khách chọn → bỏ, để mặc định hiện tại thắng.

Bảng đóng băng: bản Velopack không còn app_config.json kiểu Inno, nên không cần sinh lại.
Sinh một lần ở gốc repo bằng `python3 gen.py > bảng` với gen.py:

    import json, pprint, subprocess
    T, S = {}, {}
    for h in subprocess.run(["git", "log", "--full-history", "--format=%H", "--", "app_config.json"], capture_output=True, text=True, check=True).stdout.split():
        d = json.loads(subprocess.run(["git", "show", h + ":app_config.json"], capture_output=True, check=True).stdout.decode("utf-8-sig"))
        for k, v in d.items():
            for lst, x in ([(S.setdefault(k, {}).setdefault(sk, []), sv) for sk, sv in v.items()] if isinstance(v, dict) else [(T.setdefault(k, []), v)]):
                if all(json.dumps(x, sort_keys=True) != json.dumps(y, sort_keys=True) for y in lst):
                    lst.append(x)
    print("SHIPPED_VALUES = " + pprint.pformat(T, width=100) + "\n\nSHIPPED_SUB_VALUES = " + pprint.pformat(S, width=100))
"""

SHIPPED_VALUES = {'js_runtime_path': [''],
 'license_server_url': ['https://qlstudio.duckdns.org'],
 'midi_port_name': ['QuangLuuMIDI'],
 'youtube_cookie_browser': ['auto'],
 'youtube_cookie_file': [''],
 'youtube_cookie_profile': [''],
 'youtube_player_clients': [[]],
 'youtube_pot_auto_download': [True],
 'youtube_pot_enabled': [True],
 'ytdlp_auto_update': [True]}

SHIPPED_SUB_VALUES = {'accessibility': {'announce_focus': [False, True],
                   'announce_state': [False, True],
                   'focus_ring_thick': [False],
                   'font_scale': [1.0],
                   'high_contrast': [False],
                   'tts_enabled': [False, True],
                   'tts_engine': ['piper'],
                   'tts_piper_voice': [''],
                   'tts_rate': [180],
                   'tts_voice': [''],
                   'voice_command_enabled': [False, True],
                   'voice_command_hotkey': ['Ctrl+Space'],
                   'voice_model': ['small']},
 'key_midi_map': {'A': [103],
                  'A#': [115],
                  'Ab': [92],
                  'B': [127],
                  'Bb': [115],
                  'C': [0],
                  'C#': [11],
                  'D': [23],
                  'D#': [34],
                  'Db': [11],
                  'E': [46],
                  'Eb': [34],
                  'F': [57],
                  'F#': [69],
                  'G': [80],
                  'G#': [92]},
 'midi_cc': {'autokey': [31],
             'be': [47],
             'fix_meo': [45, 36],
             'key_root': [33],
             'key_scale': [34],
             'mix_backing': [23],
             'mix_mic': [21],
             'mix_music': [20],
             'mix_reverb': [22],
             'mode': [30],
             'mode_danca': [46, 30],
             'mode_datheloai': [39],
             'mode_lofi': [37],
             'mode_remix': [38],
             'mute_backing': [53],
             'mute_mic': [51],
             'mute_music': [50],
             'mute_reverb': [52],
             'ready_ping': [49],
             'scale_type': [35],
             'score_trigger': [32],
             'tat_on': [48],
             'tone_auto': [40, 31],
             'tone_music': [10],
             'tone_voice': [11],
             'tune_on_off': [36],
             'voice_fx': [54]},
 'mode_config': {'Dân Ca': [{'cc': 46, 'off_value': 0, 'on_value': 127},
                            {'cc': 30, 'off_value': 0, 'on_value': 127}],
                 'Lofi': [{'cc': 37, 'off_value': 0, 'on_value': 127}],
                 'Remix': [{'cc': 38, 'off_value': 0, 'on_value': 127}],
                 'Đa Thể Loại': [{'cc': 39, 'off_value': 0, 'on_value': 127}]},
 'mode_midi_map': {'Dân Ca': [42],
                   'Fix Méo': [127],
                   'Lofi': [45],
                   'Remix': [54],
                   'Đa Thể Loại': [63]},
 'mute_multi_cc': {'mix_backing': [[]],
                   'mix_mic': [[]],
                   'mix_music': [[]],
                   'mix_reverb': [[{'cc': 41, 'off_value': 0, 'on_value': 127},
                                   {'cc': 42, 'off_value': 0, 'on_value': 127},
                                   {'cc': 43, 'off_value': 0, 'on_value': 127},
                                   {'cc': 44, 'off_value': 0, 'on_value': 127}],
                                  [{'cc': 41, 'off_value': 0, 'on_value': 127}]]},
 'scale_midi_map': {'Major': [13], 'Minor': [18]},
 'scale_values': {'major': [13], 'minor': [18]},
 'toggle_invert': {'be': [False], 'fix_meo': [False], 'tat_on': [False], 'tone_auto': [False]}}
