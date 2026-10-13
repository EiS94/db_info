"""DataUpdateCoordinator for the db_info integration."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.restore_state import async_get as async_get_restore_state
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

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
    DATETIME_ENTITY_SUFFIX,
    DEFAULT_MAX_TRANSFERS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    USE_ARRIVAL_TIME_SUFFIX,
    USE_CUSTOM_TIME_SUFFIX,
)

_LOGGER = logging.getLogger(__name__)


class DBInfoUpdateCoordinator(DataUpdateCoordinator):
    """Fetches trip data for a single start -> destination config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator for one config entry."""
        self.entry = entry

        # Persists across polls so MOTIS/Transitous itineraries can be
        # refreshed (cheap) instead of re-planned (expensive) - see
        # bahn_api._fetch_from_motis. Lives as long as this coordinator
        # (i.e. the config entry), which is exactly the lifetime we want.
        self._motis_state = {}

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

        # Time settings of this entry, owned by the coordinator and written
        # by the switch/datetime entities (see set_time_setting). They are
        # seeded from the restored entity states so that the very first
        # refresh - which runs before the entities are added - already uses
        # them instead of silently falling back to "now".
        self.use_custom_time = False
        self.use_arrival_time = False
        self.custom_time: datetime | None = None
        self._restore_time_settings()

    def _restore_time_settings(self) -> None:
        """Seed the time settings from the entities' last stored states."""
        try:
            last_states = async_get_restore_state(self.hass).last_states
        except Exception:  # pylint: disable=broad-except
            # Restore-state storage not loaded (e.g. in some tests); the
            # entities still push their restored values once added.
            return

        entity_reg = er.async_get(self.hass)

        def last_state(platform: str, suffix: str) -> str | None:
            entity_id = entity_reg.async_get_entity_id(
                platform, DOMAIN, f"{DOMAIN}_{self.entry.entry_id}{suffix}"
            )
            stored = last_states.get(entity_id) if entity_id else None
            return stored.state.state if stored else None

        self.use_custom_time = last_state("switch", USE_CUSTOM_TIME_SUFFIX) == "on"
        self.use_arrival_time = last_state("switch", USE_ARRIVAL_TIME_SUFFIX) == "on"
        stored_time = last_state("datetime", DATETIME_ENTITY_SUFFIX)
        if stored_time:
            self.custom_time = dt_util.parse_datetime(stored_time)

    def set_time_setting(self, name: str, value) -> bool:
        """Update one time setting; return True if a refresh is needed.

        name is one of "use_custom_time", "use_arrival_time", "custom_time".
        Changes to the arrival switch or the time itself only affect the
        query while the custom-time switch is on.
        """
        if getattr(self, name) == value:
            return False
        setattr(self, name, value)
        return name == "use_custom_time" or self.use_custom_time

    def _get_custom_time(self) -> tuple[datetime | None, bool]:
        """Return (custom_time, is_arrival) for the next query."""
        if not self.use_custom_time or self.custom_time is None:
            return None, False
        return self.custom_time, self.use_arrival_time

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

            custom_datetime, is_arrival = self._get_custom_time()

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
                is_arrival=is_arrival,
                motis_state=self._motis_state,
            )

        except UpdateFailed:
            raise
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.exception("Error updating db_info data")
            raise UpdateFailed(err) from err
