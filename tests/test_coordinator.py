"""Unit tests for DBInfoUpdateCoordinator, now that it's its own module."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.db_info.const import (
    CONF_CONNECTION_TYPE,
    CONF_DESTINATION,
    CONF_START,
    CONNECTION_ALL,
    DOMAIN,
)
from custom_components.db_info.coordinator import DBInfoUpdateCoordinator

SOME_JOURNEYS = {"journeys": {0: {"Name": "RE 1"}}}


def _make_entry(hass, **data):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Home -> Work",
        data={
            CONF_START: "zone.home",
            CONF_DESTINATION: "zone.work",
            CONF_CONNECTION_TYPE: CONNECTION_ALL,
            **data,
        },
        options={},
    )
    entry.add_to_hass(hass)
    return entry


async def _setup_zones(hass):
    hass.states.async_set(
        "zone.home", "0", {"latitude": 49.79, "longitude": 9.95, "friendly_name": "Home"}
    )
    hass.states.async_set(
        "zone.work", "0", {"latitude": 48.13, "longitude": 11.58, "friendly_name": "Work"}
    )


@pytest.mark.asyncio
async def test_update_data_success_calls_get_trip_info_with_coordinates(hass):
    """A normal update must resolve both entities' coordinates and pass
    them straight through to get_trip_info."""
    await _setup_zones(hass)
    entry = _make_entry(hass)
    coordinator = DBInfoUpdateCoordinator(hass, entry)

    mock_get_trip_info = AsyncMock(return_value=SOME_JOURNEYS)
    with patch(
        "custom_components.db_info.coordinator.get_trip_info", new=mock_get_trip_info
    ):
        result = await coordinator._async_update_data()

    assert result == SOME_JOURNEYS
    mock_get_trip_info.assert_awaited_once()
    call = mock_get_trip_info.await_args
    assert call.args[0] == (49.79, 9.95)
    assert call.args[1] == (48.13, 11.58)
    assert call.kwargs["connection_type"] == CONNECTION_ALL


@pytest.mark.asyncio
async def test_update_data_missing_start_destination_raises(hass):
    """No start/destination configured at all must raise UpdateFailed,
    not crash with a KeyError/AttributeError."""
    entry = MockConfigEntry(domain=DOMAIN, title="Broken", data={}, options={})
    entry.add_to_hass(hass)
    coordinator = DBInfoUpdateCoordinator(hass, entry)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_update_data_entity_not_found_raises(hass):
    """A configured entity that doesn't (yet) exist must raise UpdateFailed."""
    entry = _make_entry(hass)
    coordinator = DBInfoUpdateCoordinator(hass, entry)
    # Note: zones were never created here on purpose.

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_update_data_entity_without_coordinates_raises(hass):
    """An entity that exists but has no latitude/longitude must raise
    UpdateFailed instead of an unhandled KeyError."""
    hass.states.async_set("zone.home", "0", {"friendly_name": "Home"})  # no coords
    hass.states.async_set(
        "zone.work", "0", {"latitude": 48.13, "longitude": 11.58, "friendly_name": "Work"}
    )
    entry = _make_entry(hass)
    coordinator = DBInfoUpdateCoordinator(hass, entry)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_update_data_get_trip_info_exception_becomes_update_failed(hass):
    """Any unexpected exception from get_trip_info must be converted into
    UpdateFailed, not propagate raw (which would crash the coordinator)."""
    await _setup_zones(hass)
    entry = _make_entry(hass)
    coordinator = DBInfoUpdateCoordinator(hass, entry)

    with patch(
        "custom_components.db_info.coordinator.get_trip_info",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_custom_departure_time_used_when_switch_on(hass):
    """If the custom-time switch is on and the datetime has a real value,
    it must be passed through as custom_datetime."""
    await _setup_zones(hass)
    entry = _make_entry(hass)
    coordinator = DBInfoUpdateCoordinator(hass, entry)

    switch_unique_id = f"{DOMAIN}_{entry.entry_id}_custom_time"
    datetime_unique_id = f"{DOMAIN}_{entry.entry_id}_departure_time"
    hass.states.async_set("switch.test_custom_time", "on")
    hass.states.async_set("datetime.test_departure", "2026-07-28T10:00:00+00:00")

    entity_reg_patch_targets = {
        ("switch", DOMAIN, switch_unique_id): "switch.test_custom_time",
        ("datetime", DOMAIN, datetime_unique_id): "datetime.test_departure",
    }

    def fake_get_entity_id(domain, platform, unique_id):
        return entity_reg_patch_targets.get((domain, platform, unique_id))

    mock_get_trip_info = AsyncMock(return_value=SOME_JOURNEYS)
    with patch(
        "custom_components.db_info.coordinator.er.async_get"
    ) as mock_er_get, patch(
        "custom_components.db_info.coordinator.get_trip_info", new=mock_get_trip_info
    ):
        mock_er_get.return_value.async_get_entity_id.side_effect = fake_get_entity_id
        await coordinator._async_update_data()

    assert mock_get_trip_info.await_args.kwargs["custom_datetime"] == (
        "2026-07-28T10:00:00+00:00"
    )


@pytest.mark.asyncio
async def test_custom_departure_time_none_when_entities_missing(hass):
    """If the switch/datetime entities don't exist yet (e.g. right during
    initial setup), custom_datetime must simply be None, not raise."""
    await _setup_zones(hass)
    entry = _make_entry(hass)
    coordinator = DBInfoUpdateCoordinator(hass, entry)

    mock_get_trip_info = AsyncMock(return_value=SOME_JOURNEYS)
    with patch(
        "custom_components.db_info.coordinator.get_trip_info", new=mock_get_trip_info
    ):
        await coordinator._async_update_data()

    assert mock_get_trip_info.await_args.kwargs["custom_datetime"] is None
