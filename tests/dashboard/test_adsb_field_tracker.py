"""Tests for dashboard/server.py AdsbFieldTracker.

Structured after tests/modules/test_adsb_bearing_tracker.py: the tracker
mirrors BearingTracker's retention discipline (lazy TTL eviction, capacity
cap, ICAO key normalisation) applied to the merged per-ICAO field view used
by the AI Reasoning panel.
"""

from datetime import datetime, timedelta, timezone

from dashboard.server import AdsbFieldTracker
from modules.adsb.constants import AIRCRAFT_EXPIRY_SEC, MAX_AIRCRAFT
from modules.adsb.message import AdsbMessage

BASE_TS = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def make_msg(icao="7C4B4C", ts=None, **overrides):
    """Build an AdsbMessage with all tracked fields None unless overridden."""
    fields = dict(
        icao=icao,
        callsign=None,
        altitude_ft=None,
        latitude=None,
        longitude=None,
        groundspeed=None,
        track=None,
        vertical_rate=None,
        squawk=None,
        raw_hex="8D" + str(icao).upper() + "00000000000000000000",
        timestamp=ts or BASE_TS,
    )
    fields.update(overrides)
    return AdsbMessage(**fields)


class TestAdsbFieldTracker:
    def test_first_seen_fields_none_until_resolved(self):
        """A frame carrying only a callsign leaves the other fields None."""
        tracker = AdsbFieldTracker()
        merged = tracker.update(make_msg(callsign="QFA456"))
        assert merged["callsign"] == "QFA456"
        assert merged["altitude_ft"] is None
        assert merged["groundspeed"] is None
        assert merged["track"] is None
        assert merged["vertical_rate"] is None

    def test_resolved_field_survives_frame_without_it(self):
        """The core bug: a later frame lacking a field must not erase it."""
        tracker = AdsbFieldTracker()
        tracker.update(
            make_msg(
                callsign="QFA456",
                altitude_ft=35000,
                groundspeed=450.0,
                track=90.0,
                vertical_rate=0,
                ts=BASE_TS,
            )
        )
        # Second frame carries only the callsign (e.g. a typecode 4 frame).
        merged = tracker.update(
            make_msg(callsign="QFA456", ts=BASE_TS + timedelta(seconds=5))
        )
        assert merged["callsign"] == "QFA456"
        assert merged["altitude_ft"] == 35000
        assert merged["groundspeed"] == 450.0
        assert merged["track"] == 90.0
        assert merged["vertical_rate"] == 0

    def test_new_non_none_value_overwrites_stored(self):
        """A non-None field on a later frame replaces the stored value."""
        tracker = AdsbFieldTracker()
        tracker.update(make_msg(altitude_ft=35000, ts=BASE_TS))
        merged = tracker.update(
            make_msg(altitude_ft=33000, ts=BASE_TS + timedelta(seconds=10))
        )
        assert merged["altitude_ft"] == 33000

    def test_expired_aircraft_treated_as_fresh(self):
        """After AIRCRAFT_EXPIRY_SEC the old entry is evicted, not preserved."""
        tracker = AdsbFieldTracker()
        tracker.update(
            make_msg(
                callsign="QFA456",
                altitude_ft=35000,
                groundspeed=450.0,
                track=90.0,
                vertical_rate=0,
                ts=BASE_TS,
            )
        )
        # Well past the TTL: the stored entry must be swept before merge.
        merged = tracker.update(
            make_msg(
                callsign="QFA456",
                ts=BASE_TS + timedelta(seconds=AIRCRAFT_EXPIRY_SEC + 1.0),
            )
        )
        assert merged["callsign"] == "QFA456"  # carried by the new frame
        # Fields the new frame does not carry are None again: the old
        # entry was actually evicted, not preserved.
        assert merged["altitude_ft"] is None
        assert merged["groundspeed"] is None
        assert merged["track"] is None
        assert merged["vertical_rate"] is None

    def test_evicts_oldest_aircraft_at_capacity(self):
        """At MAX_AIRCRAFT entries, a new distinct icao drops the oldest entry."""
        tracker = AdsbFieldTracker()
        # One second per icao keeps the whole span (30 s) well under
        # AIRCRAFT_EXPIRY_SEC (90 s) so _evict_stale cannot interfere.
        for i in range(MAX_AIRCRAFT):
            tracker.update(
                make_msg(icao=f"AC{i:04d}", ts=BASE_TS + timedelta(seconds=i))
            )
        assert len(tracker._state) == MAX_AIRCRAFT

        tracker.update(
            make_msg(icao="NEWEST", ts=BASE_TS + timedelta(seconds=MAX_AIRCRAFT))
        )

        assert len(tracker._state) == MAX_AIRCRAFT  # capped, not exceeded
        assert "AC0000" not in tracker._state  # oldest-timestamp icao evicted
        assert "NEWEST" in tracker._state  # newest arrival retained

    def test_two_icaos_tracked_independently(self):
        """State for ICAO A is not affected by updates for ICAO B."""
        tracker = AdsbFieldTracker()
        tracker.update(make_msg(icao="AAAAAA", callsign="AAA123", altitude_ft=35000))
        tracker.update(make_msg(icao="BBBBBB", callsign="BBB456", track=270.0))
        merged_a = tracker.update(make_msg(icao="AAAAAA", groundspeed=450.0))
        merged_b = tracker.update(make_msg(icao="BBBBBB", altitude_ft=28000))
        # A kept its own callsign/altitude and gained groundspeed.
        assert merged_a["callsign"] == "AAA123"
        assert merged_a["altitude_ft"] == 35000
        assert merged_a["groundspeed"] == 450.0
        assert merged_a["track"] is None
        # B kept its own callsign/track and gained altitude, untouched by A.
        assert merged_b["callsign"] == "BBB456"
        assert merged_b["track"] == 270.0
        assert merged_b["altitude_ft"] == 28000
        assert merged_b["groundspeed"] is None

    def test_icao_key_normalisation(self):
        """Lower-case and upper-case spellings of the same ICAO share state."""
        tracker = AdsbFieldTracker()
        tracker.update(make_msg(icao="abc123", altitude_ft=35000, ts=BASE_TS))
        merged = tracker.update(
            make_msg(icao="ABC123", callsign="QFA456", ts=BASE_TS + timedelta(seconds=5))
        )
        # Same aircraft via case normalisation: altitude from the first
        # frame survived, and the reported key is the normalised form.
        assert merged["altitude_ft"] == 35000
        assert merged["callsign"] == "QFA456"
        assert merged["icao"] == "ABC123"
        assert len(tracker._state) == 1

    def test_update_existing_icao_at_capacity_does_not_evict(self):
        """Updating an already-tracked icao at capacity must not trigger eviction."""
        tracker = AdsbFieldTracker()
        for i in range(MAX_AIRCRAFT):
            tracker.update(
                make_msg(icao=f"AC{i:04d}", ts=BASE_TS + timedelta(seconds=i))
            )
        assert len(tracker._state) == MAX_AIRCRAFT

        later_ts = BASE_TS + timedelta(seconds=MAX_AIRCRAFT + 1)
        tracker.update(make_msg(icao="AC0000", altitude_ft=35000, ts=later_ts))

        # The guard skipped eviction: the count is unchanged and no other
        # aircraft was dropped.
        assert len(tracker._state) == MAX_AIRCRAFT
        assert "AC0000" in tracker._state
        # The stored entry was refreshed with the new value/timestamp.
        assert tracker._state["AC0000"]["altitude_ft"] == 35000
        assert tracker._state["AC0000"]["_ts"] == later_ts

    def test_update_returns_merged_view(self):
        """update() returns exactly the icao key plus the 6 tracked fields."""
        tracker = AdsbFieldTracker()
        merged = tracker.update(
            make_msg(callsign="QFA456", altitude_ft=35000, vertical_rate=0)
        )
        assert set(merged.keys()) == {
            "icao",
            "callsign",
            "altitude_ft",
            "groundspeed",
            "track",
            "vertical_rate",
            "squawk",
        }
        assert merged["icao"] == "7C4B4C"
        assert merged["callsign"] == "QFA456"
        assert merged["altitude_ft"] == 35000
        assert merged["groundspeed"] is None
        assert merged["track"] is None
        assert merged["vertical_rate"] == 0

    def test_squawk_merged_and_retained(self):
        """Squawk from a DF5 frame survives a later frame carrying no squawk."""
        tracker = AdsbFieldTracker()
        tracker.update(make_msg(squawk="7500", ts=BASE_TS))
        merged = tracker.update(
            make_msg(callsign="QFA456", ts=BASE_TS + timedelta(seconds=5))
        )
        assert merged["squawk"] == "7500"
        assert merged["callsign"] == "QFA456"

    def test_squawk_none_for_never_resolved(self):
        """squawk is None for an ICAO that has never sent one."""
        tracker = AdsbFieldTracker()
        merged = tracker.update(make_msg(callsign="QFA456"))
        assert merged["squawk"] is None
