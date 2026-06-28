"""Tests for the Firewalla config flow."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_NAME
from homeassistant.util import dt as dt_util

from custom_components.firewalla.api import FirewallaApiAuthError, FirewallaApiError
from custom_components.firewalla.config_flow import (
    FirewallaConfigFlow,
    FirewallaOptionsFlow,
)
from custom_components.firewalla.const import (
    CONF_API_DAILY_REQUEST_LIMIT,
    CONF_BASE_URL,
    CONF_SCAN_INTERVAL,
    CONF_SCOPE_ID,
    CONF_SCOPE_TYPE,
    CONF_TRAFFIC_WINDOW_MINUTES,
    CONF_VERIFY_SSL,
    DEFAULT_API_DAILY_REQUEST_LIMIT,
    DEFAULT_TRAFFIC_WINDOW_MINUTES,
    DOMAIN,
    SCOPE_BOX,
    SCOPE_GLOBAL,
    SCOPE_GROUP,
)
from tests.common import MockConfigEntry


async def test_user_flow_creates_global_entry(hass) -> None:
    """Test a successful global config flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.firewalla.config_flow.FirewallaConfigFlow._validate_input",
        new=AsyncMock(),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "name": "Firewalla",
                CONF_BASE_URL: "https://example.firewalla.net",
                "token": "abc123",
                CONF_SCOPE_TYPE: SCOPE_GLOBAL,
                CONF_SCOPE_ID: "",
                CONF_SCAN_INTERVAL: 300,
                CONF_TRAFFIC_WINDOW_MINUTES: 15,
                CONF_VERIFY_SSL: True,
            },
        )

    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Firewalla"
    assert result["data"][CONF_SCOPE_TYPE] == SCOPE_GLOBAL
    assert CONF_SCOPE_ID not in result["data"]


async def test_user_flow_creates_group_entry_with_generated_title(hass) -> None:
    """Test config flow normalizes group scope and default title."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.firewalla.config_flow.FirewallaConfigFlow._validate_input",
        new=AsyncMock(),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "name": "",
                CONF_BASE_URL: "example.firewalla.net",
                "token": "abc123",
                CONF_SCOPE_TYPE: SCOPE_GROUP,
                CONF_SCOPE_ID: "  branch-office  ",
                CONF_SCAN_INTERVAL: 300,
                CONF_TRAFFIC_WINDOW_MINUTES: 15,
                CONF_VERIFY_SSL: True,
            },
        )

    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Firewalla (group branch-office)"
    assert result["data"][CONF_BASE_URL] == "https://example.firewalla.net"
    assert result["data"][CONF_SCOPE_ID] == "branch-office"


async def test_user_flow_creates_box_entry(hass) -> None:
    """Test config flow supports box scope entries."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.firewalla.config_flow.FirewallaConfigFlow._validate_input",
        new=AsyncMock(),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "name": "Branch Box",
                CONF_BASE_URL: "example.firewalla.net",
                "token": "abc123",
                CONF_SCOPE_TYPE: SCOPE_BOX,
                CONF_SCOPE_ID: "gid-1",
                CONF_SCAN_INTERVAL: 300,
                CONF_TRAFFIC_WINDOW_MINUTES: 15,
                CONF_VERIFY_SSL: True,
            },
        )

    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SCOPE_TYPE] == SCOPE_BOX
    assert result["data"][CONF_SCOPE_ID] == "gid-1"


async def test_user_flow_invalid_auth(hass) -> None:
    """Test config flow auth failure."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.firewalla.config_flow.FirewallaConfigFlow._validate_input",
        new=AsyncMock(side_effect=FirewallaApiAuthError),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "name": "Firewalla",
                CONF_BASE_URL: "https://example.firewalla.net",
                "token": "abc123",
                CONF_SCOPE_TYPE: SCOPE_GLOBAL,
                CONF_SCOPE_ID: "",
                CONF_SCAN_INTERVAL: 300,
                CONF_TRAFFIC_WINDOW_MINUTES: 15,
                CONF_VERIFY_SSL: True,
            },
        )

    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_invalid_url(hass) -> None:
    """Test config flow URL validation failure."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Firewalla",
            CONF_BASE_URL: "https://",
            "token": "abc123",
            CONF_SCOPE_TYPE: SCOPE_GLOBAL,
            CONF_SCOPE_ID: "",
            CONF_SCAN_INTERVAL: 300,
            CONF_TRAFFIC_WINDOW_MINUTES: 15,
            CONF_VERIFY_SSL: True,
        },
    )

    assert result["errors"] == {"base": "invalid_url"}


async def test_user_flow_cannot_connect(hass) -> None:
    """Test config flow connectivity failure."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.firewalla.config_flow.FirewallaConfigFlow._validate_input",
        new=AsyncMock(side_effect=FirewallaApiError),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "name": "Firewalla",
                CONF_BASE_URL: "https://example.firewalla.net",
                "token": "abc123",
                CONF_SCOPE_TYPE: SCOPE_GLOBAL,
                CONF_SCOPE_ID: "",
                CONF_SCAN_INTERVAL: 300,
                CONF_TRAFFIC_WINDOW_MINUTES: 15,
                CONF_VERIFY_SSL: True,
            },
        )

    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_requires_scope_id_for_non_global_scope(hass) -> None:
    """Test config flow rejects missing non-global scope IDs."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Firewalla",
            CONF_BASE_URL: "https://example.firewalla.net",
            "token": "abc123",
            CONF_SCOPE_TYPE: SCOPE_GROUP,
            CONF_SCOPE_ID: "",
            CONF_SCAN_INTERVAL: 300,
            CONF_TRAFFIC_WINDOW_MINUTES: 15,
            CONF_VERIFY_SSL: True,
        },
    )

    assert result["errors"] == {"base": "missing_scope_id"}


async def test_options_flow_uses_current_scan_interval(hass) -> None:
    """Test options flow shows and stores scan interval."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla",
        data={CONF_SCAN_INTERVAL: 120, CONF_TRAFFIC_WINDOW_MINUTES: 15},
        options={CONF_SCAN_INTERVAL: 240, CONF_TRAFFIC_WINDOW_MINUTES: 5},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is data_entry_flow.FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 300, CONF_TRAFFIC_WINDOW_MINUTES: 30}
    )
    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_API_DAILY_REQUEST_LIMIT: DEFAULT_API_DAILY_REQUEST_LIMIT,
        CONF_SCAN_INTERVAL: 360,
        CONF_TRAFFIC_WINDOW_MINUTES: 30,
    }


async def test_options_flow_accepts_string_traffic_window(hass) -> None:
    """Test traffic window radio values are coerced safely."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla",
        data={
            CONF_SCOPE_TYPE: SCOPE_GLOBAL,
            CONF_SCAN_INTERVAL: 360,
            CONF_TRAFFIC_WINDOW_MINUTES: 15,
        },
        options={},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is data_entry_flow.FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_API_DAILY_REQUEST_LIMIT: 3000,
            CONF_SCAN_INTERVAL: 360,
            CONF_TRAFFIC_WINDOW_MINUTES: "30",
        },
    )

    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_TRAFFIC_WINDOW_MINUTES] == 30


async def test_options_flow_shows_api_usage_summary(hass) -> None:
    """Test options flow includes the current API call tally."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla",
        data={
            CONF_SCOPE_TYPE: SCOPE_GLOBAL,
            CONF_SCAN_INTERVAL: 360,
            CONF_TRAFFIC_WINDOW_MINUTES: 15,
        },
        options={CONF_TRAFFIC_WINDOW_MINUTES: 15},
    )
    entry.runtime_data = SimpleNamespace(
        data={
            "api_calls": {
                "daily_total": 1331,
                "last_attempt_at": "2026-06-28T11:24:00-04:00",
            }
        }
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    expected_timestamp = dt_util.as_local(
        dt_util.parse_datetime("2026-06-28T11:24:00-04:00")
    ).strftime("%m/%d/%Y %I:%M%p").replace("AM", "am").replace("PM", "pm")
    assert result["description_placeholders"]["api_calls_summary"] == (
        f"{expected_timestamp} -- 1331/3000 API calls made"
    )


async def test_user_flow_aborts_for_duplicate_configured_instance(hass) -> None:
    """Test duplicate scoped instances are rejected."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla",
        unique_id="https://example.firewalla.net|group|branch-office",
        data={
            "name": "Firewalla",
            CONF_BASE_URL: "https://example.firewalla.net",
            "token": "abc123",
            CONF_SCOPE_TYPE: SCOPE_GROUP,
            CONF_SCOPE_ID: "branch-office",
            CONF_SCAN_INTERVAL: 300,
            CONF_TRAFFIC_WINDOW_MINUTES: 15,
            CONF_VERIFY_SSL: True,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.firewalla.config_flow.FirewallaConfigFlow._validate_input",
        new=AsyncMock(),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "name": "Firewalla",
                CONF_BASE_URL: "https://example.firewalla.net",
                "token": "abc123",
                CONF_SCOPE_TYPE: SCOPE_GROUP,
                CONF_SCOPE_ID: "branch-office",
                CONF_SCAN_INTERVAL: 300,
                CONF_TRAFFIC_WINDOW_MINUTES: 15,
                CONF_VERIFY_SSL: True,
            },
        )

    assert result["type"] is data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow_updates_existing_entry(hass) -> None:
    """Test reauth updates credentials on an existing entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla",
        data={
            "name": "Firewalla",
            CONF_BASE_URL: "https://old.firewalla.net",
            "token": "old-token",
            CONF_SCOPE_TYPE: SCOPE_GLOBAL,
            CONF_SCAN_INTERVAL: 300,
            CONF_TRAFFIC_WINDOW_MINUTES: 15,
            CONF_VERIFY_SSL: True,
        },
        unique_id="https://old.firewalla.net|global|global",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with (
        patch(
            "custom_components.firewalla.config_flow.FirewallaConfigFlow._validate_input",
            new=AsyncMock(),
        ),
        patch.object(hass.config_entries, "async_reload", new=AsyncMock()) as mock_reload,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "token": "new-token",
            },
        )

    updated = hass.config_entries.async_get_entry(entry.entry_id)
    assert result["type"] is data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert updated
    assert updated.data[CONF_BASE_URL] == "https://old.firewalla.net"
    assert updated.data["token"] == "new-token"
    assert updated.data[CONF_VERIFY_SSL] is True
    mock_reload.assert_awaited_once_with(entry.entry_id)


async def test_reauth_flow_handles_invalid_auth(hass) -> None:
    """Test reauth surfaces invalid auth errors."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla",
        data={
            "name": "Firewalla",
            CONF_BASE_URL: "https://old.firewalla.net",
            "token": "old-token",
            CONF_SCOPE_TYPE: SCOPE_GLOBAL,
            CONF_SCAN_INTERVAL: 300,
            CONF_TRAFFIC_WINDOW_MINUTES: 15,
            CONF_VERIFY_SSL: True,
        },
        unique_id="https://old.firewalla.net|global|global",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )

    with patch(
        "custom_components.firewalla.config_flow.FirewallaConfigFlow._validate_input",
        new=AsyncMock(side_effect=FirewallaApiAuthError),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "token": "new-token",
            },
        )

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reauth_flow_handles_connection_error(hass) -> None:
    """Test reauth surfaces connection errors."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla",
        data={
            "name": "Firewalla",
            CONF_BASE_URL: "https://old.firewalla.net",
            "token": "old-token",
            CONF_SCOPE_TYPE: SCOPE_GLOBAL,
            CONF_SCAN_INTERVAL: 300,
            CONF_TRAFFIC_WINDOW_MINUTES: 15,
            CONF_VERIFY_SSL: True,
        },
        unique_id="https://old.firewalla.net|global|global",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )

    with patch(
        "custom_components.firewalla.config_flow.FirewallaConfigFlow._validate_input",
        new=AsyncMock(side_effect=FirewallaApiError),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"token": "new-token"},
        )

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reauth_flow_handles_unknown_entry(hass) -> None:
    """Test reauth aborts when the config entry is missing."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": "missing",
        },
        data={CONF_NAME: "Firewalla"},
    )

    assert result["type"] is data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "unknown"


async def test_reconfigure_flow_updates_entry(hass) -> None:
    """Test reconfigure updates the existing config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla",
        data={
            "name": "Firewalla",
            CONF_BASE_URL: "https://old.firewalla.net",
            "token": "old-token",
            CONF_SCOPE_TYPE: SCOPE_GLOBAL,
            CONF_SCAN_INTERVAL: 300,
            CONF_TRAFFIC_WINDOW_MINUTES: 15,
            CONF_VERIFY_SSL: True,
        },
        unique_id="https://old.firewalla.net|global|global",
    )
    entry.runtime_data = SimpleNamespace(
        data={
            "api_calls": {
                "daily_total": 1331,
                "last_attempt_at": "2026-06-28T11:24:00-04:00",
            }
        }
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    expected_timestamp = dt_util.as_local(
        dt_util.parse_datetime("2026-06-28T11:24:00-04:00")
    ).strftime("%m/%d/%Y %I:%M%p").replace("AM", "am").replace("PM", "pm")
    assert result["description_placeholders"]["api_calls_summary"] == (
        f"{expected_timestamp} -- 1331/3000 API calls made"
    )

    with patch(
        "custom_components.firewalla.config_flow.FirewallaConfigFlow._validate_input",
        new=AsyncMock(),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "name": "Firewalla",
                CONF_BASE_URL: "https://new.firewalla.net",
                "token": "new-token",
                CONF_SCOPE_TYPE: SCOPE_GROUP,
                CONF_SCOPE_ID: "branch-office",
                CONF_VERIFY_SSL: False,
            },
        )

    assert result["type"] is data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_BASE_URL] == "https://new.firewalla.net"
    assert entry.data["token"] == "new-token"
    assert entry.data[CONF_SCOPE_TYPE] == SCOPE_GROUP
    assert entry.data[CONF_SCOPE_ID] == "branch-office"
    assert entry.data[CONF_VERIFY_SSL] is False


async def test_reconfigure_flow_aborts_on_conflict(hass) -> None:
    """Test reconfigure rejects duplicate unique IDs."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla Existing",
        data={
            "name": "Firewalla Existing",
            CONF_BASE_URL: "https://new.firewalla.net",
            "token": "token-2",
            CONF_SCOPE_TYPE: SCOPE_GROUP,
            CONF_SCOPE_ID: "branch-office",
            CONF_SCAN_INTERVAL: 300,
            CONF_TRAFFIC_WINDOW_MINUTES: 15,
            CONF_VERIFY_SSL: True,
        },
        unique_id="https://new.firewalla.net|group|branch-office",
    )
    existing.add_to_hass(hass)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla",
        data={
            "name": "Firewalla",
            CONF_BASE_URL: "https://old.firewalla.net",
            "token": "old-token",
            CONF_SCOPE_TYPE: SCOPE_GLOBAL,
            CONF_SCAN_INTERVAL: 300,
            CONF_TRAFFIC_WINDOW_MINUTES: 15,
            CONF_VERIFY_SSL: True,
        },
        unique_id="https://old.firewalla.net|global|global",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )

    with patch(
        "custom_components.firewalla.config_flow.FirewallaConfigFlow._validate_input",
        new=AsyncMock(),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "name": "Firewalla",
                CONF_BASE_URL: "https://new.firewalla.net",
                "token": "new-token",
                CONF_SCOPE_TYPE: SCOPE_GROUP,
                CONF_SCOPE_ID: "branch-office",
                CONF_VERIFY_SSL: True,
            },
        )

    assert result["type"] is data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"


def test_build_schema_uses_defaults() -> None:
    """Test config flow schema defaults."""
    flow = FirewallaConfigFlow()
    flow.hass = MagicMock()

    schema = flow._build_schema(None)
    serialized = schema({})

    assert serialized[CONF_BASE_URL] == "https://dn-knzvvk.firewalla.net"
    assert serialized[CONF_SCOPE_TYPE] == SCOPE_GLOBAL
    assert serialized[CONF_API_DAILY_REQUEST_LIMIT] == DEFAULT_API_DAILY_REQUEST_LIMIT
    assert serialized[CONF_SCAN_INTERVAL] == 360
    assert serialized[CONF_TRAFFIC_WINDOW_MINUTES] == DEFAULT_TRAFFIC_WINDOW_MINUTES
    assert serialized[CONF_VERIFY_SSL] is True


def test_default_title_uses_global_scope_label() -> None:
    """Test default title generation for global scope."""
    flow = FirewallaConfigFlow()
    assert flow._default_title(SCOPE_GLOBAL, "") == "Firewalla (global)"


def test_options_flow_class_is_registered() -> None:
    """Test options flow factory."""
    config_entry = MagicMock()
    options_flow = FirewallaConfigFlow.async_get_options_flow(config_entry)
    assert isinstance(options_flow, FirewallaOptionsFlow)
    assert options_flow._config_entry is config_entry


def test_normalize_user_input_supports_legacy_group_field() -> None:
    """Test normalization still accepts the legacy group field."""
    flow = FirewallaConfigFlow()
    flow.hass = MagicMock()

    normalized = flow._normalize_user_input(
        {
            "name": "",
            CONF_SCOPE_TYPE: SCOPE_GLOBAL,
            "group": "  branch-office  ",
        }
    )

    assert normalized[CONF_SCOPE_TYPE] == SCOPE_GROUP
    assert normalized[CONF_SCOPE_ID] == "branch-office"
    assert normalized["name"] == "Firewalla (group branch-office)"


async def test_validate_input_checks_box_scope(hass) -> None:
    """Test validation confirms the configured box exists."""
    flow = FirewallaConfigFlow()
    flow.hass = hass

    with (
        patch(
            "custom_components.firewalla.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.firewalla.config_flow.FirewallaApiClient.async_get_boxes",
            new=AsyncMock(side_effect=[[{"gid": "gid-1"}]]),
        ) as mock_get_boxes,
    ):
        await flow._validate_input(
            "https://example.firewalla.net",
            {
                "token": "abc123",
                CONF_SCOPE_TYPE: SCOPE_BOX,
                CONF_SCOPE_ID: "gid-1",
                CONF_VERIFY_SSL: True,
            },
        )

    mock_get_boxes.assert_awaited_once_with(group=None)


async def test_validate_input_rejects_unknown_box_scope(hass) -> None:
    """Test validation rejects unknown box IDs."""
    flow = FirewallaConfigFlow()
    flow.hass = hass

    with (
        patch(
            "custom_components.firewalla.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.firewalla.config_flow.FirewallaApiClient.async_get_boxes",
            new=AsyncMock(side_effect=[[], []]),
        ),
    ):
        with pytest.raises(ValueError, match="unknown_box"):
            await flow._validate_input(
                "https://example.firewalla.net",
                {
                    "token": "abc123",
                    CONF_SCOPE_TYPE: SCOPE_BOX,
                    CONF_SCOPE_ID: "missing",
                    CONF_VERIFY_SSL: True,
                },
            )
