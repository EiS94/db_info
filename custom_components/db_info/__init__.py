from __future__ import annotations

import logging

import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN
from .coordinator import DBInfoUpdateCoordinator
from .sessions import async_close_dbnav_session

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "button", "datetime", "switch"]

# This integration is only ever set up via a config entry (config_flow in
# manifest.json); it has no YAML configuration options. async_setup below
# exists only to register the "refresh_all" service, not to accept
# configuration - hassfest requires this to be declared explicitly rather
# than left implicit.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


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

    # Without this, changed options (e.g. the update interval) would only
    # take effect after a Home Assistant restart.
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a db_info config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # The curl_cffi session is shared by all entries, so it is only closed
    # once the last loaded entry goes away (a reload opens a new one).
    if unload_ok and not any(
        other.entry_id != entry.entry_id and other.state is ConfigEntryState.LOADED
        for other in hass.config_entries.async_entries(DOMAIN)
    ):
        await async_close_dbnav_session(hass)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload db_info config entry after its options changed."""
    await hass.config_entries.async_reload(entry.entry_id)