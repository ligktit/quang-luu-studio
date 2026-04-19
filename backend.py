"""
Quang Lưu Studio — Backend Facade

Re-exports classes and constants from the core/ package so existing imports
(`import backend; backend.SystemEngine(...)`, `from backend import ToneDetector`)
continue to work without changes.

REFACTORED: The original monolithic backend.py has been split into focused
modules under core/. See core/ for the actual implementations.

Lightweight symbols (constants, AppConfig, ConfigManager, ActivationManager)
are imported eagerly — they're needed at app startup for the activation gate.
Heavyweight symbols (SystemEngine, AudioRecorder, ToneDetector, …) are resolved
lazily via PEP 562 `__getattr__`, so merely importing `backend` for the
activation check doesn't pull in audio / MIDI / media-monitor stacks.
"""
import importlib

# ── Eager: lightweight, needed before the activation gate ──
from core.config import (
    SETTINGS_FILE,
    SONGS_FILE,
    ACTIVATION_FILE,
    MANUAL_TIMELINES_FILE,
    TONE_CACHE_FILE,
    APP_CONFIG_FILE,
    MIDI_PORT_NAME,
    FFMPEG_LOCATION,
    APP_DIR,
    DATA_DIR,
    RECORDINGS_DIR,
    AppConfig,
    ConfigManager,
)
from core.activation import ActivationManager


# ── Lazy: mapping of public name → (module, attribute) ──
# Resolved on first attribute access, then cached into module globals.
_LAZY_EXPORTS = {
    # utils
    "find_ffmpeg":         ("core.utils",         "find_ffmpeg"),
    "extract_video_id":    ("core.utils",         "extract_video_id"),
    # memory
    "MemoryProfiler":      ("core.memory",        "MemoryProfiler"),
    "MemoryGuard":         ("core.memory",        "MemoryGuard"),
    # media monitor
    "WindowsMediaMonitor": ("core.media_monitor", "WindowsMediaMonitor"),
    # midi / audio
    "MidiHandler":         ("core.midi",          "MidiHandler"),
    "AudioRecorder":       ("core.recorder",      "AudioRecorder"),
    # tone / songs / scoring
    "ToneCacheManager":    ("core.tone_cache",    "ToneCacheManager"),
    "ManualToneTimeline":  ("core.tone_cache",    "ManualToneTimeline"),
    "SongManager":         ("core.songs",         "SongManager"),
    "ScoringEngine":       ("core.scoring",       "ScoringEngine"),
    "ToneDetector":        ("core.tone_detector", "ToneDetector"),
    # engine — heaviest, pulls most of the others transitively
    "SystemEngine":        ("core.engine",        "SystemEngine"),
}


def __getattr__(name):
    """PEP 562 hook — load heavy core submodules on first access."""
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module 'backend' has no attribute {name!r}")
    module_path, attr = target
    value = getattr(importlib.import_module(module_path), attr)
    globals()[name] = value  # cache so subsequent lookups skip __getattr__
    return value


def __dir__():
    return sorted({*globals(), *_LAZY_EXPORTS})


__all__ = [
    # Constants
    "SETTINGS_FILE", "SONGS_FILE", "ACTIVATION_FILE",
    "MANUAL_TIMELINES_FILE", "TONE_CACHE_FILE", "APP_CONFIG_FILE",
    "MIDI_PORT_NAME", "FFMPEG_LOCATION",
    "APP_DIR", "DATA_DIR", "RECORDINGS_DIR",
    # Eager classes
    "AppConfig", "ConfigManager", "ActivationManager",
    # Lazy classes / functions
    *_LAZY_EXPORTS.keys(),
]
