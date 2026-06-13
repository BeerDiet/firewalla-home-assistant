# Firewalla for Home Assistant

Custom Home Assistant integration for Firewalla MSP API data.

This integration connects to a Firewalla MSP endpoint with a personal access token, detects the capabilities exposed by the configured scope, and exposes sensor entities for:

- Blocked flows, alarms, and rules
- Online and offline box counts
- Current alarms and rules
- Top-region statistics
- Main-device aggregate download/upload traffic
- Per-box security/activity sensors
- Per-network download/upload traffic under each box device

## Sensors created

The integration creates sensors in two places when `global` or `group` scope is used:

Main integration device:

- `Blocked Flows`
- `Alarms`
- `Rule Activity`
- `Online Boxes`
- `Offline Boxes`
- `Current Alarms`
- `Current Rules`
- `Top Box Blocked Flows`
- `Top Box Security Alarms`
- `Top Region Blocked Flows`
- `Download Recent Volume`
- `Upload Recent Volume`
- `Download Mbps`
- `Upload Mbps`

Per-box devices:

For each Firewalla box returned in the selected global or group scope, the integration creates:

- `<Box Name> Blocked Flows`
- `<Box Name> Alarms`
- `<Box Name> Current Alarms`

Per-box network sensors:

Under each Firewalla box device, the integration also creates:

- `<Network Name> Download Recent Volume`
- `<Network Name> Upload Recent Volume`
- `<Network Name> Download Mbps`
- `<Network Name> Upload Mbps`

Notes:

- Per-box devices are deduplicated by Firewalla `gid`, so a box is only added once even if multiple grouped flow rows refer to it.
- Per-box network sensors are only created when grouped flow and device data are available.
- Network names are automatically qualified when duplicate names exist across boxes.
- Some sensor groups may remain unavailable when the configured scope or token cannot access the required endpoint.

## Scope model

The integration supports three scopes:

- `global`: Query the entire MSP tenant
- `group`: Query a Firewalla group
- `box`: Query a single Firewalla box by `gid`

The configured scope affects which sensors can exist:

- `global` and `group` scopes can expose main-device aggregate sensors plus one device per discovered Firewalla box
- Each discovered box device can expose per-box security/activity sensors and per-network bandwidth sensors
- `box` scope behavior is narrower and depends on the MSP API responses for that specific box

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

## Configuration reference

- `Name`: Display name used for the config entry and suggested entity IDs.
- `Firewalla base URL`: The MSP endpoint URL for your tenant, such as `https://example.firewalla.net`.
- `Personal access token`: Token used for all API requests.
- `Scope type`: `global`, `group`, or `box`.
- `Scope ID`: Required for `group` and `box` scopes. For box scope, this is the Firewalla `gid`.
- `Scan interval`: Polling interval in seconds. Allowed range: `60` to `3600`.
- `Traffic window`: Rolling grouped-flow window used for recent-volume and Mbps sensors. Allowed values: `1`, `5`, `15`, or `30` minutes.
- `Verify SSL`: Enables TLS certificate validation for the MSP endpoint.

## Options

After setup, the integration options let you change:

- `Scan interval`
- `Traffic window`

## Notes

- This integration uses config entries and is configured entirely in the UI.
- Sensors are based on the Firewalla MSP API and depend on the data your token and scope can access.
- Per-network bandwidth sensors are created dynamically from network data returned by the API and are attached to the owning box device.
- Aggregate throughput sensors on the main integration device are derived from grouped flow data over the integration's recent traffic window.
- The legacy `*_last_5m` entity IDs are retained for compatibility, but they now represent the current recent-volume window exposed by the integration.
- `Download Recent Volume` and `Upload Recent Volume` sensors are rolling byte totals over the configured recent traffic window, not instantaneous throughput. Their state is shown in `GB`, and the raw byte totals remain available in attributes like `raw_download_bytes` and `raw_upload_bytes`.
- Check each sensor's `window_seconds` attribute for the exact rolling period used by the current version.
- Check each sensor's `window_minutes` attribute for the configured rolling period in minutes.
- The recent traffic window is configurable to `1`, `5`, `15`, or `30` minutes in the integration options.

## Capability diagnostics

The diagnostics payload includes:

- normalized config entry data
- scope metadata
- endpoint capability flags
- endpoint errors for unsupported or failed optional calls
- the latest redacted coordinator data

This makes it easier to understand why a given MSP tenant or scope exposes only a subset of sensors.

## Troubleshooting

- `invalid_auth` during setup or runtime:
  Update the personal access token from the integration reauthentication flow when Home Assistant prompts for it.
- `cannot_connect`:
  Confirm the base URL is reachable from Home Assistant, the MSP endpoint is online, and any reverse proxy or firewall rules allow the request.
- `unknown_box`:
  The configured box `gid` does not exist in the tenant visible to the provided token.
- Missing some per-box sensors:
  This can be expected if the MSP API does not expose matching box-level data for that metric. Per-box network bandwidth depends on grouped flow plus device/network data.
- Missing some entity groups for a global or group scope:
  The integration degrades gracefully when optional Firewalla endpoints return `403`, `404`, or other endpoint-specific failures. Check diagnostics for `capabilities` and `endpoint_errors`.
- SSL verification failures:
  If your MSP endpoint uses a private or invalid certificate, either fix the certificate chain or disable `Verify SSL` for that config entry.

## Sample dashboards

Example dashboards are included in [`examples/`](./examples):

- [`dashboard-basic.yaml`](./examples/dashboard-basic.yaml) uses built-in Lovelace cards only and focuses on the main integration device sensors.
- [`dashboard-mini-graph.yaml`](./examples/dashboard-mini-graph.yaml) uses `mini-graph-card` for historical throughput charts on the main integration device sensors.

These examples are intentionally generic and optional. They are not installed by the integration and can be adapted to your own dashboard structure.

Notes for the examples:

- The example entity IDs assume a default global-scope entry, which produces entities like `sensor.firewalla_download_mbps`, `sensor.firewalla_download_last_5m`, and `sensor.firewalla_rules`. If you use a scoped entry, Home Assistant appends the scope to the object ID, for example `sensor.firewalla_download_mbps_group_branch`.
- `sensor.firewalla_rules` is recent `Rule Activity`, not your configured rule count. Use `sensor.firewalla_current_rules` when you want the current total.
- Recent-volume entities should be labeled generically as `Recent Volume`, with the active range read from each entity's `window_minutes` attribute or from your configured integration option.
- Wired, wireless, and WireGuard sensors now live under each Firewalla box device when the API exposes those networks.

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
