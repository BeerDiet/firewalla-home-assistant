"""Tests for Firewalla diagnostics."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.firewalla.diagnostics import async_get_config_entry_diagnostics


@pytest.mark.asyncio
async def test_diagnostics_redacts_token(hass) -> None:
    """Test diagnostics output."""
    entry = SimpleNamespace(
        data={"token": "secret", "base_url": "https://example.firewalla.net"},
        options={"scan_interval": 300},
        runtime_data=SimpleNamespace(
            last_update_success=True,
            data={
                "token": "secret",
                "scope": {"type": "global", "label": "Global MSP"},
                "capabilities": {"bandwidth": True},
                "endpoint_errors": {"top_stats": "http_403"},
                "api_calls": {
                    "daily_total": 12,
                    "day_start": "2026-06-28T00:00:00-04:00",
                    "next_reset": "2026-06-29T00:00:00-04:00",
                    "timezone": "America/New_York",
                },
                "network_bandwidth": {"1": {"name": "LAN"}},
            },
        ),
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry"]["token"] == "**REDACTED**"
    assert diagnostics["data"]["token"] == "**REDACTED**"
    assert diagnostics["options"] == {"scan_interval": 300}
    assert diagnostics["last_update_success"] is True
    assert diagnostics["scope"]["type"] == "global"
    assert diagnostics["capabilities"] == {"bandwidth": True}
    assert diagnostics["endpoint_errors"] == {"top_stats": "http_403"}
    assert diagnostics["api_calls"]["daily_total"] == 12
    assert diagnostics["data_keys"] == [
        "api_calls",
        "capabilities",
        "endpoint_errors",
        "network_bandwidth",
        "scope",
        "token",
    ]
