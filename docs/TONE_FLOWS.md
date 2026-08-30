# Luồng hoạt động Dò Tone

Tài liệu mô tả các luồng dò tone, dò lại, các chế độ, và fallback trong app.
Nguồn: `core/engine/_tone.py`, `_youtube.py`, `_autokey.py`, `_session.py`, `frontend_qt.py`.

> **Lưu ý quan trọng về fallback nghe loa:** mọi luồng thu loopback giờ dùng
> chung `ToneDetector._find_loopback_device(pa)` — chọn loopback của **loa mặc
> định đang phát**, không lấy thiết bị đầu tiên trong danh sách. Trước đây lấy
> bừa cái đầu tiên gây ra triệu chứng "không có âm thanh" dù nhạc vẫn phát khi
> máy có nhiều ngõ ra (Speakers / Headset / HDMI).

> **⚠ Cập nhật (đợt sửa điểm mù tone):** Kết quả dò **TỰ ĐỘNG** giờ CHỈ ghi vào
> `ToneCache` (có TTL 30 ngày, tự dò lại được), **KHÔNG** còn ghi vào
> `ManualToneTimeline`. `ManualToneTimeline` nay chỉ chứa chỉnh sửa **thủ công**
> của người dùng (cờ `source="human"`). Nhờ vậy một lần dò sai không còn "khóa
> cứng" bài hát vĩnh viễn. Ưu tiên resolve: **manual (human) > cache**. Skip-resolve
> chỉ bị chặn khi có timeline thủ công thật (`get_timeline_source(url)=="human"`),
> không chặn vì cache.

> **⚠ Cập nhật 1.7.5 — "tone đã lưu không bị dò đè":** vá 4 chỗ khiến tone khách
> lưu vẫn bị dò lại:
> 1. **Tone của bài vào được chuỗi resolve.** `saved_songs.json → tone` (ô Tone lúc
>    "Lưu bài hát" / "Sửa thông tin") trước chỉ để HIỂN THỊ; nay là một mắt xích
>    thật (`core/tone_cache.py::song_tone_entry`), đứng **sau** `ToneCache` và
>    **trước** thư viện cộng đồng. Khách đổi tone ở 2 form đó còn được ghi luôn
>    thành chuỗi tone thủ công 1 mốc (`MainDashboard._save_single_tone_timeline`).
> 2. **Đệm resolve trong phiên tự hết hạn.** `core.tone_cache.data_version()` tăng
>    mỗi lần dữ liệu tone trên đĩa đổi; `_resolve_tone` so số này rồi bỏ đệm —
>    trước đây sửa chuỗi tone tay giữa phiên xong mở lại bài vẫn ra tone TỰ ĐỘNG
>    cũ còn nằm trong RAM. Đệm cũng khóa theo `song_match_key` (video_id) thay vì
>    chuỗi URL thô.
> 3. **Mọi đường mở bài dùng chung một nguồn.** Dán link / ô tìm kiếm
>    (`play_youtube_in_app`) trước đây xoá timeline rồi để engine dò lại; nay tra
>    `saved_tone_timeline(url)` và truyền `manual_timeline` như đường "Bài đã lưu".
> 4. **Chế độ FULL dùng chung chuỗi resolve** (trước chỉ xét timeline thủ công nên
>    có cache vẫn tải + phân tích lại cả bài), và **watcher so URL theo bài**
>    (`_same_song`, theo video_id) thay vì so chuỗi — link chia sẻ `youtu.be/…?si=`
>    không còn bị coi là "bài mới" để hủy replay.
> 5. **Đường mở bài tự chịu trách nhiệm gọi dò** (`_ensure_tone_for_url`). Trước
>    đây bài CHƯA có tone được dò *nhờ may*: app mở link chia sẻ, trình duyệt hiện
>    link chuẩn, watcher so chuỗi thấy khác nên tưởng "URL mới" rồi dò. Sửa (4)
>    làm cú dò tình cờ đó biến mất, nên `open_youtube_url` gọi thẳng — và bỏ qua
>    nếu phiên dò/replay của CHÍNH bài đó đang chạy.

---

## 1. State machine của `ToneSession`

```mermaid
stateDiagram-v2
    [*] --> IDLE
    IDLE --> SCANNING: start_scanning(url)
    SCANNING --> REPLAYING: transition_to_replaying()<br/>(dò xong, có kết quả)
    SCANNING --> IDLE: stop() / on_error<br/>(dò thất bại)
    REPLAYING --> IDLE: stop()<br/>(URL mới / đóng app / Dò Lại)
    SCANNING --> SCANNING: start_scanning(url mới)<br/>(reset cancel event)

    note right of SCANNING
        cancel_event mới được tạo.
        transition_to_replaying() chỉ
        thành công khi đang ở SCANNING,
        ngược lại trả None → không replay.
    end note
```

---

## 1b. Tự động thử lại 3 lần + báo nguyên nhân (`_dispatch_auto_detect`)

Áp dụng cho **cả 2 chế độ** (fast & full). Khi 1 lần dò lỗi → tự động dò lại tối
đa `_AUTO_DETECT_MAX_ATTEMPTS = 3` lần, cách nhau `_AUTO_DETECT_RETRY_DELAY_SEC = 3`s.
Hết lượt mới hiển thị lỗi kèm **nguyên nhân cụ thể**.

```mermaid
flowchart TD
    D0([_dispatch_auto_detect<br/>attempt=1]) --> RUN["Chạy fast/full scan"]
    RUN --> OK{Thành công?}
    OK -->|có| DONE([on_auto_tone_complete])
    OK -->|lỗi msg| STOP[_tone_session.stop]
    STOP --> CNT{attempt < 3?}
    CNT -->|có| WAIT["progress: 'đang thử lại lần X/3'<br/>chờ 3s"]
    WAIT --> GUARD{Có phiên dò khác<br/>đang chạy?}
    GUARD -->|có| ABORT[Hủy thử lại]
    GUARD -->|không| RETRY["_dispatch_auto_detect<br/>attempt+1, skip_resolve=True"]
    RETRY --> RUN
    CNT -->|"không (đã 3 lần)"| ERR["on_auto_tone_error:<br/>'Thất bại sau 3 lần.<br/>Nguyên nhân: …'"]
```

Nguyên nhân (`msg`) lấy từ tầng dò: yt-dlp lỗi + loa im lặng / không tìm thấy loopback /
mở luồng thất bại / nghe được nhưng không ra tone… (xem mục 3).

---

## 2. Toàn cảnh các điểm vào (entry points)

```mermaid
flowchart TD
    A1["YouTube Watcher<br/>(_youtube_watcher_loop)"] -->|URL mới| H{_handle_new_url}
    A2["Nút 'Dò Lại'<br/>(_on_force_rescan)"] --> R[_tone_session.stop<br/>skip_resolve=True]
    A3["open_youtube_url<br/>(có manual_timeline)"] -->|replay trực tiếp| RP[[_replay_manual_timeline]]
    A4["Mở bài: Danh sách bài hát /<br/>dán link / tìm kiếm / Setlist"] --> TL["_saved_manual_timeline(url)<br/>= saved_tone_timeline()"]
    TL -->|"có chuỗi tone đã lưu"| A3
    TL -->|không có| EN["_ensure_tone_for_url<br/>(bỏ qua nếu đang dò/replay chính bài đó)"]
    EN --> D

    H -->|"_same_song(url, _last_watched_url)"| X[Bỏ qua]
    H -->|IDLE| D[_dispatch_auto_detect]
    H -->|SCANNING| Q[Đưa vào _pending_url_queue]
    H -->|REPLAYING| S2[stop → _dispatch_auto_detect]

    R -->|có current_youtube_url| D
    R -->|không có URL| FB[detect_tone_from_browser<br/>quét trình duyệt]

    D --> M{tone_scan_mode?}
    M -->|fast| FAST[[detect_tone_from_browser]]
    M -->|full| FULL[[auto_detect_youtube_timeline]]
    Q -.->|khi session IDLE| D
```

---

## 3. Chuỗi resolve + fallback (dùng chung cho cả 2 chế độ)

```mermaid
flowchart TD
    START([Bắt đầu dò 1 URL]) --> SK{skip_resolve?}
    SK -->|true<br/>Dò Lại / force| YT
    SK -->|false| RES["_resolve_tone(url)"]

    RES --> C0{"Đệm phiên còn hạn?<br/>(data_version chưa đổi)"}
    C0 -->|"dữ liệu đã đổi"| CLR[Bỏ sạch đệm phiên] --> C2
    C0 -->|còn hạn| C1{RAM cache phiên?<br/>khóa = video_id}
    C1 -->|có| OUT_C[Trả cache → replay]
    C1 -->|không| C2{Manual timeline<br/>đã lưu?}
    C2 -->|có| OUT_M[Replay timeline thủ công]
    C2 -->|không| C3{Tone cache<br/>trên đĩa?}
    C3 -->|có| OUT_D[Replay cache]
    C3 -->|không| C4{"Tone của bài trong<br/>Danh sách bài hát?"}
    C4 -->|có| OUT_S[Replay tone đã lưu<br/>timeline 1 mốc]
    C4 -->|không| C5{Thư viện tone<br/>cộng đồng?}
    C5 -->|có| OUT_D
    C5 -->|không| YT

    YT["Tải audio qua yt-dlp"] --> YTOK{Tải được?}
    YTOK -->|có| ANALYZE[Phân tích key bằng librosa]
    YTOK -->|"thất bại<br/>(chặn vùng / login / lỗi)"| LB

    LB["FALLBACK: nghe loa<br/>detect_key_from_system_audio<br/>chọn loopback loa MẶC ĐỊNH<br/>(reason_out ghi nguyên nhân)"] --> LBOK{RMS ≥ 0.001<br/>(có âm thanh)?}
    LBOK -->|có| ANALYZE
    LBOK -->|"không<br/>(im lặng / no device / lỗi)"| ERR["reason cụ thể<br/>→ đưa lên _dispatch_auto_detect<br/>(thử lại / báo lỗi rõ)"]

    ANALYZE --> SAVE[Lưu cache + gửi MIDI] --> REPLAY[transition_to_replaying]
    ERR --> STOP[_tone_session.stop → IDLE]
```

---

## 4. Chế độ NHANH — `detect_tone_from_browser`

```mermaid
flowchart TD
    F0([detect_tone_from_browser]) --> WD["Lắp watchdog 90s<br/>(timeout → stop session + on_error)"]
    WD --> URL{Có URL chưa?}
    URL -->|chưa| SCAN[detect_youtube_url_from_browser]
    URL -->|có| SS
    SCAN -->|không thấy| E1[on_error: không thấy YouTube]
    SCAN --> SS[start_scanning → SCANNING]

    SS --> RESOLVE{skip_resolve?}
    RESOLVE -->|"manual/cache hit"| REPL1[transition_to_replaying<br/>+ replay] --> DONE
    RESOLVE -->|miss / skip| DL["Tải 45s audio (yt-dlp)"]

    DL --> DLOK{audio_path?}
    DLOK -->|có| LOAD["librosa.load sr=16000<br/>detect_key_from_audio"]
    DLOK -->|không| LBF["_loopback_fallback_detect<br/>(nghe loa 12s)"]

    LOAD --> RESULT{result?}
    LBF --> RESULT
    RESULT -->|có| FIN["update camelot/timeline<br/>gửi MIDI + lưu cache<br/>transition_to_replaying"] --> DONE([on_complete])
    RESULT -->|không| E2["on_error:<br/>'đảm bảo bài hát đang phát'"]
```

---

## 5. Chế độ FULL — `auto_detect_youtube_timeline`

```mermaid
flowchart TD
    G0([auto_detect_youtube_timeline]) --> GWD[Lắp watchdog 300s]
    GWD --> GM{"_resolve_tone(url)<br/>(nếu !skip_resolve)"}
    GM -->|manual| GREPLAY[Replay timeline thủ công] --> GDONE
    GM -->|cache| GREPLAY2["_build_cache_result + replay cache"] --> GDONE
    GM -->|không có gì| GSS[start_scanning → SCANNING]

    GSS --> GINFO[Lấy title video] --> GDL["download_youtube_audio (toàn bài)"]
    GDL --> GDLOK{audio_path?}
    GDLOK -->|có| GSEG["librosa.load sr=22050<br/>detect_timeline_advanced<br/>(nhiều mốc 15s/đoạn)"]
    GDLOK -->|"không<br/>(yt-dlp lỗi)"| GLB["_loopback_fallback_detect<br/>→ CHỈ 1 tone (timeline 1 mốc)"]

    GSEG --> GTL{timeline_entries?}
    GLB --> GTL
    GTL -->|rỗng| GE[on_error: không phát hiện tone]
    GTL -->|có| GSAVE["Lưu ToneCache (primary_key theo<br/>thời lượng, KHÔNG ghi ManualToneTimeline)"] --> GR[transition_to_replaying<br/>_replay_cached_timeline] --> GDONE([on_complete])

    GDONE --> GPEND{Có pending URL?}
    GPEND -->|có| GNEXT[_dispatch_auto_detect URL kế]
```

---

## 6. Replay đồng bộ theo vị trí phát (cache & manual)

```mermaid
flowchart TD
    RP0([_replay_*_timeline loop]) --> PLAY{is_playing?<br/>CDP hoặc WinRT}
    PLAY -->|không| WAIT[chờ 0.1s] --> PLAY
    PLAY -->|có| POS[Lấy current_position]
    POS --> SEEK{tua lùi > 2s?}
    SEEK -->|có| RESET[reset last_idx] --> ENTRY
    SEEK -->|không| ENTRY[get_entry_at_position]
    ENTRY --> CH{Đổi mốc & đổi key?}
    CH -->|có| MIDI[gửi MIDI + callback UI]
    CH -->|không| WAIT2[chờ 0.1s] --> PLAY
    MIDI --> WAIT2
    RP0 -.->|cancel_event.set| END([Kết thúc replay])
```

---

## 7. Các luồng thu loopback realtime (AutoKey & Continuous)

Hai luồng này thu loopback liên tục, **không** qua yt-dlp; nay cũng dùng
`ToneDetector._find_loopback_device`:

- `start_autokey` (`_autokey.py`) — dò key realtime, bỏ phiếu (voting) qua nhiều
  segment, cập nhật UI khi key đổi.
- `detect_tone_continuous` (`_autokey.py`) — dò liên tục theo `youtube_monitoring_active`,
  build timeline rồi lưu `ToneCache` khi kết thúc.

Cả hai dừng segment nếu `rms < 0.001` (im lặng) → báo "Đang lắng nghe...".

### 7a. Vòng bỏ phiếu (voting) — `VOTING_WINDOW = 3`

```mermaid
flowchart TD
    SEG([Mỗi segment ~5s loopback]) --> DET["result = detect_key_from_audio(buffer)"]
    DET --> STORE["results_by_key[new_key] = result<br/>(nhớ result ĐẦY ĐỦ theo key_display)"]
    STORE --> WIN["recent_keys.append(new_key)<br/>giữ tối đa VOTING_WINDOW<br/>tỉa results_by_key theo cửa sổ"]
    WIN --> VOTE["voted_key = most_common(recent_keys)<br/>voted_result = results_by_key[voted_key]<br/>voted_conf  = voted_result.confidence"]
    VOTE --> DEC{Có đổi tone?}
    DEC -->|"current=None"| COMMIT
    DEC -->|"voted≠current AND<br/>vote_ratio≥0.67 AND<br/>Δconf > −0.05"| COMMIT["current_key/confidence/result = voted_*"]
    DEC -->|không| UI
    COMMIT --> MIDI["_send_tone_midi(voted_result)"]
    MIDI --> UI["AutoKey: callback UI = current_result<br/>Continuous: entry timeline = voted_result → ToneCache"]
```

### 7b. ⭐ Bất biến nhất quán (consistency invariant)

> Trong mọi luồng, **key hiển thị = key gửi MIDI = key lưu cache** đều phải là
> CÙNG một key. Cụ thể `key_display`, `key_index`, `scale` luôn lấy từ **cùng một
> `result` dict**.

Cạm bẫy đã sửa: voting làm mượt `key_display` (chọn `voted_key`), nhưng MIDI/cache
lại lấy `key_index`/`scale` từ `result` của **frame mới nhất**. Khi frame mới nhất
khác key được bầu (đúng lúc voting phát huy tác dụng) → gửi sai tone sang Studio One.

```text
recent_keys = ['C','C','Am']   (frame mới nhất = 'Am', voted = 'C')

TRƯỚC:  hiển thị 'C'  ──  _send_tone_midi(result='Am')        ✗ LỆCH
SAU:    hiển thị 'C'  ──  _send_tone_midi(voted_result='C')   ✓ KHỚP
```

Cách sửa: giữ map `results_by_key: key_display → result`, rồi tra
`voted_result = results_by_key[voted_key]` để dùng cho cả MIDI, UI callback và
entry timeline. Áp dụng tại 3 chỗ:

| Vị trí | Trước | Sau |
|--------|-------|-----|
| `start_autokey` (voting) | MIDI/UI theo frame mới nhất | theo `current_result` (khớp `voted_key`) |
| `detect_tone_continuous` | entry/MIDI/callback theo frame mới nhất | theo `voted_result` |
| `_build_cache_result` (`_tone.py`) | hiển thị `primary_key` nhưng index/scale theo `timeline[-1]` | tìm entry **khớp `primary_key`** |

> Dữ liệu cache cũ lưu trước khi sửa có thể vẫn lệch — sẽ tự đúng lại khi dò tone mới.

---

## 8. Lõi nhận diện 1 đoạn — `ToneDetector.detect_key_from_audio`

Dùng chung cho TẤT CẢ các luồng ở trên (single-shot, timeline, voting).

```mermaid
flowchart TD
    A([audio_data]) --> P0["BƯỚC 0 — Tiền xử lý robust<br/>clip outlier → silence gate (RMS<0.001 → None)<br/>normalize percentile 99.9 → bỏ DC offset<br/>(tùy chọn) khử hum: PYIN 50–80Hz → notch filter"]
    P0 --> P1["BƯỚC 1 — Chroma CQT (energy-weighted theo RMS)<br/>→ vector 12 chiều<br/>(AutoKey: trộn EMA α=0.3 với chroma tích lũy)"]
    P1 --> P3["BƯỚC 3 — Tương quan ĐA PROFILE<br/>Aarden 50% + Temperley 30% + KS 20%<br/>→ 24 key (12 major + 12 minor)"]
    P3 --> P4["BƯỚC 4 — Phân giải họ key (disambiguation)<br/>gom top-7 key gần nhau (≥6/7 nốt chung)<br/>chấm = corr·0.85 + (tonic+5th·0.7+3rd·0.5)·0.15<br/>tiebreak theo độ phổ biến nếu chênh <2%"]
    P4 --> OUT["result = { key (nốt gốc), key_display ('Am'),<br/>key_index 0–11, scale, confidence }"]
```

> `key` = **nốt gốc** dùng cho `KEY_MIDI_MAP` (CC#33); `key_display` = tên đầy đủ
> cho UI ('Am'). `detect_timeline_advanced` (chế độ FULL) tái dùng BƯỚC 3–4 trên
> từng đoạn, thêm: novelty curve → find_peaks → refine ±3s → merge → lọc đoạn <8s.
