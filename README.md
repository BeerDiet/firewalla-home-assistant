# Firewalla for Home Assistant

Custom Home Assistant integration for Firewalla MSP API data.

This integration connects to a Firewalla MSP endpoint with a personal access token, detects the capabilities exposed by the configured scope, and exposes sensor entities for:

- Blocked flows, alarms, and rules
- Online and offline box counts
- Current alarms and rules
- Top-box and top-region statistics
- Aggregate download/upload traffic
- Per-network download/upload traffic

## Scope model

The integration supports three scopes:

- `global`: Query the entire MSP tenant
- `group`: Query a Firewalla group
- `box`: Query a single Firewalla box by `gid`

The configured scope affects which sensors can exist:

- `global` and `group` scopes can expose trend, simple-stat, top-stat, aggregate bandwidth, and per-network bandwidth sensors
- `box` scope can expose aggregate bandwidth and per-network bandwidth sensors
- `box` scope does not create trend or top-stat sensors because the MSP API does not expose those endpoints per box

During setup and updates, the integration records endpoint capabilities and degrades gracefully when optional endpoints are unavailable. That means a token or scope that cannot use one endpoint can still load and publish the sensors supported by the remaining endpoints.

## Installation

### HACS

1. Open HACS in Home Assistant.
2. Add this repository as a custom repository.
3. Choose the `Integration` category.
4. Install `Firewalla`.
5. Restart Home Assistant.

### Manual

1. Delete any existing `custom_components/firewalla` directory first.
2. Copy `custom_components/firewalla` into your Home Assistant `custom_components/` directory.
3. Restart Home Assistant.

## Upgrades

- HACS upgrades should be done from a tagged release, followed by a Home Assistant restart.
- Manual upgrades should always replace the whole `custom_components/firewalla` directory, not patch individual files.
- If a manual upgrade behaves strangely, delete `custom_components/firewalla`, copy the new folder fresh, and restart Home Assistant.
- Diagnostics now include `integration_version`, `diagnostics_version`, and `package_path` so you can verify exactly which code Home Assistant is running.

## Configuration

1. In Home Assistant, go to `Settings` -> `Devices & Services`.
2. Click `Add Integration`.
3. Search for `Firewalla`.
4. Enter:
   - A display name
   - Your Firewalla base URL
   - Your personal access token
   - A scope type: `global`, `group`, or `box`
   - An optional scope ID for `group` or `box` scopes
   - Scan interval
   - Whether SSL verification should be enabled

## Notes

- This integration uses config entries and is configured entirely in the UI.
- Sensors are based on the Firewalla MSP API and depend on the data your token and scope can access.
- Per-network bandwidth sensors are created dynamically from network data returned by the API.
- Aggregate and per-network throughput sensors are derived from grouped flow data over the integration's recent traffic window.
- The legacy `*_last_5m` entity IDs are retained for compatibility, but they now represent the current recent-volume window exposed by the integration.
- `Download Volume (15m)` and `Upload Volume (15m)` sensors are rolling byte totals over the recent traffic window, not instantaneous throughput. Their state is shown in `GB`, and the raw byte totals remain available in attributes like `raw_download_bytes` and `raw_upload_bytes`.
- Check each sensor's `window_seconds` attribute for the exact rolling period used by the current version.

## Capability diagnostics

The diagnostics payload includes:

- normalized config entry data
- scope metadata
- endpoint capability flags
- endpoint errors for unsupported or failed optional calls
- the latest redacted coordinator data

This makes it easier to understand why a given MSP tenant or scope exposes only a subset of sensors.

## Sample dashboards

Example dashboards are included in [`examples/`](./examples):

- [`dashboard-basic.yaml`](./examples/dashboard-basic.yaml) uses built-in Lovelace cards only and sticks to aggregate Internet sensors so it works across `global`, `group`, and `box` scopes.
- [`dashboard-mini-graph.yaml`](./examples/dashboard-mini-graph.yaml) uses `mini-graph-card` for historical throughput charts and the same aggregate Internet sensors for maximum scope compatibility.

These examples are intentionally generic and optional. They are not installed by the integration and can be adapted to your own dashboard structure.

Notes for the examples:

- `sensor.firewalla_rules` is `Rule Activity`, not your configured rule count. Use `sensor.firewalla_current_rules` when you want the current total.
- The retained `sensor.firewalla_*_last_5m` entity IDs now represent the integration's rolling recent-volume window and should be labeled as `Volume (15m)` in dashboards.
- Wired, wireless, and WireGuard sensors are scope-dependent. Add them only if your configured Firewalla scope actually exposes those entities.

## Development

Repository structure follows Home Assistant custom integration conventions and includes:

- `custom_components/firewalla/`
- `tests/components/firewalla/`
- `hacs.json`

The test suite covers:

- config-flow validation and scope handling
- API payload parsing and error mapping
- coordinator capability detection and graceful degradation
- sensor availability and attribute behavior across supported scopes
- config entry migration and diagnostics output

## Support

- Issues: <https://github.com/BeerDiet/firewalla-home-assistant/issues>
- Source: <https://github.com/BeerDiet/firewalla-home-assistant>
