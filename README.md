# Firewalla for Home Assistant

[![Validate](https://github.com/BeerDiet/firewalla-home-assistant/actions/workflows/validate.yml/badge.svg)](https://github.com/BeerDiet/firewalla-home-assistant/actions/workflows/validate.yml)
[![HACS Validation](https://github.com/BeerDiet/firewalla-home-assistant/actions/workflows/hacs.yml/badge.svg)](https://github.com/BeerDiet/firewalla-home-assistant/actions/workflows/hacs.yml)
[![Hassfest](https://github.com/BeerDiet/firewalla-home-assistant/actions/workflows/hassfest.yml/badge.svg)](https://github.com/BeerDiet/firewalla-home-assistant/actions/workflows/hassfest.yml)
[![Release](https://github.com/BeerDiet/firewalla-home-assistant/actions/workflows/release.yml/badge.svg)](https://github.com/BeerDiet/firewalla-home-assistant/actions/workflows/release.yml)
[![HACS](https://img.shields.io/badge/HACS-Custom%20Integration-41BDF5.svg)](https://hacs.xyz/)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Compatible-03A9F4.svg)](https://www.home-assistant.io/)
[![License](https://img.shields.io/github/license/BeerDiet/firewalla-home-assistant)](LICENSE)
[![Latest Release](https://img.shields.io/github/v/release/BeerDiet/firewalla-home-assistant)](https://github.com/BeerDiet/firewalla-home-assistant/releases)

Custom Home Assistant integration for Firewalla MSP API data.

This integration connects to a Firewalla MSP endpoint with a personal access token, detects the capabilities exposed by the configured scope, and exposes sensor entities for:

- Blocked flows, alarms, and rules
- Online and offline box counts
- Current alarms and rules
- Top-region statistics
- Main-device aggregate download/upload traffic
- Per-box security/activity sensors
- Per-box top-talker list sensors with ranked download and upload attributes
- Per-network download/upload traffic under each box device
- Rule-backed internet block switches for devices and local networks
- Config-entry API usage metrics, including the current daily call tally, the current limit, and the active adaptive scan interval

## Sensors created

The integration creates sensors in two places when `global` or `group` scope is used. The config and options dialogs also show the current API call tally, the daily request limit, and the active adaptive scan interval for the entry:

Main integration device:

- `Blocked Flows`
- `Alarms`
- `Rule Activity`
- `Online Boxes`
- `Offline Boxes`
- `Current Alarms`
- `Current Rules`
- `Current API Calls Today`
- `Daily API Usage Limit`
- `Current Scan Interval`
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
- `<Box Name> Top Talkers`

Per-box network sensors:

Under each Firewalla box device, the integration also creates:

- `<Network Name> Download Recent Volume`
- `<Network Name> Upload Recent Volume`
- `<Network Name> Download Mbps`
- `<Network Name> Upload Mbps`

Switches created:

For each Firewalla device and local network returned by the API, the integration creates:

- `<Device Name> Internet Block`
- `<Network Name> Internet Block`

Notes:

- Per-box devices are deduplicated by Firewalla `gid`, so a box is only added once even if multiple grouped flow rows refer to it.
- Per-box network sensors are only created when grouped flow and device data are available.
- Per-box `Top Talkers` sensors expose ranked upload and download device lists in attributes for that box over the configured traffic window.
- Device and network internet block entities are implemented as Firewalla rules with an `internet` target. They do not physically disable a NIC, VLAN, or WAN/LAN interface.
- Network names are automatically qualified when duplicate names exist across boxes.
- Some sensor groups may remain unavailable when the configured scope or token cannot access the required endpoint.

## Scope model

The integration supports three scopes:

- `global`: Query the entire MSP tenant
- `group`: Query a Firewalla group
- `box`: Query a single Firewalla box by `gid`

The configured scope affects which sensors can exist:

- `global` and `group` scopes can expose main-device aggregate sensors plus one device per Firewalla box returned by the API
- Each Firewalla box returned by the API can expose per-box security/activity sensors, per-box top-talker sensors, per-network bandwidth sensors, device internet-block switches, and network internet-block switches
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
   - A daily API request limit
   - Whether SSL verification should be enabled
5. The config and options dialogs also show the current API call tally, the daily request limit, and the current adaptive scan interval for the entry.

## Configuration reference

- `Name`: Display name used for the config entry and suggested entity IDs.
- `Firewalla base URL`: The MSP endpoint URL for your tenant, such as `https://example.firewalla.net`.
- `Personal access token`: Token used for all API requests.
- `Scope type`: `global`, `group`, or `box`.
- `Scope ID`: Required for `group` and `box` scopes. For box scope, this is the Firewalla `gid`.
- `Daily API request limit`: Maximum number of Firewalla API requests the entry should budget per day. The default is `3000`, which is Firewalla's current imposed limit.
- `Traffic window`: Rolling grouped-flow window used for recent-volume and Mbps sensors. Allowed values: `1`, `5`, `15`, or `30` minutes.
- `Verify SSL`: Enables TLS certificate validation for the MSP endpoint.

The reconfigure and options dialogs also display:

- `Current API calls today`
- `Current Scan Interval`

## Options

After setup, the integration options let you change:

- `Daily API request limit`
- `Traffic window`

You can also use the Home Assistant reconfigure flow on an existing Firewalla entry to change the base URL, token, scope type, scope ID, or SSL setting without removing and re-adding the integration.

## Supported functions

The integration currently exposes these Home Assistant features:

- Box-level sensors for blocked flows, alarms, current alarms, and top talkers
- Main integration sensors for blocked flows, alarms, rules, box counts, recent traffic, top-region statistics, current API calls, the daily API usage limit, and the adaptive scan interval
- Per-box network throughput sensors for download volume, upload volume, download Mbps, and upload Mbps
- Internet-block switches for client devices and local networks returned by the API
- Config-entry API usage metrics for the current daily call tally, the daily request limit, and the adaptive scan interval
- Diagnostics that include scope, capabilities, endpoint errors, and redacted runtime data
- Reauthentication and reconfiguration flows for updating the connection without removing the entry

What is not exposed:

- Physical interface disable/enable for boxes, devices, or networks
- Discovery-based onboarding
- Firmware updates or other device-management actions
- Write actions beyond the rule-backed internet block switches

## Supported devices

Supported Firewalla setups are the MSP API scopes that can return data for the configured token:

- `global`: the whole MSP tenant
- `group`: a Firewalla group within the tenant
- `box`: a single Firewalla box by `gid`

The integration is built around the box objects returned by the API:

- Each Firewalla box becomes a Home Assistant device
- Client devices returned under a box are represented as switches attached to the parent box device, not as separate Home Assistant devices
- Networks returned under a box are represented as sensors attached to the parent box device

Not every scope can populate every entity type:

- Box scope is narrower and may not expose global trends or box-level rollups
- Global and group scopes can expose the full set of box and network entities when the MSP API returns the relevant data
- If Firewalla does not return the required endpoint data, the integration keeps the entities that it can support and marks the rest unavailable

## Known Limitations

- There is no discovery path by design
- Internet blocking is rule-based and does not physically disable an interface
- The top-talker lists are based on the configured rolling traffic window, not on a live instantaneous counter
- The recent-volume sensors show rolling byte totals for the configured window, not a cumulative lifetime total
- Some entity groups depend on optional Firewalla endpoints; if the token or scope cannot read those endpoints, those entities will not appear
- The integration only manages data exposed by the Firewalla MSP API; it cannot change firewall behavior outside that API

## Use Cases

Common day-to-day uses for this integration:

- Check which boxes are online and whether any are offline
- Watch blocked-flow and alarm trends over time
- See which devices are using the most download or upload bandwidth in the selected traffic window
- Block a device from the internet temporarily without deleting it from Firewalla
- Block a local network from internet access while leaving the rest of the box available
- Inspect per-box network throughput when troubleshooting a noisy segment
- Compare the same metric across multiple boxes in a group or across the tenant

## Supported Devices and Functions

The following entities are created when the API exposes the required data:

- Main integration sensors: blocked flows, alarms, rules, box counts, top-region stats, recent traffic, current API calls, daily API usage limit, and adaptive scan interval
- Per-box sensors: blocked flows, alarms, current alarms, and top talkers
- Per-box network sensors: download volume, upload volume, download Mbps, and upload Mbps
- Per-box switches: device internet block and network internet block

The integration does not create:

- Separate Home Assistant devices for Firewalla client devices
- Network-level physical controls
- User-visible discovery onboarding flows

## Notes

- This integration uses config entries and is configured entirely in the UI.
- Sensors are based on the Firewalla MSP API and depend on the data your token and scope can access.
- Per-network bandwidth sensors are created dynamically from network data returned by the API and are attached to the owning box device.
- Device and network internet-block switches are created dynamically from device and network data returned by the API and are backed by Firewalla MSP rules.
- Device internet-block switches are attached to the owning Firewalla box device. The integration does not create separate Home Assistant devices for client devices returned by the API.
- Aggregate throughput sensors on the main integration device are derived from grouped flow data over the integration's recent traffic window.
- Each box gets a `Top Talkers` sensor. Its state is the number of ranked devices for that box, and its attributes expose `download_ranked_devices` and `upload_ranked_devices`.
- The legacy `*_last_5m` entity IDs are retained for compatibility, but they now represent the current recent-volume window exposed by the integration.
- `Download Recent Volume` and `Upload Recent Volume` sensors are rolling byte totals over the configured recent traffic window, not instantaneous throughput. Their state is shown in `GB`, and the raw byte totals remain available in attributes like `raw_download_bytes` and `raw_upload_bytes`.
- Check each sensor's `window_seconds` attribute for the exact rolling period used by the current version.
- Check each sensor's `window_minutes` attribute for the configured rolling period in minutes.
- The recent traffic window is configurable to `1`, `5`, `15`, or `30` minutes in the integration options.
- Top-talker sensors rank devices separately for download and upload. Their state is the number of known devices in the box-level list, while the `download_ranked_devices` and `upload_ranked_devices` attributes carry the ordered lists.

## Data Update

The integration polls Firewalla on an adaptive interval derived from the configured daily API request limit and the current API calls already made that day.

The current scan interval is recalculated as usage changes and is shown in the integration's reconfigure and options dialogs.

On each refresh it attempts to load, in order:

- boxes
- trends
- simple stats
- top stats
- rules
- devices
- grouped flows
- flow pages for top talkers

The configured `Traffic window` controls the grouped-flow query used for:

- recent volume sensors
- Mbps sensors
- per-box top talker lists

Top talkers are built from the aggregated flow records returned for the current scope. The integration keeps every known device in the box-level list and exposes both upload and download rankings as attributes.

If Firewalla temporarily returns an error for an optional endpoint:

- the integration logs the failure once
- it keeps any other data it could load
- it recovers automatically when the endpoint starts working again

If the API is unavailable long enough that no data can be loaded:

- the integration returns a degraded payload instead of crashing
- auth failures trigger Home Assistant reauthentication

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
- `already_configured` during reconfigure:
  The new base URL and scope combination already belongs to another Firewalla entry.
- Missing some per-box sensors:
  This can be expected if the MSP API does not expose matching box-level data for that metric. Per-box network bandwidth depends on grouped flow plus device/network data.
- Missing top-talker lists or internet-block switches:
  These depend on Firewalla returning the device, flow, and rule data needed for the configured scope. Check diagnostics for `capabilities`, `devices`, `device_traffic`, `rules`, and `endpoint_errors`.
- Missing `Top Talkers` on a box:
  Check that the box has grouped-flow data for the current traffic window and that the `top_talkers` capability is `true` in diagnostics.
- Internet-block switch changes do not stick:
  Confirm the token can read and write Firewalla rules for the configured scope and that no other rule with the same target is managed outside Home Assistant.
- Missing some entity groups for a global or group scope:
  The integration degrades gracefully when optional Firewalla endpoints return `403`, `404`, or other endpoint-specific failures. Check diagnostics for `capabilities` and `endpoint_errors`.
- Recent-traffic values look too small or too large:
  Check the configured `Traffic window` in the integration options. The sensors report rolling totals for that window, not a lifetime total.
- Device names look wrong in the block switches:
  Firewalla supplies the entity names from the device and network names returned by the API. If the name is stale there, refresh the Firewalla inventory first.
- SSL verification failures:
  If your MSP endpoint uses a private or invalid certificate, either fix the certificate chain or disable `Verify SSL` for that config entry.

## Sample dashboards

Example dashboards are included in [`examples/`](./examples):

- [`dashboard-basic.yaml`](./examples/dashboard-basic.yaml) uses built-in Lovelace cards only and focuses on the main integration device sensors.
- [`dashboard-mini-graph.yaml`](./examples/dashboard-mini-graph.yaml) uses `mini-graph-card` for historical throughput charts on the main integration device sensors.
- [`card-top-talkers.yaml`](./examples/card-top-talkers.yaml) is a standalone example for rendering the per-box `download_ranked_devices` and `upload_ranked_devices` attributes as readable lists.
- [`dashboard-basic.yaml`](./examples/dashboard-basic.yaml) includes example top-talker rendering for the main box sensor.
- [`dashboard-mini-graph.yaml`](./examples/dashboard-mini-graph.yaml) shows how to mix traffic charts with the box-level top-talker summary.

These examples are intentionally generic and optional. They are not installed by the integration and can be adapted to your own dashboard structure.

Notes for the examples:

- The example entity IDs assume a default global-scope entry, which produces entities like `sensor.firewalla_download_mbps`, `sensor.firewalla_download_last_5m`, and `sensor.firewalla_rules`. If you use a scoped entry, Home Assistant appends the scope to the object ID, for example `sensor.firewalla_download_mbps_group_branch`.
- `sensor.firewalla_rules` is recent `Rule Activity`, not your configured rule count. Use `sensor.firewalla_current_rules` when you want the current total.
- Recent-volume entities should be labeled generically as `Recent Volume`, with the active range read from each entity's `window_minutes` attribute or from your configured integration option.
- Wired, wireless, and WireGuard sensors now live under each Firewalla box device when the API exposes those networks.
- Per-box top-talker sensors and device/network block switches are dynamic. Replace the sample box, device, or network entity IDs with ones from your own Home Assistant instance.
- The top-talker card examples use `sensor.firewalla_branch_box_top_talkers` as a placeholder. Replace that with the actual top-talker sensor for your box device.
- The top-talkers card expects a box sensor and reads the `download_ranked_devices` and `upload_ranked_devices` attributes from that entity.

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
