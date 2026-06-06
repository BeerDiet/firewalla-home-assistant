"""Coordinator for Firewalla MSP data."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FirewallaApiAuthError, FirewallaApiClient, FirewallaApiError
from .const import (
    CONF_GROUP,
    CONF_SCAN_INTERVAL,
    CONF_SCOPE_ID,
    CONF_SCOPE_TYPE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STATS_LIMIT,
    DOMAIN,
    FLOW_WINDOW,
    OPTIONAL_ENDPOINT_ERRORS,
    SCOPE_BOX,
    SCOPE_GLOBAL,
    SCOPE_GROUP,
    TOP_STAT_TYPES,
    TREND_TYPES,
)

_LOGGER = logging.getLogger(__name__)


def _safe_int(value: object) -> int:
    """Return an int value or zero."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _compute_rate_mbps(byte_count: int, window_seconds: int) -> float:
    """Convert bytes over a window into Mbps."""
    return round((byte_count * 8) / window_seconds / 1_000_000, 3)


def _network_key(gid: str | None, network_id: str) -> str:
    """Build a stable network identifier within an MSP scope."""
    return f"{gid or 'global'}::{network_id}"


def _scope_from_entry(entry: ConfigEntry) -> tuple[str, str | None]:
    """Resolve the configured Firewalla scope."""
    scope_type = entry.data.get(CONF_SCOPE_TYPE)
    scope_id = entry.data.get(CONF_SCOPE_ID)

    if scope_type:
        normalized_scope_id = str(scope_id).strip() if scope_id else ""
        return str(scope_type), normalized_scope_id or None

    legacy_group = str(entry.data.get(CONF_GROUP) or "").strip()
    if legacy_group:
        return SCOPE_GROUP, legacy_group
    return SCOPE_GLOBAL, None


def _box_map(boxes: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    """Index boxes by gid."""
    indexed: dict[str, dict[str, object]] = {}
    for box in boxes:
        gid = str(box.get("gid") or "").strip()
        if gid:
            indexed[gid] = box
    return indexed


def _qualify_network_names(
    networks: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    """Ensure network display names are unique across boxes."""
    name_counts: dict[str, int] = {}
    for network in networks.values():
        name = str(network.get("name") or "").strip()
        if name:
            name_counts[name] = name_counts.get(name, 0) + 1

    for network in networks.values():
        name = str(network.get("name") or "").strip()
        box_name = str(network.get("box_name") or "").strip()
        if not name:
            continue
        if name_counts.get(name, 0) > 1 and box_name:
            network["display_name"] = f"{box_name} {name}"
        else:
            network["display_name"] = name

    return networks


def _build_known_networks(
    devices: list[dict[str, object]],
    boxes_by_gid: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    """Build a network map from device data."""
    networks: dict[str, dict[str, object]] = {}
    for device in devices:
        network = device.get("network")
        if not isinstance(network, dict):
            continue

        network_id = str(network.get("id") or "").strip()
        network_name = str(network.get("name") or "").strip()
        gid = str(device.get("gid") or "").strip()
        if not network_id or not network_name:
            continue

        box = boxes_by_gid.get(gid, {})
        key = _network_key(gid or None, network_id)
        networks[key] = {
            "id": network_id,
            "name": network_name,
            "display_name": network_name,
            "gid": gid or None,
            "box_name": str(box.get("name") or "").strip() or None,
            "box_model": str(box.get("model") or "").strip() or None,
            "type": network.get("type"),
            "group_id": (
                str(box.get("group") or "").strip() or str(network.get("gid") or "").strip() or None
            ),
        }

    return _qualify_network_names(networks)


def _build_scope_info(
    scope_type: str,
    scope_id: str | None,
    boxes: list[dict[str, object]],
) -> dict[str, object]:
    """Build scope metadata for diagnostics and entity attributes."""
    info: dict[str, object] = {
        "type": scope_type,
        "id": scope_id,
        "label": "Global MSP" if scope_type == SCOPE_GLOBAL else scope_id,
        "box_count": len(boxes),
    }

    if scope_type == SCOPE_BOX and scope_id:
        matched = next(
            (box for box in boxes if str(box.get("gid") or "").strip() == scope_id), None
        )
        if isinstance(matched, dict):
            info["label"] = str(matched.get("name") or scope_id)
            info["box_name"] = matched.get("name")
            info["box_model"] = matched.get("model")
            info["box_online"] = matched.get("online")
    elif scope_type == SCOPE_GROUP and scope_id:
        info["label"] = f"Group {scope_id}"
    return info


def _build_flow_query(scope_type: str, scope_id: str | None, window_start: int) -> str:
    """Build a grouped-flow query for the configured scope."""
    terms = [f"ts:>{window_start}", "status:ok"]
    if scope_type == SCOPE_GROUP and scope_id:
        terms.insert(0, f"box.group.id:{scope_id}")
    elif scope_type == SCOPE_BOX and scope_id:
        terms.insert(0, f"box.id:{scope_id}")
    return " ".join(terms)


def _build_network_bandwidth(
    known_networks: dict[str, dict[str, object]],
    recent_flows: list[dict[str, object]],
    window_seconds: int,
    boxes_by_gid: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    """Build per-network bandwidth stats from recent grouped flows."""
    network_bandwidth: dict[str, dict[str, object]] = {
        network_key: {
            **network,
            "download_bytes": 0,
            "upload_bytes": 0,
            "download_mbps": 0.0,
            "upload_mbps": 0.0,
            "flow_count": 0,
            "window_seconds": window_seconds,
        }
        for network_key, network in known_networks.items()
    }

    known_network_keys_by_id: dict[str, list[str]] = {}
    for network_key, network in known_networks.items():
        network_id = str(network.get("id") or "").strip()
        if not network_id:
            continue
        known_network_keys_by_id.setdefault(network_id, []).append(network_key)

    for item in recent_flows:
        if item.get("block") is True or item.get("blocked") is True:
            continue

        network = item.get("network")
        if not isinstance(network, dict):
            continue

        network_id = str(network.get("id") or "").strip()
        network_name = str(network.get("name") or "").strip()
        gid = str(item.get("gid") or "").strip()
        if not network_id or not network_name:
            continue

        download_bytes = max(_safe_int(item.get("download")), 0)
        upload_bytes = max(_safe_int(item.get("upload")), 0)
        flow_count = max(_safe_int(item.get("count")), 1)
        key = _network_key(gid or None, network_id)
        if not gid and key not in network_bandwidth:
            matching_keys = known_network_keys_by_id.get(network_id, [])
            if len(matching_keys) == 1:
                key = matching_keys[0]
                known_network = known_networks.get(key, {})
                gid = str(known_network.get("gid") or "").strip()

        box = boxes_by_gid.get(gid, {})
        current = network_bandwidth.setdefault(
            key,
            {
                "id": network_id,
                "name": network_name,
                "display_name": network_name,
                "gid": gid or None,
                "box_name": str(box.get("name") or "").strip() or None,
                "box_model": str(box.get("model") or "").strip() or None,
                "type": network.get("type"),
                "group_id": str(network.get("gid") or "").strip() or None,
                "download_bytes": 0,
                "upload_bytes": 0,
                "download_mbps": 0.0,
                "upload_mbps": 0.0,
                "flow_count": 0,
                "window_seconds": window_seconds,
            },
        )
        current["download_bytes"] = (
            _safe_int(current.get("download_bytes")) + download_bytes
        )
        current["upload_bytes"] = _safe_int(current.get("upload_bytes")) + upload_bytes
        current["flow_count"] = _safe_int(current.get("flow_count")) + flow_count
        current["download_mbps"] = _compute_rate_mbps(
            _safe_int(current.get("download_bytes")),
            window_seconds,
        )
        current["upload_mbps"] = _compute_rate_mbps(
            _safe_int(current.get("upload_bytes")),
            window_seconds,
        )

    return _qualify_network_names(network_bandwidth)


def _aggregate_bandwidth(
    network_bandwidth: dict[str, dict[str, object]], window_seconds: int
) -> dict[str, object]:
    """Aggregate global traffic totals from per-network data."""
    download_bytes = 0
    upload_bytes = 0
    counted_flows = 0

    for stats in network_bandwidth.values():
        download_bytes += _safe_int(stats.get("download_bytes"))
        upload_bytes += _safe_int(stats.get("upload_bytes"))
        counted_flows += _safe_int(stats.get("flow_count"))

    return {
        "download_bytes": download_bytes,
        "upload_bytes": upload_bytes,
        "download_mbps": _compute_rate_mbps(download_bytes, window_seconds),
        "upload_mbps": _compute_rate_mbps(upload_bytes, window_seconds),
        "flow_count": counted_flows,
        "window_seconds": window_seconds,
    }


class FirewallaTrendsCoordinator(DataUpdateCoordinator[dict[str, object]]):
    """Coordinate Firewalla polling."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: FirewallaApiClient,
    ) -> None:
        """Initialize the coordinator."""
        self.config_entry = entry
        self.client = client
        self.scope_type, self.scope_id = _scope_from_entry(entry)
        self.group = self.scope_id if self.scope_type == SCOPE_GROUP else None

        scan_seconds = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(
                CONF_SCAN_INTERVAL, int(DEFAULT_SCAN_INTERVAL.total_seconds())
            ),
        )

        super().__init__(
            hass,
            logger=_LOGGER,
            name=entry.data.get(CONF_NAME, DOMAIN),
            update_interval=timedelta(seconds=int(scan_seconds)),
        )

    async def _async_fetch_optional(self, endpoint: str, func, *args, **kwargs):
        """Fetch an optional endpoint and classify failures."""
        try:
            return True, await func(*args, **kwargs), None
        except FirewallaApiAuthError:
            raise
        except FirewallaApiError as err:
            error = str(err)
            if error in OPTIONAL_ENDPOINT_ERRORS:
                _LOGGER.debug("Firewalla endpoint %s unavailable: %s", endpoint, error)
            else:
                _LOGGER.warning("Firewalla endpoint %s failed: %s", endpoint, error)
            return False, None, error

    async def _async_update_data(self) -> dict[str, object]:
        """Fetch Firewalla data with graceful degradation."""
        try:
            now_ts = int(datetime.now(UTC).timestamp())
            window_seconds = int(FLOW_WINDOW.total_seconds())
            window_start = now_ts - window_seconds
            capabilities: dict[str, bool] = {
                "boxes": False,
                "trends": False,
                "simple_stats": False,
                "top_stats": False,
                "devices": False,
                "grouped_flows": False,
                "bandwidth": False,
                "network_bandwidth": False,
            }
            endpoint_errors: dict[str, str] = {}

            boxes: list[dict[str, object]] = []
            success, payload, error = await self._async_fetch_optional(
                "boxes",
                self.client.async_get_boxes,
                group=self.scope_id if self.scope_type == SCOPE_GROUP else None,
            )
            if success:
                boxes = payload if isinstance(payload, list) else []
                if self.scope_type == SCOPE_BOX and self.scope_id:
                    boxes = [
                        box
                        for box in boxes
                        if str(box.get("gid") or "").strip() == self.scope_id
                    ]
                capabilities["boxes"] = True
            elif error:
                endpoint_errors["boxes"] = error

            trends: dict[str, object] = {}
            if self.scope_type != SCOPE_BOX:
                trend_results: dict[str, object] = {}
                trend_supported = True
                for trend_type in TREND_TYPES:
                    success, payload, error = await self._async_fetch_optional(
                        f"trend:{trend_type}",
                        self.client.async_get_trend,
                        trend_type,
                        self.scope_id if self.scope_type == SCOPE_GROUP else None,
                    )
                    if success:
                        trend_results[trend_type] = payload
                    else:
                        trend_supported = False
                        trend_results[trend_type] = []
                        if error:
                            endpoint_errors[f"trend:{trend_type}"] = error
                trends = trend_results
                capabilities["trends"] = trend_supported
            else:
                endpoint_errors["trends"] = "unsupported_scope_box"

            simple_stats: dict[str, int] = {}
            if self.scope_type != SCOPE_BOX:
                success, payload, error = await self._async_fetch_optional(
                    "simple_stats",
                    self.client.async_get_simple_stats,
                    self.scope_id if self.scope_type == SCOPE_GROUP else None,
                )
                if success and isinstance(payload, dict):
                    simple_stats = payload
                    capabilities["simple_stats"] = True
                elif error:
                    endpoint_errors["simple_stats"] = error
            else:
                endpoint_errors["simple_stats"] = "unsupported_scope_box"

            top_stats: dict[str, object] = {}
            if self.scope_type != SCOPE_BOX:
                top_results: dict[str, object] = {}
                top_supported = True
                for stats_type in TOP_STAT_TYPES:
                    success, payload, error = await self._async_fetch_optional(
                        f"stats:{stats_type}",
                        self.client.async_get_statistics,
                        stats_type,
                        group=self.scope_id if self.scope_type == SCOPE_GROUP else None,
                        limit=DEFAULT_STATS_LIMIT,
                    )
                    if success:
                        top_results[stats_type] = payload
                    else:
                        top_supported = False
                        top_results[stats_type] = []
                        if error:
                            endpoint_errors[f"stats:{stats_type}"] = error
                top_stats = top_results
                capabilities["top_stats"] = top_supported
            else:
                endpoint_errors["top_stats"] = "unsupported_scope_box"

            devices: list[dict[str, object]] = []
            success, payload, error = await self._async_fetch_optional(
                "devices",
                self.client.async_get_devices,
                group=self.scope_id if self.scope_type == SCOPE_GROUP else None,
                box=self.scope_id if self.scope_type == SCOPE_BOX else None,
            )
            if success:
                devices = payload if isinstance(payload, list) else []
                capabilities["devices"] = True
            elif error:
                endpoint_errors["devices"] = error

            recent_flows: list[dict[str, object]] = []
            success, payload, error = await self._async_fetch_optional(
                "grouped_flows",
                self.client.async_get_grouped_flows,
                query=_build_flow_query(self.scope_type, self.scope_id, window_start),
                group_by="network",
            )
            if success:
                recent_flows = payload if isinstance(payload, list) else []
                capabilities["grouped_flows"] = True
            elif error:
                endpoint_errors["grouped_flows"] = error

            if not any(capabilities.values()):
                if endpoint_errors:
                    raise UpdateFailed(
                        "No Firewalla endpoints available: "
                        + ", ".join(sorted(f"{k}={v}" for k, v in endpoint_errors.items()))
                    )
                raise UpdateFailed("No Firewalla data returned")

            boxes_by_gid = _box_map(boxes)
            known_networks = _build_known_networks(devices, boxes_by_gid)
            network_bandwidth = (
                _build_network_bandwidth(
                    known_networks,
                    recent_flows,
                    window_seconds,
                    boxes_by_gid,
                )
                if capabilities["grouped_flows"]
                else {}
            )
            capabilities["network_bandwidth"] = bool(network_bandwidth)

            bandwidth = (
                _aggregate_bandwidth(network_bandwidth, window_seconds)
                if capabilities["grouped_flows"]
                else {
                    "download_bytes": 0,
                    "upload_bytes": 0,
                    "download_mbps": 0.0,
                    "upload_mbps": 0.0,
                    "flow_count": 0,
                    "window_seconds": window_seconds,
                }
            )
            capabilities["bandwidth"] = capabilities["grouped_flows"]

            return {
                "scope": _build_scope_info(self.scope_type, self.scope_id, boxes),
                "capabilities": capabilities,
                "endpoint_errors": endpoint_errors,
                "boxes": boxes,
                "trends": trends,
                "simple_stats": simple_stats,
                "top_stats": top_stats,
                "bandwidth": bandwidth,
                "network_bandwidth": network_bandwidth,
            }
        except FirewallaApiAuthError as err:
            raise ConfigEntryAuthFailed from err
        except FirewallaApiError as err:
            raise UpdateFailed(str(err)) from err
