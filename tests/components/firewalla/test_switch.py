"""Tests for the Firewalla switch platform."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.firewalla.api import FirewallaApiAuthError, FirewallaApiError
from custom_components.firewalla.const import SCOPE_GLOBAL
from custom_components.firewalla.switch import (
    FirewallaDeviceInternetBlockSwitch,
    FirewallaNetworkInternetBlockSwitch,
    async_setup_entry,
)


def _entry() -> SimpleNamespace:
    """Build a fake config entry."""
    return SimpleNamespace(entry_id="entry-1")


def _coordinator(rules: list[dict[str, object]] | None = None) -> SimpleNamespace:
    """Build a fake coordinator."""
    client = SimpleNamespace(
        base_url="https://example.firewalla.net",
        async_create_rule=AsyncMock(return_value={"id": "rule-1"}),
        async_pause_rule=AsyncMock(),
        async_resume_rule=AsyncMock(),
    )
    return SimpleNamespace(
        scope_type=SCOPE_GLOBAL,
        scope_id=None,
        client=client,
        data={
            "capabilities": {"rules": True},
            "devices": [
                {
                    "gid": "gid-1",
                    "id": "dev-1",
                    "name": "Laptop",
                }
            ],
            "networks": {
                "gid-1::net-1": {
                    "id": "net-1",
                    "name": "Main LAN",
                    "display_name": "Main LAN",
                    "gid": "gid-1",
                    "type": "lan",
                }
            },
            "rules": rules or [],
        },
        async_request_refresh=AsyncMock(),
    )


def test_switch_reports_blocked_state_and_attributes() -> None:
    """Test switch state derived from cached rules."""
    coordinator = _coordinator(
        [
            {
                "id": "rule-1",
                "action": "block",
                "status": "active",
                "gid": "gid-1",
                "notes": "Firewalla Home Assistant internet block: Laptop",
                "target": {"type": "internet"},
                "scope": {"type": "device", "value": "dev-1"},
            }
        ]
    )
    entity = FirewallaDeviceInternetBlockSwitch(
        coordinator, _entry(), "gid-1", "dev-1", "Laptop"
    )

    assert entity.available is True
    assert entity.is_on is True
    assert entity.extra_state_attributes["rule_id"] == "rule-1"
    assert entity.extra_state_attributes["rule_status"] == "active"


async def test_switch_creates_and_pauses_rules() -> None:
    """Test switch mutates the rule state through the API."""
    coordinator = _coordinator([])
    entity = FirewallaDeviceInternetBlockSwitch(
        coordinator, _entry(), "gid-1", "dev-1", "Laptop"
    )

    await entity.async_turn_on()
    coordinator.client.async_create_rule.assert_awaited_once()
    assert coordinator.client.async_create_rule.await_args.args == (
        {
            "action": "block",
            "direction": "bidirection",
            "gid": "gid-1",
            "notes": "Firewalla Home Assistant internet block: Laptop",
            "target": {"type": "internet"},
            "scope": {"type": "device", "value": "dev-1"},
        },
    )
    coordinator.async_request_refresh.assert_awaited()

    coordinator.data["rules"] = [
        {
            "id": "rule-1",
            "action": "block",
            "status": "active",
            "gid": "gid-1",
            "notes": "Firewalla Home Assistant internet block: Laptop",
            "target": {"type": "internet"},
            "scope": {"type": "device", "value": "dev-1"},
        }
    ]
    await entity.async_turn_off()
    coordinator.client.async_pause_rule.assert_awaited_once_with("rule-1")


def test_network_switch_reports_blocked_state_and_attributes() -> None:
    """Test network switch state derived from cached rules."""
    coordinator = _coordinator(
        [
            {
                "id": "rule-2",
                "action": "block",
                "status": "active",
                "gid": "gid-1",
                "notes": "Firewalla Home Assistant internet block: Main LAN",
                "target": {"type": "internet"},
                "scope": {"type": "network", "value": "net-1"},
            }
        ]
    )
    entity = FirewallaNetworkInternetBlockSwitch(
        coordinator, _entry(), "gid-1", "gid-1::net-1", "net-1", "Main LAN", "lan"
    )

    assert entity.available is True
    assert entity.is_on is True
    assert entity.extra_state_attributes["network_id"] == "net-1"
    assert entity.extra_state_attributes["rule_id"] == "rule-2"


async def test_network_switch_creates_network_scoped_rule() -> None:
    """Test network switch creates a network-scoped block rule."""
    coordinator = _coordinator([])
    entity = FirewallaNetworkInternetBlockSwitch(
        coordinator, _entry(), "gid-1", "gid-1::net-1", "net-1", "Main LAN", "lan"
    )

    await entity.async_turn_on()

    coordinator.client.async_create_rule.assert_awaited_once()
    assert coordinator.client.async_create_rule.await_args.args == (
        {
            "action": "block",
            "direction": "bidirection",
            "gid": "gid-1",
            "notes": "Firewalla Home Assistant internet block: Main LAN",
            "target": {"type": "internet"},
            "scope": {"type": "network", "value": "net-1"},
        },
    )


async def test_async_setup_entry_adds_device_and_network_switches() -> None:
    """Test switch setup adds device and network block entities."""
    coordinator = _coordinator([])
    entry = _entry()
    entry.runtime_data = coordinator
    added = []

    def _add_entities(entities):
        added.extend(entities)

    await async_setup_entry(SimpleNamespace(), entry, _add_entities)

    assert len(added) == 2
    assert any(isinstance(entity, FirewallaDeviceInternetBlockSwitch) for entity in added)
    assert any(isinstance(entity, FirewallaNetworkInternetBlockSwitch) for entity in added)


async def test_async_setup_entry_ignores_invalid_rows() -> None:
    """Test switch setup skips malformed device and network rows."""
    coordinator = _coordinator([])
    coordinator.data["devices"] = ["skip", {"id": ""}]
    coordinator.data["networks"] = {"bad": "skip", "bad2": {"id": "", "gid": "g1"}}
    entry = _entry()
    entry.runtime_data = coordinator
    added = []

    await async_setup_entry(SimpleNamespace(), entry, added.extend)

    assert added == []


def test_switch_availability_and_matching_rule_filters() -> None:
    """Test shared switch filter branches."""
    coordinator = _coordinator(
        [
            {"action": "allow", "gid": "gid-1", "scope": {"type": "device", "value": "dev-1"}, "target": {"type": "internet"}, "status": "active"},
            {"action": "block", "gid": "other", "scope": {"type": "device", "value": "dev-1"}, "target": {"type": "internet"}, "status": "active"},
            {"action": "block", "gid": "gid-1", "scope": {"type": "device", "value": "dev-1"}, "target": {"type": "domain", "value": "x"}, "status": "active"},
            {"action": "block", "gid": "gid-1", "scope": {"type": "network", "value": "dev-1"}, "target": {"type": "internet"}, "status": "active"},
            {"action": "block", "gid": "gid-1", "scope": {"type": "device", "value": "dev-1"}, "target": {"type": "internet"}, "status": "active", "notes": "foreign"},
        ]
    )
    entity = FirewallaDeviceInternetBlockSwitch(
        coordinator, _entry(), "gid-1", "dev-1", "Laptop"
    )

    assert entity.is_on is False
    coordinator.data["capabilities"] = "bad"
    assert entity.available is False
    coordinator.data["rules"] = "bad"
    assert entity.is_on is False


def test_device_and_network_switch_handle_scope_mismatches() -> None:
    """Test scope matching rejects malformed rules."""
    coordinator = _coordinator(
        [
            {"action": "block", "gid": "gid-1", "scope": "bad", "target": {"type": "internet"}, "status": "active"},
            {"action": "block", "gid": "gid-1", "scope": {"type": "device", "value": "other"}, "target": {"type": "internet"}, "status": "active"},
            {"action": "block", "gid": "gid-1", "scope": {"type": "network", "value": "other"}, "target": {"type": "internet"}, "status": "active"},
        ]
    )
    device = FirewallaDeviceInternetBlockSwitch(
        coordinator, _entry(), "gid-1", "dev-1", "Laptop"
    )
    network = FirewallaNetworkInternetBlockSwitch(
        coordinator, _entry(), "gid-1", "gid-1::net-1", "net-1", "Main LAN", "lan"
    )

    assert device.is_on is False
    assert network.is_on is False


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (FirewallaApiAuthError(), "Firewalla authentication failed"),
        (FirewallaApiError("http_400"), "Firewalla rule update failed: http_400"),
    ],
)
async def test_switch_turn_on_surfaces_api_errors(error, message) -> None:
    """Test API errors are converted to Home Assistant errors."""
    coordinator = _coordinator([])
    coordinator.client.async_create_rule = AsyncMock(side_effect=error)
    entity = FirewallaDeviceInternetBlockSwitch(
        coordinator, _entry(), "gid-1", "dev-1", "Laptop"
    )

    with pytest.raises(HomeAssistantError, match=message):
        await entity.async_turn_on()


async def test_switch_resume_and_noop_paths() -> None:
    """Test resume path and no-op turn off path."""
    coordinator = _coordinator(
        [
            {
                "id": "rule-1",
                "action": "block",
                "status": "paused",
                "gid": "gid-1",
                "notes": "Firewalla Home Assistant internet block: Laptop",
                "target": {"type": "internet"},
                "scope": {"type": "device", "value": "dev-1"},
            }
        ]
    )
    entity = FirewallaDeviceInternetBlockSwitch(
        coordinator, _entry(), "gid-1", "dev-1", "Laptop"
    )

    await entity.async_turn_on()
    coordinator.client.async_resume_rule.assert_awaited_once_with("rule-1")

    coordinator.client.async_pause_rule.reset_mock()
    await entity.async_turn_off()
    coordinator.client.async_pause_rule.assert_not_awaited()


def test_network_switch_device_info_and_attrs() -> None:
    """Test network switch metadata when no rule matches."""
    coordinator = _coordinator([])
    entity = FirewallaNetworkInternetBlockSwitch(
        coordinator, _entry(), "gid-1", "gid-1::net-1", "net-1", "Main LAN", None
    )

    assert entity.device_info["model"] == "MSP Network"
    assert entity.extra_state_attributes["rule_id"] is None
