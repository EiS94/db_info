from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity import build_device_info


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities([DBRefreshButton(coordinator, entry)])


class DBRefreshButton(CoordinatorEntity, ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = build_device_info(entry)
        self._attr_name = "Refresh"
        self._attr_unique_id = f"refresh_{entry.entry_id}"

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    async def async_press(self) -> None:
        await self.coordinator.async_refresh()
