"""Unit tests for time-zone handling and request building in bahn_api."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.util import dt as dt_util

from custom_components.db_info import bahn_api
from custom_components.db_info.Journey import Journey, parse_trip
from custom_components.db_info.Stop import Stop, format_time, parse_time
from custom_components.db_info.Train import Train
from custom_components.db_info.TrainProblem import TrainProblem
from custom_components.db_info.const import CONNECTION_CUSTOM

BERLIN = ZoneInfo("Europe/Berlin")


@pytest.fixture
def ha_time_zone():
    """Run with HA configured for Europe/Berlin, restoring it afterwards."""
    previous = dt_util.get_default_time_zone()
    dt_util.set_default_time_zone(BERLIN)
    yield
    dt_util.set_default_time_zone(previous)


def test_parse_time_treats_offsetless_times_as_german_local_time():
    """Offset-less times mean German time, not the TZ of the HA process."""
    assert parse_time("2026-07-28T10:00:00") == datetime(
        2026, 7, 28, 10, 0, tzinfo=BERLIN
    )


def test_format_time_is_identical_for_utc_and_local_sources(ha_time_zone):
    """EFA/MOTIS answer in UTC, DB in local time - the attributes must
    not depend on which source won."""
    from_utc = bahn_api._parse_motis_time("2026-07-28T08:00:00Z")
    from_local = parse_time("2026-07-28T10:00:00+02:00")
    assert format_time(from_utc) == format_time(from_local) == (
        "2026-07-28T10:00:00+0200"
    )


def _stop(name, arr=None, arr_real=None, dep=None, dep_real=None):
    return Stop(name, arr, arr_real, dep, dep_real, None, [])


def test_early_arrival_is_not_reported_as_delay():
    planned = datetime(2026, 7, 28, 10, 0, tzinfo=BERLIN)
    stops = [
        _stop("A", dep=planned - timedelta(hours=1)),
        _stop("B", arr=planned, arr_real=planned - timedelta(minutes=1)),
    ]
    assert stops[1].get_arrival_delay() == -1
    assert TrainProblem.DELAY not in Train("RE 1", None, stops, []).problems.values()


def test_missed_connection_is_reported():
    """A negative transfer time must be flagged, not wrap around to ~24h."""
    t = datetime(2026, 7, 28, 10, 0, tzinfo=BERLIN)
    first = Train(
        "RE 1", None,
        [_stop("A", dep=t), _stop("B", arr=t + timedelta(minutes=30),
                                  arr_real=t + timedelta(minutes=40))],
        [],
    )
    second = Train(
        "RE 2", None,
        [_stop("B", dep=t + timedelta(minutes=35)),
         _stop("C", arr=t + timedelta(minutes=60))],
        [],
    )
    journey = Journey([first, second])
    assert TrainProblem.CHANGE_NOT_ACCESSIBLE in journey.problems.values()


def _dbnav_trip(first_stop_notes, trip_notes=()):
    """Minimal DB Navigator v9 connection (Rohrbach(Ilm) -> München Hbf)."""
    return {
        "echtzeitNotizen": list(trip_notes),
        "verbindungsAbschnitte": [{
            "typ": "FAHRZEUG",
            "langtext": "RE1 (4699)",
            "richtung": "München Hbf",
            "echtzeitNotizen": [],
            "halte": [
                {"ort": {"name": "Rohrbach(Ilm)"},
                 "abgangsDatum": "2026-10-06T07:20:00+02:00",
                 "echtzeitNotizen": list(first_stop_notes)},
                {"ort": {"name": "München Hbf"},
                 "ankunftsDatum": "2026-10-06T07:56:00+02:00",
                 "ezAnkunftsDatum": "2026-10-06T07:56:00+02:00",
                 "echtzeitNotizen": []},
            ],
        }],
    }


@pytest.mark.parametrize("note", [
    {"text": "Halt entfällt", "prio": "HOCH"},
    {"text": "Stop cancelled", "prio": "HOCH"},
    {"key": "text.realtime.stop.cancelled", "text": "Arrêt supprimé"},
    {"type": "HALT_AUSFALL", "text": "?"},
])
def test_dbnav_cancelled_departure_stop_is_reported(note):
    """Issue #23: the v9 schema carries stop messages in "echtzeitNotizen"
    (not "priorisierteMeldungen"), in the language of Accept-Language."""
    journey = parse_trip(_dbnav_trip([note]))
    assert journey.trains[0].stops[0].problem == TrainProblem.STOP_NOT_APPLICABLE
    assert journey.to_json()["Problems"] == str(TrainProblem.STOP_NOT_APPLICABLE)


@pytest.mark.parametrize("note", [
    {"text": "Verbindung fällt aus"},
    {"key": "text.realtime.connection.cancelled", "text": "Trip is not possible"},
])
def test_dbnav_cancelled_connection_is_reported(note):
    journey = parse_trip(_dbnav_trip([], [note]))
    assert journey.to_json()["Problems"] == str(TrainProblem.CANCELED)


def test_dbnav_harmless_notes_are_not_problems():
    journey = parse_trip(_dbnav_trip(
        [{"key": "text.realtime.stop.entry.disabled", "text": "Hält nur zum Aussteigen"}],
        [{"text": "Delay of previous train", "prio": "HOCH"}],
    ))
    assert journey.problems == {}


def test_motis_cancelled_stop_is_reported():
    itinerary = {
        "legs": [{
            "mode": "REGIONAL_RAIL",
            "displayName": "RE1",
            "from": {"name": "Rohrbach(Ilm)", "cancelled": True,
                     "scheduledDeparture": "2026-10-06T05:20:00Z"},
            "to": {"name": "München Hbf",
                   "scheduledArrival": "2026-10-06T05:56:00Z"},
        }],
    }
    journey = bahn_api._parse_motis_itineraries([itinerary])[0][0]
    assert TrainProblem.STOP_NOT_APPLICABLE in journey.problems.values()


def test_custom_efa_mot_params_are_separate_keys():
    params = bahn_api._build_mot_params(CONNECTION_CUSTOM, ["TRAM", "SONSTIGE"])
    assert params == {
        "includedMeans": "checkbox",
        "inclMOT_3": "true",
        "inclMOT_4": "true",
        "inclMOT_8": "true",
        "inclMOT_11": "true",
        "inclMOT_17": "true",
    }


async def test_requests_use_german_local_time_for_custom_time():
    """A custom time stored in UTC must reach the offset-less EFA request
    as German local time."""
    captured = {}

    async def fake_efa(session, api, params):
        captured["efa"] = params
        return None

    with patch.object(bahn_api, "_fetch_from_dbnav_api", AsyncMock(return_value=None)), \
            patch.object(bahn_api, "_fetch_from_api", fake_efa), \
\
            patch.object(bahn_api, "_fetch_from_motis", AsyncMock(return_value=None)):
        await bahn_api.get_trip_info(
            (49.79, 9.95),
            (49.80, 9.96),
            custom_datetime=datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc),
        )

    assert captured["efa"]["itdTime"] == "10:00"
    assert captured["efa"]["itdDateDayMonthYear"] == "28.07.2026"
