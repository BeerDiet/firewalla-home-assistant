# Reference Notes

## Home Assistant Quality Scale
Source: <https://www.home-assistant.io/docs/quality_scale/>

Use the quality scale as a design and review checklist for this integration.

### Baseline expectations
- Bronze is the minimum standard for new integrations: UI-based setup, basic coding standards, automated setup tests, and end-user setup documentation.
- Silver adds runtime resilience: stable behavior under failure conditions, active code ownership, clean recovery from connection problems, automatic reauthentication on auth failure, and better troubleshooting documentation.
- Gold adds polished UX: discovery when possible, reconfiguration in the UI, translations, stronger end-user documentation, diagnostics, and automated coverage across the full integration.
- Platinum emphasizes technical excellence: fully typed code, fully async behavior, and efficient CPU/network usage.

### Practical rules for this repo
- Keep configuration in the Home Assistant UI through config entries; avoid YAML-only configuration paths.
- Preserve or expand automated coverage for setup, config flow, runtime polling, error handling, diagnostics, and sensor behavior.
- Treat `ConfigEntryAuthFailed`-style reauth behavior and graceful recovery from temporary API failures as required behaviors.
- Keep diagnostics useful but redacted.
- Maintain translations and user-facing names when entities or options change.
- Avoid unnecessary log noise during transient failures.

## Firewalla MSP API
Source: <https://docs.firewalla.net/>

Treat the public MSP docs as the primary API contract, but verify behavior carefully because the docs explicitly warn that the MSP API evolves quickly and documentation may lag.

### Authentication and base shape
- Authentication uses a personal access token in the header: `Authorization: Token <token>`.
- API examples use tenant-specific MSP domains such as `https://mydomain.firewalla.net`.
- Public endpoints shown in the docs are under `/v2/...`.

### Common response and query patterns
- Collection endpoints may support `limit`, `cursor`, `sortBy`, `groupBy`, and `query`.
- Pagination may be returned through fields like `next_cursor`.
- Alarm and box payloads use Firewalla identifiers such as `gid` for box ID and `aid` for alarm ID.

### Current examples reflected in the docs
- `GET /v2/boxes` returns box inventory data such as `gid`, `name`, `model`, `online`, `version`, `deviceCount`, `ruleCount`, and `alarmCount`.
- `GET /v2/alarms` returns paged alarm collections with `count`, `results`, and `next_cursor`.
- `GET /v2/alarms/:gid/:aid` returns detailed alarm data, including nested device and network information when available.
- `DELETE /v2/alarms/:gid/:aid` deletes an alarm.

### Practical rules for this repo
- Do not hard-code undocumented response fields without test coverage around fallbacks.
- Expect optional or missing endpoints and preserve graceful degradation when MSP scope or token permissions limit access.
- Verify endpoint semantics against the latest docs before changing query shapes, pagination behavior, or alarm/box parsing.
- Never commit real tokens, tenant domains, or raw diagnostics that could expose customer data.

## Repo Markdown Context
Based on current repository markdown and config files.

### README takeaways
- The integration is a Home Assistant custom integration for Firewalla MSP data.
- Supported scopes are `global`, `group`, and `box`.
- It creates both aggregate sensors and per-box or per-network sensors when the API provides enough data.
- Installation is via HACS or manual copy into `custom_components/firewalla/`.
- User-facing troubleshooting and diagnostics are part of the supported workflow and should remain documented.

### Development conventions already present
- Linting uses Ruff with an 88-character target and Python 3.13.
- Tests run with `pytest`, `pytest-homeassistant-custom-component`, and a 90% coverage floor in CI.
- The release workflow updates `custom_components/firewalla/manifest.json`, tags a semantic version, and publishes a zip artifact.
