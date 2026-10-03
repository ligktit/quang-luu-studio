"""
Quang Lưu Studio — Tone Detector
Class: ToneDetector
Pipeline: HPSS (harmonic, single-shot) → Chroma CQT (energy-weighted) → Weighted Multi-profile (Aarden/Temperley/KS) → Disambiguation
"""
import gc
import ctypes


class ToneDetector:
    """
    Dò Tone bài hát - Phát hiện key/tonality từ audio
    Pipeline: HPSS (harmonic, single-shot) → Chroma CQT (energy-weighted) → Weighted Multi-profile (Aarden/Temperley/KS) → Disambiguation
    """
    
    # Krumhansl-Schmuckler key profiles (1990) - weight 20%
    KS_MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
    KS_MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
    
    # Temperley key profiles (CBMS, 2001) - weight 30%
    TEMP_MAJOR = [5.0, 2.0, 3.5, 2.0, 4.5, 4.0, 2.0, 4.5, 2.0, 3.5, 1.5, 4.0]
    TEMP_MINOR = [5.0, 2.0, 3.5, 4.5, 2.0, 4.0, 2.0, 4.5, 3.5, 2.0, 1.5, 4.0]
    
    # Aarden-Essen key profiles (corpus-based) - weight 50% (tối ưu cho pop)
    AARDEN_MAJOR = [17.7661, 0.145624, 14.9265, 0.160186, 19.8049, 11.3587,
                    0.291248, 22.062, 0.145624, 8.15494, 0.232998, 4.95122]
    AARDEN_MINOR = [18.2648, 0.737619, 14.0499, 16.8599, 0.702494, 14.4362,
                    0.702494, 18.6161, 4.56621, 1.93186, 7.37619, 1.75623]
    
    # Trọng số từng bộ profile
    PROFILE_WEIGHTS = {
        'aarden': 0.50,
        'temperley': 0.30,
        'ks': 0.20
    }
    
    # Backward compatibility aliases
    MAJOR_PROFILE = KS_MAJOR
    MINOR_PROFILE = KS_MINOR
    
    # Key names - khớp với Auto-Tune (đều dùng sharp notation)
    MAJOR_KEY_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    MINOR_KEY_NAMES = ["Cm", "C#m", "Dm", "D#m", "Em", "Fm", "F#m", "Gm", "G#m", "Am", "A#m", "Bm"]
    
    # Relative key pairs: Major index → Minor index (cách 9 semitone)
    # C Major (0) ↔ Am (9), D Major (2) ↔ Bm (11), ...
    RELATIVE_MINOR_OFFSET = 9  # Major + 9 semitone = relative Minor
    
    # Confidence threshold: chỉ chuyển tone khi chênh lệch > 5%
    KEY_CHANGE_THRESHOLD = 0.05

    # Ngưỡng phân loại độ tin cậy của best correlation (single-shot).
    # Dưới LOW → uncertain=True (UI nên cảnh báo); chỉ gắn cờ, KHÔNG chặn kết quả.
    CONFIDENCE_LOW_THRESHOLD = 0.30   # < 0.30 → 'low'  + uncertain
    CONFIDENCE_HIGH_THRESHOLD = 0.60  # >= 0.60 → 'high'

    # Ngưỡng chênh lệch correlation giữa top candidate relative/parallel:
    # khi |corr1 - corr2| < ngưỡng này thì correlation gần như đồng hạng,
    # cần tonal_strength phân giải mạnh hơn (corr nuốt tín hiệu tonal nếu giữ 0.85).
    RELATIVE_CORR_TIE_THRESHOLD = 0.05

    # Ngưỡng RMS coi là im lặng — DÙNG CHUNG cho single-shot (audio thô)
    # và detect_timeline_advanced (mean rms từng segment). Trước đây 2 chỗ
    # dùng 2 giá trị khác nhau (0.001 vs 0.005) gây bất nhất: đoạn bị coi là
    # Silence ở timeline lại detect được ở single-shot. Thống nhất tại đây.
    SILENCE_RMS_THRESHOLD = 0.005
    
    # Voting window: số segments cần đồng thuận trước khi chuyển tone
    VOTING_WINDOW = 3

    # ── Chia VÙNG tone cho "dò toàn bài" (xem _regionalize) ────────────────────
    # Đoạn cắt theo cấu trúc chỉ dài 10–20s nên tone dò riêng từng đoạn thực chất
    # là hợp âm của đoạn đó: trên 12 bài karaoke Việt có đáp án người sửa tay,
    # cách gộp cũ báo 15.7 lần đổi tone/bài (đáp án: 0–1), nhảy qua lại giữa các
    # tone cùng bộ nốt (A↔F#m↔Bm, C↔Am↔Dm). Chia vùng: 0.2 lần/bài, khớp tập nốt
    # theo thời lượng 44% → 64%, vẫn bắt đúng nâng ½ cung / 1 cung / nâng cuối
    # bài trên âm thanh tổng hợp. Số đo: tools/danh_gia_do_tone.py,
    # docs/NGHIEN_CUU_DO_TONE.md.
    # ── Dò nhanh: tự phân tích thêm khi kém tự tin (detect_key_from_file) ──────
    # Chạy NGẦM, không báo gì cho khách. Trên 12 bài karaoke Việt có đáp án:
    # 45s đầu đúng tập nốt 6/12; dò lại trên 120s khi confidence < 0.80 → 8/12
    # (ngang dò cả bài, mà cả bài tốn 15s CPU, 120s chỉ ~5s; chỉ nửa số bài
    # phải dò thêm). Mọi bài < 0.70 trong mẫu đều sai. Theo dõi tiếp ở
    # /admin/library/errors — lượt dò mở rộng mang mode "nhanh-mo-rong".
    FAST_FIRST_SECONDS = 45
    FAST_EXTEND_SECONDS = 120
    FAST_EXTEND_BELOW_CONFIDENCE = 0.80

    TIMELINE_REGION_MIN_SECONDS = 30   # vùng tone ngắn hơn → nhập vào vùng kề
    TIMELINE_REGION_MIN_GAIN = 0.20    # tone đoạn phải thắng tone vùng bấy nhiêu tương quan
    TIMELINE_FAMILY_OVERLAP = 6        # chung >= bấy nhiêu nốt = cùng họ, không tính đổi tone

    # ── Trần an toàn + tham số xử lý theo khối cho chế độ "dò toàn bài" ────────
    #
    # detect_timeline_advanced() trước đây nạp và xử lý NGUYÊN bài trong RAM.
    # Đỉnh RAM tỉ lệ tuyến tính với độ dài bài (đo thực tế ~1.3 MB cho mỗi giây
    # audio ở sr=22050): bài 15 phút ngốn ~1.17 GB đỉnh. Trên máy quán chạy kèm
    # Studio One + VST + trình duyệt thì đó là vùng nguy hiểm — và gc.collect()
    # sau khi dò xong KHÔNG cứu được, vì đỉnh xảy ra lúc bộ nhớ đang được dùng.
    #
    # Hai biện pháp, dùng cùng nhau:
    #   1. TIMELINE_MAX_SECONDS — trần cứng, chặn từ lúc nạp file (xem _tone.py).
    #   2. Xử lý theo khối — RAM đỉnh phẳng theo kích thước khối, không theo
    #      độ dài bài. Đo thực tế: ~90 MB dù bài 5, 10 hay 15 phút.
    TIMELINE_MAX_SECONDS = 20 * 60   # 20 phút — dư cho mọi bài karaoke/liên khúc

    # Thu loopback (nghe từ loa) — chống treo. stream.read() của WASAPI loopback
    # CHẶN cho tới khi có gói âm thanh, mà Windows KHÔNG gửi gói nào khi loa không
    # phát gì (nhạc đang dừng) hoặc loa vừa bị rút/tắt (Bluetooth, HDMI) — luồng dò
    # treo mãi. Nên chỉ đọc phần đã có sẵn (get_read_available) và tự bỏ cuộc:
    #   - quá LOOPBACK_NO_DATA_SEC giây liền không nhận được mẫu nào → coi như im lặng;
    #   - tổng thời gian thu vượt duration + LOOPBACK_GRACE_SEC → dừng với phần đã có.
    LOOPBACK_NO_DATA_SEC = 4
    LOOPBACK_GRACE_SEC = 5
    LOOPBACK_POLL_SEC = 0.02

    # Kích thước khối xử lý. librosa dựng lại filter bank CQT ở MỖI lần gọi
    # (librosa.cache mặc định là no-op) nên khối càng nhỏ thì chi phí cố định
    # càng lấn: đo trên bài 15 phút, khối 30s mất 6.3s còn khối 60s mất 6.0s,
    # trong khi RAM đỉnh chỉ nhích từ 22MB lên 36MB. 60s là điểm cân bằng.
    TIMELINE_BLOCK_SECONDS = 60

    # Đệm hai bên mỗi khối rồi VỨT BỎ phần đệm sau khi tính. Phải phủ được nửa
    # chiều dài filter CQT dài nhất (bin thấp nhất C1≈32.7Hz, bins_per_octave=36
    # → Q≈51.4 → filter ≈ 51.4*sr/32.7 ≈ 1.57s ở sr=22050, nửa ≈ 0.79s). Lấy 2s
    # cho dư. Nhờ vậy mọi frame được giữ đều "nhìn thấy" audio thật ở cả hai bên,
    # đúng như khi tính nguyên bài.
    TIMELINE_BLOCK_PAD_SECONDS = 2.0

    # Ước lượng tuning: librosa.feature.chroma_cqt(tuning=None) tự gọi
    # estimate_tuning() trên TOÀN BỘ mảng được truyền vào. Đó vừa là thủ phạm
    # chính của đỉnh RAM (đo được 1098 MB / 1171 MB tổng ở bài 15 phút), vừa
    # khiến chia khối làm SAI kết quả — mỗi khối tự ước lượng một tuning khác
    # nhau nên chroma lệch nhau ~0.03. Cách xử lý: ước lượng tuning MỘT LẦN từ
    # một mẫu có giới hạn, rồi truyền tuning đó vào mọi khối.
    TUNING_SAMPLE_SECONDS = 60   # tổng độ dài audio dùng để ước lượng
    TUNING_EXCERPT_COUNT = 6     # chia thành bấy nhiêu đoạn trải đều khắp bài

    # Độ phân giải khi ƯỚC LƯỢNG tuning — KHÁC độ phân giải CQT (36 bin/quãng 8).
    # librosa.estimate_tuning trả về phần lẻ của MỘT BIN trong [-0.5, 0.5). Ước
    # lượng ở 36 bin thì một bin chỉ rộng 33 cent → chỉ đọc đúng ±16.7 cent, lệch
    # hơn là bị gấp vòng (đo được: bài lệch +20 cent đọc thành -11 cent) và dò
    # sang tone quãng 5. Ước lượng ở 12 bin (±50 cent) rồi đổi sang đơn vị bin
    # của CQT. Chroma_cqt(tuning=None) mặc định mắc đúng lỗi này nên mọi lời gọi
    # chroma_cqt trong file đều phải truyền tuning tường minh.
    TUNING_ESTIMATE_BINS_PER_OCTAVE = 12
    CHROMA_BINS_PER_OCTAVE = 36  # mặc định của librosa.feature.chroma_cqt
    
    # Bảng ánh xạ Key → MIDI CC value (từ knob% thực tế trên plugin Auto-Tune)
    # Plugin nhận 0-127 → hiển thị 0-100%. Công thức: round(knob% × 127/100)
    #
    # ⚠ NGUỒN THẬT: core.config._DEFAULT_APP_CONFIG['key_midi_map']. Hai hằng
    # KEY_MIDI_MAP/SCALE_MIDI_MAP dưới đây chỉ là FALLBACK khi AppConfig import
    # lỗi (xem key_index_to_midi/scale_to_midi). Nếu ai đổi config mà quên cập
    # nhật 2 hằng này → lệch âm thầm. test_tone_detector.TestMidiMapNoDrift
    # khẳng định 2 bảng phải BẰNG config default để bắt mọi drift ngay.
    KEY_MIDI_MAP = {
        "C": 0,   "C#": 11,  "Db": 11,  "D": 23,  "D#": 34,  "Eb": 34,
        "E": 46,  "F": 57,   "F#": 69,  "G": 80,
        "G#": 92, "Ab": 92,  "A": 103,  "A#": 115, "Bb": 115, "B": 127,
    }
    # Scale → MIDI CC value (từ knob% thực tế trên plugin)
    # NGUỒN THẬT: core.config._DEFAULT_APP_CONFIG['scale_midi_map'] (fallback).
    SCALE_MIDI_MAP = {
        "Major": 13,
        "Minor": 18,
    }
    
    @staticmethod
    def _safe_corrcoef(a, b):
        """
        Pearson correlation an toàn: nếu một trong hai vector phẳng (std≈0,
        VD chroma noise/silence) thì np.corrcoef trả NaN và phát
        RuntimeWarning "invalid value in divide". Ở đây ta tự kiểm tra std
        trước, trả 0.0 thay vì NaN để sort/disambiguation luôn xác định.
        """
        import numpy as np
        a = np.asarray(a, dtype=float)
        b = np.asarray(b, dtype=float)
        std_a = np.std(a)
        std_b = np.std(b)
        if std_a == 0.0 or std_b == 0.0 or not np.isfinite(std_a) or not np.isfinite(std_b):
            return 0.0
        corr = float(np.corrcoef(a, b)[0, 1])
        # Chốt chặn cuối: bất kỳ NaN/inf nào lọt qua → 0.0
        if not np.isfinite(corr):
            return 0.0
        return corr

    @staticmethod
    def _correlate_profiles(chroma_avg, major_profile, minor_profile):
        """
        Tính correlation cho 1 bộ profile (Major + Minor) với chroma vector.
        Trả về dict {uid: correlation} cho 24 keys.
        """
        import numpy as np
        results = {}
        for i in range(12):
            rotated = np.roll(chroma_avg, -i)
            major_corr = ToneDetector._safe_corrcoef(rotated, major_profile)
            uid_major = f"{ToneDetector.MAJOR_KEY_NAMES[i]}_Major"
            results[uid_major] = {
                "key": ToneDetector.MAJOR_KEY_NAMES[i],
                "scale": "Major",
                "correlation": major_corr,
                "key_index": i
            }
            minor_corr = ToneDetector._safe_corrcoef(rotated, minor_profile)
            uid_minor = f"{ToneDetector.MINOR_KEY_NAMES[i]}_Minor"
            results[uid_minor] = {
                "key": ToneDetector.MINOR_KEY_NAMES[i],
                "scale": "Minor",
                "correlation": minor_corr,
                "key_index": i
            }
        return results
    
    @staticmethod
    def _is_relative_pair(key1_idx, scale1, key2_idx, scale2):
        """Kiểm tra 2 key có phải relative pair không (C Major ↔ Am)"""
        if scale1 == "Major" and scale2 == "Minor":
            return (key1_idx + ToneDetector.RELATIVE_MINOR_OFFSET) % 12 == key2_idx
        if scale1 == "Minor" and scale2 == "Major":
            return (key2_idx + ToneDetector.RELATIVE_MINOR_OFFSET) % 12 == key1_idx
        return False
    
    @staticmethod
    def _note_overlap(key1_idx, scale1, key2_idx, scale2):
        """Số nốt chung giữa 2 scale (0..7)."""
        major_intervals = [0, 2, 4, 5, 7, 9, 11]  # W W H W W W H
        minor_intervals = [0, 2, 3, 5, 7, 8, 10]  # Natural minor

        if scale1 == "Major":
            notes1 = set((key1_idx + i) % 12 for i in major_intervals)
        else:
            notes1 = set((key1_idx + i) % 12 for i in minor_intervals)

        if scale2 == "Major":
            notes2 = set((key2_idx + i) % 12 for i in major_intervals)
        else:
            notes2 = set((key2_idx + i) % 12 for i in minor_intervals)

        return len(notes1 & notes2)

    @staticmethod
    def _relation_level(key1_idx, scale1, key2_idx, scale2):
        """
        Phân loại mức độ liên quan giữa 2 key:
          'relative' — relative pair (C↔Am, 7 nốt chung, cùng "tonic-family")
          'parallel' — parallel pair (C↔Cm, cùng tonic root)
          'neighbor' — lân cận trên circle of fifths (6 nốt chung, VD C↔G, C↔Dm)
          None       — không liên quan đủ gần

        Phân biệt mức độ này để disambiguation ưu tiên relative/parallel hơn
        neighbor: đổi tonic sang quãng-5 (neighbor) chỉ khi bằng chứng tonal mạnh.
        """
        if ToneDetector._is_relative_pair(key1_idx, scale1, key2_idx, scale2):
            return 'relative'
        if key1_idx == key2_idx and scale1 != scale2:
            return 'parallel'
        overlap = ToneDetector._note_overlap(key1_idx, scale1, key2_idx, scale2)
        if overlap >= 6:
            return 'neighbor'
        return None

    @staticmethod
    def _are_closely_related(key1_idx, scale1, key2_idx, scale2):
        """
        Kiểm tra 2 key có closely related không (chia sẻ >= 6/7 nốt).
        Bao gồm: relative keys, parallel keys, và các key lân cận trên circle of fifths.
        VD: Eb Major ↔ Fm, C Major ↔ Am, C Major ↔ Dm, G Major ↔ Em, ...
        """
        return ToneDetector._note_overlap(key1_idx, scale1, key2_idx, scale2) >= 6

    @staticmethod
    def detect_key_from_audio(audio_data, sample_rate, accumulated_chroma=None,
                              skip_hum_detection=False, use_hpss=True):
        """
        Phát hiện tone/key của bài hát từ audio data.
        Pipeline: Robust Preprocessing → HPSS (harmonic) → CQT chroma (energy-weighted)
                  → Weighted Multi-profile → Disambiguation

        use_hpss: True (mặc định cho single-shot) tách thành phần harmonic bằng
            librosa.effects.hpss trước khi tính chroma, loại bớt percussion/transient
            làm nhiễu chroma. Các luồng realtime/nhanh (autokey 5s/lần) có thể truyền
            use_hpss=False để bỏ qua, tiết kiệm CPU.

        skip_hum_detection: True bỏ qua bước notch hum 50/60Hz (Stage 5), tiết
            kiệm ~100–200ms. ĐÁNH ĐỔI: chỉ an toàn khi nguồn audio đã sạch hum —
            đúng với nhạc YouTube đã master/encode chuẩn (detect_key_from_youtube
            truyền True). KHÔNG đúng tuyệt đối với video quay điện thoại / livestream
            / cover thu tại nhà đăng lên YouTube: các nguồn này có thể dính hum
            mains 50/60Hz lọt vào dải bass và làm lệch tonic. Hiện vẫn để mặc định
            skip cho YouTube (đa số là nhạc sạch, ưu tiên tốc độ); nếu cần độ chính
            xác tối đa cho nguồn nghi ngờ có hum, gọi với skip_hum_detection=False.
            Hum thường nằm ngoài dải tonal nên rủi ro lệch là thấp-trung, không cao.
        """
        try:
            import librosa
            import numpy as np
            
            audio_data = np.nan_to_num(audio_data, nan=0.0, posinf=0.0, neginf=0.0)
            
            # === BƯỚC 0: Robust Preprocessing ===
            
            # Stage 1: Clip extreme outliers (corrupted samples, VD: max=1.8e29)
            audio_data = np.clip(audio_data, -1e6, 1e6)

            # Stage 2: Silence gate trên audio THÔ — phải kiểm tra TRƯỚC khi
            # normalize, vì percentile normalize sẽ khuếch đại noise im lặng
            # lên full scale và bị "detect" nhầm thành nhạc.
            rms_check = np.sqrt(np.mean(audio_data ** 2))
            if rms_check < ToneDetector.SILENCE_RMS_THRESHOLD:
                print("   Audio quá nhỏ hoặc im lặng, bỏ qua")
                return None

            # Stage 3: Percentile-based normalize (tránh 1 sample lỗi phá hủy signal)
            p999 = np.percentile(np.abs(audio_data), 99.9)
            if p999 > 0:
                audio_data = audio_data / p999
            audio_data = np.clip(audio_data, -1.0, 1.0)

            # Stage 4: DC offset removal
            audio_data = audio_data - np.mean(audio_data)
            
            # Stage 5: Adaptive hum removal (PYIN detect → notch filter)
            # Skipped khi skip_hum_detection=True (YouTube) để tiết kiệm ~100–200ms.
            # ĐÁNH ĐỔI: giả định "nguồn đã sạch hum" KHÔNG đúng với video quay
            # điện thoại / livestream / cover thu tại nhà có hum mains 50/60Hz
            # (xem docstring detect_key_from_audio). Mặc định vẫn skip cho YouTube;
            # rủi ro lệch tonic do hum là thấp-trung (hum nằm dưới dải tonal).
            if not skip_hum_detection:
                try:
                    f0_detect, voiced, _ = librosa.pyin(
                        audio_data, fmin=50, fmax=80, sr=sample_rate,
                        frame_length=4096
                    )
                    valid_f0 = f0_detect[~np.isnan(f0_detect) & voiced]
                    del f0_detect, voiced  # Giải phóng mảng pyin ngay
                    if len(valid_f0) > 100:
                        hum_freq = np.median(valid_f0)
                        hum_ratio = np.sum(np.abs(valid_f0 - hum_freq) < 2) / len(valid_f0)
                        if hum_ratio > 0.95:
                            S = librosa.stft(audio_data)
                            freqs = librosa.fft_frequencies(sr=sample_rate)
                            for harmonic_n in range(1, 4):
                                target = hum_freq * harmonic_n
                                S[np.abs(freqs - target) < 5] = 0
                            audio_data = librosa.istft(S, length=len(audio_data))
                            del S, freqs  # Giải phóng STFT matrix (~8MB)
                            print(f"   Notch: loại hum {hum_freq:.0f}Hz ({hum_ratio*100:.0f}%)")
                    del valid_f0
                except Exception:
                    pass
            
            print(f"   Preprocessing OK (p99.9={p999:.4f}, rms={rms_check:.4f})")
            print("🎵 [DÒ TONE] Pipeline: HPSS → CQT → Weighted Multi-profile...")

            # === BƯỚC 0.5: HPSS — tách thành phần harmonic ===
            # Percussion/transient (trống, hi-hat...) tạo năng lượng broadband làm
            # chroma "phẳng" và nhiễu tonic. Tách harmonic trước khi tính chroma giúp
            # profile correlation rõ ràng hơn. Tắt được qua use_hpss=False cho luồng nhanh.
            chroma_source = audio_data
            if use_hpss:
                try:
                    harmonic = librosa.effects.hpss(audio_data)[0]
                    # Chỉ dùng harmonic nếu nó còn năng lượng (tránh case suy biến)
                    if np.any(harmonic) and np.isfinite(harmonic).all():
                        chroma_source = harmonic
                        print("   ✅ HPSS: dùng thành phần harmonic cho chroma")
                    del harmonic
                except Exception as e:
                    print(f"   ⚠ HPSS bỏ qua ({e}) — dùng audio gốc")

            # === BƯỚC 1: Chroma CQT (energy-weighted) ===
            # Tuning truyền tường minh — để None thì librosa ước lượng ở 36 bin và
            # gấp vòng khi bài lệch quá ±16.7 cent (xem TUNING_ESTIMATE_BINS_PER_OCTAVE).
            tuning_cents = ToneDetector._estimate_tuning_cents(chroma_source, sample_rate)
            chroma_cqt = librosa.feature.chroma_cqt(
                y=chroma_source, sr=sample_rate,
                tuning=ToneDetector._cents_to_chroma_bins(tuning_cents))
            rms = librosa.feature.rms(y=chroma_source)[0]
            min_frames = min(len(rms), chroma_cqt.shape[1])
            rms = rms[:min_frames]
            rms_sum = np.sum(rms)
            if rms_sum > 0:
                # ĐÁNH ĐỔI energy-weight: trọng số = rms tuyến tính nên các frame
                # cực to (chorus/drop) lấn át trung bình chroma. Cách dịu hơn là
                # sqrt(rms) hoặc winsorize trọng số ở percentile cao. KHÔNG đổi ở
                # đây: thay đổi này ảnh hưởng MỌI luồng dò và chưa có bằng chứng
                # cải thiện key đúng — pop/ballad thường đồng nhất tone qua chorus,
                # nên việc chorus lấn át hiếm khi đổi tonic. Giữ tuyến tính để bảo
                # toàn kết quả hiện có; nếu sau này có dataset chứng minh lợi >
                # hại thì winsorize tại đây + đồng bộ chỗ timeline bên dưới.
                chroma_avg = np.average(chroma_cqt[:, :min_frames], axis=1, weights=rms / rms_sum)
            else:
                chroma_avg = np.mean(chroma_cqt, axis=1)
            del chroma_cqt, rms  # Giải phóng mảng 2D chroma + rms (~2MB)
            
            # Normalize
            cs = np.sum(chroma_avg)
            if cs > 0:
                chroma_avg = chroma_avg / cs
            
            # Lưu normalized (cho disambiguation)
            cqt_normalized = chroma_avg.copy()
            
            print(f"   Chroma CQT (energy-weighted)")
            print(f"📊 [DÒ TONE] Chroma: {[f'{x:.3f}' for x in chroma_avg]}")
            
            # === BƯỚC 2b: EMA (AutoKey mode) ===
            if accumulated_chroma is not None:
                alpha = 0.3
                chroma_for_analysis = alpha * chroma_avg + (1 - alpha) * accumulated_chroma
                cs2 = np.sum(chroma_for_analysis)
                if cs2 > 0:
                    chroma_for_analysis = chroma_for_analysis / cs2
                print(f"   ✅ EMA blending (α={alpha})")
            else:
                chroma_for_analysis = chroma_avg

            result = ToneDetector._detect_key_from_chroma_impl(chroma_for_analysis, cqt_normalized)
            if result is not None:
                # Độ lệch so với A4=440Hz. Chưa ai dùng để điều khiển — ghi ra để
                # đo (tools/danh_gia_do_tone.py) và làm nền cho Detune của Auto-Tune.
                result["tuning_cents"] = round(tuning_cents, 1)
            return result

        except Exception as e:
            print(f"[DÒ TONE] Lỗi phân tích: {e}")
            import traceback
            print(traceback.format_exc())
            return None
            
    @staticmethod
    def _detect_key_from_chroma_impl(chroma_for_analysis, cqt_normalized, verbose=True,
                                     cleanup=True):
        """verbose=False: không in log phân tích; cleanup=False: bỏ
        MemoryGuard.force_cleanup() (full GC + trả RAM về Windows) ở cuối. Cả hai
        dùng khi gọi lặp nhiều lần trên vector 12 phần tử (chia vùng tone ở
        detect_timeline_advanced) — dọn RAM mỗi lần là lãng phí, caller dọn một
        lần ở cuối. Không dùng redirect_stdout thay cho verbose vì nó tráo
        sys.stdout của CẢ tiến trình, nuốt log của các luồng khác."""
        log = print if verbose else (lambda *a, **k: None)
        try:
            import numpy as np

            # Guard NaN/inf đầu vào: caller có thể gọi impl trực tiếp với chroma
            # chưa làm sạch. _safe_corrcoef đã chặn NaN/inf phía correlation,
            # nhưng nhánh tonal_strength (disambiguation) đọc thẳng cqt_normalized
            # → 1 phần tử inf/NaN sẽ lan vào tonal_norm/combined và phá so sánh
            # (RuntimeWarning "invalid value in subtract"). Làm sạch 1 lần tại đây.
            chroma_for_analysis = np.nan_to_num(
                np.asarray(chroma_for_analysis, dtype=float),
                nan=0.0, posinf=0.0, neginf=0.0
            )
            cqt_normalized = np.nan_to_num(
                np.asarray(cqt_normalized, dtype=float),
                nan=0.0, posinf=0.0, neginf=0.0
            )

            # === BƯỚC 3: Weighted Multi-profile correlation ===
            W = ToneDetector.PROFILE_WEIGHTS
            
            ks_results = ToneDetector._correlate_profiles(
                chroma_for_analysis, ToneDetector.KS_MAJOR, ToneDetector.KS_MINOR
            )
            temp_results = ToneDetector._correlate_profiles(
                chroma_for_analysis, ToneDetector.TEMP_MAJOR, ToneDetector.TEMP_MINOR
            )
            aarden_results = ToneDetector._correlate_profiles(
                chroma_for_analysis, ToneDetector.AARDEN_MAJOR, ToneDetector.AARDEN_MINOR
            )
            
            all_uids = set(ks_results.keys()) | set(temp_results.keys()) | set(aarden_results.keys())
            all_results = []
            for uid in all_uids:
                ks_c = ks_results.get(uid, {}).get('correlation', 0)
                temp_c = temp_results.get(uid, {}).get('correlation', 0)
                aarden_c = aarden_results.get(uid, {}).get('correlation', 0)
                
                weighted_corr = W['ks'] * ks_c + W['temperley'] * temp_c + W['aarden'] * aarden_c
                
                ref = ks_results.get(uid) or temp_results.get(uid) or aarden_results.get(uid)
                
                all_results.append({
                    "key": ref["key"], "scale": ref["scale"],
                    "correlation": weighted_corr, "key_index": ref["key_index"],
                    "ks_corr": ks_c, "temp_corr": temp_c, "aarden_corr": aarden_c
                })
            
            all_results.sort(key=lambda x: x["correlation"], reverse=True)
            
            # === BƯỚC 4: Key Family Disambiguation ===
            # Tìm TẤT CẢ keys closely-related trong top 7 → chọn key tốt nhất
            best = all_results[0]
            
            # Key commonality: keys phổ biến trong pop/Vietnamese music
            # Score 1.0 = rất phổ biến, 0.0 = rất hiếm
            KEY_COMMON = {
                # Major (sharp notation - khớp Auto-Tune)
                'C': 1.0, 'G': 0.9, 'D': 0.9, 'A': 0.8, 'E': 0.7,
                'F': 0.9, 'A#': 0.8, 'D#': 0.8, 'G#': 0.7,
                'C#': 0.5, 'F#': 0.3, 'B': 0.5,
                # Minor (sharp notation - khớp Auto-Tune)
                'Am': 1.0, 'Em': 0.9, 'Dm': 0.9, 'Bm': 0.7,
                'Gm': 0.8, 'Cm': 0.8, 'Fm': 0.8, 'A#m': 0.5,
                'F#m': 0.6, 'C#m': 0.6, 'G#m': 0.3, 'D#m': 0.3,
            }
            
            # Thu thập candidates closely-related với best, kèm mức độ liên quan.
            # relation_level: 'relative'/'parallel' (mạnh) vs 'neighbor' (yếu).
            family = [best]
            relation_of = {id(best): 'self'}
            for r in all_results[1:7]:
                level = ToneDetector._relation_level(
                    best["key_index"], best["scale"],
                    r["key_index"], r["scale"]
                )
                if level is not None:
                    family.append(r)
                    relation_of[id(r)] = level

            if len(family) >= 2:
                log(f"   Key family ({len(family)} candidates):")

                # --- Trọng số động cho tonal_strength ---
                # Khi correlation của các candidate gần đồng hạng (relative pair
                # như C↔Am có corr gần bằng nhau), correlation 0.85 nuốt tín hiệu
                # tonal → không phân biệt được tonic thật. Lúc đó nâng tỉ trọng
                # tonal lên để tonic/3rd/5th quyết định.
                corr_spread = max(c["correlation"] for c in family) - \
                              min(c["correlation"] for c in family)
                if corr_spread < ToneDetector.RELATIVE_CORR_TIE_THRESHOLD:
                    corr_w, tonal_w = 0.60, 0.40
                    log(f"   ⚖ Corr gần đồng hạng (spread={corr_spread:.3f}) → tonal weight 0.40")
                else:
                    corr_w, tonal_w = 0.85, 0.15

                # Chuẩn hóa tonal_strength trong family để so sánh tương đối
                # (giá trị tuyệt đối phụ thuộc phân bố chroma, không ổn định).
                raw_tonal = {}
                for r in family:
                    tonic = cqt_normalized[r["key_index"]]
                    fifth = cqt_normalized[(r["key_index"] + 7) % 12]
                    if r["scale"] == "Minor":
                        third = cqt_normalized[(r["key_index"] + 3) % 12]
                    else:
                        third = cqt_normalized[(r["key_index"] + 4) % 12]
                    raw_tonal[id(r)] = (tonic + fifth * 0.7 + third * 0.5, tonic, fifth, third)
                # Guard NaN/inf + chia-0: nếu cqt_normalized bẩn (caller gọi impl
                # trực tiếp với chroma chưa làm sạch) thì max(...) có thể là NaN —
                # và "NaN or 1.0" trả NaN (NaN truthy) → tonal_norm NaN, hỏng so
                # sánh combined. Ép về 1.0 khi không finite hoặc <= 0.
                max_tonal = max(v[0] for v in raw_tonal.values())
                if not np.isfinite(max_tonal) or max_tonal <= 0:
                    max_tonal = 1.0

                best_candidate = None
                best_score = -1
                family_scores = []  # Lưu (r, combined) cho tiebreaker

                for r in family:
                    tonal_strength, tonic, fifth, third = raw_tonal[id(r)]
                    tonal_norm = tonal_strength / max_tonal

                    combined = r["correlation"] * corr_w + tonal_norm * tonal_w

                    # Ưu tiên relative/parallel hơn neighbor: neighbor (đổi tonic
                    # sang quãng-5) chỉ thắng nếu tonal vượt trội RÕ RỆT, nếu không
                    # bị phạt nhẹ để tránh nhảy key sang quãng 5 thiếu căn cứ.
                    level = relation_of.get(id(r), 'self')
                    if level == 'neighbor' and tonal_norm < 0.95:
                        combined -= 0.05
                        neigh_tag = " (neighbor -0.05)"
                    else:
                        neigh_tag = ""

                    family_scores.append((r, combined))

                    log(f"      {r['key']:4s}[{level}]: corr={r['correlation']:.3f} "
                          f"T={tonic:.3f} 5={fifth:.3f} 3={third:.3f} "
                          f"tn={tonal_norm:.2f} → {combined:.4f}{neigh_tag}")

                    if combined > best_score:
                        best_score = combined
                        best_candidate = r

                # Commonality tiebreaker: chỉ khi top-2 chênh nhau < 2%
                if best_candidate and len(family_scores) >= 2:
                    family_scores.sort(key=lambda x: x[1], reverse=True)
                    top1, top1_combined = family_scores[0]
                    top2, top2_combined = family_scores[1]
                    if abs(top1_combined - top2_combined) < 0.02:
                        # Dùng commonality phân giải
                        top1_common = KEY_COMMON.get(top1["key"], 0.5)
                        top2_common = KEY_COMMON.get(top2["key"], 0.5)
                        if top2_common > top1_common:
                            best_candidate = top2
                            log(f"   Tiebreaker: {top1['key']} ({top1_common:.1f}) → {top2['key']} ({top2_common:.1f})")

                if best_candidate and best_candidate["key"] != best["key"]:
                    log(f"   Family winner: {best['key']} → {best_candidate['key']}")
                else:
                    log(f"   Giữ {best['key']}")
                best = best_candidate or best
            
            best_key = best["key_index"]
            best_scale = best["scale"]
            best_corr = best["correlation"]
            
            if best_scale == "Major":
                key_display = ToneDetector.MAJOR_KEY_NAMES[best_key]
            else:
                key_display = ToneDetector.MINOR_KEY_NAMES[best_key]
            
            # === Confidence gating (Fix #2) ===
            # KHÔNG chặn kết quả — chỉ gắn cờ để UI cảnh báo khi correlation thấp.
            if best_corr < ToneDetector.CONFIDENCE_LOW_THRESHOLD:
                confidence_level = "low"
                uncertain = True
            elif best_corr >= ToneDetector.CONFIDENCE_HIGH_THRESHOLD:
                confidence_level = "high"
                uncertain = False
            else:
                confidence_level = "medium"
                uncertain = False

            log(f"Kết quả: {key_display} (confidence: {best_corr:.4f} → {confidence_level}"
                  f"{', UNCERTAIN' if uncertain else ''})")
            log(f"   📊 KS={best.get('ks_corr',0):.4f}  T={best.get('temp_corr',0):.4f}  A={best.get('aarden_corr',0):.4f}")
            log(f"Top 5:")
            for r in all_results[:5]:
                log(f"   {r['key']}: {r['correlation']:.4f}")

            # Giải phóng mảng trung gian trước khi return
            del all_results
            if cleanup:
                try:
                    from core.memory import MemoryGuard
                    MemoryGuard.force_cleanup()
                except Exception:
                    pass

            return {
                "key": ToneDetector.MAJOR_KEY_NAMES[best_key],
                "key_index": best_key,
                "scale": best_scale,
                "confidence": best_corr,
                "key_display": key_display,
                "confidence_level": confidence_level,
                "uncertain": uncertain,
            }
            
        except Exception as e:
            print(f"[DÒ TONE] Lỗi phân tích: {e}")
            import traceback
            print(traceback.format_exc())
            return None
    
    @staticmethod
    def _find_loopback_device(pa):
        """Chọn WASAPI loopback device tốt nhất để thu âm.

        Thứ tự ưu tiên:
          1. Loopback analogue của WASAPI default output (loa ĐANG phát nhạc)
          2. Bất kỳ WASAPI loopback device nào còn lại

        Lý do: máy có nhiều loa (Speakers, Headset, HDMI...) thì phải lấy đúng
        loopback của loa mặc định đang phát, không phải loopback đầu tiên trong
        danh sách — nếu lấy nhầm sẽ thu được im lặng dù nhạc vẫn đang phát.
        (Cùng logic với recorder_worker.find_loopback_device.)
        """
        wasapi_info = None
        for i in range(pa.get_host_api_count()):
            info = pa.get_host_api_info_by_index(i)
            if "wasapi" in info.get("name", "").lower():
                wasapi_info = info
                break

        if not wasapi_info:
            print("[DÒ TONE] Không tìm thấy WASAPI host API!")
            return None

        wasapi_api_idx = wasapi_info["index"]

        all_loopbacks = []
        for i in range(pa.get_device_count()):
            try:
                dev = pa.get_device_info_by_index(i)
                if dev.get("isLoopbackDevice", False) and dev.get("hostApi") == wasapi_api_idx:
                    all_loopbacks.append(dev)
            except Exception:
                continue

        if not all_loopbacks:
            print("[DÒ TONE] Không tìm thấy thiết bị loopback!")
            return None

        # Ưu tiên 1: loopback của default output device
        try:
            default_out_idx = wasapi_info.get("defaultOutputDevice", -1)
            if default_out_idx is not None and default_out_idx >= 0:
                default_out = pa.get_device_info_by_index(default_out_idx)
                default_out_name = default_out.get("name", "").lower()
                print(f"[DÒ TONE] Loa mặc định: {default_out.get('name', '?')}")

                for lb in all_loopbacks:
                    lb_base = lb.get("name", "").lower().replace("[loopback]", "").strip()
                    if lb_base and (lb_base in default_out_name or default_out_name in lb_base):
                        return lb

                # Thử helper API của pyaudiowpatch nếu khớp tên thất bại
                try:
                    analogue = pa.get_wasapi_loopback_analogue_by_index(default_out_idx)
                    if analogue:
                        return analogue
                except Exception:
                    pass
        except Exception as e:
            print(f"[DÒ TONE] Không xác định được loopback của loa mặc định: {e}")

        # Ưu tiên 2: loopback đầu tiên
        fallback = all_loopbacks[0]
        print(f"[DÒ TONE] Dùng loopback dự phòng: {fallback['name']}")
        return fallback

    @staticmethod
    def detect_key_from_system_audio(duration=10, sample_rate=48000, on_progress=None,
                                     reason_out=None, cancelled=None):
        """
        Thu âm loopback từ hệ thống (bắt âm thanh đang phát trên loa)
        và phát hiện tone bài hát. Không cần tải từ YouTube.

        Sử dụng WASAPI Loopback (Windows) qua thư viện pyaudiowpatch.

        ``reason_out``: nếu truyền vào 1 list, khi thất bại (trả None) hàm sẽ
        append một câu mô tả NGUYÊN NHÂN cụ thể (để hiển thị cho người dùng).

        ``cancelled``: hàm không tham số trả True khi phiên dò đã huỷ/hết giờ —
        kiểm trong lúc thu để dừng ngay, không nghe loa cho phiên đã bỏ.
        """
        import time
        import numpy as np

        def _fail(reason):
            if reason_out is not None:
                reason_out.append(reason)
            return None

        # Import pyaudiowpatch (thay thế soundcard)
        try:
            import pyaudiowpatch as pyaudio
        except ImportError:
            print("[DÒ TONE] Thư viện 'pyaudiowpatch' chưa được cài đặt.")
            print("   Chạy: pip install pyaudiowpatch")
            return _fail("Ứng dụng thiếu thành phần thu âm nội bộ nên không thể nghe từ loa. "
                         "Vui lòng cài đặt lại ứng dụng.")
        
        # Khởi tạo COM cho background thread (WASAPI yêu cầu COM per-thread)
        com_initialized = False
        try:
            hr = ctypes.windll.ole32.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED
            com_initialized = (hr == 0)  # Chỉ tính khi S_OK
        except Exception:
            pass
        
        pa = None
        stream = None
        try:
            print(f"Thu âm loopback từ hệ thống ({duration}s)...")
            
            pa = pyaudio.PyAudio()

            # Chọn đúng loopback của loa MẶC ĐỊNH đang phát (không phải cái đầu tiên)
            loopback_dev = ToneDetector._find_loopback_device(pa)
            if not loopback_dev:
                return _fail("Không tìm thấy thiết bị loopback (loa) trên hệ thống — "
                             "kiểm tra driver âm thanh / loa mặc định.")

            device_sr = int(loopback_dev["defaultSampleRate"])
            chunk_size = 1024
            
            print(f"[DÒ TONE] Sử dụng loopback: {loopback_dev['name']}")
            print(f"[DÒ TONE] Đang thu âm {duration} giây...")
            
            # Mở stream với fallback channels (giống recorder_worker.py):
            # nhiều thiết bị WASAPI loopback từ chối mono → thử số kênh của
            # device trước, rồi 2, rồi 1. Downmix về mono sau khi thu.
            dev_channels = int(loopback_dev.get("maxInputChannels", 2) or 2)
            channels_used = None
            last_err = None
            for attempt_ch in dict.fromkeys([dev_channels, 2, 1]):
                if attempt_ch < 1:
                    continue
                try:
                    stream = pa.open(
                        format=pyaudio.paFloat32,
                        channels=attempt_ch,
                        rate=device_sr,
                        input=True,
                        input_device_index=loopback_dev["index"],
                        frames_per_buffer=chunk_size
                    )
                    channels_used = attempt_ch
                    break
                except Exception as e:
                    last_err = e
                    print(f"[DÒ TONE] Mở stream thất bại với channels={attempt_ch}: {e}")

            if channels_used is None:
                print(f"[DÒ TONE] Không mở được loopback stream: {last_err}")
                return _fail(f"Không thu được âm thanh từ loa '{loopback_dev['name']}'. "
                             "Hãy kiểm tra loa này có đang phát nhạc và có phải là loa "
                             "mặc định của Windows không.")

            if channels_used > 1:
                print(f"[DÒ TONE] Thu {channels_used} kênh, sẽ downmix về mono")

            # Thu âm theo từng giây để cập nhật progress. KHÔNG gọi stream.read()
            # khi chưa có dữ liệu — xem LOOPBACK_NO_DATA_SEC.
            audio_chunks = []
            started = time.monotonic()
            hard_deadline = started + duration + ToneDetector.LOOPBACK_GRACE_SEC
            last_data = started
            stop_reason = None
            for sec in range(duration):
                frames_needed = device_sr
                frames_read = 0
                while frames_read < frames_needed:
                    if cancelled is not None and cancelled():
                        print("[DÒ TONE] Phiên dò đã huỷ — dừng nghe loa")
                        return _fail("Đã dừng dò tone.")
                    now = time.monotonic()
                    if now - last_data > ToneDetector.LOOPBACK_NO_DATA_SEC:
                        stop_reason = "no_data"
                        break
                    if now > hard_deadline:
                        stop_reason = "deadline"
                        break
                    available = stream.get_read_available()
                    if available <= 0:
                        time.sleep(ToneDetector.LOOPBACK_POLL_SEC)
                        continue
                    data = stream.read(min(available, chunk_size),
                                       exception_on_overflow=False)
                    last_data = time.monotonic()
                    chunk_np = np.frombuffer(data, dtype=np.float32)
                    if channels_used > 1:
                        # Downmix về mono: trung bình các kênh interleaved
                        usable = (len(chunk_np) // channels_used) * channels_used
                        chunk_np = chunk_np[:usable].reshape(-1, channels_used).mean(axis=1)
                    audio_chunks.append(chunk_np)
                    frames_read += len(chunk_np)
                if stop_reason:
                    break

                remaining = duration - sec - 1
                if on_progress:
                    try:
                        on_progress(remaining)
                    except Exception:
                        pass

                print(f"   Còn {remaining}s...")

            got_sec = sum(len(c) for c in audio_chunks) / device_sr
            if stop_reason:
                print(f"[DÒ TONE] Dừng thu sớm ({stop_reason}) sau "
                      f"{time.monotonic() - started:.1f}s, có {got_sec:.1f}s âm thanh")
            # Quá ít để phân tích (loa không đẩy dữ liệu = đang không phát gì).
            if got_sec < min(3.0, duration * 0.5):
                return _fail(f"Loa '{loopback_dev['name']}' không phát ra âm thanh (im lặng). "
                             "Kiểm tra: bài hát có đang phát không, và loa đang phát có đúng "
                             "là loa MẶC ĐỊNH của Windows không.")

            # Ghép các chunks
            audio_data = np.concatenate(audio_chunks)
            del audio_chunks  # Giải phóng list chunks ngay lập tức
            audio_data = np.nan_to_num(audio_data, nan=0.0, posinf=0.0, neginf=0.0)
            
            actual_duration = len(audio_data) / device_sr
            print(f"[DÒ TONE] Đã thu: {actual_duration:.1f}s, {len(audio_data)} samples")
            
            # Kiểm tra âm thanh
            rms = np.sqrt(np.mean(audio_data ** 2))
            print(f"📊 [DÒ TONE] RMS level: {rms:.6f}")
            
            if rms < 0.001:
                print("[DÒ TONE] Không phát hiện âm thanh! Hãy đảm bảo đang phát nhạc.")
                return _fail(f"Loa '{loopback_dev['name']}' không phát ra âm thanh (im lặng). "
                             "Kiểm tra: bài hát có đang phát không, và loa đang phát có đúng "
                             "là loa MẶC ĐỊNH của Windows không.")
            
            # Resample to 22050Hz for faster CQT processing without losing low-frequency resolution
            target_sr = 22050
            if device_sr > target_sr:
                import librosa
                from core.numba_cache import run_healing
                audio_data = run_healing(
                    librosa.resample, audio_data, orig_sr=device_sr, target_sr=target_sr)
                analyze_sr = target_sr
                print(f"[DÒ TONE] Đã downsample loopback từ {device_sr}Hz xuống {target_sr}Hz (Đảm bảo độ chính xác)")
            else:
                analyze_sr = device_sr

            # Phân tích key
            result = ToneDetector.detect_key_from_audio(audio_data, analyze_sr)
            del audio_data  # Giải phóng audio data ngay sau khi dò tone
            try:
                from core.memory import MemoryGuard
                MemoryGuard.force_cleanup()
            except Exception:
                pass
            if not result:
                return _fail("Đã nghe được âm thanh từ loa nhưng không nhận diện được tone "
                             "(âm thanh quá nhiễu hoặc không có giai điệu rõ ràng).")
            # Nguồn audio — chỉ để ghi số đo nội bộ (tone_share diag), không hiển thị.
            result["audio_source"] = "loa"
            return result

        except Exception as e:
            print(f"[DÒ TONE] Lỗi thu âm: {e}")
            import traceback
            print(traceback.format_exc())
            return _fail("Gặp lỗi khi nghe âm thanh từ loa. Vui lòng thử lại; nếu vẫn "
                         "lỗi, kiểm tra thiết bị âm thanh trong phần Cài đặt.")
        finally:
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            if pa:
                try:
                    pa.terminate()
                except Exception:
                    pass
            if com_initialized:
                try:
                    ctypes.windll.ole32.CoUninitialize()
                except Exception:
                    pass
    
    @staticmethod
    def detect_key_from_file(audio_path, sr=16000, first_seconds=None, cancelled=None):
        """Dò tone nhanh từ file audio đầu bài, tự phân tích thêm khi kém tự tin.

        Dò trên `first_seconds` đầu (mặc định FAST_FIRST_SECONDS). Nếu
        confidence < FAST_EXTEND_BELOW_CONFIDENCE và file có đủ audio thì dò lại
        trên FAST_EXTEND_SECONDS đầu và DÙNG kết quả đó — lặng lẽ, không báo gì
        cho khách (quyết định sản phẩm: không hiện "dò chưa chắc"). Kết quả mở
        rộng mang 'extended_seconds' để số đo nội bộ tách riêng được.

        cancelled: hàm không tham số trả True khi phiên đã huỷ — kiểm trước lần
        dò bổ sung để không tốn CPU cho phiên đã bỏ.
        """
        import librosa
        from core.numba_cache import run_healing

        first = first_seconds or ToneDetector.FAST_FIRST_SECONDS
        extend = max(first, ToneDetector.FAST_EXTEND_SECONDS)
        # run_healing: cache numba hỏng thì xoá rồi nạp lại một lần
        # (xem core/numba_cache.py). Nạp một lần đủ cho cả lần dò bổ sung.
        audio_data, sr = run_healing(librosa.load, audio_path, sr=sr, mono=True,
                                     duration=extend)
        print(f"[DÒ TONE] Đã nạp {len(audio_data) / sr:.1f}giây, sr={sr}")

        head = audio_data[:int(first * sr)]
        result = ToneDetector.detect_key_from_audio(head, sr, skip_hum_detection=True)
        del head

        # Chỉ mở rộng khi thật sự có thêm audio đáng kể (bài ngắn / tải hụt thì thôi).
        has_more = len(audio_data) >= int((first + 15) * sr)
        if (result and has_more
                and result.get("confidence", 0) < ToneDetector.FAST_EXTEND_BELOW_CONFIDENCE
                and not (cancelled and cancelled())):
            print(f"[DÒ TONE] confidence {result.get('confidence', 0):.2f} < "
                  f"{ToneDetector.FAST_EXTEND_BELOW_CONFIDENCE} → phân tích thêm "
                  f"{len(audio_data) / sr:.0f}s")
            extended = ToneDetector.detect_key_from_audio(audio_data, sr, skip_hum_detection=True)
            if extended:
                extended["extended_seconds"] = round(len(audio_data) / sr, 1)
                result = extended
        del audio_data
        return result

    @staticmethod
    def detect_key_from_youtube(youtube_url, duration_limit=60, errors_out=None):
        """
        Tải audio từ YouTube và phát hiện tone
        Chỉ phân tích tối đa duration_limit giây đầu tiên

        ``errors_out``: list (tùy chọn) — khi thất bại nhận lỗi gốc (exception) để
        người gọi ghi nhật ký; hàm vẫn trả None như cũ.

        Lưu ý: truyền skip_hum_detection=True (bỏ notch hum để nhanh hơn) vì đa
        số nhạc YouTube đã master sạch hum. ĐÁNH ĐỔI cho nguồn quay điện thoại /
        livestream / cover thu tại nhà có thể dính hum 50/60Hz — xem docstring
        detect_key_from_audio. Rủi ro lệch tonic do hum là thấp-trung.
        """
        try:
            from core.scoring import ScoringEngine

            print(f"Bắt đầu dò tone từ YouTube...")
            print(f"🔗 URL: {youtube_url}")
            
            # Download audio
            scoring_engine = ScoringEngine()
            # Tải đủ cho cả lần dò bổ sung (detect_key_from_file) — một lần đi
            # mạng, không tải lại khi phải phân tích thêm.
            audio_path = scoring_engine.download_youtube_audio(
                youtube_url,
                max_seconds=max(duration_limit, ToneDetector.FAST_EXTEND_SECONDS) + 5)

            if not audio_path:
                print("[DÒ TONE] Không thể tải audio")
                if errors_out is not None and scoring_engine.last_download_error is not None:
                    errors_out.append(scoring_engine.last_download_error)
                return None

            try:
                result = ToneDetector.detect_key_from_file(
                    audio_path, sr=22050, first_seconds=duration_limit)
                try:
                    from core.memory import MemoryGuard
                    MemoryGuard.force_cleanup()
                except Exception:
                    pass
                if result:
                    result["audio_source"] = "youtube"
                return result

            finally:
                scoring_engine.cleanup_temp_file()
                
        except Exception as e:
            print(f"[DÒ TONE] Lỗi: {e}")
            import traceback
            print(traceback.format_exc())
            if errors_out is not None:
                errors_out.append(e)
            return None

    @staticmethod
    def _estimate_tuning_cents(y, sr):
        """Độ lệch tuning của y so với A4=440Hz, tính bằng cent, trong [-50, 50).

        Ước lượng ở TUNING_ESTIMATE_BINS_PER_OCTAVE (12) để không bị gấp vòng.
        Trả 0.0 nếu thất bại — cùng nghĩa "không lệch", mặc định an toàn của librosa.
        """
        import librosa
        import numpy as np

        try:
            bpo = ToneDetector.TUNING_ESTIMATE_BINS_PER_OCTAVE
            frac = float(librosa.estimate_tuning(y=y, sr=sr, bins_per_octave=bpo))
            cents = frac * 1200.0 / bpo
            return cents if np.isfinite(cents) else 0.0
        except Exception as e:
            print(f"   ⚠ Ước lượng tuning thất bại ({e}) — dùng tuning=0")
            return 0.0

    @staticmethod
    def _cents_to_chroma_bins(cents, bins_per_octave=None):
        """Đổi cent sang đơn vị tham số `tuning` của chroma_cqt (phần lẻ của 1 bin)."""
        if bins_per_octave is None:
            bins_per_octave = ToneDetector.CHROMA_BINS_PER_OCTAVE
        return cents * bins_per_octave / 1200.0

    @staticmethod
    def _estimate_tuning_bounded(audio_data, sr, bins_per_octave=36):
        """Ước lượng tuning từ một mẫu có giới hạn thay vì toàn bài.

        librosa.estimate_tuning() dựng piptrack (STFT) trên cả mảng đầu vào nên
        RAM tỉ lệ với độ dài bài — đo được 1098 MB cho bài 15 phút. Tuning lại
        là thuộc tính TOÀN CỤC và gần như bất biến trong một bản thu, nên lấy
        vài đoạn trải đều khắp bài là đủ: đo trên tín hiệu thử, mẫu 60s cho ra
        đúng cùng giá trị với toàn bài mà chỉ tốn ~73 MB.

        Trả về tham số `tuning` cho chroma_cqt ở `bins_per_octave` (phần lẻ của
        một bin CQT — có thể vượt ±0.5 vì ước lượng ở 12 bin, xem
        TUNING_ESTIMATE_BINS_PER_OCTAVE). 0.0 nếu ước lượng thất bại — cùng
        nghĩa "không lệch tuning", là mặc định an toàn của librosa.
        """
        import numpy as np

        try:
            n_excerpts = max(1, ToneDetector.TUNING_EXCERPT_COUNT)
            budget = int(ToneDetector.TUNING_SAMPLE_SECONDS * sr)
            if len(audio_data) <= budget:
                sample = audio_data
            else:
                # Trải đều các đoạn khắp bài: intro/verse/chorus/outro đều có mặt,
                # không thiên vị 60s đầu (nhiều bài mở đầu chỉ có nhạc nền).
                ex_len = max(1, budget // n_excerpts)
                offsets = np.linspace(0, len(audio_data) - ex_len, n_excerpts).astype(int)
                sample = np.concatenate([audio_data[o:o + ex_len] for o in offsets])
        except Exception as e:
            print(f"   ⚠ Ước lượng tuning thất bại ({e}) — dùng tuning=0")
            return 0.0
        cents = ToneDetector._estimate_tuning_cents(sample, sr)
        del sample
        return ToneDetector._cents_to_chroma_bins(cents, bins_per_octave)

    @staticmethod
    def _chroma_rms_blockwise(audio_data, sr, hop_length, tuning,
                              dc_offset=0.0, clip=False, want_rms=True,
                              on_block=None):
        """Tính chroma_cqt (+ rms) theo KHỐI — RAM đỉnh phẳng theo kích thước khối.

        Kết quả khớp với cách tính nguyên bài tới sai số float32 (~1e-7), nhờ
        hai điều kiện BẮT BUỘC:

        1. `tuning` phải được truyền vào tường minh. Để tuning=None thì mỗi khối
           tự ước lượng một giá trị khác nhau và chroma lệch nhau tới ~0.03.
        2. Mỗi khối được nới thêm TIMELINE_BLOCK_PAD_SECONDS ở hai bên rồi bỏ
           phần đệm đi, để frame ở rìa khối vẫn nhìn thấy audio thật hai bên
           thay vì phần đệm phản chiếu do center=True sinh ra.

        Lưới frame giữ nguyên quy ước của librosa (center=True): frame thứ i
        tâm tại mẫu i*hop_length, tổng 1 + len(y)//hop_length frame.

        dc_offset/clip: tiền xử lý áp cho từng khối thay vì nhân đôi cả mảng
        audio trong RAM. dc_offset phải là trung bình TOÀN BÀI (tính sẵn bởi
        caller) để giống hệt phép trừ trên nguyên mảng.

        on_block(done, total): gọi sau mỗi khối, để caller báo tiến độ.
        """
        import librosa
        import numpy as np
        import math

        n = len(audio_data)
        if n == 0:
            empty_rms = np.zeros(0, dtype=np.float32) if want_rms else None
            return np.zeros((12, 0), dtype=np.float32), empty_rms

        n_frames = 1 + n // hop_length
        pad_frames = int(math.ceil(
            ToneDetector.TIMELINE_BLOCK_PAD_SECONDS * sr / hop_length))
        frames_per_block = max(1, int(round(
            ToneDetector.TIMELINE_BLOCK_SECONDS * sr / hop_length)))
        total_blocks = int(math.ceil(n_frames / frames_per_block))

        chroma_parts, rms_parts = [], []
        f0 = 0
        done = 0
        while f0 < n_frames:
            f1 = min(f0 + frames_per_block, n_frames)

            # Mốc đầu khối phải là bội của hop_length thì frame của khối con mới
            # trùng lưới frame toàn bài (offset j0 dưới đây mới là số nguyên).
            start_frame = max(0, f0 - pad_frames)
            start = start_frame * hop_length
            end = min(n, (f1 - 1 + pad_frames) * hop_length + 1)

            block = np.array(audio_data[start:end], dtype=np.float32)
            if dc_offset:
                block -= dc_offset
            if clip:
                np.clip(block, -1.0, 1.0, out=block)

            chroma_blk = librosa.feature.chroma_cqt(
                y=block, sr=sr, hop_length=hop_length, tuning=tuning)
            rms_blk = (librosa.feature.rms(y=block, hop_length=hop_length)[0]
                       if want_rms else None)

            j0 = f0 - start_frame
            j1 = min(j0 + (f1 - f0), chroma_blk.shape[1])
            chroma_parts.append(np.array(chroma_blk[:, j0:j1]))
            if want_rms:
                rms_parts.append(np.array(rms_blk[j0:j1]))

            # KHÔNG gọi gc.collect() ở đây: numpy giải phóng ngay bằng đếm
            # tham chiếu khi del, còn full GC mỗi khối tốn 2s/bài 15 phút mà
            # RAM đỉnh không giảm (đo được 22MB có gc vs 22MB không gc).
            del block, chroma_blk, rms_blk

            f0 = f1
            done += 1
            if on_block:
                on_block(done, total_blocks)

        chroma = np.concatenate(chroma_parts, axis=1)
        chroma_parts.clear()
        rms = np.concatenate(rms_parts) if want_rms else None
        rms_parts.clear()
        return chroma, rms

    @staticmethod
    def detect_timeline_advanced(audio_data, sr, on_progress=None):
        """
        Dò tone tiên tiến:
        1. Dùng novelty-based segmentation để tìm đổi cấu trúc.
        2. Refine với sliding window nhỏ (±3s).
        3. Dò tone mỗi segment.
        4. Gộp segment thành VÙNG tone (_regionalize): chỉ báo đổi tone khi một
           vùng >= TIMELINE_REGION_MIN_SECONDS lệch hẳn sang bộ nốt khác.
        """
        # Không import librosa ở đây nữa: mọi lời gọi librosa của hàm này đã dời
        # vào _chroma_rms_blockwise / _estimate_tuning_bounded.
        import numpy as np
        import scipy.signal
        
        # Trần cứng phòng thủ. Caller (_tone.py) đã chặn từ lúc nạp file, nhưng
        # hàm này là public và còn được tools/batch_detect_tone.py gọi trực tiếp
        # — không để một video 2 tiếng lọt vào đây làm sập app.
        max_samples = int(ToneDetector.TIMELINE_MAX_SECONDS * sr)
        if len(audio_data) > max_samples:
            print(f"[TIMELINE] Bài dài {len(audio_data) / sr / 60:.1f} phút — "
                  f"chỉ phân tích {ToneDetector.TIMELINE_MAX_SECONDS // 60} phút đầu")
            if on_progress:
                on_progress(f"Bài quá dài — phân tích "
                            f"{ToneDetector.TIMELINE_MAX_SECONDS // 60} phút đầu...")
            audio_data = audio_data[:max_samples]

        duration = len(audio_data) / sr
        if on_progress: on_progress("Phân tích cấu trúc...")
        print("[NOVELTY] Bắt đầu phân tích cấu trúc...")

        # Ước lượng tuning MỘT LẦN cho cả hai lượt chroma bên dưới. Bắt buộc phải
        # truyền tường minh vào từng khối — xem _chroma_rms_blockwise. Tiện thể
        # bỏ luôn một lần estimate_tuning: trước đây mỗi lượt chroma_cqt tự gọi
        # một lần trên nguyên bài, và chính nó là đỉnh RAM lớn nhất của hàm này.
        tuning = ToneDetector._estimate_tuning_bounded(audio_data, sr)
        print(f"[TIMELINE] Tuning = {tuning:+.4f} bin "
              f"({tuning * 1200 / ToneDetector.CHROMA_BINS_PER_OCTAVE:+.0f} cent, mẫu giới hạn)")

        # 1. Novelty curve (dựa trên chroma) — tính theo khối, RAM phẳng.
        hop_length = int(sr / 2) # 0.5s per frame
        chroma, _ = ToneDetector._chroma_rms_blockwise(
            audio_data, sr, hop_length, tuning, want_rms=False)

        novelty = np.zeros(chroma.shape[1])
        window_frames = 10 # 5s
        for i in range(window_frames, chroma.shape[1] - window_frames):
            past = np.mean(chroma[:, i-window_frames:i], axis=1)
            future = np.mean(chroma[:, i:i+window_frames], axis=1)
            n_p = np.linalg.norm(past)
            n_f = np.linalg.norm(future)
            if n_p > 0 and n_f > 0:
                novelty[i] = 1.0 - np.dot(past, future) / (n_p * n_f)
        del chroma  # Giải phóng chroma matrix lớn
                
        peaks, _ = scipy.signal.find_peaks(novelty, prominence=0.03, distance=16) # distance = 8s
        initial_boundaries = [p * hop_length / sr for p in peaks]
        print(f"📊 [NOVELTY] Đã tìm thấy {len(initial_boundaries)} điểm thay đổi cấu trúc thô")
        
        # 2. Refine với sliding window (±3s)
        if on_progress: on_progress("Tinh chỉnh điểm chuyển...")
        refined_boundaries = []
        for b in initial_boundaries:
            start_frame = int(max(0, b - 3.0) * sr / hop_length)
            end_frame = int(min(duration, b + 3.0) * sr / hop_length)
            if start_frame < end_frame:
                local_nov = novelty[start_frame:end_frame]
                local_max_idx = np.argmax(local_nov)
                refined_b = max(0, b - 3.0) + local_max_idx * hop_length / sr
                refined_boundaries.append(refined_b)
            else:
                refined_boundaries.append(b)
                
        boundaries = [0.0] + refined_boundaries + [duration]
        boundaries = sorted(list(set(boundaries)))
        print(f"🎯 [NOVELTY] Refined {len(refined_boundaries)} điểm chuyển cấu trúc")
        
        # 3. Detect tone cho mỗi phân đoạn bằng cách slice từ chroma tổng
        # Tính CQT cho toàn bộ track một lần duy nhất (nhanh gấp nhiều lần gọi lại hàm detect)
        print("[TIMELINE] Bắt đầu tính ma trận CQT tổng...")
        if on_progress: on_progress("Tính ma trận CQT...")

        # Xoá mean và giới hạn độ lớn. KHÔNG mutate in-place mảng audio_data của
        # caller (caller có thể còn dùng tiếp) — nhưng cũng KHÔNG nhân đôi cả
        # mảng nữa: mean tính một lần ở đây rồi áp cho từng khối bên trong
        # _chroma_rms_blockwise, cho kết quả y hệt mà không tốn thêm RAM.
        dc_offset = float(np.mean(audio_data))

        # Use fine-grained hop_length for the actual detection
        detect_hop_length = 512

        def _cqt_progress(done, total):
            if on_progress:
                on_progress(f"Tính ma trận CQT {done}/{total}...")

        full_chroma_cqt, full_rms = ToneDetector._chroma_rms_blockwise(
            audio_data, sr, detect_hop_length, tuning,
            dc_offset=dc_offset, clip=True, want_rms=True,
            on_block=_cqt_progress)

        segments = []
        for i in range(len(boundaries) - 1):
            start = boundaries[i]
            end = boundaries[i+1]
            
            if on_progress:
                pct = int((i + 1) / (len(boundaries) - 1) * 100)
                on_progress(f"Dò tone {i+1}/{len(boundaries)-1} ({pct}%)...")
                
            start_frame = int(start * sr / detect_hop_length)
            end_frame = int(end * sr / detect_hop_length)
            
            if (end - start) < 2.0 or start_frame >= end_frame:
                segments.append({'start': start, 'end': end, 'key_display': 'Silence', 'result': None})
                continue
                
            # Extract slice from precomputed RMS to check volume
            rms_slice = full_rms[start_frame:end_frame]
            if np.mean(rms_slice) < ToneDetector.SILENCE_RMS_THRESHOLD:
                segments.append({'start': start, 'end': end, 'key_display': 'Silence', 'result': None})
                continue
                
            # Extract slice from precomputed CQT
            chroma_slice = full_chroma_cqt[:, start_frame:end_frame]
            
            # Energy weighted average (xem ĐÁNH ĐỔI energy-weight ở
            # detect_key_from_audio: giữ rms tuyến tính, không winsorize, để
            # đồng nhất hành vi giữa single-shot và timeline).
            rms_sum = np.sum(rms_slice)
            if rms_sum > 0:
                chroma_avg = np.average(chroma_slice, axis=1, weights=rms_slice / rms_sum)
            else:
                chroma_avg = np.mean(chroma_slice, axis=1)
                
            # Normalize
            cs = np.sum(chroma_avg)
            if cs > 0:
                chroma_avg = chroma_avg / cs
                
            cqt_normalized = chroma_avg.copy()
            
            # Re-use the extracted correlation logic
            # cleanup=False: hàm này tự dọn RAM một lần ở cuối, không dọn sau mỗi đoạn.
            result = ToneDetector._detect_key_from_chroma_impl(chroma_avg, cqt_normalized,
                                                                cleanup=False)
            
            if result:
                segments.append({
                    'start': start, 'end': end,
                    'key_display': result['key_display'],
                    'result': result,
                    'start_frame': start_frame, 'end_frame': end_frame,
                    'chroma': chroma_avg,
                })
                print(f"   🎵 Phân đoạn [{start:.1f}s - {end:.1f}s]: {result['key_display']} (conf={result.get('confidence',0):.3f})")
            else:
                segments.append({'start': start, 'end': end, 'key_display': 'Unknown', 'result': None})
                
        # 4. Gộp các đoạn thành VÙNG tone — mỗi vùng neo vào tone tính từ chroma
        #    tích luỹ của chính nó (xem _regionalize và TIMELINE_REGION_*).
        regions = ToneDetector._regionalize(segments, full_chroma_cqt, full_rms)
        del full_chroma_cqt, full_rms  # Giải phóng biến lớn

        timeline_entries = []
        for idx, reg in enumerate(regions):
            res = reg['result']
            if not res:
                continue
            if timeline_entries and timeline_entries[-1]['key_display'] == res['key_display']:
                continue
            # Mốc đầu luôn ở 0s: đoạn im lặng/intro trước vùng đầu thuộc về vùng đó.
            t = 0.0 if not timeline_entries else float(reg['start'])
            timeline_entries.append({
                'time': t,
                'key_display': res['key_display'],
                'key_index': res['key_index'],
                'scale': res['scale'],
                'confidence': float(res.get('confidence', 0.8)),
                # Số đo nội bộ (tone_share diag) — tuning là của cả bài.
                'tuning_cents': round(tuning * 1200 / ToneDetector.CHROMA_BINS_PER_OCTAVE, 1),
            })
            print(f"[TIMELINE] {t:.1f}s -> {res['key_display']} "
                  f"(vùng {reg['start']:.0f}–{reg['end']:.0f}s)")
            
        # Giải phóng RAM sau khi dò toàn bộ timeline
        try:
            from core.memory import MemoryGuard
            MemoryGuard.force_cleanup()
        except Exception:
            pass
        
        return timeline_entries
        
    @staticmethod
    def _weighted_key_corr(chroma, key_index, scale):
        """Tương quan có trọng số (Aarden/Temperley/KS) của chroma với MỘT tone."""
        import numpy as np
        W = ToneDetector.PROFILE_WEIGHTS
        if scale == "Minor":
            profiles = (ToneDetector.AARDEN_MINOR, ToneDetector.TEMP_MINOR, ToneDetector.KS_MINOR)
        else:
            profiles = (ToneDetector.AARDEN_MAJOR, ToneDetector.TEMP_MAJOR, ToneDetector.KS_MAJOR)
        rotated = np.roll(np.asarray(chroma, dtype=float), -int(key_index))
        return sum(w * ToneDetector._safe_corrcoef(rotated, p)
                   for w, p in zip((W['aarden'], W['temperley'], W['ks']), profiles))

    @staticmethod
    def _regionalize(segments, chroma, rms):
        """Gộp các đoạn đã dò thành VÙNG tone.

        Mỗi vùng neo vào tone tính từ chroma TÍCH LUỸ của cả vùng (chứ không phải
        tone của từng đoạn 10–20s — đó thực chất là hợp âm). Đoạn kế tiếp:
          - cùng họ với tone vùng (chung >= TIMELINE_FAMILY_OVERLAP nốt), hoặc
          - không thắng tone vùng >= TIMELINE_REGION_MIN_GAIN trên chroma của nó
        → bị hút vào vùng. Ngược lại là ỨNG VIÊN vùng mới: kéo dài qua các đoạn
        tiếp theo cùng họ với nó; chỉ thành vùng mới nếu dài >=
        TIMELINE_REGION_MIN_SECONDS. Cuối cùng vùng nào (kể cả intro) ngắn hơn
        ngưỡng thì nhập vào vùng kề, rồi dò lại tone từng vùng trên chroma của nó.

        segments: list dict của detect_timeline_advanced; đoạn có 'result' mới
        mang 'start_frame'/'end_frame'/'chroma'. Trả list
        {'start', 'end', 'result'} theo thứ tự thời gian.
        """
        import numpy as np

        valid = [s for s in segments if s.get('result') and 'chroma' in s]
        if not valid:
            return []

        n_frames = chroma.shape[1]

        def region_result(fa, fb):
            fb = min(fb, n_frames)
            c, r = chroma[:, fa:fb], rms[fa:fb]
            total = float(np.sum(r))
            v = np.average(c, axis=1, weights=r / total) if total > 0 else np.mean(c, axis=1)
            s = float(np.sum(v))
            if s > 0:
                v = v / s
            return ToneDetector._detect_key_from_chroma_impl(v, v.copy(), verbose=False, cleanup=False)

        def same_family(k1, k2):
            return ToneDetector._note_overlap(k1[0], k1[1], k2[0], k2[1]) >= \
                ToneDetector.TIMELINE_FAMILY_OVERLAP

        def key_of(seg):
            return (seg['result']['key_index'], seg['result']['scale'])

        min_len = ToneDetector.TIMELINE_REGION_MIN_SECONDS
        min_gain = ToneDetector.TIMELINE_REGION_MIN_GAIN

        regions = []
        i = 0
        while i < len(valid):
            seg = valid[i]
            if not regions:
                regions.append({'start': seg['start'], 'end': seg['end'],
                                'fa': seg['start_frame'], 'fb': seg['end_frame']})
                i += 1
                continue
            reg = regions[-1]
            rres = region_result(reg['fa'], reg['fb'])
            k = key_of(seg)
            rkey = (rres['key_index'], rres['scale']) if rres else k
            gain = (ToneDetector._weighted_key_corr(seg['chroma'], *k)
                    - ToneDetector._weighted_key_corr(seg['chroma'], *rkey))
            if same_family(k, rkey) or gain < min_gain:
                reg['end'], reg['fb'] = seg['end'], seg['end_frame']
                i += 1
                continue
            j = i + 1
            while j < len(valid) and same_family(key_of(valid[j]), k):
                j += 1
            last = valid[j - 1]
            if last['end'] - seg['start'] >= min_len:
                regions.append({'start': seg['start'], 'end': last['end'],
                                'fa': seg['start_frame'], 'fb': last['end_frame']})
            else:
                reg['end'], reg['fb'] = last['end'], last['end_frame']
            i = j

        # Vùng ngắn (kể cả vùng đầu = intro) nhập vào vùng kề sau, vùng cuối
        # thì nhập vào vùng kề trước.
        merged = True
        while merged and len(regions) > 1:
            merged = False
            for idx, reg in enumerate(regions):
                if reg['end'] - reg['start'] < min_len:
                    if idx + 1 < len(regions):
                        nxt = regions[idx + 1]
                        nxt['start'], nxt['fa'] = reg['start'], reg['fa']
                    else:
                        prv = regions[idx - 1]
                        prv['end'], prv['fb'] = reg['end'], reg['fb']
                    regions.pop(idx)
                    merged = True
                    break

        return [{'start': reg['start'], 'end': reg['end'],
                 'result': region_result(reg['fa'], reg['fb'])} for reg in regions]

    @staticmethod
    def key_index_to_midi(key_index):
        """
        Chuyển key index (0-11) sang MIDI CC value cho plugin Auto-Tune.
        NGUỒN THẬT: AppConfig.get_key_midi_map() (key_midi_map trong app_config),
        fallback hằng KEY_MIDI_MAP của class (đã đồng bộ với config) nếu import lỗi.
        Trước đây dùng công thức tuyến tính key_index*127/11 — MÂU THUẪN với map
        thật (VD C#: tuyến tính=11 vs config=11 trùng tình cờ, nhưng D: 23 vs 11...).
        index ngoài [0,11] → clamp về biên.
        """
        idx = min(11, max(0, int(key_index)))
        note = ToneDetector.MAJOR_KEY_NAMES[idx]  # tên nốt sharp: C, C#, D, ...
        try:
            from core.config import AppConfig
            midi_map = AppConfig.get_key_midi_map()
        except Exception:
            midi_map = ToneDetector.KEY_MIDI_MAP
        return int(midi_map.get(note, ToneDetector.KEY_MIDI_MAP.get(note, 0)))

    @staticmethod
    def scale_to_midi(scale):
        """
        Chuyển scale type sang MIDI CC value cho plugin Auto-Tune.
        NGUỒN THẬT: AppConfig.get_scale_midi_map() → Major=13, Minor=18
        (fallback hằng SCALE_MIDI_MAP của class). Trước đây trả 0/127 — SAI so với
        plugin (knob% thật: Major 13, Minor 18). Scale lạ → mặc định như Major.
        """
        try:
            from core.config import AppConfig
            scale_map = AppConfig.get_scale_midi_map()
        except Exception:
            scale_map = ToneDetector.SCALE_MIDI_MAP
        default_major = scale_map.get("Major", ToneDetector.SCALE_MIDI_MAP["Major"])
        return int(scale_map.get(scale, default_major))
