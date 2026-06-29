"""Optional neural text-to-speech engine backed by ``edge-tts``.

This synthesises chat messages with Microsoft Edge's online neural voices
(e.g. ``ru-RU-SvetlanaNeural``), which sound far more natural than the browser's
built-in ``speechSynthesis`` voices. It is an *optional* engine: the default TTS
path stays in the browser. ``edge-tts`` is imported lazily inside the methods so
the rest of the app runs, and ``py_compile`` succeeds, even when it is not
installed.

Design (per architecture review):
- A single synthesis worker drains a bounded ``asyncio.Queue`` so concurrent
  requests serialise instead of hammering the remote service; a full queue
  surfaces as HTTP 503 rather than blocking the event loop.
- Repeated phrases (greetings, catch-phrases) are common in chat, so results are
  memoised in a small manual LRU map keyed by ``(text, voice)`` — avoiding a hard
  dependency on ``cachetools`` and the extra PyInstaller bundling risk.
- Every remote call is wrapped in a 5 s timeout; on timeout/network error the
  caller gets an exception which the endpoint translates to 503. Offline (e.g. a
  frozen binary with no network) therefore degrades gracefully instead of
  crashing.
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from typing import Optional

log = logging.getLogger("tts_neural")

_QUEUE_MAXSIZE = 5
_CACHE_MAXSIZE = 50
_MAX_TEXT = 200
_SYNTH_TIMEOUT_SECONDS = 5.0


def is_available() -> bool:
    """True when ``edge-tts`` can be imported (i.e. the neural engine is usable)."""
    try:
        import edge_tts  # noqa: F401
    except Exception:
        return False
    return True


class NeuralTTSEngine:
    def __init__(self) -> None:
        self._queue: Optional[asyncio.Queue] = None
        self._worker: Optional[asyncio.Task] = None
        self._cache: "OrderedDict[tuple[str, str], bytes]" = OrderedDict()
        self._voices_cache: Optional[list[dict]] = None

    def start(self) -> None:
        if self._worker is not None:
            return
        self._queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        self._worker = asyncio.create_task(self._run_worker())

    async def aclose(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None
        self._queue = None

    async def _run_worker(self) -> None:
        assert self._queue is not None
        while True:
            text, voice, fut = await self._queue.get()
            try:
                audio = await self._synthesize_now(text, voice)
                if not fut.done():
                    fut.set_result(audio)
            except Exception as exc:  # noqa: BLE001 - propagate to the awaiting caller
                if not fut.done():
                    fut.set_exception(exc)
            finally:
                self._queue.task_done()

    async def synthesize(self, text: str, voice: str) -> bytes:
        """Return MP3 bytes for ``text`` in ``voice``.

        Raises ``RuntimeError`` if the engine is not started, ``QueueFull`` when
        the backlog is saturated (-> 503), or a synthesis/timeout error from the
        worker.
        """
        text = (text or "").strip()[:_MAX_TEXT]
        if not text:
            raise ValueError("empty text")
        voice = (voice or "").strip()
        if not voice:
            raise ValueError("missing voice")

        key = (text, voice)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached

        if self._queue is None:
            raise RuntimeError("neural TTS engine not started")

        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        # Non-blocking put: a full queue raises asyncio.QueueFull -> endpoint 503.
        self._queue.put_nowait((text, voice, fut))
        audio = await fut

        self._cache[key] = audio
        self._cache.move_to_end(key)
        while len(self._cache) > _CACHE_MAXSIZE:
            self._cache.popitem(last=False)
        return audio

    async def _synthesize_now(self, text: str, voice: str) -> bytes:
        import edge_tts  # lazy: keeps the module importable without the dep

        async def _do() -> bytes:
            chunks = bytearray()
            communicate = edge_tts.Communicate(text, voice)
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio" and chunk.get("data"):
                    chunks.extend(chunk["data"])
            return bytes(chunks)

        return await asyncio.wait_for(_do(), timeout=_SYNTH_TIMEOUT_SECONDS)

    async def list_voices(self, locale_prefix: str = "ru") -> list[dict]:
        if self._voices_cache is None:
            import edge_tts  # lazy

            raw = await asyncio.wait_for(
                edge_tts.list_voices(), timeout=_SYNTH_TIMEOUT_SECONDS
            )
            self._voices_cache = [
                {
                    "id": v.get("ShortName", ""),
                    "name": v.get("FriendlyName", v.get("ShortName", "")),
                    "gender": v.get("Gender", ""),
                    "locale": v.get("Locale", ""),
                }
                for v in raw
            ]
        prefix = (locale_prefix or "").lower()
        if not prefix:
            return list(self._voices_cache)
        return [v for v in self._voices_cache if v["locale"].lower().startswith(prefix)]
