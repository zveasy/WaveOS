# WaveOS Bundle Specification V2

## Overview

A WaveOS bundle is a versioned, signed release artifact containing application code, configuration, and deployment metadata. Bundles are the unit of delivery in the WaveOS secure release platform.

## Bundle Format

A bundle is a directory (or tar/zip archive) containing:

```
<bundle_id>/
  bundle.json          # V2 manifest (required)
  bundle.sig           # HMAC-SHA256 signature (optional)
  checksums.txt        # SHA256 checksums for all payloads
  attestation.json     # Build provenance (optional)
  sbom.json            # Software Bill of Materials (optional)
  <payload files>      # Application files
```

## Manifest Schema

See `schemas/bundle_manifest.schema.json` for the full JSON Schema.

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `bundle_id` | string | Unique identifier |
| `version` | string | Semantic version |

### Core Metadata

| Field | Type | Description |
|-------|------|-------------|
| `build_commit` | string | Git commit SHA |
| `build_time` | ISO 8601 | Build timestamp |
| `waveos_version` | string | WaveOS version |
| `policy_version` | string | Policy version |
| `channel` | enum | `dev\|staging\|prod\|mission-critical` |

### Targets

OS/arch/CPU constraints. The agent's preflight engine checks these before install.

```json
{
  "targets": [
    {"os": "linux", "os_version": ">=20.04", "arch": "x86_64", "cpu_features": []}
  ]
}
```

### Payload

Files with install locations and permissions.

### Runtimes

Dependency/isolation strategy: `bundled`, `side_by_side`, `container`, or `vm`.

### Services

What to run, ordering, health checks, restart policies.

### Bridge

Optional legacy/new adapter wiring. See `docs/BRIDGE_PATTERNS.md`.

### Rollback

Previous versions and rollback conditions (`crash_loop`, `health_below_50`, `latency_regression`).

### Policy Gates

Gates required to activate (health score thresholds, approvals).

## Integrity

- All payload files have SHA256 checksums in both the manifest and `checksums.txt`
- Manifests are signed with HMAC-SHA256 (`bundle.sig`)
- Verification uses a trust store directory containing `*.key` files

## CLI Commands

```bash
waveos bundle build --dir <path>
waveos bundle inspect --dir <path>
waveos bundle verify --dir <path> [--trust-store <path>]
waveos bundle sign --dir <path>
waveos bundle install --dir <path>
waveos bundle promote
waveos bundle rollback
```
