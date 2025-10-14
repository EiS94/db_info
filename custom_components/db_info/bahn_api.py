from datetime import datetime  # noqa: D100
import logging

import aiohttp

from .Journey import parse_trip

_LOGGER = logging.getLogger(__name__)

DB_API_URL = "https://www.bahn.de/web/api/angebote/fahrplan"

DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "de",
    "Content-Type": "application/json; charset=utf-8",
    "Origin": "https://www.bahn.de",
    "Referer": "https://www.bahn.de/buchung/fahrplan/suche",
}


async def get_trip_info(start_coordinates, destination_coordinates):
    """
    Get train connection info between two coordinate pairs from Bahn.de.
    Returns dict of parsed journeys.
    """

    time = datetime.now()

    time_str = time.strftime("%Y-%m-%dT%H:%M:%S")

    start_coordinates = convert_coordinates_to_db_format(start_coordinates)
    destination_coordinates = convert_coordinates_to_db_format(destination_coordinates)

    data = {
        "abfahrtsHalt": start_coordinates,
        "anfrageZeitpunkt": time_str,
        "ankunftsHalt": destination_coordinates,
        "ankunftSuche": "ABFAHRT",
        "klasse": "KLASSE_2",
        "produktgattungen": [
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
        ],
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

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                DB_API_URL, headers=DEFAULT_HEADERS, json=data, timeout=10
            ) as response:
                response.raise_for_status()
                json_data = await response.json()
    except aiohttp.ClientError as err:
        _LOGGER.error("Error fetching data from Bahn API: %s", err)
        return {"journeys": {}}

    journeys = []
    for journey in json_data.get("verbindungen", []):
        journeys.append(parse_trip(journey))

    json_output = {"journeys": {}}
    for i, journey in enumerate(journeys):
        json_output["journeys"][i] = journey.to_json()

    _LOGGER.info("Successfully fetched %d journeys from Bahn API", len(journeys))

    return json_output


def convert_coordinates_to_db_format(coordinates):
    """
    :type coordinates: tuple[float, float, str]
    :param coordinates: tuple of lat, lng coordinates, e.g. (50.0014936, 8.2591178)
    :return: string of the coordinates in db-format: # Y=..@X=.. Coordinates (without decimal point, 6 decimal places must be specified)
    """
    lat_split = str(coordinates[0]).split(".")
    lat = f"{lat_split[0]}{lat_split[1][0:6]}"
    lng_split = str(coordinates[1]).split(".")
    lng = f"{lng_split[0]}{lng_split[1][0:6]}"
    return f"Y={lat}@X={lng}"
