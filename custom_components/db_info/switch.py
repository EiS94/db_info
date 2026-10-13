"""Platform for switch entities."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, USE_ARRIVAL_TIME_SUFFIX, USE_CUSTOM_TIME_SUFFIX
from .entity import build_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch entities."""
    async_add_entities(
        [DBUseCustomTimeSwitch(entry), DBUseArrivalTimeSwitch(entry)]
    )


class _DBTimeSettingSwitch(SwitchEntity, RestoreEntity):
    """Switch backed by one time setting of this entry's coordinator.

    The coordinator holds the actual value (see
    DBInfoUpdateCoordinator.set_time_setting), so every entry only ever
    reads its own switches.
    """

    _attr_has_entity_name = True
    _setting: str
    _suffix: str

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the switch entity."""
        self._entry = entry
        self._attr_device_info = build_device_info(entry)
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}{self._suffix}"

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return getattr(self._entry.runtime_data, self._setting)

    async def async_added_to_hass(self) -> None:
        """Restore last state when entity is added to hass."""
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        if last_state and last_state.state in ("on", "off"):
            _LOGGER.debug("Restored %s: %s", self._setting, last_state.state)
            await self._async_set(last_state.state == "on", write_state=False)

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off."""
        await self._async_set(False)

    async def _async_set(self, value: bool, write_state: bool = True) -> None:
        coordinator = self._entry.runtime_data
        needs_refresh = coordinator.set_time_setting(self._setting, value)
        if write_state:
            self.async_write_ha_state()
        if needs_refresh:
            await coordinator.async_request_refresh()


class DBUseCustomTimeSwitch(_DBTimeSettingSwitch):
    """Switch to use the custom time instead of the current time."""

    _setting = "use_custom_time"
    _suffix = USE_CUSTOM_TIME_SUFFIX
    _attr_name = "Benutzerdefinierte Zeit verwenden"


class DBUseArrivalTimeSwitch(_DBTimeSettingSwitch):
    """Switch to interpret the custom time as arrival time.

    Only relevant while `DBUseCustomTimeSwitch` is on. When this switch is
    off (default), the custom time set on the datetime entity is used as a
    departure time. When on, it is used as an arrival time instead ("I want
    to arrive by this time" instead of "I want to depart at this time").
    """

    _setting = "use_arrival_time"
    _suffix = USE_ARRIVAL_TIME_SUFFIX
    _attr_name = "Ankunftszeit verwenden"
    _attr_icon = "mdi:clock-end"
