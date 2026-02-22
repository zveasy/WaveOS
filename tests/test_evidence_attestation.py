"""Tests for evidence pack attestation (Persistence Phase 3)."""

import tempfile
from pathlib import Path

from waveos.reporting import build_evidence_attestation, verify_evidence_attestation


def test_build_and_verify_evidence_attestation() -> None:
    """Building attestation then verifying passes."""
    with tempfile.TemporaryDirectory() as d:
        out_dir = Path(d)
        (out_dir / "run_meta.json").write_text('{"run_id":"test"}', encoding="utf-8")
        (out_dir / "health_summary.json").write_text("[]", encoding="utf-8")
        (out_dir / "actions.json").write_text("[]", encoding="utf-8")
        attestation_path = build_evidence_attestation(out_dir, run_id="test")
        assert attestation_path.is_file()
        assert attestation_path.name == "evidence_attestation.json"
        ok, errors = verify_evidence_attestation(attestation_path)
        assert ok, errors
        assert not errors


def test_verify_evidence_attestation_mismatch() -> None:
    """After tampering, verification fails."""
    with tempfile.TemporaryDirectory() as d:
        out_dir = Path(d)
        (out_dir / "run_meta.json").write_text('{"run_id":"test"}', encoding="utf-8")
        build_evidence_attestation(out_dir, run_id="test")
        (out_dir / "run_meta.json").write_text('{"run_id":"tampered"}', encoding="utf-8")
        ok, errors = verify_evidence_attestation(out_dir / "evidence_attestation.json")
        assert not ok
        assert any("mismatch" in e.lower() for e in errors)


def test_verify_evidence_attestation_missing_file() -> None:
    """Verifying non-existent path returns error."""
    ok, errors = verify_evidence_attestation(Path("/nonexistent/evidence_attestation.json"))
    assert not ok
    assert len(errors) >= 1
