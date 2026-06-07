"""Tests for Firewalla sensors."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from homeassistant.helpers import entity_registry as er

from custom_components.firewalla.api import TrendPoint
from custom_components.firewalla.const import SCOPE_GROUP
from custom_components.firewalla.sensor import (
    _GLOBAL_SENSOR_KEYS,
    _PER_BOX_SENSOR_KEYS,
    SENSOR_DESCRIPTIONS,
    FirewallaPerBoxNetworkBandwidthSensor,
    FirewallaPerBoxSensor,
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
                    "name": "Box One",
                    "model": "FW",
                    "online": True,
                }
            ],
            "capabilities": {
                "trends": True,
                "simple_stats": True,
                "top_stats": True,
                "bandwidth": True,
                "box_bandwidth": True,
                "network_bandwidth": True,
            },
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
                    "name": "Box One",
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
                    "box_name": "Box One",
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


def test_trend_sensor_device_info_and_state_fallbacks() -> None:
    """Test trend sensors fall back to coordinator scope metadata."""
    entry = _entry()
    coordinator = _coordinator()
    coordinator.data["scope"] = "bad"
    coordinator.data["capabilities"] = "bad"

    sensor = FirewallaTrendSensor(
        coordinator,
        entry,
        next(item for item in SENSOR_DESCRIPTIONS if item.key == "flows"),
    )

    assert sensor.device_info["name"] == "Firewalla global"
    assert sensor.extra_state_attributes["scope_type"] == "global"
    assert sensor.extra_state_attributes["scope_id"] is None
    assert sensor.available is False
    assert sensor.native_value is None


def test_trend_sensor_handles_all_source_variants() -> None:
    """Test trend sensors cover the remaining source-specific fallbacks."""
    entry = _entry()
    coordinator = _coordinator()

    simple_description = next(
        item for item in SENSOR_DESCRIPTIONS if item.key == "online_boxes"
    )
    coordinator.data["simple_stats"] = "bad"
    simple_sensor = FirewallaTrendSensor(coordinator, entry, simple_description)
    assert simple_sensor.native_value is None

    top_description = next(
        item for item in SENSOR_DESCRIPTIONS if item.key == "top_box_blocked_flows"
    )
    coordinator.data["top_stats"] = "bad"
    top_sensor = FirewallaTrendSensor(coordinator, entry, top_description)
    assert top_sensor.native_value is None
    assert top_sensor.extra_state_attributes["source"] == "top_stats"

    coordinator.data["top_stats"] = {"topBoxesByBlockedFlows": [{"value": "bad"}]}
    top_sensor = FirewallaTrendSensor(coordinator, entry, top_description)
    assert top_sensor.native_value == 0

    bandwidth_description = next(
        item for item in SENSOR_DESCRIPTIONS if item.key == "download_mbps"
    )
    coordinator.data["bandwidth"] = "bad"
    bandwidth_sensor = FirewallaTrendSensor(coordinator, entry, bandwidth_description)
    assert bandwidth_sensor.native_value is None
    assert bandwidth_sensor.extra_state_attributes["source"] == "grouped_flows"

    coordinator.data["bandwidth"] = {"download_mbps": "bad"}
    bandwidth_sensor = FirewallaTrendSensor(coordinator, entry, bandwidth_description)
    assert bandwidth_sensor.native_value == 0

    flow_description = next(item for item in SENSOR_DESCRIPTIONS if item.key == "flows")
    coordinator.data["trends"] = "bad"
    trend_sensor = FirewallaTrendSensor(coordinator, entry, flow_description)
    assert trend_sensor.native_value is None
    assert trend_sensor.extra_state_attributes["source"] == "trends"

    coordinator.data["trends"] = {"flows": []}
    trend_sensor = FirewallaTrendSensor(coordinator, entry, flow_description)
    assert trend_sensor.native_value == 0
    assert trend_sensor.extra_state_attributes["trend_type"] == "flows"

    coordinator.data["trends"] = {"flows": [{"value": 10}]}
    trend_sensor = FirewallaTrendSensor(coordinator, entry, flow_description)
    assert trend_sensor.native_value == 0


def test_per_box_sensor_value_and_attrs() -> None:
    """Test per-box sensors use box-scoped data."""
    entry = _entry()
    coordinator = _coordinator()
    description = next(item for item in SENSOR_DESCRIPTIONS if item.key == "flows")
    sensor = FirewallaPerBoxSensor(coordinator, entry, "g1", "Box One", description)

    assert sensor.available is True
    assert sensor.native_value == 8
    assert sensor.device_info["name"] == "Firewalla Box One"
    assert sensor.extra_state_attributes["source"] == "top_stats"
    assert sensor.extra_state_attributes["stats_type"] == "topBoxesByBlockedFlows"


def test_per_box_sensor_uses_top_stats_and_box_metadata() -> None:
    """Test per-box sensors derive counts from box-scoped top stats."""
    entry = _entry()
    coordinator = _coordinator()

    blocked_description = next(item for item in SENSOR_DESCRIPTIONS if item.key == "flows")
    blocked_sensor = FirewallaPerBoxSensor(
        coordinator, entry, "g1", "Box One", blocked_description
    )
    assert blocked_sensor.native_value == 8


def test_per_box_sensor_fallbacks_and_unsupported_metrics() -> None:
    """Test per-box sensors cover fallback metadata and unsupported keys."""
    entry = _entry()
    coordinator = _coordinator()
    coordinator.data["boxes"] = []
    coordinator.data["box_bandwidth"] = {
        "g1": {"gid": "g1", "name": "Fallback Box", "model": "FW2", "online": False}
    }
    coordinator.data["top_stats"]["topBoxesByBlockedFlows"] = [
        {"meta": {"gid": "other"}, "value": 4}
    ]
    coordinator.data["top_stats"]["topBoxesBySecurityAlarms"] = "bad"

    blocked_description = next(item for item in SENSOR_DESCRIPTIONS if item.key == "flows")
    blocked_sensor = FirewallaPerBoxSensor(
        coordinator, entry, "g1", "Box One", blocked_description
    )
    assert blocked_sensor.device_info["name"] == "Firewalla Fallback Box"
    assert blocked_sensor.native_value == 0
    assert blocked_sensor.extra_state_attributes["box_name"] == "Fallback Box"
    assert blocked_sensor._box() == {
        "gid": "g1",
        "name": "Fallback Box",
        "model": "FW2",
        "online": False,
    }
    coordinator.data["boxes"] = ["bad", {"gid": "other", "name": "Wrong Box"}]
    coordinator.data["box_bandwidth"] = {}
    assert blocked_sensor._box() == {}

    coordinator.data["top_stats"] = {
        "topBoxesByBlockedFlows": [{"meta": "bad", "value": 4}],
        "topBoxesBySecurityAlarms": [{"meta": {"gid": "g1"}, "value": 6}],
    }
    alarm_sensor = FirewallaPerBoxSensor(
        coordinator,
        entry,
        "g1",
        "Box One",
        next(item for item in SENSOR_DESCRIPTIONS if item.key == "alarms"),
    )
    assert alarm_sensor.native_value == 6
    assert alarm_sensor.extra_state_attributes["stats_type"] == "topBoxesBySecurityAlarms"

    unsupported_description = next(
        item for item in SENSOR_DESCRIPTIONS if item.key == "download_mbps"
    )
    unsupported_sensor = FirewallaPerBoxSensor(
        coordinator, entry, "g1", "Box One", unsupported_description
    )
    assert unsupported_sensor.available is False
    assert unsupported_sensor.native_value is None
    assert unsupported_sensor.extra_state_attributes["source"] == "unsupported_box_metric"


def test_per_box_sensor_handles_malformed_top_stats() -> None:
    """Test per-box top-stat helper handles malformed payloads."""
    entry = _entry()
    coordinator = _coordinator()
    coordinator.data["top_stats"] = "bad"
    sensor = FirewallaPerBoxSensor(
        coordinator,
        entry,
        "g1",
        "Box One",
        next(item for item in SENSOR_DESCRIPTIONS if item.key == "flows"),
    )

    assert sensor.available is True
    assert sensor.native_value is None

    coordinator.data["top_stats"] = {"topBoxesByBlockedFlows": "bad"}
    assert sensor._box_top_stat_value("topBoxesByBlockedFlows") is None

    coordinator.data["top_stats"] = {
        "topBoxesByBlockedFlows": [1],
        "topBoxesBySecurityAlarms": [{"meta": {"gid": "other"}, "value": 1}],
    }
    assert sensor._box_top_stat_value("topBoxesByBlockedFlows") == 0
    assert sensor._box_top_stat_value("topBoxesBySecurityAlarms") == 0
    coordinator.data["capabilities"] = "bad"
    assert sensor.available is False


async def test_async_setup_entry_adds_supported_per_box_entities() -> None:
    """Test sensor setup adds one standard sensor set per discovered box."""
    entry = _entry()
    entry.runtime_data = _coordinator()
    hass = SimpleNamespace(data={"firewalla": {"entry-1": entry.runtime_data}})
    added = []

    def _add_entities(entities):
        added.extend(entities)

    await async_setup_entry(hass, entry, _add_entities)

    assert len(added) == len(_GLOBAL_SENSOR_KEYS) + len(_PER_BOX_SENSOR_KEYS) + 4


@patch.object(
    er,
    "async_entries_for_config_entry",
    return_value=[
        SimpleNamespace(platform="light", entity_id="sensor.skip"),
        SimpleNamespace(platform="firewalla", entity_id="sensor.old"),
    ],
)
@patch.object(er, "async_get")
async def test_async_setup_entry_removes_existing_entities(
    mock_async_get, mock_entries
) -> None:
    """Test setup removes existing registry entries for the config entry."""
    entry = _entry()
    entry.runtime_data = _coordinator()
    entity_registry = MagicMock()
    mock_async_get.return_value = entity_registry
    hass = SimpleNamespace(data={"firewalla": {"entry-1": entry.runtime_data}})
    added = []

    await async_setup_entry(hass, entry, added.extend)

    entity_registry.async_remove.assert_called_once_with("sensor.old")
    assert len(added) > 0


@patch.object(er, "async_entries_for_config_entry", return_value=[])
@patch.object(er, "async_get")
async def test_async_setup_entry_skips_malformed_box_rows(
    mock_async_get, mock_entries
) -> None:
    """Test setup skips malformed boxes but still adds valid entities."""
    entry = _entry()
    coordinator = _coordinator()
    coordinator.data["boxes"] = [
        "bad",
        {"gid": "", "name": "No GID"},
        {"gid": "g1", "name": "Box One", "model": "FW", "online": True},
    ]
    coordinator.data["network_bandwidth"] = "bad"
    entry.runtime_data = coordinator
    mock_async_get.return_value = MagicMock()
    hass = SimpleNamespace(data={"firewalla": {"entry-1": coordinator}})
    added = []

    await async_setup_entry(hass, entry, added.extend)

    assert len(added) == len(_GLOBAL_SENSOR_KEYS) + len(_PER_BOX_SENSOR_KEYS)


@patch.object(er, "async_get", side_effect=TypeError)
async def test_async_setup_entry_handles_invalid_registry_and_non_list_data(_mock_async_get) -> None:
    """Test setup tolerates invalid registry lookup and malformed data payloads."""
    entry = _entry()
    coordinator = _coordinator()
    coordinator.data["boxes"] = "bad"
    coordinator.data["network_bandwidth"] = "bad"
    entry.runtime_data = coordinator
    hass = SimpleNamespace(data={"firewalla": {"entry-1": coordinator}})
    added = []

    await async_setup_entry(hass, entry, added.extend)

    assert len(added) == len(_GLOBAL_SENSOR_KEYS)


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

    expected = len(_GLOBAL_SENSOR_KEYS) + len(_PER_BOX_SENSOR_KEYS)
    assert len(added) == expected


def test_per_box_network_bandwidth_sensor_value_and_attrs() -> None:
    """Test per-box network bandwidth sensors attach to the box device."""
    entry = _entry()
    coordinator = _coordinator()
    sensor = FirewallaPerBoxNetworkBandwidthSensor(
        coordinator,
        entry,
        "g1",
        "Box One",
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
    assert sensor._attr_name == "Box One-Main LAN-Download Mbps"
    assert sensor._attr_suggested_object_id == "firewalla_box_one_main_lan_download_mbps"
    assert sensor.device_info["name"] == "Firewalla Box One"
    assert sensor.extra_state_attributes["network_name"] == "Main LAN"


def test_per_box_network_bandwidth_sensor_fallbacks() -> None:
    """Test network bandwidth sensors handle missing network data."""
    entry = _entry()
    coordinator = _coordinator()
    coordinator.data["boxes"] = []
    coordinator.data["network_bandwidth"] = {}

    sensor = FirewallaPerBoxNetworkBandwidthSensor(
        coordinator,
        entry,
        "g1",
        "Box One",
        "g1::missing",
        "Missing LAN",
        "download_bytes",
        "Download Recent Volume",
        "mdi:download-network-outline",
        "GB",
        None,
    )

    assert sensor.device_info["name"] == "Firewalla g1"
    assert sensor.device_info["model"] == "MSP API"
    assert sensor.available is True
    assert sensor.native_value == 0
    assert sensor.extra_state_attributes["source"] == "grouped_flows_by_network"
    assert sensor.extra_state_attributes["network_key"] == "g1::missing"

    coordinator.data["network_bandwidth"] = "bad"
    bad_sensor = FirewallaPerBoxNetworkBandwidthSensor(
        coordinator,
        entry,
        "g1",
        "Box One",
        "g1::net1",
        "Main LAN",
        "upload_mbps",
        "Upload Mbps",
        "mdi:speedometer-medium",
        "Mbps",
        None,
    )
    assert bad_sensor.native_value is None
    assert bad_sensor.extra_state_attributes["source"] == "grouped_flows_by_network"

    coordinator.data["capabilities"] = "bad"
    unavailable_sensor = FirewallaPerBoxNetworkBandwidthSensor(
        coordinator,
        entry,
        "g1",
        "Box One",
        "g1::net1",
        "Main LAN",
        "upload_mbps",
        "Upload Mbps",
        "mdi:speedometer-medium",
        "Mbps",
        None,
    )
    assert unavailable_sensor.available is False
    assert unavailable_sensor.native_value is None

    coordinator.data["capabilities"] = {
        "trends": True,
        "simple_stats": True,
        "top_stats": True,
        "bandwidth": True,
        "box_bandwidth": True,
        "network_bandwidth": True,
    }
    coordinator.data["network_bandwidth"] = {
        "g1::net1": {
            "id": "net1",
            "name": "Main LAN",
            "display_name": "Main LAN",
            "gid": "g1",
            "box_name": "Box One",
            "type": "lan",
            "download_bytes": 500,
            "upload_bytes": 250,
            "flow_count": 2,
            "window_minutes": 15,
            "window_seconds": 900,
        }
    }
    download_sensor = FirewallaPerBoxNetworkBandwidthSensor(
        coordinator,
        entry,
        "g1",
        "Box One",
        "g1::net1",
        "Main LAN",
        "download_bytes",
        "Download Recent Volume",
        "mdi:download-network-outline",
        "GB",
        None,
    )
    assert download_sensor.native_value == 0.0
    assert download_sensor.extra_state_attributes["network_name"] == "Main LAN"


def test_per_box_network_bandwidth_sensor_handles_device_fallbacks() -> None:
    """Test network bandwidth sensors fall back cleanly when box metadata is partial."""
    entry = _entry()
    coordinator = _coordinator()
    coordinator.data["boxes"] = [
        "bad",
        {"gid": "other", "name": "Wrong Box"},
    ]
    sensor = FirewallaPerBoxNetworkBandwidthSensor(
        coordinator,
        entry,
        "g1",
        "Box One",
        "g1::net1",
        "Main LAN",
        "download_mbps",
        "Download Mbps",
        "mdi:speedometer",
        "Mbps",
        None,
    )

    assert sensor.device_info["name"] == "Firewalla g1"
    assert sensor.device_info["model"] == "MSP API"
    assert sensor._box_name == "Box One"


def test_sensor_handle_coordinator_update_callbacks() -> None:
    """Test sensor update callbacks call write_state."""
    entry = _entry()
    coordinator = _coordinator()
    trend_sensor = FirewallaTrendSensor(
        coordinator,
        entry,
        next(item for item in SENSOR_DESCRIPTIONS if item.key == "flows"),
    )
    box_sensor = FirewallaPerBoxSensor(
        coordinator,
        entry,
        "g1",
        "Box One",
        next(item for item in SENSOR_DESCRIPTIONS if item.key == "flows"),
    )
    network_sensor = FirewallaPerBoxNetworkBandwidthSensor(
        coordinator,
        entry,
        "g1",
        "Box One",
        "g1::net1",
        "Main LAN",
        "download_mbps",
        "Download Mbps",
        "mdi:speedometer",
        "Mbps",
        None,
    )

    trend_sensor.async_write_ha_state = MagicMock()
    box_sensor.async_write_ha_state = MagicMock()
    network_sensor.async_write_ha_state = MagicMock()

    trend_sensor._handle_coordinator_update()
    box_sensor._handle_coordinator_update()
    network_sensor._handle_coordinator_update()

    trend_sensor.async_write_ha_state.assert_called_once()
    box_sensor.async_write_ha_state.assert_called_once()
    network_sensor.async_write_ha_state.assert_called_once()
