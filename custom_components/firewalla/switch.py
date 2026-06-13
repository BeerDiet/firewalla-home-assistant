"""Switch platform for Firewalla device internet blocking."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import FirewallaApiAuthError, FirewallaApiError
from .const import DOMAIN, SCOPE_BOX, SCOPE_GROUP

_RULE_NOTES_PREFIX = "Firewalla Home Assistant internet block"


def _slugify(value: str) -> str:
    """Convert an arbitrary string into an entity-id-safe slug fragment."""
    return "".join(char if char.isalnum() else "_" for char in value.lower()).strip("_")


@dataclass(frozen=True, kw_only=True)
class FirewallaSwitchDescription(SwitchEntityDescription):
    """Describe a Firewalla switch."""


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    """Set up Firewalla switches."""
    coordinator = entry.runtime_data
    entities: list[FirewallaRuleSwitch] = []
    devices = coordinator.data.get("devices", [])
    if not isinstance(devices, list):
        devices = []

    for device in devices:
        if not isinstance(device, dict):
            continue
        device_id = str(device.get("id") or "").strip()
        device_gid = str(device.get("gid") or "").strip()
        device_name = str(device.get("name") or device_id).strip()
        if not device_id or not device_gid or not device_name:
            continue
        entities.append(
            FirewallaDeviceInternetBlockSwitch(
                coordinator,
                entry,
                device_gid,
                device_id,
                device_name,
            )
        )

    networks = coordinator.data.get("networks", {})
    if isinstance(networks, dict):
        for network_key, network in networks.items():
            if not isinstance(network, dict):
                continue
            network_id = str(network.get("id") or "").strip()
            network_name = str(
                network.get("display_name") or network.get("name") or network_id
            ).strip()
            box_gid = str(network.get("gid") or "").strip()
            if not network_id or not network_name or not box_gid:
                continue
            entities.append(
                FirewallaNetworkInternetBlockSwitch(
                    coordinator,
                    entry,
                    box_gid,
                    network_key,
                    network_id,
                    network_name,
                    str(network.get("type") or "").strip() or None,
                )
            )

    async_add_entities(entities)


class FirewallaRuleSwitch(CoordinatorEntity, SwitchEntity):
    """Shared rule-backed switch behavior."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry, box_gid: str) -> None:
        """Initialize the base switch."""
        super().__init__(coordinator)
        self._entry = entry
        self._box_gid = box_gid

    @property
    def available(self) -> bool:
        """Return whether the switch is available."""
        capabilities = self.coordinator.data.get("capabilities", {})
        if not isinstance(capabilities, dict):
            return False
        return bool(capabilities.get("rules"))

    def _rules(self) -> list[dict[str, object]]:
        """Return cached rules."""
        rules = self.coordinator.data.get("rules", [])
        if isinstance(rules, list):
            return [rule for rule in rules if isinstance(rule, dict)]
        return []

    def _rule_target_matches(self, rule: dict[str, object]) -> bool:
        """Return whether a rule matches the internet target."""
        target = rule.get("target", {})
        if not isinstance(target, dict):
            return False
        if str(target.get("type") or "") != "internet":
            return False
        value = target.get("value")
        return value in (None, "")

    def _rule_owner_matches(self, rule: dict[str, object]) -> bool:
        """Return whether a rule is owned by the same box or group."""
        if self.coordinator.scope_type == SCOPE_GROUP and self.coordinator.scope_id:
            return str(rule.get("group") or "").strip() == self.coordinator.scope_id
        if self.coordinator.scope_type == SCOPE_BOX and self.coordinator.scope_id:
            return str(rule.get("gid") or "").strip() == self.coordinator.scope_id
        return str(rule.get("gid") or "").strip() == self._box_gid

    def _rule_scope_matches(self, rule: dict[str, object]) -> bool:
        """Return whether a rule matches this entity."""
        raise NotImplementedError

    def _matching_rule(self) -> dict[str, object] | None:
        """Return the matching internet-block rule if present."""
        for rule in self._rules():
            if str(rule.get("action") or "") != "block":
                continue
            if not self._rule_owner_matches(rule):
                continue
            if not self._rule_scope_matches(rule):
                continue
            if not self._rule_target_matches(rule):
                continue
            notes = str(rule.get("notes") or "")
            if notes and not notes.startswith(_RULE_NOTES_PREFIX):
                continue
            return rule
        return None

    def _create_rule_payload(self) -> dict[str, object]:
        """Return the payload used to create the matching rule."""
        raise NotImplementedError

    @property
    def is_on(self) -> bool | None:
        """Return whether the entity is blocked from the internet."""
        rule = self._matching_rule()
        if not rule:
            return False
        return str(rule.get("status") or "") == "active"

    async def _async_apply_rule(self, on: bool) -> None:
        """Create, resume, or pause the matching rule."""
        rule = self._matching_rule()
        try:
            if on:
                if rule and str(rule.get("status") or "") == "paused":
                    await self.coordinator.client.async_resume_rule(str(rule["id"]))
                elif not rule:
                    await self.coordinator.client.async_create_rule(
                        self._create_rule_payload()
                    )
            elif rule and str(rule.get("status") or "") == "active":
                await self.coordinator.client.async_pause_rule(str(rule["id"]))
        except FirewallaApiAuthError as err:
            raise HomeAssistantError("Firewalla authentication failed") from err
        except FirewallaApiError as err:
            raise HomeAssistantError(f"Firewalla rule update failed: {err}") from err

        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs) -> None:
        """Enable internet blocking for the device."""
        await self._async_apply_rule(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Disable internet blocking for the device."""
        await self._async_apply_rule(False)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated coordinator data."""
        self.async_write_ha_state()


class FirewallaDeviceInternetBlockSwitch(FirewallaRuleSwitch):
    """Represent a device internet-block rule."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        box_gid: str,
        device_id: str,
        device_name: str,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, entry, box_gid)
        self._device_id = device_id
        self._device_name = device_name
        self._attr_name = "Internet Block"
        self._attr_unique_id = (
            f"{entry.entry_id}_device_internet_block_{box_gid}_{device_id}"
        )
        self._attr_suggested_object_id = (
            f"firewalla_{_slugify(box_gid)}_{_slugify(device_id)}_internet_block"
        )
        self._attr_entity_description = FirewallaSwitchDescription(
            key="internet_block",
            name="Internet Block",
            icon="mdi:earth-off",
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device metadata."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_device_{self._box_gid}_{self._device_id}")},
            name=f"Firewalla {self._device_name}",
            manufacturer="Firewalla",
            model="MSP Device",
            configuration_url=self.coordinator.client.base_url,
        )

    def _rule_scope_matches(self, rule: dict[str, object]) -> bool:
        """Return whether a rule matches this device."""
        scope = rule.get("scope", {})
        if not isinstance(scope, dict):
            return False
        if str(scope.get("type") or "") != "device":
            return False
        return str(scope.get("value") or "").strip() == self._device_id

    def _create_rule_payload(self) -> dict[str, object]:
        """Return the payload used to create the device rule."""
        return {
            "action": "block",
            "direction": "bidirection",
            **(
                {"group": self.coordinator.scope_id}
                if self.coordinator.scope_type == SCOPE_GROUP
                and self.coordinator.scope_id
                else {"gid": self.coordinator.scope_id or self._box_gid}
            ),
            "notes": f"{_RULE_NOTES_PREFIX}: {self._device_name}",
            "target": {"type": "internet"},
            "scope": {"type": "device", "value": self._device_id},
        }

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return switch attributes."""
        rule = self._matching_rule()
        return {
            "device_id": self._device_id,
            "device_name": self._device_name,
            "box_gid": self._box_gid,
            "rule_id": rule.get("id") if isinstance(rule, dict) else None,
            "rule_status": rule.get("status") if isinstance(rule, dict) else None,
            "rule_notes": rule.get("notes") if isinstance(rule, dict) else None,
        }


class FirewallaNetworkInternetBlockSwitch(FirewallaRuleSwitch):
    """Represent a network internet-block rule."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        box_gid: str,
        network_key: str,
        network_id: str,
        network_name: str,
        network_type: str | None,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, entry, box_gid)
        self._network_key = network_key
        self._network_id = network_id
        self._network_name = network_name
        self._network_type = network_type
        self._attr_name = "Internet Block"
        self._attr_unique_id = (
            f"{entry.entry_id}_network_internet_block_{network_key}"
        )
        self._attr_suggested_object_id = (
            f"firewalla_{_slugify(network_key)}_internet_block"
        )
        self._attr_entity_description = FirewallaSwitchDescription(
            key="internet_block",
            name="Internet Block",
            icon="mdi:lan-disconnect",
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return network metadata."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_network_{self._network_key}")},
            name=f"Firewalla {self._network_name}",
            manufacturer="Firewalla",
            model=self._network_type or "MSP Network",
            configuration_url=self.coordinator.client.base_url,
            via_device=(DOMAIN, f"{self._entry.entry_id}_box_{self._box_gid}"),
        )

    def _rule_scope_matches(self, rule: dict[str, object]) -> bool:
        """Return whether a rule matches this network."""
        scope = rule.get("scope", {})
        if not isinstance(scope, dict):
            return False
        if str(scope.get("type") or "") != "network":
            return False
        return str(scope.get("value") or "").strip() == self._network_id

    def _create_rule_payload(self) -> dict[str, object]:
        """Return the payload used to create the network rule."""
        return {
            "action": "block",
            "direction": "bidirection",
            **(
                {"group": self.coordinator.scope_id}
                if self.coordinator.scope_type == SCOPE_GROUP
                and self.coordinator.scope_id
                else {"gid": self.coordinator.scope_id or self._box_gid}
            ),
            "notes": f"{_RULE_NOTES_PREFIX}: {self._network_name}",
            "target": {"type": "internet"},
            "scope": {"type": "network", "value": self._network_id},
        }

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return switch attributes."""
        rule = self._matching_rule()
        return {
            "network_key": self._network_key,
            "network_id": self._network_id,
            "network_name": self._network_name,
            "network_type": self._network_type,
            "box_gid": self._box_gid,
            "rule_id": rule.get("id") if isinstance(rule, dict) else None,
            "rule_status": rule.get("status") if isinstance(rule, dict) else None,
            "rule_notes": rule.get("notes") if isinstance(rule, dict) else None,
        }
