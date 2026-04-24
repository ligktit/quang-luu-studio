import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from core.scoring import ScoringEngine
import sys

@pytest.fixture(autouse=True)
def mock_librosa():
    mock_librosa_module = MagicMock()
    sys.modules['librosa'] = mock_librosa_module
    yield mock_librosa_module
    if 'librosa' in sys.modules:
        del sys.modules['librosa']

@pytest.fixture
def engine():
    return ScoringEngine()

def test_load_audio_data(engine):
    # SC-01
    audio = np.zeros(44100)
    assert engine.load_audio_data(audio) is True
    assert engine.audio_data is not None
    assert engine.sample_rate == 44100

def test_load_audio_file(mock_librosa, engine):
    # SC-02
    mock_load = mock_librosa.load
    mock_load.return_value = (np.zeros(44100), 44100)
    assert engine.load_audio("test.wav") is True
    assert engine.audio_data is not None

def test_analyze_pitch(mock_librosa, engine):
    # SC-03
    mock_pyin = mock_librosa.pyin
    audio = np.zeros(44100)
    engine.load_audio_data(audio)
    mock_pyin.return_value = (np.array([440.0, np.nan, 442.0]), [True, False, True], [0.9, 0.1, 0.9])
    
    pitches = engine.analyze_pitch()
    assert pitches is not None
    assert len(pitches) == 2
    assert pitches[0] == 440.0

def test_calculate_score_perfect(mock_librosa, engine):
    # SC-04 (Quick mode since standard uses randoms for pitch and timing and requires pyin)
    mock_pyin = mock_librosa.pyin
    audio = np.ones(44100) # Constant volume, std=0
    engine.load_audio_data(audio)
    
    score = engine.calculate_score(quick=True)
    assert score is not None
    assert score["total_score"] >= 77

def test_calculate_score_no_audio(engine):
    # SC-06
    score = engine.calculate_score()
    assert score is None

def test_generate_feedback_excellent(engine):
    # SC-07
    fb = engine._generate_feedback(96, 95, 95)
    assert fb["rank"] == "Siêu Sao"
    assert fb["icon"] == "👑"

def test_generate_feedback_good(engine):
    # SC-08
    fb = engine._generate_feedback(82, 80, 80)
    assert fb["rank"] == "Giọng Ca Triển Vọng"
    assert fb["icon"] == "🎤"

def test_generate_feedback_needs_practice(engine):
    # SC-09
    fb = engine._generate_feedback(60, 50, 50)
    assert fb["rank"] == "Tập Sự Đầy Tiềm Năng"
    assert fb["icon"] == "💪"

@patch("core.scoring.download_with_auth")
def test_download_youtube_audio(mock_download, engine, tmp_path):
    # SC-10
    # Patch the temporary dir
    with patch("core.scoring.RECORDINGS_DIR", str(tmp_path)):
        # Provide a fake file that seems downloaded
        def mock_download_side_effect(url, ydl_opts, log_prefix):
            outtmpl = ydl_opts["outtmpl"]
            base = outtmpl.replace(".%(ext)s", "")
            with open(base + ".m4a", "w") as f:
                f.write("dummy")
            
        mock_download.side_effect = mock_download_side_effect
        res = engine.download_youtube_audio("http://yt.com", output_dir=str(tmp_path))
        
        assert res is not None
        assert res.endswith(".wav") or res.endswith(".m4a")
        mock_download.assert_called()

def test_cleanup_temp_file(engine, tmp_path):
    # SC-11
    test_file = tmp_path / "test.wav"
    test_file.write_text("dummy")
    
    engine.temp_audio_path = str(test_file)
    engine.audio_data = np.zeros(10)
    
    engine.cleanup_temp_file()
    
    assert engine.audio_data is None
    assert engine.temp_audio_path is None
    assert not test_file.exists()
