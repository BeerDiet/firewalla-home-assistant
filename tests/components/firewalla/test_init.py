"""Tests for Firewalla setup and unload."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.util import dt as dt_util

from custom_components.firewalla import async_migrate_entry, async_setup
from custom_components.firewalla.const import (
    CONF_API_CALL_STATS,
    CONF_BASE_URL,
    CONF_SCOPE_ID,
    CONF_SCOPE_TYPE,
    DOMAIN,
    SCOPE_GLOBAL,
    SCOPE_GROUP,
)
from tests.common import MockConfigEntry


async def test_setup_and_unload_entry(hass) -> None:
    """Test config entry setup and unload."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla",
        data={
            "base_url": "https://example.firewalla.net",
            "token": "abc123",
            "verify_ssl": True,
            CONF_SCOPE_TYPE: SCOPE_GLOBAL,
            "scan_interval": 300,
            "name": "Firewalla",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla.FirewallaTrendsCoordinator.async_config_entry_first_refresh",
            new=AsyncMock(),
        ),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            new=AsyncMock(),
        ),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
            new=AsyncMock(return_value=True),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        assert entry.state is ConfigEntryState.LOADED
        assert entry.runtime_data is not None
        assert int(entry.runtime_data.update_interval.total_seconds()) == 360

        assert await hass.config_entries.async_unload(entry.entry_id)
        assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_entry_restores_persisted_api_usage(hass) -> None:
    """Test setup restores the API tally stored on the entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla",
        data={
            CONF_BASE_URL: "https://example.firewalla.net",
            "token": "abc123",
            "verify_ssl": True,
            CONF_SCOPE_TYPE: SCOPE_GLOBAL,
            "scan_interval": 300,
            "name": "Firewalla",
            CONF_API_CALL_STATS: {
                "daily_total": 1331,
                "day_start": "2026-06-28T00:00:00-04:00",
                "last_attempt_at": "2026-06-28T11:24:00-04:00",
            },
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla.dt_util.now",
            return_value=dt_util.parse_datetime("2026-06-28T12:00:00-04:00"),
        ),
        patch(
            "custom_components.firewalla.FirewallaTrendsCoordinator.async_config_entry_first_refresh",
            new=AsyncMock(),
        ),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            new=AsyncMock(),
        ),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
            new=AsyncMock(return_value=True),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        assert entry.runtime_data is not None
        assert (
            entry.runtime_data.client.api_call_stats()["daily_total"] == 1331
        )
        assert int(entry.runtime_data.update_interval.total_seconds()) == 648


async def test_async_setup_returns_true(hass) -> None:
    """Test top-level async setup."""
    assert await async_setup(hass, {}) is True


async def test_async_migrate_entry_returns_true(hass) -> None:
    """Test config entry migration updates legacy scope fields."""
    entry = MagicMock()
    entry.data = {"group": "branch-office"}

    with patch.object(hass.config_entries, "async_update_entry") as mock_update:
        assert await async_migrate_entry(hass, entry) is True

    mock_update.assert_called_once()
    migrated = mock_update.call_args.kwargs["data"]
    assert migrated[CONF_SCOPE_TYPE] == SCOPE_GROUP
    assert migrated[CONF_SCOPE_ID] == "branch-office"


async def test_async_migrate_entry_sets_global_scope_when_legacy_group_empty(hass) -> None:
    """Test empty legacy scope migrates to global."""
    entry = MagicMock()
    entry.data = {"group": ""}

    with patch.object(hass.config_entries, "async_update_entry") as mock_update:
        assert await async_migrate_entry(hass, entry) is True

    migrated = mock_update.call_args.kwargs["data"]
    assert migrated[CONF_SCOPE_TYPE] == SCOPE_GLOBAL
    assert CONF_SCOPE_ID not in migrated


async def test_unload_entry_failure_reports_false(hass) -> None:
    """Test unload failure is reported."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla",
        data={
            "base_url": "https://example.firewalla.net",
            "token": "abc123",
            "verify_ssl": True,
            CONF_SCOPE_TYPE: SCOPE_GLOBAL,
            "scan_interval": 300,
            "name": "Firewalla",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla.FirewallaTrendsCoordinator.async_config_entry_first_refresh",
            new=AsyncMock(),
        ),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            new=AsyncMock(),
        ),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
            new=AsyncMock(return_value=False),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        assert await hass.config_entries.async_unload(entry.entry_id) is False


async def test_setup_entry_propagates_initial_refresh_failure(hass) -> None:
    """Test setup fails hard when the initial refresh fails."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla",
        data={
            "base_url": "https://example.firewalla.net",
            "token": "abc123",
            "verify_ssl": True,
            CONF_SCOPE_TYPE: SCOPE_GLOBAL,
            "scan_interval": 300,
            "name": "Firewalla",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.firewalla.FirewallaTrendsCoordinator.async_config_entry_first_refresh",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            new=AsyncMock(),
        ) as mock_forward,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id) is False
        mock_forward.assert_not_awaited()
