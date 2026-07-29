"""Common entity helpers for the db_info integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import DOMAIN


def build_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Build the shared DeviceInfo for all entities of a config entry.

    All entities for a given start -> destination route (5 connection
    sensors, the refresh button, the custom-time switch and the departure
    datetime) are grouped under one virtual "service" device, named after
    the route (the entry title). This lets entities use has_entity_name
    with just their own relative name (e.g. "Verbindung 1", "Refresh"),
    while Home Assistant composes the full display name from the device
    name automatically.
    """
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="DB Info",
        entry_type=DeviceEntryType.SERVICE,
    )
