"""
tests/dashboard/test_pluto_band_profiles.py
Mimir RF Scanner — Pluto Band Support Tests

Tests for the PLUTO_BAND_PROFILES dict and band_supported_by_device()
added to dashboard/shared_state.py in Phase 36.
No hardware required — these are pure data and logic tests.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.device.profiles import DEVICE_PROFILES
from dashboard.shared_state import (
    BAND_PROFILES,
    PLUTO_BAND_PROFILES,
    band_supported_by_device,
)


class TestPlutoBandProfiles:
    """Tests for the PLUTO_BAND_PROFILES additive override dict."""

    def test_keys_match_band_profiles_exactly(self):
        """All eight band keys present, same spelling as BAND_PROFILES."""
        assert set(PLUTO_BAND_PROFILES.keys()) == set(BAND_PROFILES.keys())

    def test_exactly_ism_and_adsb_are_supported(self):
        """Only ism and adsb have supported=True; the other six are False."""
        supported = {
            band
            for band, entry in PLUTO_BAND_PROFILES.items()
            if entry["supported"]
        }
        assert supported == {"ism", "adsb"}

    def test_no_entry_restates_inherited_keys(self):
        """center_freq_hz and crop_half_width_hz are inherited from
        BAND_PROFILES. Restating them here would break the additive-
        override rule, so this guards against future drift."""
        for band, entry in PLUTO_BAND_PROFILES.items():
            assert "center_freq_hz" not in entry, band
            assert "crop_half_width_hz" not in entry, band

    def test_unsupported_entries_carry_no_gain_or_threshold(self):
        """Unsupported bands must not carry gain_db or signal_threshold_db."""
        for band, entry in PLUTO_BAND_PROFILES.items():
            if not entry["supported"]:
                assert "gain_db" not in entry, band
                assert "signal_threshold_db" not in entry, band

    def test_unsupported_entries_carry_a_non_empty_reason(self):
        """Every unsupported band explains why it is unsupported."""
        for band, entry in PLUTO_BAND_PROFILES.items():
            if not entry["supported"]:
                assert isinstance(entry.get("reason"), str), band
                assert entry["reason"].strip(), band

    def test_supported_flag_agrees_with_pluto_frequency_range(self):
        """CROSS-CHECK: for each band, the declared supported flag must
        agree with whether that band's centre frequency (from
        BAND_PROFILES) falls inside Pluto's physical tuning range.

        Support is declared by the flag, not derived from the range —
        but this test proves the flag and the hardware range have not
        drifted apart. If someone later adds a band or edits a frequency
        and forgets the flag, this fails."""
        pluto = DEVICE_PROFILES["plutosdr"]
        for band, entry in PLUTO_BAND_PROFILES.items():
            centre_hz = BAND_PROFILES[band]["center_freq_hz"]
            within_range = (
                pluto["min_freq_hz"] <= centre_hz <= pluto["max_freq_hz"]
            )
            assert entry["supported"] == within_range, (
                f"{band}: supported={entry['supported']} but centre "
                f"{centre_hz} Hz within Pluto range is {within_range}"
            )


class TestBandSupportedByDevice:
    """Tests for the band_supported_by_device helper."""

    def test_hackrf_supports_all_eight_bands(self):
        """HackRF's 1 MHz–6 GHz range covers every band in the plan.
        Asserted per band rather than asserting the function returns True
        unconditionally."""
        assert len(BAND_PROFILES) == 8
        for band in BAND_PROFILES:
            assert band_supported_by_device(band, "hackrf") is True, band

    def test_plutosdr_matches_supported_flag_for_all_bands(self):
        """Pluto support follows the PLUTO_BAND_PROFILES flag exactly."""
        for band in BAND_PROFILES:
            expected = PLUTO_BAND_PROFILES[band]["supported"]
            assert band_supported_by_device(band, "plutosdr") == expected, band

    def test_unknown_band_raises_keyerror(self):
        """An unrecognised band name raises KeyError naming the band."""
        with pytest.raises(KeyError, match="not_a_band"):
            band_supported_by_device("not_a_band", "hackrf")

    def test_unknown_device_raises_keyerror(self):
        """An unrecognised device driver raises KeyError naming the device."""
        with pytest.raises(KeyError, match="not_a_device"):
            band_supported_by_device("fm_broadcast", "not_a_device")


class TestBandProfilesUnmodified:
    """Guards that the Phase 36 append did not restructure BAND_PROFILES."""

    def test_all_eight_original_keys_still_present(self):
        expected = {
            "fm_broadcast", "aviation", "acars", "aprs",
            "ais", "ism", "adsb", "noise_floor",
        }
        assert set(BAND_PROFILES.keys()) == expected

    def test_fm_broadcast_still_uses_split_gain_keys(self):
        """fm_broadcast keeps its lna_gain_db / vga_gain_db keys — proof
        the append did not restructure any existing entry."""
        assert "lna_gain_db" in BAND_PROFILES["fm_broadcast"]
        assert "vga_gain_db" in BAND_PROFILES["fm_broadcast"]
