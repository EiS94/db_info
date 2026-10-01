from datetime import datetime

from .TrainProblem import TrainProblem


class Stop:
    def __init__(
        self,
        name,
        arrival_time,
        arrival_time_real,
        departure_time,
        departure_time_real,
        platform,
        notes,
    ):
        self.name = name
        self.arrival_time = arrival_time
        self.arrival_time_real = arrival_time_real
        self.departure_time = departure_time
        self.departure_time_real = departure_time_real
        self.platform = platform
        self.notes = notes
        self.problem = None
        self.detect_problems()

    def __str__(self):
        time_infos = ""
        if self.arrival_time is not None and self.departure_time is not None:
            time_infos = f"{self.arrival_time} ({self.arrival_time_real}) -> {self.departure_time} ({self.departure_time_real})"
        elif self.departure_time is not None:
            time_infos = f"{self.departure_time} ({self.departure_time_real})"
        elif self.arrival_time is not None:
            time_infos = f"{self.arrival_time} ({self.arrival_time_real})"
        return f"{self.name}: {time_infos}"

    def detect_problems(self):
        for note in self.notes:
            if "halt entfällt" in note.lower():
                self.problem = TrainProblem.STOP_NOT_APPLICABLE

    def get_arrival_delay(self):
        if self.arrival_time_real is not None:
            delay = self.arrival_time_real - self.arrival_time
            delay = delay.seconds
            return delay / 60
        else:
            return 0

    def get_departure_delay(self):
        if self.departure_time_real is not None:
            delay = self.departure_time_real - self.departure_time
            delay = delay.seconds
            return delay / 60
        else:
            return 0


def parse_time(time_str):
    # The mobile API includes a UTC offset ("...+02:00"); the bahn.de-web
    # API this was originally written against did not. datetime.fromisoformat
    # handles both, so it replaces the previous fixed strptime format that
    # broke on the offset with "ValueError: unconverted data remains".
    return datetime.fromisoformat(time_str)


def _get_stop_name(json_data):
    # In the schema this codebase was originally written against, the stop
    # name sits directly on the stopover object. In the mobile-API schema,
    # it's nested under an "ort" (or "station"/"stop") sub-object instead -
    # see db-vendo-client's parse/stopover.js (`st.ort || st.station || st`)
    # and parse/location.js (`l.name`). Try both rather than assuming one.
    if json_data.get("name"):
        return json_data["name"]
    for key in ("ort", "station", "stop", "halt"):
        nested = json_data.get(key)
        if isinstance(nested, dict) and nested.get("name"):
            return nested["name"]
    return "Unbekannt"


def _get_time(json_data, *keys):
    """Return the first present, non-null value among `keys`, parsed as a
    time. Different schema versions use different field names for the same
    thing (e.g. "abfahrtsZeitpunkt" vs "abgangsDatum" for a planned
    departure) - see db-vendo-client's parse/stopover.js for the exact
    fallback chain this mirrors."""
    for key in keys:
        value = json_data.get(key)
        if value:
            return parse_time(value)
    return None


def parse_stop(json_data):
    name = _get_stop_name(json_data)
    if "gleis" in json_data:
        platform = json_data["gleis"]
    elif "ezGleis" in json_data:
        platform = json_data["ezGleis"]
    else:
        platform = None
    departure_time = _get_time(json_data, "abfahrtsZeitpunkt", "abgangsDatum")
    departure_time_real = _get_time(json_data, "ezAbfahrtsZeitpunkt", "ezAbgangsDatum")
    arrival_time = _get_time(json_data, "ankunftsZeitpunkt", "ankunftsDatum")
    arrival_time_real = _get_time(json_data, "ezAnkunftsZeitpunkt", "ezAnkunftsDatum")
    notes = []
    for note in json_data.get("priorisierteMeldungen", []):
        notes.append(note["text"])
    return Stop(
        name,
        arrival_time,
        arrival_time_real,
        departure_time,
        departure_time_real,
        platform,
        notes,
    )
