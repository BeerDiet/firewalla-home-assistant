"""Tests for the Firewalla API client."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aiohttp import ClientError, ClientResponseError

from custom_components.firewalla.api import (
    FirewallaApiAuthError,
    FirewallaApiClient,
    FirewallaApiError,
    TrendPoint,
    normalize_base_url,
)


class MockResponse:
    """Mock aiohttp response."""

    def __init__(self, payload, *, status: int = 200) -> None:
        self._payload = payload
        self.status = status

    def raise_for_status(self) -> None:
        """Raise status error when needed."""
        if self.status >= 400:
            raise ClientResponseError(None, (), status=self.status)

    async def json(self):
        """Return JSON payload."""
        return self._payload


class MockSession:
    """Mock aiohttp session."""

    def __init__(self, response=None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[dict[str, object]] = []

    async def get(self, url, **kwargs):
        """Capture GET requests."""
        self.calls.append({"url": url, **kwargs})
        if self._error is not None:
            raise self._error
        return self._response


def test_normalize_base_url() -> None:
    """Test URL normalization."""
    assert (
        normalize_base_url("example.firewalla.net") == "https://example.firewalla.net"
    )
    assert (
        normalize_base_url(" https://example.firewalla.net/path ")
        == "https://example.firewalla.net"
    )


def test_normalize_base_url_rejects_invalid() -> None:
    """Test invalid URL normalization."""
    with pytest.raises(ValueError):
        normalize_base_url("https://")


def test_trend_point_as_datetime() -> None:
    """Test TrendPoint datetime conversion."""
    point = TrendPoint(ts=1_700_000_000, value=5)
    assert point.as_datetime == datetime.fromtimestamp(1_700_000_000, UTC)


def test_client_base_url_property() -> None:
    """Test the normalized base URL property."""
    client = FirewallaApiClient(
        MockSession(),
        "example.firewalla.net",
        "token",
        verify_ssl=True,
    )
    assert client.base_url == "https://example.firewalla.net"


@pytest.mark.asyncio
async def test_async_get_trend_sorts_and_filters_payload() -> None:
    """Test trend parsing and sorting."""
    session = MockSession(
        MockResponse(
            [
                {"ts": 2, "value": 20},
                {"ts": 4, "value": "8"},
                {"ts": 3, "value": "bad"},
                {"value": 1},
                "ignore",
            ]
        )
    )
    client = FirewallaApiClient(
        session, "https://example.firewalla.net", " token ", verify_ssl=False
    )

    result = await client.async_get_trend("flows", "group-a")

    assert [(point.ts, point.value) for point in result] == [(4, 8), (3, 0), (2, 20)]
    assert session.calls[0]["params"] == {"group": "group-a"}
    assert session.calls[0]["headers"] == {"Authorization": "Token token"}
    assert session.calls[0]["ssl"] is False


@pytest.mark.asyncio
async def test_async_get_trend_raises_auth_error() -> None:
    """Test trend auth error."""
    client = FirewallaApiClient(
        MockSession(MockResponse([], status=401)),
        "https://example.firewalla.net",
        "token",
        verify_ssl=True,
    )

    with pytest.raises(FirewallaApiAuthError):
        await client.async_get_trend("flows")


@pytest.mark.asyncio
async def test_async_get_trend_raises_connect_error() -> None:
    """Test trend transport error."""
    client = FirewallaApiClient(
        MockSession(error=ClientError()),
        "https://example.firewalla.net",
        "token",
        verify_ssl=True,
    )

    with pytest.raises(FirewallaApiError, match="cannot_connect"):
        await client.async_get_trend("flows")


@pytest.mark.asyncio
async def test_async_get_trend_rejects_non_list_payload() -> None:
    """Test trend endpoint rejects invalid payload shape."""
    client = FirewallaApiClient(
        MockSession(MockResponse({"results": []})),
        "https://example.firewalla.net",
        "token",
        verify_ssl=True,
    )

    with pytest.raises(FirewallaApiError, match="invalid_response"):
        await client.async_get_trend("flows")


@pytest.mark.asyncio
async def test_async_get_simple_stats_parses_known_keys() -> None:
    """Test simple stats parsing."""
    client = FirewallaApiClient(
        MockSession(
            MockResponse(
                {
                    "onlineBoxes": "3",
                    "offlineBoxes": 2,
                    "alarms": "bad",
                    "rules": 9,
                    "ignored": 5,
                }
            )
        ),
        "https://example.firewalla.net",
        "token",
        verify_ssl=True,
    )

    result = await client.async_get_simple_stats()
    assert result == {"onlineBoxes": 3, "offlineBoxes": 2, "rules": 9}


@pytest.mark.asyncio
async def test_async_get_simple_stats_rejects_non_dict_payload() -> None:
    """Test simple stats endpoint rejects invalid payload shape."""
    client = FirewallaApiClient(
        MockSession(MockResponse([])),
        "https://example.firewalla.net",
        "token",
        verify_ssl=True,
    )

    with pytest.raises(FirewallaApiError, match="invalid_response"):
        await client.async_get_simple_stats()


@pytest.mark.asyncio
async def test_async_get_statistics_filters_invalid_entries() -> None:
    """Test top stats parsing."""
    client = FirewallaApiClient(
        MockSession(
            MockResponse(
                [
                    {"meta": {"name": "A", "gid": 7, "none": None}, "value": "10"},
                    {"meta": "bad", "value": 11},
                    {"meta": {"name": "skip"}, "value": "bad"},
                ]
            )
        ),
        "https://example.firewalla.net",
        "token",
        verify_ssl=True,
    )

    result = await client.async_get_statistics("topBoxesByBlockedFlows", limit=2)
    assert result == [
        {"meta": {"name": "A", "gid": "7"}, "value": 10},
        {"meta": {}, "value": 11},
    ]


@pytest.mark.asyncio
async def test_async_get_statistics_rejects_non_list_payload() -> None:
    """Test stats endpoint rejects invalid payload shape."""
    client = FirewallaApiClient(
        MockSession(MockResponse({"results": []})),
        "https://example.firewalla.net",
        "token",
        verify_ssl=True,
    )

    with pytest.raises(FirewallaApiError, match="invalid_response"):
        await client.async_get_statistics("topBoxesByBlockedFlows")


@pytest.mark.asyncio
async def test_async_get_boxes_parses_payload_and_group_param() -> None:
    """Test boxes parsing and query params."""
    session = MockSession(MockResponse([{"gid": "1"}, "skip"]))
    client = FirewallaApiClient(
        session, "https://example.firewalla.net", "token", verify_ssl=True
    )

    result = await client.async_get_boxes(group="branch")

    assert result == [{"gid": "1"}]
    assert session.calls[0]["params"] == {"group": "branch"}


@pytest.mark.asyncio
async def test_async_get_boxes_rejects_invalid_payload() -> None:
    """Test boxes endpoint rejects invalid payload shape."""
    client = FirewallaApiClient(
        MockSession(MockResponse({"value": []})),
        "https://example.firewalla.net",
        "token",
        verify_ssl=True,
    )

    with pytest.raises(FirewallaApiError, match="invalid_response"):
        await client.async_get_boxes()


@pytest.mark.asyncio
async def test_async_get_devices_accepts_list_and_dict_payloads() -> None:
    """Test devices payload variants."""
    list_session = MockSession(MockResponse([{"id": 1}, "skip"]))
    list_client = FirewallaApiClient(
        list_session,
        "https://example.firewalla.net",
        "token",
        verify_ssl=True,
    )
    dict_session = MockSession(MockResponse({"value": [{"id": 2}, "skip"]}))
    dict_client = FirewallaApiClient(
        dict_session,
        "https://example.firewalla.net",
        "token",
        verify_ssl=True,
    )

    assert await list_client.async_get_devices(group="g1") == [{"id": 1}]
    assert list_session.calls[0]["params"] == {"group": "g1"}

    assert await dict_client.async_get_devices(box="box-1") == [{"id": 2}]
    assert dict_session.calls[0]["params"] == {"box": "box-1"}


@pytest.mark.asyncio
async def test_async_get_devices_rejects_invalid_payload() -> None:
    """Test devices endpoint rejects invalid payload shape."""
    client = FirewallaApiClient(
        MockSession(MockResponse({"value": "bad"})),
        "https://example.firewalla.net",
        "token",
        verify_ssl=True,
    )

    with pytest.raises(FirewallaApiError, match="invalid_response"):
        await client.async_get_devices()


@pytest.mark.asyncio
async def test_async_get_grouped_flows_and_flows_validate_payloads() -> None:
    """Test flow endpoints parsing."""
    grouped_session = MockSession(MockResponse({"results": [{"id": 1}, "skip"]}))
    grouped_client = FirewallaApiClient(
        grouped_session,
        "https://example.firewalla.net",
        "token",
        verify_ssl=True,
    )
    flows_session = MockSession(
        MockResponse({"results": [{"id": 2}], "next_cursor": 5})
    )
    flows_client = FirewallaApiClient(
        flows_session,
        "https://example.firewalla.net",
        "token",
        verify_ssl=True,
    )

    assert await grouped_client.async_get_grouped_flows(query="q") == [{"id": 1}]
    assert grouped_session.calls[0]["params"] == {
        "limit": "100",
        "groupBy": "network",
        "query": "q",
    }
    items, cursor = await flows_client.async_get_flows(query="q", cursor="abc")
    assert items == [{"id": 2}]
    assert cursor is None
    assert flows_session.calls[0]["params"] == {
        "limit": "500",
        "query": "q",
        "cursor": "abc",
    }


@pytest.mark.asyncio
async def test_async_get_grouped_flows_rejects_invalid_results_shape() -> None:
    """Test grouped flows endpoint rejects invalid payload shape."""
    client = FirewallaApiClient(
        MockSession(MockResponse({"results": "bad"})),
        "https://example.firewalla.net",
        "token",
        verify_ssl=True,
    )

    with pytest.raises(FirewallaApiError, match="invalid_response"):
        await client.async_get_grouped_flows()


@pytest.mark.asyncio
async def test_async_get_flows_rejects_invalid_payload_shape() -> None:
    """Test flows endpoint rejects invalid payload shape."""
    client = FirewallaApiClient(
        MockSession(MockResponse({"results": "bad", "next_cursor": "next"})),
        "https://example.firewalla.net",
        "token",
        verify_ssl=True,
    )

    with pytest.raises(FirewallaApiError, match="invalid_response"):
        await client.async_get_flows()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "args", "kwargs"),
    [
        ("async_get_trend", ("flows",), {}),
        ("async_get_simple_stats", (), {}),
        ("async_get_statistics", ("topBoxesByBlockedFlows",), {}),
        ("async_get_boxes", (), {}),
        ("async_get_devices", (), {}),
        ("async_get_grouped_flows", (), {}),
        ("async_get_flows", (), {}),
    ],
)
async def test_api_methods_raise_http_error_for_non_auth_failures(
    method_name: str,
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> None:
    """Test API methods surface non-auth HTTP errors consistently."""
    client = FirewallaApiClient(
        MockSession(MockResponse({}, status=403)),
        "https://example.firewalla.net",
        "token",
        verify_ssl=True,
    )

    with pytest.raises(FirewallaApiError, match="http_403"):
        await getattr(client, method_name)(*args, **kwargs)
