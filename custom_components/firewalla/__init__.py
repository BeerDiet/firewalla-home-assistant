"""The Firewalla integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .api import FirewallaApiCallTracker, FirewallaApiClient
from .const import (
    CONF_BASE_URL,
    CONF_GROUP,
    CONF_SCAN_INTERVAL,
    CONF_SCOPE_ID,
    CONF_SCOPE_TYPE,
    CONF_VERIFY_SSL,
    INTEGRATION_VERSION,
    PLATFORMS,
    SCOPE_GLOBAL,
    SCOPE_GROUP,
)
from .coordinator import FirewallaTrendsCoordinator

_LOGGER = logging.getLogger(__name__)

type FirewallaConfigEntry = ConfigEntry[FirewallaTrendsCoordinator]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Firewalla integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FirewallaConfigEntry) -> bool:
    """Set up Firewalla from a config entry."""
    _LOGGER.info(
        "Setting up Firewalla integration version %s from %s",
        INTEGRATION_VERSION,
        Path(__file__).resolve().parent,
    )
    session = async_get_clientsession(hass)
    request_tracker = FirewallaApiCallTracker(dt_util.now)
    client = FirewallaApiClient(
        session,
        entry.data[CONF_BASE_URL],
        entry.data[CONF_TOKEN],
        verify_ssl=entry.data[CONF_VERIFY_SSL],
        request_tracker=request_tracker,
    )
    coordinator = FirewallaTrendsCoordinator(hass, entry, client)

    configured_scan = entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL),
    )
    if configured_scan is None or int(configured_scan) != coordinator.effective_scan_seconds:
        hass.config_entries.async_update_entry(
            entry,
            options={
                **entry.options,
                CONF_SCAN_INTERVAL: coordinator.effective_scan_seconds,
            },
        )

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FirewallaConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries."""
    if CONF_SCOPE_TYPE not in entry.data:
        legacy_group = str(entry.data.get(CONF_GROUP) or "").strip()
        migrated_data = dict(entry.data)
        if legacy_group:
            migrated_data[CONF_SCOPE_TYPE] = SCOPE_GROUP
            migrated_data[CONF_SCOPE_ID] = legacy_group
        else:
            migrated_data[CONF_SCOPE_TYPE] = SCOPE_GLOBAL
            migrated_data.pop(CONF_SCOPE_ID, None)
        migrated_data.pop(CONF_GROUP, None)
        hass.config_entries.async_update_entry(entry, data=migrated_data)
    return True
