"""Tests for the Firewalla config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries, data_entry_flow

from custom_components.firewalla.api import FirewallaApiAuthError, FirewallaApiError
from custom_components.firewalla.config_flow import (
    FirewallaConfigFlow,
    FirewallaOptionsFlow,
)
from custom_components.firewalla.const import (
    CONF_BASE_URL,
    CONF_SCAN_INTERVAL,
    CONF_SCOPE_ID,
    CONF_SCOPE_TYPE,
    CONF_VERIFY_SSL,
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
            CONF_VERIFY_SSL: True,
        },
    )

    assert result["errors"] == {"base": "missing_scope_id"}


async def test_options_flow_uses_current_scan_interval(hass) -> None:
    """Test options flow shows and stores scan interval."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Firewalla",
        data={CONF_SCAN_INTERVAL: 120},
        options={CONF_SCAN_INTERVAL: 240},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is data_entry_flow.FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 300}
    )
    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_SCAN_INTERVAL: 300}


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
    assert serialized[CONF_SCAN_INTERVAL] == 60
    assert serialized[CONF_VERIFY_SSL] is True


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
