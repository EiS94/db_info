"""Unit tests for DBInfoUpdateCoordinator, now that it's its own module."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache,
)

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
    """If the custom-time switch is on, the coordinator's custom time and
    arrival flag must be passed through to get_trip_info."""
    await _setup_zones(hass)
    entry = _make_entry(hass)
    coordinator = DBInfoUpdateCoordinator(hass, entry)
    custom_time = datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc)

    coordinator.set_time_setting("custom_time", custom_time)
    coordinator.set_time_setting("use_arrival_time", True)
    coordinator.set_time_setting("use_custom_time", True)

    mock_get_trip_info = AsyncMock(return_value=SOME_JOURNEYS)
    with patch(
        "custom_components.db_info.coordinator.get_trip_info", new=mock_get_trip_info
    ):
        await coordinator._async_update_data()

    assert mock_get_trip_info.await_args.kwargs["custom_datetime"] == custom_time
    assert mock_get_trip_info.await_args.kwargs["is_arrival"] is True


@pytest.mark.asyncio
async def test_custom_departure_time_none_when_switch_off(hass):
    """With the custom-time switch off, neither the stored time nor the
    arrival switch may influence the query."""
    await _setup_zones(hass)
    entry = _make_entry(hass)
    coordinator = DBInfoUpdateCoordinator(hass, entry)
    coordinator.set_time_setting(
        "custom_time", datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc)
    )
    coordinator.set_time_setting("use_arrival_time", True)

    mock_get_trip_info = AsyncMock(return_value=SOME_JOURNEYS)
    with patch(
        "custom_components.db_info.coordinator.get_trip_info", new=mock_get_trip_info
    ):
        await coordinator._async_update_data()

    assert mock_get_trip_info.await_args.kwargs["custom_datetime"] is None
    assert mock_get_trip_info.await_args.kwargs["is_arrival"] is False


@pytest.mark.asyncio
async def test_set_time_setting_only_requests_refresh_when_relevant(hass):
    """Time and arrival flag only matter while the custom-time switch is on."""
    entry = _make_entry(hass)
    coordinator = DBInfoUpdateCoordinator(hass, entry)
    custom_time = datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc)

    assert coordinator.set_time_setting("custom_time", custom_time) is False
    assert coordinator.set_time_setting("use_arrival_time", True) is False
    assert coordinator.set_time_setting("use_custom_time", True) is True
    assert coordinator.set_time_setting("use_custom_time", True) is False
    assert coordinator.set_time_setting("use_arrival_time", False) is True
    assert coordinator.set_time_setting("use_custom_time", False) is True


@pytest.mark.asyncio
async def test_time_settings_are_per_entry(hass):
    """Two entries must never see each other's time settings."""
    entry_a = _make_entry(hass)
    entry_b = MockConfigEntry(
        domain=DOMAIN,
        title="Work -> Home",
        data={
            CONF_START: "zone.work",
            CONF_DESTINATION: "zone.home",
            CONF_CONNECTION_TYPE: CONNECTION_ALL,
        },
    )
    entry_b.add_to_hass(hass)
    coordinator_a = DBInfoUpdateCoordinator(hass, entry_a)
    coordinator_b = DBInfoUpdateCoordinator(hass, entry_b)

    coordinator_a.set_time_setting("use_custom_time", True)

    assert coordinator_a.use_custom_time is True
    assert coordinator_b.use_custom_time is False


@pytest.mark.asyncio
async def test_time_settings_seeded_from_restored_states(hass):
    """The first refresh runs before the switch/datetime entities are
    added, so the coordinator must already pick up their restored states."""
    entry = _make_entry(hass)
    entity_reg = er.async_get(hass)
    for platform, suffix, object_id in (
        ("switch", "_custom_time", "custom"),
        ("switch", "_use_arrival_time", "arrival"),
        ("datetime", "_departure_time", "time"),
    ):
        entity_reg.async_get_or_create(
            platform, DOMAIN, f"{DOMAIN}_{entry.entry_id}{suffix}",
            suggested_object_id=object_id,
        )
    mock_restore_cache(
        hass,
        [
            State("switch.custom", "on"),
            State("switch.arrival", "on"),
            State("datetime.time", "2026-07-28T10:00:00+00:00"),
        ],
    )

    coordinator = DBInfoUpdateCoordinator(hass, entry)

    assert coordinator._get_custom_time() == (
        datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc),
        True,
    )
