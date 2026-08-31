"""Unit tests for core.pipeline.frequency.freq_matches and FOCUS_FREQ_TOLERANCE_HZ."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.pipeline.frequency import (
    FOCUS_FREQ_TOLERANCE_HZ,
    freq_matches,
)


class TestFreqMatches:
    """Unit tests for freq_matches() and FOCUS_FREQ_TOLERANCE_HZ."""

    def test_real_bug_scenario_offset_within_tolerance(self):
        """The actual bug: 1_090_030_000 vs 1_090_000_000 (30 kHz offset) is True.

        Mirrors dashboard/frontend/src/utils/frequency.js tests in spirit
        but is backend Python. The 30 kHz offset is the observed value
        from capture_1090030000hz_*.sigmf-meta.
        """
        assert freq_matches(1_090_030_000, 1_090_000_000) is True

    def test_cross_band_aviation_vs_acars_is_false(self):
        """127_000_000 vs 129_125_000 (2.125 MHz gap) is False.

        Regression guard: a focusable aviation signal must NOT match an
        ACARS focus, and vice versa. The 2.125 MHz gap is the smallest
        in the focusable band set.
        """
        assert freq_matches(127_000_000, 129_125_000) is False

    def test_cross_band_ais_vs_ism_is_false(self):
        """162_000_000 vs 915_000_000 (753 MHz gap) is False."""
        assert freq_matches(162_000_000, 915_000_000) is False

    def test_none_a_returns_false(self):
        assert freq_matches(None, 1_090_000_000) is False

    def test_none_b_returns_false(self):
        assert freq_matches(1_090_030_000, None) is False

    def test_both_none_returns_false(self):
        assert freq_matches(None, None) is False

    def test_exact_equality_returns_true(self):
        assert freq_matches(98_000_000, 98_000_000) is True

    def test_at_tolerance_boundary_returns_true(self):
        """Exactly 100 kHz apart is inside the tolerance (inclusive)."""
        assert freq_matches(1_090_000_000, 1_090_100_000) is True

    def test_just_outside_tolerance_returns_false(self):
        """Just over 100 kHz apart is outside the tolerance."""
        assert freq_matches(1_090_000_000, 1_090_100_001) is False

    def test_default_tolerance_is_100khz(self):
        assert FOCUS_FREQ_TOLERANCE_HZ == 100_000

    def test_custom_tolerance_honoured(self):
        assert freq_matches(1_090_000_000, 1_090_200_000, tolerance_hz=250_000) is True
        assert freq_matches(1_090_000_000, 1_090_200_000, tolerance_hz=100_000) is False
        assert freq_matches(1_090_000_000, 1_090_200_000, tolerance_hz=50_000) is False

    def test_accepts_int_and_float(self):
        """Both int and float frequencies work."""
        assert freq_matches(1_090_000_000, 1_090_030_000.0) is True
        assert freq_matches(1_090_000_000.0, 1_090_030_000) is True

    def test_nan_returns_false(self):
        """NaN on either side returns False (NaN <= x is False in Python).

        Mirrors the JS-side test in
        dashboard/frontend/src/utils/frequency.js (which asserts the same).
        Documents and pins the implementation's NaN handling as a contract.
        """
        import math
        assert freq_matches(math.nan, 1_090_000_000) is False
        assert freq_matches(1_090_000_000, math.nan) is False
        assert freq_matches(math.nan, math.nan) is False

    def test_python_tolerance_matches_frontend_constant(self):
        """FOCUS_FREQ_TOLERANCE_HZ (Python) MUST equal FREQ_TOLERANCE_HZ (JS).

        The Phase 76 demo-mode bug was fundamentally a cross-language
        strict-equality mismatch — Fix 4 fixed the JS side, Fix 5 fixes
        the Python side. Both must use the same 100 kHz tolerance or a
        future edit to either side silently re-introduces the bug class
        (frontend filters emit but backend drops, or vice versa — harder
        to diagnose than the original all-or-nothing drop).

        Mirrors the project ADV-01 pattern (only HIGH_TURN_RATE had a
        JS↔Python contract test before this).
        """
        import re
        from pathlib import Path
        js_path = (
            Path(__file__).parent.parent.parent
            / "dashboard"
            / "frontend"
            / "src"
            / "utils"
            / "frequency.js"
        )
        js_source = js_path.read_text(encoding="utf-8")
        match = re.search(r"export\s+const\s+FREQ_TOLERANCE_HZ\s*=\s*(\d[\d_]*)", js_source)
        assert match is not None, (
            "Could not find `export const FREQ_TOLERANCE_HZ = <number>` in "
            f"{js_path}. If the JS constant was renamed, update this "
            "test (and the cross-language parity docstring in "
            "core/pipeline/frequency.py) to match."
        )
        js_value = int(match.group(1).replace("_", ""))
        assert FOCUS_FREQ_TOLERANCE_HZ == js_value, (
            f"Frontend JS tolerance ({js_value} Hz) does not match "
            f"backend Python tolerance ({FOCUS_FREQ_TOLERANCE_HZ} Hz). "
            "Both sides of the focus filter must agree or a real captured "
            "frequency can match one side and miss the other, silently "
            "re-introducing the Phase 76 Fix 5 bug class."
        )
