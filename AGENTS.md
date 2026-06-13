# Repository Guidelines

## Project Structure & Module Organization
Core integration code lives in `custom_components/firewalla/`. Key modules include `api.py` for Firewalla MSP calls, `coordinator.py` for polling and state assembly, `sensor.py` for entities, and `config_flow.py` for UI setup. Tests mirror that layout under `tests/components/firewalla/`. Repository assets are kept in `brand/`, with integration-local branding in `custom_components/firewalla/brand/`. Sample Lovelace dashboards live in `examples/`.

## Build, Test, and Development Commands
Create a local environment and install test tooling:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements_test.txt ruff
```

Run the same checks used in CI:

```powershell
ruff check custom_components tests
python -m compileall custom_components tests
pytest --cov=custom_components.firewalla --cov-report=term-missing --cov-fail-under=90
```

There is no separate build step; this repository ships the custom component directly.

## Coding Style & Naming Conventions
Use 4-space indentation, keep lines within Ruff's 88-character target, and follow existing typed Python patterns. Prefer module-level constants in `UPPER_SNAKE_CASE`, config keys such as `CONF_SCOPE_TYPE`, and descriptive async function names. Match Home Assistant conventions: one integration package under `custom_components/<domain>` and translation strings in `translations/en.json`.

## Testing Guidelines
Pytest is configured in `pyproject.toml` with `asyncio_mode = "auto"` and strict markers. Add tests beside the related module using `test_<module>.py` naming, for example `test_config_flow.py`. Cover parsing, capability fallbacks, entity state and attributes, and config-entry behavior. CI enforces `--cov-fail-under=90`; treat that as the minimum bar for new work.

## Commit & Pull Request Guidelines
Recent history uses short, imperative subjects such as `Icons`, `Release 0.4.4`, and `Update brand icons`. Keep commits focused and concise; use `Release x.y.z` only for version and tag updates. PRs should describe user-visible changes, note any API or entity-model impact, link the relevant issue, and include screenshots or sample entity output when dashboard or diagnostics behavior changes.

## Security & Configuration Tips
Do not commit real MSP base URLs, tokens, or captured diagnostics with sensitive fields. Keep example YAML generic, and preserve the integration's redaction behavior in diagnostics-related changes.

## External Guidance To Follow
Treat Home Assistant's quality scale as a standing bar for changes in this repo. At minimum, preserve Bronze requirements: UI-based setup, automated setup tests, and clear end-user setup docs. Prefer Silver and above when changing runtime behavior: recover cleanly from connection failures, trigger reauthentication on auth errors, avoid noisy logs, keep translations current, and maintain troubleshooting guidance and diagnostics support.

Use Firewalla MSP docs as the primary API reference. Current public docs describe personal access token auth with `Authorization: Token <token>`, MSP endpoints under `/v2/...`, and list-style responses that may include pagination, limits, grouping, and sorting. Because Firewalla's docs explicitly warn the MSP API evolves quickly, verify endpoint behavior against the latest docs before changing request shapes, query parameters, or response parsing.

For fuller repository, Home Assistant, and Firewalla reference notes, see `docs/reference-notes.md`.
