# WaveOS Plugin Marketplace (V3)

This document describes how to package, publish, and certify plugins for the WaveOS control-plane OS.

## Plugin packaging

- Plugins are discovered via **entry points** (e.g. `waveos.plugins`) in `pyproject.toml` or `setup.cfg`.
- Each plugin must expose **PluginMetadata** (name, kind, version, description).
- Supported **PluginKind** values: `collector`, `actuator`, `policy`, `adapter`, `custom`.

Example in your package:

```toml
[project.entry-points."waveos.plugins"]
my_plugin = "my_package.waveos_plugin:PLUGIN_METADATA"
```

## Certification checklist

- [ ] Implements the correct interface for the declared kind (e.g. collector returns records, actuator executes actions).
- [ ] No hardcoded secrets; use WaveOS secrets provider or env.
- [ ] Logging via `waveos.utils.get_logger(__name__)`; no PII in logs.
- [ ] Documented configuration (env vars and config file keys).
- [ ] Compatible with WaveOS schema version and device API (if applicable).

## Device adapters

- Device drivers register under **DeviceCapability** (e.g. `charger`, `inverter`, `bess`) and a vendor key.
- Implement **DeviceDriver** (list_devices, get_telemetry, send_command) and register via `register_driver()`.
- For V3 zero-trust, use **DeviceIdentity** (device_id, credential_hint) where supported.

## Distribution

- Distribute via PyPI or private index; WaveOS discovers plugins in the environment.
- For air-gapped sites, ship wheels and config in a signed bundle; use `waveos bundle build` and attestation (V3).

See [V2_ROADMAP.md](V2_ROADMAP.md) and [V3_ROADMAP.md](V3_ROADMAP.md) for capability timelines.
