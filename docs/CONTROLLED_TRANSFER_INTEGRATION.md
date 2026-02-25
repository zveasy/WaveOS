# WaveOS Controlled Transfer Integration

## Overview

WaveOS integrates with existing secure transfer mechanisms for defense and regulated environments. It does not bypass security boundaries — it works within them.

## Supported Patterns

### 1. CDS Pipeline → Internal Mirror

Cross-Domain Solution (CDS) transfers bundles from high-side CI/CD to a low-side internal mirror.

```
[CI/CD Build] → [CDS] → [Internal Mirror] → [Agent Pull]
```

### 2. Secure File Transfer Gateway → Internal Registry Mirror

Secure gateway (e.g., SFTP, SCP) transfers bundles to an internal registry.

### 3. Data Diode (One-Way) Mirror Sync

One-way transfer for classified environments.

## Internal Mirror Mode

WaveOS provides a registry that can operate as an internal mirror:

```bash
# On the high side: publish to external registry
waveos registry publish <bundle> --channel prod

# Transfer bundle directory to internal network (via CDS/gateway/diode)

# On the internal network: publish to internal mirror
waveos registry publish <bundle> --channel prod --registry /opt/waveos/mirror

# Agents pull from internal mirror
waveos agent-v2 update --channel prod --registry /opt/waveos/mirror
```

## Transport Security

- mTLS support for registry connections
- Short-lived tokens / OIDC where available
- Offline trust-store support (pinned keys in `*.key` files)
- All bundles verified via signature before install

## Air-Gap Support

For fully air-gapped environments with a physical transfer mechanism:

```bash
# Export bundle to portable media
waveos bundle build --dir /path/to/bundle
waveos bundle sign --dir /path/to/bundle

# Import on air-gapped network
waveos bundle install --from-cache /media/bundles --bundle-id <id>
```
