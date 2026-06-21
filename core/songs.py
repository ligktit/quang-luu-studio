"""
Quang Lưu Studio — Song Manager & Playlist Manager
Classes: SongManager, PlaylistManager
"""
import os
import json
import time
import threading

from core.config import SONGS_FILE, PLAYLISTS_FILE
from core.utils import atomic_write_json, song_match_key as _song_match_key

# Lock bảo vệ chu trình read-modify-write trên saved_songs.json
# (add/delete/update có thể được gọi từ nhiều thread)
_songs_lock = threading.Lock()
_playlists_lock = threading.Lock()


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
        """Lưu danh sách bài hát vào file (atomic write)"""
        try:
            atomic_write_json(SONGS_FILE, songs_list)
            return True
        except Exception as e:
            print(f"Lỗi lưu danh sách bài hát: {e}")
            return False

    @staticmethod
    def add_song(title, url, tone, favorite=None):
        """Thêm bài hát mới vào danh sách.

        Chống trùng theo video_id (fallback URL). Nếu bài đã tồn tại → cập nhật
        title/tone, giữ nguyên favorite/playlist (trừ khi favorite được truyền).
        """
        with _songs_lock:
            songs = SongManager.load_songs()
            match_key = _song_match_key(url)

            # Kiểm tra xem bài hát đã tồn tại chưa (theo video_id / URL)
            for song in songs:
                if _song_match_key(song.get("url", "")) == match_key:
                    # Cập nhật thông tin nếu đã tồn tại
                    song["tone"] = tone
                    song["title"] = title
                    if favorite is not None:
                        song["favorite"] = bool(favorite)
                    SongManager.save_songs(songs)
                    return True

            # ID mới = max(id hiện có) + 1 — len(songs)+1 sẽ trùng ID sau khi xóa
            existing_ids = [s.get("id") for s in songs if isinstance(s.get("id"), int)]
            new_id = (max(existing_ids) + 1) if existing_ids else 1

            # Thêm bài hát mới
            new_song = {
                "id": new_id,
                "title": title,
                "url": url,
                "tone": tone,
                "favorite": bool(favorite) if favorite is not None else False,
                "date_added": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            songs.append(new_song)
            return SongManager.save_songs(songs)

    @staticmethod
    def delete_song(song_id):
        """Xóa bài hát khỏi danh sách (và khỏi mọi playlist)"""
        with _songs_lock:
            songs = SongManager.load_songs()
            songs = [s for s in songs if s.get("id") != song_id]
            ok = SongManager.save_songs(songs)
        # Dọn bài khỏi các playlist (lock riêng để tránh deadlock)
        PlaylistManager.remove_song_everywhere(song_id)
        return ok

    @staticmethod
    def update_song(song_id, **kwargs):
        """Cập nhật thông tin bài hát theo ID. kwargs có thể chứa title, tone, url..."""
        with _songs_lock:
            songs = SongManager.load_songs()
            for song in songs:
                if song.get("id") == song_id:
                    for key, value in kwargs.items():
                        song[key] = value
                    return SongManager.save_songs(songs)
            return False

    @staticmethod
    def toggle_favorite(song_id):
        """Đảo trạng thái yêu thích. Trả về trạng thái mới (bool)."""
        with _songs_lock:
            songs = SongManager.load_songs()
            for song in songs:
                if song.get("id") == song_id:
                    new_state = not bool(song.get("favorite", False))
                    song["favorite"] = new_state
                    SongManager.save_songs(songs)
                    return new_state
            return False

    @staticmethod
    def get_song_by_id(song_id):
        """Lấy thông tin bài hát theo ID"""
        songs = SongManager.load_songs()
        for song in songs:
            if song.get("id") == song_id:
                return song
        return None

    @staticmethod
    def sort_for_display(songs):
        """Sắp xếp để hiển thị: bài yêu thích lên đầu, giữ thứ tự gốc trong nhóm."""
        return sorted(songs, key=lambda s: 0 if s.get("favorite") else 1)


class PlaylistManager:
    """Quản lý danh sách phát (playlist).

    Cấu trúc playlists.json:
        [{"id": 1, "name": "...", "song_ids": [1, 3], "created_at": "..."}]
    """

    @staticmethod
    def load_playlists():
        if os.path.exists(PLAYLISTS_FILE):
            try:
                with open(PLAYLISTS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, list) else []
            except Exception:
                return []
        return []

    @staticmethod
    def save_playlists(playlists):
        try:
            atomic_write_json(PLAYLISTS_FILE, playlists)
            return True
        except Exception as e:
            print(f"Lỗi lưu playlists: {e}")
            return False

    @staticmethod
    def create_playlist(name):
        """Tạo playlist mới. Trả về dict playlist vừa tạo, hoặc None nếu tên rỗng/trùng."""
        name = (name or "").strip()
        if not name:
            return None
        with _playlists_lock:
            playlists = PlaylistManager.load_playlists()
            if any(p.get("name", "").lower() == name.lower() for p in playlists):
                return None  # Trùng tên
            existing_ids = [p.get("id") for p in playlists if isinstance(p.get("id"), int)]
            new_id = (max(existing_ids) + 1) if existing_ids else 1
            playlist = {
                "id": new_id,
                "name": name,
                "song_ids": [],
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            playlists.append(playlist)
            PlaylistManager.save_playlists(playlists)
            return playlist

    @staticmethod
    def rename_playlist(playlist_id, name):
        name = (name or "").strip()
        if not name:
            return False
        with _playlists_lock:
            playlists = PlaylistManager.load_playlists()
            if any(p.get("name", "").lower() == name.lower() and p.get("id") != playlist_id
                   for p in playlists):
                return False  # Trùng tên playlist khác
            for p in playlists:
                if p.get("id") == playlist_id:
                    p["name"] = name
                    return PlaylistManager.save_playlists(playlists)
            return False

    @staticmethod
    def delete_playlist(playlist_id):
        with _playlists_lock:
            playlists = PlaylistManager.load_playlists()
            new_list = [p for p in playlists if p.get("id") != playlist_id]
            if len(new_list) == len(playlists):
                return False
            return PlaylistManager.save_playlists(new_list)

    @staticmethod
    def get_playlist(playlist_id):
        for p in PlaylistManager.load_playlists():
            if p.get("id") == playlist_id:
                return p
        return None

    @staticmethod
    def add_song_to_playlist(playlist_id, song_id):
        with _playlists_lock:
            playlists = PlaylistManager.load_playlists()
            for p in playlists:
                if p.get("id") == playlist_id:
                    ids = p.setdefault("song_ids", [])
                    if song_id not in ids:
                        ids.append(song_id)
                        return PlaylistManager.save_playlists(playlists)
                    return True  # Đã có sẵn
            return False

    @staticmethod
    def remove_song_from_playlist(playlist_id, song_id):
        with _playlists_lock:
            playlists = PlaylistManager.load_playlists()
            for p in playlists:
                if p.get("id") == playlist_id:
                    ids = p.setdefault("song_ids", [])
                    if song_id in ids:
                        ids.remove(song_id)
                        return PlaylistManager.save_playlists(playlists)
                    return True
            return False

    @staticmethod
    def remove_song_everywhere(song_id):
        """Gỡ một bài khỏi tất cả playlist (gọi khi xóa bài hát)."""
        with _playlists_lock:
            playlists = PlaylistManager.load_playlists()
            changed = False
            for p in playlists:
                ids = p.get("song_ids", [])
                if song_id in ids:
                    ids.remove(song_id)
                    changed = True
            if changed:
                PlaylistManager.save_playlists(playlists)
            return changed

    @staticmethod
    def playlists_containing(song_id):
        """Trả về set id các playlist đang chứa bài hát này."""
        return {
            p.get("id") for p in PlaylistManager.load_playlists()
            if song_id in p.get("song_ids", [])
        }
