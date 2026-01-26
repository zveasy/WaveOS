# Release Testing

## Phase 1: Dry Run (No Publish)
Use the manual workflow to build, SBOM, and sign without publishing.

1) GitHub Actions → `release-dry-run` → Run workflow
2) Download artifacts from the workflow run

## Phase 2: TestPyPI (RC Tags)
Publish only to TestPyPI using RC tags (no production publish).

Create and push an RC tag:
```bash
make release-rc VERSION=0.1.0 RC=1
```

This triggers `release-testpypi.yml` and publishes to TestPyPI.

## Production Publish (Non-RC Tags)
Only tags without `-rc` publish to production registries.

```bash
git tag v0.1.0
git push origin v0.1.0
```

## Notes
- RC tags: `vX.Y.Z-rcN`
- Prod tags: `vX.Y.Z`
- RC tags never publish to prod registries.
