# Release Process

## Versioning Policy
- Follow semantic versioning: MAJOR.MINOR.PATCH.
- MAJOR: breaking changes to CLI or data contracts.
- MINOR: new features with backward compatibility.
- PATCH: bug fixes and doc updates.

## Build and Package
1) Update version in `pyproject.toml`.
2) Run tests: `pytest -q`.
3) Build artifacts: `python -m build`.
4) Verify artifacts with a clean environment install.

## Signing (Cosign Keyless OIDC)
- Tool: `cosign` for artifact signatures.
- No long-lived secrets required; GitHub OIDC is used during CI and release.
- CI signs `dist/*.whl` and `dist/*.tar.gz` and emits `.sig` and `.crt` files.
- SBOM is generated via Syft (`dist/sbom.spdx.json`) and signed with cosign.
- Verify with:
  ```
  cosign verify-blob \
    --certificate-identity "https://github.com/<org>/<repo>/.github/workflows/release.yml@refs/tags/<tag>" \
    --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
    --signature <artifact>.sig \
    --certificate <artifact>.crt \
    <artifact>
  ```

## SBOM Verification
The SBOM is generated during CI and signed using cosign keyless (OIDC). No long-lived signing keys are used.

```
cosign verify-blob \
  --certificate-identity "https://github.com/<org>/<repo>/.github/workflows/release.yml@refs/tags/<tag>" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  --signature sbom.spdx.json.sig \
  sbom.spdx.json
```

## Release Notes
- Release notes are generated automatically from GitHub (labels/commits) and include:
  - artifact list
  - SHA256 checksums
- cosign verification instructions

## Internal Registry Promotion
- Build artifacts and publish to internal registry:
  - `bin/publish_internal.sh` (requires `INTERNAL_PYPI_URL` and `INTERNAL_PYPI_TOKEN`)
- Promotion process:
  1. Publish to internal registry.
  2. Validate in staging via smoke tests.
  3. Tag production release and publish to public registry.
  - SBOM link (when available)

## Publishing
- Default: GitHub Packages (internal registry) via `release.yml`.
- Optional PyPI: set `PYPI_API_TOKEN` in CI secrets to enable.
  - Use this for community distribution only.

## Release Checklist
- Changelog updated.
- CI green on main.
- Artifacts built and signed (if required).
- Publish to internal registry or package index.
