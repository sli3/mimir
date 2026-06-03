"""
llm/acma_reference.py — ACMA Spectrum Plan Reference

Loads and queries data/frequency_reference.json — the structured ACMA
Australian Radiofrequency Spectrum Plan. Provides range-based lookup for
determining which spectrum allocations cover a given frequency.

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       Jurisdiction: AU/SA. Authority: ACMA.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_PATH = "data/frequency_reference.json"


class AcmaReference:
    """
    ACMA frequency allocation reference.

    Loads the ACMA spectrum plan JSON at initialisation and provides
    range-based lookup of allocations for a given frequency.

    Usage:
        ref = AcmaReference()
        allocations = ref.lookup(98_000_000)
        # Returns list of dicts with freq_start_mhz, freq_end_mhz,
        # services, mimir_band, etc.
    """

    def __init__(self, path: str = _DEFAULT_PATH) -> None:
        self._entries: list[dict] = []
        try:
            p = Path(path)
            if not p.exists():
                logger.warning("ACMA reference not found at %s — empty lookup", path)
                return
            text = p.read_text(encoding="utf-8")
            self._entries = json.loads(text)
            logger.debug("Loaded %d ACMA frequency allocations", len(self._entries))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "Failed to load ACMA reference from %s: %s — empty lookup", path, exc
            )

    def lookup(self, freq_hz: float) -> list[dict]:
        if not self._entries:
            return []
        freq_mhz = freq_hz / 1_000_000
        return [
            e
            for e in self._entries
            if e["freq_start_mhz"] <= freq_mhz <= e["freq_end_mhz"]
        ]
