from .Stop import format_time
from .Train import parse_train
from .TrainProblem import (
    TrainProblem,
    collect_notes,
    has_cancelled_flag,
    is_trip_cancelled_note,
)

import logging

_LOGGER = logging.getLogger(__name__)


class Journey:
    def __init__(self, trains, cancelled=False):
        self.trains = trains
        self.cancelled = cancelled
        self.problems = {}
        self.detect_problems()
        name = ""
        for train in self.trains:
            name += train.name + " -> "
        self.name = name[0:-4]

    def detect_problems(self):
        if self.cancelled:
            # First entry, so to_json() reports it as "the" problem.
            self.problems["Verbindung"] = TrainProblem.CANCELED
        for train in self.trains:
            self.problems.update(train.problems)
        for i in range(len(self.trains) - 1):
            train1 = self.trains[i]
            if train1.name == "Fußweg":
                continue
            train2 = self.trains[i + 1]
            if train2.name == "Fußweg":
                if len(self.trains) > i + 2:
                    train2 = self.trains[i + 2]
                else:
                    continue
            if (
                    train1.stops[-1].arrival_time_real is not None
                    and train2.stops[0].departure_time_real is not None
            ):
                change_time = (
                        train2.stops[0].departure_time_real
                        - train1.stops[-1].arrival_time_real
                )
            elif (
                    train2.stops[0].departure_time_real is None
                    and train1.stops[-1].arrival_time_real is not None
            ):
                change_time = (
                        train2.stops[0].departure_time - train1.stops[-1].arrival_time_real
                )
            else:
                change_time = (
                        train2.stops[0].departure_time - train1.stops[-1].arrival_time
                )
            # total_seconds(), not .seconds: a missed connection gives a
            # negative timedelta, whose .seconds is close to 86400.
            if change_time.total_seconds() / 60 < 2:
                self.problems[
                    f"{train1.get_destination()} -> {train2.get_departure()}"
                ] = TrainProblem.CHANGE_NOT_ACCESSIBLE

    def get_departure(self):
        return self.trains[0].stops[0].name

    def get_destination(self):
        return self.trains[-1].stops[-1].name

    def get_number_of_train_changes(self):
        counter = 0
        for train in self.trains:
            if train.name != "Fußweg":
                counter += 1
        return counter - 1

    def get_departure_time(self):
        return self.trains[0].stops[0].departure_time

    def get_departure_time_real(self):
        return self.trains[0].stops[0].departure_time_real

    def get_arrival_time(self):
        return self.trains[-1].stops[-1].arrival_time

    def get_arrival_time_real(self):
        return self.trains[-1].stops[-1].arrival_time_real

    def get_duration(self):
        # detect if there are complete real_time information
        # if so, use them - if not, use the scheduled information
        if self.get_arrival_time_real() is not None:
            arrival_time = self.get_arrival_time_real()
        else:
            arrival_time = self.get_arrival_time()
        if self.get_departure_time_real() is not None:
            departure_time = self.get_departure_time_real()
        else:
            departure_time = self.get_departure_time()
        return arrival_time - departure_time

    def __str__(self):
        return f"{self.get_departure()} -> {self.get_destination()}, Dauer: {self.get_duration()}, Train-Changes: {self.get_number_of_train_changes()}"

    def to_json(self):
        problems = None
        if len(self.problems) > 0:
            problems = str(next(iter(self.problems.values())))
        trains = []
        for train in self.trains:
            trains.append(train.to_json())
        attributes = {
            "Name": self.name,
            "Departure": self.get_departure(),
            "Arrival": self.get_destination(),
            "Transfers": self.get_number_of_train_changes(),
            "Duration": parse_duration(self.get_duration()),
            "Departure Time": format_time(self.get_departure_time()),
            "Departure Time Real": format_time(self.get_departure_time_real()),
            "Arrival Time": format_time(self.get_arrival_time()),
            "Arrival Time Real": format_time(self.get_arrival_time_real()),
            "Problems": problems,
            "Details": str(trains).replace("None", "null"),
        }
        return attributes

    def to_plain_text(self):
        return self.pretty_print()

    def pretty_print(self):
        output = ""
        for train in self.trains:
            if train.name == "Fußweg":
                output += "       ║ Fußweg\n       ║\n"
                continue
            output += f"{parse_time(train.get_departure_time())}  ┬  {train.get_departure()}\n"
            output += (
                f"{parse_time(train.get_departure_time_real())}  │  {train.name}\n"
            )
            output += f"       │  {train.get_number_of_stops()} Haltestellen\n"
            output += "       │\n"
            output += f"{parse_time(train.get_arrival_time())}  │\n"
            output += f"{parse_time(train.get_arrival_time_real())}  ┴  {train.get_destination()}\n"
            output += "       ║\n"
        return output[0:-9]


def parse_time(time):
    if time is None:
        return "     "
    return time.strftime("%H:%M")


def detect_image_size(journey):
    size = 0
    for train in journey.trains:
        if train.name == "Fußweg":
            size += 40
        else:
            size += 330
    return size + 20


def parse_duration(time):
    if time is None:
        return ""
    hours, remainder = divmod(int(time.total_seconds()), 3600)
    minutes = remainder // 60
    if hours > 0:
        return f"{hours}h {minutes}min"
    else:
        return f"{minutes}min"


def parse_trip(json_data):
    MAX_LEN = 200
    json_short = str(json_data)
    if len(json_short) > MAX_LEN:
        json_short = json_short[:MAX_LEN] + "…"

    _LOGGER.debug("Parsing journey from JSON data: %s", json_short)

    trains = []
    for train in json_data.get("verbindungsAbschnitte", []):
        trains.append(parse_train(train))
    if len(trains) > 1:
        if trains[0].name == "Fußweg":
            trains.pop(0)
        if trains[-1].name == "Fußweg":
            trains.pop(-1)
    cancelled = has_cancelled_flag(json_data) or any(
        is_trip_cancelled_note(note) for note in collect_notes(json_data)
    )
    return Journey(trains, cancelled)
