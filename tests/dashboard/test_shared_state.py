"""
tests/dashboard/test_shared_state.py
Mimir RF Scanner — Dashboard Shared State Tests

Tests for dashboard/shared_state.py constants.
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import dashboard.shared_state as shared_state
from dashboard.shared_state import (
    BAND_PROFILES,
    TRIGGER_ARMABLE_BANDS,
    band_key_for_freq,
    get_band_for_freq,
    get_last_trigger_snr,
    is_trigger_armed,
    set_last_trigger_snr,
    set_trigger_armed,
)


class TestBandProfiles:
    """Tests for the BAND_PROFILES constant."""

    def test_fm_broadcast_lna_gain_is_calibrated(self):
        """fm_broadcast lna_gain_db must be 24 after calibration."""
        assert BAND_PROFILES["fm_broadcast"]["lna_gain_db"] == 24

    def test_fm_broadcast_vga_gain_is_calibrated(self):
        """fm_broadcast vga_gain_db must be 26 after calibration."""
        assert BAND_PROFILES["fm_broadcast"]["vga_gain_db"] == 26

    def test_aviation_gains_unchanged(self):
        """aviation gains must remain at their pre-calibration values."""
        assert BAND_PROFILES["aviation"]["lna_gain_db"] == 16
        assert BAND_PROFILES["aviation"]["vga_gain_db"] == 20

    def test_adsb_gains_unchanged(self):
        """adsb gains must remain at their pre-calibration values."""
        assert BAND_PROFILES["adsb"]["lna_gain_db"] == 24
        assert BAND_PROFILES["adsb"]["vga_gain_db"] == 24

    def test_all_entries_have_signal_threshold_db(self):
        """Every BAND_PROFILES entry must have a positive signal_threshold_db key."""
        for name, profile in BAND_PROFILES.items():
            assert "signal_threshold_db" in profile, f"{name} missing signal_threshold_db"
            assert isinstance(profile["signal_threshold_db"], (int, float)), f"{name} signal_threshold_db not numeric"
            assert profile["signal_threshold_db"] > 0, f"{name} signal_threshold_db not positive"


    def test_ais_in_band_profiles(self):
        """ais entry must exist in BAND_PROFILES with correct center frequency."""
        assert "ais" in BAND_PROFILES
        assert BAND_PROFILES["ais"]["center_freq_hz"] == 162_000_000
        assert BAND_PROFILES["ais"]["signal_threshold_db"] > 0

    def test_ais_centre_freq_matches_constants(self):
        """AIS centre freq in BAND_PROFILES must match AU_AIS_CENTRE_FREQ_HZ."""
        from modules.ais.constants import AU_AIS_CENTRE_FREQ_HZ
        assert BAND_PROFILES["ais"]["center_freq_hz"] == AU_AIS_CENTRE_FREQ_HZ

    def test_ais_gains_match_aviation_acars(self):
        """AIS gains (lna=16, vga=20) match aviation and ACARS VHF-low peers."""
        assert BAND_PROFILES["ais"]["lna_gain_db"] == 16
        assert BAND_PROFILES["ais"]["vga_gain_db"] == 20


class TestGetBandForFreq:
    """Tests for the get_band_for_freq helper."""

    def test_known_freq_returns_profile(self):
        """get_band_for_freq returns a dict for a known center_freq_hz."""
        result = get_band_for_freq(98_000_000)
        assert result is not None
        assert result["signal_threshold_db"] == BAND_PROFILES["fm_broadcast"]["signal_threshold_db"]

    def test_unknown_freq_returns_none(self):
        """get_band_for_freq returns None for a frequency not in BAND_PROFILES."""
        result = get_band_for_freq(100_000_000)
        assert result is None

    def test_none_input_returns_none(self):
        """get_band_for_freq returns None when passed None."""
        result = get_band_for_freq(None)
        assert result is None

    def test_returns_copy_not_reference(self):
        """get_band_for_freq returns a copy — mutations do not affect BAND_PROFILES."""
        result = get_band_for_freq(98_000_000)
        result["signal_threshold_db"] = 999.0
        assert BAND_PROFILES["fm_broadcast"]["signal_threshold_db"] != 999.0

    def test_ais_band_profile_lookup(self):
        """get_band_for_freq returns the AIS profile for 162.000 MHz."""
        result = get_band_for_freq(162_000_000)
        assert result is not None
        assert result["center_freq_hz"] == 162_000_000
        assert result["signal_threshold_db"] > 0

    def test_ais_ch1_freq_no_longer_matches(self):
        """get_band_for_freq(161_975_000) returns None after centre freq change to
        162.000 MHz. This documents the known frontend/backend gap: the frontend still
        sends 161.975 MHz (CH1) when the user clicks AIS, so the AIS band profile gains
        and threshold are not applied until the frontend is updated."""
        result = get_band_for_freq(161_975_000)
        assert result is None


class TestBandKeyForFreq:
    """Tests for the band_key_for_freq helper (Phase 37).

    band_key_for_freq returns the BAND_PROFILES KEY (not the profile dict),
    which is what band_supported_by_device() needs for the scan loop's
    unsupported-band guard.
    """

    def test_exact_match_known_bands(self):
        """Exact centre frequencies return their band keys."""
        assert band_key_for_freq(98_000_000) == "fm_broadcast"
        assert band_key_for_freq(1_090_000_000) == "adsb"
        assert band_key_for_freq(162_000_000) == "ais"

    def test_exact_match_98mhz_returns_fm_broadcast_not_noise_floor(self):
        """98 MHz must resolve to fm_broadcast, never noise_floor.

        Both profiles sit at 98 MHz; the first match in definition order
        wins, mirroring get_band_for_freq. The dashboard must never select
        the zero-gain noise_floor reference from a frequency change.
        """
        assert band_key_for_freq(98_000_000) == "fm_broadcast"
        assert band_key_for_freq(98_000_000) != "noise_floor"

    def test_off_centre_freq_returns_nearest_key(self):
        """100 MHz is nearer to FM (98 MHz) than aviation (127 MHz)."""
        assert band_key_for_freq(100_000_000) == "fm_broadcast"

    def test_nearest_excludes_noise_floor(self):
        """The nearest-match fallback must never return noise_floor.

        98.5 MHz is only 500 kHz from the noise_floor centre (98 MHz) but
        noise_floor is excluded from the candidate set, so the result is
        fm_broadcast.
        """
        assert band_key_for_freq(98_500_000) != "noise_floor"
        assert band_key_for_freq(98_500_000) == "fm_broadcast"

    def test_none_input_returns_none(self):
        """None in, None out — mirrors the other band helpers."""
        assert band_key_for_freq(None) is None

    def test_ais_off_centre_returns_ais(self):
        """161.5 MHz is nearer to AIS (162 MHz) than APRS (145.175 MHz)."""
        assert band_key_for_freq(161_500_000) == "ais"


class TestCaptureTriggerState:
    """Tests for the Phase 63 SNR-edge auto-capture trigger state.

    The armed flags and last-SNR readings are module-level dicts shared
    across the whole test session, so every test snapshots and restores
    them via the autouse fixture below.
    """

    @pytest.fixture(autouse=True)
    def reset_trigger_state(self):
        """Snapshot and restore module-level trigger state around each test."""
        with shared_state.trigger_state_lock:
            saved_armed = dict(shared_state.trigger_armed)
            saved_snr = dict(shared_state._trigger_last_snr)
        yield
        with shared_state.trigger_state_lock:
            shared_state.trigger_armed.clear()
            shared_state.trigger_armed.update(saved_armed)
            shared_state._trigger_last_snr.clear()
            shared_state._trigger_last_snr.update(saved_snr)

    def test_armable_bands_are_exactly_the_four_calibrated_bands(self):
        """TRIGGER_ARMABLE_BANDS must match the four BAND_PROFILES entries
        whose signal_threshold_db carries a real "# Calibrated:" comment."""
        assert TRIGGER_ARMABLE_BANDS == frozenset(
            {"fm_broadcast", "aprs", "ism", "adsb"}
        )

    def test_default_state_is_disarmed_with_no_snr(self):
        """Every armable band starts disarmed with no previous SNR reading."""
        for band in TRIGGER_ARMABLE_BANDS:
            assert is_trigger_armed(band) is False
            assert get_last_trigger_snr(band) is None

    def test_set_trigger_armed_rejects_non_armable_band(self):
        """A band outside TRIGGER_ARMABLE_BANDS raises ValueError, and the
        message must name the valid bands (mirroring capture.py's style)."""
        with pytest.raises(ValueError) as excinfo:
            set_trigger_armed("aviation", True)
        message = str(excinfo.value)
        assert "aviation" in message
        for valid in ("fm_broadcast", "aprs", "ism", "adsb"):
            assert valid in message

    def test_set_trigger_armed_rejects_noise_floor(self):
        """noise_floor is a baseline reference, not a signal band - it must
        be rejected even though it is a valid BAND_PROFILES key."""
        assert "noise_floor" in BAND_PROFILES
        with pytest.raises(ValueError):
            set_trigger_armed("noise_floor", True)

    def test_arm_bands_independently(self):
        """Arming one band must not arm any other."""
        set_trigger_armed("ism", True)
        assert is_trigger_armed("ism") is True
        for band in ("fm_broadcast", "aprs", "adsb"):
            assert is_trigger_armed(band) is False

    def test_disarm_after_arm(self):
        """Arming then disarming returns the band to not-armed."""
        set_trigger_armed("adsb", True)
        assert is_trigger_armed("adsb") is True
        set_trigger_armed("adsb", False)
        assert is_trigger_armed("adsb") is False

    def test_is_trigger_armed_unknown_band_returns_false_no_raise(self):
        """An unknown band key reads as not-armed; the hot scan loop must
        never see an exception from this getter."""
        assert is_trigger_armed("not_a_band") is False

    def test_last_trigger_snr_round_trip_per_band(self):
        """Setting the last SNR for one band must not affect any other."""
        set_last_trigger_snr("ism", 12.5)
        assert get_last_trigger_snr("ism") == 12.5
        assert get_last_trigger_snr("adsb") is None
        assert get_last_trigger_snr("fm_broadcast") is None

    def test_last_trigger_snr_getter_unknown_band_returns_none(self):
        """The getter is defensive: unknown keys read as None, no raise."""
        assert get_last_trigger_snr("not_a_band") is None

    def test_set_last_trigger_snr_accepts_none(self):
        """None is a valid stored value (fingerprint produced no SNR)."""
        set_last_trigger_snr("aprs", 9.0)
        set_last_trigger_snr("aprs", None)
        assert get_last_trigger_snr("aprs") is None
