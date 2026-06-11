"""Tests for AcarsDecoder — frame sync, field parsing, CRC-16."""

import pytest

from modules.acars.decoder import AcarsDecoder
from modules.acars.message import AcarsMessage


class TestAcarsDecoder:
    def setup_method(self):
        self.decoder = AcarsDecoder()

    def test_crc16_known_value(self):
        """CRC-16 of '123456789' is a well-known test vector."""
        data = b"123456789"
        crc = self.decoder.crc16(data)
        # CRC-CCITT (0x1021, init 0x0000) of "123456789" = 0x31C3
        assert crc == 0x31C3

    def test_bits_to_bytes_lsb_first(self):
        """LSB-first grouping: 0x55 = 0b01010101."""
        bits = [1, 0, 1, 0, 1, 0, 1, 0]
        bytes_ = self.decoder.bits_to_bytes(bits)
        assert bytes_ == [0x55]

    def test_bits_to_bytes_strips_parity(self):
        """Parity bit (bit 7) is stripped, leaving 7-bit data."""
        # 0x55 with odd parity on bit 7 -> 0xD5 (0b1010101 + 1 parity = 11010101)
        bits = [1, 0, 1, 0, 1, 0, 1, 1]
        bytes_ = self.decoder.bits_to_bytes(bits)
        assert bytes_ == [0x55]

    def test_find_frame_start_detects_preamble_and_sync(self):
        """48+ 1-bits followed by SYN SYN SOH is detected."""
        preamble = [1] * 48
        syn_bits = self._byte_to_bits(0x16)
        soh_bits = self._byte_to_bits(0x01)
        bits = preamble + syn_bits + syn_bits + soh_bits
        idx = self.decoder.find_frame_start(bits)
        assert idx == 48

    def test_find_frame_start_returns_none_when_absent(self):
        """Random bits without preamble+sync return None."""
        bits = [0, 1, 0, 1] * 100
        assert self.decoder.find_frame_start(bits) is None

    def test_parse_frame_valid_message(self):
        """A synthetically valid frame parses into an AcarsMessage."""
        # Build a minimal valid frame
        mode = 0x32  # '2'
        dot = 0x2E
        reg = [0x56, 0x48, 0x2D, 0x4F, 0x47, 0x45, 0x20]  # 'VH-OGE '
        tak = 0x41
        label = [0x48, 0x31]  # 'H1'
        block_id = 0x41
        stx = 0x02
        text = [0x54, 0x45, 0x53, 0x54]  # 'TEST'
        etx = 0x83
        del_ = 0x7F

        # CRC is computed over all bytes up to and including ETX (not DEL)
        crc_payload = (
            [mode, dot] + reg + [tak] + label + [block_id, stx]
            + text + [etx]
        )
        crc = self.decoder.crc16(bytes(crc_payload))
        crc_low = crc & 0xFF
        crc_high = (crc >> 8) & 0xFF
        frame_bytes = crc_payload + [del_, crc_low, crc_high]

        msg = self.decoder.parse_frame(frame_bytes)
        assert isinstance(msg, AcarsMessage)
        assert msg.mode == "2"
        assert msg.registration == "VH-OGE"
        assert msg.label == "H1"
        assert msg.block_id == "A"
        assert msg.text == "TEST"
        assert msg.crc_ok is True

    def test_parse_frame_crc_fail_sets_flag(self):
        """Corrupted CRC bytes set crc_ok=False."""
        mode = 0x32
        dot = 0x2E
        reg = [0x56, 0x48, 0x2D, 0x4F, 0x47, 0x45, 0x20]
        tak = 0x41
        label = [0x48, 0x31]
        block_id = 0x41
        stx = 0x02
        text = [0x54, 0x45, 0x53, 0x54]
        etx = 0x83
        del_ = 0x7F

        frame_bytes = (
            [mode, dot] + reg + [tak] + label + [block_id, stx]
            + text + [etx, del_]
        )
        # Append wrong CRC
        frame_bytes += [0xFF, 0xFF]

        msg = self.decoder.parse_frame(frame_bytes)
        assert isinstance(msg, AcarsMessage)
        assert msg.crc_ok is False

    def test_parse_frame_returns_none_on_malformed(self):
        """Missing STX causes parse_frame to return None."""
        frame_bytes = [0x32, 0x2E] + [0x20] * 7 + [0x41, 0x48, 0x31, 0x41, 0x99]
        assert self.decoder.parse_frame(frame_bytes) is None

    def _byte_to_bits(self, value: int) -> list[int]:
        """Helper: convert a byte to 8 LSB-first bits with odd parity."""
        bits = [(value >> i) & 1 for i in range(7)]
        parity = 1 if sum(bits) % 2 == 0 else 0
        bits.append(parity)
        return bits
