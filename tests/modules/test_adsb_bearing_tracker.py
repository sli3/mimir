"""Tests for modules/adsb/bearing_tracker.py."""

from datetime import datetime, timedelta, timezone

import pytest

from modules.adsb.bearing_tracker import (
    BearingTracker,
    angular_diff_deg,
    initial_bearing_deg,
)
from modules.adsb.constants import (
    ADELAIDE_LAT,
    ADELAIDE_LON,
    AIRCRAFT_EXPIRY_SEC,
    MAX_AIRCRAFT,
)
from modules.adsb.message import AdsbMessage

BASE_TS = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def make_msg(icao="7C4B4C", lat=-34.0, lon=139.0, ts=None, **kwargs):
    return AdsbMessage(
        icao=icao,
        callsign=None,
        altitude_ft=32000,
        latitude=lat,
        longitude=lon,
        groundspeed=450.0,
        track=90.0,
        vertical_rate=0,
        raw_hex="8D" + icao.upper() + "00000000000000000000",
        timestamp=ts or BASE_TS,
        **kwargs,
    )


class TestInitialBearing:
    def test_due_north(self):
        assert initial_bearing_deg(0.0, 0.0, 1.0, 0.0) == pytest.approx(0.0)

    def test_due_east(self):
        assert initial_bearing_deg(0.0, 0.0, 0.0, 1.0) == pytest.approx(90.0)

    def test_due_south(self):
        assert initial_bearing_deg(0.0, 0.0, -1.0, 0.0) == pytest.approx(180.0)

    def test_due_west(self):
        assert initial_bearing_deg(0.0, 0.0, 0.0, -1.0) == pytest.approx(270.0)

    def test_adelaide_to_eastern_airspace(self):
        """Aircraft due east of Adelaide (same latitude, +1 deg longitude).

        Hand-verified great-circle initial bearing: ~90.29 deg, i.e. just
        north of due east as the great circle curves towards the pole in
        the southern hemisphere.
        """
        bearing = initial_bearing_deg(ADELAIDE_LAT, ADELAIDE_LON, -34.93, 139.60)
        assert 80.0 < bearing < 120.0
        assert bearing == pytest.approx(90.29, abs=1.0)

    def test_coincident_point_returns_zero(self):
        """atan2(0, 0) is 0 — a documented convention, not a measurement."""
        assert initial_bearing_deg(-34.93, 138.60, -34.93, 138.60) == 0.0


class TestAngularDiff:
    def test_no_wraparound(self):
        assert angular_diff_deg(90.0, 45.0) == pytest.approx(45.0)

    def test_positive_wraparound(self):
        assert angular_diff_deg(5.0, 355.0) == pytest.approx(10.0)

    def test_negative_wraparound(self):
        assert angular_diff_deg(355.0, 5.0) == pytest.approx(-10.0)

    def test_zero_difference(self):
        assert angular_diff_deg(180.0, 180.0) == pytest.approx(0.0)


class TestBearingTracker:
    def test_first_message_has_no_delta_r(self):
        tracker = BearingTracker()
        report = tracker.update(make_msg())
        assert report is not None
        assert report.delta_r_deg_per_sec is None
        assert 0.0 <= report.bearing_deg < 360.0

    def test_second_message_computes_delta_r(self):
        tracker = BearingTracker()
        tracker.update(make_msg(lat=-34.0, lon=139.0, ts=BASE_TS))
        report = tracker.update(
            make_msg(lat=-33.9, lon=139.1, ts=BASE_TS + timedelta(seconds=10))
        )
        assert report is not None
        assert report.delta_r_deg_per_sec is not None
        assert isinstance(report.delta_r_deg_per_sec, float)

    def test_none_latitude_returns_none(self):
        tracker = BearingTracker()
        assert tracker.update(make_msg(lat=None)) is None

    def test_none_longitude_returns_none(self):
        tracker = BearingTracker()
        assert tracker.update(make_msg(lon=None)) is None

    def test_two_icaos_tracked_independently(self):
        tracker = BearingTracker()
        tracker.update(make_msg(icao="AAAAAA", lat=-34.0, lon=139.0, ts=BASE_TS))
        tracker.update(make_msg(icao="BBBBBB", lat=-35.5, lon=138.0, ts=BASE_TS))
        report_a = tracker.update(
            make_msg(icao="AAAAAA", lat=-33.9, lon=139.1, ts=BASE_TS + timedelta(seconds=10))
        )
        assert report_a is not None
        # A's delta_r must be computed against A's first reading, not B's.
        assert report_a.delta_r_deg_per_sec is not None

    def test_duplicate_timestamp_returns_none_delta_r(self):
        tracker = BearingTracker()
        tracker.update(make_msg(lat=-34.0, lon=139.0, ts=BASE_TS))
        report = tracker.update(make_msg(lat=-33.9, lon=139.1, ts=BASE_TS))
        assert report is not None
        assert report.delta_r_deg_per_sec is None

    def test_out_of_order_timestamp_returns_none_delta_r(self):
        tracker = BearingTracker()
        tracker.update(make_msg(lat=-34.0, lon=139.0, ts=BASE_TS + timedelta(seconds=10)))
        report = tracker.update(make_msg(lat=-33.9, lon=139.1, ts=BASE_TS))
        assert report is not None
        assert report.delta_r_deg_per_sec is None
        # The stale message must not roll back the more-recent reading:
        # a third, newer message computes delta_r against the FIRST reading.
        report2 = tracker.update(
            make_msg(lat=-33.8, lon=139.2, ts=BASE_TS + timedelta(seconds=20))
        )
        assert report2 is not None
        assert report2.delta_r_deg_per_sec is not None

    def test_expired_aircraft_treated_as_fresh(self):
        tracker = BearingTracker()
        tracker.update(make_msg(lat=-34.0, lon=139.0, ts=BASE_TS))
        report = tracker.update(
            make_msg(
                lat=-33.9,
                lon=139.1,
                ts=BASE_TS + timedelta(seconds=AIRCRAFT_EXPIRY_SEC + 1.0),
            )
        )
        assert report is not None
        assert report.delta_r_deg_per_sec is None

    def test_icao_key_normalisation(self):
        tracker = BearingTracker()
        tracker.update(make_msg(icao="abc123", lat=-34.0, lon=139.0, ts=BASE_TS))
        report = tracker.update(
            make_msg(icao="ABC123", lat=-33.9, lon=139.1, ts=BASE_TS + timedelta(seconds=10))
        )
        assert report is not None
        # Same aircraft via case normalisation: state was shared.
        assert report.delta_r_deg_per_sec is not None
        assert report.icao == "ABC123"

    def test_evicts_oldest_aircraft_at_capacity(self):
        """At MAX_AIRCRAFT entries, a new distinct icao drops the oldest entry."""
        tracker = BearingTracker()
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

    def test_update_existing_icao_at_capacity_does_not_evict(self):
        """Updating an already-tracked icao at capacity must not trigger eviction."""
        tracker = BearingTracker()
        for i in range(MAX_AIRCRAFT):
            tracker.update(
                make_msg(icao=f"AC{i:04d}", ts=BASE_TS + timedelta(seconds=i))
            )
        assert len(tracker._state) == MAX_AIRCRAFT

        later_ts = BASE_TS + timedelta(seconds=MAX_AIRCRAFT + 1)
        report = tracker.update(
            make_msg(icao="AC0000", lat=-33.9, lon=139.1, ts=later_ts)
        )

        # The guard `icao_key not in self._state` skipped eviction: the count
        # is unchanged and no other aircraft was dropped.
        assert len(tracker._state) == MAX_AIRCRAFT
        assert "AC0000" in tracker._state
        # The stored reading was replaced with the new bearing/timestamp.
        _, stored_ts = tracker._state["AC0000"]
        assert stored_ts == later_ts
        # And the update produced a rate against the prior reading.
        assert report is not None
        assert report.delta_r_deg_per_sec is not None
