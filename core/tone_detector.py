"""
Quang Lưu Studio — Tone Detector
Class: ToneDetector
Pipeline: HPSS → Chroma CQT (energy-weighted) → Weighted Multi-profile (Aarden/Temperley/KS) → Disambiguation
"""
import gc
import ctypes


class ToneDetector:
    """
    Dò Tone bài hát - Phát hiện key/tonality từ audio
    Pipeline: HPSS → Chroma CQT (energy-weighted) → Weighted Multi-profile (Aarden/Temperley/KS) → Disambiguation
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
    
    # Voting window: số segments cần đồng thuận trước khi chuyển tone
    VOTING_WINDOW = 3
    
    # Bảng ánh xạ Key → MIDI CC value (từ knob% thực tế trên plugin Auto-Tune)
    # Plugin nhận 0-127 → hiển thị 0-100%. Công thức: round(knob% × 127/100)
    KEY_MIDI_MAP = {
        "C": 0,   "C#": 11,  "Db": 11,  "D": 23,  "D#": 34,  "Eb": 34,
        "E": 46,  "F": 57,   "F#": 69,  "G": 80,
        "G#": 92, "Ab": 92,  "A": 103,  "A#": 115, "Bb": 115, "B": 127,
    }
    # Scale → MIDI CC value (từ knob% thực tế trên plugin)
    SCALE_MIDI_MAP = {
        "Major": 13,
        "Minor": 18,
    }
    
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
            major_corr = float(np.corrcoef(rotated, major_profile)[0, 1])
            uid_major = f"{ToneDetector.MAJOR_KEY_NAMES[i]}_Major"
            results[uid_major] = {
                "key": ToneDetector.MAJOR_KEY_NAMES[i],
                "scale": "Major",
                "correlation": major_corr,
                "key_index": i
            }
            minor_corr = float(np.corrcoef(rotated, minor_profile)[0, 1])
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
    def _are_closely_related(key1_idx, scale1, key2_idx, scale2):
        """
        Kiểm tra 2 key có closely related không (chia sẻ >= 6/7 nốt).
        Bao gồm: relative keys, parallel keys, và các key lân cận trên circle of fifths.
        VD: Eb Major ↔ Fm, C Major ↔ Am, C Major ↔ Dm, G Major ↔ Em, ...
        """
        # Tạo scale degrees cho mỗi key
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
        
        overlap = len(notes1 & notes2)
        return overlap >= 6  # Chia sẻ ít nhất 6 nốt

    @staticmethod
    def detect_key_from_audio(audio_data, sample_rate, accumulated_chroma=None):
        """
        Phát hiện tone/key của bài hát từ audio data.
        Pipeline: Robust Preprocessing → CQT chroma (energy-weighted) → Weighted Multi-profile → Disambiguation
        """
        try:
            import librosa
            import numpy as np
            
            audio_data = np.nan_to_num(audio_data, nan=0.0, posinf=0.0, neginf=0.0)
            
            # === BƯỚC 0: Robust Preprocessing ===
            
            # Stage 1: Clip extreme outliers (corrupted samples, VD: max=1.8e29)
            audio_data = np.clip(audio_data, -1e6, 1e6)
            
            # Stage 2: Percentile-based normalize (tránh 1 sample lỗi phá hủy signal)
            p999 = np.percentile(np.abs(audio_data), 99.9)
            if p999 > 0:
                audio_data = audio_data / p999
            audio_data = np.clip(audio_data, -1.0, 1.0)
            
            # Stage 3: DC offset removal
            audio_data = audio_data - np.mean(audio_data)
            
            # Stage 4: Quality validation
            rms_check = np.sqrt(np.mean(audio_data ** 2))
            if rms_check < 0.001:
                print("   ⚠️ Audio quá nhỏ hoặc im lặng, bỏ qua")
                return None
            
            # Stage 5: Adaptive hum removal (PYIN detect → notch filter)
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
                        print(f"   ✅ Notch: loại hum {hum_freq:.0f}Hz ({hum_ratio*100:.0f}%)")
                del valid_f0
            except Exception:
                pass
            
            print(f"   ✅ Preprocessing OK (p99.9={p999:.4f}, rms={rms_check:.4f})")
            print("🎵 [DÒ TONE] Pipeline: CQT → Weighted Multi-profile...")
            
            # === BƯỚC 1: Chroma CQT (energy-weighted) ===
            chroma_cqt = librosa.feature.chroma_cqt(y=audio_data, sr=sample_rate)
            rms = librosa.feature.rms(y=audio_data)[0]
            min_frames = min(len(rms), chroma_cqt.shape[1])
            rms = rms[:min_frames]
            rms_sum = np.sum(rms)
            if rms_sum > 0:
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
            
            print(f"   ✅ Chroma CQT (energy-weighted)")
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
            
            # Thu thập candidates closely-related với best
            family = [best]
            for r in all_results[1:7]:
                if ToneDetector._are_closely_related(
                    best["key_index"], best["scale"],
                    r["key_index"], r["scale"]
                ):
                    family.append(r)
            
            if len(family) >= 2:
                print(f"   🔍 Key family ({len(family)} candidates):")
                
                best_candidate = None
                best_score = -1
                family_scores = []  # Lưu combined score cho tiebreaker
                
                for r in family:
                    # Tonic + 5th + 3rd strength
                    tonic = cqt_normalized[r["key_index"]]
                    fifth = cqt_normalized[(r["key_index"] + 7) % 12]
                    if r["scale"] == "Minor":
                        third = cqt_normalized[(r["key_index"] + 3) % 12]
                    else:
                        third = cqt_normalized[(r["key_index"] + 4) % 12]
                    
                    tonal_strength = tonic + fifth * 0.7 + third * 0.5
                    
                    # Combined: profile correlation (chính) + tonal strength (phụ)
                    combined = r["correlation"] * 0.85 + tonal_strength * 0.15
                    family_scores.append((r, combined))
                    
                    print(f"      {r['key']:4s}: corr={r['correlation']:.3f} T={tonic:.3f} 5={fifth:.3f} 3={third:.3f} → {combined:.4f}")
                    
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
                            print(f"   🎯 Tiebreaker: {top1['key']} ({top1_common:.1f}) → {top2['key']} ({top2_common:.1f})")
                

                
                if best_candidate and best_candidate["key"] != best["key"]:
                    print(f"   🔄 Family winner: {best['key']} → {best_candidate['key']}")
                else:
                    print(f"   ✅ Giữ {best['key']}")
                best = best_candidate or best
            
            best_key = best["key_index"]
            best_scale = best["scale"]
            best_corr = best["correlation"]
            
            if best_scale == "Major":
                key_display = ToneDetector.MAJOR_KEY_NAMES[best_key]
            else:
                key_display = ToneDetector.MINOR_KEY_NAMES[best_key]
            
            print(f"🎯 [DÒ TONE] Kết quả: {key_display} (confidence: {best_corr:.4f})")
            print(f"   📊 KS={best.get('ks_corr',0):.4f}  T={best.get('temp_corr',0):.4f}  A={best.get('aarden_corr',0):.4f}")
            print(f"🎯 [DÒ TONE] Top 5:")
            for r in all_results[:5]:
                print(f"   {r['key']}: {r['correlation']:.4f}")
            
            # Giải phóng mảng trung gian trước khi return
            del chroma_avg, cqt_normalized, chroma_for_analysis, all_results
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
            }
            
        except Exception as e:
            print(f"❌ [DÒ TONE] Lỗi phân tích: {e}")
            import traceback
            print(traceback.format_exc())
            return None
    
    @staticmethod
    def detect_key_from_system_audio(duration=10, sample_rate=48000, on_progress=None):
        """
        Thu âm loopback từ hệ thống (bắt âm thanh đang phát trên loa)
        và phát hiện tone bài hát. Không cần tải từ YouTube.
        
        Sử dụng WASAPI Loopback (Windows) qua thư viện pyaudiowpatch.
        """
        import numpy as np
        
        # Import pyaudiowpatch (thay thế soundcard)
        try:
            import pyaudiowpatch as pyaudio
        except ImportError:
            print("❌ [DÒ TONE] Thư viện 'pyaudiowpatch' chưa được cài đặt.")
            print("   Chạy: pip install pyaudiowpatch")
            return None
        
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
            print("=" * 60)
            print(f"🎤 [DÒ TONE] Thu âm loopback từ hệ thống ({duration}s)...")
            
            pa = pyaudio.PyAudio()
            
            # Tìm WASAPI loopback device
            wasapi_info = None
            for i in range(pa.get_host_api_count()):
                info = pa.get_host_api_info_by_index(i)
                if "wasapi" in info.get("name", "").lower():
                    wasapi_info = info
                    break
            
            if not wasapi_info:
                print("❌ [DÒ TONE] Không tìm thấy WASAPI host API!")
                return None
            
            loopback_dev = None
            for i in range(pa.get_device_count()):
                dev = pa.get_device_info_by_index(i)
                if dev.get("isLoopbackDevice", False):
                    if dev.get("hostApi") == wasapi_info["index"]:
                        loopback_dev = dev
                        break
            
            if not loopback_dev:
                print("❌ [DÒ TONE] Không tìm thấy thiết bị loopback!")
                return None
            
            device_sr = int(loopback_dev["defaultSampleRate"])
            chunk_size = 1024
            
            print(f"✅ [DÒ TONE] Sử dụng loopback: {loopback_dev['name']}")
            print(f"⏺️  [DÒ TONE] Đang thu âm {duration} giây...")
            
            stream = pa.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=device_sr,
                input=True,
                input_device_index=loopback_dev["index"],
                frames_per_buffer=chunk_size
            )
            
            # Thu âm theo từng giây để cập nhật progress
            audio_chunks = []
            for sec in range(duration):
                frames_needed = device_sr
                frames_read = 0
                while frames_read < frames_needed:
                    data = stream.read(chunk_size, exception_on_overflow=False)
                    chunk_np = np.frombuffer(data, dtype=np.float32)
                    audio_chunks.append(chunk_np)
                    frames_read += len(chunk_np)
                
                remaining = duration - sec - 1
                if on_progress:
                    try:
                        on_progress(remaining)
                    except Exception:
                        pass
                
                print(f"   ⏱️  Còn {remaining}s...")
            
            # Ghép các chunks
            audio_data = np.concatenate(audio_chunks)
            del audio_chunks  # Giải phóng list chunks ngay lập tức
            audio_data = np.nan_to_num(audio_data, nan=0.0, posinf=0.0, neginf=0.0)
            
            actual_duration = len(audio_data) / device_sr
            print(f"✅ [DÒ TONE] Đã thu: {actual_duration:.1f}s, {len(audio_data)} samples")
            
            # Kiểm tra âm thanh
            rms = np.sqrt(np.mean(audio_data ** 2))
            print(f"📊 [DÒ TONE] RMS level: {rms:.6f}")
            
            if rms < 0.001:
                print("⚠️ [DÒ TONE] Không phát hiện âm thanh! Hãy đảm bảo đang phát nhạc.")
                return None
            
            
            # Phân tích key
            result = ToneDetector.detect_key_from_audio(audio_data, device_sr)
            del audio_data  # Giải phóng audio data ngay sau khi dò tone
            try:
                from core.memory import MemoryGuard
                MemoryGuard.force_cleanup()
            except Exception:
                pass
            return result
            
        except Exception as e:
            print(f"❌ [DÒ TONE] Lỗi thu âm: {e}")
            import traceback
            print(traceback.format_exc())
            return None
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
    def detect_key_from_youtube(youtube_url, duration_limit=60):
        """
        Tải audio từ YouTube và phát hiện tone
        Chỉ phân tích tối đa duration_limit giây đầu tiên
        """
        try:
            import librosa
            from core.scoring import ScoringEngine
            
            print("=" * 60)
            print(f"🎵 [DÒ TONE] Bắt đầu dò tone từ YouTube...")
            print(f"🔗 URL: {youtube_url}")
            
            # Download audio
            scoring_engine = ScoringEngine()
            audio_path = scoring_engine.download_youtube_audio(youtube_url)
            
            if not audio_path:
                print("❌ [DÒ TONE] Không thể tải audio")
                return None
            
            try:
                # Load audio (giới hạn thời gian để tăng tốc)
                print(f"📂 [DÒ TONE] Loading audio (max {duration_limit}s)...")
                audio_data, sr = librosa.load(
                    audio_path,
                    sr=22050,
                    mono=True,
                    duration=duration_limit
                )
                
                actual_duration = len(audio_data) / sr
                print(f"✅ [DÒ TONE] Loaded: {actual_duration:.1f}s, sr={sr}")
                
                # Detect key
                result = ToneDetector.detect_key_from_audio(audio_data, sr)
                del audio_data  # Giải phóng audio data ngay sau khi dò tone
                try:
                    from core.memory import MemoryGuard
                    MemoryGuard.force_cleanup()
                except Exception:
                    pass
                return result
                
            finally:
                scoring_engine.cleanup_temp_file()
                
        except Exception as e:
            print(f"❌ [DÒ TONE] Lỗi: {e}")
            import traceback
            print(traceback.format_exc())
            return None
    
    @staticmethod
    def detect_timeline_advanced(audio_data, sr, on_progress=None):
        """
        Dò tone tiên tiến:
        1. Dùng novelty-based segmentation để tìm đổi cấu trúc.
        2. Refine với sliding window nhỏ (±3s).
        3. Dò tone mỗi segment.
        4. Merge segment cùng key.
        5. Filter chuyển tone ngắn (<8s).
        """
        import librosa
        import numpy as np
        import scipy.signal
        
        duration = len(audio_data) / sr
        if on_progress: on_progress("Đang phân tích cấu trúc bài hát (novelty curve)...")
        print("🔍 [NOVELTY] Bắt đầu phân tích cấu trúc...")
        
        # 1. Novelty curve (dựa trên chroma)
        hop_length = int(sr / 2) # 0.5s per frame
        chroma = librosa.feature.chroma_cqt(y=audio_data, sr=sr, hop_length=hop_length)
        
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
        if on_progress: on_progress("Đang tinh chỉnh các điểm chuyển đoạn...")
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
        
        # 3. Detect tone cho mỗi phân đoạn
        segments = []
        for i in range(len(boundaries) - 1):
            start = boundaries[i]
            end = boundaries[i+1]
            
            if on_progress:
                pct = int((i + 1) / (len(boundaries) - 1) * 100)
                on_progress(f"Dò tone phân đoạn {i+1}/{len(boundaries)-1} ({pct}%)...")
                
            seg_audio = audio_data[int(start*sr):int(end*sr)]
            if len(seg_audio) < sr * 2:
                continue
                
            rms = np.sqrt(np.mean(seg_audio ** 2))
            if rms < 0.005:
                del seg_audio  # Giải phóng segment audio
                segments.append({'start': start, 'end': end, 'key_display': 'Silence', 'result': None})
                continue
                
            result = ToneDetector.detect_key_from_audio(seg_audio, sr)
            del seg_audio  # Giải phóng segment audio ngay sau khi dò tone
            if result:
                segments.append({
                    'start': start, 'end': end,
                    'key_display': result['key_display'],
                    'result': result
                })
                print(f"   🎵 Phân đoạn [{start:.1f}s - {end:.1f}s]: {result['key_display']} (conf={result.get('confidence',0):.3f})")
            else:
                segments.append({'start': start, 'end': end, 'key_display': 'Unknown', 'result': None})
                
        # 4. Merge adjacent segments (bỏ Silence/Unknown)
        merged_segments = []
        for seg in segments:
            if not merged_segments:
                merged_segments.append(seg)
            else:
                last_seg = merged_segments[-1]
                if seg['key_display'] in ['Silence', 'Unknown']:
                    last_seg['end'] = seg['end']
                elif last_seg['key_display'] in ['Silence', 'Unknown']:
                    last_seg['key_display'] = seg['key_display']
                    last_seg['result'] = seg['result']
                    last_seg['end'] = seg['end']
                elif last_seg['key_display'] == seg['key_display']:
                    last_seg['end'] = seg['end']
                    if seg['result'] and last_seg['result']:
                        if seg['result'].get('confidence',0) > last_seg['result'].get('confidence',0):
                            last_seg['result'] = seg['result']
                else:
                    merged_segments.append(seg)
                    
        # 5. Filter short segments (<8s) (Loc Nhiễu)
        MIN_DURATION = 8.0
        filtered_segments = []
        for seg in merged_segments:
            seg_dur = seg['end'] - seg['start']
            if seg_dur < MIN_DURATION:
                if not filtered_segments:
                    filtered_segments.append(seg)
                else:
                    filtered_segments[-1]['end'] = seg['end']
                    print(f"   ✂️ Bỏ qua đoạn chuyển nhiễu ({seg_dur:.1f}s), gộp vào {filtered_segments[-1]['key_display']}")
            else:
                if filtered_segments and filtered_segments[-1]['key_display'] == seg['key_display']:
                    filtered_segments[-1]['end'] = seg['end']
                else:
                    filtered_segments.append(seg)
                    
        # Final pass merge
        final_segments = []
        for seg in filtered_segments:
            if not final_segments:
                final_segments.append(seg)
            elif final_segments[-1]['key_display'] == seg['key_display']:
                final_segments[-1]['end'] = seg['end']
            else:
                final_segments.append(seg)
                
        # Tạo kết quả cuối cùng
        timeline_entries = []
        for seg in final_segments:
            if seg['result'] and seg['key_display'] not in ['Silence', 'Unknown']:
                entry = {
                    'time': float(seg['start']),
                    'key_display': seg['result']['key_display'],
                    'key_index': seg['result']['key_index'],
                    'scale': seg['result']['scale'],
                    'confidence': float(seg['result'].get('confidence', 0.8))
                }
                timeline_entries.append(entry)
                print(f"✅ [TIMELINE] {seg['start']:.1f}s → {seg['key_display']}")
                
        # Xử lý case track toàn bị Silent/ngắn
        if not timeline_entries and final_segments and final_segments[0]['result']:
            seg = final_segments[0]
            timeline_entries.append({
                'time': 0.0,
                'key_display': seg['result']['key_display'],
                'key_index': seg['result']['key_index'],
                'scale': seg['result']['scale'],
                'confidence': float(seg['result'].get('confidence', 0.8))
            })
            
        # Giải phóng RAM sau khi dò toàn bộ timeline
        try:
            from core.memory import MemoryGuard
            MemoryGuard.force_cleanup()
        except Exception:
            pass
        
        return timeline_entries
        
    @staticmethod
    def key_index_to_midi(key_index):
        """Chuyển key index (0-11) sang MIDI CC value (0-127)"""
        return min(127, max(0, int(key_index * 127 / 11)))
    
    @staticmethod
    def scale_to_midi(scale):
        """Chuyển scale type sang MIDI CC value (0=Major, 127=Minor)"""
        return 127 if scale == "Minor" else 0
