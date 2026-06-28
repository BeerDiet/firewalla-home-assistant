"""Tests for the Firewalla API client."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aiohttp import ClientError, ClientResponseError

from custom_components.firewalla.api import (
    FirewallaApiAuthError,
    FirewallaApiCallTracker,
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
        return await self.request("GET", url, **kwargs)

    async def request(self, method, url, **kwargs):
        """Capture arbitrary requests."""
        self.calls.append({"method": method, "url": url, **kwargs})
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


def test_api_call_tracker_rolls_over_each_day() -> None:
    """Test daily API call counts reset in the local timezone."""

    class FixedNow:
        def __init__(self, moment: datetime) -> None:
            self.moment = moment

        def __call__(self) -> datetime:
            return self.moment

    now = FixedNow(datetime(2026, 6, 28, 23, 59, tzinfo=UTC))
    tracker = FirewallaApiCallTracker(now)

    tracker.record_attempt()
    tracker.record_attempt()

    first_snapshot = tracker.snapshot()
    assert first_snapshot["daily_total"] == 2
    assert first_snapshot["day_start"] == "2026-06-28T00:00:00+00:00"

    now.moment = datetime(2026, 6, 29, 0, 1, tzinfo=UTC)
    tracker.record_attempt()

    second_snapshot = tracker.snapshot()
    assert second_snapshot["daily_total"] == 1
    assert second_snapshot["day_start"] == "2026-06-29T00:00:00+00:00"


@pytest.mark.asyncio
async def test_api_client_counts_failed_requests() -> None:
    """Test every request attempt is counted, even when the request fails."""

    tracker = FirewallaApiCallTracker(
        lambda: datetime(2026, 6, 28, 12, 0, tzinfo=UTC)
    )
    client = FirewallaApiClient(
        MockSession(error=ClientError()),
        "https://example.firewalla.net",
        "token",
        verify_ssl=True,
        request_tracker=tracker,
    )

    with pytest.raises(FirewallaApiError, match="cannot_connect"):
        await client.async_get_boxes()

    assert tracker.snapshot()["daily_total"] == 1


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
async def test_async_get_simple_stats_passes_group_param() -> None:
    """Test simple stats include the group query parameter."""
    session = MockSession(MockResponse({"onlineBoxes": "1"}))
    client = FirewallaApiClient(
        session, "https://example.firewalla.net", "token", verify_ssl=True
    )

    await client.async_get_simple_stats(group="branch")

    assert session.calls[0]["params"] == {"group": "branch"}


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
async def test_async_get_statistics_passes_group_param() -> None:
    """Test stats requests include the group query parameter."""
    session = MockSession(MockResponse([{"meta": {"name": "A"}, "value": 1}]))
    client = FirewallaApiClient(
        session, "https://example.firewalla.net", "token", verify_ssl=True
    )

    await client.async_get_statistics("topBoxesByBlockedFlows", group="branch")

    assert session.calls[0]["params"] == {"limit": "5", "group": "branch"}


@pytest.mark.asyncio
async def test_async_get_statistics_skips_non_dict_items() -> None:
    """Test stats parsing skips malformed list items."""
    client = FirewallaApiClient(
        MockSession(MockResponse(["skip", {"meta": {"name": "A"}, "value": 1}])),
        "https://example.firewalla.net",
        "token",
        verify_ssl=True,
    )

    result = await client.async_get_statistics("topBoxesByBlockedFlows")
    assert result == [{"meta": {"name": "A"}, "value": 1}]


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
async def test_async_get_devices_rejects_non_container_payload() -> None:
    """Test devices endpoint rejects non-container payloads."""
    client = FirewallaApiClient(
        MockSession(MockResponse("bad")),
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
async def test_async_get_grouped_flows_rejects_non_dict_payload() -> None:
    """Test grouped flows endpoint rejects non-dict payloads."""
    client = FirewallaApiClient(
        MockSession(MockResponse([])),
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
async def test_async_get_flows_rejects_non_dict_payload() -> None:
    """Test flows endpoint rejects non-dict payloads."""
    client = FirewallaApiClient(
        MockSession(MockResponse([])),
        "https://example.firewalla.net",
        "token",
        verify_ssl=True,
    )

    with pytest.raises(FirewallaApiError, match="invalid_response"):
        await client.async_get_flows()


@pytest.mark.asyncio
async def test_async_get_rules_parses_payload_and_query_params() -> None:
    """Test rules payload parsing."""
    session = MockSession(
        MockResponse({"results": [{"id": 1}, "skip"], "next_cursor": "next"})
    )
    client = FirewallaApiClient(
        session,
        "https://example.firewalla.net",
        "token",
        verify_ssl=True,
    )

    items, cursor = await client.async_get_rules(query="box.id:g1", cursor="abc")

    assert items == [{"id": 1}]
    assert cursor == "next"
    assert session.calls[0]["params"] == {
        "limit": "500",
        "query": "box.id:g1",
        "cursor": "abc",
    }


@pytest.mark.asyncio
async def test_async_get_rules_rejects_invalid_payload_shapes() -> None:
    """Test rules endpoint rejects malformed payloads."""
    payloads = [
        MockResponse([]),
        MockResponse({"results": "bad", "next_cursor": 1}),
    ]

    for payload in payloads:
        client = FirewallaApiClient(
            MockSession(payload),
            "https://example.firewalla.net",
            "token",
            verify_ssl=True,
        )

        with pytest.raises(FirewallaApiError, match="invalid_response"):
            await client.async_get_rules()


@pytest.mark.asyncio
async def test_async_create_rule_posts_json_payload() -> None:
    """Test rule creation."""
    session = MockSession(MockResponse({"id": "rule-1"}))
    client = FirewallaApiClient(
        session,
        "https://example.firewalla.net",
        "token",
        verify_ssl=False,
    )

    result = await client.async_create_rule({"action": "block"})

    assert result == {"id": "rule-1"}
    assert session.calls[0]["method"] == "POST"
    assert session.calls[0]["json"] == {"action": "block"}


@pytest.mark.asyncio
async def test_async_create_rule_rejects_non_dict_payload() -> None:
    """Test rule creation rejects invalid payloads."""
    client = FirewallaApiClient(
        MockSession(MockResponse([])),
        "https://example.firewalla.net",
        "token",
        verify_ssl=True,
    )

    with pytest.raises(FirewallaApiError, match="invalid_response"):
        await client.async_create_rule({"action": "block"})


@pytest.mark.asyncio
async def test_async_pause_and_resume_rule_do_not_expect_json() -> None:
    """Test rule pause and resume requests."""
    session = MockSession(MockResponse(None))
    client = FirewallaApiClient(
        session,
        "https://example.firewalla.net",
        "token",
        verify_ssl=True,
    )

    await client.async_pause_rule("rule-1")
    await client.async_resume_rule("rule-2")

    assert session.calls[0]["method"] == "POST"
    assert session.calls[0]["url"].endswith("/v2/rules/rule-1/pause")
    assert session.calls[1]["url"].endswith("/v2/rules/rule-2/resume")


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
        ("async_get_rules", (), {}),
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
