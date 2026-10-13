from enum import Enum


class TrainProblem(Enum):
    DELAY = 1
    CANCELED = 2
    STOP_NOT_APPLICABLE = 3
    CHANGE_NOT_ACCESSIBLE = 4


# Realtime message fields of the DB Navigator API. The current (v9) mobile
# schema uses "echtzeitNotizen" plus single "serviceNotiz"/"topNotiz"
# objects; "priorisierteMeldungen" and "risNotizen" are from older schemas.
# "himNotizen" is deliberately left out: those are construction notices that
# often mention cancellations of *other* stops or dates (e.g. "The stop Mainz
# Hbf is cancelled") and would cause false positives.
_NOTE_LIST_FIELDS = ("echtzeitNotizen", "priorisierteMeldungen", "risNotizen")
_NOTE_SINGLE_FIELDS = ("serviceNotiz", "topNotiz")

# Language-independent markers (see db-vendo-client parse/remarks.js).
_STOP_CANCELLED_CODES = {"text.realtime.stop.cancelled", "HALT_AUSFALL"}
_TRIP_CANCELLED_CODES = {
    "text.realtime.connection.cancelled",
    "text.realtime.journey.cancelled",
}

# Text fallbacks, lower case. Both languages are needed: the API answers in
# whatever "Accept-Language" asks for, and other sources add German notes.
_STOP_CANCELLED_TEXTS = ("halt entfällt", "stop cancelled", "stop canceled")
_TRIP_CANCELLED_TEXTS = (
    "fällt aus",
    "nicht mehr fahrbar",
    "trip is not possible",
    "trip cancelled",
    "trip canceled",
    "connection cancelled",
    "connection canceled",
)


def collect_notes(json_data):
    """Return all realtime messages of a DB API object (connection, section
    or stop) as dicts with at least a "text" key."""
    notes = []
    for field in _NOTE_LIST_FIELDS:
        notes.extend(n for n in json_data.get(field) or [] if isinstance(n, dict))
    for field in _NOTE_SINGLE_FIELDS:
        note = json_data.get(field)
        if isinstance(note, dict):
            notes.append(note)
    return notes


def note_texts(notes):
    return [note["text"] for note in notes if note.get("text")]


def _note_matches(note, codes, texts):
    if isinstance(note, dict):
        if note.get("key") in codes or note.get("type") in codes:
            return True
        note = note.get("text") or ""
    note = note.lower()
    return any(text in note for text in texts)


def is_stop_cancelled_note(note):
    """True if a note (text or raw API dict) says a stop is not served."""
    return _note_matches(note, _STOP_CANCELLED_CODES, _STOP_CANCELLED_TEXTS)


def is_trip_cancelled_note(note):
    """True if a note (text or raw API dict) says a trip/connection is cancelled."""
    if is_stop_cancelled_note(note):
        return False
    return _note_matches(note, _TRIP_CANCELLED_CODES, _TRIP_CANCELLED_TEXTS)


def has_cancelled_flag(json_data):
    return any(
        json_data.get(key) is True
        for key in ("cancelled", "canceled", "ausfall", "ausgefallen")
    )
