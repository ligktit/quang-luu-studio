import pytest
import json
from unittest.mock import patch
from core.songs import SongManager, PlaylistManager

@pytest.fixture(autouse=True)
def mock_songs_file(tmp_path):
    songs_file = tmp_path / "saved_songs.json"
    playlists_file = tmp_path / "playlists.json"
    with patch("core.songs.SONGS_FILE", str(songs_file)), \
         patch("core.songs.PLAYLISTS_FILE", str(playlists_file)):
        yield songs_file

def test_load_songs_empty_file(mock_songs_file):
    # S-01
    mock_songs_file.write_text("[]", encoding="utf-8")
    assert SongManager.load_songs() == []

def test_load_songs_not_exists(mock_songs_file):
    # S-02
    assert SongManager.load_songs() == []

def test_add_song_new(mock_songs_file):
    # S-03
    SongManager.add_song("Song 1", "http://yt.com/1", "C Major")
    songs = SongManager.load_songs()
    assert len(songs) == 1
    assert songs[0]["id"] == 1
    assert songs[0]["title"] == "Song 1"

def test_add_song_next(mock_songs_file):
    # S-04
    SongManager.add_song("Song 1", "http://yt.com/1", "C Major")
    SongManager.add_song("Song 2", "http://yt.com/2", "D Major")
    songs = SongManager.load_songs()
    assert len(songs) == 2
    assert songs[1]["id"] == 2

def test_add_song_update_duplicate_url(mock_songs_file):
    # S-05
    SongManager.add_song("Song 1", "http://yt.com/1", "C Major")
    SongManager.add_song("Song 1 Updated", "http://yt.com/1", "D Major")
    songs = SongManager.load_songs()
    assert len(songs) == 1
    assert songs[0]["tone"] == "D Major"
    assert songs[0]["title"] == "Song 1 Updated"

def test_get_song_by_id_exists(mock_songs_file):
    # S-06
    SongManager.add_song("Song 1", "http://yt.com/1", "C Major")
    song = SongManager.get_song_by_id(1)
    assert song is not None
    assert song["title"] == "Song 1"

def test_get_song_by_id_not_exists(mock_songs_file):
    # S-07
    assert SongManager.get_song_by_id(999) is None

def test_delete_song_exists(mock_songs_file):
    # S-08
    SongManager.add_song("Song 1", "http://yt.com/1", "C Major")
    SongManager.delete_song(1)
    assert len(SongManager.load_songs()) == 0

def test_delete_song_not_exists(mock_songs_file):
    # S-09
    SongManager.add_song("Song 1", "http://yt.com/1", "C Major")
    SongManager.delete_song(999)
    assert len(SongManager.load_songs()) == 1

def test_update_song(mock_songs_file):
    # S-10
    SongManager.add_song("Song 1", "http://yt.com/1", "C Major")
    res = SongManager.update_song(1, title="New Title")
    assert res is True
    song = SongManager.get_song_by_id(1)
    assert song["title"] == "New Title"

def test_add_song_no_id_collision_after_delete(mock_songs_file):
    # S-12: ID mới = max(id)+1, không trùng sau khi xóa
    SongManager.add_song("Song 1", "http://yt.com/1", "C Major")
    SongManager.add_song("Song 2", "http://yt.com/2", "D Major")
    SongManager.delete_song(1)
    SongManager.add_song("Song 3", "http://yt.com/3", "E Minor")
    songs = SongManager.load_songs()
    ids = [s["id"] for s in songs]
    assert len(ids) == len(set(ids))  # Không trùng ID
    assert SongManager.get_song_by_id(3)["title"] == "Song 3"

def test_add_song_dedup_by_video_id(mock_songs_file):
    # S-13: cùng video YouTube nhưng khác định dạng URL → không lưu trùng
    SongManager.add_song("Song", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "C")
    SongManager.add_song("Song", "https://youtu.be/dQw4w9WgXcQ?t=30", "Am")
    songs = SongManager.load_songs()
    assert len(songs) == 1
    assert songs[0]["tone"] == "Am"

def test_add_song_default_favorite_false(mock_songs_file):
    SongManager.add_song("Song", "http://yt.com/1", "C")
    assert SongManager.load_songs()[0]["favorite"] is False

def test_toggle_favorite(mock_songs_file):
    SongManager.add_song("Song", "http://yt.com/1", "C")
    assert SongManager.toggle_favorite(1) is True
    assert SongManager.get_song_by_id(1)["favorite"] is True
    assert SongManager.toggle_favorite(1) is False
    assert SongManager.get_song_by_id(1)["favorite"] is False

def test_add_song_preserves_favorite_on_update(mock_songs_file):
    SongManager.add_song("Song", "http://yt.com/1", "C")
    SongManager.toggle_favorite(1)
    SongManager.add_song("Song updated", "http://yt.com/1", "D")  # update path
    assert SongManager.get_song_by_id(1)["favorite"] is True

def test_sort_for_display_favorites_first(mock_songs_file):
    SongManager.add_song("A", "http://yt.com/1", "C")
    SongManager.add_song("B", "http://yt.com/2", "C")
    SongManager.add_song("C", "http://yt.com/3", "C")
    SongManager.toggle_favorite(3)
    ordered = SongManager.sort_for_display(SongManager.load_songs())
    assert ordered[0]["id"] == 3

def test_create_and_get_playlist(mock_songs_file):
    pl = PlaylistManager.create_playlist("Nhạc trẻ")
    assert pl["id"] == 1
    assert PlaylistManager.get_playlist(1)["name"] == "Nhạc trẻ"

def test_create_playlist_rejects_duplicate_name(mock_songs_file):
    PlaylistManager.create_playlist("List")
    assert PlaylistManager.create_playlist("list") is None  # case-insensitive

def test_add_remove_song_in_playlist(mock_songs_file):
    PlaylistManager.create_playlist("List")
    assert PlaylistManager.add_song_to_playlist(1, 5) is True
    assert 1 in PlaylistManager.playlists_containing(5)
    PlaylistManager.remove_song_from_playlist(1, 5)
    assert 1 not in PlaylistManager.playlists_containing(5)

def test_delete_song_removes_from_playlists(mock_songs_file):
    SongManager.add_song("Song", "http://yt.com/1", "C")
    PlaylistManager.create_playlist("List")
    PlaylistManager.add_song_to_playlist(1, 1)
    SongManager.delete_song(1)
    assert PlaylistManager.get_playlist(1)["song_ids"] == []

def test_rename_and_delete_playlist(mock_songs_file):
    PlaylistManager.create_playlist("Old")
    assert PlaylistManager.rename_playlist(1, "New") is True
    assert PlaylistManager.get_playlist(1)["name"] == "New"
    assert PlaylistManager.delete_playlist(1) is True
    assert PlaylistManager.get_playlist(1) is None

def test_save_and_load_round_trip(mock_songs_file):
    # S-11
    songs_to_save = [
        {"id": 1, "title": "A", "url": "U1", "tone": "T1"},
        {"id": 2, "title": "B", "url": "U2", "tone": "T2"},
        {"id": 3, "title": "C", "url": "U3", "tone": "T3"},
    ]
    SongManager.save_songs(songs_to_save)
    loaded = SongManager.load_songs()
    assert loaded == songs_to_save
