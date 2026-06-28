"""Config flow for Firewalla."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_TOKEN
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .api import (
    FirewallaApiAuthError,
    FirewallaApiClient,
    FirewallaApiError,
    normalize_base_url,
)
from .const import (
    CONF_API_DAILY_REQUEST_LIMIT,
    CONF_BASE_URL,
    CONF_GROUP,
    CONF_SCAN_INTERVAL,
    CONF_SCOPE_ID,
    CONF_SCOPE_TYPE,
    CONF_TRAFFIC_WINDOW_MINUTES,
    CONF_VERIFY_SSL,
    DEFAULT_API_DAILY_REQUEST_LIMIT,
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
from .coordinator import _minimum_scan_interval_seconds

_LOGGER = logging.getLogger(__name__)


def _format_api_calls_timestamp(value: object) -> str | None:
    """Format the last API call timestamp for display."""
    if not isinstance(value, str):
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        return None
    local = dt_util.as_local(parsed)
    return local.strftime("%m/%d/%Y %I:%M%p").replace("AM", "am").replace(
        "PM", "pm"
    )


def _api_calls_summary_from_entry(entry) -> str:
    """Build a concise API usage summary for a config entry."""
    coordinator = getattr(entry, "runtime_data", None)
    api_calls: dict[str, object] = {}
    if coordinator is not None:
        data = getattr(coordinator, "data", None)
        if isinstance(data, dict):
            raw_api_calls = data.get("api_calls", {})
            if isinstance(raw_api_calls, dict):
                api_calls = raw_api_calls

    daily_total = api_calls.get("daily_total")
    if not isinstance(daily_total, int):
        daily_total = 0

    timestamp = _format_api_calls_timestamp(api_calls.get("last_attempt_at"))
    limit = getattr(getattr(entry, "runtime_data", None), "api_daily_request_limit", None)
    if not isinstance(limit, int):
        limit = entry.options.get(
            CONF_API_DAILY_REQUEST_LIMIT,
            entry.data.get(CONF_API_DAILY_REQUEST_LIMIT, DEFAULT_API_DAILY_REQUEST_LIMIT),
        )
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = DEFAULT_API_DAILY_REQUEST_LIMIT
    summary = f"{daily_total}/{limit} API calls made"
    if timestamp:
        return f"{timestamp} -- {summary}"
    return summary


def _api_daily_limit_from_mapping(mapping: dict) -> int:
    """Resolve the API daily request limit from a config mapping."""
    value = mapping.get(CONF_API_DAILY_REQUEST_LIMIT, DEFAULT_API_DAILY_REQUEST_LIMIT)
    try:
        return max(int(value), 1)
    except (TypeError, ValueError):
        return DEFAULT_API_DAILY_REQUEST_LIMIT


class FirewallaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Firewalla."""

    VERSION = 1
    MINOR_VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow."""
        return FirewallaOptionsFlow(config_entry)

    async def async_step_reauth(self, entry_data):
        """Start the reauthentication flow."""
        self.context["title_placeholders"] = {
            "name": entry_data.get(CONF_NAME, "Firewalla")
        }
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Handle reauthentication for an existing config entry."""
        errors: dict[str, str] = {}
        try:
            entry = self._get_reauth_entry()
        except config_entries.UnknownEntry:
            return self.async_abort(reason="unknown")

        if user_input is not None:
            try:
                validation_input = {
                    **entry.data,
                    CONF_TOKEN: user_input[CONF_TOKEN],
                }
                await self._validate_input(entry.data[CONF_BASE_URL], validation_input)
            except ValueError as err:
                errors["base"] = str(err)
            except FirewallaApiAuthError:
                errors["base"] = "invalid_auth"
            except FirewallaApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_TOKEN: user_input[CONF_TOKEN]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOKEN, default=""): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input=None):
        """Handle reconfiguration for an existing config entry."""
        try:
            entry = self._get_reconfigure_entry()
        except config_entries.UnknownEntry:
            return self.async_abort(reason="unknown")
        self.context["title_placeholders"] = {"name": entry.title}
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                normalized_base_url = normalize_base_url(user_input[CONF_BASE_URL])
                normalized_input = self._normalize_user_input({**entry.data, **user_input})
                await self._validate_input(normalized_base_url, normalized_input)
                scope_key = (
                    normalized_input[CONF_SCOPE_ID]
                    if normalized_input[CONF_SCOPE_TYPE] != SCOPE_GLOBAL
                    else SCOPE_GLOBAL
                )
                unique_id = (
                    f"{normalized_base_url}|"
                    f"{normalized_input[CONF_SCOPE_TYPE]}|"
                    f"{scope_key}"
                )
                conflict_entry = self.hass.config_entries.async_entry_for_domain_unique_id(
                    DOMAIN, unique_id
                )
                if conflict_entry and conflict_entry.entry_id != entry.entry_id:
                    return self.async_abort(reason="already_configured")
            except ValueError as err:
                errors["base"] = str(err)
            except FirewallaApiAuthError:
                errors["base"] = "invalid_auth"
            except FirewallaApiError:
                errors["base"] = "cannot_connect"
            else:
                normalized_input[CONF_API_DAILY_REQUEST_LIMIT] = _api_daily_limit_from_mapping(
                    {**entry.data, **normalized_input}
                )
                normalized_input[CONF_SCAN_INTERVAL] = max(
                    int(normalized_input.get(CONF_SCAN_INTERVAL, 0)),
                    _minimum_scan_interval_seconds(
                        normalized_input[CONF_SCOPE_TYPE],
                        normalized_input[CONF_API_DAILY_REQUEST_LIMIT],
                    ),
                )
                updated_data = {**entry.data, **normalized_input}
                updated_data[CONF_BASE_URL] = normalized_base_url
                if not updated_data[CONF_SCOPE_ID]:
                    updated_data.pop(CONF_SCOPE_ID, None)
                updated_data.pop(CONF_GROUP, None)
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=unique_id,
                    data_updates=updated_data,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._build_reconfigure_schema(entry.data),
            description_placeholders={
                "base_url_example": "https://example.firewalla.net",
                "api_calls_summary": _api_calls_summary_from_entry(entry),
            },
            errors=errors,
        )

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
                normalized_input[CONF_API_DAILY_REQUEST_LIMIT] = _api_daily_limit_from_mapping(
                    normalized_input
                )
                normalized_input[CONF_SCAN_INTERVAL] = max(
                    int(normalized_input.get(CONF_SCAN_INTERVAL, 0)),
                    _minimum_scan_interval_seconds(
                        normalized_input[CONF_SCOPE_TYPE],
                        normalized_input[CONF_API_DAILY_REQUEST_LIMIT],
                    ),
                )
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
            description_placeholders={
                "base_url_example": "https://example.firewalla.net"
            },
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
        default_api_limit = _api_daily_limit_from_mapping(user_input)
        minimum_scan_seconds = _minimum_scan_interval_seconds(
            default_scope_type, default_api_limit
        )
        default_scan_seconds = int(
            user_input.get(CONF_SCAN_INTERVAL, int(DEFAULT_SCAN_INTERVAL.total_seconds()))
        )
        default_scan_seconds = max(default_scan_seconds, minimum_scan_seconds)

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
                    CONF_API_DAILY_REQUEST_LIMIT, default=default_api_limit
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=100000)),
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=default_scan_seconds,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=60, max=3600),
                ),
                vol.Required(
                    CONF_TRAFFIC_WINDOW_MINUTES,
                    default=user_input.get(
                        CONF_TRAFFIC_WINDOW_MINUTES,
                        DEFAULT_TRAFFIC_WINDOW_MINUTES,
                    ),
                ): vol.All(
                    vol.Coerce(int), vol.In(TRAFFIC_WINDOW_MINUTES_OPTIONS)
                ),
                vol.Optional(
                    CONF_VERIFY_SSL,
                    default=user_input.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
                ): bool,
            }
        )

    def _build_reconfigure_schema(self, entry_data: dict) -> vol.Schema:
        """Build the reconfigure schema."""
        default_api_limit = _api_daily_limit_from_mapping(entry_data)
        minimum_scan_seconds = _minimum_scan_interval_seconds(
            entry_data.get(CONF_SCOPE_TYPE, SCOPE_GLOBAL), default_api_limit
        )
        default_scan_seconds = int(
            entry_data.get(CONF_SCAN_INTERVAL, int(DEFAULT_SCAN_INTERVAL.total_seconds()))
        )
        default_scan_seconds = max(default_scan_seconds, minimum_scan_seconds)
        return vol.Schema(
            {
                vol.Optional(
                    CONF_NAME, default=entry_data.get(CONF_NAME, "Firewalla")
                ): str,
                vol.Required(
                    CONF_BASE_URL,
                    default=entry_data.get(
                        CONF_BASE_URL, "https://dn-knzvvk.firewalla.net"
                    ),
                ): str,
                vol.Required(CONF_TOKEN, default=entry_data.get(CONF_TOKEN, "")): str,
                vol.Required(
                    CONF_SCOPE_TYPE,
                    default=entry_data.get(CONF_SCOPE_TYPE, SCOPE_GLOBAL),
                ): vol.In(SCOPE_TYPES),
                vol.Optional(
                    CONF_SCOPE_ID, default=entry_data.get(CONF_SCOPE_ID, "")
                ): str,
                vol.Optional(
                    CONF_API_DAILY_REQUEST_LIMIT, default=default_api_limit
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=100000)),
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=default_scan_seconds
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=60, max=3600),
                ),
                vol.Optional(
                    CONF_VERIFY_SSL,
                    default=entry_data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
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
            updated_scan = max(
                int(user_input[CONF_SCAN_INTERVAL]),
                _minimum_scan_interval_seconds(
                    self._config_entry.data.get(CONF_SCOPE_TYPE, SCOPE_GLOBAL),
                    _api_daily_limit_from_mapping(
                        {**self._config_entry.data, **self._config_entry.options}
                    ),
                ),
            )
            updated_limit = _api_daily_limit_from_mapping(user_input)
            return self.async_create_entry(
                title="",
                data={
                    **user_input,
                    CONF_API_DAILY_REQUEST_LIMIT: updated_limit,
                    CONF_SCAN_INTERVAL: updated_scan,
                },
            )

        current_limit = _api_daily_limit_from_mapping(
            {**self._config_entry.data, **self._config_entry.options}
        )
        minimum_scan_seconds = _minimum_scan_interval_seconds(
            self._config_entry.data.get(CONF_SCOPE_TYPE, SCOPE_GLOBAL), current_limit
        )
        current_scan = self._config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self._config_entry.data.get(
                CONF_SCAN_INTERVAL,
                int(DEFAULT_SCAN_INTERVAL.total_seconds()),
            ),
        )
        current_scan = max(int(current_scan), minimum_scan_seconds)
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
                    vol.Optional(
                        CONF_API_DAILY_REQUEST_LIMIT, default=current_limit
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=100000)),
                    vol.Optional(CONF_SCAN_INTERVAL, default=current_scan): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=60, max=3600),
                    ),
                    vol.Required(
                        CONF_TRAFFIC_WINDOW_MINUTES, default=current_window
                    ): vol.All(
                        vol.Coerce(int), vol.In(TRAFFIC_WINDOW_MINUTES_OPTIONS)
                    ),
                }
            ),
            description_placeholders={
                "api_calls_summary": _api_calls_summary_from_entry(
                    self._config_entry
                ),
            },
        )
