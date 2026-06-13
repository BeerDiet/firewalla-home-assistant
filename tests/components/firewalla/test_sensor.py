"""Tests for Firewalla sensors."""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.firewalla.api import TrendPoint
from custom_components.firewalla.const import SCOPE_GROUP
from custom_components.firewalla.sensor import (
    _GLOBAL_SENSOR_KEYS,
    _PER_BOX_SENSOR_KEYS,
    SENSOR_DESCRIPTIONS,
    FirewallaPerBoxNetworkBandwidthSensor,
    FirewallaPerBoxSensor,
    FirewallaPerDeviceTrafficSensor,
    FirewallaTrendSensor,
    _bytes_to_gigabytes,
    _slugify,
    async_setup_entry,
)


def _entry() -> SimpleNamespace:
    """Build a fake config entry."""
    return SimpleNamespace(entry_id="entry-1", runtime_data=None)


def _coordinator(scope_id: str | None = None) -> SimpleNamespace:
    """Build a fake coordinator."""
    return SimpleNamespace(
        scope_type=SCOPE_GROUP if scope_id else "global",
        scope_id=scope_id,
        group=scope_id,
        client=SimpleNamespace(base_url="https://example.firewalla.net"),
        data={
            "scope": {
                "type": SCOPE_GROUP if scope_id else "global",
                "id": scope_id,
                "label": scope_id or "Global MSP",
            },
            "boxes": [
                {
                    "gid": "g1",
                    "name": "Branch Box",
                    "model": "FW",
                    "online": True,
                }
            ],
            "devices": [
                {
                    "gid": "g1",
                    "id": "dev-1",
                    "name": "Laptop",
                    "network": {"id": "net1", "name": "Main LAN", "type": "lan"},
                }
            ],
            "capabilities": {
                "trends": True,
                "simple_stats": True,
                "top_stats": True,
                "bandwidth": True,
                "box_bandwidth": True,
                "network_bandwidth": True,
                "top_talkers": True,
            },
            "device_traffic": [
                {
                    "device_id": "dev-1",
                    "device_name": "Laptop",
                    "gid": "g1",
                    "box_name": "Branch Box",
                    "box_model": "FW",
                    "network_id": "net1",
                    "network_name": "Main LAN",
                    "download_bytes": 1_000,
                    "upload_bytes": 500,
                    "total_bytes": 1_500,
                    "download_mbps": 0.009,
                    "upload_mbps": 0.004,
                    "flow_count": 2,
                    "window_minutes": 15,
                    "window_seconds": 900,
                }
            ],
            "simple_stats": {
                "onlineBoxes": 2,
                "offlineBoxes": 1,
                "alarms": 3,
                "rules": 4,
            },
            "top_stats": {
                "topBoxesByBlockedFlows": [
                    {"meta": {"name": "LAN", "model": "FW", "gid": "g1"}, "value": 8}
                ]
            },
            "bandwidth": {
                "download_mbps": 4.2,
                "upload_mbps": 1.5,
                "download_bytes": 10,
                "upload_bytes": 11,
                "flow_count": 2,
                "window_minutes": 15,
                "window_seconds": 900,
            },
            "box_bandwidth": {
                "g1": {
                    "gid": "g1",
                    "name": "Branch Box",
                    "model": "FW",
                    "online": True,
                    "download_mbps": 3.1,
                    "upload_mbps": 1.1,
                    "download_bytes": 200,
                    "upload_bytes": 100,
                    "flow_count": 4,
                    "window_minutes": 15,
                    "window_seconds": 900,
                }
            },
            "trends": {
                "flows": [
                    TrendPoint(ts=1_700_000_100, value=10),
                    TrendPoint(ts=1_700_000_000, value=9),
                ],
                "alarms": [TrendPoint(ts=1_700_000_200, value=5)],
                "rules": [TrendPoint(ts=1_700_000_300, value=7)],
            },
            "network_bandwidth": {
                "g1::net1": {
                    "id": "net1",
                    "name": "Main LAN",
                    "display_name": "Main LAN",
                    "gid": "g1",
                    "box_name": "Branch Box",
                    "type": "lan",
                    "download_mbps": 2.5,
                    "upload_mbps": 0.8,
                    "download_bytes": 100,
                    "upload_bytes": 50,
                    "flow_count": 4,
                    "window_minutes": 15,
                    "window_seconds": 900,
                }
            },
            "networks": {
                "g1::net1": {
                    "id": "net1",
                    "name": "Main LAN",
                    "display_name": "Main LAN",
                    "gid": "g1",
                    "box_name": "Branch Box",
                    "box_model": "FW",
                    "type": "lan",
                }
            },
            "top_talkers": [
                {
                    "device_id": "dev-1",
                    "device_name": "Laptop",
                    "gid": "g1",
                    "box_name": "Branch Box",
                    "box_model": "FW",
                    "network_id": "net1",
                    "network_name": "Main LAN",
                    "download_bytes": 1_000,
                    "upload_bytes": 500,
                    "total_bytes": 1_500,
                    "download_mbps": 0.009,
                    "upload_mbps": 0.004,
                    "flow_count": 2,
                    "window_minutes": 15,
                    "window_seconds": 900,
                }
            ],
        },
    )


def test_slugify() -> None:
    """Test slugify helper."""
    assert _slugify("Main LAN") == "main_lan"
    assert _slugify("  ") == "group"
    assert _bytes_to_gigabytes(1_246_400_717) == 1.25


def test_trend_sensor_native_value_and_attrs_for_trends() -> None:
    """Test trend sensor values and attributes."""
    entry = _entry()
    coordinator = _coordinator("branch")
    description = next(item for item in SENSOR_DESCRIPTIONS if item.key == "flows")
    sensor = FirewallaTrendSensor(coordinator, entry, description)

    assert sensor.available is True
    assert sensor.native_value == 10
    assert sensor._attr_suggested_object_id == "firewalla_flows_group_branch"
    assert sensor.extra_state_attributes["previous_value"] == 9
    assert sensor.extra_state_attributes["scope_id"] == "branch"


def test_trend_sensor_native_value_and_attrs_for_simple_stats() -> None:
    """Test simple stats sensor values."""
    entry = _entry()
    coordinator = _coordinator()
    description = next(
        item for item in SENSOR_DESCRIPTIONS if item.key == "online_boxes"
    )
    sensor = FirewallaTrendSensor(coordinator, entry, description)

    assert sensor.native_value == 2
    assert sensor.extra_state_attributes["source"] == "simple_stats"
    assert sensor.extra_state_attributes["scope_type"] == "global"


def test_trend_sensor_handles_missing_simple_stats_value() -> None:
    """Test simple stats sensor returns None when source data is not an int."""
    entry = _entry()
    coordinator = _coordinator()
    coordinator.data["simple_stats"]["onlineBoxes"] = "bad"
    description = next(
        item for item in SENSOR_DESCRIPTIONS if item.key == "online_boxes"
    )
    sensor = FirewallaTrendSensor(coordinator, entry, description)

    assert sensor.native_value is None


def test_trend_sensor_native_value_and_attrs_for_top_stats() -> None:
    """Test top stats sensor values."""
    entry = _entry()
    coordinator = _coordinator()
    description = next(
        item for item in SENSOR_DESCRIPTIONS if item.key == "top_box_blocked_flows"
    )
    sensor = FirewallaTrendSensor(coordinator, entry, description)

    assert sensor.native_value == 8
    assert sensor.extra_state_attributes["leader_name"] == "LAN"
    assert sensor.extra_state_attributes["results"][0]["value"] == 8


def test_trend_sensor_handles_empty_top_stats() -> None:
    """Test top stats sensor defaults when the result set is empty."""
    entry = _entry()
    coordinator = _coordinator()
    coordinator.data["top_stats"]["topBoxesByBlockedFlows"] = []
    description = next(
        item for item in SENSOR_DESCRIPTIONS if item.key == "top_box_blocked_flows"
    )
    sensor = FirewallaTrendSensor(coordinator, entry, description)

    assert sensor.native_value == 0
    assert sensor.extra_state_attributes["results"] == []


def test_trend_sensor_native_value_and_attrs_for_bandwidth() -> None:
    """Test bandwidth sensor values."""
    entry = _entry()
    coordinator = _coordinator()
    description = next(
        item for item in SENSOR_DESCRIPTIONS if item.key == "download_mbps"
    )
    sensor = FirewallaTrendSensor(coordinator, entry, description)

    assert sensor.native_value == 4.2
    assert sensor.extra_state_attributes["source"] == "grouped_flows"


def test_trend_sensor_native_value_and_attrs_for_top_talkers() -> None:
    """Test top talker sensor values."""
    entry = _entry()
    coordinator = _coordinator()
    description = next(item for item in SENSOR_DESCRIPTIONS if item.key == "top_talkers")
    sensor = FirewallaTrendSensor(coordinator, entry, description)

    assert sensor.available is True
    assert sensor.native_value == 0.0
    assert sensor.extra_state_attributes["source"] == "top_talkers"
    assert sensor.extra_state_attributes["leader_device_name"] == "Laptop"
    assert sensor.extra_state_attributes["results"][0]["device_id"] == "dev-1"


def test_per_device_traffic_sensor_value_and_attrs() -> None:
    """Test per-device traffic sensors expose ranked traffic data."""
    entry = _entry()
    coordinator = _coordinator()
    sensor = FirewallaPerDeviceTrafficSensor(
        coordinator, entry, "g1", "dev-1", "Laptop"
    )

    assert sensor.available is True
    assert sensor.native_value == 0.0
    assert sensor.device_info["name"] == "Firewalla Laptop"
    assert sensor.extra_state_attributes["rank"] == 1
    assert sensor.extra_state_attributes["network_name"] == "Main LAN"
    assert sensor.extra_state_attributes["raw_total_bytes"] == 1_500


def test_trend_sensor_formats_recent_volume_in_gigabytes() -> None:
    """Test recent volume sensors display GB while keeping raw bytes in attrs."""
    entry = _entry()
    coordinator = _coordinator()
    coordinator.data["bandwidth"]["download_bytes"] = 1_246_400_717
    description = next(
        item for item in SENSOR_DESCRIPTIONS if item.key == "download_last_5m"
    )
    sensor = FirewallaTrendSensor(coordinator, entry, description)

    assert sensor.native_value == 1.25
    assert sensor.extra_state_attributes["raw_download_bytes"] == 1_246_400_717
    assert sensor.extra_state_attributes["window_minutes"] == 15
    assert sensor.extra_state_attributes["window_seconds"] == 900


def test_trend_sensor_unavailable_when_capability_is_missing() -> None:
    """Test sensors go unavailable when their source capability is absent."""
    entry = _entry()
    coordinator = _coordinator()
    coordinator.data["capabilities"]["trends"] = False
    description = next(item for item in SENSOR_DESCRIPTIONS if item.key == "flows")
    sensor = FirewallaTrendSensor(coordinator, entry, description)

    assert sensor.available is False
    assert sensor.native_value is None


def test_trend_sensor_handles_invalid_source_payloads() -> None:
    """Test malformed payloads return safe defaults."""
    entry = _entry()
    coordinator = _coordinator()

    top_description = next(
        item for item in SENSOR_DESCRIPTIONS if item.key == "top_box_blocked_flows"
    )
    coordinator.data["top_stats"] = "bad"
    top_sensor = FirewallaTrendSensor(coordinator, entry, top_description)
    assert top_sensor.native_value is None

    bandwidth_description = next(
        item for item in SENSOR_DESCRIPTIONS if item.key == "download_mbps"
    )
    coordinator.data["bandwidth"] = "bad"
    bandwidth_sensor = FirewallaTrendSensor(coordinator, entry, bandwidth_description)
    assert bandwidth_sensor.native_value is None


def test_per_box_sensor_value_and_attrs() -> None:
    """Test per-box sensors use box-scoped data."""
    entry = _entry()
    coordinator = _coordinator()
    description = next(item for item in SENSOR_DESCRIPTIONS if item.key == "flows")
    sensor = FirewallaPerBoxSensor(coordinator, entry, "g1", "Branch Box", description)

    assert sensor.available is True
    assert sensor.native_value == 8
    assert sensor.device_info["name"] == "Firewalla Branch Box"
    assert sensor.extra_state_attributes["source"] == "top_stats"
    assert sensor.extra_state_attributes["stats_type"] == "topBoxesByBlockedFlows"


def test_per_box_sensor_uses_top_stats_and_box_metadata() -> None:
    """Test per-box sensors derive counts from box-scoped top stats."""
    entry = _entry()
    coordinator = _coordinator()

    blocked_description = next(item for item in SENSOR_DESCRIPTIONS if item.key == "flows")
    blocked_sensor = FirewallaPerBoxSensor(
        coordinator, entry, "g1", "Branch Box", blocked_description
    )
    assert blocked_sensor.native_value == 8


async def test_async_setup_entry_adds_supported_per_box_entities() -> None:
    """Test sensor setup adds one standard sensor set per discovered box."""
    entry = _entry()
    entry.runtime_data = _coordinator()
    hass = SimpleNamespace(data={"firewalla": {"entry-1": entry.runtime_data}})
    added = []

    def _add_entities(entities):
        added.extend(entities)

    await async_setup_entry(hass, entry, _add_entities)

    assert len(added) == (
        len(_GLOBAL_SENSOR_KEYS) + len(_PER_BOX_SENSOR_KEYS) + 4 + 1
    )
    assert any(isinstance(entity, FirewallaPerDeviceTrafficSensor) for entity in added)


async def test_async_setup_entry_ignores_network_rows() -> None:
    """Test setup ignores per-network rows and still adds per-box entities."""
    entry = _entry()
    entry.runtime_data = _coordinator()
    entry.runtime_data.data["capabilities"]["top_stats"] = False
    entry.runtime_data.data["network_bandwidth"] = {
        "bad1": "skip",
        "bad2": {"id": "bad2", "name": ""},
    }
    hass = SimpleNamespace(data={"firewalla": {"entry-1": entry.runtime_data}})
    added = []

    def _add_entities(entities):
        added.extend(entities)

    await async_setup_entry(hass, entry, _add_entities)

    expected = len(_GLOBAL_SENSOR_KEYS) + len(_PER_BOX_SENSOR_KEYS) + 1
    assert len(added) == expected


def test_per_box_network_bandwidth_sensor_value_and_attrs() -> None:
    """Test per-box network bandwidth sensors attach to the box device."""
    entry = _entry()
    coordinator = _coordinator()
    sensor = FirewallaPerBoxNetworkBandwidthSensor(
        coordinator,
        entry,
        "g1",
        "g1::net1",
        "Main LAN",
        "download_mbps",
        "Download Mbps",
        "mdi:speedometer",
        "Mbps",
        None,
    )

    assert sensor.available is True
    assert sensor.native_value == 2.5
    assert sensor.device_info["name"] == "Firewalla Branch Box"
    assert sensor.extra_state_attributes["network_name"] == "Main LAN"
