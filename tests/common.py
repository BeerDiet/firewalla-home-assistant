"""Test compatibility helpers."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.util import ulid as ulid_util


class MockConfigEntry(config_entries.ConfigEntry):
    """Helper for creating config entries that adds some defaults."""

    def __init__(
        self,
        *,
        data=None,
        disabled_by=None,
        discovery_keys=None,
        domain="test",
        entry_id=None,
        minor_version=1,
        options=None,
        pref_disable_new_entities=None,
        pref_disable_polling=None,
        reason=None,
        source=config_entries.SOURCE_USER,
        state=None,
        subentries_data=None,
        title="Mock Title",
        unique_id=None,
        version=1,
    ) -> None:
        """Initialize a mock config entry."""
        discovery_keys = discovery_keys or {}
        kwargs = {
            "data": data or {},
            "disabled_by": disabled_by,
            "discovery_keys": discovery_keys,
            "domain": domain,
            "entry_id": entry_id or ulid_util.ulid_now(),
            "minor_version": minor_version,
            "options": options or {},
            "pref_disable_new_entities": pref_disable_new_entities,
            "pref_disable_polling": pref_disable_polling,
            "subentries_data": subentries_data or (),
            "title": title,
            "unique_id": unique_id,
            "version": version,
        }
        if source is not None:
            kwargs["source"] = source
        if state is not None:
            kwargs["state"] = state
        super().__init__(**kwargs)
        if reason is not None:
            object.__setattr__(self, "reason", reason)

    def add_to_hass(self, hass: HomeAssistant) -> None:
        """Test helper to add entry to hass."""
        hass.config_entries._entries[self.entry_id] = self

    def add_to_manager(self, manager: config_entries.ConfigEntries) -> None:
        """Test helper to add entry to entry manager."""
        manager._entries[self.entry_id] = self
