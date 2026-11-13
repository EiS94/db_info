"""Tests for the refresh button."""
from unittest.mock import MagicMock

from custom_components.db_info.button import DBRefreshButton


def test_refresh_button_stays_available_after_failed_update():
    coordinator = MagicMock()
    coordinator.last_update_success = False
    entry = MagicMock(entry_id="abc", title="A -> B")
    assert DBRefreshButton(coordinator, entry).available is True
