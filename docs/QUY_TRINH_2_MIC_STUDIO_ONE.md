# Quy trình dựng bài mẫu 2 micro trên Studio One (làm tay, qua UltraViewer)

Áp dụng cho **máy có hai micro** chạy Studio One. Máy một mic giữ bài mẫu của mình, không làm theo tài liệu này.
Thiết kế gốc: `docs/superpowers/specs/2026-11-02-hai-mic-studio-one-design.md` (mục 2, 6.2, 6.5, 7).

Nguyên tắc: **Mic 1 = MIDI channel 1 (status `#B0`), Mic 2 = MIDI channel 2 (status `#B1`)**, cùng số CC. Không đụng CC mới.

| | Mic 1 | Mic 2 |
|---|---|---|
| Track Studio One | `MIC  P420` (hai dấu cách; mic dây, Input L) | `MIC KG` (không dây, Input R) |
| Tên mặc định trong app | Mic Dây | Mic Không Dây |
| Kênh MIDI | 1 (`#B0`) | 2 (`#B1`) |
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
5. Cả bước 3 và 4 đạt mới đi tiếp. Hỏng bước 3 = chép đè làm mất gán cũ; hỏng bước 4 = Studio One không nhận `#B1` (phương án lùi: bộ CC riêng cho mic 2, quay lại bàn với người thiết kế).

## 1. Bật tính năng trong app

1. Cập nhật app lên bản có tính năng 2 mic (Velopack, theo `docs/QUY_TRINH_PHAT_HANH.md`).
2. **Cài đặt → Âm thanh → "Phòng có 2 micro (Studio One)"**: tích chọn. (Bị khoá/xám khi đang dùng Cubase — chỉ chạy được trên Studio One.)
3. Đặt hai tên hiển thị (mặc định "Mic Dây" / "Mic Không Dây"), lưu.
4. Lần bật đầu tiên **Mic 2 khởi động ở trạng thái tắt (mute)**; trạng thái bật/tắt từng mic được nhớ cho các lần mở sau.
5. Mixer có thêm kênh Mic 2 (phần mở rộng). Bỏ tích thì mixer về như một mic.

## 2. Gán Control Link cho Mic 1 (`MIC  P420`)

Trong Studio One: chọn tham số → Control Link / gán cho control của thiết bị `QuangLuuMIDI`. Cột "Đích" của mục **chưa gán** là chỗ KTV điền
tham số thực tế, **theo cách các bài mẫu một mic đang gán**.

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

## 3. Gán Control Link cho Mic 2 (`MIC KG`)

Mỗi control kênh 2 gán vào **tham số tương ứng** của control kênh 1 ở bảng trên, nhưng trên track `MIC KG`. Hai riêng từng mic: `mixMic2`, `muteMic2`;
còn lại app tự phát đôi (cùng giá trị sang kênh 2) nên chỉ cần gán đúng đích.

**Send khác tên giữa hai track** — gán theo tên, không theo số:

| Send | `MIC  P420` | `MIC KG` |
|---|---|---|
| Vang | Send01 | Send01 |
| Echo | Send06 | **Send02** |
| Hall | Send07 | **Send03** |
| Main | Send04 | Send04 |
| Vang 2 | Send02 | **Send05** |

| Control (kênh 2, status `#B1`) | CC | Đích trên `MIC KG` | Ghi chú |
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

Mẹo: cột "Đích" điền xong ở bảng mục 2 thì chép nguyên sang đây, chỉ đổi track (và số send ở các dòng mute send). Thanh Vang chung cho cả hai mic (app phát đôi).

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
- [ ] Mute Vang, Echo, Hall, Main, Vang 2: đúng send trên **cả hai** track (nhớ số send khác nhau).
- [ ] Tắt Ồn, Auto-Tune, Fix Méo, Tone Giọng, Hiệu Ứng Giọng, các MODE: tác động cả hai mic.
- [ ] Mở app lại: trạng thái bật/tắt từng mic được nhớ; tắt "Phòng có 2 micro" thì mixer về như một mic.
- [ ] Audio Doctor không báo sai về mic 2 (sau khi chép surface mới).
- [ ] Ghi kết quả vào memory máy khách.
