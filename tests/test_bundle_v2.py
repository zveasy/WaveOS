"""Tests for WaveOS Bundle V2 system."""

from __future__ import annotations

from pathlib import Path

from waveos.bundle import sign_manifest
from waveos.bundle_v2 import (
    BridgeSpec,
    BundleManifestV2,
    PolicyGate,
    RollbackSpec,
    RuntimeSpec,
    ServiceSpec,
    TargetConstraint,
    build_manifest_v2,
    inspect_bundle,
    read_manifest_v2,
    verify_bundle_checksums,
    verify_bundle_with_trust_store,
    write_manifest_v2,
)


def _create_test_bundle(tmp_path: Path) -> Path:
    bundle_dir = tmp_path / "test_bundle"
    bundle_dir.mkdir()
    (bundle_dir / "app.py").write_text("print('hello')\n")
    (bundle_dir / "config.json").write_text('{"key": "value"}\n')
    return bundle_dir


def test_build_manifest_v2(tmp_path: Path) -> None:
    bundle_dir = _create_test_bundle(tmp_path)
    manifest = build_manifest_v2(
        bundle_dir,
        bundle_id="test-bundle-1",
        version="1.0.0",
        waveos_version="0.1.0rc4",
        channel="dev",
    )
    assert manifest.bundle_id == "test-bundle-1"
    assert manifest.version == "1.0.0"
    assert len(manifest.artifacts) == 2
    assert len(manifest.checksums) == 2
    assert manifest.channel == "dev"


def test_write_and_read_manifest_v2(tmp_path: Path) -> None:
    bundle_dir = _create_test_bundle(tmp_path)
    manifest = build_manifest_v2(bundle_dir, bundle_id="test-rw", version="2.0.0")
    write_manifest_v2(bundle_dir, manifest)
    assert (bundle_dir / "bundle.json").exists()
    assert (bundle_dir / "checksums.txt").exists()
    loaded = read_manifest_v2(bundle_dir)
    assert loaded is not None
    assert loaded.bundle_id == "test-rw"
    assert loaded.version == "2.0.0"
    assert len(loaded.artifacts) == len(manifest.artifacts)


def test_manifest_v2_with_all_fields(tmp_path: Path) -> None:
    bundle_dir = _create_test_bundle(tmp_path)
    manifest = build_manifest_v2(
        bundle_dir,
        bundle_id="full-bundle",
        version="3.0.0",
        targets=[TargetConstraint(os="linux", arch="x86_64")],
        services=[ServiceSpec(name="api", command="python api.py", order=1)],
        bridge=BridgeSpec(mode="mirror", legacy_service="old-api"),
        rollback=RollbackSpec(conditions=["crash_loop"]),
        policy_gates=[PolicyGate(name="health", threshold=70.0)],
        runtimes=RuntimeSpec(strategy="side_by_side"),
    )
    d = manifest.to_dict()
    assert d["manifest_version"] == "2.0"
    assert len(d["targets"]) == 1
    assert d["targets"][0]["os"] == "linux"
    assert len(d["services"]) == 1
    assert d["bridge"]["mode"] == "mirror"
    assert d["rollback"]["conditions"] == ["crash_loop"]
    assert len(d["policy"]) == 1


def test_manifest_v2_roundtrip(tmp_path: Path) -> None:
    bundle_dir = _create_test_bundle(tmp_path)
    original = build_manifest_v2(
        bundle_dir,
        bundle_id="roundtrip",
        version="1.0.0",
        targets=[TargetConstraint(os="linux", arch="aarch64")],
        services=[ServiceSpec(name="svc1", command="run.sh")],
    )
    d = original.to_dict()
    restored = BundleManifestV2.from_dict(d)
    assert restored.bundle_id == original.bundle_id
    assert len(restored.targets) == 1
    assert restored.targets[0].arch == "aarch64"


def test_inspect_bundle(tmp_path: Path) -> None:
    bundle_dir = _create_test_bundle(tmp_path)
    manifest = build_manifest_v2(bundle_dir, bundle_id="inspect-me", version="1.0.0")
    write_manifest_v2(bundle_dir, manifest)
    info = inspect_bundle(bundle_dir)
    assert info["bundle_id"] == "inspect-me"
    assert info["artifact_count"] == 2
    assert info["total_size_bytes"] > 0


def test_verify_bundle_checksums(tmp_path: Path) -> None:
    bundle_dir = _create_test_bundle(tmp_path)
    manifest = build_manifest_v2(bundle_dir, bundle_id="verify-cs", version="1.0.0")
    write_manifest_v2(bundle_dir, manifest)
    ok, errors = verify_bundle_checksums(bundle_dir)
    assert ok
    assert errors == []


def test_verify_bundle_checksums_tampered(tmp_path: Path) -> None:
    bundle_dir = _create_test_bundle(tmp_path)
    manifest = build_manifest_v2(bundle_dir, bundle_id="tampered", version="1.0.0")
    write_manifest_v2(bundle_dir, manifest)
    (bundle_dir / "app.py").write_text("TAMPERED\n")
    ok, errors = verify_bundle_checksums(bundle_dir)
    assert not ok
    assert any("mismatch" in e for e in errors)


def test_verify_with_trust_store(tmp_path: Path) -> None:
    bundle_dir = _create_test_bundle(tmp_path)
    manifest = build_manifest_v2(bundle_dir, bundle_id="trust-test", version="1.0.0")
    write_manifest_v2(bundle_dir, manifest)
    hmac_key = "test-secret-key-123"
    sign_manifest(bundle_dir / "bundle.json", hmac_key)
    trust_store = tmp_path / "trust_store"
    trust_store.mkdir()
    (trust_store / "prod.key").write_text(hmac_key + "\n")
    ok, errors = verify_bundle_with_trust_store(bundle_dir, trust_store)
    assert ok
    assert errors == []


def test_verify_with_trust_store_wrong_key(tmp_path: Path) -> None:
    bundle_dir = _create_test_bundle(tmp_path)
    manifest = build_manifest_v2(bundle_dir, bundle_id="wrong-key", version="1.0.0")
    write_manifest_v2(bundle_dir, manifest)
    sign_manifest(bundle_dir / "bundle.json", "correct-key")
    trust_store = tmp_path / "trust_store"
    trust_store.mkdir()
    (trust_store / "wrong.key").write_text("wrong-key\n")
    ok, errors = verify_bundle_with_trust_store(bundle_dir, trust_store)
    assert not ok
