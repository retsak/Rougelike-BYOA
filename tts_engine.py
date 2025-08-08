"""OpenAI Onyx voice TTS engine for Dungeon Master narration.

Non-blocking, queued playback using OpenAI's speech synthesis endpoint.
"""
from __future__ import annotations

import os
import io
import time
import wave
import threading
import queue
from typing import List

import requests

try:
    import simpleaudio as sa  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    sa = None

try:
    from config import (
        TTS_ENABLED,
        TTS_MODEL,
        TTS_VOICE,
        TTS_FORMAT,
        TTS_MAX_CHARS,
    )
except Exception:  # pragma: no cover - fallback defaults
    TTS_ENABLED = True
    TTS_MODEL = "gpt-4o-mini-tts"
    TTS_VOICE = "onyx"
    TTS_FORMAT = "wav"
    TTS_MAX_CHARS = 600

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
API_URL = "https://api.openai.com/v1/audio/speech"


def _chunk_text(text: str, limit: int) -> List[str]:
    if len(text) <= limit:
        return [text]
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            # Try to split on sentence boundary
            dot = text.rfind(". ", start, end)
            if dot == -1:
                dot = text.rfind("! ", start, end)
            if dot == -1:
                dot = text.rfind("? ", start, end)
            if dot != -1 and dot + 2 - start > limit * 0.5:
                end = dot + 2
        chunks.append(text[start:end].strip())
        start = end
    return [c for c in chunks if c]


class OpenAITTS:
    def __init__(self, enabled: bool) -> None:
        self.enabled = bool(enabled) and bool(OPENAI_API_KEY)
        self._q: "queue.Queue[str | None]" = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if not OPENAI_API_KEY:
            print("[TTS] OPENAI_API_KEY not set; narration voice disabled.")
        if sa is None:
            print("[TTS] simpleaudio not available; install it to hear narration.")

    def speak(self, text: str) -> None:
        if not self.enabled or not text:
            return
        for chunk in _chunk_text(text, TTS_MAX_CHARS):
            self._q.put(chunk)

    def shutdown(self) -> None:
        if self.enabled:
            self._q.put(None)
            # Do not join to avoid hanging on exit; thread is daemon.

    # Internal worker
    def _run(self) -> None:  # pragma: no cover - background thread
        while True:
            item = self._q.get()
            if item is None:
                break
            self._synth_and_play(item)
            time.sleep(0.05)

    def _synth_and_play(self, text: str) -> None:
        try:
            payload = {
                "model": TTS_MODEL,
                "voice": TTS_VOICE,
                "input": text,
                # Some API variants expect 'format', others 'response_format'; send both.
                "format": TTS_FORMAT,
                "response_format": TTS_FORMAT,
            }
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
                "Accept": f"audio/{'wav' if TTS_FORMAT=='wav' else '*'}",
            }
            r = requests.post(API_URL, json=payload, headers=headers, timeout=90)
            ct = r.headers.get("Content-Type", "").lower()
            if r.status_code != 200:
                # Try to extract JSON error if present
                snippet = r.text[:200].replace('\n', ' ')
                print(f"[TTS] HTTP {r.status_code} ({ct}): {snippet}")
                return
            data = r.content
            # Diagnostics: verify WAV header if requested
            if TTS_FORMAT == "wav":
                if not data.startswith(b"RIFF"):
                    # Possibly JSON error masquerading, or MP3 (ID3) despite request.
                    prefix = data[:16]
                    if ct.startswith("application/json"):
                        try:
                            import json as _json
                            err_obj = _json.loads(data.decode(errors='ignore'))
                            print(f"[TTS] JSON instead of WAV: {err_obj}")
                        except Exception:
                            print(f"[TTS] Non-WAV JSON-like response: {prefix!r}")
                    elif data.startswith(b"ID3") or data[0:1] == b"\xff":
                        print("[TTS] Received MP3 data while expecting WAV; playback not implemented for MP3.\n"
                              "      Set TTS_FORMAT='mp3' or install pydub/ffmpeg for MP3 support.")
                    else:
                        print(f"[TTS] Unexpected audio header (first 16 bytes): {prefix!r}")
                    return
                self._play_wav_bytes(data)
            else:
                print(f"[TTS] Format {TTS_FORMAT} playback not implemented.")
        except Exception as e:  # pragma: no cover
            print(f"[TTS] Exception: {e}")

    def _play_wav_bytes(self, raw: bytes) -> None:
        if sa is None:
            return
        with wave.open(io.BytesIO(raw)) as wf:
            frames = wf.readframes(wf.getnframes())
            wave_obj = sa.WaveObject(frames, wf.getnchannels(), wf.getsampwidth(), wf.getframerate())
            # Block until this chunk finishes so ordering is preserved and audio doesn't overlap.
            try:
                play_obj = wave_obj.play()
                play_obj.wait_done()
            except Exception as e:
                print(f"[TTS] Playback error: {e}")


voice = OpenAITTS(enabled=TTS_ENABLED)


def dm_say(text: str, also_print: bool = True) -> None:
    if also_print:
        print(text)
    voice.speak(text)


__all__ = ["dm_say", "voice", "OpenAITTS"]
