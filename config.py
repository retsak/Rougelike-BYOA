from pathlib import Path

ASSETS_DIR = Path(__file__).parent / "Assets"
BASIC_ENEMIES_DIR = ASSETS_DIR / "Basic Enemies"
BOSSES_DIR = ASSETS_DIR / "Bosses"
HERO_DIR = ASSETS_DIR / "Hero"
BACKGROUND_DIR = ASSETS_DIR / "Backgrounds"
AUDIO_DIR = ASSETS_DIR / "Audio"

# --- Text-To-Speech (Dungeon Master Voice) Configuration ---
# Master toggle for enabling/disabling spoken narration.
TTS_ENABLED: bool = True
# OpenAI TTS model (supports voices like 'onyx').
TTS_MODEL: str = "gpt-4o-mini-tts"
# Voice name to use for narration.
TTS_VOICE: str = "onyx"
# Audio format requested from the API (wav easiest for playback).
TTS_FORMAT: str = "wav"
# Maximum characters per chunk sent to TTS (long narratives are split to avoid latency/timeouts).
TTS_MAX_CHARS: int = 600
# Playback volume scaling (0.0 - 1.0 applied client-side after synthesis if supported)
TTS_VOLUME: float = 0.9
# Speaking rate multiplier (1.0 = normal). Implemented by naive frame duplication/drop or API param if available.
TTS_RATE: float = 1.0
# Allow offline fallback (simple tone) when API unavailable.
TTS_OFFLINE_FALLBACK: bool = True

# Ambient audio
AMBIENT_VOLUME: float = 0.35  # 0.0 - 1.0
