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
    CONF_TRAFFIC_WINDOW_MINUTES,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STATS_LIMIT,
    DEFAULT_TOP_TALKERS_LIMIT,
    DEFAULT_TRAFFIC_WINDOW_MINUTES,
    DOMAIN,
    OPTIONAL_ENDPOINT_ERRORS,
    SCOPE_BOX,
    SCOPE_GLOBAL,
    SCOPE_GROUP,
    TEMPORARY_ENDPOINT_ERRORS,
    TOP_STAT_TYPES,
    TREND_TYPES,
)

_LOGGER = logging.getLogger(__name__)
_RATE_LIMIT_BACKOFF_BASE = timedelta(minutes=1)
_RATE_LIMIT_BACKOFF_MAX = timedelta(minutes=15)


class _FirewallaRateLimitedError(Exception):
    """Raised when the Firewalla API returns a rate-limit response."""

    def __init__(self, endpoint: str) -> None:
        """Initialize the error."""
        self.endpoint = endpoint
        super().__init__(endpoint)


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


def _traffic_window_minutes_from_entry(entry: ConfigEntry) -> int:
    """Resolve the configured recent-traffic window in minutes."""
    value = entry.options.get(
        CONF_TRAFFIC_WINDOW_MINUTES,
        entry.data.get(CONF_TRAFFIC_WINDOW_MINUTES, DEFAULT_TRAFFIC_WINDOW_MINUTES),
    )
    try:
        return int(value)
    except (TypeError, ValueError):
        return DEFAULT_TRAFFIC_WINDOW_MINUTES


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


def _build_rule_query(scope_type: str, scope_id: str | None) -> str | None:
    """Build a rule search query for the configured scope."""
    if scope_type == SCOPE_GROUP and scope_id:
        return f"box.group.id:{scope_id}"
    if scope_type == SCOPE_BOX and scope_id:
        return f"box.id:{scope_id}"
    return None


def _build_top_talkers_query(
    scope_type: str, scope_id: str | None, window_start: int
) -> str:
    """Build a flow query for top-talker aggregation."""
    return _build_flow_query(scope_type, scope_id, window_start)


def _device_key(gid: str | None, device_id: str) -> str:
    """Build a stable device identifier within an MSP scope."""
    return f"{gid or 'global'}::{device_id}"


def _build_network_bandwidth(
    known_networks: dict[str, dict[str, object]],
    recent_flows: list[dict[str, object]],
    window_seconds: int,
    window_minutes: int,
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
            "window_minutes": window_minutes,
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
                "window_minutes": window_minutes,
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
    network_bandwidth: dict[str, dict[str, object]],
    window_seconds: int,
    window_minutes: int,
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
        "window_minutes": window_minutes,
    }


def _build_box_bandwidth(
    recent_flows: list[dict[str, object]],
    window_seconds: int,
    window_minutes: int,
    boxes_by_gid: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    """Build per-box bandwidth stats from recent grouped flows."""
    box_bandwidth: dict[str, dict[str, object]] = {}
    known_box_gids = list(boxes_by_gid)

    for item in recent_flows:
        if item.get("block") is True or item.get("blocked") is True:
            continue

        gid = str(item.get("gid") or "").strip()
        if not gid and len(known_box_gids) == 1:
            gid = known_box_gids[0]
        if not gid:
            continue

        download_bytes = max(_safe_int(item.get("download")), 0)
        upload_bytes = max(_safe_int(item.get("upload")), 0)
        flow_count = max(_safe_int(item.get("count")), 1)
        box = boxes_by_gid.get(gid, {})
        current = box_bandwidth.setdefault(
            gid,
            {
                "gid": gid,
                "name": str(box.get("name") or gid).strip() or gid,
                "model": str(box.get("model") or "").strip() or None,
                "group_id": str(box.get("group") or "").strip() or None,
                "online": box.get("online"),
                "download_bytes": 0,
                "upload_bytes": 0,
                "download_mbps": 0.0,
                "upload_mbps": 0.0,
                "flow_count": 0,
                "window_seconds": window_seconds,
                "window_minutes": window_minutes,
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

    return box_bandwidth


def _build_top_talkers(
    flows: list[dict[str, object]],
    window_seconds: int,
    window_minutes: int,
    boxes_by_gid: dict[str, dict[str, object]],
    limit: int | None = DEFAULT_TOP_TALKERS_LIMIT,
) -> list[dict[str, object]]:
    """Aggregate top talkers from recent flow records."""
    top_talkers: dict[str, dict[str, object]] = {}

    for item in flows:
        if item.get("block") is True or item.get("blocked") is True:
            continue

        device = item.get("device")
        if not isinstance(device, dict):
            continue

        device_id = str(device.get("id") or "").strip()
        if not device_id:
            continue

        gid = str(item.get("gid") or "").strip()
        if not gid:
            continue

        box = boxes_by_gid.get(gid, {})
        key = _device_key(gid or None, device_id)
        download_bytes = max(_safe_int(item.get("download")), 0)
        upload_bytes = max(_safe_int(item.get("upload")), 0)
        flow_count = max(_safe_int(item.get("count")), 1)
        current = top_talkers.setdefault(
            key,
            {
                "device_id": device_id,
                "device_name": str(device.get("name") or device_id).strip() or device_id,
                "gid": gid,
                "box_name": str(box.get("name") or "").strip() or None,
                "box_model": str(box.get("model") or "").strip() or None,
                "network_id": None,
                "network_name": None,
                "download_bytes": 0,
                "upload_bytes": 0,
                "total_bytes": 0,
                "download_mbps": 0.0,
                "upload_mbps": 0.0,
                "flow_count": 0,
                "window_seconds": window_seconds,
                "window_minutes": window_minutes,
            },
        )

        network = item.get("network")
        if isinstance(network, dict):
            current["network_id"] = str(network.get("id") or "").strip() or None
            current["network_name"] = str(network.get("name") or "").strip() or None

        current["download_bytes"] = (
            _safe_int(current.get("download_bytes")) + download_bytes
        )
        current["upload_bytes"] = _safe_int(current.get("upload_bytes")) + upload_bytes
        current["total_bytes"] = _safe_int(current.get("total_bytes")) + download_bytes + upload_bytes
        current["flow_count"] = _safe_int(current.get("flow_count")) + flow_count
        current["download_mbps"] = _compute_rate_mbps(
            _safe_int(current.get("download_bytes")),
            window_seconds,
        )
        current["upload_mbps"] = _compute_rate_mbps(
            _safe_int(current.get("upload_bytes")),
            window_seconds,
        )

    results = sorted(
        top_talkers.values(),
        key=lambda item: (
            _safe_int(item.get("total_bytes")),
            _safe_int(item.get("download_bytes")),
            _safe_int(item.get("upload_bytes")),
            str(item.get("device_name") or ""),
        ),
        reverse=True,
    )
    if limit is None:
        return results
    return results[:limit]


def _empty_payload(
    scope_type: str,
    scope_id: str | None,
    boxes: list[dict[str, object]],
    capabilities: dict[str, bool],
    endpoint_errors: dict[str, str],
    window_seconds: int,
    window_minutes: int,
) -> dict[str, object]:
    """Build an empty coordinator payload for degraded startup/update states."""
    return {
        "scope": _build_scope_info(scope_type, scope_id, boxes),
        "capabilities": capabilities,
        "endpoint_errors": endpoint_errors,
        "boxes": boxes,
        "devices": [],
        "networks": {},
        "trends": {},
        "simple_stats": {},
        "top_stats": {},
        "rules": [],
        "device_traffic": [],
        "top_talkers": [],
        "bandwidth": {
            "download_bytes": 0,
            "upload_bytes": 0,
            "download_mbps": 0.0,
            "upload_mbps": 0.0,
            "flow_count": 0,
            "window_seconds": window_seconds,
            "window_minutes": window_minutes,
        },
        "box_bandwidth": {},
        "network_bandwidth": {},
    }


def _merge_endpoint_errors(
    current_data: dict[str, object],
    endpoint_errors: dict[str, str],
) -> dict[str, object]:
    """Return a copy of current data with updated endpoint error details."""
    merged = dict(current_data)
    current_errors = current_data.get("endpoint_errors", {})
    if not isinstance(current_errors, dict):
        current_errors = {}
    merged["endpoint_errors"] = {**current_errors, **endpoint_errors}
    return merged


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
        self.traffic_window_minutes = _traffic_window_minutes_from_entry(entry)
        self._endpoint_available: dict[str, bool] = {}
        self._rate_limited_until: datetime | None = None
        self._rate_limit_attempts = 0

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

    def _rate_limit_active(self, now: datetime) -> bool:
        """Return whether a rate-limit backoff window is currently active."""
        return self._rate_limited_until is not None and now < self._rate_limited_until

    def _activate_rate_limit_backoff(self, endpoint: str, now: datetime) -> None:
        """Increase the rate-limit backoff window."""
        self._rate_limit_attempts += 1
        delay_seconds = min(
            int(_RATE_LIMIT_BACKOFF_BASE.total_seconds()) * (2 ** (self._rate_limit_attempts - 1)),
            int(_RATE_LIMIT_BACKOFF_MAX.total_seconds()),
        )
        self._rate_limited_until = now + timedelta(seconds=delay_seconds)
        _LOGGER.warning(
            "Firewalla endpoint %s rate limited; backing off for %s seconds",
            endpoint,
            delay_seconds,
        )

    def _clear_rate_limit_backoff(self) -> None:
        """Clear any active rate-limit backoff after a successful refresh."""
        self._rate_limited_until = None
        self._rate_limit_attempts = 0

    def _update_endpoint_availability(
        self,
        endpoint: str,
        available: bool,
        error: str | None = None,
    ) -> None:
        """Track endpoint availability and only log state transitions."""
        previous = self._endpoint_available.get(endpoint)
        self._endpoint_available[endpoint] = available

        if available:
            if previous is False:
                _LOGGER.info("Firewalla endpoint %s recovered", endpoint)
            return

        if previous is False:
            return

        if error in OPTIONAL_ENDPOINT_ERRORS:
            _LOGGER.debug("Firewalla endpoint %s unavailable: %s", endpoint, error)
        else:
            _LOGGER.warning("Firewalla endpoint %s failed: %s", endpoint, error)

    async def _async_fetch_optional(self, endpoint: str, func, *args, **kwargs):
        """Fetch an optional endpoint and classify failures."""
        try:
            result = await func(*args, **kwargs)
        except FirewallaApiAuthError:
            raise
        except FirewallaApiError as err:
            error = str(err)
            self._update_endpoint_availability(endpoint, False, error)
            if error == "http_429":
                self._activate_rate_limit_backoff(endpoint, datetime.now(UTC))
                raise _FirewallaRateLimitedError(endpoint) from err
            return False, None, error
        self._update_endpoint_availability(endpoint, True)
        return True, result, None

    async def _async_update_data(self) -> dict[str, object]:
        """Fetch Firewalla data with graceful degradation."""
        now = datetime.now(UTC)
        window_seconds = self.traffic_window_minutes * 60
        capabilities: dict[str, bool] = {
            "boxes": False,
            "trends": False,
            "simple_stats": False,
            "top_stats": False,
            "rules": False,
            "devices": False,
            "grouped_flows": False,
            "top_talkers": False,
            "bandwidth": False,
            "box_bandwidth": False,
            "network_bandwidth": False,
        }
        endpoint_errors: dict[str, str] = {}
        boxes: list[dict[str, object]] = []

        if self._rate_limit_active(now):
            remaining_seconds = max(
                int((self._rate_limited_until - now).total_seconds()),
                1,
            )
            endpoint_errors["rate_limit"] = f"backoff_active_{remaining_seconds}s"
            _LOGGER.debug(
                "Firewalla rate-limit backoff active for %s more seconds",
                remaining_seconds,
            )
            if isinstance(self.data, dict):
                return _merge_endpoint_errors(self.data, endpoint_errors)
            return _empty_payload(
                self.scope_type,
                self.scope_id,
                boxes,
                capabilities,
                endpoint_errors,
                window_seconds,
                self.traffic_window_minutes,
            )

        try:
            now_ts = int(now.timestamp())
            window_start = now_ts - window_seconds
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

            rules: list[dict[str, object]] = []
            success, payload, error = await self._async_fetch_optional(
                "rules",
                self.client.async_get_rules,
                query=_build_rule_query(self.scope_type, self.scope_id),
            )
            if success:
                rules = payload if isinstance(payload, list) else []
                capabilities["rules"] = True
            elif error:
                endpoint_errors["rules"] = error

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

            boxes_by_gid = _box_map(boxes)
            known_networks = _build_known_networks(devices, boxes_by_gid)

            device_traffic: list[dict[str, object]] = []
            top_talkers: list[dict[str, object]] = []
            aggregated_flows: list[dict[str, object]] = []
            cursor: str | None = None
            while True:
                success, payload, error = await self._async_fetch_optional(
                    "flows",
                    self.client.async_get_flows,
                    query=_build_top_talkers_query(
                        self.scope_type, self.scope_id, window_start
                    ),
                    limit=500,
                    cursor=cursor,
                )
                if not success:
                    if error:
                        endpoint_errors["flows"] = error
                    break
                page_items = []
                next_cursor: str | None = None
                if isinstance(payload, tuple) and len(payload) == 2:
                    page_items, next_cursor = payload
                if isinstance(page_items, list):
                    aggregated_flows.extend(
                        item for item in page_items if isinstance(item, dict)
                    )
                if not next_cursor:
                    capabilities["top_talkers"] = True
                    break
                cursor = next_cursor

            if capabilities["top_talkers"]:
                device_traffic = _build_top_talkers(
                    aggregated_flows,
                    window_seconds,
                    self.traffic_window_minutes,
                    boxes_by_gid,
                    limit=None,
                )
                top_talkers = device_traffic[:DEFAULT_TOP_TALKERS_LIMIT]

            if not any(capabilities.values()):
                if endpoint_errors:
                    if all(
                        error in TEMPORARY_ENDPOINT_ERRORS
                        for error in endpoint_errors.values()
                        if error != "unsupported_scope_box"
                    ):
                        _LOGGER.warning(
                            "Firewalla API temporarily unavailable during refresh: %s",
                            ", ".join(
                                sorted(
                                    f"{key}={value}"
                                    for key, value in endpoint_errors.items()
                                )
                            ),
                        )
                        return _empty_payload(
                            self.scope_type,
                            self.scope_id,
                            boxes,
                            capabilities,
                            endpoint_errors,
                            window_seconds,
                            self.traffic_window_minutes,
                        )
                    raise UpdateFailed(
                        "No Firewalla endpoints available: "
                        + ", ".join(sorted(f"{k}={v}" for k, v in endpoint_errors.items()))
                    )
                raise UpdateFailed("No Firewalla data returned")

            box_bandwidth = (
                _build_box_bandwidth(
                    recent_flows,
                    window_seconds,
                    self.traffic_window_minutes,
                    boxes_by_gid,
                )
                if capabilities["grouped_flows"]
                else {}
            )
            capabilities["box_bandwidth"] = bool(box_bandwidth)
            network_bandwidth = (
                _build_network_bandwidth(
                    known_networks,
                    recent_flows,
                    window_seconds,
                    self.traffic_window_minutes,
                    boxes_by_gid,
                )
                if capabilities["grouped_flows"]
                else {}
            )
            capabilities["network_bandwidth"] = bool(network_bandwidth)

            bandwidth = (
                _aggregate_bandwidth(
                    network_bandwidth,
                    window_seconds,
                    self.traffic_window_minutes,
                )
                if capabilities["grouped_flows"]
                else {
                    "download_bytes": 0,
                    "upload_bytes": 0,
                    "download_mbps": 0.0,
                    "upload_mbps": 0.0,
                    "flow_count": 0,
                    "window_seconds": window_seconds,
                    "window_minutes": self.traffic_window_minutes,
                }
            )
            capabilities["bandwidth"] = capabilities["grouped_flows"]

            result = {
                "scope": _build_scope_info(self.scope_type, self.scope_id, boxes),
                "capabilities": capabilities,
                "endpoint_errors": endpoint_errors,
                "boxes": boxes,
                "devices": devices,
                "networks": known_networks,
                "trends": trends,
                "simple_stats": simple_stats,
                "top_stats": top_stats,
                "rules": rules,
                "device_traffic": device_traffic,
                "top_talkers": top_talkers,
                "bandwidth": bandwidth,
                "box_bandwidth": box_bandwidth,
                "network_bandwidth": network_bandwidth,
            }
            self._clear_rate_limit_backoff()
            return result
        except _FirewallaRateLimitedError as err:
            endpoint_errors[err.endpoint] = "http_429"
            if isinstance(self.data, dict):
                return _merge_endpoint_errors(self.data, endpoint_errors)
            return _empty_payload(
                self.scope_type,
                self.scope_id,
                boxes,
                capabilities,
                endpoint_errors,
                window_seconds,
                self.traffic_window_minutes,
            )
        except FirewallaApiAuthError as err:
            raise ConfigEntryAuthFailed from err
        except FirewallaApiError as err:
            raise UpdateFailed(str(err)) from err
