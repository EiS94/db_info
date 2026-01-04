from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .bahn_api import get_trip_info
from .const import (
    CONNECTION_ALL,
    DOMAIN,
    CONF_START,
    CONF_DESTINATION,
    CONF_UPDATE_INTERVAL,
    CONF_CONNECTION_TYPE,
    DEFAULT_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "button"]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the db_info integration (global setup)."""

    async def async_refresh_all(call: ServiceCall) -> None:
        """Refresh all db_info coordinators at once."""
        domain_data = hass.data.get(DOMAIN, {})
        _LOGGER.debug("Refreshing all db_info entries (%s found)", len(domain_data))

        for coordinator in domain_data.values():
            await coordinator.async_refresh()

    hass.services.async_register(
        DOMAIN,
        "refresh_all",
        async_refresh_all,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up db_info from a config entry."""

    start_entity = entry.data.get(CONF_START)
    destination_entity = entry.data.get(CONF_DESTINATION)

    update_interval = entry.options.get(
        CONF_UPDATE_INTERVAL,
        entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
    )

    async def async_update_data():
        """Fetch data from the Bahn API."""
        try:
            if not start_entity or not destination_entity:
                raise UpdateFailed("Start or destination entity not configured")

            start_state = hass.states.get(start_entity)
            dest_state = hass.states.get(destination_entity)

            if start_state is None:
                raise UpdateFailed(f"Start entity {start_entity} not found")
            if dest_state is None:
                raise UpdateFailed(f"Destination entity {destination_entity} not found")

            start_attrs = start_state.attributes
            dest_attrs = dest_state.attributes

            if "latitude" not in start_attrs or "longitude" not in start_attrs:
                raise UpdateFailed(
                    f"Start entity {start_entity} has no latitude/longitude"
                )

            if "latitude" not in dest_attrs or "longitude" not in dest_attrs:
                raise UpdateFailed(
                    f"Destination entity {destination_entity} has no latitude/longitude"
                )

            start_coords = (
                start_attrs["latitude"],
                start_attrs["longitude"],
            )
            dest_coords = (
                dest_attrs["latitude"],
                dest_attrs["longitude"],
            )

            connection_type = entry.options.get(
                CONF_CONNECTION_TYPE,
                entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_ALL),
            )

            return await get_trip_info(
                start_coords, dest_coords, connection_type=connection_type
            )

        except UpdateFailed:
            raise
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.exception("Error updating db_info data")
            raise UpdateFailed(err) from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"db_info_{entry.entry_id}",
        update_method=async_update_data,
        update_interval=timedelta(minutes=int(update_interval)),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a db_info config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload db_info config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
