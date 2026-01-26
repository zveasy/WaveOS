from waveos.utils import get_secret


def test_get_secret_from_env(monkeypatch) -> None:
    monkeypatch.setenv("TEST_SECRET", "value")
    assert get_secret("TEST_SECRET", provider="env") == "value"


def test_get_secret_from_vault_json(monkeypatch) -> None:
    monkeypatch.setenv("WAVEOS_VAULT_SECRETS_JSON", '{"db_password": "vault-secret"}')
    assert get_secret("db_password", provider="vault") == "vault-secret"


def test_get_secret_from_aws_json(monkeypatch) -> None:
    monkeypatch.setenv("WAVEOS_AWS_SECRETS_JSON", '{"api_key": "aws-secret"}')
    assert get_secret("api_key", provider="aws") == "aws-secret"


def test_get_secret_from_gcp_json(monkeypatch) -> None:
    monkeypatch.setenv("WAVEOS_GCP_SECRETS_JSON", '{"token": "gcp-secret"}')
    assert get_secret("token", provider="gcp") == "gcp-secret"
