from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN
from .coordinator import DBInfoUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "button", "datetime", "switch"]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the db_info integration (global setup)."""

    async def async_refresh_all(call: ServiceCall) -> None:
        """Refresh all db_info coordinators at once."""
        entries = hass.config_entries.async_entries(DOMAIN)
        _LOGGER.debug("Refreshing all db_info entries (%s found)", len(entries))

        for entry in entries:
            coordinator = getattr(entry, "runtime_data", None)
            if coordinator is not None:
                await coordinator.async_refresh()

    hass.services.async_register(
        DOMAIN,
        "refresh_all",
        async_refresh_all,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up db_info from a config entry."""
    coordinator = DBInfoUpdateCoordinator(hass, entry)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a db_info config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload db_info config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
