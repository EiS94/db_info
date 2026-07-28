"""Platform for datetime input entities."""

from __future__ import annotations

from datetime import datetime
import logging

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .entity import build_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the datetime entity."""
    async_add_entities([DBDepartureDateTimeEntity(entry)])


class DBDepartureDateTimeEntity(DateTimeEntity, RestoreEntity):
    """Representation of a departure time datetime entity."""

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the datetime entity."""
        self._entry = entry
        self._attr_device_info = build_device_info(entry)
        self._attr_name = "Abfahrtszeit"
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_departure_time"
        self._attr_icon = "mdi:clock-outline"

        # Set default to current time with timezone
        self._attr_native_value = dt_util.now()

    async def async_added_to_hass(self) -> None:
        """Restore last state when entity is added to hass."""
        await super().async_added_to_hass()

        # Restore previous state if available
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in ["unknown", "unavailable"]:
            try:
                # Parse the ISO format datetime string with timezone
                self._attr_native_value = dt_util.parse_datetime(last_state.state)
                if self._attr_native_value is None:
                    raise ValueError("Failed to parse datetime")
                _LOGGER.debug(f"Restored datetime state: {self._attr_native_value}")
            except (ValueError, TypeError) as err:
                _LOGGER.warning(f"Could not restore datetime state: {err}")
                self._attr_native_value = dt_util.now()
        else:
            self._attr_native_value = dt_util.now()

    async def async_set_value(self, value: datetime) -> None:
        """Update the datetime value."""
        # Ensure timezone awareness
        if value.tzinfo is None:
            value = dt_util.as_local(value)
        self._attr_native_value = value
        self.async_write_ha_state()
        _LOGGER.debug(f"Departure time set to: {value}")

    @property
    def native_value(self) -> datetime | None:
        """Return the current datetime value."""
        return self._attr_native_value
