# Luồng hoạt động Dò Tone

Tài liệu mô tả các luồng dò tone, dò lại, các chế độ, và fallback trong app.
Nguồn: `core/engine/_tone.py`, `_youtube.py`, `_autokey.py`, `_session.py`, `frontend_qt.py`.

> **Lưu ý quan trọng về fallback nghe loa:** mọi luồng thu loopback giờ dùng
> chung `ToneDetector._find_loopback_device(pa)` — chọn loopback của **loa mặc
> định đang phát**, không lấy thiết bị đầu tiên trong danh sách. Trước đây lấy
> bừa cái đầu tiên gây ra triệu chứng "không có âm thanh" dù nhạc vẫn phát khi
> máy có nhiều ngõ ra (Speakers / Headset / HDMI).

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

    H -->|url == _last_watched_url| X[Bỏ qua]
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

    RES --> C1{RAM cache phiên?}
    C1 -->|có| OUT_C[Trả cache → replay]
    C1 -->|không| C2{Manual timeline<br/>đã lưu?}
    C2 -->|có| OUT_M[Replay timeline thủ công]
    C2 -->|không| C3{Tone cache<br/>trên đĩa?}
    C3 -->|có| OUT_D[Replay cache]
    C3 -->|không| YT

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
    GWD --> GM{Manual timeline<br/>đã lưu? (nếu !skip_resolve)}
    GM -->|có| GREPLAY[Replay timeline thủ công] --> GDONE
    GM -->|không| GSS[start_scanning → SCANNING]

    GSS --> GINFO[Lấy title video] --> GDL["download_youtube_audio (toàn bài)"]
    GDL --> GDLOK{audio_path?}
    GDLOK -->|có| GSEG["librosa.load sr=22050<br/>detect_timeline_advanced<br/>(nhiều mốc 15s/đoạn)"]
    GDLOK -->|"không<br/>(yt-dlp lỗi)"| GLB["_loopback_fallback_detect<br/>→ CHỈ 1 tone (timeline 1 mốc)"]

    GSEG --> GTL{timeline_entries?}
    GLB --> GTL
    GTL -->|rỗng| GE[on_error: không phát hiện tone]
    GTL -->|có| GSAVE["Lưu ManualToneTimeline<br/>+ ToneCache"] --> GR[transition_to_replaying<br/>_replay_manual_timeline] --> GDONE([on_complete])

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

## 7. Các luồng thu loopback realtime khác (AutoKey)

Hai luồng này thu loopback liên tục, **không** qua yt-dlp; nay cũng dùng
`ToneDetector._find_loopback_device`:

- `start_autokey` (`_autokey.py`) — dò key realtime, bỏ phiếu (voting) qua nhiều
  segment, cập nhật UI khi key đổi.
- `detect_tone_continuous` (`_autokey.py`) — dò liên tục theo `youtube_monitoring_active`,
  build timeline rồi lưu `ToneCache` khi kết thúc.

Cả hai dừng segment nếu `rms < 0.001` (im lặng) → báo "Đang lắng nghe...".
