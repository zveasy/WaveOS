"""Tests for health contracts, SLOs, rollback proofs, quarantine (§6)."""
from __future__ import annotations
import json
from pathlib import Path
from waveos.health_contracts import (ServiceSLO, check_service_slo, SLOCheckResult, RollbackProof,
    generate_rollback_proof, write_rollback_proof, QuarantineRegistry, QuarantineStatus, BundleQuarantineEntry)

def test_slo_pass():
    slo = ServiceSLO(service_name="api", min_health_score=70, max_latency_ms=200)
    result = check_service_slo(slo, health_score=90, latency_ms=50)
    assert result.passed

def test_slo_fail_health():
    slo = ServiceSLO(service_name="api", min_health_score=80)
    result = check_service_slo(slo, health_score=50)
    assert not result.passed

def test_slo_fail_latency():
    slo = ServiceSLO(service_name="api", max_latency_ms=100)
    result = check_service_slo(slo, latency_ms=200)
    assert not result.passed

def test_slo_invariants():
    slo = ServiceSLO(service_name="api", invariants=["db_connected"])
    result = check_service_slo(slo, invariant_results={"db_connected": False})
    assert not result.passed

def test_rollback_proof():
    slo = ServiceSLO(service_name="api", min_health_score=70)
    slo_result = check_service_slo(slo, health_score=30)
    proof = generate_rollback_proof("b1", "health_below", "Score 30 < 70", slo_result=slo_result, rolled_back_to="b0")
    assert proof.bundle_id == "b1" and len(proof.slo_violations) > 0

def test_rollback_proof_write(tmp_path: Path):
    proof = generate_rollback_proof("b1", "crash_loop", "3 crashes in 5 min")
    p = write_rollback_proof(proof, tmp_path / "proofs")
    assert p.exists()

def test_quarantine_registry(tmp_path: Path):
    qr = QuarantineRegistry(tmp_path / "q.json")
    qr.quarantine("b1", reason="failed health", by="agent")
    blocked, msg = qr.is_blocked("b1")
    assert blocked and "quarantined" in msg

def test_quarantine_ban(tmp_path: Path):
    qr = QuarantineRegistry(tmp_path / "q.json")
    qr.ban("b1", reason="CVE found")
    assert qr.get_status("b1").status == QuarantineStatus.BANNED

def test_quarantine_release(tmp_path: Path):
    qr = QuarantineRegistry(tmp_path / "q.json")
    qr.hold("b1", reason="under review")
    assert qr.is_blocked("b1")[0]
    qr.release("b1")
    assert not qr.is_blocked("b1")[0]

def test_quarantine_persistence(tmp_path: Path):
    p = tmp_path / "q.json"
    qr = QuarantineRegistry(p)
    qr.quarantine("b1", reason="test")
    qr2 = QuarantineRegistry(p)
    assert qr2.is_blocked("b1")[0]
