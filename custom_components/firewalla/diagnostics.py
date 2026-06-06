"""Diagnostics support for Firewalla."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_TOKEN, DIAGNOSTICS_VERSION, INTEGRATION_VERSION

TO_REDACT = {CONF_TOKEN}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data

    return {
        "integration_version": INTEGRATION_VERSION,
        "diagnostics_version": DIAGNOSTICS_VERSION,
        "package_path": str(Path(__file__).resolve().parent),
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "last_update_success": coordinator.last_update_success,
        "scope": coordinator.data.get("scope"),
        "capabilities": coordinator.data.get("capabilities"),
        "endpoint_errors": coordinator.data.get("endpoint_errors"),
        "data_keys": sorted(coordinator.data.keys()),
        "data": async_redact_data(coordinator.data, TO_REDACT),
    }
