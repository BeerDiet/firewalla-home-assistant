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
        "polling": {
            "configured_seconds": entry.options.get(
                "scan_interval", entry.data.get("scan_interval")
            ),
            "minimum_seconds": getattr(coordinator, "minimum_scan_seconds", None),
            "effective_seconds": getattr(coordinator, "effective_scan_seconds", None),
            "api_daily_request_limit": getattr(
                coordinator, "api_daily_request_limit", None
            ),
        },
        "scope": coordinator.data.get("scope"),
        "capabilities": coordinator.data.get("capabilities"),
        "endpoint_errors": coordinator.data.get("endpoint_errors"),
        "api_calls": coordinator.data.get("api_calls"),
        "data_keys": sorted(coordinator.data.keys()),
        "data": async_redact_data(coordinator.data, TO_REDACT),
    }
