"""
Quang Lưu Studio — Tone Cache & Manual Timeline
Classes: ToneCacheManager, ManualToneTimeline
"""
import os
import json
import time
import re
import threading

from core.utils import extract_video_id, atomic_write_json
from core.config import MANUAL_TIMELINES_FILE, TONE_CACHE_FILE

# Lock bảo vệ chu trình read-modify-write trên các file JSON cache
_cache_lock = threading.Lock()
_timeline_lock = threading.Lock()


class ToneCacheManager:
    """Quản lý cache kết quả dò tone YouTube — tránh dò lại bài đã biết"""

    CACHE_FILE = TONE_CACHE_FILE
    CACHE_TTL_DAYS = 30  # Hết hạn sau 30 ngày

    @staticmethod
    def _load_cache():
        if os.path.exists(ToneCacheManager.CACHE_FILE):
            try:
                with open(ToneCacheManager.CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
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
        """Lấy tone đã cache cho YouTube URL (theo video ID)"""
        video_id = extract_video_id(youtube_url)
        if not video_id:
            return None
        
        cache = ToneCacheManager._load_cache()
        entry = cache.get(video_id)
        
        if not entry:
            return None
        
        # Kiểm tra TTL
        cached_time = entry.get("cached_at", 0)
        if time.time() - cached_time > ToneCacheManager.CACHE_TTL_DAYS * 86400:
            return None  # Hết hạn
        
        return entry
    
    @staticmethod
    def save_tone(youtube_url, tone_data):
        """Lưu kết quả dò tone vào cache"""
        video_id = extract_video_id(youtube_url)
        if not video_id:
            return

        with _cache_lock:
            cache = ToneCacheManager._load_cache()
            # Prune entry hết hạn khi save — file không phình to vô hạn
            cache = ToneCacheManager._prune_expired(cache)
            tone_data["cached_at"] = time.time()
            cache[video_id] = tone_data
            ToneCacheManager._save_cache(cache)
        print(f"[CACHE] Đã lưu tone cho video {video_id}")

    @staticmethod
    def clear_cache():
        """Xóa toàn bộ cache"""
        with _cache_lock:
            ToneCacheManager._save_cache({})


class ManualToneTimeline:
    """Quản lý timeline tone thủ công (user nhập) cho từng bài YouTube"""
    
    @staticmethod
    def _load_all():
        if os.path.exists(MANUAL_TIMELINES_FILE):
            try:
                with open(MANUAL_TIMELINES_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
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
        """Load timeline cho 1 bài YouTube (theo video ID)"""
        video_id = extract_video_id(youtube_url)
        if not video_id:
            return None
        
        all_data = ManualToneTimeline._load_all()
        return all_data.get(video_id)
    
    @staticmethod
    def save_timeline(youtube_url, title, timeline_entries):
        """
        Lưu timeline cho 1 bài YouTube.
        
        Args:
            youtube_url: YouTube URL
            title: Tên bài hát
            timeline_entries: list of {time, key_display, key_index, scale}
        """
        video_id = extract_video_id(youtube_url)
        if not video_id:
            return False

        with _timeline_lock:
            all_data = ManualToneTimeline._load_all()
            all_data[video_id] = {
                "title": title,
                "url": youtube_url,
                "timeline": timeline_entries,
                "updated_at": time.time()
            }
            return ManualToneTimeline._save_all(all_data)
    
    @staticmethod
    def delete_timeline(youtube_url):
        """Xóa timeline của 1 bài"""
        video_id = extract_video_id(youtube_url)
        if not video_id:
            return False

        with _timeline_lock:
            all_data = ManualToneTimeline._load_all()
            if video_id in all_data:
                del all_data[video_id]
                return ManualToneTimeline._save_all(all_data)
            return False
    
    @staticmethod
    def list_all_timelines():
        """Liệt kê tất cả timeline đã lưu"""
        all_data = ManualToneTimeline._load_all()
        result = []
        for video_id, data in all_data.items():
            result.append({
                "video_id": video_id,
                "title": data.get("title", ""),
                "url": data.get("url", ""),
                "entries_count": len(data.get("timeline", [])),
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
