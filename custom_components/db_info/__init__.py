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
    CONNECTION_CUSTOM,
    DOMAIN,
    CONF_START,
    CONF_DESTINATION,
    CONF_UPDATE_INTERVAL,
    CONF_CONNECTION_TYPE,
    CONF_TRANSPORT_TYPES,
    DEFAULT_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "button", "datetime", "switch"]


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

            transport_types = None
            if connection_type == CONNECTION_CUSTOM:
                transport_types = entry.options.get(
                    CONF_TRANSPORT_TYPES,
                    entry.data.get(CONF_TRANSPORT_TYPES, None),
                ) or None

            # Find the switch and datetime entities by unique_id
            from homeassistant.helpers import entity_registry as er

            entity_reg = er.async_get(hass)
            custom_datetime = None

            # Find switch entity
            switch_unique_id = f"{DOMAIN}_{entry.entry_id}_custom_time"
            switch_entity_id = entity_reg.async_get_entity_id(
                "switch", DOMAIN, switch_unique_id
            )

            # Find datetime entity
            datetime_unique_id = f"{DOMAIN}_{entry.entry_id}_departure_time"
            datetime_entity_id = entity_reg.async_get_entity_id(
                "datetime", DOMAIN, datetime_unique_id
            )

            if switch_entity_id and datetime_entity_id:
                custom_time_state = hass.states.get(switch_entity_id)

                if custom_time_state and custom_time_state.state == "on":
                    datetime_state = hass.states.get(datetime_entity_id)
                    if datetime_state and datetime_state.state not in [
                        "unknown",
                        "unavailable",
                    ]:
                        custom_datetime = datetime_state.state
                        _LOGGER.debug(f"Using custom departure time: {custom_datetime}")
            else:
                _LOGGER.debug(
                    f"Custom time entities not found yet (switch: {switch_entity_id}, datetime: {datetime_entity_id})"
                )

            return await get_trip_info(
                start_coords,
                dest_coords,
                connection_type=connection_type,
                custom_datetime=custom_datetime,
                transport_types=transport_types,
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
