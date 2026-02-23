"""
Secrets provider tests. Vault/AWS/GCP tests use *_SECRETS_JSON env fallback.

In production (WAVEOS_LICENSE_SKIP != 1), JSON fallback is disabled for security.
These tests run with WAVEOS_LICENSE_SKIP=1 so JSON fallback is allowed (dev/test).
For real Vault/AWS/GCP, use integration tests with real credentials (see docs/SECRETS.md).
"""
import pytest

from waveos.utils import get_secret


def test_get_secret_from_env(monkeypatch) -> None:
    monkeypatch.setenv("TEST_SECRET", "value")
    assert get_secret("TEST_SECRET", provider="env") == "value"


@pytest.mark.parametrize("license_skip", ["1"], ids=["dev_mode"])
def test_get_secret_from_vault_json(monkeypatch, license_skip: str) -> None:
    monkeypatch.setenv("WAVEOS_LICENSE_SKIP", license_skip)
    monkeypatch.setenv("WAVEOS_VAULT_SECRETS_JSON", '{"db_password": "vault-secret"}')
    assert get_secret("db_password", provider="vault") == "vault-secret"


@pytest.mark.parametrize("license_skip", ["1"], ids=["dev_mode"])
def test_get_secret_from_aws_json(monkeypatch, license_skip: str) -> None:
    monkeypatch.setenv("WAVEOS_LICENSE_SKIP", license_skip)
    monkeypatch.setenv("WAVEOS_AWS_SECRETS_JSON", '{"api_key": "aws-secret"}')
    assert get_secret("api_key", provider="aws") == "aws-secret"


@pytest.mark.parametrize("license_skip", ["1"], ids=["dev_mode"])
def test_get_secret_from_gcp_json(monkeypatch, license_skip: str) -> None:
    monkeypatch.setenv("WAVEOS_LICENSE_SKIP", license_skip)
    monkeypatch.setenv("WAVEOS_GCP_SECRETS_JSON", '{"token": "gcp-secret"}')
    assert get_secret("token", provider="gcp") == "gcp-secret"
