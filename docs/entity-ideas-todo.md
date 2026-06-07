# Entity Ideas TODO

## High Priority
- Add per-device online `binary_sensor` entities from `GET /v2/devices`.
- Add per-device total download `sensor` entities from `GET /v2/devices`.
- Add per-device total upload `sensor` entities from `GET /v2/devices`.
- Add per-device reserved-IP `binary_sensor` entities from `GET /v2/devices`.
- Expose per-device `lastSeen`, `macVendor`, `network`, and `group` as attributes or dedicated entities where useful.

## Medium Priority
- Add box online `binary_sensor` entities from `GET /v2/boxes`.
- Add box version `sensor` entities from `GET /v2/boxes`.
- Add box public IP `sensor` entities from `GET /v2/boxes`.
- Add box last-seen `sensor` entities from `GET /v2/boxes`.
- Decide whether box `model`, `mode`, and `location` should be standalone entities or device attributes.

## Analytical / Derived Entities
- Add daily blocked-flow trend sensors from `GET /v2/trends/flows`.
- Add daily alarm trend sensors from `GET /v2/trends/alarms`.
- Add daily rule-creation trend sensors from `GET /v2/trends/rules`.
- Add rule summary sensors from `GET /v2/rules`, such as block vs allow counts.
- Explore grouped flow-based sensors for top domains, categories, or regions using Firewalla query syntax.

## Lower Priority
- Add active alarm count by alarm type from `GET /v2/alarms`.
- Add target-list count or summary sensors from `GET /v2/target-lists`.
- Explore additional top-list sensors backed by Firewalla statistics and grouped queries.

## Notes
- Prefer attributes over standalone entities when the value is mostly descriptive metadata.
- Name network sensors as `<box name>-<network name>-<metric>`.
- Verify endpoint scope support and permission behavior before implementation.
- Preserve graceful degradation when endpoints are unavailable or partially accessible.
