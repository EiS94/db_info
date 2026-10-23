"""Tests that HTTP sessions are reused across polls and closed on unload."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_CLOSE
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.db_info import bahn_api
from custom_components.db_info.const import (
    CONF_CONNECTION_TYPE,
    CONF_DESTINATION,
    CONF_START,
    CONNECTION_ALL,
    DOMAIN,
)
from custom_components.db_info.coordinator import DBInfoUpdateCoordinator
from custom_components.db_info.sessions import (
    DATA_DBNAV_SESSION,
    async_get_dbnav_session,
)

SOME_JOURNEYS = {"journeys": {0: {"Name": "RE 1"}}}


def _make_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Home -> Work",
        data={
            CONF_START: "zone.home",
            CONF_DESTINATION: "zone.work",
            CONF_CONNECTION_TYPE: CONNECTION_ALL,
        },
        options={},
    )
    entry.add_to_hass(hass)
    return entry


async def _setup_zones(hass):
    hass.states.async_set("zone.home", "0", {"latitude": 49.79, "longitude": 9.95})
    hass.states.async_set("zone.work", "0", {"latitude": 48.13, "longitude": 11.58})


@pytest.fixture
def mock_async_session():
    """Replace curl_cffi's AsyncSession with a mock that records instances."""
    with patch("custom_components.db_info.sessions.AsyncSession") as session_cls:
        session_cls.side_effect = lambda **kwargs: MagicMock(
            post=AsyncMock(return_value=MagicMock(status_code=503, text="")),
            close=AsyncMock(),
        )
        yield session_cls


async def test_polls_reuse_the_same_sessions(hass, mock_async_session):
    """Several polls (also of different entries) must share one curl_cffi
    session for DB Navigator and HA's aiohttp session for EFA/MOTIS."""
    await _setup_zones(hass)
    fallback_sessions = []

    async def fake_efa(session, api, params):
        fallback_sessions.append(session)

    async def fake_motis(session, params, cache_key, motis_state):
        fallback_sessions.append(session)

    coordinators = [
        DBInfoUpdateCoordinator(hass, _make_entry(hass)) for _ in range(2)
    ]
    with patch.object(bahn_api, "_fetch_from_api", fake_efa), \
            patch.object(bahn_api, "_fetch_from_motis", fake_motis):
        for coordinator in coordinators * 2:
            await coordinator._async_update_data()

    mock_async_session.assert_called_once_with(discard_cookies=True)
    dbnav_session = hass.data[DATA_DBNAV_SESSION]["session"]
    assert dbnav_session.post.await_count == 4

    # DB Navigator answered 503, so every poll fell back to EFA + MOTIS
    # (MOTIS is always queried, EFA only for the APIs covering the trip).
    assert len(fallback_sessions) > 4
    assert all(s is async_get_clientsession(hass) for s in fallback_sessions)


async def test_unloading_last_entry_closes_dbnav_session(hass, mock_async_session):
    """The shared session must survive unloading one entry and be closed
    once the last entry is unloaded."""
    await _setup_zones(hass)
    first, second = _make_entry(hass), _make_entry(hass)

    with patch(
        "custom_components.db_info.coordinator.get_trip_info",
        new=AsyncMock(return_value=SOME_JOURNEYS),
    ):
        assert await hass.config_entries.async_setup(first.entry_id)
        await hass.async_block_till_done()
        assert second.state is ConfigEntryState.LOADED

        session = hass.data[DATA_DBNAV_SESSION]["session"]
        mock_async_session.assert_called_once()

        assert await hass.config_entries.async_unload(first.entry_id)
        session.close.assert_not_awaited()
        assert hass.data[DATA_DBNAV_SESSION]["session"] is session

        assert await hass.config_entries.async_unload(second.entry_id)
        session.close.assert_awaited_once()
        assert DATA_DBNAV_SESSION not in hass.data


async def test_dbnav_session_is_closed_when_home_assistant_stops(
    hass, mock_async_session
):
    session = async_get_dbnav_session(hass)
    assert async_get_dbnav_session(hass) is session

    hass.bus.async_fire(EVENT_HOMEASSISTANT_CLOSE)
    await hass.async_block_till_done()

    session.close.assert_awaited_once()
    assert DATA_DBNAV_SESSION not in hass.data
