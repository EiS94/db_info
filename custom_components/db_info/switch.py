"""Platform for switch entities."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch entity."""
    async_add_entities([DBUseCustomTimeSwitch(entry)])


class DBUseCustomTimeSwitch(SwitchEntity, RestoreEntity):
    """Representation of a switch to enable/disable custom departure time."""

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the switch entity."""
        self._entry = entry
        self._attr_name = f"{entry.title} Benutzerdefinierte Zeit verwenden"
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_custom_time"
        self._is_on = False

    async def async_added_to_hass(self) -> None:
        """Restore last state when entity is added to hass."""
        await super().async_added_to_hass()

        # Restore previous state if available
        last_state = await self.async_get_last_state()
        if last_state and last_state.state in ["on", "off"]:
            self._is_on = last_state.state == "on"
            _LOGGER.debug(f"Restored switch state: {self._is_on}")
        else:
            self._is_on = False

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self._is_on

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        self._is_on = True
        self.async_write_ha_state()
        _LOGGER.debug("Custom departure time enabled")

        # Trigger coordinator refresh to use the custom time
        coordinator = self.hass.data[DOMAIN][self._entry.entry_id]
        await coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off."""
        self._is_on = False
        self.async_write_ha_state()
        _LOGGER.debug("Custom departure time disabled")

        # Trigger coordinator refresh to use current time
        coordinator = self.hass.data[DOMAIN][self._entry.entry_id]
        await coordinator.async_request_refresh()
