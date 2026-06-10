import pytest
import json
from unittest.mock import patch
from core.songs import SongManager

@pytest.fixture(autouse=True)
def mock_songs_file(tmp_path):
    songs_file = tmp_path / "saved_songs.json"
    with patch("core.songs.SONGS_FILE", str(songs_file)):
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
