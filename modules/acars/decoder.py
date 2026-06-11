"""ACARS decoder — frame sync, field parsing, CRC-16 validation.

Frame format follows ARINC 618 downlink specification.

Legal: passive receive only.  Radiocommunications Act 1992 (Cth).
Jurisdiction: AU / SA.  Authority: ACMA.
"""

import logging
from datetime import datetime

from modules.acars.message import AcarsMessage

logger = logging.getLogger(__name__)


class AcarsDecoder:
    """Extract ACARS messages from a decoded bit stream."""

    SYN = 0x16
    SOH = 0x01
    STX = 0x02
    ETX = 0x83
    ETB = 0x97
    DEL = 0x7F
    PREAMBLE_BITS = 128

    def bits_to_bytes(self, bits: list[int]) -> list[int]:
        """Group bits into 8-bit bytes (LSB first) and strip parity.

        ACARS characters are 7-bit ASCII with odd parity on bit 7.
        We mask with 0x7F to keep only the data bits.

        Args:
            bits: List of 0/1 bits.

        Returns:
            List of byte values (0-127).
        """
        bytes_: list[int] = []
        for i in range(0, len(bits) - 7, 8):
            byte = 0
            for j in range(8):
                byte |= bits[i + j] << j
            bytes_.append(byte & 0x7F)
        return bytes_

    def find_frame_start(self, bits: list[int]) -> int | None:
        """Scan for preamble + SYN SYN SOH and return bit index of first SYN.

        The preamble is relaxed from 128 bits to 48 bits to tolerate noise.

        Args:
            bits: Decoded bit stream.

        Returns:
            Bit index where SYN SYN SOH begins, or ``None``.
        """
        run_start: int | None = None
        for i, bit in enumerate(bits):
            if bit == 1:
                if run_start is None:
                    run_start = i
            else:
                if run_start is not None and i - run_start >= 48:
                    start_idx = i
                    if start_idx + 24 <= len(bits):
                        chunk = bits[start_idx : start_idx + 24]
                        bytes_ = self.bits_to_bytes(chunk)
                        if bytes_[:3] == [self.SYN, self.SYN, self.SOH]:
                            return start_idx
                run_start = None

        # End-of-stream check
        if run_start is not None and len(bits) - run_start >= 48:
            start_idx = len(bits)
            if start_idx + 24 <= len(bits):
                chunk = bits[start_idx : start_idx + 24]
                bytes_ = self.bits_to_bytes(chunk)
                if bytes_[:3] == [self.SYN, self.SYN, self.SOH]:
                    return start_idx

        return None

    def parse_frame(self, bytes_: list[int]) -> AcarsMessage | None:
        """Parse an ACARS downlink frame starting at the byte after SOH.

        Field layout (ARINC 618 downlink):
            [0]     Mode (1 byte, e.g. '2')
            [1]     dot/period (1 byte, literal 0x2E)
            [2:9]   Aircraft registration (7 bytes, e.g. 'VH-OGE ')
            [9]     TAK (1 byte)
            [10:12] Label (2 bytes)
            [12]    Block ID (1 byte)
            [13]    STX (0x02)
            [14:-3] Message text (variable, 0-220 bytes)
            [-3]    ETX (0x83) or ETB (0x97)
            [-2]    DEL (0x7F)
            [-1:-]  CRC-16 low byte
            [end]   CRC-16 high byte

        Args:
            bytes_: Byte list starting with Mode (after SOH).

        Returns:
            ``AcarsMessage`` on success, or ``None`` if malformed.
        """
        if len(bytes_) < 16:
            return None

        if bytes_[13] != self.STX:
            return None

        # Find ETX or ETB
        etx_idx: int | None = None
        for i in range(14, len(bytes_) - 3):
            if bytes_[i] in (self.ETX, self.ETB):
                etx_idx = i
                break

        if etx_idx is None:
            return None

        # Extract fields
        mode = chr(bytes_[0])
        registration = "".join(chr(b) for b in bytes_[2:9]).strip()
        label = "".join(chr(b) for b in bytes_[10:12])
        block_id = chr(bytes_[12])
        text = "".join(chr(b) for b in bytes_[14:etx_idx])

        # CRC-16 validation
        crc_data = bytes(bytes_[: etx_idx + 1])
        received_crc = (bytes_[-1] << 8) | bytes_[-2]
        computed_crc = self.crc16(crc_data)
        crc_ok = computed_crc == received_crc

        # Count parity errors (odd parity expected on the raw 8-bit value)
        error_count = 0
        for b in bytes_:
            if bin(b).count("1") % 2 == 0:
                error_count += 1

        return AcarsMessage(
            timestamp=datetime.now(),
            freq_hz=0.0,
            mode=mode,
            registration=registration,
            label=label,
            block_id=block_id,
            text=text,
            crc_ok=crc_ok,
            error_count=error_count,
        )

    def crc16(self, data: bytes) -> int:
        """Compute CRC-CCITT (0x1021) with initial value 0x0000.

        Args:
            data: Byte sequence to checksum.

        Returns:
            16-bit CRC value.
        """
        crc = 0x0000
        for byte in data:
            crc ^= byte << 8
            for _ in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ 0x1021
                else:
                    crc <<= 1
            crc &= 0xFFFF
        return crc
