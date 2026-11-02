from core.mic2 import is_enabled, shared_cc_numbers, expand

MIDI_CC = {"mix_mic": 21, "mute_mic": 51, "key_root": 33, "scale_type": 35, "be": 47, "mix_reverb": 22}
MODES = {"Lofi": {"cc": 37, "on_value": 127, "off_value": 0}}


def test_is_enabled_only_for_two():
    assert not is_enabled(None) and not is_enabled({}) and not is_enabled({"mic_count": 1})
    assert is_enabled({"mic_count": 2}) and is_enabled({"mic_count": "2"})


def test_shared_excludes_per_mic():
    s = shared_cc_numbers(MIDI_CC, ["key_root", "scale_type", "be", "mix_mic"], MODES, {})
    assert s == frozenset({33, 35, 47, 37})          # 21 bị trừ dù có trong names


def test_shared_includes_custom_mute_multi():
    mm = {"mix_reverb": [{"cc": 41}, {"cc": 42}, {"cc": 43}, {"cc": 44}], "mix_mic": [{"cc": 60}]}
    s = shared_cc_numbers(MIDI_CC, ["mix_reverb"], {}, mm)
    assert s == frozenset({22, 41, 42, 43, 44})       # 60 (dưới mix_mic) không phát đôi


def test_shared_skips_unknown_names():
    assert shared_cc_numbers(MIDI_CC, ["khong_co"], {}, {"x": [{"bad": 1}]}) == frozenset()


def test_shared_skips_malformed_entries():
    mm = {"a": [{"cc": "x"}, "rac", {"cc": 70}], "b": "khong-phai-list"}
    assert shared_cc_numbers(MIDI_CC, [], {"m": "rac"}, mm) == frozenset({70})


def test_expand_order():
    assert expand([(33, 2), (35, 13)], frozenset({33, 35})) == [(0, 33, 2), (0, 35, 13), (1, 33, 2), (1, 35, 13)]
    assert expand([(21, 76)], frozenset({33})) == [(0, 21, 76)]


def test_labels_mac_dinh_va_ten_tu_dat():
    from core.mic2 import labels
    assert labels({}) == {"mix_mic": "Mic Dây", "mix_mic_2": "Mic Không Dây"}
    assert labels(None) == {"mix_mic": "Mic Dây", "mix_mic_2": "Mic Không Dây"}
    assert labels({"mic_labels": {"mix_mic": " Shure ", "mix_mic_2": ""}}) == {
        "mix_mic": "Shure", "mix_mic_2": "Mic Không Dây"}
    assert labels({"mic_labels": "rac"}) == {"mix_mic": "Mic Dây", "mix_mic_2": "Mic Không Dây"}
