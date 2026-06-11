"""Tests for AcarsMessage dataclass and field validation."""

from datetime import datetime

from modules.acars.message import AcarsMessage


def test_acars_message_dataclass_fields():
    """All fields are stored correctly."""
    msg = AcarsMessage(
        timestamp=datetime(2024, 1, 1, 12, 0, 0),
        freq_hz=129_125_000.0,
        mode="2",
        registration="VH-OGE",
        label="H1",
        block_id="A",
        text="TEST",
        crc_ok=True,
        error_count=0,
    )
    assert msg.timestamp == datetime(2024, 1, 1, 12, 0, 0)
    assert msg.freq_hz == 129_125_000.0
    assert msg.mode == "2"
    assert msg.registration == "VH-OGE"
    assert msg.label == "H1"
    assert msg.block_id == "A"
    assert msg.text == "TEST"
    assert msg.crc_ok is True
    assert msg.error_count == 0


def test_acars_message_crc_ok_default_false():
    """crc_ok defaults to False when omitted."""
    msg = AcarsMessage(
        timestamp=datetime.now(),
        freq_hz=0.0,
        mode="",
        registration="",
        label="",
        block_id="",
        text="",
        crc_ok=False,
    )
    assert msg.crc_ok is False
    assert msg.error_count == 0
