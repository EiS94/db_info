from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_MAX_CONNECTIONS
from .entity import build_device_info


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    sensors = []

    for i in range(DEFAULT_MAX_CONNECTIONS):
        sensors.append(DBTrainSensor(coordinator, entry, i))

    async_add_entities(sensors, True)


class DBTrainSensor(CoordinatorEntity, Entity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, index):
        super().__init__(coordinator)
        self.entry = entry
        self.index = index
        self._attr_icon = "mdi:train"

        self._attr_device_info = build_device_info(entry)
        self._attr_name = f"Verbindung {index + 1}"
        self._attr_unique_id = f"db_info_{entry.entry_id}_{index + 1}"

    @property
    def state(self):
        journeys = self.coordinator.data or {}
        journey = journeys.get("journeys").get(self.index) or journeys.get(
            "journeys"
        ).get(str(self.index))
        if journey:
            return journey.get("Departure Time Real") or journey.get("Departure Time")
        return None

    @property
    def extra_state_attributes(self):
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
            "Details": journey.get("Details"),
            "Source": journey.get("Source"),
        }