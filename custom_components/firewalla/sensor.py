"""Sensor platform for Firewalla."""

from __future__ import annotations

import re
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfDataRate, UnitOfInformation, UnitOfTime
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_API_DAILY_REQUEST_LIMIT,
    DEFAULT_API_DAILY_REQUEST_LIMIT,
    DEFAULT_RECENT_POINTS,
    DOMAIN,
)


def _slugify(value: str) -> str:
    """Convert an arbitrary string into an entity-id-safe slug fragment."""
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "group"


def _bytes_to_gigabytes(value: int | float) -> float:
    """Convert raw bytes to decimal gigabytes for human-friendly display."""
    return round(float(value) / 1_000_000_000, 2)


@dataclass(frozen=True, kw_only=True)
class FirewallaTrendSensorDescription(SensorEntityDescription):
    """Describe a Firewalla sensor."""

    trend_type: str
    source: str = "trends"


@dataclass(frozen=True, kw_only=True)
class FirewallaEntrySensorDescription(SensorEntityDescription):
    """Describe a Firewalla entry-level sensor."""

    metric: str


SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    FirewallaTrendSensorDescription(
        key="flows",
        name="Blocked Flows",
        icon="mdi:shield-outline",
        state_class=SensorStateClass.MEASUREMENT,
        trend_type="flows",
    ),
    FirewallaTrendSensorDescription(
        key="alarms",
        name="Alarms",
        icon="mdi:alarm-light-outline",
        state_class=SensorStateClass.MEASUREMENT,
        trend_type="alarms",
    ),
    FirewallaTrendSensorDescription(
        key="rules",
        name="Rule Activity",
        icon="mdi:playlist-check",
        state_class=SensorStateClass.MEASUREMENT,
        trend_type="rules",
    ),
    FirewallaTrendSensorDescription(
        key="online_boxes",
        name="Online Boxes",
        icon="mdi:router-network",
        state_class=SensorStateClass.MEASUREMENT,
        trend_type="onlineBoxes",
        source="simple_stats",
    ),
    FirewallaTrendSensorDescription(
        key="offline_boxes",
        name="Offline Boxes",
        icon="mdi:lan-disconnect",
        state_class=SensorStateClass.MEASUREMENT,
        trend_type="offlineBoxes",
        source="simple_stats",
    ),
    FirewallaTrendSensorDescription(
        key="current_alarms",
        name="Current Alarms",
        icon="mdi:alarm-light",
        state_class=SensorStateClass.MEASUREMENT,
        trend_type="alarms",
        source="simple_stats",
    ),
    FirewallaTrendSensorDescription(
        key="current_rules",
        name="Current Rules",
        icon="mdi:shield-check-outline",
        state_class=SensorStateClass.MEASUREMENT,
        trend_type="rules",
        source="simple_stats",
    ),
    FirewallaTrendSensorDescription(
        key="top_box_blocked_flows",
        name="Top Box Blocked Flows",
        icon="mdi:counter",
        state_class=SensorStateClass.MEASUREMENT,
        trend_type="topBoxesByBlockedFlows",
        source="top_stats",
    ),
    FirewallaTrendSensorDescription(
        key="top_box_security_alarms",
        name="Top Box Security Alarms",
        icon="mdi:counter",
        state_class=SensorStateClass.MEASUREMENT,
        trend_type="topBoxesBySecurityAlarms",
        source="top_stats",
    ),
    FirewallaTrendSensorDescription(
        key="top_region_blocked_flows",
        name="Top Region Blocked Flows",
        icon="mdi:counter",
        state_class=SensorStateClass.MEASUREMENT,
        trend_type="topRegionsByBlockedFlows",
        source="top_stats",
    ),
    FirewallaTrendSensorDescription(
        key="download_last_5m",
        name="Download Recent Volume",
        icon="mdi:download-network-outline",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
        trend_type="download_bytes",
        source="bandwidth",
    ),
    FirewallaTrendSensorDescription(
        key="upload_last_5m",
        name="Upload Recent Volume",
        icon="mdi:upload-network-outline",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
        trend_type="upload_bytes",
        source="bandwidth",
    ),
    FirewallaTrendSensorDescription(
        key="download_mbps",
        name="Download Mbps",
        icon="mdi:speedometer",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        trend_type="download_mbps",
        source="bandwidth",
    ),
    FirewallaTrendSensorDescription(
        key="upload_mbps",
        name="Upload Mbps",
        icon="mdi:speedometer-medium",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        trend_type="upload_mbps",
        source="bandwidth",
    ),
    FirewallaTrendSensorDescription(
        key="api_calls_today",
        name="Current API Calls Today",
        icon="mdi:api",
        state_class=SensorStateClass.TOTAL,
        trend_type="daily_total",
        source="api_calls",
    ),
)

ENTRY_SENSOR_DESCRIPTIONS: tuple[FirewallaEntrySensorDescription, ...] = (
    FirewallaEntrySensorDescription(
        key="api_daily_request_limit",
        name="Daily API Usage Limit",
        icon="mdi:counter",
        state_class=SensorStateClass.MEASUREMENT,
        metric="api_daily_request_limit",
    ),
    FirewallaEntrySensorDescription(
        key="current_scan_interval",
        name="Current Scan Interval",
        icon="mdi:timer-outline",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        metric="current_scan_interval",
    ),
)

SENSOR_DESCRIPTIONS = SENSOR_DESCRIPTIONS + ENTRY_SENSOR_DESCRIPTIONS

_SOURCE_CAPABILITY = {
    "trends": "trends",
    "simple_stats": "simple_stats",
    "top_stats": "top_stats",
    "bandwidth": "bandwidth",
}

PARALLEL_UPDATES = 0
_BANDWIDTH_SENSOR_METRICS = (
    (
        "download_bytes",
        "Download Recent Volume",
        "mdi:download-network-outline",
        UnitOfInformation.GIGABYTES,
        SensorDeviceClass.DATA_SIZE,
    ),
    (
        "upload_bytes",
        "Upload Recent Volume",
        "mdi:upload-network-outline",
        UnitOfInformation.GIGABYTES,
        SensorDeviceClass.DATA_SIZE,
    ),
    (
        "download_mbps",
        "Download Mbps",
        "mdi:speedometer",
        UnitOfDataRate.MEGABITS_PER_SECOND,
        SensorDeviceClass.DATA_RATE,
    ),
    (
        "upload_mbps",
        "Upload Mbps",
        "mdi:speedometer-medium",
        UnitOfDataRate.MEGABITS_PER_SECOND,
        SensorDeviceClass.DATA_RATE,
    ),
)
_PER_BOX_SENSOR_KEYS = {
    "flows",
    "alarms",
    "current_alarms",
}
_GLOBAL_SENSOR_KEYS = {
    "flows",
    "alarms",
    "online_boxes",
    "offline_boxes",
    "download_last_5m",
    "upload_last_5m",
    "download_mbps",
    "upload_mbps",
    "top_region_blocked_flows",
    "current_rules",
    "rules",
    "api_calls_today",
    "api_daily_request_limit",
    "current_scan_interval",
}


async def async_setup_entry(hass, entry: ConfigEntry, async_add_entities) -> None:
    """Set up Firewalla sensors."""
    coordinator = entry.runtime_data

    entities = [
        (
            FirewallaEntrySensor(coordinator, entry, description)
            if isinstance(description, FirewallaEntrySensorDescription)
            else FirewallaTrendSensor(coordinator, entry, description)
        )
        for description in SENSOR_DESCRIPTIONS
        if description.key in _GLOBAL_SENSOR_KEYS
    ]
    boxes = coordinator.data.get("boxes", [])
    if not isinstance(boxes, list):
        boxes = []

    for box in boxes:
        if not isinstance(box, dict):
            continue
        box_gid = str(box.get("gid") or "").strip()
        box_name = str(box.get("name") or box_gid).strip()
        if not box_gid or not box_name:
            continue
        entities.extend(
            FirewallaPerBoxSensor(coordinator, entry, box_gid, box_name, description)
            for description in SENSOR_DESCRIPTIONS
            if description.key in _PER_BOX_SENSOR_KEYS
        )
        entities.append(FirewallaPerBoxTopTalkersSensor(coordinator, entry, box_gid, box_name))

    network_bandwidth = coordinator.data.get("network_bandwidth", {})
    if isinstance(network_bandwidth, dict):
        for network_key, network in network_bandwidth.items():
            if not isinstance(network, dict):
                continue
            box_gid = str(network.get("gid") or "").strip()
            network_name = str(network.get("display_name") or network.get("name") or "").strip()
            if not network_key or not network_name or not box_gid:
                continue
            entities.extend(
                FirewallaPerBoxNetworkBandwidthSensor(
                    coordinator,
                    entry,
                    box_gid,
                    network_key,
                    network_name,
                    metric_key,
                    metric_name,
                    icon,
                    unit,
                    device_class,
                )
                for metric_key, metric_name, icon, unit, device_class in _BANDWIDTH_SENSOR_METRICS
            )

    async_add_entities(entities)


class FirewallaBaseSensor(CoordinatorEntity, SensorEntity):
    """Shared Firewalla sensor behavior."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the base sensor."""
        super().__init__(coordinator)
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        """Return device metadata."""
        scope = self.coordinator.data.get("scope", {})
        if not isinstance(scope, dict):
            scope = {}
        label = str(scope.get("label") or self.coordinator.scope_type).strip()
        return DeviceInfo(
            identifiers={
                (
                    DOMAIN,
                    f"{self._entry.entry_id}_{self.coordinator.scope_type}_{self.coordinator.scope_id or 'global'}",
                )
            },
            name=f"Firewalla {label}",
            manufacturer="Firewalla",
            model="MSP API",
            configuration_url=self.coordinator.client.base_url,
        )

    def _scope_attributes(self) -> dict[str, object]:
        """Return common scope metadata."""
        scope = self.coordinator.data.get("scope", {})
        if isinstance(scope, dict):
            return {
                "scope_type": scope.get("type"),
                "scope_id": scope.get("id"),
                "scope_label": scope.get("label"),
            }
        return {
            "scope_type": self.coordinator.scope_type,
            "scope_id": self.coordinator.scope_id,
            "scope_label": self.coordinator.scope_type,
        }


def _api_daily_request_limit_from_entry(entry: ConfigEntry) -> int:
    """Return the configured daily API request limit for the entry."""
    options = getattr(entry, "options", {})
    data = getattr(entry, "data", {})
    if not isinstance(options, dict):
        options = {}
    if not isinstance(data, dict):
        data = {}
    value = options.get(
        CONF_API_DAILY_REQUEST_LIMIT,
        data.get(CONF_API_DAILY_REQUEST_LIMIT, DEFAULT_API_DAILY_REQUEST_LIMIT),
    )
    try:
        return max(int(value), 1)
    except (TypeError, ValueError):
        return DEFAULT_API_DAILY_REQUEST_LIMIT


class FirewallaPerBoxTopTalkersSensor(FirewallaBaseSensor):
    """Representation of a per-box top talkers sensor."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        box_gid: str,
        box_name: str,
    ) -> None:
        """Initialize the top talkers sensor."""
        super().__init__(coordinator, entry)
        self._box_gid = box_gid
        self._box_name = box_name
        self._attr_name = "Top Talkers"
        self._attr_unique_id = f"{entry.entry_id}_box_{box_gid}_top_talkers"
        self._attr_suggested_object_id = f"firewalla_{_slugify(box_name)}_top_talkers"
        self._attr_icon = "mdi:account-network-outline"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def device_info(self) -> DeviceInfo:
        """Return box metadata."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_box_{self._box_gid}")},
            name=f"Firewalla {self._box_name}",
            manufacturer="Firewalla",
            model="MSP API",
            configuration_url=self.coordinator.client.base_url,
        )

    def _device_traffic(self) -> list[dict[str, object]]:
        """Return aggregated traffic rows for the box."""
        device_traffic = self.coordinator.data.get("device_traffic", [])
        if not isinstance(device_traffic, list):
            return []
        return [
            item
            for item in device_traffic
            if isinstance(item, dict)
            and str(item.get("gid") or "").strip() == self._box_gid
        ]

    def _ranked_devices(self, metric: str) -> list[dict[str, object]]:
        """Return ranked traffic rows for the box by the given metric."""
        ranked = sorted(
            self._device_traffic(),
            key=lambda item: (
                item.get(metric, 0) if isinstance(item.get(metric), (int, float)) else 0,
                str(item.get("device_name") or ""),
            ),
            reverse=True,
        )
        return [
            {
                "rank": index,
                "device_id": item.get("device_id"),
                "device_name": item.get("device_name"),
                "network_id": item.get("network_id"),
                "network_name": item.get("network_name"),
                "box_name": item.get("box_name"),
                "bytes": item.get(metric, 0),
                "window_minutes": item.get("window_minutes"),
                "window_seconds": item.get("window_seconds"),
            }
            for index, item in enumerate(ranked, start=1)
        ]

    @property
    def available(self) -> bool:
        """Return whether the sensor is available."""
        capabilities = self.coordinator.data.get("capabilities", {})
        if not isinstance(capabilities, dict):
            return False
        return bool(capabilities.get("top_talkers"))

    @property
    def native_value(self) -> int | float | None:
        """Return the number of ranked devices for the box."""
        if not self.available:
            return None
        return len(self._device_traffic())

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return ranked per-box download and upload lists."""
        attrs = self._scope_attributes()
        traffic = self._device_traffic()
        first = traffic[0] if traffic else {}
        return {
            "source": "top_talkers",
            "box_gid": self._box_gid,
            "box_name": self._box_name,
            "download_ranked_devices": self._ranked_devices("download_bytes"),
            "upload_ranked_devices": self._ranked_devices("upload_bytes"),
            "window_minutes": first.get("window_minutes"),
            "window_seconds": first.get("window_seconds"),
            **attrs,
        }


class FirewallaTrendSensor(FirewallaBaseSensor):
    """Representation of a Firewalla sensor."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        description: FirewallaTrendSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self.entity_description = description
        scope_fragment = self.coordinator.scope_id or "global"
        self._attr_unique_id = (
            f"{entry.entry_id}_{description.key}_{self.coordinator.scope_type}_{scope_fragment}"
        )
        if self.coordinator.scope_id:
            suffix = f"{self.coordinator.scope_type}_{_slugify(self.coordinator.scope_id)}"
            self._attr_suggested_object_id = f"firewalla_{description.key}_{suffix}"
        else:
            self._attr_suggested_object_id = f"firewalla_{description.key}"

    @property
    def available(self) -> bool:
        """Return whether the sensor is available."""
        if self.entity_description.source == "api_calls":
            api_calls = self.coordinator.data.get("api_calls", {})
            return isinstance(api_calls, dict)

        capabilities = self.coordinator.data.get("capabilities", {})
        if not isinstance(capabilities, dict):
            return False
        return bool(capabilities.get(_SOURCE_CAPABILITY[self.entity_description.source]))

    @property
    def native_value(self) -> int | float | None:
        """Return the current sensor state."""
        if not self.available:
            return None

        if self.entity_description.source == "simple_stats":
            simple_stats = self.coordinator.data.get("simple_stats", {})
            if not isinstance(simple_stats, dict):
                return None
            value = simple_stats.get(self.entity_description.trend_type)
            return value if isinstance(value, int) else None

        if self.entity_description.source == "top_stats":
            top_stats = self.coordinator.data.get("top_stats", {})
            if not isinstance(top_stats, dict):
                return None
            results = top_stats.get(self.entity_description.trend_type, [])
            if not isinstance(results, list) or not results:
                return 0
            leader = results[0]
            value = leader.get("value") if isinstance(leader, dict) else None
            return value if isinstance(value, int) else 0

        if self.entity_description.source == "bandwidth":
            bandwidth = self.coordinator.data.get("bandwidth", {})
            if not isinstance(bandwidth, dict):
                return None
            value = bandwidth.get(self.entity_description.trend_type)
            if not isinstance(value, (int, float)):
                return 0
            if self.entity_description.trend_type.endswith("_bytes"):
                return _bytes_to_gigabytes(value)
            return value

        if self.entity_description.source == "api_calls":
            api_calls = self.coordinator.data.get("api_calls", {})
            if not isinstance(api_calls, dict):
                return 0
            value = api_calls.get("daily_total")
            return value if isinstance(value, int) else 0

        trends = self.coordinator.data.get("trends", {})
        if not isinstance(trends, dict):
            return None
        series = trends.get(self.entity_description.trend_type, [])
        if not isinstance(series, list) or not series:
            return 0
        latest = series[0]
        return latest.value if hasattr(latest, "value") else 0

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return sensor attributes."""
        attrs = self._scope_attributes()

        if self.entity_description.source == "simple_stats":
            return {"source": "simple_stats", **attrs}

        if self.entity_description.source == "top_stats":
            top_stats = self.coordinator.data.get("top_stats", {})
            if not isinstance(top_stats, dict):
                return {"source": "top_stats", **attrs}
            results = top_stats.get(self.entity_description.trend_type, [])
            if not isinstance(results, list) or not results:
                return {
                    "source": "top_stats",
                    "stats_type": self.entity_description.trend_type,
                    "results": [],
                    **attrs,
                }

            leader = results[0]
            leader_meta = leader.get("meta", {}) if isinstance(leader, dict) else {}
            top_attrs: dict[str, object] = {
                "source": "top_stats",
                "stats_type": self.entity_description.trend_type,
                "results": results,
                **attrs,
            }
            if isinstance(leader_meta, dict):
                top_attrs["leader_name"] = leader_meta.get("name")
                top_attrs["leader_model"] = leader_meta.get("model")
                top_attrs["leader_gid"] = leader_meta.get("gid")
                top_attrs["leader_region"] = leader_meta.get("region")
            return top_attrs

        if self.entity_description.source == "bandwidth":
            bandwidth = self.coordinator.data.get("bandwidth", {})
            if not isinstance(bandwidth, dict):
                return {"source": "grouped_flows", **attrs}
            return {
                "source": "grouped_flows",
                "raw_download_bytes": bandwidth.get("download_bytes"),
                "raw_upload_bytes": bandwidth.get("upload_bytes"),
                "window_minutes": bandwidth.get("window_minutes"),
                "window_seconds": bandwidth.get("window_seconds"),
                "flow_count": bandwidth.get("flow_count"),
                **attrs,
            }

        if self.entity_description.source == "api_calls":
            api_calls = self.coordinator.data.get("api_calls", {})
            if not isinstance(api_calls, dict):
                return {"source": "api_calls", **attrs}
            return {"source": "api_calls", **api_calls, **attrs}

        trends = self.coordinator.data.get("trends", {})
        if not isinstance(trends, dict):
            return {"source": "trends", "trend_type": self.entity_description.trend_type, **attrs}
        series = trends.get(self.entity_description.trend_type, [])
        if not isinstance(series, list) or not series:
            return {"source": "trends", "trend_type": self.entity_description.trend_type, **attrs}

        latest = series[0]
        trend_attrs: dict[str, object] = {
            "source": "trends",
            "trend_type": self.entity_description.trend_type,
            "latest_timestamp": latest.as_datetime.isoformat(),
            "recent_points": [
                {"timestamp": point.as_datetime.isoformat(), "value": point.value}
                for point in series[:DEFAULT_RECENT_POINTS]
            ],
            **attrs,
        }

        if len(series) > 1:
            trend_attrs["previous_value"] = series[1].value
            trend_attrs["previous_timestamp"] = series[1].as_datetime.isoformat()

        return trend_attrs

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated coordinator data."""
        self.async_write_ha_state()


class FirewallaEntrySensor(FirewallaBaseSensor):
    """Representation of a Firewalla entry-level sensor."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        description: FirewallaEntrySensorDescription,
    ) -> None:
        """Initialize the entry sensor."""
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_name = description.name
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_suggested_object_id = f"firewalla_{_slugify(description.key)}"

    @property
    def available(self) -> bool:
        """Return whether the sensor is available."""
        return True

    @property
    def native_value(self) -> int | None:
        """Return the current sensor state."""
        metric = self.entity_description.metric
        if metric == "api_daily_request_limit":
            return _api_daily_request_limit_from_entry(self._entry)
        if metric == "current_scan_interval":
            return int(getattr(self.coordinator, "effective_scan_seconds", 0) or 0)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return entry sensor attributes."""
        attrs = self._scope_attributes()
        api_calls = self.coordinator.data.get("api_calls", {})
        if not isinstance(api_calls, dict):
            api_calls = {}
        return {
            "source": "entry_settings",
            "metric": self.entity_description.metric,
            **api_calls,
            **attrs,
        }


class FirewallaPerBoxSensor(FirewallaBaseSensor):
    """Representation of a per-box Firewalla sensor."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        box_gid: str,
        box_name: str,
        description: FirewallaTrendSensorDescription,
    ) -> None:
        """Initialize the per-box sensor."""
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._box_gid = box_gid
        self._box_name = box_name
        self._attr_name = description.name
        self._attr_unique_id = f"{entry.entry_id}_{description.key}_box_{box_gid}"
        self._attr_suggested_object_id = f"firewalla_{_slugify(box_name)}_{description.key}"

    def _box(self) -> dict[str, object]:
        """Return the current box metadata."""
        boxes = self.coordinator.data.get("boxes", [])
        if isinstance(boxes, list):
            for box in boxes:
                if not isinstance(box, dict):
                    continue
                if str(box.get("gid") or "").strip() == self._box_gid:
                    return box

        box_bandwidth = self.coordinator.data.get("box_bandwidth", {})
        if isinstance(box_bandwidth, dict):
            box = box_bandwidth.get(self._box_gid, {})
            if isinstance(box, dict):
                return box

        return {}

    def _box_top_stat_value(self, stats_type: str) -> int | None:
        """Return a per-box top-stat value."""
        top_stats = self.coordinator.data.get("top_stats", {})
        if not isinstance(top_stats, dict):
            return None

        results = top_stats.get(stats_type, [])
        if not isinstance(results, list):
            return None

        for result in results:
            if not isinstance(result, dict):
                continue
            meta = result.get("meta", {})
            if not isinstance(meta, dict):
                continue
            if str(meta.get("gid") or "").strip() != self._box_gid:
                continue
            value = result.get("value")
            return value if isinstance(value, int) else 0

        return 0

    @property
    def device_info(self) -> DeviceInfo:
        """Return box device metadata."""
        box = self._box()
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_box_{self._box_gid}")},
            name=f"Firewalla {box.get('name') or self._box_name}",
            manufacturer="Firewalla",
            model=str(box.get("model") or "MSP API"),
            configuration_url=self.coordinator.client.base_url,
        )

    @property
    def available(self) -> bool:
        """Return whether the sensor is available."""
        capabilities = self.coordinator.data.get("capabilities", {})
        if not isinstance(capabilities, dict):
            return False

        key = self.entity_description.key
        if key in {
            "flows",
            "alarms",
            "current_alarms",
            "top_box_blocked_flows",
            "top_box_security_alarms",
        }:
            return bool(capabilities.get("top_stats"))
        return False

    @property
    def native_value(self) -> int | float | None:
        """Return the sensor state."""
        if not self.available:
            return None

        key = self.entity_description.key
        if key in {"flows", "top_box_blocked_flows"}:
            return self._box_top_stat_value("topBoxesByBlockedFlows")

        if key in {"alarms", "current_alarms", "top_box_security_alarms"}:
            return self._box_top_stat_value("topBoxesBySecurityAlarms")

        return None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return box sensor attributes."""
        attrs = self._scope_attributes()
        box = self._box()
        box_attrs = {
            "box_gid": self._box_gid,
            "box_name": box.get("name") or self._box_name,
            "box_model": box.get("model"),
            "box_online": box.get("online"),
            **attrs,
        }

        key = self.entity_description.key
        if key in {"flows", "top_box_blocked_flows"}:
            return {"source": "top_stats", "stats_type": "topBoxesByBlockedFlows", **box_attrs}

        if key in {"alarms", "current_alarms", "top_box_security_alarms"}:
            return {"source": "top_stats", "stats_type": "topBoxesBySecurityAlarms", **box_attrs}

        return {"source": "unsupported_box_metric", **box_attrs}

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated coordinator data."""
        self.async_write_ha_state()


class FirewallaPerBoxNetworkBandwidthSensor(FirewallaBaseSensor):
    """Representation of a per-network bandwidth sensor attached to a box device."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        box_gid: str,
        network_key: str,
        network_name: str,
        metric_key: str,
        metric_name: str,
        icon: str,
        unit,
        device_class,
    ) -> None:
        """Initialize the per-box network sensor."""
        super().__init__(coordinator, entry)
        self._box_gid = box_gid
        self._network_key = network_key
        self._network_name = network_name
        self._metric_key = metric_key
        self._attr_name = f"{network_name} {metric_name}"
        self._attr_unique_id = f"{entry.entry_id}_box_{box_gid}_network_{network_key}_{metric_key}"
        self._attr_suggested_object_id = (
            f"firewalla_{_slugify(self._box_gid)}_{_slugify(network_name)}_{metric_key}"
        )
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def device_info(self) -> DeviceInfo:
        """Return parent box device metadata."""
        boxes = self.coordinator.data.get("boxes", [])
        box_name = self._box_gid
        box_model = "MSP API"
        if isinstance(boxes, list):
            for box in boxes:
                if not isinstance(box, dict):
                    continue
                if str(box.get("gid") or "").strip() != self._box_gid:
                    continue
                box_name = str(box.get("name") or self._box_gid)
                box_model = str(box.get("model") or "MSP API")
                break

        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_box_{self._box_gid}")},
            name=f"Firewalla {box_name}",
            manufacturer="Firewalla",
            model=box_model,
            configuration_url=self.coordinator.client.base_url,
        )

    @property
    def available(self) -> bool:
        """Return whether the sensor is available."""
        capabilities = self.coordinator.data.get("capabilities", {})
        if not isinstance(capabilities, dict):
            return False
        return bool(capabilities.get("network_bandwidth"))

    @property
    def native_value(self) -> int | float | None:
        """Return the sensor state."""
        if not self.available:
            return None
        network_bandwidth = self.coordinator.data.get("network_bandwidth", {})
        if not isinstance(network_bandwidth, dict):
            return None
        network = network_bandwidth.get(self._network_key, {})
        if not isinstance(network, dict):
            return 0
        value = network.get(self._metric_key)
        if not isinstance(value, (int, float)):
            return 0
        if self._metric_key.endswith("_bytes"):
            return _bytes_to_gigabytes(value)
        return value

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return network metadata."""
        attrs = self._scope_attributes()
        network_bandwidth = self.coordinator.data.get("network_bandwidth", {})
        if not isinstance(network_bandwidth, dict):
            return {"source": "grouped_flows_by_network", **attrs}
        network = network_bandwidth.get(self._network_key, {})
        if not isinstance(network, dict):
            return {
                "source": "grouped_flows_by_network",
                "network_key": self._network_key,
                "network_name": self._network_name,
                "box_gid": self._box_gid,
                **attrs,
            }
        return {
            "source": "grouped_flows_by_network",
            "network_key": self._network_key,
            "network_id": network.get("id"),
            "network_name": network.get("display_name") or network.get("name"),
            "network_type": network.get("type"),
            "box_gid": self._box_gid,
            "box_name": network.get("box_name"),
            "raw_download_bytes": network.get("download_bytes"),
            "raw_upload_bytes": network.get("upload_bytes"),
            "flow_count": network.get("flow_count"),
            "window_minutes": network.get("window_minutes"),
            "window_seconds": network.get("window_seconds"),
            **attrs,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated coordinator data."""
        self.async_write_ha_state()
