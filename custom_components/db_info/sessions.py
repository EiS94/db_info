"""Long-lived HTTP sessions shared by all db_info config entries.

Creating a new session per poll meant a fresh DNS lookup and TLS handshake
for every single update of every entry. The EFA/transitous.org requests
use Home Assistant's shared aiohttp session; the DB Navigator requests
need curl_cffi (TLS impersonation), so one AsyncSession is kept in
hass.data and closed when the last entry is unloaded or HA stops.
"""

from __future__ import annotations

from curl_cffi.requests import AsyncSession

from homeassistant.const import EVENT_HOMEASSISTANT_CLOSE
from homeassistant.core import Event, HomeAssistant, callback

from .const import DOMAIN

DATA_DBNAV_SESSION = f"{DOMAIN}_dbnav_session"


@callback
def async_get_dbnav_session(hass: HomeAssistant) -> AsyncSession:
    """Return the shared curl_cffi session, creating it on first use."""
    data = hass.data.get(DATA_DBNAV_SESSION)
    if data is not None:
        return data["session"]

    async def _close_on_stop(event: Event) -> None:
        # The listener has already fired (and removed itself).
        hass.data[DATA_DBNAV_SESSION]["remove_listener"] = None
        await async_close_dbnav_session(hass)

    # discard_cookies: keep every request as stateless as with the former
    # one-session-per-request approach; only the connection is reused.
    session = AsyncSession(discard_cookies=True)
    hass.data[DATA_DBNAV_SESSION] = {
        "session": session,
        "remove_listener": hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_CLOSE, _close_on_stop
        ),
    }
    return session


async def async_close_dbnav_session(hass: HomeAssistant) -> None:
    """Close the shared curl_cffi session, if one is open."""
    data = hass.data.pop(DATA_DBNAV_SESSION, None)
    if data is None:
        return
    if data["remove_listener"] is not None:
        data["remove_listener"]()
    await data["session"].close()
