from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .bahn_api import get_trip_info
from .const import DOMAIN, CONF_START, CONF_DESTINATION, CONF_UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up db_info from a config entry."""

    # Start & Ziel bleiben dauerhaft in entry.data
    start_entity = entry.data[CONF_START]
    destination_entity = entry.data[CONF_DESTINATION]

    # Intervall kommt NUR aus entry.options,
    # sonst hat jeder Eintrag das gleiche Intervall!
    update_interval = entry.options.get(CONF_UPDATE_INTERVAL, 10)

    async def async_update_data():
        try:
            from_state = hass.states.get(start_entity)
            to_state = hass.states.get(destination_entity)

            if not from_state or not to_state:
                raise UpdateFailed("Person or zone entity not found")

            from_coords = (
                from_state.attributes["latitude"],
                from_state.attributes["longitude"],
            )
            to_coords = (
                to_state.attributes["latitude"],
                to_state.attributes["longitude"],
            )

            data = await get_trip_info(from_coords, to_coords)
            return data

        except Exception as e:
            raise UpdateFailed(f"Error fetching DB data: {e}") from e

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"db_info_{entry.entry_id}",
        update_method=async_update_data,
        update_interval=timedelta(minutes=update_interval),
    )

    await coordinator.async_config_entry_first_refresh()

    # Jeder Entry bekommt seinen eigenen Coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    return True
