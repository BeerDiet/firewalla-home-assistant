"""API client for Firewalla MSP endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

from aiohttp import ClientError, ClientResponseError, ClientSession


class FirewallaApiError(Exception):
    """Base API error."""


class FirewallaApiAuthError(FirewallaApiError):
    """Authentication error."""


@dataclass(slots=True, frozen=True)
class TrendPoint:
    """A Firewalla trend point."""

    ts: int
    value: int

    @property
    def as_datetime(self) -> datetime:
        """Return the point timestamp in UTC."""
        return datetime.fromtimestamp(self.ts, UTC)


def normalize_base_url(raw_url: str) -> str:
    """Normalize user input into the Firewalla API base URL."""
    raw_value = raw_url.strip()
    if "://" not in raw_value:
        raw_value = f"https://{raw_value}"

    parsed = urlparse(raw_value)
    if not parsed.netloc:
        raise ValueError("invalid_url")

    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


class FirewallaApiClient:
    """Client for Firewalla MSP endpoints."""

    def __init__(
        self,
        session: ClientSession,
        base_url: str,
        token: str,
        *,
        verify_ssl: bool,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._base_url = normalize_base_url(base_url)
        self._token = token.strip()
        self._verify_ssl = verify_ssl

    @property
    def base_url(self) -> str:
        """Return the normalized base URL."""
        return self._base_url

    async def _async_get_json(
        self, path: str, *, params: dict[str, str] | None = None
    ) -> object:
        """Issue a GET request and decode JSON."""
        try:
            response = await self._session.get(
                f"{self._base_url}{path}",
                params=params,
                headers={"Authorization": f"Token {self._token}"},
                ssl=self._verify_ssl,
            )
            response.raise_for_status()
        except ClientResponseError as err:
            if err.status == 401:
                raise FirewallaApiAuthError("invalid_auth") from err
            raise FirewallaApiError(f"http_{err.status}") from err
        except ClientError as err:
            raise FirewallaApiError("cannot_connect") from err

        return await response.json()

    async def async_get_trend(
        self, trend_type: str, group: str | None = None
    ) -> list[TrendPoint]:
        """Fetch a trend series."""
        params: dict[str, str] = {}
        if group:
            params["group"] = group

        payload = await self._async_get_json(f"/v2/trends/{trend_type}", params=params)
        if not isinstance(payload, list):
            raise FirewallaApiError("invalid_response")

        points: list[TrendPoint] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            try:
                ts = int(item["ts"])
            except (KeyError, TypeError, ValueError):
                continue
            try:
                value = int(item.get("value", 0))
            except (TypeError, ValueError):
                value = 0
            points.append(TrendPoint(ts=ts, value=value))

        points.sort(key=lambda point: point.ts, reverse=True)
        return points

    async def async_get_simple_stats(self, group: str | None = None) -> dict[str, int]:
        """Fetch simple statistics."""
        params: dict[str, str] = {}
        if group:
            params["group"] = group

        payload = await self._async_get_json("/v2/stats/simple", params=params)
        if not isinstance(payload, dict):
            raise FirewallaApiError("invalid_response")

        stats: dict[str, int] = {}
        for key in ("onlineBoxes", "offlineBoxes", "alarms", "rules"):
            try:
                stats[key] = int(payload[key])
            except (KeyError, TypeError, ValueError):
                continue

        return stats

    async def async_get_statistics(
        self,
        stats_type: str,
        *,
        group: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, object]]:
        """Fetch ordered statistics data."""
        params: dict[str, str] = {"limit": str(limit)}
        if group:
            params["group"] = group

        payload = await self._async_get_json(f"/v2/stats/{stats_type}", params=params)
        if not isinstance(payload, list):
            raise FirewallaApiError("invalid_response")

        stats: list[dict[str, object]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            meta = item.get("meta", {})
            value = item.get("value")
            if not isinstance(meta, dict):
                meta = {}
            try:
                parsed_value = int(value)
            except (TypeError, ValueError):
                continue

            stats.append(
                {
                    "meta": {
                        str(key): str(val)
                        for key, val in meta.items()
                        if val is not None
                    },
                    "value": parsed_value,
                }
            )

        return stats

    async def async_get_boxes(
        self, *, group: str | None = None
    ) -> list[dict[str, object]]:
        """Fetch boxes."""
        params: dict[str, str] = {}
        if group:
            params["group"] = group

        payload = await self._async_get_json("/v2/boxes", params=params)
        if not isinstance(payload, list):
            raise FirewallaApiError("invalid_response")
        return [box for box in payload if isinstance(box, dict)]

    async def async_get_devices(
        self, *, group: str | None = None, box: str | None = None
    ) -> list[dict[str, object]]:
        """Fetch devices."""
        params: dict[str, str] = {}
        if group:
            params["group"] = group
        if box:
            params["box"] = box

        payload = await self._async_get_json("/v2/devices", params=params)
        if isinstance(payload, list):
            devices = payload
        elif isinstance(payload, dict):
            devices = payload.get("value", [])
        else:
            raise FirewallaApiError("invalid_response")

        if not isinstance(devices, list):
            raise FirewallaApiError("invalid_response")
        return [device for device in devices if isinstance(device, dict)]

    async def async_get_grouped_flows(
        self,
        *,
        query: str | None = None,
        group_by: str = "network",
        limit: int = 100,
    ) -> list[dict[str, object]]:
        """Fetch grouped flow records."""
        params: dict[str, str] = {"limit": str(limit), "groupBy": group_by}
        if query:
            params["query"] = query

        payload = await self._async_get_json("/v2/flows", params=params)
        if not isinstance(payload, dict):
            raise FirewallaApiError("invalid_response")

        results = payload.get("results", [])
        if not isinstance(results, list):
            raise FirewallaApiError("invalid_response")
        return [result for result in results if isinstance(result, dict)]

    async def async_get_flows(
        self,
        *,
        query: str | None = None,
        limit: int = 500,
        cursor: str | None = None,
    ) -> tuple[list[dict[str, object]], str | None]:
        """Fetch flow records."""
        params: dict[str, str] = {"limit": str(limit)}
        if query:
            params["query"] = query
        if cursor:
            params["cursor"] = cursor

        payload = await self._async_get_json("/v2/flows", params=params)
        if not isinstance(payload, dict):
            raise FirewallaApiError("invalid_response")

        items = payload.get("results", [])
        next_cursor = payload.get("next_cursor")
        if not isinstance(items, list):
            raise FirewallaApiError("invalid_response")
        if next_cursor is not None and not isinstance(next_cursor, str):
            next_cursor = None

        return items, next_cursor
