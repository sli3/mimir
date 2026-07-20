"""
tests/core/test_factory.py
Mimir RF Scanner — Device Factory Tests

Legal: Receive-only. Radiocommunications Act 1992 (Cth).
       No transmission. Jurisdiction: AU/SA. Authority: ACMA.

Tests for core/device/factory.py (build_device).
Hardware is never touched: the factory returns UN-OPENED receiver
instances, and no test here calls open().
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.device.factory import build_device
from core.device.hackrf_rx import HackRFReceiver
from core.device.pluto_rx import PlutoReceiver
from core.legal.compliance_guard import HardwareTransmitError


class TestBuildDevice:
    """Tests for build_device() driver routing and gain handling."""

    def test_hackrf_returns_hackrf_receiver_instance(self):
        """build_device("hackrf") returns an un-opened HackRFReceiver."""
        receiver = build_device("hackrf")
        assert isinstance(receiver, HackRFReceiver)
        assert receiver.is_open is False

    def test_hackrf_uses_config_gains(self):
        """HackRF split gains passed as keywords land on the instance."""
        receiver = build_device(
            "hackrf", lna_gain_db=16.0, vga_gain_db=20.0, amp_enable=True
        )
        assert receiver._lna_gain_db == 16.0
        assert receiver._vga_gain_db == 20.0
        assert receiver._amp_enable is True

    def test_plutosdr_returns_pluto_receiver_instance(self):
        """build_device("plutosdr") returns an un-opened PlutoReceiver."""
        receiver = build_device("plutosdr")
        assert isinstance(receiver, PlutoReceiver)
        assert receiver.gain_db == PlutoReceiver.DEFAULT_GAIN_DB
        assert receiver.is_open is False

    def test_plutosdr_uses_default_gain_regardless_of_kwargs(self):
        """HackRF LNA/VGA/amp kwargs must NOT be forwarded to Pluto.

        Pluto has a single combined gain stage; the HackRF split-gain
        vocabulary has no principled mapping onto it, so the factory
        always uses PlutoReceiver.DEFAULT_GAIN_DB instead.
        """
        receiver = build_device(
            "plutosdr", lna_gain_db=99.0, vga_gain_db=99.0, amp_enable=True
        )
        assert receiver.gain_db == PlutoReceiver.DEFAULT_GAIN_DB

    def test_unknown_driver_raises_value_error(self):
        """Unknown driver keys fail loudly with guidance for --device."""
        with pytest.raises(ValueError) as exc_info:
            build_device("rtlsdr")
        message = str(exc_info.value)
        assert "--device" in message
        assert "hackrf" in message
        assert "plutosdr" in message

    def test_returns_unopened_instance(self):
        """Neither driver path opens hardware inside the factory."""
        assert build_device("hackrf").is_open is False
        assert build_device("plutosdr").is_open is False

    def test_plutosdr_constructed_blocks_transmit(self):
        """TX methods on the factory-built Pluto raise HardwareTransmitError."""
        receiver = build_device("plutosdr")
        with pytest.raises(HardwareTransmitError):
            receiver.transmit()
        with pytest.raises(HardwareTransmitError):
            receiver.writeStream()
        with pytest.raises(HardwareTransmitError):
            receiver.setupTxStream()

    def test_hackrf_constructed_blocks_transmit(self):
        """TX methods on the factory-built HackRF raise HardwareTransmitError."""
        receiver = build_device("hackrf")
        with pytest.raises(HardwareTransmitError):
            receiver.transmit()
        with pytest.raises(HardwareTransmitError):
            receiver.writeStream()
        with pytest.raises(HardwareTransmitError):
            receiver.setupTxStream()

    def test_factory_uses_keyword_only_args(self):
        """Gain arguments are keyword-only; positional passing raises TypeError."""
        with pytest.raises(TypeError):
            build_device("hackrf", 24.0, 26.0, False)
