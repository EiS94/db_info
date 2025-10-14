from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, DEFAULT_MAX_CONNECTIONS


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the db_info sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    sensors = []

    for i in range(DEFAULT_MAX_CONNECTIONS):
        sensors.append(DBTrainSensor(coordinator, entry, i))

    async_add_entities(sensors, True)


class DBTrainSensor(CoordinatorEntity, Entity):
    """Representation of a DB train connection."""

    def __init__(self, coordinator, entry, index):
        super().__init__(coordinator)
        self.entry = entry
        self.index = index
        self._attr_icon = "mdi:train"

        # Dynamischer Name & eindeutige ID
        self._attr_name = f"{entry.title} Verbindung {index + 1}"
        self._attr_unique_id = f"db_info_{entry.entry_id}_{index + 1}"

    @property
    def state(self):
        """Return the departure time of the train."""
        journeys = self.coordinator.data or {}
        journey = journeys.get("journeys").get(self.index) or journeys.get(
            "journeys"
        ).get(str(self.index))
        if journey:
            return journey.get("Departure Time Real") or journey.get("Departure Time")
        return None

    @property
    def extra_state_attributes(self):
        """Return the rest of the journey info as attributes."""
        journeys = self.coordinator.data or {}
        journey = journeys.get("journeys").get(self.index) or journeys.get(
            "journeys"
        ).get(str(self.index))
        if not journey:
            return {}

        return {
            "Departure": journey.get("Departure"),
            "Arrival": journey.get("Arrival"),
            "Departure Time": journey.get("Departure Time"),
            "Departure Time Real": journey.get("Departure Time Real"),
            "Arrival Time": journey.get("Arrival Time"),
            "Arrival Time Real": journey.get("Arrival Time Real"),
            "Duration": journey.get("Duration"),
            "Name": journey.get("Name"),
            "Transfers": journey.get("Transfers"),
            "Problems": journey.get("Problems"),
        }
