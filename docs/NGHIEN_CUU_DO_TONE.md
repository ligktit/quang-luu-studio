# Nghiên cứu: cải thiện độ chính xác & độ tin cậy dò tone

Ngày: 2026-09-27. Phạm vi: lõi `core/tone_detector.py` (dò 1 lần + chuỗi tone
`detect_timeline_advanced`). Chưa sửa code — tài liệu này là căn cứ để quyết định.

Ký hiệu: **[TL]** = có tài liệu/nguồn; **[ĐO]** = tự đo trong repo (âm thanh
tổng hợp); **[ĐOÁN]** = suy luận, chưa kiểm chứng.

---

## 1. Hiện trạng đo được **[ĐO]**

Bộ thử: 6 vòng hợp âm × 12 tone, có/không trống + nhiễu, lệch tuning.

| Tình huống | Đúng |
|---|---|
| Sạch / có trống+nhiễu / AutoKey không HPSS | gần 100% trừ các ca bên dưới |
| Vòng Andalusian giọng thứ (Am–G–F–E) | 2–4/6 — nhầm sang trưởng song song |
| Am–F–C–G | luôn ra C trưởng (vòng này **trùng nốt** với C vi–IV–I–V — không thuật toán trung bình chroma nào tách được) |
| Lệch tuning +20 cent | **24/36** → sau khi sửa ước lượng tuning: **32/36** |
| Chuỗi tone: nâng ½ cung / 1 cung đoạn cuối | cách hiện tại bắt đúng cả hai, không báo đổi tone giả |

Hai lỗi cấu trúc:

1. **Ước lượng tuning bị gấp vòng.** `chroma_cqt(tuning=None)` gọi
   `estimate_tuning(bins_per_octave=36)` → chỉ đúng trong ±16,7 cent (+20 cent đọc
   thành −11 cent). Cùng lỗi ở `_estimate_tuning_bounded` (dòng 939). Sửa: ước
   lượng ở 12 bin/quãng tám (±50 cent) rồi truyền `tuning*3` vào `chroma_cqt`.
   (Xác nhận trong mã nguồn librosa 0.11 **[TL]**.)
2. **`confidence` là hệ số tương quan thô**, luôn 0,68–0,86 kể cả khi sai → cờ
   `uncertain` (< 0,30) không bao giờ bật. Khoảng cách hạng 1 − hạng 2 mới phân
   biệt được: đúng ≈ 0,15, sai ≈ 0,01–0,04.

---

## 2. Các "ông lớn" làm thế nào

### Antares Auto-Key 2 — quan trọng nhất vì đầu ra của ta đi vào Auto-Tune **[TL]**
- Lõi dò key/scale **mua bản quyền từ zplane TONART v3** (tempo: zplane AUFTAKT).
  Nguồn: Auto-Key 2 User Guide (PDF của Antares).
- Chỉ 24 key + Chromatic; cần ≥ 5 s; khuyên đặt trên bus tổng, không đặt trên vocal.
- **Dò cả tần số chuẩn A4** để đưa sang tham số Detune của Auto-Tune.
- **Không tự giải được nhầm trưởng/thứ song song**: tài liệu thừa nhận có thể ra
  "C major thay vì A minor" và cho nút **Relative Key Swap** để người dùng đảo.
- **Không có chuỗi tone tự động** — đổi tone giữa bài phải tự vẽ automation.

### zplane TONART v3 (SDK C++ thương mại) **[TL]**
- Hai chế độ thể loại `electronic` / `general`; trả về key tốt nhất **kèm xác suất**,
  xác suất **cho cả 24 key**, và tần số tuning.
- Giả định tín hiệu **chỉ có một key** — không phải công cụ dò chuỗi tone.
- Khách hàng: Mixed In Key, djay, FL Studio, Beatport, Microsoft… Có bản dùng thử 3 tuần.
  https://licensing.zplane.de/technology

### Mixed In Key **[TL]**
- Khởi đầu là giao diện cho zplane tONaRT; từ 2007 kết hợp thêm thuật toán riêng.
- Bằng sáng chế US7842878: so profile cường độ nốt với cơ sở dữ liệu cụm audio
  tham chiếu, giữ điểm tương quan của mọi key, phân tích theo đoạn độ dài thay đổi.
- Không công bố phương pháp cho bản 10/11.

### Khác **[TL]**
- **Melodyne 5**: dò hợp âm + **đổi tone trên Key Track**, cho người dùng chọn
  cách hiểu thay thế — gần nhất với tính năng chuỗi tone của ta.
- **Logic Pro**: suy ra key từ **hợp âm**, không từ audio thô.
- **Spotify/Echo Nest**: trả `key_confidence` và `mode_confidence` **tách riêng**,
  và có key + độ tin cậy **theo từng section**. Nhầm phổ biến nhất: trưởng ↔ thứ song song.
- **KeyFinder** (luận văn Sha'ath 2011): lựa chọn profile + phép đo tương đồng
  quan trọng nhất; cosine thắng Pearson (nhạc dance); giới hạn C1–B6 là tốt nhất;
  **chia đoạn không giúp gì cho key tổng thể**.

### Độ chính xác thực tế **[TL]**
| Nguồn | Kết quả |
|---|---|
| ISMIR 2015, GiantSteps (604 bài EDM) | Rekordbox 71,9% đúng; Mixed In Key 7: 67,2%; KeyFinder 45,4%; Essentia 30,5% |
| DJ TechTools 2015 (66 bài) | MIK 86%, Serato 70%, Rekordbox 70%, Traktor 47% |
| CNN học thuật tốt nhất (Korzeniowski 2018, S-KEY 2025, KeyMyna 2026) | ~72–76 điểm MIREX trên EDM, ~85 trên pop |
| Profile Krumhansl trên CQT, 5.489 bài pop (FMAKv2) | **53,4** điểm MIREX, đúng mode chỉ 64,9% |

→ Trần thực tế ~70–85% đúng tuyệt đối. Con người đồng thuận ~75% (theo MIK).
Mọi bộ thử là EDM/pop phương Tây — **không có bolero/ballad Việt**.

---

## 3. Học thuật & mã nguồn mở

- **Mô hình học sâu dùng được thương mại: Deezer S-KEY** (ICASSP 2025), repo **MIT**,
  trọng số 765 KB có sẵn. Ngang madmom (73,2 vs 73,1 trên FMAKv2), đúng mode
  **79%** so với 64,9% của Krumhansl. https://github.com/deezer/skey
  **[ĐOÁN]** Xuất ChromaNet sang ONNX, tự tính CQT bằng librosa → không cần torch
  trong bản build; cần kiểm tra CQT librosa khớp nnAudio. Thời gian < 1 s/30 s (chưa đo).
- **Tránh** (giấy phép): madmom model (CC BY-NC-SA), Essentia (AGPL, model NC,
  không có wheel Windows), key-cnn (AGPL), libKeyFinder (GPLv3), Chordino/NNLS (GPL).
- **Cải tiến rẻ, thuần numpy** **[TL]**: nén log `log(1+γ·chroma)`; học profile từ
  dữ liệu thay vì trộn tay 50/30/20; dùng khoảng cách Euclid (Albrecht & Shanahan
  2013, tốt hơn cho giọng thứ); **đoạn kết/hợp âm cuối và nốt bass** mang nhiều
  thông tin về chủ âm nhất.
- **Chuỗi tone**: HMM 24 trạng thái + Viterbi, xác suất tự chuyển 1−ε
  (Weiss/Schreiber/Müller ICASSP 2020: HMM 71% vs CNN 73%). Korzeniowski: đoạn
  ngắn dò sai nhiều hơn hẳn → cần ngữ cảnh cả bài.
- **Hiệu chỉnh độ tin cậy**: softmax(điểm / T), T học trên tập có nhãn (Guo 2017).
- **Chấm điểm**: `mir_eval.key.weighted_score` (MIT): đúng 1, quãng 5 0,5,
  song song 0,3, cùng chủ âm 0,2.

**[ĐO]** Thử HMM đơn giản trên bài tổng hợp: **kém hơn** cách hiện tại — nhảy
Am↔C qua lại trong bài bolero, và posterior luôn ≈ 1,0 (quá tự tin vì các frame
không độc lập). HMM chỉ đáng làm khi có (a) phạt riêng bước nhảy giữa hai tone
song song, (b) hiệu chỉnh xác suất.

---

## 4. Nhận định quan trọng cho app này

**Nhầm trưởng ↔ thứ song song gần như vô hại với Auto-Tune.** C trưởng và La thứ
(tự nhiên) có **cùng 7 nốt** → Auto-Tune kéo giọng về cùng tập nốt. Lỗi thật sự
làm hát lệch là:
- **nhầm quãng 5** (lệch 1 nốt),
- **nhầm cùng chủ âm trưởng/thứ** (lệch 3 nốt),
- **lệch tuning** (Auto-Tune kéo về A=440 trong khi bài thu ở A=430 → giọng lệch nền nhạc).

→ Nên ưu tiên sửa theo tác hại âm thanh, không theo điểm MIREX. Nhầm song song
chủ yếu hại **tên tone hiển thị** — giải bằng nút đảo như Auto-Key.

**[ĐOÁN]** Scale "Minor" của Auto-Tune là thứ tự nhiên → bài dùng bậc 7 nâng
(G# trong Am, rất phổ biến ở bolero) sẽ bị kéo G# về G. Cần kiểm tra trên plugin;
nếu đúng, cân nhắc gửi scale thứ hoà âm nếu plugin hỗ trợ qua MIDI.

---

## 5. Lộ trình đề xuất

### Giai đoạn 0 — Thước đo (làm trước mọi thứ)
- Tập đáp án từ **Thư viện tone dùng chung**: các biến thể `source="human"` /
  `pinned` trong bảng `shared_tones` trên server = bài hát Việt thật đã có người sửa tay.
- Công cụ chấm `tools/`: tải audio → chạy thuật toán → báo 3 con số:
  (1) đúng tuyệt đối, (2) điểm MIREX, (3) **"đúng tập nốt Auto-Tune"** (tính
  trưởng/thứ song song là đúng). Kèm biểu đồ độ tin cậy.
- Dữ liệu công khai bổ sung: FMAK (5.489 bài, audio CC) https://zenodo.org/records/12759100,
  GTZAN key.

### Giai đoạn 1 — Rẻ, an toàn, thuần numpy
1. Sửa ước lượng tuning (2 chỗ). Xuất thêm **tần số chuẩn A4** trong kết quả.
2. Trả về **vector điểm 24 key**; `confidence` mới = softmax có nhiệt độ + khoảng
   cách hạng 1–2; tách **độ tin cậy key** và **độ tin cậy mode** (như Spotify).
3. Nút **đảo trưởng/thứ song song** một chạm trên UI khi hạng 2 là tone song song
   và khoảng cách nhỏ (như Auto-Key).
4. Nén log chroma; thử cosine thay Pearson — **chỉ giữ nếu thước đo GĐ0 tốt lên**.

### Giai đoạn 2 — Tận dụng đặc thù nhạc Việt
5. Đặc trưng thêm: chroma dải bass (~30–130 Hz), chroma 10–15 s cuối / hợp âm kết.
6. Học profile (hồi quy logistic 24 lớp, vài KB trọng số) trên 100–300 bài đã gán nhãn.

### Giai đoạn 3 — Mô hình học sâu
7. Đánh giá **S-KEY (MIT) qua ONNX** như bộ phân loại chính hoặc một phiếu bầu
   cạnh profile; so bằng thước đo GĐ0 trước khi đưa vào bản build.

### Chuỗi tone
- Giữ cơ chế cắt đoạn hiện tại (đo tốt trên bài tổng hợp).
- Tính **key tổng thể cả bài trước**; một đoạn chỉ được báo đổi tone khi độ tin
  cậy của nó **vượt rõ** key tổng thể (mô hình của Spotify section).
- Ưu tiên bước đổi +1/+2 cung cùng mode (kiểu nâng tone điệp khúc cuối); phạt
  bước đổi sang tone song song giữa bài.
- HMM/Viterbi: để sau, chỉ làm khi có hiệu chỉnh + phạt song song (xem mục 3).

### Lựa chọn kinh doanh
- **Mua bản quyền zplane TONART** — chính lõi trong Auto-Key 2 → kết quả khớp
  những gì người dùng Antares thấy, có sẵn xác suất 24 key + tuning. Cần hỏi giá;
  vẫn không giải chuỗi tone. Có bản thử 3 tuần để so trên tập GĐ0.

---

## Trạng thái thực hiện

### 2026-09-27 — GĐ0 + sửa tuning (chưa commit)

**Sửa tuning** — `core/tone_detector.py`:
- `_estimate_tuning_cents()` ước lượng ở 12 bin/quãng 8 (±50 cent);
  `_cents_to_chroma_bins()` đổi sang tham số `tuning` của `chroma_cqt` 36 bin.
- Dò 1 lần (`detect_key_from_audio`) truyền tuning tường minh; dò toàn bài
  (`_estimate_tuning_bounded`) dùng cùng hàm.
- Kết quả dò có thêm trường `tuning_cents` (độ lệch so với A=440; chưa điều khiển gì).
- Chi phí: ~0,07 s — code cũ cũng ước lượng tuning bên trong librosa nên gần như không đổi.

Đo bằng `tools/danh_gia_do_tone.py tong-hop --nhanh` (120 ca, sr=16000):

| | Trước | Sau |
|---|---|---|
| Đúng tuyệt đối | 85,0% | **96,7%** |
| Điểm MIREX | 89,2 | **97,7** |
| Đúng tập nốt (Auto-Tune) | 85,0% | **100%** |
| Lệch +20 cent / +40 cent | 66,7% / 66,7% | 95,8% / 95,8% |

4 lỗi còn lại đều là nhầm giọng song song ở vòng Andalusian — vô hại với
Auto-Tune, là việc của GĐ1–2.

**Server** — `GET /admin/library/export` (nút "Tải bộ đáp án (JSON)" ở trang
Thư viện): bản thắng của mỗi bài, chỉ lấy bản người sửa tay hoặc dev ghim
(`?all=1` lấy cả bản máy dò). **Đã deploy 2026-09-27** (sao lưu bản cũ: `/opt/qls/server/backups/20260927_155818/`).

**Công cụ chấm** — `tools/danh_gia_do_tone.py`:
```
# bộ thử tổng hợp, không cần mạng (test hồi quy khi đổi thuật toán)
.venv\Scripts\python.exe tools\danh_gia_do_tone.py tong-hop [--nhanh]

# bộ đáp án thật: file tải từ admin, hoặc data\manual_timelines.json
.venv\Scripts\python.exe tools\danh_gia_do_tone.py chay dap_an_tone.json --bao-cao kq.csv
.venv\Scripts\python.exe tools\danh_gia_do_tone.py chay dap_an_tone.json --che-do toan-bai

# bộ đáp án kiểm chứng tay, version trong repo (JSON tự soạn)
.venv\Scripts\python.exe tools\danh_gia_do_tone.py chay tools\dap_an_tone_kiem_chung.json
```
Audio tải về giữ trong `.cache/danh_gia_tone/` (đã gitignore) — lần chạy sau
không tải lại. Chế độ `toan-bai` báo thêm % thời lượng khớp và số bài báo
thừa/thiếu lần đổi tone.

Test: `tests/test_danh_gia_do_tone.py` (31), `tests/core/test_tone_detector.py`
(+2 test tuning, sửa TD-13c vốn khoá cứng hành vi lỗi), `server/tests/test_library.py` (+2).

### 2026-09-27 — Số đo thật đầu tiên + chuỗi tone chia vùng (chưa commit)

Bộ đáp án từ server: 12 bài karaoke Việt (6 bài dev ghim), hơn nửa là dân ca
Nghệ Tĩnh (ngũ cung). 1 bài có đổi tone.

**Dò nhanh (45s đầu):** đúng tuyệt đối 3/12, **đúng tập nốt 6/12**. Tệ hơn hẳn
bộ tổng hợp. Chẩn đoán từng bài:
- Nhạc ngũ cung: 5 nốt chính nằm trọn trong 4–6 tone 7 nốt khác nhau → profile
  phương Tây phân vân giữa các tone đó (D ↔ A, Fm ↔ A#m).
- "1 Mẹ 10 Con": lệch tuning **-46 cent** (gần đúng nửa cung — bản hạ tone bằng
  phần mềm) → audio nằm giữa hai nốt, không thuật toán nào chắc được.
- **Nhãn đáng ngờ, cần nghe lại:** "Áo Xanh" đáp án Gm nhưng audio rõ là G#m
  (5 nốt C# D# G# A# B chiếm áp đảo, đáp án xếp hạng 17/24); "Giọng Nghệ tìm về"
  đáp án G trưởng nhưng audio có D# và F mạnh, không có B → nhiều khả năng Gm.
- `confidence` có mang tín hiệu trên nhạc thật: 4/4 bài < 0,7 đều sai; 6/6 bài
  ≥ 0,8 đều đúng tập nốt → ngưỡng cảnh báo 0,30 hiện tại vô dụng, ~0,7 hợp lý
  hơn (cần thêm dữ liệu để chốt).

**Dò toàn bài — lỗi lớn nhất:** cách gộp cũ báo **15,7 lần đổi tone/bài**
(đáp án 0–1), tone khớp 27% thời lượng. Nguyên nhân: đoạn cắt theo cấu trúc
chỉ 10–20s nên tone từng đoạn là hợp âm, nhảy A↔F#m↔Bm↔C#m, C↔Am↔Em↔Dm.

**Sửa: chia VÙNG tone** (`ToneDetector._regionalize`, hằng `TIMELINE_REGION_*`):
mỗi vùng neo vào tone tính từ chroma tích luỹ của nó; chỉ mở vùng mới khi đoạn
khác bộ nốt (chung < 6 nốt), thắng tone vùng ≥ 0,20 tương quan và dài ≥ 30s.
Tham số chọn bằng quét lưới (min 20/30/45s × Δ 0,10/0,15/0,20) trên 12 bài thật
+ 4 bài tổng hợp có/không chuyển tone.

| Dò toàn bài | Cách cũ | Chia vùng |
|---|---|---|
| Đổi tone TB mỗi bài (thật) | 15,7 | **0,2** |
| Khớp tập nốt theo thời lượng (thật) | 43,8% | **63,5%** |
| Đúng tập nốt tone chính (thật) | 58,3% | **66,7%** |
| Đúng tuyệt đối tone chính (thật) | 41,7% | 25,0% ⚠ |
| Tổng hợp: số lần đổi (đúng: 1,1,1,0) | 1,4,3,2 | **1,1,1,0** |

⚠ Đánh đổi: dò trên chroma cả vùng nghiêng về giọng TRƯỞNG song song (Sông Lam
Am→C, Xa Khơi G#m→B). Vô hại với Auto-Tune (cùng 7 nốt) nhưng tên tone hiển
thị sai — việc của GĐ1–2.

Kèm theo: `_detect_key_from_chroma_impl(verbose=, cleanup=)` — gọi lặp không in
log, không `MemoryGuard.force_cleanup()` (full GC) mỗi lần; vòng dò từng đoạn
cũng bỏ dọn RAM sau mỗi đoạn (hàm đã dọn một lần ở cuối). Test: `TestRegionalize` (6).

### 2026-09-27 — Quyết định sản phẩm + thu thập số đo ngầm (chưa commit)

**Quyết định:** KHÔNG hiện cảnh báo "dò chưa chắc", nhãn độ tin cậy hay nút đảo
trưởng/thứ cho khách — làm giảm lòng tin vào app. Mọi cải tiến chạy ngầm: thu
thập số đo + chỉnh thuật toán nội bộ. (Màu cam của ô tone ở `frontend_qt.py`
gắn với cờ `uncertain` < 0,30 — gần như không bao giờ bật; nếu sau này đổi
thang độ tin cậy thì PHẢI tách khỏi màu hiển thị này.)

**Thu thập** (đi qua đường Thư viện tone dùng chung có sẵn — mặc định bật,
tắt được trong Thiết lập; chỉ mã video + tone + con số, không dữ liệu cá nhân):
- Client: mỗi lượt MÁY DÒ gửi kèm `diag` = chế độ (nhanh/toan-bai), nguồn audio
  (youtube/loa), độ tin cậy của tone chính, tuning (cent), bản app. Bản người sửa
  tay không gửi. `tone_share._clean_diag` kẹp giá trị về miền server nhận (vượt
  miền là server từ chối CẢ gói). Server cũ bỏ qua trường lạ → phát hành client
  và server theo thứ tự nào cũng được.
- Server: bảng `tone_detections`, upsert theo (bài, máy, chế độ) — không phình.
  Tự tạo khi container khởi động (`init-db`). Không ảnh hưởng biến thể/phiếu.
  **Server đã deploy 2026-09-27** (sao lưu: `/opt/qls/server/backups/20260927_174043/`).
- Trang `/admin/library/errors` "Máy dò vs người sửa" (+ `errors.json`): mọi kết
  quả máy dò (lượt dò có số đo + biến thể máy dò của client cũ) đặt cạnh bản
  người sửa/ghim của cùng bài; đếm theo loại lỗi và bảng "độ tin cậy ↔ tỉ lệ
  đúng" để hiệu chỉnh. Bộ đáp án tự lớn dần mỗi khi khách sửa tay.

### 2026-09-27 — Phần 2: dò nhanh tự phân tích thêm khi kém tự tin (chưa commit)

Đo trên 12 bài thật (đáp án = tone chính cả bài):

| Cách | Đúng tuyệt đối | Đúng tập nốt | CPU phân tích |
|---|---|---|---|
| 45s đầu (cũ) | 3/12 | 6/12 | 1,9s |
| 120s đầu | 4/12 | 8/12 | 5,0s |
| Cả bài | 5/12 | 8/12 | 15,2s |
| **45s; confidence < 0,80 thì dò lại 120s** | **5/12** | **8/12** | 3,3s TB (6/12 bài dò thêm) |
| Chọn kết quả tự tin hơn giữa 45s / cả bài | 4/12 | 7/12 | — |

Chọn ngưỡng 0,80 + cửa sổ 120s (quét T = 0,60…0,85). Hết lỗi quãng 5.
⚠ Mức cải thiện đến từ 2 bài (Hà Tĩnh Quê Ơi A→D, Ngôi Sao Lẻ Loi A#m→Fm) —
mẫu nhỏ, theo dõi tiếp ở `/admin/library/errors` (lượt mở rộng mang mode
`nhanh-mo-rong`).

Cài đặt:
- `ToneDetector.detect_key_from_file(path, sr, first_seconds, cancelled)` +
  hằng `FAST_FIRST_SECONDS` / `FAST_EXTEND_SECONDS` / `FAST_EXTEND_BELOW_CONFIDENCE`.
  Kết quả mở rộng mang `extended_seconds`. Không báo gì cho khách.
- Dò nhanh từ trình duyệt và `detect_key_from_youtube` cùng dùng hàm này; tải
  **125s một lần** ngay từ đầu (`download_youtube_audio_with_info(max_seconds=)`)
  — audio nén ~2MB, không phải đi mạng lần hai khi cần dò thêm.
- Không áp cho nghe loa (muốn thêm audio phải bắt khách chờ đếm ngược lâu hơn).
- Công cụ chấm `--che-do nhanh` đi đúng hàm này; cache dò nhanh đổi tên theo độ
  dài (`<id>.nhanh125.wav`) — file 50s đời cũ không đủ cho lần dò thêm.
- Test: `TestDetectKeyFromFile` (4); sửa `test_tai_dung_bang_duration_limit`
  (giờ khẳng định tải ĐỦ thay vì tải ĐÚNG BẰNG).

**Việc tiếp theo:**
1. Nghe lại 2 nhãn đáng ngờ (Áo Xanh, Giọng Nghệ tìm về) — sửa trong app nếu sai.
2. Mở rộng bộ đáp án (ghim thêm bài đã kiểm chứng) — 12 bài quá ít để chốt tham số.
   → bắt đầu tại `tools/dap_an_tone_kiem_chung.json` (xem mục 2026-10-03).
3. GĐ1: độ tin cậy mới + ngưỡng cảnh báo; phân giải trưởng/thứ song song
   (bass/đoạn kết); xem xét profile cho nhạc ngũ cung.

### 2026-10-03 — Bộ đáp án kiểm chứng tay trong repo + ca nhầm quãng 5 đầu tiên

Bộ đáp án trên server chỉ lớn khi khách sửa tay; thêm một file version trong
repo cho bài đã kiểm chứng độc lập: `tools/dap_an_tone_kiem_chung.json` (định
dạng JSON tự soạn của công cụ chấm, mỗi mục có `kiem_chung` ghi căn cứ).
Test `test_file_dap_an_kiem_chung_trong_repo_doc_duoc` giữ file luôn đọc được.

**Bài 1 — Lưng Cha Bụng Mẹ (Thiên Chí, karaoke, pMPvJE1wwnc): đáp án F#m, máy
dò ra Bm ở cả hai chế độ** (nhanh: conf 0,74 → tự mở rộng 120s vẫn Bm; toàn bài:
một vùng Bm). Chấm: nhầm quãng 5 (Bm = bậc iv của F#m), MIREX 50.

Căn cứ đáp án: hopamviet.vn / hopamchuan.com ghi tone gốc F#m, hợp âm (dịch
về F#m) F#m–D–E–Bm–C#m. Đo trên audio khớp hoàn toàn: G# 7,7% vs G 3,4% (Bm cần
G, F#m cần G#); bass F# 56s, C# 52s, A 15s; kết bài C#m → F#m.

Vì sao sai **[ĐO]**: hai tone chung 6/7 nốt. Hợp âm bVII (E) dùng liên tục
nên E mạnh (14,2%); profile Aarden minor (trọng số 50%) cho bậc 4 (14,4) nặng
gấp đôi bậc b7 (7,4) → đọc E là bậc 4 của Bm chứ không phải b7 của F#m. Aarden
Bm 0,88 > F#m 0,78 dù KS nói ngược (F#m 0,68 > Bm 0,54). Ở lượt 60s, F#m đứng
hạng 2, kém 0,036. Dò toàn bài: từng đoạn ra F#m/C#m/A/Bm xen kẽ, `_regionalize`
lấy Bm vì tương quan cao nhất, không phải vì là chủ âm.

Gợi ý cho GĐ1 (chưa làm): tín hiệu bass (nốt gốc chiếm thời lượng) và hợp âm
kết bài đều chỉ đúng F#m ở bài này — đúng hướng "phân giải bằng bass/đoạn kết"
đã nêu, và nên áp cho cả cặp quãng 5 chứ không riêng trưởng/thứ song song.

## Script đo nháp
Bộ thử tổng hợp đã chuyển vào `tools/danh_gia_do_tone.py`. Nguyên mẫu HMM
(`hmm_proto.py`) chỉ nằm trong thư mục tạm của phiên nghiên cứu, không giữ lại.
