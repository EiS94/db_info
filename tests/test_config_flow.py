"""Full config- and options-flow coverage for the db_info integration."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries, data_entry_flow
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.db_info.const import (
    CONF_CONNECTION_TYPE,
    CONF_DESTINATION,
    CONF_MAX_TRANSFERS,
    CONF_START,
    CONF_TRANSPORT_TYPES,
    CONF_UPDATE_INTERVAL,
    CONNECTION_ALL,
    CONNECTION_CUSTOM,
    CONNECTION_LONG_DISTANCE,
    CONNECTION_REGIONAL,
    DOMAIN,
)
from custom_components.db_info.config_flow import MAX_TRANSFERS_UNLIMITED

SOME_JOURNEYS = {"journeys": {0: {"Name": "RE 1"}}}
NO_JOURNEYS = {"journeys": {}}


def _mock_get_trip_info(return_value):
    """Patch get_trip_info everywhere it's referenced (config_flow.py's own
    import AND the one coordinator.py uses during actual entry setup), so
    background coordinator refreshes after entry creation don't make real
    network calls during a test.
    """
    return (
        patch(
            "custom_components.db_info.config_flow.get_trip_info",
            new=AsyncMock(return_value=return_value),
        ),
        patch(
            "custom_components.db_info.coordinator.get_trip_info",
            new=AsyncMock(return_value=return_value),
        ),
    )


async def _setup_zones(hass):
    """Create two zone entities with coordinates, usable as start/destination."""
    hass.states.async_set(
        "zone.home", "0", {"latitude": 49.79, "longitude": 9.95, "friendly_name": "Home"}
    )
    hass.states.async_set(
        "zone.work", "0", {"latitude": 48.13, "longitude": 11.58, "friendly_name": "Work"}
    )


async def _start_user_flow(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


@pytest.mark.asyncio
async def test_no_entities_with_coordinates_shows_error(hass):
    """With no person/zone entities at all, the form must show an error,
    not crash, and must not offer any way to proceed."""
    result = await _start_user_flow(hass)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"]["base"] == "no_entities_with_coordinates"


@pytest.mark.asyncio
async def test_no_entities_recovers_once_zones_exist(hass):
    """After the 'no entities' error, the same flow must succeed as soon as
    usable entities exist."""
    result = await _start_user_flow(hass)
    assert result["errors"]["base"] == "no_entities_with_coordinates"

    await _setup_zones(hass)

    p1, p2 = _mock_get_trip_info(SOME_JOURNEYS)
    with p1, p2:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_START: "zone.home",
                CONF_DESTINATION: "zone.work",
                CONF_CONNECTION_TYPE: CONNECTION_ALL,
                CONF_UPDATE_INTERVAL: 10,
            },
        )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize(
    "connection_type", [CONNECTION_ALL, CONNECTION_REGIONAL, CONNECTION_LONG_DISTANCE]
)
@pytest.mark.asyncio
async def test_user_flow_success(hass, connection_type):
    """Happy path for every non-custom connection type: a reachable backend
    must result in a created entry with the right title/data/options."""
    await _setup_zones(hass)

    p1, p2 = _mock_get_trip_info(SOME_JOURNEYS)
    with p1, p2:
        result = await _start_user_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_START: "zone.home",
                CONF_DESTINATION: "zone.work",
                CONF_CONNECTION_TYPE: connection_type,
                CONF_UPDATE_INTERVAL: 15,
            },
        )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Home -> Work"
    assert result["data"][CONF_START] == "zone.home"
    assert result["data"][CONF_DESTINATION] == "zone.work"
    assert result["data"][CONF_CONNECTION_TYPE] == connection_type
    assert result["options"][CONF_UPDATE_INTERVAL] == 15


@pytest.mark.asyncio
async def test_user_flow_cannot_connect_blocks_entry_creation(hass):
    """If no source returns usable journeys, the flow must show
    'cannot_connect' and must NOT create an entry."""
    await _setup_zones(hass)

    p1, p2 = _mock_get_trip_info(NO_JOURNEYS)
    with p1, p2:
        result = await _start_user_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_START: "zone.home",
                CONF_DESTINATION: "zone.work",
                CONF_CONNECTION_TYPE: CONNECTION_ALL,
                CONF_UPDATE_INTERVAL: 10,
            },
        )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"

    # Once the backend is reachable again, the same flow must recover.
    p1, p2 = _mock_get_trip_info(SOME_JOURNEYS)
    with p1, p2:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_START: "zone.home",
                CONF_DESTINATION: "zone.work",
                CONF_CONNECTION_TYPE: CONNECTION_ALL,
                CONF_UPDATE_INTERVAL: 10,
            },
        )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Home -> Work"


@pytest.mark.asyncio
async def test_duplicate_start_destination_is_aborted(hass):
    """The exact same start/destination pair cannot be configured twice."""
    await _setup_zones(hass)

    p1, p2 = _mock_get_trip_info(SOME_JOURNEYS)
    with p1, p2:
        result = await _start_user_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_START: "zone.home",
                CONF_DESTINATION: "zone.work",
                CONF_CONNECTION_TYPE: CONNECTION_ALL,
                CONF_UPDATE_INTERVAL: 10,
            },
        )
        assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

        result2 = await _start_user_flow(hass)
        result2 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {
                CONF_START: "zone.home",
                CONF_DESTINATION: "zone.work",
                CONF_CONNECTION_TYPE: CONNECTION_ALL,
                CONF_UPDATE_INTERVAL: 10,
            },
        )

    assert result2["type"] == data_entry_flow.FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


@pytest.mark.asyncio
async def test_custom_types_flow_success(hass):
    """Selecting CONNECTION_CUSTOM must lead to the custom_types step, and a
    reachable backend there must create an entry with the chosen types."""
    await _setup_zones(hass)

    p1, p2 = _mock_get_trip_info(SOME_JOURNEYS)
    with p1, p2:
        result = await _start_user_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_START: "zone.home",
                CONF_DESTINATION: "zone.work",
                CONF_CONNECTION_TYPE: CONNECTION_CUSTOM,
                CONF_UPDATE_INTERVAL: 10,
            },
        )
        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["step_id"] == "custom_types"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_TRANSPORT_TYPES: ["ICE", "IC/EC"]},
        )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CONNECTION_TYPE] == CONNECTION_CUSTOM
    assert result["data"][CONF_TRANSPORT_TYPES] == ["ICE", "IC/EC"]


@pytest.mark.asyncio
async def test_custom_types_flow_cannot_connect(hass):
    """A failed connectivity test in the custom_types step must show an
    error and must NOT create an entry either."""
    await _setup_zones(hass)

    with patch(
        "custom_components.db_info.config_flow.get_trip_info",
        new=AsyncMock(return_value=SOME_JOURNEYS),
    ):
        result = await _start_user_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_START: "zone.home",
                CONF_DESTINATION: "zone.work",
                CONF_CONNECTION_TYPE: CONNECTION_CUSTOM,
                CONF_UPDATE_INTERVAL: 10,
            },
        )
        assert result["step_id"] == "custom_types"

    # Now make the connectivity test fail for the custom_types submission itself
    with patch(
        "custom_components.db_info.config_flow.get_trip_info",
        new=AsyncMock(return_value=NO_JOURNEYS),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_TRANSPORT_TYPES: ["ICE"]},
        )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"

    # The custom_types step must recover once the backend is reachable again.
    p1, p2 = _mock_get_trip_info(SOME_JOURNEYS)
    with p1, p2:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_TRANSPORT_TYPES: ["ICE"]},
        )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CONNECTION_TYPE] == CONNECTION_CUSTOM
    assert result["data"][CONF_TRANSPORT_TYPES] == ["ICE"]


@pytest.mark.asyncio
async def test_options_flow_update_interval_and_connection_type(hass):
    """The options flow must let you change interval/connection type
    without going through the custom_types step for non-custom types."""
    await _setup_zones(hass)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Home -> Work",
        data={
            CONF_START: "zone.home",
            CONF_DESTINATION: "zone.work",
            CONF_CONNECTION_TYPE: CONNECTION_ALL,
        },
        options={CONF_UPDATE_INTERVAL: 10},
        unique_id="zone.home::zone.work",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_CONNECTION_TYPE: CONNECTION_REGIONAL,
            CONF_UPDATE_INTERVAL: 20,
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CONNECTION_TYPE] == CONNECTION_REGIONAL
    assert result["data"][CONF_UPDATE_INTERVAL] == 20


@pytest.mark.asyncio
async def test_options_flow_custom_types(hass):
    """Choosing CONNECTION_CUSTOM in the options flow must lead to its own
    custom_types step and merge the chosen types into the final options."""
    await _setup_zones(hass)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Home -> Work",
        data={
            CONF_START: "zone.home",
            CONF_DESTINATION: "zone.work",
            CONF_CONNECTION_TYPE: CONNECTION_ALL,
        },
        options={CONF_UPDATE_INTERVAL: 10},
        unique_id="zone.home::zone.work",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_CONNECTION_TYPE: CONNECTION_CUSTOM,
            CONF_UPDATE_INTERVAL: 10,
        },
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "custom_types"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_TRANSPORT_TYPES: ["BUS", "TRAM"]},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CONNECTION_TYPE] == CONNECTION_CUSTOM
    assert result["data"][CONF_TRANSPORT_TYPES] == ["BUS", "TRAM"]


@pytest.mark.asyncio
async def test_user_flow_stores_max_transfers(hass):
    """A chosen max-transfers option must be stored as an int in the options."""
    await _setup_zones(hass)

    p1, p2 = _mock_get_trip_info(SOME_JOURNEYS)
    with p1, p2:
        result = await _start_user_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_START: "zone.home",
                CONF_DESTINATION: "zone.work",
                CONF_CONNECTION_TYPE: CONNECTION_ALL,
                CONF_UPDATE_INTERVAL: 10,
                CONF_MAX_TRANSFERS: "2",
            },
        )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_MAX_TRANSFERS] == 2


@pytest.mark.asyncio
async def test_custom_types_flow_stores_max_transfers(hass):
    """The max-transfers choice from the first step must survive the
    custom_types step."""
    await _setup_zones(hass)

    p1, p2 = _mock_get_trip_info(SOME_JOURNEYS)
    with p1, p2:
        result = await _start_user_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_START: "zone.home",
                CONF_DESTINATION: "zone.work",
                CONF_CONNECTION_TYPE: CONNECTION_CUSTOM,
                CONF_UPDATE_INTERVAL: 10,
                CONF_MAX_TRANSFERS: "0",
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_TRANSPORT_TYPES: ["BUS"]},
        )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_MAX_TRANSFERS] == 0


@pytest.mark.asyncio
async def test_start_entity_removed_before_submit(hass):
    """If the start entity disappears between showing and submitting the
    form, the flow must show 'cannot_connect' instead of crashing."""
    await _setup_zones(hass)

    result = await _start_user_flow(hass)
    hass.states.async_remove("zone.home")

    p1, p2 = _mock_get_trip_info(SOME_JOURNEYS)
    with p1, p2:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_START: "zone.home",
                CONF_DESTINATION: "zone.work",
                CONF_CONNECTION_TYPE: CONNECTION_ALL,
                CONF_UPDATE_INTERVAL: 10,
            },
        )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


@pytest.mark.parametrize(
    ("start", "destination"),
    [("zone.nowhere", "zone.work"), ("zone.home", "zone.nowhere")],
)
@pytest.mark.asyncio
async def test_entity_without_coordinates_cannot_connect(hass, start, destination):
    """A start or destination without latitude/longitude must show
    'cannot_connect' without querying any backend."""
    await _setup_zones(hass)
    hass.states.async_set("zone.nowhere", "0", {"friendly_name": "Nowhere"})

    p1, p2 = _mock_get_trip_info(SOME_JOURNEYS)
    with p1 as mock_get_trip_info, p2:
        result = await _start_user_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_START: start,
                CONF_DESTINATION: destination,
                CONF_CONNECTION_TYPE: CONNECTION_ALL,
                CONF_UPDATE_INTERVAL: 10,
            },
        )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"
    mock_get_trip_info.assert_not_called()


@pytest.mark.asyncio
async def test_backend_exception_shows_cannot_connect(hass):
    """An unexpected exception from the backend must be turned into
    'cannot_connect' instead of aborting the flow."""
    await _setup_zones(hass)

    with patch(
        "custom_components.db_info.config_flow.get_trip_info",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        result = await _start_user_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_START: "zone.home",
                CONF_DESTINATION: "zone.work",
                CONF_CONNECTION_TYPE: CONNECTION_ALL,
                CONF_UPDATE_INTERVAL: 10,
            },
        )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


@pytest.mark.parametrize(
    ("current", "submitted", "expected"),
    [(None, "3", 3), (3, MAX_TRANSFERS_UNLIMITED, None)],
)
@pytest.mark.asyncio
async def test_options_flow_max_transfers(hass, current, submitted, expected):
    """The options flow must convert the max-transfers option in both
    directions: a number to an int, and 'unlimited' back to None."""
    await _setup_zones(hass)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Home -> Work",
        data={
            CONF_START: "zone.home",
            CONF_DESTINATION: "zone.work",
            CONF_CONNECTION_TYPE: CONNECTION_ALL,
        },
        options={CONF_UPDATE_INTERVAL: 10, CONF_MAX_TRANSFERS: current},
        unique_id="zone.home::zone.work",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_CONNECTION_TYPE: CONNECTION_ALL,
            CONF_UPDATE_INTERVAL: 10,
            CONF_MAX_TRANSFERS: submitted,
        },
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MAX_TRANSFERS] == expected
