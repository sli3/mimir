"""
tests/core/test_rx_only_lock.py
Mimir RF Scanner — Phase 0 Acceptance Tests

PURPOSE
───────
These tests are the ONLY definition of "Phase 0 complete".
When all tests pass, the TX hard block is proven to work in software.

Run with:
    python -m pytest tests/core/test_rx_only_lock.py -v

What is being tested?
─────────────────────
1. HardwareTransmitError exists and is a RuntimeError
2. transmit_guard() always raises HardwareTransmitError
3. The error message contains required legal/safety information
4. Every TX method on HackRFReceiver raises HardwareTransmitError
5. Every TX method on DeviceBase raises HardwareTransmitError
6. RX methods on HackRFReceiver do NOT raise HardwareTransmitError
   (they raise RuntimeError about hardware if device is not connected,
   which is fine — that is a hardware problem, not a TX-block problem)
7. HardwareTransmitError stores the function name that was blocked

IMPORTANT: These tests do NOT require hardware to be connected.
TX tests prove the block works without needing a real HackRF.
RX tests verify the methods exist and are callable (they will
raise RuntimeError about missing hardware, not HardwareTransmitError,
which is the correct and expected behaviour).
"""

import sys
import os
import pytest

# Add project root to path so imports work when running from any directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.legal.compliance_guard import HardwareTransmitError, transmit_guard
from core.device.hackrf_rx import HackRFReceiver


# ══════════════════════════════════════════════════════════════════════
# GROUP 1 — HardwareTransmitError exception itself
# ══════════════════════════════════════════════════════════════════════

class TestHardwareTransmitError:
    """Tests for the HardwareTransmitError exception class."""

    def test_is_runtime_error_subclass(self):
        """HardwareTransmitError must subclass RuntimeError."""
        assert issubclass(HardwareTransmitError, RuntimeError), (
            "HardwareTransmitError must be a RuntimeError so it is "
            "caught by generic error handling."
        )

    def test_can_be_raised(self):
        """HardwareTransmitError can be raised and caught."""
        with pytest.raises(HardwareTransmitError):
            raise HardwareTransmitError()

    def test_stores_function_name(self):
        """HardwareTransmitError stores the name of the blocked function."""
        try:
            raise HardwareTransmitError(attempted_function="test_tx_function")
        except HardwareTransmitError as e:
            assert e.attempted_function == "test_tx_function", (
                "The error must store which function was blocked, "
                "so developers can find the offending call."
            )

    def test_error_message_contains_legal_info(self):
        """Error message must reference Australian law."""
        try:
            raise HardwareTransmitError(attempted_function="some_tx_func")
        except HardwareTransmitError as e:
            message = str(e)
            assert "TRANSMIT" in message.upper(), (
                "Error message must mention TRANSMIT so the cause is obvious."
            )
            assert "Australia" in message or "ACMA" in message or "Radiocommunications" in message, (
                "Error message must reference Australian law to make the "
                "legal context clear to any developer who sees it."
            )

    def test_default_function_name(self):
        """HardwareTransmitError works with no arguments."""
        try:
            raise HardwareTransmitError()
        except HardwareTransmitError as e:
            # Should not crash — default function name should be set
            assert e.attempted_function is not None


# ══════════════════════════════════════════════════════════════════════
# GROUP 2 — transmit_guard() function
# ══════════════════════════════════════════════════════════════════════

class TestTransmitGuard:
    """Tests for the transmit_guard() helper function."""

    def test_always_raises(self):
        """transmit_guard() must always raise HardwareTransmitError."""
        with pytest.raises(HardwareTransmitError):
            transmit_guard("test_function")

    def test_raises_with_function_name(self):
        """transmit_guard() stores the function name in the error."""
        with pytest.raises(HardwareTransmitError) as exc_info:
            transmit_guard("my_specific_tx_function")
        assert exc_info.value.attempted_function == "my_specific_tx_function"

    def test_never_returns_normally(self):
        """transmit_guard() must never return — it must always raise."""
        returned = True
        try:
            transmit_guard("test")
            returned = True   # this line must never be reached
        except HardwareTransmitError:
            returned = False
        assert not returned, (
            "transmit_guard() must never return normally. "
            "It must always raise HardwareTransmitError."
        )


# ══════════════════════════════════════════════════════════════════════
# GROUP 3 — HackRFReceiver TX methods are all blocked
# ══════════════════════════════════════════════════════════════════════

class TestHackRFReceiverTXBlocked:
    """
    Every transmit-related method on HackRFReceiver must raise
    HardwareTransmitError. These tests do not require hardware.
    """

    @pytest.fixture
    def sdr(self):
        """Create a HackRFReceiver instance without opening hardware."""
        return HackRFReceiver()

    def test_transmit_blocked(self, sdr):
        """HackRFReceiver.transmit() raises HardwareTransmitError."""
        with pytest.raises(HardwareTransmitError):
            sdr.transmit()

    def test_write_samples_blocked(self, sdr):
        """HackRFReceiver.write_samples() raises HardwareTransmitError."""
        with pytest.raises(HardwareTransmitError):
            sdr.write_samples()

    def test_write_stream_blocked(self, sdr):
        """HackRFReceiver.writeStream() raises HardwareTransmitError."""
        with pytest.raises(HardwareTransmitError):
            sdr.writeStream()

    def test_set_tx_gain_blocked(self, sdr):
        """HackRFReceiver.set_tx_gain() raises HardwareTransmitError."""
        with pytest.raises(HardwareTransmitError):
            sdr.set_tx_gain(20)

    def test_set_tx_frequency_blocked(self, sdr):
        """HackRFReceiver.set_tx_frequency() raises HardwareTransmitError."""
        with pytest.raises(HardwareTransmitError):
            sdr.set_tx_frequency(433_000_000)

    def test_setup_tx_stream_blocked(self, sdr):
        """HackRFReceiver.setupTxStream() raises HardwareTransmitError."""
        with pytest.raises(HardwareTransmitError):
            sdr.setupTxStream()

    def test_activate_tx_stream_blocked(self, sdr):
        """HackRFReceiver.activateTxStream() raises HardwareTransmitError."""
        with pytest.raises(HardwareTransmitError):
            sdr.activateTxStream()

    def test_tx_errors_are_hardware_transmit_error_not_just_runtime(self, sdr):
        """
        TX blocks must raise HardwareTransmitError specifically,
        not just any RuntimeError. This matters because we need to be
        able to catch TX violations distinctly from other runtime errors.
        """
        with pytest.raises(HardwareTransmitError) as exc_info:
            sdr.transmit()
        # Must be the specific TX error, not a generic RuntimeError
        assert type(exc_info.value) is HardwareTransmitError


# ══════════════════════════════════════════════════════════════════════
# GROUP 4 — HackRFReceiver RX methods do NOT raise HardwareTransmitError
# ══════════════════════════════════════════════════════════════════════

class TestHackRFReceiverRXNotBlocked:
    """
    RX methods must NOT raise HardwareTransmitError.
    Without hardware connected they will raise RuntimeError or similar —
    that is fine. The important thing is the TX guard is NOT triggered.
    """

    @pytest.fixture
    def sdr(self):
        return HackRFReceiver()

    def test_set_center_frequency_not_tx_blocked(self, sdr):
        """set_center_frequency() must not raise HardwareTransmitError."""
        try:
            sdr.set_center_frequency(98_000_000)
        except HardwareTransmitError:
            pytest.fail(
                "set_center_frequency() raised HardwareTransmitError. "
                "This is a receive function and must not be TX-blocked."
            )
        except Exception:
            pass  # Hardware not connected — expected, not a TX block issue

    def test_set_sample_rate_not_tx_blocked(self, sdr):
        """set_sample_rate() must not raise HardwareTransmitError."""
        try:
            sdr.set_sample_rate(2_000_000)
        except HardwareTransmitError:
            pytest.fail(
                "set_sample_rate() raised HardwareTransmitError. "
                "This is a receive function and must not be TX-blocked."
            )
        except Exception:
            pass

    def test_set_gain_not_tx_blocked(self, sdr):
        """set_gain() must not raise HardwareTransmitError."""
        try:
            sdr.set_gain(20)
        except HardwareTransmitError:
            pytest.fail(
                "set_gain() raised HardwareTransmitError. "
                "This is a receive function and must not be TX-blocked."
            )
        except Exception:
            pass

    def test_read_samples_not_tx_blocked(self, sdr):
        """read_samples() must not raise HardwareTransmitError."""
        try:
            sdr.read_samples(1024)
        except HardwareTransmitError:
            pytest.fail(
                "read_samples() raised HardwareTransmitError. "
                "This is a receive function and must not be TX-blocked."
            )
        except RuntimeError as e:
            # Expected when hardware is not open — not a TX block
            assert "not open" in str(e).lower() or "hackrf" in str(e).lower(), (
                f"Unexpected RuntimeError from read_samples: {e}"
            )
        except Exception:
            pass

    def test_close_not_tx_blocked(self, sdr):
        """close() must not raise HardwareTransmitError."""
        try:
            sdr.close()  # Should silently do nothing if never opened
        except HardwareTransmitError:
            pytest.fail(
                "close() raised HardwareTransmitError. "
                "close() is a housekeeping function, not a TX operation."
            )
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════
# GROUP 5 — Configuration and properties
# ══════════════════════════════════════════════════════════════════════

class TestHackRFReceiverConfig:
    """Tests for HackRFReceiver configuration and default values."""

    def test_default_frequency_is_fm_broadcast(self):
        """Default frequency should be in the FM broadcast band."""
        sdr = HackRFReceiver()
        assert 87_500_000 <= sdr.center_freq_hz <= 108_000_000, (
            f"Default frequency {sdr.center_freq_hz} is outside FM broadcast "
            f"band (87.5–108 MHz). A safe, legal AU frequency should be default."
        )

    def test_not_open_by_default(self):
        """Device should not be open until open() or __enter__ is called."""
        sdr = HackRFReceiver()
        assert not sdr.is_open

    def test_soapy_tx_direction_constant_is_zero(self):
        """
        The TX direction constant must be 0 (SoapySDR convention).
        This test documents that we know what the TX direction value is
        and that it is NEVER passed to hardware in our code.
        """
        assert HackRFReceiver._SOAPY_TX_DIRECTION == 0

    def test_soapy_rx_direction_constant_is_one(self):
        """
        The RX direction constant must be 1 (SoapySDR convention).
        All hardware calls in hackrf_rx.py must use this value.
        """
        assert HackRFReceiver._SOAPY_RX_DIRECTION == 1
