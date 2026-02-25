"""Tests for WaveOS Attestation module."""

from __future__ import annotations

from pathlib import Path

from waveos.attestation import (
    Attestation,
    BuildProvenance,
    generate_attestation,
    read_attestation,
    write_attestation,
)


def test_build_provenance_roundtrip() -> None:
    prov = BuildProvenance(build_id="build-123", commit_sha="abc123", ci_provider="github-actions")
    d = prov.to_dict()
    restored = BuildProvenance.from_dict(d)
    assert restored.build_id == "build-123"
    assert restored.ci_provider == "github-actions"


def test_attestation_roundtrip() -> None:
    att = Attestation(
        subject=[{"name": "app.py", "digest": {"sha256": "abc"}}],
        provenance=BuildProvenance(build_id="b1"),
    )
    d = att.to_dict()
    restored = Attestation.from_dict(d)
    assert len(restored.subject) == 1
    assert restored.provenance is not None
    assert restored.provenance.build_id == "b1"


def test_generate_attestation(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "app.py").write_text("# test\n")
    att = generate_attestation(bundle_dir, bundle_id="test-att")
    assert att.provenance is not None
    assert att.provenance.build_id != ""
    assert len(att.subject) == 1
    assert att.metadata.get("bundle_id") == "test-att"


def test_write_and_read_attestation(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "file.txt").write_text("data\n")
    att = generate_attestation(bundle_dir, bundle_id="rw-test")
    path = write_attestation(bundle_dir, att)
    assert path.exists()
    loaded = read_attestation(bundle_dir)
    assert loaded is not None
    assert loaded.provenance.build_id == att.provenance.build_id


def test_read_attestation_missing(tmp_path: Path) -> None:
    result = read_attestation(tmp_path)
    assert result is None
