# Quy trình dựng bài mẫu 2 micro trên Studio One (làm tay, qua UltraViewer)

Áp dụng cho **máy có hai micro** chạy Studio One. Máy một mic giữ bài mẫu của mình, không làm theo tài liệu này.
Thiết kế gốc: `docs/superpowers/specs/2026-11-02-hai-mic-studio-one-design.md` (mục 2, 6.2, 6.5, 7).

Nguyên tắc: **Mic 1 = MIDI channel 1 (`channel="0"`), Mic 2 = MIDI channel 2 (`channel="1"`)**, cùng số CC. Không đụng CC mới.
Trong surface XML mọi control đều là `status="#B0"` và ghi rõ `channel` — Studio One 5 không nhận `#B1`, và control không ghi
`channel` nhận mọi kênh (đã kiểm trên máy khách 2026-11-02, spec mục 7).

| | Mic 1 | Mic 2 |
|---|---|---|
| Track Studio One | `MIC  P420` (hai dấu cách; mic dây, Input L) | `MIC KG` (không dây, Input R) |
| Tên mặc định trong app | Mic Dây | Mic Không Dây |
| Kênh MIDI | 1 (`channel="0"`) | 2 (`channel="1"`) |
| Control trong surface | tên gốc (`keyRoot`...) | hậu tố `2` (`keyRoot2`...) |

Chuỗi insert hai track giống hệt thứ tự: RVox → Aphex Vintage Exciter → C1 → FabFilter Pro-Q 2 (bên KG đổi tên "Pro-Q 4") →
MannyM EQ → CLA-2A → Auto-Tune Pro → "Tat On" (Waves NS1). Track `BEAT` giữ SoundShifter (Tone Nhạc).

## 0. Kiểm trước khi triển khai (chặn, làm trước mọi việc khác)

Hai rủi ro phải loại trừ trên máy khách thật. Nếu một trong hai hỏng thì **dừng và báo lại, KHÔNG gỡ/thêm lại thiết bị** (gỡ có thể làm mất Control Link của các bài đã lưu).

0. **Hỏi người dùng máy có ai đang dùng/đang hát không** trước khi click qua UltraViewer (xem `docs/QUY_TRINH_UV_CUBASE.md`, nguyên tắc 3; `cb.sh quiet 20`).
1. **Sao lưu**: copy cả thư mục `%APPDATA%\PreSonus\Studio One <phiên bản>\User Devices\QuangLuuMIDI\` và file bài của khách (`vp.song`) sang chỗ khác (vd Desktop\SaoLuu_2mic\).
2. **Chép đè** `studio_one\QuangLuuMIDI.surface.xml` mới vào thư mục trên. **Không** Remove/Add device. Khởi động lại Studio One.
3. **Mở bài cũ** (bài một mic đã lưu trước đây) và xác nhận các Control Link cũ vẫn ăn: gửi từ app một lần Key, Mute Mic, mute Vang và thấy track/FX phản ứng.
4. **Kiểm Studio One có nhận control kênh 2**: trong bài mẫu, gán `keyRoot2` → tham số 2 (Key) của Auto-Tune Pro trên `MIC KG`; từ app/công cụ MIDI gửi **CC 33 trên MIDI channel 2**. Chỉ Key của `MIC KG` đổi, `MIC  P420` không đổi.
5. Cả bước 3 và 4 đạt mới đi tiếp. Hỏng bước 4 = Studio One không tách kênh 2 (phương án lùi: bộ CC riêng cho mic 2, quay lại bàn với người thiết kế).
   **Hỏng bước 3** (chép đè làm mất gán cũ): đóng Studio One → chép **trả lại** thư mục `User Devices\QuangLuuMIDI\` và file bài (`vp.song`) từ bản sao lưu ở bước 1 → mở lại Studio One, mở bài cũ, xác nhận các Control Link cũ đã về (gửi lại Key, Mute Mic, mute Vang) → **DỪNG, không làm tiếp, báo lại** người thiết kế.

## 1. Cập nhật app (CHƯA bật 2 micro)

1. Cập nhật app lên bản có tính năng 2 mic (Velopack, theo `docs/QUY_TRINH_PHAT_HANH.md`).
2. **Cài đặt → Âm thanh → "Phòng có 2 micro (Studio One)" phải đang TẮT** (bỏ tích) suốt mục 2. Chỉ bật ở đầu mục 3.

> **Vì sao phải theo thứ tự này:** khi bật 2 micro, mỗi lần app chạm một control dùng chung (Key, MODE...) nó gửi kênh 1 **rồi** kênh 2.
> Ô Control Link của Studio One hiện control **chạm sau cùng** — tức là bản `…2`. Gán Mic 1 lúc đang bật 2 micro thì rất dễ gán nhầm tham số
> `MIC  P420` vào control `…2` (của Mic 2).

## 2. Gán Control Link cho Mic 1 (`MIC  P420`) — "Phòng có 2 micro" TẮT

Trong Studio One: chọn tham số → Control Link / gán cho control của thiết bị `QuangLuuMIDI`. Cột "Đích" của mục **chưa gán** là chỗ KTV điền
tham số thực tế, **theo cách các bài mẫu một mic đang gán**.

**Kiểm mỗi lần gán:** tên control Studio One hiện ở ô Control Link **KHÔNG được kết thúc bằng `2`** (đúng: `keyRoot`, sai: `keyRoot2`). Thấy `…2` là
đang bật 2 micro — huỷ gán đó, tắt ô "Phòng có 2 micro", gán lại. Sau này cần gán thêm cho `MIC  P420` thì cũng tắt ô này trước.

| Control (kênh 1) | CC | Trạng thái | Đích trên `MIC  P420` |
|---|---|---|---|
| keyRoot | 33 | đã gán | Auto-Tune Pro, tham số 2 (Key) |
| keyScale | 34 | đã gán | Auto-Tune Pro, tham số 162 (Scale) |
| scaleType | 35 | đã gán | Auto-Tune Pro, tham số 162 (Scale) |
| be | 47 | đã gán | Auto-Tune Pro, tham số 155 |
| muteMic | 51 | đã gán | Mute của track |
| muteReverb | 52 | đã gán | Mute Send01 (Vang) |
| muteMulti1 | 41 | đã gán | Mute Send06 (Echo) |
| muteMulti2 | 42 | đã gán | Mute Send07 (Hall) |
| muteMulti3 | 43 | đã gán | Mute Send04 (Main) |
| muteMulti4 | 44 | đã gán | Mute Send02 (Vang 2) |
| mixMic | 21 | CHƯA | Fader (volume) của track |
| mixReverb | 22 | CHƯA | ........ (mức Vang) |
| toneVoice | 11 | CHƯA | ........ |
| toneAuto | 40 | CHƯA | ........ (nút Auto-Tune) |
| tuneOnOff | 36 | CHƯA | ........ (bypass Auto-Tune) |
| fixMeo | 45 | CHƯA | ........ |
| tatOn | 48 | CHƯA | Waves NS1 ("Tat On") — bật/tắt |
| voiceFx | 54 | CHƯA | ........ |
| liveTunerMode | 30 | CHƯA | ........ |
| modeDanca | 46 | CHƯA | ........ |
| modeLofi | 37 | CHƯA | ........ |
| modeRemix | 38 | CHƯA | ........ |
| modeDatheloai | 39 | CHƯA | ........ |

Control không theo mic, không gán vào track mic: `toneMusic` (CC 10) → `BEAT` SoundShifter tham số 2 (đã gán); mixMusic, mixBacking, autokey, scoreTrigger... giữ như bài mẫu một mic.

## 3. Bật 2 micro, gán Control Link cho Mic 2 (`MIC KG`)

Bật tính năng trong app trước:

1. **Cài đặt → Âm thanh → "Phòng có 2 micro (Studio One)"**: tích chọn. (Bị khoá/xám khi đang dùng Cubase — chỉ chạy được trên Studio One.)
2. Đặt hai tên hiển thị (mặc định "Mic Dây" / "Mic Không Dây"), lưu.
3. Lần bật đầu tiên **Mic 2 khởi động ở trạng thái tắt (mute)**; trạng thái bật/tắt từng mic được nhớ cho các lần mở sau.
4. Mixer có thêm kênh Mic 2 và kênh Vang Mic 2, Công cụ có thêm nút Bè Mic 2 (phần mở rộng). Bỏ tích thì app tắt Mic 2 trong Studio One rồi mixer về như một mic.

Sau đó gán: **MỌI control kênh 2 trong bảng dưới đều phải gán** vào **tham số tương ứng** của control kênh 1 ở bảng mục 2, nhưng trên track `MIC KG`
— kể cả `mixReverb2` → mức Send01 Vang của `MIC KG`, `muteReverb2`/`muteMulti*_2` → các send của `MIC KG`. Thiếu một dòng là nút đó
trên app không tác động Mic 2.

Khác nhau chỉ ở **giá trị** app gửi: riêng từng mic là `mixMic2`, `muteMic2` (kênh Mic 2 trên mixer) và `mixReverb2`, `muteReverb2`,
`muteMulti1_2`…`muteMulti4_2` (kênh Vang Mic 2 trên mixer — tắt Vang mic này không tắt vang mic kia) và `be2` (nút Bè Mic 2);
mọi control còn lại
app gửi **cùng một giá trị** cho cả hai kênh (phát đôi).

**Kiểm mỗi lần gán:** tên control Studio One hiện ở ô Control Link **PHẢI kết thúc bằng `2`** (`keyRoot2`, `muteMulti1_2`...). Không có `2` là
đang gán nhầm control của Mic 1 — huỷ gán đó, gán lại.

**Send khác tên giữa hai track** — gán theo tên, không theo số:

| Send | `MIC  P420` | `MIC KG` |
|---|---|---|
| Vang | Send01 | Send01 |
| Echo | Send06 | **Send02** |
| Hall | Send07 | **Send03** |
| Main | Send04 | Send04 |
| Vang 2 | Send02 | **Send05** |

| Control (kênh 2, `channel="1"`) | CC | Đích trên `MIC KG` | Ghi chú |
|---|---|---|---|
| keyRoot2 | 33 | Auto-Tune Pro, tham số 2 (Key) | |
| keyScale2 | 34 | Auto-Tune Pro, tham số 162 | giống kênh 1 |
| scaleType2 | 35 | Auto-Tune Pro, tham số 162 | giống kênh 1 |
| be2 | 47 | Auto-Tune Pro, tham số 155 | |
| muteMic2 | 51 | Mute của track `MIC KG` | riêng từng mic |
| mixMic2 | 21 | Fader của track `MIC KG` | riêng từng mic |
| muteReverb2 | 52 | Mute Send01 (Vang) | |
| muteMulti1_2 | 41 | Mute Send02 (Echo) | khác P420 |
| muteMulti2_2 | 42 | Mute Send03 (Hall) | khác P420 |
| muteMulti3_2 | 43 | Mute Send04 (Main) | |
| muteMulti4_2 | 44 | Mute Send05 (Vang 2) | khác P420 |
| mixReverb2 | 22 | ........ (như mixReverb, theo send của KG) | |
| toneVoice2 | 11 | ........ (như toneVoice) | |
| toneAuto2 | 40 | ........ (như toneAuto) | |
| tuneOnOff2 | 36 | ........ (như tuneOnOff) | |
| fixMeo2 | 45 | ........ (như fixMeo) | |
| tatOn2 | 48 | Waves NS1 ("Tat On") của `MIC KG` | |
| voiceFx2 | 54 | ........ (như voiceFx) | |
| liveTunerMode2 | 30 | ........ (như liveTunerMode) | |
| modeDanca2 | 46 | ........ | |
| modeLofi2 | 37 | ........ | |
| modeRemix2 | 38 | ........ | |
| modeDatheloai2 | 39 | ........ | |

Mẹo: cột "Đích" điền xong ở bảng mục 2 thì chép nguyên sang đây, chỉ đổi track (và số send ở các dòng mute send). Mỗi mic có thanh Vang riêng
trên app (Vang, Vang Mic 2); tên kênh Vang Mic 2 tự theo tên mic 2, đổi được bằng Dev Mode → Sửa.

**Thêm/bớt control dùng chung:** danh sách tên control (theo `midi_cc`) mà app phát đôi sang Mic 2 nằm ở key `mic2_shared_cc` trong `app_config.json`
của app; thiếu key thì app dùng mặc định `core/mic2.py` → `DEFAULT_SHARED_NAMES`. Các CC trong `mode_config` và CC phụ `mute_multi_cc` (trừ của Mic)
tự được phát đôi. `mix_mic`, `mute_mic`, `mix_reverb`, `mute_reverb`, CC phụ của Vang và `be` không bao giờ phát đôi (riêng từng mic). Sửa xong phải mở lại app mới áp.

## 4. Tắt sẵn track không dùng, lưu bài mẫu

1. Cả hai track đang record-arm + monitor, không mute → mở bài là hai mic cùng kêu. Đặt trạng thái mặc định: **Mic 2 (`MIC KG`) mute** (khớp với app lần đầu bật), Mic 1 mở. Tắt mic nào không dùng thì mute track đó.
2. File → Save As: lưu thành **bài mẫu của máy** (đặt tên dễ nhận, vd `Mau_2Mic`), dùng bài này làm gốc cho các bài mới. Bài mẫu hai mic chỉ dành cho máy hai mic.
3. Giữ lại bản sao lưu của mục 0.

## 5. Danh sách kiểm cuối

- [ ] Bước 0: chép đè surface XML không làm mất Control Link bài cũ; CC 33 kênh 2 chỉ đổi Key `MIC KG`.
- [ ] Đổi bài → Key (và Scale) của **hai** kênh cùng đổi đúng.
- [ ] Tắt/mở **Mic 1** từ app: chỉ `MIC  P420` mute/mở.
- [ ] Tắt/mở **Mic 2** từ app: chỉ `MIC KG` mute/mở.
- [ ] Song ca: mở cả hai mic, cả hai cùng kêu, kéo thanh mức từng mic chỉ đổi fader của mic đó.
- [ ] Tắt **Vang** (mic 1) từ app: chỉ 5 send (Vang, Echo, Hall, Main, Vang 2) của `MIC  P420` tắt; tắt **Vang Mic 2**: chỉ 5 send của `MIC KG` tắt (nhớ số send khác nhau).
- [ ] Bấm **Bè** (mic 1): chỉ Auto-Tune của `MIC  P420` đổi; bấm **Bè Mic 2**: chỉ Auto-Tune của `MIC KG` đổi.
- [ ] Tắt Ồn, Auto-Tune, Fix Méo, Tone Giọng, Hiệu Ứng Giọng: bấm từ app, thấy **cả hai** track phản ứng.
- [ ] Từng MODE (Dân Ca, Lofi, Remix, Đa Thể Loại) và chế độ Live Tuner (CC 30): bấm từ app, kiểm **cả hai** track phản ứng (MODE nào chỉ ăn một track → thiếu gán `…2` hoặc CC không có trong danh sách phát đôi).
- [ ] Không có tham số `MIC  P420` nào gán vào control `…2`, và mọi gán trên `MIC KG` đều là control `…2`.
- [ ] Mở app lại: trạng thái bật/tắt từng mic được nhớ; tắt "Phòng có 2 micro" thì `MIC KG` bị mute và mixer về như một mic.
- [ ] Mic 2 đang tắt, Mic 1 mở → chạy Audio Doctor "Tự sửa": Mic 2 vẫn tắt.
- [ ] Audio Doctor không báo sai về mic 2 (sau khi chép surface mới).
- [ ] Ghi kết quả vào memory máy khách.
