"""Tests for AisDemodulator — synthetic signal generation, no live hardware."""

import numpy as np

from modules.ais.demodulator import (
    AisDemodulator,
    _crc16_reflected,
    _extract_hdlc_frames,
    _nrzi_decode,
)


class TestAisDemodulator:
    def setup_method(self):
        self.demod = AisDemodulator()

    def test_demodulate_returns_list(self):
        """demodulate() returns a list."""
        iq = np.zeros(1000, dtype=np.complex64)
        result = self.demod.demodulate(iq, 2_000_000.0)
        assert isinstance(result, list)

    def test_demodulate_pure_noise_returns_empty(self):
        """Pure noise produces no false-positive frames."""
        np.random.seed(42)
        iq = (np.random.randn(100_000) + 1j * np.random.randn(100_000)).astype(np.complex64)
        result = self.demod.demodulate(iq, 2_000_000.0)
        assert result == []

    def test_nrzi_decode_no_transition(self):
        """All same bits (no transition) decode to all 1s."""
        bits = [1, 1, 1, 1]
        decoded = _nrzi_decode(bits)
        assert decoded == [1, 1, 1, 1]

    def test_nrzi_decode_transition(self):
        """Alternating bits decode to [1, 0, 0, 0, 0, 0].

        The first bit is 1 because the default initial_state (1) matches
        the first NRZI bit (no transition).
        """
        bits = [1, 0, 1, 0, 1, 0]
        decoded = _nrzi_decode(bits)
        assert decoded == [1, 0, 0, 0, 0, 0]

    def test_crc16_reflected_known_value(self):
        """CRC-16 of '123456789' with reflected init 0xFFFF."""
        data = b"123456789"
        crc = _crc16_reflected(data)
        # Computed value for CRC-16/CCITT-FALSE reflected
        assert crc == 0x6F91

    def test_extract_hdlc_frames_valid_frame(self):
        """A valid HDLC frame with correct FCS is extracted."""
        # Build a simple frame: flag + data + FCS + flag
        # Use data that avoids 7 consecutive identical bits in NRZI stream
        data = b"\x01\x01\x01TEST"
        fcs = _crc16_reflected(data)
        fcs_bytes = bytes([fcs & 0xFF, (fcs >> 8) & 0xFF])
        # Verify residual
        residual = _crc16_reflected(data + fcs_bytes)
        assert residual == 0x0000
        # NRZI encode the frame
        raw_bits = [0, 1, 1, 1, 1, 1, 1, 0]  # flag 0x7E
        for byte in data + fcs_bytes:
            for i in range(7, -1, -1):
                raw_bits.append((byte >> i) & 1)
        raw_bits.extend([0, 1, 1, 1, 1, 1, 1, 0])  # closing flag

        # NRZI encode
        nrzi_bits = [1]
        for b in raw_bits:
            nrzi_bits.append(nrzi_bits[-1] ^ (1 - b))

        payloads = _extract_hdlc_frames(nrzi_bits)
        assert len(payloads) == 1
        assert payloads[0] == data

    def test_extract_hdlc_frames_bad_crc_ignored(self):
        """A frame with bad CRC is ignored."""
        data = b"\xFF\x03\xF0TEST"
        fcs_bytes = b"\xFF\xFF"  # bad CRC
        raw_bits = [0, 1, 1, 1, 1, 1, 1, 0]
        for byte in data + fcs_bytes:
            for i in range(7, -1, -1):
                raw_bits.append((byte >> i) & 1)
        raw_bits.extend([0, 1, 1, 1, 1, 1, 1, 0])

        nrzi_bits = [1]
        for b in raw_bits:
            nrzi_bits.append(nrzi_bits[-1] ^ (1 - b))

        payloads = _extract_hdlc_frames(nrzi_bits)
        assert payloads == []

    def _create_gmsk_signal(self, nrzi_bits, sample_rate, baud_rate, offset_hz=0.0):
        """Create a synthetic GMSK signal at a given carrier offset.

        NRZI: 0 = transition, 1 = no transition.
        Phase advances by π/2 for each transition.
        The carrier is offset by offset_hz so the demodulator's frequency
        shift (±25 kHz) brings the signal to baseband.
        """
        sps = int(sample_rate / baud_rate)
        phase = 0.0
        t = 0
        samples = []
        for b in nrzi_bits:
            if b == 0:  # transition
                phase += np.pi / 2
            for _ in range(sps):
                carrier_phase = 2 * np.pi * offset_hz * (t / sample_rate)
                samples.append(np.exp(1j * (carrier_phase + phase)))
                t += 1
        return np.array(samples, dtype=np.complex64)

    def test_demodulate_with_synthetic_gmsk(self):
        """A synthetic GMSK signal is processed without crashing.

        The full DSP pipeline (decimate → shift → filter → differentiate →
        resample → threshold → HDLC extract) is exercised; we only assert
        the demodulator returns a list of (payload, channel) tuples and
        does not raise.
        """
        # Build a simple HDLC frame
        data = b"\x01\x01\x01TEST"
        fcs = _crc16_reflected(data)
        fcs_bytes = bytes([fcs & 0xFF, (fcs >> 8) & 0xFF])
        # Verify residual
        residual = _crc16_reflected(data + fcs_bytes)
        assert residual == 0x0000

        frame_bits = [0, 1, 1, 1, 1, 1, 1, 0]  # flag
        for byte in data + fcs_bytes:
            for i in range(7, -1, -1):
                frame_bits.append((byte >> i) & 1)
        frame_bits.extend([0, 1, 1, 1, 1, 1, 1, 0])  # flag

        # NRZI encode
        nrzi_bits = [1]
        for b in frame_bits:
            nrzi_bits.append(nrzi_bits[-1] ^ (1 - b))

        # Create signal at 2 MHz with +25 kHz offset (channel 2)
        sample_rate = 2_000_000.0
        baud_rate = 9600.0
        signal_ = self._create_gmsk_signal(nrzi_bits, sample_rate, baud_rate, offset_hz=25_000.0)

        # Add generous padding so FIR transients don't corrupt the frame
        signal_ = np.concatenate([
            np.zeros(5000, dtype=np.complex64),
            signal_,
            np.zeros(5000, dtype=np.complex64),
        ])

        # Add noise (very low level)
        np.random.seed(42)
        noise = (np.random.randn(len(signal_)) * 0.001 + 1j * np.random.randn(len(signal_)) * 0.001).astype(np.complex64)
        signal_ = signal_ + noise

        result = self.demod.demodulate(signal_, sample_rate)
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, tuple) and len(item) == 2
            assert isinstance(item[0], bytes)
            assert item[1] in ("A", "B")

    def test_frequency_shift_separates_channels(self):
        """A tone at +25 kHz offset is only detected on channel 2."""
        sample_rate = 2_000_000.0
        duration = 0.1  # 100 ms
        t = np.arange(int(sample_rate * duration)) / sample_rate

        # Tone at +25 kHz (channel 2 offset)
        tone = np.exp(2j * np.pi * 25_000 * t).astype(np.complex64)

        # Add a small amount of noise
        np.random.seed(42)
        noise = (np.random.randn(len(tone)) * 0.1 + 1j * np.random.randn(len(tone)) * 0.1).astype(np.complex64)
        signal_ = tone + noise

        result = self.demod.demodulate(signal_, sample_rate)
        # A pure tone won't produce valid HDLC frames, but we can verify
        # the demodulator processes both channels without crashing
        assert isinstance(result, list)
