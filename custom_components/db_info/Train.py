from .Stop import parse_stop
from .TrainProblem import TrainProblem


class Train:
    def __init__(self, name, direction, stops, notes):
        """
        :type name: str
        :type direction: str
        :type stops: list[Stop.Stop]
        :type notes: list[str]
        :param name:
        :param direction:
        :param stops:
        :param notes:
        """
        self.name = name
        self.direction = direction
        self.stops = stops
        self.notes = notes
        self.problems = {}
        self.detect_problems()

    def __str__(self):
        direction = ""
        if self.direction is not None:
            direction = f" to {self.direction}"
        return f"{self.name}{direction}"

    def detect_problems(self):
        for note in self.notes:
            if "verbindung fällt aus" in note.lower():
                self.problems[self.name] = TrainProblem.CANCELED
        if self.name != "Fußweg":
            if self.stops[0].problem == TrainProblem.STOP_NOT_APPLICABLE:
                self.problems[self.stops[0]] = TrainProblem.STOP_NOT_APPLICABLE
            if self.stops[-1].problem == TrainProblem.STOP_NOT_APPLICABLE:
                self.problems[self.stops[-1]] = TrainProblem.STOP_NOT_APPLICABLE
            if self.stops[-1].get_arrival_delay() > 20:
                self.problems[self.name] = TrainProblem.DELAY

    def get_number_of_stops(self):
        return len(self.stops) - 2

    def get_arrival_time(self):
        return self.stops[-1].arrival_time

    def get_arrival_time_real(self):
        return self.stops[-1].arrival_time_real

    def get_departure_time(self):
        return self.stops[0].departure_time

    def get_departure_time_real(self):
        return self.stops[0].departure_time_real

    def get_departure(self):
        return self.stops[0].name

    def get_destination(self):
        return self.stops[-1].name

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

    def get_arrival_platform(self):
        return self.stops[0].platform

    def get_destination_platform(self):
        return self.stops[-1].platform

    def to_json(self):
        attributes = {
            "Departure": self.get_departure(),
            "Arrival": self.get_arrival_platform(),
            "Duration": self.get_duration(),
        }


def parse_train(json_data):
    if "langText" in json_data["verkehrsmittel"]:
        name = json_data["verkehrsmittel"]["langText"]
    else:
        name = json_data["verkehrsmittel"]["name"]
    if "richtung" in json_data["verkehrsmittel"]:
        destination = json_data["verkehrsmittel"]["richtung"]
    else:
        destination = None
    notes = []
    for note in json_data["priorisierteMeldungen"]:
        notes.append(note["text"])
    stops = []
    for stop in json_data["halte"]:
        stops.append(parse_stop(stop))
    return Train(name, destination, stops, notes)
