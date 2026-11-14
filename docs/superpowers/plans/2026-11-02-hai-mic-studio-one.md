# Hai micro trên Studio One — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** App điều khiển được hai kênh mic trong Studio One: mỗi mic một thanh mức + nút tắt riêng; Key/Scale và mọi điều khiển giọng hát đến cả hai mic cùng lúc.

**Architecture:** Mic 2 = cùng số CC, MIDI channel 2 (status `0xB1`). Một module thuần `core/mic2.py` quyết định CC nào phát đôi; lớp gửi của engine (`send_midi`, `send_midi_pair`) tự phát đôi khi bật 2 mic, nên UI và luồng tone không phải biết có 2 mic. Thanh/nút Mic 2 gửi thẳng channel 2 qua `send_midi_on_channel`. Surface XML thêm bộ control `#B1`.

**Tech Stack:** Python 3.13, PySide6, mido (loopMIDI), Studio One control-surface XML, pytest + pytest-qt.

**Spec:** `docs/superpowers/specs/2026-11-02-hai-mic-studio-one-design.md`

## Global Constraints

- Mặc định `settings["mic_count"]` thiếu hoặc khác 2 → app gửi MIDI **y hệt hiện nay** (không tin nào trên channel 2, mixer không đổi).
- Mic 2 dùng MIDI channel index `1` (= kênh 2), cùng số CC với mic 1. Không chiếm CC mới.
- Cặp Key + Scale (cả hai kênh) gửi trong **một lần giữ `_send_lock`** — giữ nguyên tính nguyên tử của `bb15fa4` / `b0d46b3`.
- `mix_mic` (21) và `mute_mic` (51) **không** phát đôi.
- Cubase không đổi: không sửa `cubase/QuangLuu_QuangLuuMIDI.js`.
- Làm trong worktree tách từ `feat/velopack-installer` (thư mục chính đang có thay đổi chưa commit — không đụng).
- Test UI/engine chạy bằng Python Windows:
  `cmd.exe /c "D:\...\<worktree>\.venv\Scripts\python.exe -m pytest <tests> -q -p no:cacheprovider --rootdir=D:\...\<worktree>"`
  (venv dùng chung `D:\Projects\quang-luu-studio\.venv` nếu worktree chưa có). Sau khi chạy: `git checkout app_config.json`, đặt lại `settings.json`.

## Review Focus

1. **Đổi bài trong lúc bật 2 mic** — Key/Scale cũ không được lọt sang channel 2 sau Key mới (race đổi bài). → Task 2 test `test_pair_mirror_atomic_order`.
2. **Bật/tắt 2 mic trong Cài đặt rồi lưu** — mixer dựng lại đúng (có/không Mic 2), engine ngừng/bắt đầu phát đôi ngay, không cần mở lại app. → Task 4 test `test_toggle_mic_count_rebuilds_and_rewires`.
3. **Mở lại app** — mic đã tắt vẫn tắt (cả trên app lẫn lệnh gửi DAW lúc đồng bộ). → Task 4 test `test_mic_mutes_persist_and_resync`.
4. **`app_config.json` máy khách có `mute_multi_cc` khác mặc định** (vd Vang 41–44) — mọi CC đó phát đôi, trừ entry nằm dưới `mix_mic`. → Task 1 test `test_shared_includes_custom_mute_multi`.
5. **Audio Doctor khi chỉ một mic đang mở** — không báo "Kênh Mic đang tắt". → Task 5 test `test_mic_check_ok_when_one_mic_on`.

---

### Task 0: Kiểm trên Studio One thật (cổng chặn — làm trước khi viết code)

Việc tay, trên máy khách Studio One (qua UltraViewer, **hỏi trước xem có người đang dùng máy không**), có người dùng đồng ý.

**Files:**
- Create (tạm, không commit): `tools/tham_do_studio_one/kenh2_thu.surface.xml` = surface hiện tại + một control `keyRoot2` (`status="#B1" address="33"`).

- [ ] **Step 1:** Sao lưu `%APPDATA%\PreSonus\Studio One *\User Devices\QuangLuuMIDI\` và bài khách đang dùng.
- [ ] **Step 2:** Chép đè surface thử (KHÔNG gỡ/thêm lại thiết bị), mở lại Studio One, mở một bài cũ của khách.
  Kỳ vọng: các Control Link cũ (Key/Scale/Mute…) vẫn còn và vẫn ăn khi gửi từ app.
- [ ] **Step 3:** Gán `keyRoot2` vào tham số Key của Auto-Tune kênh `MIC KG`, gửi `control_change channel=1 control=33` bằng mido. Kỳ vọng: Key kênh KG đổi, Key P420 không đổi.
- [ ] **Step 4:** Ghi kết quả vào spec mục 7. Nếu Step 2 hỏng → dừng, báo người dùng (phải đổi cách triển khai surface). Nếu Step 3 hỏng → dùng phương án lùi trong spec mục 7 (bộ CC riêng trong dải trống, tránh 60–67) và sửa `MIC2_CHANNEL`/Task 3 tương ứng trước khi làm tiếp. Khôi phục bản sao lưu.

---

### Task 1: `core/mic2.py` + gửi nhiều kênh trong `MidiHandler`

**Files:**
- Create: `core/mic2.py`
- Modify: `core/midi.py` (thêm `send_messages`; `_listen_loop` lọc channel)
- Modify: `core/config.py` (`_DEFAULT_APP_CONFIG["mic2_shared_cc"]`, `AppConfig.get_mic2_shared_cc()`)
- Test: `tests/core/test_mic2.py`, `tests/core/test_midi.py`

**Interfaces:**
- Produces:
  - `core.mic2.MIC2_CHANNEL: int = 1`
  - `core.mic2.MIC_KEY = "mix_mic"`, `core.mic2.MIC2_KEY = "mix_mic_2"`
  - `core.mic2.DEFAULT_SHARED_NAMES: tuple[str, ...]` = `("tone_voice", "mix_reverb", "mode", "key_root", "key_scale", "scale_type", "tune_on_off", "tone_auto", "fix_meo", "be", "tat_on", "mute_reverb", "voice_fx", "mode_danca", "mode_lofi", "mode_remix", "mode_datheloai")`
  - `core.mic2.is_enabled(settings: dict | None) -> bool` — `True` chỉ khi `settings.get("mic_count") == 2` (chấp nhận `"2"`).
  - `core.mic2.shared_cc_numbers(midi_cc: dict, names: Iterable[str], mode_config: dict, mute_multi_cc: dict) -> frozenset[int]` — số CC của `names` + `mode_config[*]["cc"]` + mọi `mute_multi_cc[k][*]["cc"]` với `k != "mix_mic"`; luôn trừ `midi_cc["mix_mic"]`, `midi_cc["mute_mic"]`. Bỏ qua tên/entry hỏng.
  - `core.mic2.expand(pairs: Iterable[tuple[int, int]], shared: frozenset[int]) -> list[tuple[int, int, int]]` — trả `(channel, cc, value)`: toàn bộ `pairs` trên channel 0 theo thứ tự, **sau đó** các cặp có `cc in shared` trên `MIC2_CHANNEL`, giữ thứ tự.
  - `MidiHandler.send_messages(msgs: Iterable[tuple[int, int, int]]) -> bool` — gửi `(channel, cc, value)` trong một lần giữ `_send_lock`; `True` nếu tất cả thành công; không dừng giữa chừng.
  - `AppConfig.get_mic2_shared_cc() -> list[str]` (mặc định `list(DEFAULT_SHARED_NAMES)`).

- [ ] **Step 1: Viết test hỏng** (`tests/core/test_mic2.py`)

```python
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

def test_expand_order():
    assert expand([(33, 2), (35, 13)], frozenset({33, 35})) == [(0, 33, 2), (0, 35, 13), (1, 33, 2), (1, 35, 13)]
    assert expand([(21, 76)], frozenset({33})) == [(0, 21, 76)]
```

Trong `tests/core/test_midi.py` (dùng fixture `mock_mido` sẵn có):
- `test_send_messages_one_lock_all_channels`: `send_messages([(0,33,2),(1,33,2)])` → `mido.Message` gọi đúng 2 lần với `channel=0` rồi `channel=1`, trả `True`; không kết nối → `False`.
- `test_listen_loop_ignores_other_channels`: inport giả trả tin `channel=1 control=49` rồi `channel=0 control=49`; `on_cc_received` chỉ được gọi một lần với `(49, v)`.

- [ ] **Step 2:** Chạy `pytest tests/core/test_mic2.py tests/core/test_midi.py -q` (Python Linux được với 2 file này) → FAIL (module chưa có).
- [ ] **Step 3:** Viết `core/mic2.py`, `MidiHandler.send_messages`, lọc `msg.channel == 0` trong `_listen_loop`, khoá `mic2_shared_cc` trong config (kèm comment giải thích như các khoá khác).
- [ ] **Step 4:** Chạy lại → PASS; chạy thêm `tests/core/test_config.py`.
- [ ] **Step 5:** Commit `feat(mic2): module phát đôi CC cho mic 2 + MidiHandler gửi nhiều kênh`.

---

### Task 2: Engine phát đôi

**Files:**
- Modify: `core/engine/_midi.py`, `core/engine/__init__.py` (gọi `refresh_mic2_mirror()` trong `__init__` sau khi tạo `midi_handler`)
- Test: `tests/core/test_engine.py` (lớp test mới `TestMic2Mirror`)

**Interfaces:**
- Consumes: Task 1 (`mic2.is_enabled`, `mic2.shared_cc_numbers`, `mic2.expand`, `MidiHandler.send_messages`, `AppConfig.get_mic2_shared_cc`)
- Produces:
  - `SystemEngine.refresh_mic2_mirror() -> None` — đọc `self.settings` + `AppConfig` (midi_cc, mic2_shared_cc, mode_config, mute_multi_cc), gán `self._mic2_shared: frozenset[int]` (rỗng khi tắt).
  - `send_midi(cc, value, auto_reconnect=True)` / `send_midi_pair(cc1, val1, cc2, val2, auto_reconnect=True)`: chữ ký không đổi. Khi `_mic2_shared` rỗng → gọi `send_cc` / `send_cc_pair` như cũ (test cũ phải xanh nguyên). Khi không rỗng và có CC nằm trong tập → `send_messages(mic2.expand(...))`, giữ cơ chế reconnect + throttle cảnh báo.
  - `SystemEngine.send_midi_on_channel(channel: int, cc: int, value: int, auto_reconnect=True) -> bool` — gửi đúng một tin, không phát đôi.

- [ ] **Step 1: Viết test hỏng**
  - `test_mirror_off_by_default`: settings `{}` → `send_midi(33, 2)` gọi `midi_handler.send_cc(33, 2)`, không gọi `send_messages`.
  - `test_mirror_shared_cc`: settings `{"mic_count": 2}`, `refresh_mic2_mirror()` → `send_midi(33, 2)` gọi `send_messages([(0,33,2),(1,33,2)])`.
  - `test_mirror_skips_mix_mic`: `send_midi(21, 76)` khi bật → `send_cc(21, 76)`, không có channel 1.
  - `test_pair_mirror_atomic_order`: `send_midi_pair(33, 23, 35, 85)` khi bật → **một** lời gọi `send_messages([(0,33,23),(0,35,85),(1,33,23),(1,35,85)])`.
  - `test_refresh_turns_off`: bật → refresh → đặt `settings["mic_count"]=1` → refresh → `send_midi(33,2)` quay về `send_cc`.
  - `test_send_midi_on_channel`: gọi `send_messages([(1, 51, 127)])` và không phát đôi.
- [ ] **Step 2:** Chạy (Windows) `tests/core/test_engine.py -k "Mic2 or send_midi"` → FAIL.
- [ ] **Step 3:** Cài đặt như Interfaces.
- [ ] **Step 4:** Chạy lại toàn bộ `tests/core/test_engine.py` → PASS (gồm E-05, E-30 cũ).
- [ ] **Step 5:** Commit `feat(mic2): engine tự phát đôi CC dùng chung sang kênh MIDI 2`.

---

### Task 3: Surface XML kênh 2

**Files:**
- Modify: `studio_one/QuangLuuMIDI.surface.xml` (thêm khối "MIC 2 — MIDI CHANNEL 2" + cập nhật comment đầu file)
- Modify: `tests/test_surface_xml.py`

**Interfaces:**
- Consumes: `core.mic2.shared_cc_numbers`, `core.mic2.DEFAULT_SHARED_NAMES`
- Produces: control tên `<tên kênh 1>2` (vd `keyRoot2`, `scaleType2`, `muteMic2`, `mixMic2`, `muteMulti1_2`…), `status="#B1"`, `options="receive public"`, title tiếng Việt có hậu tố " (Mic 2)".

- [ ] **Step 1: Sửa/viết test**
  - `_declared_addresses()` đổi khoá thành `(status, address)`; các test cũ (`every_app_cc_has_a_control`, `no_orphan_controls`) chỉ xét `#B0` như trước; `no_duplicate_control_addresses` xét theo `(status, address)`.
  - `test_mic2_controls_match_shared_set`: tập address `#B1` == `shared_cc_numbers(mặc định config) ∪ {21, 51}`.
  - `test_mic2_controls_receive_only`: mọi control `#B1` không có `transmit`.
- [ ] **Step 2:** Chạy `pytest tests/test_surface_xml.py -q` → FAIL (thiếu control `#B1`).
- [ ] **Step 3:** Thêm control vào XML.
- [ ] **Step 4:** Chạy lại → PASS; chạy cả `tests/test_cubase_script.py` (không được đỏ).
- [ ] **Step 5:** Commit `feat(mic2): surface Studio One thêm bộ control kênh MIDI 2 cho mic 2`.

---

### Task 4: Mixer Mic 2, cài đặt, nhớ trạng thái, đồng bộ lại

**Files:**
- Modify: `ui/panels/mixer.py`, `frontend_qt.py` (khởi tạo `mute_states`, khối đồng bộ "Mute Mic / Vang / Bè" ~dòng 1146, hàm mới `_apply_mic_count_setting`), `ui/dialogs/settings_dialog.py` (tab Âm thanh: mục "Micro"), `ui/song_settings.py` (`_MIXER_NAMES["mix_mic_2"] = "mic2"`)
- Test: `tests/ui/test_mixer_mic2.py` (mới), `tests/ui/test_song_settings_recall.py`

**Interfaces:**
- Consumes: Task 1 (`MIC_KEY`, `MIC2_KEY`, `MIC2_CHANNEL`, `is_enabled`), Task 2 (`refresh_mic2_mirror`, `send_midi_on_channel`)
- Produces / khoá settings:
  - `settings["mic_count"]`: `1 | 2`
  - `settings["mic_labels"]`: `{"mix_mic": str, "mix_mic_2": str}`, mặc định `"Mic Dây"` / `"Mic Không Dây"`
  - `settings["mic_mutes"]`: `{"mix_mic": bool, "mix_mic_2": bool}` — ghi ngay (`ConfigManager.save_settings`) mỗi lần bấm tắt/mở mic khi bật 2 mic; chỉ đọc khi bật 2 mic.
  - `MainDashboard._apply_mic_count_setting() -> None` — gọi `engine.refresh_mic2_mirror()`, rồi `refresh_ui()`, rồi `_sync_midi_states()`.

Hành vi cần làm (người làm tự dựng code):
- `build_panel_mixer`: khi `is_enabled(settings)` → kênh `mix_mic` lấy nhãn `mic_labels["mix_mic"]`; chèn ngay sau nó một `HMixerChannel` `cc_key="mix_mic_2"` cùng icon/màu/dải/`has_mute`/`has_inf_bottom` với kênh Mic, nhãn `mic_labels["mix_mic_2"]`, mức từ `mixer_levels["mix_mic_2"]` (mặc định 0). Không bật thì không có kênh này (không thêm vào `ui_config` để `_merge_new_defaults` không đẩy nó sang máy khác). Hai kênh mic dựng xong phải hiện đúng trạng thái tắt theo `mute_states`.
- Thanh Mic 2: `db_to_midi(...)` như Mic → `engine.send_midi_on_channel(MIC2_CHANNEL, MIDI_CC["mix_mic"], v)`. Nút tắt Mic 2: `send_midi_on_channel(MIC2_CHANNEL, MIDI_CC["mute_mic"], 127|0)` + các entry `mute_multi_cc["mix_mic"]` trên cùng channel 2.
- Khởi tạo `mute_states`: khi bật 2 mic, `mix_mic` và `mix_mic_2` lấy từ `mic_mutes` (thiếu = `False`).
- Khối đồng bộ toàn cục: khi bật 2 mic, gửi thêm mute Mic 2 trên channel 2. (`_sync_mixer_midi` tự gửi mức Mic 2 vì nó có trong `_mixer_senders`.)
- Cài đặt → tab Âm thanh, mục mới "Micro": ô "Phòng có 2 micro (Studio One)" + hai ô tên (chỉ bật khi tick). `_save` ghi 3 khoá; nếu `mic_count` hoặc nhãn đổi → `dashboard._apply_mic_count_setting()`. Ô bị vô hiệu kèm tooltip "Chỉ hỗ trợ Studio One" khi chọn Cubase.

- [ ] **Step 1: Viết test hỏng** (`tests/ui/test_mixer_mic2.py`, dựng dashboard như `tests/ui/test_mixer_unity_daw.py`, `engine` giả)
  - `test_single_mic_unchanged`: settings không có `mic_count` → không có `"mix_mic_2"` trong `_mixer_sliders`; kéo thanh Mic chỉ gọi `send_midi(21, …)`.
  - `test_mic2_strip_sends_channel_2`: bật → kênh `mix_mic_2` nằm ngay sau `mix_mic`, nhãn "Mic Không Dây"; `setValue(0)` → `send_midi_on_channel(1, 21, 76)`; bấm tắt → `send_midi_on_channel(1, 51, 127)`, `mute_states["mix_mic_2"] is True`.
  - `test_mic_mutes_persist_and_resync`: bật, tắt Mic 2 → `settings["mic_mutes"]["mix_mic_2"] is True` và đã gọi `save_settings`; dựng dashboard mới từ settings đó → kênh Mic 2 hiện tắt, `_sync_midi_states()` gửi `send_midi_on_channel(1, 51, 127)`.
  - `test_toggle_mic_count_rebuilds_and_rewires`: đặt `mic_count=2`, gọi `_apply_mic_count_setting()` → có `mix_mic_2` và `engine.refresh_mic2_mirror` đã được gọi; đặt lại 1 → gọi lại → không còn `mix_mic_2`.
  - Trong `test_song_settings_recall.py`: `test_mixer_recall_mic2` — capture có `"mic2"`, apply đặt lại thanh `mix_mic_2`.
- [ ] **Step 2:** Chạy (Windows) `tests/ui/test_mixer_mic2.py tests/ui/test_song_settings_recall.py -k mic2` → FAIL.
- [ ] **Step 3:** Cài đặt.
- [ ] **Step 4:** Chạy lại → PASS; chạy thêm `tests/ui/test_mixer_unity_daw.py tests/ui/test_mixer_music_youtube.py tests/ui/test_midi_resync_on_so_ready.py tests/ui/test_settings_save_and_sync.py tests/ui/test_settings_daw_kind.py tests/ui/test_qt_warnings.py`.
- [ ] **Step 5:** Mở app thật (Windows) với `mic_count=2`, chụp màn hình mixer ở 1366×768 để xem kênh thứ năm có chật không; nếu chật, giảm khoảng cách trong panel (không đổi kích thước kênh khác).
- [ ] **Step 6:** Commit `feat(mic2): kênh Mic 2 trên mixer, cài đặt 2 micro, nhớ trạng thái tắt/mở`.

---

### Task 5: Audio Doctor hiểu hai mic

**Files:**
- Modify: `ui/audio_doctor_bridge.py` (`app_mic_state`, `ensure_app_mic_on`)
- Test: `tests/ui/test_audio_doctor_bridge.py`

**Interfaces:**
- Consumes: `core.mic2.MIC2_KEY`, `core.mic2.is_enabled`
- Produces: `app_mic_state() -> tuple[bool, float] | None` — khi bật 2 mic: `muted` = **mọi** mic đều tắt; `level` = mức cao nhất trong các mic đang mở (hoặc của Mic 1 nếu cả hai tắt). `ensure_app_mic_on()` khi bật 2 mic: mở **cả hai** mic và đưa thanh về 0 dB nếu đang kéo hết (Claude tự quyết: Audio Doctor không biết khách đang cầm mic nào).

- [ ] **Step 1: Viết test hỏng**
  - `test_mic_check_ok_when_one_mic_on`: bật 2 mic, Mic 1 tắt, Mic 2 mở ở 0 dB → `app_mic_state() == (False, 0.0)`.
  - `test_mic_check_all_off`: cả hai tắt → `muted is True`.
  - `test_ensure_mic_on_opens_both`: cả hai tắt → sau `ensure_app_mic_on()` cả hai `is_muted() is False`.
  - Test cũ một mic giữ nguyên.
- [ ] **Step 2:** Chạy (Windows) `tests/ui/test_audio_doctor_bridge.py` → FAIL.
- [ ] **Step 3:** Cài đặt.
- [ ] **Step 4:** Chạy lại cùng `tests/core/audio_doctor` → PASS.
- [ ] **Step 5:** Commit `feat(mic2): Tự sửa âm thanh xét cả hai mic`.

---

### Task 6: Tài liệu bài mẫu + triển khai một máy

**Files:**
- Create: `docs/QUY_TRINH_2_MIC_STUDIO_ONE.md`

Nội dung tài liệu (người làm viết):
- Bảng gán Control Link cho từng control kênh 1 → tham số trên `MIC  P420`, control kênh 2 → tham số tương ứng trên `MIC KG`; ghi rõ ánh xạ send khác tên (KG: Echo = Send02, Hall = Send03, Vang 2 = Send05; P420: Echo = Send06, Hall = Send07, Vang 2 = Send02) và Main = Send04 cả hai.
- Gán **đủ** các control đang thiếu trong `vp.song` (mixMic → fader track, mixReverb, toneVoice, toneAuto, tuneOnOff, fixMeo, tatOn → NS1, voiceFx, các mode) cho cả hai kênh.
- Tắt sẵn track mic không dùng; lưu thành bài mẫu của máy.
- Bước bật "Phòng có 2 micro" trong app, đặt tên hai mic, và danh sách kiểm: đổi bài → Key hai kênh cùng đổi; tắt/mở từng mic; song ca mở cả hai.

- [ ] **Step 1:** Viết tài liệu, commit `docs(mic2): quy trình bài mẫu 2 micro Studio One`.
- [ ] **Step 2 (tay, cùng người dùng):** Phát hành theo `docs/QUY_TRINH_PHAT_HANH.md` / quy trình Velopack đang dùng; trên máy khách: cập nhật surface XML (Audio Doctor sẽ báo bản cũ — chép bản mới), gán Control Link theo tài liệu, chạy danh sách kiểm. Ghi kết quả vào memory máy khách.
