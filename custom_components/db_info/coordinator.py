"""DataUpdateCoordinator for the db_info integration."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .bahn_api import get_trip_info
from .const import (
    CONF_CONNECTION_TYPE,
    CONF_DESTINATION,
    CONF_MAX_TRANSFERS,
    CONF_START,
    CONF_TRANSPORT_TYPES,
    CONF_UPDATE_INTERVAL,
    CONNECTION_ALL,
    CONNECTION_CUSTOM,
    DEFAULT_MAX_TRANSFERS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class DBInfoUpdateCoordinator(DataUpdateCoordinator):
    """Fetches trip data for a single start -> destination config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator for one config entry."""
        self.entry = entry

        update_interval = entry.options.get(
            CONF_UPDATE_INTERVAL,
            entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )

        super().__init__(
            hass,
            _LOGGER,
            name=f"db_info_{entry.entry_id}",
            update_interval=timedelta(minutes=int(update_interval)),
        )

    def _get_custom_departure_time(self) -> str | None:
        """Return the user-set custom departure time, if its switch is on."""
        entity_reg = er.async_get(self.hass)

        switch_unique_id = f"{DOMAIN}_{self.entry.entry_id}_custom_time"
        switch_entity_id = entity_reg.async_get_entity_id(
            "switch", DOMAIN, switch_unique_id
        )

        datetime_unique_id = f"{DOMAIN}_{self.entry.entry_id}_departure_time"
        datetime_entity_id = entity_reg.async_get_entity_id(
            "datetime", DOMAIN, datetime_unique_id
        )

        if not switch_entity_id or not datetime_entity_id:
            _LOGGER.debug(
                "Custom time entities not found yet (switch: %s, datetime: %s)",
                switch_entity_id,
                datetime_entity_id,
            )
            return None

        custom_time_state = self.hass.states.get(switch_entity_id)
        if not custom_time_state or custom_time_state.state != "on":
            return None

        datetime_state = self.hass.states.get(datetime_entity_id)
        if not datetime_state or datetime_state.state in ("unknown", "unavailable"):
            return None

        _LOGGER.debug("Using custom departure time: %s", datetime_state.state)
        return datetime_state.state

    async def _async_update_data(self):
        """Fetch data from the configured trip-planning sources."""
        entry = self.entry
        start_entity = entry.data.get(CONF_START)
        destination_entity = entry.data.get(CONF_DESTINATION)

        try:
            if not start_entity or not destination_entity:
                raise UpdateFailed("Start or destination entity not configured")

            start_state = self.hass.states.get(start_entity)
            dest_state = self.hass.states.get(destination_entity)

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

            start_coords = (start_attrs["latitude"], start_attrs["longitude"])
            dest_coords = (dest_attrs["latitude"], dest_attrs["longitude"])

            connection_type = entry.options.get(
                CONF_CONNECTION_TYPE,
                entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_ALL),
            )

            transport_types = None
            if connection_type == CONNECTION_CUSTOM:
                transport_types = (
                    entry.options.get(
                        CONF_TRANSPORT_TYPES,
                        entry.data.get(CONF_TRANSPORT_TYPES, None),
                    )
                    or None
                )

            custom_datetime = self._get_custom_departure_time()

            max_transfers = entry.options.get(
                CONF_MAX_TRANSFERS,
                entry.data.get(CONF_MAX_TRANSFERS, DEFAULT_MAX_TRANSFERS),
            )

            return await get_trip_info(
                start_coords,
                dest_coords,
                connection_type=connection_type,
                custom_datetime=custom_datetime,
                transport_types=transport_types,
                max_transfers=max_transfers,
            )

        except UpdateFailed:
            raise
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.exception("Error updating db_info data")
            raise UpdateFailed(err) from err
