"""Config flow for Firewalla."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_TOKEN
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    FirewallaApiAuthError,
    FirewallaApiClient,
    FirewallaApiError,
    normalize_base_url,
)
from .const import (
    CONF_BASE_URL,
    CONF_GROUP,
    CONF_SCAN_INTERVAL,
    CONF_SCOPE_ID,
    CONF_SCOPE_TYPE,
    CONF_TRAFFIC_WINDOW_MINUTES,
    CONF_VERIFY_SSL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TRAFFIC_WINDOW_MINUTES,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    SCOPE_BOX,
    SCOPE_GLOBAL,
    SCOPE_GROUP,
    SCOPE_TYPES,
    TRAFFIC_WINDOW_MINUTES_OPTIONS,
)

_LOGGER = logging.getLogger(__name__)


class FirewallaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Firewalla."""

    VERSION = 1
    MINOR_VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow."""
        return FirewallaOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle the initial config step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                normalized_base_url = normalize_base_url(user_input[CONF_BASE_URL])
                normalized_input = self._normalize_user_input(user_input)
                await self._validate_input(normalized_base_url, normalized_input)
            except ValueError as err:
                errors["base"] = str(err)
            except FirewallaApiAuthError:
                errors["base"] = "invalid_auth"
            except FirewallaApiError:
                errors["base"] = "cannot_connect"
            else:
                scope_key = (
                    normalized_input[CONF_SCOPE_ID]
                    if normalized_input[CONF_SCOPE_TYPE] != SCOPE_GLOBAL
                    else SCOPE_GLOBAL
                )
                await self.async_set_unique_id(
                    f"{normalized_base_url}|{normalized_input[CONF_SCOPE_TYPE]}|{scope_key}"
                )
                self._abort_if_unique_id_configured()

                data = dict(normalized_input)
                data[CONF_BASE_URL] = normalized_base_url
                if not data[CONF_SCOPE_ID]:
                    data.pop(CONF_SCOPE_ID, None)
                data.pop(CONF_GROUP, None)
                return self.async_create_entry(title=data[CONF_NAME], data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=self._build_schema(user_input),
            errors=errors,
        )

    async def _validate_input(self, base_url: str, user_input: dict) -> None:
        """Validate credentials and requested scope."""
        client = FirewallaApiClient(
            async_get_clientsession(self.hass),
            base_url,
            user_input[CONF_TOKEN],
            verify_ssl=user_input[CONF_VERIFY_SSL],
        )

        scope_type = user_input[CONF_SCOPE_TYPE]
        scope_id = user_input.get(CONF_SCOPE_ID) or None
        boxes = await client.async_get_boxes(
            group=scope_id if scope_type == SCOPE_GROUP else None
        )

        if scope_type == SCOPE_BOX and scope_id:
            if not any(str(box.get("gid") or "").strip() == scope_id for box in boxes):
                global_boxes = await client.async_get_boxes()
                if not any(
                    str(box.get("gid") or "").strip() == scope_id for box in global_boxes
                ):
                    raise ValueError("unknown_box")

    def _normalize_user_input(self, user_input: dict) -> dict:
        """Normalize submitted config flow values."""
        data = dict(user_input)
        scope_type = str(data.get(CONF_SCOPE_TYPE, SCOPE_GLOBAL))
        scope_id = str(data.get(CONF_SCOPE_ID, "") or "").strip()
        legacy_group = str(data.get(CONF_GROUP, "") or "").strip()

        if not scope_id and legacy_group:
            scope_type = SCOPE_GROUP
            scope_id = legacy_group

        if scope_type == SCOPE_GLOBAL:
            scope_id = ""
        elif not scope_id:
            raise ValueError("missing_scope_id")

        data[CONF_SCOPE_TYPE] = scope_type
        data[CONF_SCOPE_ID] = scope_id
        data[CONF_NAME] = (
            data.get(CONF_NAME) or self._default_title(scope_type, scope_id)
        ).strip()
        return data

    def _default_title(self, scope_type: str, scope_id: str) -> str:
        """Build the default entry title."""
        if scope_type == SCOPE_GLOBAL:
            return "Firewalla (global)"
        return f"Firewalla ({scope_type} {scope_id})"

    def _build_schema(self, user_input: dict | None) -> vol.Schema:
        """Build the setup schema."""
        user_input = user_input or {}
        default_scope_type = user_input.get(CONF_SCOPE_TYPE)
        if not default_scope_type:
            legacy_group = str(user_input.get(CONF_GROUP) or "").strip()
            default_scope_type = SCOPE_GROUP if legacy_group else SCOPE_GLOBAL
        default_scope_id = user_input.get(CONF_SCOPE_ID)
        if default_scope_id is None:
            default_scope_id = user_input.get(CONF_GROUP, "")

        return vol.Schema(
            {
                vol.Optional(
                    CONF_NAME, default=user_input.get(CONF_NAME, "Firewalla")
                ): str,
                vol.Required(
                    CONF_BASE_URL,
                    default=user_input.get(
                        CONF_BASE_URL, "https://dn-knzvvk.firewalla.net"
                    ),
                ): str,
                vol.Required(CONF_TOKEN, default=user_input.get(CONF_TOKEN, "")): str,
                vol.Required(
                    CONF_SCOPE_TYPE, default=default_scope_type
                ): vol.In(SCOPE_TYPES),
                vol.Optional(CONF_SCOPE_ID, default=default_scope_id): str,
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=user_input.get(
                        CONF_SCAN_INTERVAL,
                        int(DEFAULT_SCAN_INTERVAL.total_seconds()),
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=60, max=3600)),
                vol.Required(
                    CONF_TRAFFIC_WINDOW_MINUTES,
                    default=user_input.get(
                        CONF_TRAFFIC_WINDOW_MINUTES,
                        DEFAULT_TRAFFIC_WINDOW_MINUTES,
                    ),
                ): vol.In(TRAFFIC_WINDOW_MINUTES_OPTIONS),
                vol.Optional(
                    CONF_VERIFY_SSL,
                    default=user_input.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
                ): bool,
            }
        )


class FirewallaOptionsFlow(config_entries.OptionsFlow):
    """Options flow for Firewalla."""

    def __init__(self, config_entry) -> None:
        """Initialize the options flow."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_scan = self._config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self._config_entry.data.get(
                CONF_SCAN_INTERVAL,
                int(DEFAULT_SCAN_INTERVAL.total_seconds()),
            ),
        )
        current_window = self._config_entry.options.get(
            CONF_TRAFFIC_WINDOW_MINUTES,
            self._config_entry.data.get(
                CONF_TRAFFIC_WINDOW_MINUTES,
                DEFAULT_TRAFFIC_WINDOW_MINUTES,
            ),
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_SCAN_INTERVAL, default=current_scan): vol.All(
                        vol.Coerce(int), vol.Range(min=60, max=3600)
                    ),
                    vol.Required(
                        CONF_TRAFFIC_WINDOW_MINUTES, default=current_window
                    ): vol.In(TRAFFIC_WINDOW_MINUTES_OPTIONS),
                }
            ),
        )
