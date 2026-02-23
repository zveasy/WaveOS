# Secrets and Integration Tests

## Unit tests (Vault / AWS / GCP)

The tests in `tests/test_secrets.py` for Vault, AWS, and GCP use the **JSON fallback** (`WAVEOS_VAULT_SECRETS_JSON`, `WAVEOS_AWS_SECRETS_JSON`, `WAVEOS_GCP_SECRETS_JSON`). This fallback is **only allowed when**:

- `WAVEOS_LICENSE_SKIP=1` (dev/test mode), and  
- `WAVEOS_STRICT_SECRETS` is not set to a truthy value.

The tests set `WAVEOS_LICENSE_SKIP=1` (via parametrize) so that the JSON fallback is used and the tests pass without real Vault/AWS/GCP.

## Production

In **production** (no `WAVEOS_LICENSE_SKIP`), the JSON fallback is **disabled**. You must use a real secrets provider (Vault, AWS Secrets Manager, or GCP Secret Manager) with the appropriate env vars (`WAVEOS_VAULT_ADDR`, `WAVEOS_VAULT_TOKEN`, etc.). See [SECURITY_PRODUCTION.md](SECURITY_PRODUCTION.md).

## Integration tests (real providers)

To validate real Vault/AWS/GCP integration:

1. Set the required env vars for the provider (e.g. `WAVEOS_VAULT_ADDR`, `WAVEOS_VAULT_TOKEN`, `WAVEOS_VAULT_PATH`).
2. Do **not** set `WAVEOS_LICENSE_SKIP=1` if you want to test production behavior.
3. Run a separate integration test suite (e.g. `pytest tests/integration/test_secrets_vault.py -v`) that is **not** run in CI unless credentials are provided (or mark with `@pytest.mark.integration` and skip by default).

CI behavior: the unit tests in `test_secrets.py` run in CI and pass using the JSON fallback under `WAVEOS_LICENSE_SKIP=1`. Integration tests against real providers are optional and should be gated (env or marker).
