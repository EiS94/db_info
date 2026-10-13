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

from .const import DATETIME_ENTITY_SUFFIX, DOMAIN
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
    """Representation of the trip time datetime entity.

    Used either as a departure or an arrival time, depending on the
    "Ankunftszeit verwenden" switch (see switch.py).
    """

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the datetime entity."""
        self._entry = entry
        self._attr_device_info = build_device_info(entry)
        self._attr_name = "Reisezeit"
        # unique_id intentionally left as "_departure_time" so existing
        # entity_ids and automations referencing this entity keep working.
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}{DATETIME_ENTITY_SUFFIX}"
        self._attr_icon = "mdi:clock-outline"

    async def async_added_to_hass(self) -> None:
        """Restore last state when entity is added to hass."""
        await super().async_added_to_hass()

        value = None
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in ("unknown", "unavailable"):
            value = dt_util.parse_datetime(last_state.state)
            if value is None:
                _LOGGER.warning("Could not restore Reisezeit: %s", last_state.state)
            else:
                _LOGGER.debug("Restored Reisezeit: %s", value)
        await self._async_set(value or dt_util.now(), write_state=False)

    async def async_set_value(self, value: datetime) -> None:
        """Update the datetime value."""
        await self._async_set(value)
        _LOGGER.debug("Reisezeit set to: %s", value)

    async def _async_set(self, value: datetime, write_state: bool = True) -> None:
        # Naive values are meant in HA's time zone (as_local would treat
        # them as UTC instead).
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt_util.get_default_time_zone())
        coordinator = self._entry.runtime_data
        needs_refresh = coordinator.set_time_setting("custom_time", value)
        if write_state:
            self.async_write_ha_state()
        if needs_refresh:
            await coordinator.async_request_refresh()

    @property
    def native_value(self) -> datetime | None:
        """Return the current datetime value."""
        return self._entry.runtime_data.custom_time
