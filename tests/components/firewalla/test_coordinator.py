"""Tests for coordinator helpers and data updates."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.firewalla.api import (
    FirewallaApiAuthError,
    FirewallaApiError,
    TrendPoint,
)
from custom_components.firewalla.const import (
    CONF_SCOPE_ID,
    CONF_SCOPE_TYPE,
    CONF_TRAFFIC_WINDOW_MINUTES,
    DEFAULT_TRAFFIC_WINDOW_MINUTES,
    DOMAIN,
    SCOPE_BOX,
    SCOPE_GLOBAL,
    SCOPE_GROUP,
)
from custom_components.firewalla.coordinator import (
    FirewallaTrendsCoordinator,
    _aggregate_bandwidth,
    _build_flow_query,
    _build_known_networks,
    _build_network_bandwidth,
    _build_scope_info,
    _compute_rate_mbps,
    _network_key,
    _scope_from_entry,
)


def test_helper_builders() -> None:
    """Test coordinator helper builders."""
    assert _network_key("g1", "net1") == "g1::net1"
    assert _network_key(None, "net1") == "global::net1"
    assert _compute_rate_mbps(625_000, 5) == 1.0
    assert _build_flow_query(SCOPE_GLOBAL, None, 10) == "ts:>10 status:ok"
    assert (
        _build_flow_query(SCOPE_GROUP, "branch", 10)
        == "box.group.id:branch ts:>10 status:ok"
    )
    assert _build_flow_query(SCOPE_BOX, "gid-1", 10) == "box.id:gid-1 ts:>10 status:ok"

    assert _scope_from_entry(SimpleNamespace(data={})) == (SCOPE_GLOBAL, None)
    assert _scope_from_entry(
        SimpleNamespace(data={CONF_SCOPE_TYPE: SCOPE_BOX, CONF_SCOPE_ID: "gid-1"})
    ) == (SCOPE_BOX, "gid-1")
    assert _scope_from_entry(SimpleNamespace(data={"group": "legacy"})) == (
        SCOPE_GROUP,
        "legacy",
    )
    from custom_components.firewalla.coordinator import _traffic_window_minutes_from_entry

    assert _traffic_window_minutes_from_entry(SimpleNamespace(data={}, options={})) == (
        DEFAULT_TRAFFIC_WINDOW_MINUTES
    )
    assert _traffic_window_minutes_from_entry(
        SimpleNamespace(data={CONF_TRAFFIC_WINDOW_MINUTES: 5}, options={})
    ) == 5
    assert _traffic_window_minutes_from_entry(
        SimpleNamespace(data={}, options={CONF_TRAFFIC_WINDOW_MINUTES: 30})
    ) == 30


def test_scope_info_and_bandwidth_helpers() -> None:
    """Test scope metadata and bandwidth aggregation helpers."""
    boxes = [{"gid": "gid-1", "name": "Branch Box", "model": "FWG", "online": True}]
    scope = _build_scope_info(SCOPE_BOX, "gid-1", boxes)
    assert scope["label"] == "Branch Box"
    assert scope["box_model"] == "FWG"

    known_networks = _build_known_networks(
        [
            {"gid": "gid-1", "network": {"id": "1", "name": "LAN", "type": "lan"}},
            {"gid": "gid-2", "network": {"id": "2", "name": "LAN", "type": "lan"}},
            {"network": {"id": "", "name": "skip"}},
            {"network": "skip"},
        ],
        {
            "gid-1": {"gid": "gid-1", "name": "Box One", "model": "FW1"},
            "gid-2": {"gid": "gid-2", "name": "Box Two", "model": "FW2"},
        },
    )
    assert known_networks["gid-1::1"]["display_name"] == "Box One LAN"
    assert known_networks["gid-2::2"]["display_name"] == "Box Two LAN"

    network_bandwidth = _build_network_bandwidth(
        known_networks,
        [
            {
                "gid": "gid-1",
                "network": {"id": "1", "name": "LAN", "type": "lan"},
                "download": 1_250_000,
                "upload": 625_000,
                "count": 2,
            },
            {
                "gid": "gid-2",
                "network": {"id": "2", "name": "LAN"},
                "download": -100,
                "upload": 125_000,
                "count": 0,
            },
            {"blocked": True, "network": {"id": "3", "name": "Blocked"}, "download": 99},
            {"network": "bad", "download": 100},
        ],
        5,
        {
            "gid-1": {"gid": "gid-1", "name": "Box One", "model": "FW1"},
            "gid-2": {"gid": "gid-2", "name": "Box Two", "model": "FW2"},
        },
    )
    assert network_bandwidth["gid-1::1"]["download_mbps"] == 2.0
    assert network_bandwidth["gid-1::1"]["upload_mbps"] == 1.0
    assert network_bandwidth["gid-2::2"]["download_bytes"] == 0
    assert network_bandwidth["gid-2::2"]["flow_count"] == 1

    aggregate = _aggregate_bandwidth(network_bandwidth, 5)
    assert aggregate["download_bytes"] == 1_250_000
    assert aggregate["upload_bytes"] == 750_000
    assert aggregate["download_mbps"] == 2.0
    assert aggregate["upload_mbps"] == 1.2


def test_network_bandwidth_merges_missing_gid_into_known_network() -> None:
    """Test grouped flows without gid reuse the only matching known network."""
    known_networks = _build_known_networks(
        [
            {
                "gid": "gid-1",
                "network": {"id": "1", "name": "Wired", "type": "lan"},
            }
        ],
        {"gid-1": {"gid": "gid-1", "name": "Tudor Firewalla", "model": "FW"}},
    )

    network_bandwidth = _build_network_bandwidth(
        known_networks,
        [
            {
                "network": {"id": "1", "name": "Wired", "type": "lan"},
                "download": 1_250_000,
                "upload": 625_000,
                "count": 2,
            }
        ],
        5,
        {"gid-1": {"gid": "gid-1", "name": "Tudor Firewalla", "model": "FW"}},
    )

    assert "global::1" not in network_bandwidth
    assert network_bandwidth["gid-1::1"]["download_bytes"] == 1_250_000
    assert network_bandwidth["gid-1::1"]["display_name"] == "Wired"


class MockClient:
    """Mock client for coordinator tests."""

    def __init__(self) -> None:
        self.base_url = "https://example.firewalla.net"
        self.grouped_flow_queries: list[str | None] = []
        self.device_kwargs: list[dict[str, object]] = []
        self.box_group_filters: list[str | None] = []

    async def async_get_boxes(self, *, group: str | None = None) -> list[dict[str, object]]:
        self.box_group_filters.append(group)
        return [
            {"gid": "gid-1", "name": "Box One", "model": "FW1", "online": True},
            {"gid": "gid-2", "name": "Box Two", "model": "FW2", "online": False},
        ]

    async def async_get_trend(
        self, trend_type: str, group: str | None
    ) -> list[TrendPoint]:
        return [TrendPoint(ts=1_700_000_000, value=len(trend_type))]

    async def async_get_simple_stats(self, group: str | None) -> dict[str, int]:
        return {"onlineBoxes": 3, "offlineBoxes": 1, "alarms": 2, "rules": 4}

    async def async_get_devices(
        self, *, group: str | None = None, box: str | None = None
    ) -> list[dict[str, object]]:
        self.device_kwargs.append({"group": group, "box": box})
        gid = box or "gid-1"
        return [{"gid": gid, "network": {"id": "1", "name": "LAN", "type": "lan"}}]

    async def async_get_statistics(
        self, stats_type: str, *, group: str | None, limit: int
    ) -> list[dict[str, object]]:
        return [{"meta": {"name": stats_type}, "value": 5}]

    async def async_get_grouped_flows(
        self,
        *,
        query: str | None = None,
        group_by: str = "network",
        limit: int = 100,
    ) -> list[dict[str, object]]:
        self.grouped_flow_queries.append(query)
        return [
            {
                "gid": "gid-1",
                "network": {"id": "1", "name": "LAN", "type": "lan"},
                "download": 1_250_000,
                "upload": 625_000,
                "count": 2,
            }
        ]


@pytest.mark.asyncio
async def test_coordinator_update_success_global_scope(hass) -> None:
    """Test coordinator update success path."""
    entry = SimpleNamespace(
        data={"name": "Firewalla", "scan_interval": 300, CONF_SCOPE_TYPE: SCOPE_GLOBAL},
        options={},
    )
    coordinator = FirewallaTrendsCoordinator(hass, entry, MockClient())
    result = await coordinator._async_update_data()

    expected_download_mbps = round(
        (1_250_000 * 8) / (DEFAULT_TRAFFIC_WINDOW_MINUTES * 60) / 1_000_000, 3
    )
    assert sorted(result["trends"].keys()) == ["alarms", "flows", "rules"]
    assert result["simple_stats"]["onlineBoxes"] == 3
    assert result["bandwidth"]["download_mbps"] == expected_download_mbps
    assert result["bandwidth"]["window_minutes"] == DEFAULT_TRAFFIC_WINDOW_MINUTES
    assert result["network_bandwidth"]["gid-1::1"]["name"] == "LAN"
    assert result["bandwidth"]["flow_count"] == 2
    assert result["capabilities"]["top_stats"] is True
    assert result["scope"]["type"] == SCOPE_GLOBAL


@pytest.mark.asyncio
async def test_coordinator_box_scope_degrades_gracefully(hass) -> None:
    """Test box scope skips unsupported trend/stat endpoints."""
    client = MockClient()
    entry = SimpleNamespace(
        data={
            "name": "Firewalla",
            "scan_interval": 300,
            CONF_SCOPE_TYPE: SCOPE_BOX,
            CONF_SCOPE_ID: "gid-1",
            CONF_TRAFFIC_WINDOW_MINUTES: 5,
        },
        options={},
    )
    coordinator = FirewallaTrendsCoordinator(hass, entry, client)
    result = await coordinator._async_update_data()

    assert result["capabilities"]["trends"] is False
    assert result["capabilities"]["simple_stats"] is False
    assert result["capabilities"]["top_stats"] is False
    assert result["capabilities"]["devices"] is True
    assert result["capabilities"]["bandwidth"] is True
    assert result["endpoint_errors"]["trends"] == "unsupported_scope_box"
    assert client.device_kwargs == [{"group": None, "box": "gid-1"}]
    assert client.grouped_flow_queries[0].startswith("box.id:gid-1 ")
    assert result["bandwidth"]["window_minutes"] == 5


@pytest.mark.asyncio
async def test_coordinator_group_scope_uses_group_filters(hass) -> None:
    """Test group scope applies group filters to supported endpoints."""
    client = MockClient()
    entry = SimpleNamespace(
        data={
            "name": "Firewalla",
            "scan_interval": 300,
            CONF_SCOPE_TYPE: SCOPE_GROUP,
            CONF_SCOPE_ID: "branch",
        },
        options={CONF_TRAFFIC_WINDOW_MINUTES: 30},
    )
    coordinator = FirewallaTrendsCoordinator(hass, entry, client)
    await coordinator._async_update_data()

    assert client.box_group_filters == ["branch"]
    assert client.device_kwargs == [{"group": "branch", "box": None}]
    assert client.grouped_flow_queries[0].startswith("box.group.id:branch ")
    assert coordinator.traffic_window_minutes == 30


@pytest.mark.asyncio
async def test_coordinator_optional_endpoint_failure_is_non_fatal(hass) -> None:
    """Test optional endpoint failures degrade instead of aborting."""

    class PartialClient(MockClient):
        async def async_get_statistics(
            self, stats_type: str, *, group: str | None, limit: int
        ) -> list[dict[str, object]]:
            raise FirewallaApiError("http_403")

    entry = SimpleNamespace(
        data={"name": "Firewalla", "scan_interval": 300, CONF_SCOPE_TYPE: SCOPE_GLOBAL},
        options={},
    )
    coordinator = FirewallaTrendsCoordinator(hass, entry, PartialClient())
    result = await coordinator._async_update_data()

    assert result["capabilities"]["top_stats"] is False
    assert result["endpoint_errors"]["stats:topBoxesByBlockedFlows"] == "http_403"
    assert result["bandwidth"]["download_bytes"] == 1_250_000


@pytest.mark.asyncio
async def test_coordinator_update_auth_failure(hass) -> None:
    """Test coordinator converts auth failure."""

    class AuthFailClient(MockClient):
        async def async_get_boxes(self, *, group: str | None = None):
            raise FirewallaApiAuthError

    entry = SimpleNamespace(
        data={"name": DOMAIN, "scan_interval": 300, CONF_SCOPE_TYPE: SCOPE_GLOBAL},
        options={},
    )
    coordinator = FirewallaTrendsCoordinator(hass, entry, AuthFailClient())

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_coordinator_update_transport_failure_when_no_endpoint_works(hass) -> None:
    """Test coordinator fails when no usable endpoints remain."""

    class ErrorClient(MockClient):
        async def async_get_boxes(self, *, group: str | None = None):
            raise FirewallaApiError("cannot_connect")

        async def async_get_trend(self, trend_type: str, group: str | None):
            raise FirewallaApiError("cannot_connect")

        async def async_get_simple_stats(self, group: str | None):
            raise FirewallaApiError("cannot_connect")

        async def async_get_statistics(
            self, stats_type: str, *, group: str | None, limit: int
        ):
            raise FirewallaApiError("cannot_connect")

        async def async_get_devices(self, *, group: str | None = None, box: str | None = None):
            raise FirewallaApiError("cannot_connect")

        async def async_get_grouped_flows(self, *, query: str | None = None, group_by: str = "network", limit: int = 100):
            raise FirewallaApiError("cannot_connect")

    entry = SimpleNamespace(
        data={"name": DOMAIN, "scan_interval": 300, CONF_SCOPE_TYPE: SCOPE_GLOBAL},
        options={},
    )
    coordinator = FirewallaTrendsCoordinator(hass, entry, ErrorClient())

    with pytest.raises(UpdateFailed, match="No Firewalla endpoints available"):
        await coordinator._async_update_data()
