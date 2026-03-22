"""
Quang Lưu Studio — Song Manager
Class: SongManager
"""
import os
import json
import time

from core.config import SONGS_FILE


class SongManager:
    """Quản lý danh sách bài hát đã lưu"""
    @staticmethod
    def load_songs():
        """Load danh sách bài hát từ file"""
        if os.path.exists(SONGS_FILE):
            try:
                with open(SONGS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []
    
    @staticmethod
    def save_songs(songs_list):
        """Lưu danh sách bài hát vào file"""
        try:
            with open(SONGS_FILE, "w", encoding="utf-8") as f:
                json.dump(songs_list, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Lỗi lưu danh sách bài hát: {e}")
            return False
    
    @staticmethod
    def add_song(title, url, tone):
        """Thêm bài hát mới vào danh sách"""
        songs = SongManager.load_songs()
        
        # Kiểm tra xem bài hát đã tồn tại chưa
        for song in songs:
            if song.get("url") == url:
                # Cập nhật tone nếu đã tồn tại
                song["tone"] = tone
                song["title"] = title
                SongManager.save_songs(songs)
                return True
        
        # Thêm bài hát mới
        new_song = {
            "id": len(songs) + 1 if songs else 1,
            "title": title,
            "url": url,
            "tone": tone,
            "date_added": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        songs.append(new_song)
        return SongManager.save_songs(songs)
    
    @staticmethod
    def delete_song(song_id):
        """Xóa bài hát khỏi danh sách"""
        songs = SongManager.load_songs()
        songs = [s for s in songs if s.get("id") != song_id]
        return SongManager.save_songs(songs)
    
    @staticmethod
    def update_song(song_id, **kwargs):
        """Cập nhật thông tin bài hát theo ID. kwargs có thể chứa title, tone, url..."""
        songs = SongManager.load_songs()
        for song in songs:
            if song.get("id") == song_id:
                for key, value in kwargs.items():
                    song[key] = value
                return SongManager.save_songs(songs)
        return False
    
    @staticmethod
    def get_song_by_id(song_id):
        """Lấy thông tin bài hát theo ID"""
        songs = SongManager.load_songs()
        for song in songs:
            if song.get("id") == song_id:
                return song
        return None
