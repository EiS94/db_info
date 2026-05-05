from datetime import datetime  # noqa: D100
import logging
import random
import uuid

import aiohttp

from .Journey import parse_trip

_LOGGER = logging.getLogger(__name__)

DB_API_URL = "https://www.bahn.de/web/api/angebote/fahrplan"

# User-Agent-Rotation
def random_chrome():
    major = random.randint(126, 128)
    patch = random.randint(6478, 6668)
    build = random.randint(29, 234)
    return (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{major}.0.{patch}.{build} Safari/537.36"
    )

def random_firefox():
    major = random.randint(128, 130)
    esr = "esr" if random.random() < 0.3 else ""
    return (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{major}.0) "
        f"Gecko/20100101 Firefox/{major}.0{esr}"
    )

def random_useragent():
    if random.random() <= 0.2:
        return random_firefox()
    return random_chrome()

async def get_trip_info(
    start_coordinates,
    destination_coordinates,
    connection_type="all",
    custom_datetime=None,
):
    _LOGGER.debug("Fetching trip info from Bahn API")

    if custom_datetime:
        # custom_datetime is already a datetime object (from datetime entity state)
        # or a string in ISO format from the entity
        try:
            if isinstance(custom_datetime, str):
                # Parse ISO format string (with timezone info)
                time = datetime.fromisoformat(custom_datetime)
                # Remove timezone info for API (API expects naive datetime)
                time = time.replace(tzinfo=None)
            elif isinstance(custom_datetime, datetime):
                # If it's already a datetime object, remove timezone if present
                time = (
                    custom_datetime.replace(tzinfo=None)
                    if custom_datetime.tzinfo
                    else custom_datetime
                )
            else:
                _LOGGER.warning(
                    f"Unexpected custom_datetime type: {type(custom_datetime)}. Using current time."
                )
                time = datetime.now()

            _LOGGER.info(f"Using custom departure time: {time}")
        except (ValueError, AttributeError) as err:
            _LOGGER.warning(
                f"Could not parse custom datetime '{custom_datetime}': {err}. Using current time."
            )
            time = datetime.now()
    else:
        time = datetime.now()

    time_str = time.strftime("%Y-%m-%dT%H:%M:%S")

    start_coordinates = convert_coordinates_to_db_format(start_coordinates)
    destination_coordinates = convert_coordinates_to_db_format(destination_coordinates)

    if connection_type == "regional":
        produktgattungen = [
            "REGIONAL",
            "SBAHN",
            "BUS",
            "SCHIFF",
            "UBAHN",
            "TRAM",
            "ANRUFPFLICHTIG",
        ]
    elif connection_type == "long_distance":
        produktgattungen = [
            "ICE",
            "EC_IC",
            "IR",
        ]
    else:
        produktgattungen = [
            "ICE",
            "EC_IC",
            "IR",
            "REGIONAL",
            "SBAHN",
            "BUS",
            "SCHIFF",
            "UBAHN",
            "TRAM",
            "ANRUFPFLICHTIG",
        ]

    data = {
        "abfahrtsHalt": start_coordinates,
        "anfrageZeitpunkt": time_str,
        "ankunftsHalt": destination_coordinates,
        "ankunftSuche": "ABFAHRT",
        "klasse": "KLASSE_2",
        "produktgattungen": produktgattungen,
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

    correlation_id = f"{uuid.uuid4()}_{uuid.uuid4()}"

    HEADERS = {
        "User-Agent":       random_useragent(),
        "Accept":           "application/json",
        "Content-Type":     "application/json; charset=utf-8",
        "Referer":          "https://www.bahn.de/buchung/fahrplan/suche",
        "Origin":           "https://www.bahn.de",
        "x-correlation-id": correlation_id
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                DB_API_URL, headers=HEADERS, json=data, timeout=20
            ) as response:
                response.raise_for_status()
                json_data = await response.json()
    except aiohttp.ClientError as err:
        _LOGGER.error("Error fetching data from Bahn API: %s", err)
        return {"journeys": {}}

    _LOGGER.debug("Parsing trip info from Bahn API response")

    journeys = []
    for journey in json_data.get("verbindungen", []):
        journeys.append(parse_trip(journey))

    json_output = {"journeys": {}}
    for i, journey in enumerate(journeys):
        json_output["journeys"][i] = journey.to_json()

    _LOGGER.info(
        "Successfully fetched %d journeys from Bahn API, timestamp: %f",
        len(journeys),
        time.timestamp(),
    )

    return json_output


def convert_coordinates_to_db_format(coordinates):
    """
    :type coordinates: tuple[float, float, str]
    :param coordinates: tuple of lat, lng coordinates, e.g. (50.0014936, 8.2591178)
    :return: string of the coordinates in db-format: # Y=..@X=.. Coordinates (without decimal point, 6 decimal places must be specified)
    """

    _LOGGER.debug("Converting coordinates to DB format")

    lat_split = str(coordinates[0]).split(".")
    dec = lat_split[1][0:6].ljust(6, "0")
    lat = f"{lat_split[0]}{dec}"

    lng_split = str(coordinates[1]).split(".")
    dec = lng_split[1][0:6].ljust(6, "0")
    lng = f"{lng_split[0]}{dec}"

    return f"Y={lat}@X={lng}"
