from datetime import datetime, timezone
import logging
from zoneinfo import ZoneInfo

import aiohttp

from .Journey import Journey
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

EFA_TRIP_URL = "https://bahnland-bayern.de/efa/XML_TRIP_REQUEST2"

# EFA MOT (Means of Transport) class mapping
# class 16 = Fernverkehr (ICE, IC, EC, EN)
# class 13 = Regionalzug (RE, RB, IRE)
# class 14 = S-Bahn
# class  5 = Bus
# class  6 = Tram/Straßenbahn
# class  7 = U-Bahn
# class 10 = Schiff
# class  9 = Anrufpflichtig/AST
#
# inclMOT_N parameters use the index N, not the class value.
# Mapping: MOT index → product class
_MOT_ALL = {str(i): "true" for i in range(0, 21)}

_MOT_LONG_DISTANCE = {
    "inclMOT_0": "true",  # Zug (allgemein / Fernverkehr)
}

_MOT_REGIONAL = {
    "inclMOT_1": "true",  # S-Bahn (DB)
    "inclMOT_2": "true",  # U-Bahn
    "inclMOT_3": "true",  # Stadtbahn
    "inclMOT_4": "true",  # Tram
    "inclMOT_5": "true",  # Bus
    "inclMOT_6": "true",  # Regionalbus
    "inclMOT_7": "true",  # Schnellbus
    "inclMOT_8": "true",  # Seilbahn/Fähre
    "inclMOT_9": "true",  # AST/Anrufpflichtig
    "inclMOT_10": "true",  # Regionalzug
    "inclMOT_11": "true",  # Stadtexpress
}

# Internal transport type → MOT inclMOT_N key
_TYPE_TO_MOT = {
    "ICE": "inclMOT_0",
    "EC_IC": "inclMOT_0",
    "IR": "inclMOT_0",
    "REGIONAL": "inclMOT_10",
    "SBAHN": "inclMOT_1",
    "BUS": "inclMOT_5",
    "SCHIFF": "inclMOT_8",
    "UBAHN": "inclMOT_2",
    "TRAM": "inclMOT_4",
    "ANRUFPFLICHTIG": "inclMOT_9",
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

                # Use real-time arr/dep only when different from planned
                arr_real = (
                    arr_estimated
                    if arr_estimated and arr_estimated != arr_planned
                    else None
                )
                dep_real = (
                    dep_estimated
                    if dep_estimated and dep_estimated != dep_planned
                    else None
                )

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


async def get_trip_info(
    start_coordinates,
    destination_coordinates,
    connection_type="all",
    custom_datetime=None,
    transport_types=None,
):
    _LOGGER.debug("Fetching trip info from EFA API (bahnland-bayern.de)")

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
                time = datetime.now(ZoneInfo("Europe/Berlin"))
            _LOGGER.info("Using custom departure time: %s", time)
        except (ValueError, AttributeError) as err:
            _LOGGER.warning(
                "Could not parse custom datetime '%s': %s. Using current time.",
                custom_datetime,
                err,
            )
            time = datetime.now(ZoneInfo("Europe/Berlin"))
    else:
        time = datetime.now(ZoneInfo("Europe/Berlin"))

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

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                EFA_TRIP_URL, params=params, timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                response.raise_for_status()
                json_data = await response.json(content_type=None)
    except aiohttp.ClientError as err:
        _LOGGER.error("Error fetching data from EFA API: %s", err)
        return {"journeys": {}}

    _LOGGER.debug("Parsing EFA response")

    try:
        journeys = _parse_efa_response(json_data)
    except Exception as err:
        _LOGGER.error("Error parsing EFA response: %s", err)
        return {"journeys": {}}

    json_output = {"journeys": {}}
    for i, journey in enumerate(journeys):
        json_output["journeys"][i] = journey.to_json()

    _LOGGER.info(
        "Successfully fetched %d journeys from EFA API, timestamp: %f",
        len(journeys),
        time.timestamp(),
    )

    return json_output
