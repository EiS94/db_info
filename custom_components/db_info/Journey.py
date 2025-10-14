import io

from .Train import parse_train
from .TrainProblem import TrainProblem


class Journey:
    def __init__(self, trains):
        """
        :type trains: list[Train.Train]
        :param trains: list of trains that must be used for this journey in the correct order
        """
        self.trains = trains
        self.problems = {}
        self.detect_problems()
        name = ""
        for train in self.trains:
            name += train.name + " -> "
        self.name = name[0:-4]

    def detect_problems(self):
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
            i += 1
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
            if change_time.seconds / 60 < 2:
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
        name = ""
        for train in self.trains:
            name += train.name + " -> "
        dt_real = self.get_departure_time_real()
        if dt_real is not None:
            dt_real = dt_real.strftime("%Y-%m-%dT%H:%M:%S%z")
        at_real = self.get_arrival_time_real()
        if at_real is not None:
            at_real = at_real.strftime("%Y-%m-%dT%H:%M:%S%z")
        attributes = {
            "Name": name[0:-4],
            "Departure": self.get_departure(),
            "Arrival": self.get_destination(),
            "Transfers": self.get_number_of_train_changes(),
            "Duration": parse_duration(self.get_duration()),
            "Departure Time": self.get_departure_time().strftime("%Y-%m-%dT%H:%M:%S%z"),
            "Departure Time Real": dt_real,
            "Arrival Time": self.get_arrival_time().strftime("%Y-%m-%dT%H:%M:%S%z"),
            "Arrival Time Real": at_real,
            "Problems": problems,
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
    hours, remainder = divmod(time.seconds, 3600)
    minutes = remainder // 60
    if hours > 0:
        return f"{hours}h {minutes}min"
    else:
        return f"{minutes}min"


def parse_trip(json_data):
    trains = []
    for train in json_data["verbindungsAbschnitte"]:
        trains.append(parse_train(train))
    if trains[0].name == "Fußweg":
        trains.pop(0)
    if trains[-1].name == "Fußweg":
        trains.pop(-1)
    return Journey(trains)
