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
    mm = {"mix_backing": [{"cc": 45}], "mix_mic": [{"cc": 60}]}
    s = shared_cc_numbers(MIDI_CC, [], {}, mm)
    assert s == frozenset({45})                       # 60 (dưới mix_mic) không phát đôi


def test_vang_rieng_tung_mic_khong_phat_doi():
    """Máy 826077C: tắt Vang mic dây làm tắt luôn vang mic không dây đang hát.
    Vang (mức, tắt, CC phụ) là của riêng từng mic — kể cả cấu hình cũ vẫn liệt kê."""
    cc = dict(MIDI_CC, mute_reverb=52)
    mm = {"mix_reverb": [{"cc": 41}, {"cc": 42}, {"cc": 43}, {"cc": 44}]}
    s = shared_cc_numbers(cc, ["mix_reverb", "mute_reverb", "be"], {}, mm)
    assert s == frozenset({47})


def test_mac_dinh_khong_con_vang_trong_danh_sach_phat_doi():
    from core.mic2 import DEFAULT_SHARED_NAMES
    assert "mix_reverb" not in DEFAULT_SHARED_NAMES and "mute_reverb" not in DEFAULT_SHARED_NAMES


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


def test_is_enabled_chi_studio_one():
    from core.mic2 import two_mics_configured
    assert not is_enabled({"mic_count": 2, "daw_kind": "cubase"})
    assert is_enabled({"mic_count": 2})                         # thiếu daw_kind = Studio One
    assert is_enabled({"mic_count": 2, "daw_kind": "studio_one"})
    assert is_enabled({"mic_count": 2, "daw_kind": "la_hoac"})  # lạ = Studio One (như daw.kind_of)
    # Ô "2 micro" trong Cài đặt đọc ý định gốc, không phụ thuộc DAW.
    assert two_mics_configured({"mic_count": 2, "daw_kind": "cubase"})
    assert not two_mics_configured({"mic_count": 1}) and not two_mics_configured(None)


def test_with_label_doi_mot_mic_giu_mic_kia():
    from core.mic2 import with_label
    s = {"mic_labels": {"mix_mic": "A", "mix_mic_2": "B"}}
    assert with_label(s, "mix_mic", "  Mic P420 ") == {"mix_mic": "Mic P420", "mix_mic_2": "B"}
    assert with_label({}, "mix_mic_2", "Mic KG") == {"mix_mic": "Mic Dây", "mix_mic_2": "Mic KG"}
    # Tên trống / không phải chuỗi -> về tên mặc định, không lưu chuỗi rỗng.
    assert with_label(s, "mix_mic", "  ")["mix_mic"] == "Mic Dây"
    assert with_label(s, "mix_mic_2", None)["mix_mic_2"] == "Mic Không Dây"
    # Không sửa dict settings gốc.
    assert s["mic_labels"] == {"mix_mic": "A", "mix_mic_2": "B"}


def test_with_label_tu_choi_khoa_la():
    import pytest
    from core.mic2 import with_label
    with pytest.raises(ValueError):
        with_label({}, "mix_reverb", "x")


def test_ten_vang_mic2_tu_suy_va_tu_dat():
    from core.mic2 import reverb2_label, with_label
    assert reverb2_label({}) == "Vang Mic Không Dây"
    assert reverb2_label({"mic_labels": {"mix_mic_2": "Mic KG"}}) == "Vang Mic KG"
    s = {"mic_labels": {"mix_mic_2": "Mic KG"}}
    s["mic_labels"] = with_label(s, "mix_reverb_2", " Vang KG ")
    assert reverb2_label(s) == "Vang KG"
    # Đổi tên mic vẫn giữ tên vang tự đặt; xoá trống -> về tên tự suy.
    s["mic_labels"] = with_label(s, "mix_mic", "Mic P420")
    assert s["mic_labels"] == {"mix_mic": "Mic P420", "mix_mic_2": "Mic KG", "mix_reverb_2": "Vang KG"}
    s["mic_labels"] = with_label(s, "mix_reverb_2", "")
    assert "mix_reverb_2" not in s["mic_labels"] and reverb2_label(s) == "Vang Mic KG"
