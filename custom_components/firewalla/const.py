"""Constants for the Firewalla integration."""

import json
from datetime import timedelta
from pathlib import Path
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "firewalla"
NAME: Final = "Firewalla"
INTEGRATION_VERSION: Final = str(
    json.loads(Path(__file__).with_name("manifest.json").read_text(encoding="utf-8"))[
        "version"
    ]
)
DIAGNOSTICS_VERSION: Final = 1

CONF_BASE_URL = "base_url"
CONF_GROUP = "group"
CONF_SCOPE_ID = "scope_id"
CONF_SCOPE_TYPE = "scope_type"
CONF_TOKEN = "token"
CONF_TRAFFIC_WINDOW_MINUTES = "traffic_window_minutes"
CONF_VERIFY_SSL = "verify_ssl"
CONF_SCAN_INTERVAL = "scan_interval"

SCOPE_GLOBAL: Final = "global"
SCOPE_GROUP: Final = "group"
SCOPE_BOX: Final = "box"
SCOPE_TYPES: Final = (SCOPE_GLOBAL, SCOPE_GROUP, SCOPE_BOX)

DEFAULT_SCAN_INTERVAL = timedelta(minutes=1)
DEFAULT_VERIFY_SSL = True
DEFAULT_RECENT_POINTS = 7
DEFAULT_STATS_LIMIT = 5
DEFAULT_TRAFFIC_WINDOW_MINUTES: Final = 15
TRAFFIC_WINDOW_MINUTES_OPTIONS: Final = (1, 5, 15, 30)

OPTIONAL_ENDPOINT_ERRORS: Final = frozenset({"http_400", "http_403", "http_404"})

PLATFORMS: Final = [Platform.SENSOR]

TREND_TYPES: tuple[str, ...] = ("flows", "alarms", "rules")
TOP_STAT_TYPES: tuple[str, ...] = (
    "topBoxesByBlockedFlows",
    "topBoxesBySecurityAlarms",
    "topRegionsByBlockedFlows",
)
