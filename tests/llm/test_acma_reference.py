"""
tests/llm/test_acma_reference.py — AcmaReference Unit Tests

PURPOSE
───────
Tests the ACMA spectrum plan reference loader and lookup logic in
isolation. Uses the real data/frequency_reference.json for range-match
tests and synthetic inputs for error-path tests.

Run with:
    uv run --system-site-packages python -m pytest tests/llm/test_acma_reference.py -v
"""

import json
import sys
import os
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from llm.acma_reference import AcmaReference


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def acma_ref() -> AcmaReference:
    """AcmaReference instance using the real frequency_reference.json."""
    return AcmaReference()


# ══════════════════════════════════════════════════════════════════════════
# GROUP 1 — Range match (uses real data file)
# ══════════════════════════════════════════════════════════════════════════

class TestRangeMatch:
    """Tests that range-based lookup returns correct allocations."""

    def test_fm_broadcast(self, acma_ref):
        """98 MHz returns at least one entry with mimir_band fm_broadcast."""
        results = acma_ref.lookup(98_000_000)
        assert len(results) > 0
        assert any(r["mimir_band"] == "fm_broadcast" for r in results)

    def test_aprs(self, acma_ref):
        """145.175 MHz returns at least one entry with mimir_band aprs."""
        results = acma_ref.lookup(145_175_000)
        assert len(results) > 0
        assert any(r["mimir_band"] == "aprs" for r in results)

    def test_ism_lora(self, acma_ref):
        """915 MHz returns at least one entry with mimir_band ism_lora."""
        results = acma_ref.lookup(915_000_000)
        assert len(results) > 0
        assert any(r["mimir_band"] == "ism_lora" for r in results)

    def test_adsb(self, acma_ref):
        """1090 MHz returns at least one entry with mimir_band adsb."""
        results = acma_ref.lookup(1_090_000_000)
        assert len(results) > 0
        assert any(r["mimir_band"] == "adsb" for r in results)

    def test_out_of_range_returns_empty(self, acma_ref):
        """0 Hz (below any ACMA entry) returns an empty list."""
        results = acma_ref.lookup(0)
        assert results == []


# ══════════════════════════════════════════════════════════════════════════
# GROUP 2 — Error handling
# ══════════════════════════════════════════════════════════════════════════

class TestErrorHandling:
    """Tests that AcmaReference degrades gracefully on bad inputs."""

    def test_missing_file_returns_empty(self):
        """Non-existent path does not raise and returns empty list."""
        ref = AcmaReference("/nonexistent/path.json")
        results = ref.lookup(98_000_000)
        assert results == []

    @patch("llm.acma_reference.Path.read_text")
    def test_corrupted_file_returns_empty(self, mock_read):
        """JSON decode error does not raise and returns empty list."""
        mock_read.side_effect = json.JSONDecodeError("bad json", "", 0)
        ref = AcmaReference()
        results = ref.lookup(98_000_000)
        assert results == []


# ══════════════════════════════════════════════════════════════════════════
# GROUP 3 — Data integrity
# ══════════════════════════════════════════════════════════════════════════

class TestDataIntegrity:
    """Tests that returned entries have the expected structure."""

    def test_entries_have_expected_fields(self, acma_ref):
        """Each returned dict contains freq_start_mhz, freq_end_mhz,
        services, mimir_band."""
        results = acma_ref.lookup(98_000_000)
        assert len(results) > 0
        for entry in results:
            assert "freq_start_mhz" in entry
            assert "freq_end_mhz" in entry
            assert "services" in entry
            assert "mimir_band" in entry

    def test_inclusive_lower_bound(self, acma_ref):
        """87.5 MHz (exact lower bound of FM entry) returns fm_broadcast."""
        results = acma_ref.lookup(87_500_000)
        assert len(results) > 0
        assert any(r["mimir_band"] == "fm_broadcast" for r in results)

    def test_inclusive_upper_bound(self, acma_ref):
        """108 MHz (exact upper bound of FM entry) returns fm_broadcast."""
        results = acma_ref.lookup(108_000_000)
        assert len(results) > 0
        assert any(r["mimir_band"] == "fm_broadcast" for r in results)

    def test_entries_include_notes_field(self, acma_ref):
        """Each returned dict contains a 'notes' key (may be empty string)."""
        results = acma_ref.lookup(98_000_000)
        assert len(results) > 0
        for entry in results:
            assert "notes" in entry, (
                "ACMA lookup result must include a 'notes' key so the "
                "classifier can pass it through to the LLM prompt."
            )

    def test_notes_preserved_for_entries_with_notes(self, acma_ref):
        """Entries that have non-empty notes in the JSON retain them."""
        # 406.0-406.1 MHz epirb_plb entry has notes
        results = acma_ref.lookup(406_000_000)
        assert len(results) > 0
        epirb = [r for r in results if r.get("mimir_band") == "epirb_plb"]
        assert len(epirb) > 0
        for entry in epirb:
            assert entry.get("notes", "") != "", (
                "epirb_plb entries in the 406.0-406.1 MHz range should "
                "have non-empty notes in the ACMA reference file."
            )


# ══════════════════════════════════════════════════════════════════════════
# GROUP 4 — TX safety
# ══════════════════════════════════════════════════════════════════════════

class TestSafetyChecks:
    """TX safety and AU legal compliance checks."""

    def test_no_tx_patterns_in_acma_reference(self):
        """
        acma_reference.py must contain no transmit-related patterns.
        """
        ref_path = Path(__file__).parent.parent.parent / "llm" / "acma_reference.py"
        assert ref_path.exists(), (
            f"acma_reference.py not found at expected path: {ref_path}"
        )
        source = ref_path.read_text()
        forbidden = [
            "writeStream",
            "SOAPY_SDR_TX",
            "hackrf_start_tx",
            "set_tx_gain",
            "set_tx_frequency",
            "setupTxStream",
            "activateTxStream",
        ]
        for pattern in forbidden:
            assert pattern not in source, (
                f"TX pattern '{pattern}' found in acma_reference.py — "
                f"this is a TX safety violation. Remove it immediately."
            )

    def test_acma_reference_does_not_import_sdr(self):
        """acma_reference.py must not import any SDR library."""
        ref_path = Path(__file__).parent.parent.parent / "llm" / "acma_reference.py"
        source = ref_path.read_text()
        sdr_imports = ["SoapySDR", "hackrf", "rtlsdr"]
        for imp in sdr_imports:
            assert imp not in source, (
                f"SDR import '{imp}' found in acma_reference.py — "
                f"this module should only deal with ACMA reference data."
            )
