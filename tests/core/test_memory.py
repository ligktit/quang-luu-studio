import pytest
import os
import sys
import time
from unittest.mock import patch, MagicMock
from core.memory import MemoryProfiler, MemoryGuard

@pytest.fixture
def mock_psutil():
    mock_psutil_module = MagicMock()
    mock_proc = MagicMock()
    mock_mem_info = MagicMock()
    mock_mem_info.rss = 100 * 1024 * 1024  # 100MB
    mock_proc.memory_info.return_value = mock_mem_info
    mock_psutil_module.Process.return_value = mock_proc
    sys.modules['psutil'] = mock_psutil_module
    yield mock_proc, mock_mem_info
    del sys.modules['psutil']

def test_checkpoint_logs(mock_psutil, capsys):
    # MM-01
    mock_proc, mock_mem_info = mock_psutil
    profiler = MemoryProfiler("TEST")
    
    # Tăng 30MB (vượt ngưỡng log 20MB)
    mock_mem_info.rss += 30 * 1024 * 1024
    profiler.checkpoint("label")
    
    captured = capsys.readouterr()
    assert "[TEST]" in captured.out
    assert "label" in captured.out

def test_checkpoint_no_log(mock_psutil, capsys):
    # MM-02
    mock_proc, mock_mem_info = mock_psutil
    profiler = MemoryProfiler("TEST")
    
    # Tăng 2MB
    mock_mem_info.rss += 2 * 1024 * 1024
    profiler.checkpoint("label")
    
    captured = capsys.readouterr()
    assert captured.out == ""

def test_summary_no_raise(mock_psutil):
    # MM-03
    profiler = MemoryProfiler("TEST")
    profiler.checkpoint()
    profiler.summary()  # Should not raise

def test_guard_start_stop():
    # MM-04
    guard = MemoryGuard(interval=0.1)
    guard.start()
    assert guard._running is True
    assert guard._thread is not None
    assert guard._thread.is_alive()
    
    guard.stop()
    assert guard._running is False
    assert guard._thread is None or not guard._thread.is_alive()

@patch("core.memory.gc.collect")
def test_force_cleanup(mock_gc_collect):
    # MM-05
    MemoryGuard.force_cleanup()
    mock_gc_collect.assert_called_with(2)

def test_cleanup_temp_files(tmp_path):
    # MM-06
    # Patch RECORDINGS_DIR to use tmp_path
    with patch("core.config.RECORDINGS_DIR", str(tmp_path)):
        guard = MemoryGuard(cache_ttl_seconds=1)

        # File tạm của app (prefix qls_tmp_) → bị xóa
        temp_file = tmp_path / "qls_tmp_abc123.wav"
        temp_file.write_text("dummy", encoding="utf-8")

        # Recording của user (KHÔNG có prefix) → phải được giữ lại
        user_file = tmp_path / "recording_12345.wav"
        user_file.write_text("dummy", encoding="utf-8")

        # Set mtime to past
        os.utime(temp_file, (time.time() - 10, time.time() - 10))
        os.utime(user_file, (time.time() - 10, time.time() - 10))

        guard._cleanup_temp_files()
        assert not temp_file.exists()
        assert user_file.exists()

def test_get_status(mock_psutil):
    # MM-07
    guard = MemoryGuard(gc_threshold_mb=50, emergency_threshold_mb=500)
    status = guard.get_status()
    
    assert "running" in status
    assert status["rss_mb"] == 100
    assert status["gc_threshold_mb"] == 50
    assert status["emergency_threshold_mb"] == 500
