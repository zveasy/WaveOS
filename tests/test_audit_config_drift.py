from pathlib import Path

from waveos.utils import append_audit, config_fingerprint, WaveOSConfig


def test_append_audit_writes_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    append_audit(path, {"event": "authz", "allowed": True})
    assert path.exists()
    assert "authz" in path.read_text(encoding="utf-8")


def test_config_fingerprint_changes() -> None:
    config_a = WaveOSConfig()
    config_b = WaveOSConfig(log_level="DEBUG")
    assert config_fingerprint(config_a) != config_fingerprint(config_b)
