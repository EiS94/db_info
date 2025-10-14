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
    return datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S")


def parse_stop(json_data):
    name = json_data["name"]
    if "gleis" in json_data:
        platform = json_data["gleis"]
    else:
        platform = None
    if "abfahrtsZeitpunkt" in json_data:
        departure_time = parse_time(json_data["abfahrtsZeitpunkt"])
    else:
        departure_time = None
    if "ezAbfahrtsZeitpunkt" in json_data:
        departure_time_real = parse_time(json_data["ezAbfahrtsZeitpunkt"])
    else:
        departure_time_real = None
    if "ankunftsZeitpunkt" in json_data:
        arrival_time = parse_time(json_data["ankunftsZeitpunkt"])
    else:
        arrival_time = None
    if "ezAnkunftsZeitpunkt" in json_data:
        arrival_time_real = parse_time(json_data["ezAnkunftsZeitpunkt"])
    else:
        arrival_time_real = None
    notes = []
    for note in json_data["priorisierteMeldungen"]:
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
