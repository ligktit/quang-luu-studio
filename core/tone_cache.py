"""
Quang Lưu Studio — Tone Cache & Manual Timeline
Classes: ToneCacheManager, ManualToneTimeline
"""
import os
import json
import time
import re
import errno
import threading
import contextlib

from core.utils import extract_video_id, atomic_write_json, song_match_key
from core.config import MANUAL_TIMELINES_FILE, TONE_CACHE_FILE

# Lock bảo vệ chu trình read-modify-write trên các file JSON cache TRONG 1 process
# (threading.Lock). Để chống lost-update GIỮA CÁC TIẾN TRÌNH (vd app + tools/
# batch_detect_tone.py chạy song song), ta lồng thêm file-lock liên tiến trình
# bên ngoài threading.Lock (xem _interprocess_lock).
_cache_lock = threading.Lock()
_timeline_lock = threading.Lock()

# Cấu hình file-lock liên tiến trình
_LOCK_TIMEOUT = 5.0       # giây — tối đa chờ lấy lock trước khi fallback ghi thẳng
_LOCK_POLL = 0.05         # giây — khoảng giữa các lần thử
_LOCK_STALE_AGE = 30.0    # giây — lockfile cũ hơn mức này coi là mồ côi → cướp


@contextlib.contextmanager
def _interprocess_lock(data_path):
    """Khóa LIÊN TIẾN TRÌNH quanh chu trình read-modify-write của 1 file JSON.

    Cơ chế: tạo file ``<data_path>.lock`` bằng O_CREAT|O_EXCL (atomic trên cả
    Windows lẫn POSIX). Nếu file đã tồn tại → process khác đang giữ lock, retry
    ngắn (poll) tới ``_LOCK_TIMEOUT``.

    An toàn / không treo app:
      * Lockfile mồ côi (process giữ lock bị crash, không nhả): nếu file cũ hơn
        ``_LOCK_STALE_AGE`` thì coi là stale và cướp (xóa) — tránh deadlock vĩnh
        viễn.
      * Hết timeout vẫn không lấy được: KHÔNG raise, KHÔNG treo — vẫn cho caller
        ghi (yield) nhưng log cảnh báo. Bảo toàn hành vi "luôn ghi được".
      * Nền không hỗ trợ (thư mục read-only, lỗi OS lạ...): nuốt lỗi, yield để
        ghi vẫn chạy.

    LUÔN nhả lock trong finally (xóa lockfile nếu chính ta đã tạo).
    """
    lock_path = "{}.lock".format(data_path)
    acquired = False
    deadline = time.time() + _LOCK_TIMEOUT
    try:
        lock_dir = os.path.dirname(lock_path)
        if lock_dir and not os.path.isdir(lock_dir):
            try:
                os.makedirs(lock_dir, exist_ok=True)
            except OSError:
                pass

        while True:
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    os.write(fd, str(os.getpid()).encode("ascii", "ignore"))
                finally:
                    os.close(fd)
                acquired = True
                break
            except FileExistsError:
                # Lock đang bị giữ — kiểm tra mồ côi (stale) rồi retry.
                try:
                    age = time.time() - os.path.getmtime(lock_path)
                    if age > _LOCK_STALE_AGE:
                        # Lockfile quá cũ: process giữ nó có thể đã chết. Cướp.
                        os.remove(lock_path)
                        print(
                            "[CẢNH BÁO] Lockfile mồ côi {} (tuổi {:.0f}s) — đã "
                            "xóa và thử lại.".format(lock_path, age)
                        )
                        continue
                except OSError:
                    pass
                if time.time() >= deadline:
                    print(
                        "[CẢNH BÁO] Không lấy được file-lock {} sau {:.0f}s — "
                        "ghi không có khóa liên tiến trình (có thể chạy song "
                        "song). Dữ liệu trong 1 process vẫn an toàn.".format(
                            lock_path, _LOCK_TIMEOUT
                        )
                    )
                    break
                time.sleep(_LOCK_POLL)
            except OSError as e:
                # Nền không hỗ trợ O_EXCL / thư mục read-only / lỗi lạ: đừng vỡ.
                print(
                    "[CẢNH BÁO] Không tạo được file-lock {} ({}) — bỏ qua khóa "
                    "liên tiến trình.".format(lock_path, e)
                )
                break

        yield acquired
    finally:
        if acquired:
            try:
                os.remove(lock_path)
            except OSError as e:
                if getattr(e, "errno", None) != errno.ENOENT:
                    print("[CẢNH BÁO] Không xóa được lockfile {}: {}".format(lock_path, e))


def _backup_corrupt_file(path, err):
    """Sao lưu file JSON hỏng sang <path>.corrupt-<timestamp> trước khi caller
    trả {} — tránh để atomic_write kế tiếp GHI ĐÈ lên dữ liệu còn cứu được.

    Best-effort: nếu ngay cả việc sao lưu cũng thất bại thì chỉ log, không raise
    (để luồng đọc vẫn trả {} và app không sập).
    """
    backup_path = "{}.corrupt-{}".format(path, int(time.time()))
    try:
        os.replace(path, backup_path)
        print(
            "[CẢNH BÁO] File JSON hỏng: {} ({}). Đã sao lưu sang {} — "
            "dữ liệu KHÔNG bị ghi đè, có thể khôi phục thủ công.".format(
                path, err, backup_path
            )
        )
    except OSError as move_err:
        print(
            "[CẢNH BÁO] File JSON hỏng: {} ({}). Sao lưu thất bại ({}) — "
            "trả về rỗng.".format(path, err, move_err)
        )


class ToneCacheManager:
    """Quản lý cache kết quả dò tone (auto) — tránh dò lại bài đã biết.

    Khóa lưu trữ dùng song_match_key (extract_video_id or url.strip()) để MỌI
    nguồn (YouTube, file local, link /live/, loopback...) đều cache được, không
    chỉ riêng YouTube URL chuẩn. Vẫn đọc được entry cũ key theo video_id thuần.
    """

    CACHE_FILE = TONE_CACHE_FILE
    CACHE_TTL_DAYS = 30  # Hết hạn sau 30 ngày

    @staticmethod
    def _load_cache():
        if os.path.exists(ToneCacheManager.CACHE_FILE):
            try:
                with open(ToneCacheManager.CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as e:
                # File hỏng: sao lưu trước rồi mới trả {} — KHÔNG để save kế
                # tiếp load {} rồi atomic_write đè mất dữ liệu trong im lặng.
                _backup_corrupt_file(ToneCacheManager.CACHE_FILE, e)
                return {}
            except OSError as e:
                # Lỗi đọc khác (quyền, khoá file...): log, trả {} nhưng KHÔNG
                # sao lưu/di chuyển vì file có thể vẫn nguyên vẹn.
                print(f"[CẢNH BÁO] Không đọc được tone cache {ToneCacheManager.CACHE_FILE}: {e}")
                return {}
        return {}

    @staticmethod
    def _prune_expired(cache):
        """Loại bỏ entry đã hết hạn TTL — tránh file cache phình to vô hạn."""
        now = time.time()
        ttl = ToneCacheManager.CACHE_TTL_DAYS * 86400
        return {
            vid: entry for vid, entry in cache.items()
            if isinstance(entry, dict) and now - entry.get("cached_at", 0) <= ttl
        }

    @staticmethod
    def _save_cache(cache):
        try:
            atomic_write_json(ToneCacheManager.CACHE_FILE, cache, indent=2)
        except Exception as e:
            print(f"Lỗi lưu tone cache: {e}")

    @staticmethod
    def get_cached_tone(youtube_url):
        """Lấy tone đã cache cho URL (theo song_match_key, fallback video_id thuần)."""
        key = song_match_key(youtube_url)
        if not key:
            return None

        cache = ToneCacheManager._load_cache()
        # Tương thích ngược: entry cũ có thể được key theo video_id thuần.
        entry = cache.get(key)
        if not entry:
            legacy_key = extract_video_id(youtube_url)
            if legacy_key and legacy_key != key:
                entry = cache.get(legacy_key)

        if not entry:
            return None

        # Kiểm tra TTL
        cached_time = entry.get("cached_at", 0)
        if time.time() - cached_time > ToneCacheManager.CACHE_TTL_DAYS * 86400:
            return None  # Hết hạn

        return entry

    @staticmethod
    def save_tone(youtube_url, tone_data):
        """Lưu kết quả dò tone (auto) vào cache.

        Không mutate tone_data của caller (copy trước khi thêm cached_at).
        Chỉ bỏ qua khi key thực sự rỗng (URL/None rỗng).
        """
        key = song_match_key(youtube_url)
        if not key:
            return

        # File-lock liên tiến trình LỒNG NGOÀI threading.Lock để chống
        # lost-update khi app + tools/batch_detect_tone.py ghi song song.
        with _interprocess_lock(ToneCacheManager.CACHE_FILE), _cache_lock:
            cache = ToneCacheManager._load_cache()
            # Prune entry hết hạn khi save — file không phình to vô hạn
            cache = ToneCacheManager._prune_expired(cache)
            # Copy để không mutate dict của caller
            entry = dict(tone_data) if isinstance(tone_data, dict) else {"value": tone_data}
            entry["cached_at"] = time.time()
            cache[key] = entry
            ToneCacheManager._save_cache(cache)
        print(f"[CACHE] Đã lưu tone cho {key}")

    @staticmethod
    def clear_cache():
        """Xóa toàn bộ cache"""
        with _interprocess_lock(ToneCacheManager.CACHE_FILE), _cache_lock:
            ToneCacheManager._save_cache({})


class ManualToneTimeline:
    """Quản lý timeline tone THỦ CÔNG (user nhập) cho từng bài.

    Đây là dữ liệu người dùng → KHÔNG có TTL/prune, không tự xóa. Kết quả dò
    AUTO không còn ghi qua đây nữa (chỉ ghi vào ToneCacheManager).

    Mỗi entry có cờ "source": "human" (mặc định) để phân biệt với "auto" về sau.
    Entry CŨ không có cờ source được coi là "human" (đã sửa tay) — tương thích
    ngược, không mất ưu tiên.

    Phình kích thước: đây là DỮ LIỆU NGƯỜI DÙNG nên KHÔNG có TTL và KHÔNG tự
    xóa. Để tránh file phình âm thầm tới mức bất thường, save_timeline gọi
    _maybe_warn_size() — chỉ LOG CẢNH BÁO khi vượt SIZE_WARN_THRESHOLD, tuyệt
    đối không xóa entry nào. Dùng count_timelines() để kiểm tra số lượng.
    """

    DEFAULT_SOURCE = "human"

    # Ngưỡng cảnh báo (không xóa). Vượt mức này → log nhắc người dùng dọn thủ
    # công. Chọn lớn (2000) vì mỗi bài là 1 entry — người dùng thực khó chạm tới.
    SIZE_WARN_THRESHOLD = 2000

    @staticmethod
    def count_timelines():
        """Trả về số timeline đang lưu (số bài). Không tải nặng — chỉ đếm key."""
        return len(ManualToneTimeline._load_all())

    @staticmethod
    def _maybe_warn_size(all_data):
        """Log cảnh báo nếu số timeline vượt ngưỡng. KHÔNG xóa gì cả.

        Best-effort: mọi lỗi đều nuốt để không bao giờ chặn việc lưu dữ liệu
        người dùng.
        """
        try:
            count = len(all_data)
            if count > ManualToneTimeline.SIZE_WARN_THRESHOLD:
                print(
                    "[CẢNH BÁO] manual_timelines có {} bài (> {}). Dữ liệu KHÔNG "
                    "bị tự xóa; cân nhắc dọn thủ công các bài không dùng để file "
                    "gọn hơn.".format(count, ManualToneTimeline.SIZE_WARN_THRESHOLD)
                )
        except Exception:
            pass

    @staticmethod
    def _load_all():
        if os.path.exists(MANUAL_TIMELINES_FILE):
            try:
                with open(MANUAL_TIMELINES_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as e:
                # File hỏng: sao lưu trước rồi mới trả {} — dữ liệu người dùng
                # quý hơn cache, tuyệt đối KHÔNG để bị atomic_write đè mất.
                _backup_corrupt_file(MANUAL_TIMELINES_FILE, e)
                return {}
            except OSError as e:
                print(f"[CẢNH BÁO] Không đọc được manual timelines {MANUAL_TIMELINES_FILE}: {e}")
                return {}
        return {}

    @staticmethod
    def _save_all(data):
        try:
            atomic_write_json(MANUAL_TIMELINES_FILE, data, indent=2)
            return True
        except Exception as e:
            print(f"Lỗi lưu manual timelines: {e}")
            return False

    @staticmethod
    def load_timeline(youtube_url):
        """Load timeline cho 1 bài (theo video_id, fallback URL nguyên văn)."""
        key = song_match_key(youtube_url)
        if not key:
            return None

        all_data = ManualToneTimeline._load_all()
        # Tương thích ngược: dữ liệu cũ key theo video_id thuần
        return all_data.get(key) or all_data.get(extract_video_id(youtube_url))

    @staticmethod
    def get_timeline_source(youtube_url):
        """Đọc cờ source ('human'/'auto') của timeline 1 bài.

        Entry KHÔNG có cờ source được coi là 'human' (tương thích data cũ).
        Trả None nếu không có timeline cho bài đó.
        """
        entry = ManualToneTimeline.load_timeline(youtube_url)
        if not entry:
            return None
        return entry.get("source", ManualToneTimeline.DEFAULT_SOURCE)

    @staticmethod
    def save_timeline(youtube_url, title, timeline_entries, source="human"):
        """
        Lưu timeline cho 1 bài.

        Args:
            youtube_url: URL (YouTube hoặc nguồn khác)
            title: Tên bài hát
            timeline_entries: list of {time, key_display, key_index, scale}
            source: "human" (mặc định, user sửa tay) hoặc "auto". Lưu vào entry
                    để phân biệt nguồn về sau.
        """
        key = song_match_key(youtube_url)
        if not key:
            return False

        with _interprocess_lock(MANUAL_TIMELINES_FILE), _timeline_lock:
            all_data = ManualToneTimeline._load_all()
            all_data[key] = {
                "title": title,
                "url": youtube_url,
                "timeline": timeline_entries,
                "source": source,
                "updated_at": time.time()
            }
            ManualToneTimeline._maybe_warn_size(all_data)
            return ManualToneTimeline._save_all(all_data)

    @staticmethod
    def delete_timeline(youtube_url):
        """Xóa timeline của 1 bài (theo video_id, fallback URL nguyên văn)."""
        key = song_match_key(youtube_url)
        if not key:
            return False

        with _interprocess_lock(MANUAL_TIMELINES_FILE), _timeline_lock:
            all_data = ManualToneTimeline._load_all()
            # Tương thích ngược: xóa cả key cũ (video_id thuần) nếu có
            removed = False
            for k in {key, extract_video_id(youtube_url)}:
                if k and k in all_data:
                    del all_data[k]
                    removed = True
            if removed:
                return ManualToneTimeline._save_all(all_data)
            return False

    @staticmethod
    def list_all_timelines():
        """Liệt kê tất cả timeline đã lưu"""
        all_data = ManualToneTimeline._load_all()
        result = []
        for video_id, data in all_data.items():
            if not isinstance(data, dict):
                continue
            result.append({
                "video_id": video_id,
                "title": data.get("title", ""),
                "url": data.get("url", ""),
                "entries_count": len(data.get("timeline", [])),
                "source": data.get("source", ManualToneTimeline.DEFAULT_SOURCE),
                "updated_at": data.get("updated_at", 0)
            })
        return result

    @staticmethod
    def get_entry_at_position(timeline, position_seconds):
        """Lấy entry áp dụng cho thời gian hiện tại (thời gian <= position lớn nhất)"""
        if not timeline:
            return None, -1

        target_idx = -1
        for i, entry in enumerate(timeline):
            if entry['time'] <= position_seconds:
                target_idx = i
            else:
                break

        if target_idx >= 0:
            return timeline[target_idx], target_idx
        return None, -1

    @staticmethod
    def time_str_to_seconds(time_str):
        """Chuyển 'MM:SS' hoặc 'HH:MM:SS' thành giây (float). Trả None nếu không hợp lệ."""
        try:
            parts = time_str.strip().split(":")
            if len(parts) == 2:
                return int(parts[0]) * 60 + float(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
            # Thử parse số thuần (giây)
            val = float(time_str.strip())
            if val >= 0:
                return val
        except (ValueError, IndexError):
            pass
        return None

    @staticmethod
    def parse_time_str(time_str):
        """Alias của time_str_to_seconds — dùng bởi frontend_qt.py."""
        return ManualToneTimeline.time_str_to_seconds(time_str)

    @staticmethod
    def seconds_to_time_str(seconds):
        """Chuyển giây thành 'MM:SS'"""
        m = int(seconds) // 60
        s = int(seconds) % 60
        return f"{m}:{s:02d}"
