from enum import Enum


class TrainProblem(Enum):
    DELAY = 1
    CANCELED = 2
    STOP_NOT_APPLICABLE = 3
    CHANGE_NOT_ACCESSIBLE = 4
