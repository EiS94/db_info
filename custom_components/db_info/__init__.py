from datetime import timedelta  # noqa: D104
import json
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .bahn_api import get_trip_info
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up db_info from a config entry."""

    start_entity = entry.data["Startpunkt"]
    destination_entity = entry.data["Ziel"]
    update_interval = entry.data.get("uUpdate Intervall", 10)

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

        except Exception as e:  # noqa: BLE001
            raise UpdateFailed(f"Error fetching DB data: {e}")

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="db_info",
        update_method=async_update_data,
        update_interval=timedelta(minutes=update_interval),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    return True
