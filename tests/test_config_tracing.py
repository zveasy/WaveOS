from pathlib import Path

import pytest
from pydantic import ValidationError

from waveos.utils import init_tracer, load_config


def test_load_config_from_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "waveos.toml"
    config_path.write_text(
        "\n".join(
            [
                'log_format = "text"',
                'log_level = "DEBUG"',
                "metrics_port = 9109",
                'otel_endpoint = "http://localhost:4318/v1/traces"',
            ]
        ),
        encoding="utf-8",
    )
    config = load_config(config_path)
    assert config.log_format == "text"
    assert config.log_level == "DEBUG"
    assert config.metrics_port == 9109
    assert config.otel_endpoint.endswith("/v1/traces")


def test_init_tracer_is_idempotent() -> None:
    init_tracer(service_name="waveos-test")
    init_tracer(service_name="waveos-test")


def test_load_config_invalid_metrics_port(tmp_path: Path) -> None:
    config_path = tmp_path / "waveos.json"
    config_path.write_text('{"metrics_port": "invalid"}', encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(config_path)


def test_load_config_invalid_log_format(tmp_path: Path) -> None:
    config_path = tmp_path / "waveos.json"
    config_path.write_text('{"log_format": "xml"}', encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(config_path)
