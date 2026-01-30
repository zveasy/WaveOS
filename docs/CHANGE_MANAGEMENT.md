# Change Management

## Release Approvals
- Require a review before tagging production releases.
- Verify SBOM and signatures in CI.

## Rollback
- Use `waveos bundle rollback` to restore the last known-good bundle.
- Validate rollback with a test run and report review.
