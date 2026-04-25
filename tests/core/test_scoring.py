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

def test_calculate_score_quick_mode(engine):
    # SC-04: Quick mode scoring (volume + voiced ratio)
    audio = np.ones(44100)  # Constant volume, std=0
    engine.load_audio_data(audio)

    score = engine.calculate_score(quick=True)
    assert score is not None
    assert score["total_score"] >= 65  # Encouraging floor
    assert score["total_score"] <= 98  # Ceiling
    assert "volume_consistency" in score
    assert "voiced_ratio" in score
    assert "feedback" in score

def test_calculate_score_full_mode(mock_librosa, engine):
    # SC-04b: Full mode scoring with pitch analysis
    audio = np.random.randn(44100).astype(np.float32) * 0.5
    engine.load_audio_data(audio)

    # Mock pyin to return valid pitch data
    n_frames = 50
    f0 = np.full(n_frames, 440.0)
    voiced_flag = np.ones(n_frames, dtype=bool)
    voiced_probs = np.full(n_frames, 0.9)
    mock_librosa.pyin.return_value = (f0, voiced_flag, voiced_probs)
    mock_librosa.note_to_hz.side_effect = lambda n: 65.41 if n == 'C2' else 2093.0

    # Mock onset detection
    mock_librosa.onset.onset_detect.return_value = np.array([0.5, 1.0, 1.5, 2.0])

    score = engine.calculate_score(quick=False, key_reference="Am")
    assert score is not None
    assert score["total_score"] >= 65
    assert score["total_score"] <= 98
    assert "pitch_intonation" in score
    assert "pitch_stability" in score
    assert "key_conformity" in score
    assert "rhythm_score" in score

def test_calculate_score_no_audio(engine):
    # SC-06
    score = engine.calculate_score()
    assert score is None

def test_generate_feedback_excellent(engine):
    # SC-07: Sieu Sao rank (>= 93)
    fb = engine._generate_feedback(
        total_score=96, pitch_intonation=95, pitch_stability=95,
        volume_consistency=90, rhythm_score=90, voiced_ratio=85, key_conformity=92,
    )
    assert fb["rank"] == "Sieu Sao"
    assert fb["icon"] == "👑"

def test_generate_feedback_good(engine):
    # SC-08: Giong Ca Trien Vong rank (75-82)
    fb = engine._generate_feedback(
        total_score=78, pitch_intonation=70, pitch_stability=70,
        volume_consistency=75, rhythm_score=70, voiced_ratio=80, key_conformity=75,
    )
    assert fb["rank"] == "Giong Ca Trien Vong"
    assert fb["icon"] == "🎤"

def test_generate_feedback_needs_practice(engine):
    # SC-09: Tap Su Rank (< 75)
    fb = engine._generate_feedback(
        total_score=60, pitch_intonation=40, pitch_stability=40,
        volume_consistency=50, rhythm_score=40, voiced_ratio=60, key_conformity=50,
    )
    assert fb["rank"] == "Tap Su Day Tiem Nang"
    assert fb["icon"] == "💪"

def test_generate_feedback_has_tips(engine):
    # SC-09b: Tips should be based on real metrics
    fb = engine._generate_feedback(
        total_score=75, pitch_intonation=40, pitch_stability=40,
        volume_consistency=50, rhythm_score=30, voiced_ratio=70, key_conformity=50,
    )
    assert len(fb["tips"]) >= 1
    assert len(fb["tips"]) <= 3

def test_encourage_transform(engine):
    # Test the encouraging score transform
    assert ScoringEngine._encourage(0) == 65    # Floor
    assert ScoringEngine._encourage(100) == 98  # Ceiling
    assert 65 < ScoringEngine._encourage(50) < 98  # Middle

def test_key_conformity_no_key(engine):
    # Without key reference, should return neutral score
    engine.key_reference = None
    score = engine._compute_key_conformity(np.array([440.0] * 20), np.ones(20, dtype=bool))
    assert score == 80

@patch("core.scoring.download_with_auth")
def test_download_youtube_audio(mock_download, engine, tmp_path):
    # SC-10
    with patch("core.scoring.RECORDINGS_DIR", str(tmp_path)):
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
