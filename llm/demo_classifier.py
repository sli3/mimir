"""
llm/demo_classifier.py — Cache-backed demo-mode classifier

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.

WHAT THIS FILE DOES
-------------------
This is the demo-mode replacement for ``SignalClassifier``. It loads a
JSON cache of pre-computed ``ClassificationResult`` objects keyed by
``(file_id, chunk_index)`` strings and returns them on ``classify()``
without any network call. The cache is produced offline by
``tools/generate_demo_cache.py``.

The classifier mirrors ``SignalClassifier``'s public signature so
downstream code (the scanner's AI loop, the dashboard) does not need to
know which classifier it is talking to.

WHY A SEPARATE CLASS (NOT SignalClassifier)
-------------------------------------------
Following the precedent set by ``llm/path_reasoner.py`` relative to
``SignalClassifier``: ``SignalClassifier`` carries live-scan state
(cooldown timers, LLM base URL, model name) and is designed for real
HTTP calls. Demo mode has different needs (no network, no cooldown, a
cache file) and different failure modes (cache miss, malformed cache).
Keeping the two classes separate prevents demo logic from leaking into
the live classifier and prevents live-scan cooldown state from
interfering with demo playback.

HOUSE CONTRACT
--------------
* ``check_connection()`` returns ``True`` immediately — there is no live
  LLM to probe.
* ``classify()`` NEVER raises. On cache miss or malformed input it returns
  the same fallback shape ``SignalClassifier`` uses
  (``signal_type="unavailable"``, ``confidence="low"``,
  ``confidence_score=0.0``).
* ``classify()`` NEVER falls through to live HTTP. The wire-level
  regression test in ``tests/llm/test_demo_classifier.py`` monkey-patches
  ``requests.post`` and ``requests.get`` to raise if called.
* The stable lookup key is read from ``fingerprint["mimir:demo_key"]``,
  which ``DemoProducer`` annotates before pushing a fingerprint to the
  queue.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from llm.classifier import ClassificationResult, SignalClassifier

logger = logging.getLogger(__name__)

# Cache size sanity cap (50 MB). Prevents a multi-gigabyte cache file from
# being slurped into memory in the worker thread.
_MAX_CACHE_SIZE_BYTES = 50_000_000


class DemoSignalClassifier(SignalClassifier):
    """Cache-backed subclass of SignalClassifier for ``--demo`` mode.

    Loads a JSON cache of pre-computed ``ClassificationResult`` objects
    and returns them on ``classify()`` without network calls. On any
    construction or lookup failure it falls back to the same safe shape
    ``SignalClassifier`` uses.
    """

    def __init__(
        self,
        cache_path: Path,
        device_driver: str = "hackrf",
    ) -> None:
        """Initialise the demo classifier from a cache file.

        Args:
            cache_path: Path to the JSON cache produced by
                ``tools/generate_demo_cache.py``. If the file is missing,
                malformed, oversized, or has an unexpected top-level shape,
                a warning is logged and ``self._cache`` is set to ``{}``.
                The classifier remains safe to use; cache misses will
                simply return fallback results.
            device_driver: Informational only — used in fallback reason
                strings for clarity. Default "hackrf".
        """
        # Initialise the parent with harmless defaults. These fields are
        # not used by the demo path, but inheriting from SignalClassifier
        # means some tests and type checks may inspect them.
        super().__init__(
            base_url="http://demo.local/v1",
            model="demo-cache",
            temperature=0.1,
            cooldown_sec=0.0,
            connect_timeout_sec=0.0,
        )
        self._cache_path = Path(cache_path)
        self._device_driver = str(device_driver)
        self._cache: dict[str, Any] = self._load_cache(self._cache_path)

    def _load_cache(self, cache_path: Path) -> dict[str, Any]:
        """Load and lightly validate the cache JSON.

        Returns an empty dict on any problem so construction never
        raises. Malformed individual entries are skipped at lookup time,
        not here.
        """
        try:
            if not cache_path.is_file():
                logger.warning(
                    "Demo cache not found at %s — all classifications will "
                    "return fallback results.",
                    cache_path,
                )
                return {}

            size = cache_path.stat().st_size
            if size > _MAX_CACHE_SIZE_BYTES:
                logger.warning(
                    "Demo cache at %s is %.2f MB, exceeding the %d MB cap — "
                    "refusing to load it into memory.",
                    cache_path,
                    size / 1_000_000,
                    _MAX_CACHE_SIZE_BYTES // 1_000_000,
                )
                return {}

            with cache_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "Demo cache at %s could not be loaded: %s — "
                "falling back to empty cache.",
                cache_path,
                exc,
            )
            return {}

        if not isinstance(data, dict) or "files" not in data:
            logger.warning(
                "Demo cache at %s has unexpected shape (expected top-level "
                "dict with 'files' key) — falling back to empty cache.",
                cache_path,
            )
            return {}

        return data

    def check_connection(self) -> bool:
        """Demo mode has no live LLM connection to probe.

        Returns ``True`` immediately so scan.py can skip the startup
        connectivity check without logging spurious warnings.
        """
        return True

    def classify(
        self,
        fingerprint: dict,
        neighbours: list,
        acma_allocations: list[dict] | None = None,
    ) -> ClassificationResult:
        """Return the cached ClassificationResult for this fingerprint.

        The lookup key is read from ``fingerprint["mimir:demo_key"]``,
        which has the form ``"<file_id>:<chunk_idx>"``. On cache hit the
        stored dict is unpacked into a ``ClassificationResult``. On any
        failure (missing key, malformed key, missing file/entry, or
        malformed entry fields) a fallback result is returned.

        Args:
            fingerprint: Dict from the fingerprint pipeline. Must carry
                ``mimir:demo_key`` for a cache hit.
            neighbours: Ignored — present for signature compatibility
                with ``SignalClassifier.classify()``.
            acma_allocations: Ignored — present for signature
                compatibility.

        Returns:
            ``ClassificationResult`` — always. Never raises.
        """
        key = fingerprint.get("mimir:demo_key")
        if not isinstance(key, str):
            return self._fallback_result(
                "Demo cache key missing — DemoProducer did not annotate the "
                "fingerprint with mimir:demo_key."
            )

        file_id, chunk_idx = self._parse_demo_key(key)
        if file_id is None:
            return self._fallback_result(
                f"Demo cache key malformed: {key!r} — expected "
                f"'<file_id>:<chunk_idx>'."
            )

        try:
            file_entry = self._cache.get("files", {}).get(file_id)
            if file_entry is None:
                return self._fallback_result(
                    f"Demo cache miss for key {key} — file {file_id} not "
                    f"covered by cached responses."
                )
            chunk_entry = file_entry.get("chunks", {}).get(chunk_idx)
            if chunk_entry is None:
                return self._fallback_result(
                    f"Demo cache miss for key {key} — chunk not covered by "
                    f"cached responses."
                )
            result = ClassificationResult(**chunk_entry)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "Demo cache entry for key %s is malformed: %s — "
                "returning fallback result.",
                key,
                exc,
            )
            return self._fallback_result(
                f"Demo cache entry malformed for key {key}: {exc}"
            )

        return result

    def _parse_demo_key(self, key: str) -> tuple[str | None, str | None]:
        """Split a demo key into (file_id, chunk_idx).

        The key format is ``"<file_id>:<chunk_idx>"``. The rightmost
        colon is the delimiter so a file_id containing colons is still
        parseable (file_ids are hex SHA-256 strings and contain none,
        but the delimiter choice is defensive).
        """
        if ":" not in key:
            return None, None
        file_id, _, chunk_idx = key.rpartition(":")
        if not file_id or not chunk_idx:
            return None, None
        return file_id, chunk_idx
