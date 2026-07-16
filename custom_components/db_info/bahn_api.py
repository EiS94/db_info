from datetime import datetime, timedelta, timezone
import asyncio
import logging
import random
import uuid

import aiohttp

from .Journey import Journey, parse_trip
from .Train import Train
from .Stop import Stop
from .const import (
    CONNECTION_REGIONAL,
    CONNECTION_LONG_DISTANCE,
    CONNECTION_CUSTOM,
    TRANSPORT_TYPES_REGIONAL,
    TRANSPORT_TYPES_LONG_DISTANCE,
)

_LOGGER = logging.getLogger(__name__)

# Several EFA (Elektronische Fahrplanauskunft) instances expose the same
# XML_TRIP_REQUEST2 endpoint and can all answer DB-network trip requests.
# Since any single instance can be temporarily unavailable or slow, all of
# them are queried in parallel and the best usable response is used.
EFA_APIS = [
    {"name": "bahnland-bayern.de", "url": "https://bahnland-bayern.de/efa/XML_TRIP_REQUEST2", "bounds": None},
    {"name": "efa.de", "url": "https://www.efa.de/hit-efa/XML_TRIP_REQUEST2", "bounds": None},
    {"name": "efa-bw.de", "url": "http://www.efa-bw.de/nvbw/XML_TRIP_REQUEST2", "bounds": None},
    {
        "name": "vrr.de",
        "url": "https://www.vrr.de/vrr-efa/XML_TRIP_REQUEST2",
        # vrr.de appears to hang until timeout (instead of returning a fast
        # error) for trips outside its home region, so it is only queried
        # when origin AND destination roughly fall within North
        # Rhine-Westphalia. Approximate bounding box, not the exact border.
        "bounds": {"lat_min": 50.3, "lat_max": 52.6, "lon_min": 5.7, "lon_max": 9.5},
    },
]


def _in_bounds(coordinates, bounds):
    """Check whether (lat, lon) coordinates fall within a bounding box.

    bounds=None means "no restriction" (always in bounds).
    """
    if bounds is None:
        return True
    lat, lon = coordinates[0], coordinates[1]
    return (
        bounds["lat_min"] <= lat <= bounds["lat_max"]
        and bounds["lon_min"] <= lon <= bounds["lon_max"]
    )

# Timeout for a single EFA endpoint. Requests run concurrently, so this is
# the worst-case additional wait time, not a sum across all endpoints.
_EFA_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)

# The official bahn.de trip-planner API. It usually has the best/most
# reliable real-time data of all sources, but is an internal API not meant
# for external use, so it is queried with a rotating browser-like
# User-Agent to reduce the chance of being blocked as bot traffic.
DB_API_URL = "https://www.bahn.de/web/api/angebote/fahrplan"
_DB_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)
# Short timeout for the best-effort cookie warm-up - it must never be
# allowed to eat into the overall latency budget the way a full 10s+10s
# worst case would.
_DB_WARMUP_TIMEOUT = aiohttp.ClientTimeout(total=5)


def _chrome_profile():
    """A Chrome/Windows profile with headers that are consistent with each
    other (matching sec-ch-ua major version, etc.) - a bare User-Agent
    without matching Client-Hints headers is itself a bot signal."""
    major = random.randint(126, 128)
    patch = random.randint(6478, 6668)
    build = random.randint(29, 234)
    return {
        "user_agent": (
            f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{major}.0.{patch}.{build} Safari/537.36"
        ),
        "accept_language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
        # Real Chrome sends these Client-Hints headers on every request.
        "client_hints": {
            "sec-ch-ua": (
                f'"Chromium";v="{major}", "Not)A;Brand";v="8", '
                f'"Google Chrome";v="{major}"'
            ),
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        },
    }


def _firefox_profile():
    """A Firefox/Windows profile. Firefox does not send sec-ch-ua
    Client-Hints headers at all, so sending them alongside a Firefox
    User-Agent would itself be an inconsistency a bot filter can catch."""
    major = random.randint(128, 130)
    esr = "esr" if random.random() < 0.3 else ""
    return {
        "user_agent": (
            f"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{major}.0) "
            f"Gecko/20100101 Firefox/{major}.0{esr}"
        ),
        "accept_language": "de-DE,de;q=0.8,en-US;q=0.5,en;q=0.3",
        "client_hints": {},
    }


def _random_browser_profile():
    return _firefox_profile() if random.random() <= 0.2 else _chrome_profile()


def _db_navigation_headers(profile):
    """Headers for the 'warm-up' GET to the search page - looks like a
    real top-level page load, so the session picks up bahn.de's session
    cookie(s) before the API is called, same as a real browser would."""
    return {
        "User-Agent": profile["user_agent"],
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": profile["accept_language"],
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        **profile["client_hints"],
    }


def _db_api_headers(profile, correlation_id):
    """Headers for the actual XHR/fetch-style call to the trip API,
    as if made from JS running on the bahn.de search page."""
    return {
        "User-Agent": profile["user_agent"],
        "Accept": "application/json",
        "Accept-Language": profile["accept_language"],
        "Content-Type": "application/json; charset=utf-8",
        "Referer": "https://www.bahn.de/buchung/fahrplan/suche",
        "Origin": "https://www.bahn.de",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "x-correlation-id": correlation_id,
        **profile["client_hints"],
    }

# Some EFA instances (e.g. bahnland-bayern.de) reject requests that carry
# aiohttp's default "Python/3.x aiohttp/3.x" User-Agent as bot traffic and
# answer with HTTP 403. A browser-like User-Agent avoids that.
_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# EFA MOT (Means of Transport) class mapping
# class  1 = S-Bahn
# class  2 = U-Bahn
# class  3 = Tram
# class  4 = Tram
# class  5 = Stadtbus
# class  6 = Regionalbus
# class  7 = Expressbus
# class  8 = Sonstige
# class  9 = Schiff
# class 10 = AST/Rufbus
# class 11 = Sonstige
# class 13 = Nahverkehr
# class 14 = IC/EC
# class 15 = IC/EC
# class 16 = ICE
# class 17 = Sonstige
# class 20 = AST/Rufbus

# inclMOT_N parameters use the index N, not the class value.
# Mapping: MOT index → product class
_MOT_ALL = {str(i): "true" for i in range(0, 21)}

_MOT_LONG_DISTANCE = {
    "inclMOT_14": "true",  # IC/EC,
    "inclMOT_15": "true",  # IC/EC,
    "inclMOT_16": "true"   # ICE
}

_MOT_REGIONAL = {
    "inclMOT_1": "true",  # S-Bahn
    "inclMOT_2": "true",  # U-Bahn
    "inclMOT_3": "true",  # Tram
    "inclMOT_4": "true",  # Tram
    "inclMOT_5": "true",  # Stadtbus
    "inclMOT_6": "true",  # Regionalbus
    "inclMOT_7": "true",  # Expressbus
    "inclMOT_8": "true",  # Sonstige
    "inclMOT_9": "true",  # Schiff
    "inclMOT_10": "true",  # AST/Rufbus
    "inclMOT_11": "true",  # Sonstige
    "inclMOT_13": "true",  # Nahverkehr
    "inclMOT_17": "true",  # Sonstige
    "inclMOT_20": "true"  # AST/Rufbus
}

# Internal transport type → MOT inclMOT_N key
_TYPE_TO_MOT = {
    "SBAHN": "inclMOT_1",
    "UBAHN": "inclMOT_2",
    "TRAM": "inclMOT_3&inclMOT_4",
    "BUS": "inclMOT_5&inclMOT_6&inclMOT_7",
    "SCHIFF": "inclMOT_9",
    "AST/RUFBUS": "inclMOT_10&inclMOT_20",
    "ICE": "inclMOT_16",
    "IC/EC": "inclMOT_14&inclMOT_15",
    "Sonstige": "inclMOT_17&inclMOT_8&inclMOT_11",
    "NAHVERKEHR": "inclMOT_13"
}


def _build_mot_params(connection_type, custom_types=None):
    """Return dict of inclMOT_N params for the given connection type."""
    if connection_type == CONNECTION_CUSTOM and custom_types:
        mot = {}
        for t in custom_types:
            key = _TYPE_TO_MOT.get(t)
            if key:
                mot[key] = "true"
        return {"includedMeans": "checkbox", **mot}
    elif connection_type == CONNECTION_LONG_DISTANCE:
        return {"includedMeans": "checkbox", **_MOT_LONG_DISTANCE}
    elif connection_type == CONNECTION_REGIONAL:
        return {"includedMeans": "checkbox", **_MOT_REGIONAL}
    # Default: all
    return {
        "includedMeans": "checkbox",
        **{f"inclMOT_{i}": "true" for i in range(0, 21)},
    }


# Internal transport type → DB API "produktgattungen" value.
# "SONSTIGE" has no equivalent category in the DB API and is omitted; a
# custom selection consisting only of unmapped types falls back to "all".
_TYPE_TO_PRODUKTGATTUNG = {
    "SBAHN": "SBAHN",
    "UBAHN": "UBAHN",
    "TRAM": "TRAM",
    "BUS": "BUS",
    "SCHIFF": "SCHIFF",
    "AST/RUFBUS": "ANRUFPFLICHTIG",
    "ICE": "ICE",
    "IC/EC": "EC_IC",
    "NAHVERKEHR": "REGIONAL",
}

_PRODUKTGATTUNGEN_REGIONAL = [
    "REGIONAL", "SBAHN", "BUS", "SCHIFF", "UBAHN", "TRAM", "ANRUFPFLICHTIG",
]
_PRODUKTGATTUNGEN_LONG_DISTANCE = ["ICE", "EC_IC", "IR"]
_PRODUKTGATTUNGEN_ALL = _PRODUKTGATTUNGEN_LONG_DISTANCE + _PRODUKTGATTUNGEN_REGIONAL


def _build_produktgattungen(connection_type, custom_types=None):
    """Return list of "produktgattungen" for the DB API's given connection type."""
    if connection_type == CONNECTION_CUSTOM and custom_types:
        result = []
        for t in custom_types:
            value = _TYPE_TO_PRODUKTGATTUNG.get(t)
            if value and value not in result:
                result.append(value)
        if result:
            return result
        # No usable mapping (e.g. only "SONSTIGE" selected) -> fall back to "all"

    if connection_type == CONNECTION_LONG_DISTANCE:
        return _PRODUKTGATTUNGEN_LONG_DISTANCE
    if connection_type == CONNECTION_REGIONAL:
        return _PRODUKTGATTUNGEN_REGIONAL
    return _PRODUKTGATTUNGEN_ALL


def convert_coordinates_to_db_format(coordinates):
    """
    :type coordinates: tuple[float, float, str]
    :param coordinates: tuple of lat, lng coordinates, e.g. (50.0014936, 8.2591178)
    :return: string of the coordinates in db-format: # Y=..@X=.. Coordinates (without decimal point, 6 decimal places must be specified)
    """
    lat_split = str(coordinates[0]).split(".")
    dec = lat_split[1][0:6].ljust(6, "0")
    lat = f"{lat_split[0]}{dec}"

    lng_split = str(coordinates[1]).split(".")
    dec = lng_split[1][0:6].ljust(6, "0")
    lng = f"{lng_split[0]}{dec}"

    return f"Y={lat}@X={lng}"


def _parse_efa_time(iso_str):
    if not iso_str:
        return None

    try:
        if iso_str.endswith("Z"):
            return datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )

        return datetime.fromisoformat(iso_str)

    except Exception:
        return None


def _parse_efa_response(data):
    """Parse EFA XML_TRIP_REQUEST2 rapidJSON response into Journey objects."""
    journeys = []

    for raw_journey in data.get("journeys", []):
        trains = []

        for leg in raw_journey.get("legs", []):
            transportation = leg.get("transportation", {})
            product = transportation.get("product", {})
            origin = leg.get("origin", {})
            destination = leg.get("destination", {})

            is_walk = (
                    product.get("class") == 100
                    or product.get("name") == "footpath"
                    or not transportation.get("name")
            )

            if is_walk:
                dep_time = _parse_efa_time(
                    origin.get("departureTimeEstimated")
                    or origin.get("departureTimePlanned")
                )
                arr_time = _parse_efa_time(
                    destination.get("arrivalTimeEstimated")
                    or destination.get("arrivalTimePlanned")
                )
                walk_dep = Stop(
                    origin.get("name", ""), None, None, dep_time, None, None, []
                )
                walk_arr = Stop(
                    destination.get("name", ""), arr_time, None, None, None, None, []
                )
                trains.append(Train("Fußweg", None, [walk_dep, walk_arr], []))
                continue

            # Build train name
            disassembled = transportation.get("disassembledName") or ""
            t_name = transportation.get("name", "").strip()
            prod_name = product.get("name", "")

            if disassembled and disassembled != t_name:
                train_name = (
                    f"{prod_name} {disassembled}".strip() if prod_name else t_name
                )
            else:
                train_name = t_name

            direction = transportation.get("destination", {}).get("name")

            # Build stops from stopSequence
            stops = []
            stop_sequence = leg.get("stopSequence", [])

            # Always include origin as first stop if stopSequence is empty
            if not stop_sequence:
                stop_sequence = [origin, destination]

            for i, raw_stop in enumerate(stop_sequence):
                stop_name = raw_stop.get("name", "")
                props = raw_stop.get("properties", {})

                # Arrival times
                arr_planned = _parse_efa_time(raw_stop.get("arrivalTimePlanned"))
                arr_estimated = _parse_efa_time(raw_stop.get("arrivalTimeEstimated"))

                # Departure times
                dep_planned = _parse_efa_time(raw_stop.get("departureTimePlanned"))
                dep_estimated = _parse_efa_time(raw_stop.get("departureTimeEstimated"))

                # Platform: prefer realtimeStatus-affected value
                platform = props.get("platformName") or props.get("platform") or None
                planned_platform = props.get("plannedPlatformName") or platform

                arr_real = arr_estimated
                dep_real = dep_estimated

                stops.append(
                    Stop(
                        stop_name,
                        arr_planned,
                        arr_real,
                        dep_planned,
                        dep_real,
                        planned_platform,
                        [],
                    )
                )

            if stops:
                trains.append(Train(train_name, direction, stops, []))

        # Strip leading/trailing walk
        if len(trains) > 1:
            if trains[0].name == "Fußweg":
                trains.pop(0)
            if trains and trains[-1].name == "Fußweg":
                trains.pop(-1)

        if trains:
            journeys.append(Journey(trains))

    return journeys


async def _fetch_from_api(session, api, params):
    """Query a single EFA API and parse its response into Journey objects.

    Returns a dict {"name", "url", "journeys"} on success, or None if the
    API was unreachable, returned invalid data, or yielded no journeys.
    """
    name = api["name"]
    url = api["url"]

    try:
        async with session.get(
                url,
                params=params,
                headers=_REQUEST_HEADERS,
                timeout=_EFA_REQUEST_TIMEOUT,
        ) as response:
            response.raise_for_status()
            json_data = await response.json(content_type=None)
    except asyncio.TimeoutError:
        _LOGGER.warning(
            "EFA API '%s' (%s) not reachable: timed out after %ss",
            name, url, _EFA_REQUEST_TIMEOUT.total,
        )
        return None
    except aiohttp.ClientError as err:
        _LOGGER.warning(
            "EFA API '%s' (%s) not reachable: %s: %s",
            name, url, type(err).__name__, err or "no further details",
        )
        return None
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.warning(
            "EFA API '%s' (%s) returned invalid data: %s: %s",
            name, url, type(err).__name__, err or "no further details",
        )
        return None

    try:
        journeys = _parse_efa_response(json_data)
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.warning("Error parsing response from '%s': %s", name, err)
        return None

    if not journeys:
        _LOGGER.debug("EFA API '%s' returned no journeys", name)
        return None

    return {"name": name, "url": url, "journeys": journeys}


def _score_result(result):
    """Score a result set from one API for comparison against the others.

    Lower is better. Scoring is based on the *first* (soonest/next)
    journey in the list only - that is the one that actually becomes
    "Verbindung 1" in the sensors, so it's the one that matters for this
    comparison. Looking at "any journey anywhere in the list" or the
    shortest duration across the whole list (as done previously) could
    pick an API because some journey much later in the list happened to
    have real-time data or an unusually short duration, while the actual
    next connection shown to the user had neither.
    """
    first_journey = result["journeys"][0]
    has_realtime = (
        first_journey.get_departure_time_real() is not None
        or first_journey.get_arrival_time_real() is not None
    )
    return (0 if has_realtime else 1, first_journey.get_duration())


async def _fetch_from_db_api(session, data):
    """Query the official bahn.de trip planner API.

    Uses a full, internally-consistent browser profile (User-Agent +
    matching Client-Hints/Accept-Language) and a fresh correlation id per
    request, since this is an internal API not meant for external clients.
    Also performs a best-effort "warm-up" GET to the search page first, so
    the session picks up bahn.de's session cookie(s) the same way a real
    browser would before calling the API - if that fails, the actual
    request is attempted anyway. Returns a dict {"name", "url", "journeys"}
    on success, or None if the API was unreachable, returned invalid data,
    or yielded no journeys - matching the contract of _fetch_from_api so
    both can be scored together.
    """
    name = "bahn.de"
    url = DB_API_URL
    correlation_id = f"{uuid.uuid4()}_{uuid.uuid4()}"
    profile = _random_browser_profile()

    try:
        async with session.get(
                "https://www.bahn.de/buchung/fahrplan/suche",
                headers=_db_navigation_headers(profile),
                timeout=_DB_WARMUP_TIMEOUT,
        ) as warmup_response:
            await warmup_response.read()
    except (aiohttp.ClientError, asyncio.TimeoutError):
        pass  # best-effort only; proceed to the real request regardless

    headers = _db_api_headers(profile, correlation_id)

    try:
        async with session.post(
                url, headers=headers, json=data, timeout=_DB_REQUEST_TIMEOUT
        ) as response:
            response.raise_for_status()
            json_data = await response.json()
    except asyncio.TimeoutError:
        _LOGGER.warning(
            "DB API '%s' (%s) not reachable: timed out after %ss",
            name, url, _DB_REQUEST_TIMEOUT.total,
        )
        return None
    except aiohttp.ClientError as err:
        _LOGGER.warning(
            "DB API '%s' (%s) not reachable: %s: %s",
            name, url, type(err).__name__, err or "no further details",
        )
        return None
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.warning(
            "DB API '%s' (%s) returned invalid data: %s: %s",
            name, url, type(err).__name__, err or "no further details",
        )
        return None

    try:
        journeys = [
            parse_trip(journey) for journey in json_data.get("verbindungen", [])
        ]
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.warning("Error parsing response from '%s': %s", name, err)
        return None

    if not journeys:
        _LOGGER.debug("DB API '%s' returned no journeys", name)
        return None

    return {"name": name, "url": url, "journeys": journeys}


async def get_trip_info(
        start_coordinates,
        destination_coordinates,
        connection_type="all",
        custom_datetime=None,
        transport_types=None,
):
    applicable_efa_apis = [
        api for api in EFA_APIS
        if _in_bounds(start_coordinates, api["bounds"])
        and _in_bounds(destination_coordinates, api["bounds"])
    ]
    skipped_apis = [api["name"] for api in EFA_APIS if api not in applicable_efa_apis]
    if skipped_apis:
        _LOGGER.debug(
            "Skipping %s: trip is outside their coverage area",
            ", ".join(skipped_apis),
        )

    total_sources = len(applicable_efa_apis) + 1  # + bahn.de
    _LOGGER.debug(
        "Fetching trip info from %d APIs in parallel (%d EFA + bahn.de)",
        total_sources, len(applicable_efa_apis),
    )

    # Resolve departure time
    if custom_datetime:
        try:
            if isinstance(custom_datetime, str):
                time = datetime.fromisoformat(custom_datetime).astimezone()
            elif isinstance(custom_datetime, datetime):
                time = custom_datetime.astimezone()
            else:
                _LOGGER.warning(
                    "Unexpected custom_datetime type: %s. Using current time.",
                    type(custom_datetime),
                )
                time = datetime.now().astimezone()
            _LOGGER.info("Using custom departure time: %s", time)
        except (ValueError, AttributeError) as err:
            _LOGGER.warning(
                "Could not parse custom datetime '%s': %s. Using current time.",
                custom_datetime,
                err,
            )
            time = datetime.now().astimezone()
    else:
        time = datetime.now().astimezone()

    lat_s, lon_s = start_coordinates[0], start_coordinates[1]
    lat_d, lon_d = destination_coordinates[0], destination_coordinates[1]

    # EFA coordinate format: "lon:lat:WGS84[dd.ddddd]"
    coord_origin = f"{lon_s}:{lat_s}:WGS84[dd.ddddd]"
    coord_dest = f"{lon_d}:{lat_d}:WGS84[dd.ddddd]"

    mot_params = _build_mot_params(connection_type, transport_types)

    params = {
        "outputFormat": "rapidJSON",
        "language": "de",
        "type_origin": "coord",
        "name_origin": coord_origin,
        "type_destination": "coord",
        "name_destination": coord_dest,
        "itdDateDayMonthYear": time.strftime("%d.%m.%Y"),
        "itdTime": time.astimezone().strftime("%H:%M"),
        "itdTripDateTimeDepArr": "dep",
        "coordOutputFormat": "WGS84[dd.ddddd]",
        "useRealtime": "1",
        "calcOneDirection": "1",
        "calcNumberOfTrips": "5",
        "allInterchangesAsLegs": "1",
        "ptOptionsActive": "1",
        "itOptionsActive": "1",
        "lineRestriction": "400",
        "serverInfo": "0",
        **mot_params,
    }

    db_data = {
        "abfahrtsHalt": convert_coordinates_to_db_format(start_coordinates),
        "anfrageZeitpunkt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "ankunftsHalt": convert_coordinates_to_db_format(destination_coordinates),
        "ankunftSuche": "ABFAHRT",
        "klasse": "KLASSE_2",
        "produktgattungen": _build_produktgattungen(connection_type, transport_types),
        "reisende": [
            {
                "typ": "ERWACHSENER",
                "ermaessigungen": [
                    {"art": "KEINE_ERMAESSIGUNG", "klasse": "KLASSENLOS"}
                ],
                "alter": [],
                "anzahl": 1,
            }
        ],
        "schnelleVerbindungen": True,
        "sitzplatzOnly": False,
        "bikeCarriage": False,
        "reservierungsKontingenteVorhanden": False,
    }

    async with aiohttp.ClientSession() as session:
        tasks = [_fetch_from_api(session, api, params) for api in applicable_efa_apis]
        tasks.append(_fetch_from_db_api(session, db_data))
        results = await asyncio.gather(*tasks)

    valid_results = [result for result in results if result]

    if not valid_results:
        _LOGGER.error(
            "None of the %d APIs (EFA + bahn.de) returned usable data",
            total_sources,
        )
        return {"journeys": {}}

    best = min(valid_results, key=_score_result)
    best_score = _score_result(best)
    has_realtime = best_score[0] == 0
    next_connection_duration = best_score[1]

    _LOGGER.info(
        "Using result from '%s' (%d/%d sources usable, next connection: "
        "realtime=%s, duration=%s)",
        best["name"],
        len(valid_results),
        total_sources,
        has_realtime,
        next_connection_duration,
    )

    journeys = best["journeys"]

    json_output = {"journeys": {}}
    for i, journey in enumerate(journeys):
        journey_json = journey.to_json()
        journey_json["Source"] = best["name"]
        json_output["journeys"][i] = journey_json

    _LOGGER.info(
        "Successfully fetched %d journeys (source: %s), timestamp: %f",
        len(journeys),
        best["name"],
        time.timestamp(),
    )

    return json_output