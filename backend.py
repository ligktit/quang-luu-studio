"""
Quang Lưu Studio — Backend Facade

This module re-exports all classes and constants from the core/ package
so that existing imports like `import backend; backend.SystemEngine()`
continue to work without changes.

REFACTORED: The original monolithic backend.py has been split into
focused modules under core/. See core/ for the actual implementations.
"""
import gc  # re-export (used by consumers)

# ── Constants ──
from core.config import (
    SETTINGS_FILE,
    SONGS_FILE,
    ACTIVATION_FILE,
    MANUAL_TIMELINES_FILE,
    APP_CONFIG_FILE,
    MIDI_PORT_NAME,
    FFMPEG_LOCATION,
)

# ── Classes ──
from core.config import AppConfig, ConfigManager
from core.utils import find_ffmpeg, extract_video_id
from core.memory import MemoryProfiler, MemoryGuard
from core.media_monitor import WindowsMediaMonitor, _WIN_MEDIA_AVAILABLE
from core.midi import MidiHandler
from core.tone_cache import ToneCacheManager, ManualToneTimeline
from core.recorder import AudioRecorder
from core.songs import SongManager
from core.scoring import ScoringEngine
from core.tone_detector import ToneDetector
from core.activation import ActivationManager
from core.engine import SystemEngine

# ── Backward-compat alias ──
# The old backend.py had a module-level _find_ffmpeg function
_find_ffmpeg = find_ffmpeg

__all__ = [
    # Constants
    "SETTINGS_FILE", "SONGS_FILE", "ACTIVATION_FILE",
    "MANUAL_TIMELINES_FILE", "APP_CONFIG_FILE",
    "MIDI_PORT_NAME", "FFMPEG_LOCATION",
    # Classes
    "AppConfig", "ConfigManager",
    "MemoryProfiler", "MemoryGuard",
    "WindowsMediaMonitor", "_WIN_MEDIA_AVAILABLE",
    "MidiHandler",
    "ToneCacheManager", "ManualToneTimeline",
    "AudioRecorder",
    "SongManager",
    "ScoringEngine",
    "ToneDetector",
    "ActivationManager",
    "SystemEngine",
    # Utilities
    "find_ffmpeg", "extract_video_id", "_find_ffmpeg",
    # Modules
    "gc",
]