"""Tests for controlled-transfer gateway, diode, audit (§2)."""
from __future__ import annotations
import json
from pathlib import Path
from waveos.transfer import TransferGateway, TransferJob, TransferJobStatus, DiodeSync, DiodeMode
from waveos.transfer.audit import TransferAuditChain, ChainOfCustodyEntry

def _bundle(tmp: Path, bid: str = "b1") -> Path:
    d = tmp / f"bundle_{bid}"; d.mkdir()
    (d / "bundle.json").write_text(json.dumps({"bundle_id": bid, "version": "1.0"}))
    return d

def test_gateway_create_and_execute(tmp_path: Path):
    staging = tmp_path / "staging"
    dest = tmp_path / "mirror"
    gw = TransferGateway(staging)
    src = _bundle(tmp_path, "b1")
    job = gw.create_job("b1", src, str(dest))
    result = gw.execute_job(job.job_id)
    assert result.status == TransferJobStatus.COMPLETED

def test_gateway_scan_reject(tmp_path: Path):
    gw = TransferGateway(tmp_path / "staging", scan_hook=lambda p: {"passed": False, "reason": "malware"})
    src = _bundle(tmp_path, "b1")
    job = gw.create_job("b1", src, str(tmp_path / "mirror"))
    result = gw.execute_job(job.job_id)
    assert result.status == TransferJobStatus.REJECTED

def test_gateway_approval_deny(tmp_path: Path):
    gw = TransferGateway(tmp_path / "staging", approval_hook=lambda j: False)
    src = _bundle(tmp_path, "b1")
    job = gw.create_job("b1", src, str(tmp_path / "mirror"))
    result = gw.execute_job(job.job_id)
    assert result.status == TransferJobStatus.REJECTED

def test_diode_push(tmp_path: Path):
    src = tmp_path / "src" / "bundles"; src.mkdir(parents=True)
    (src / "b1").mkdir(); (src / "b1" / "bundle.json").write_text("{}")
    dst = tmp_path / "dst"
    d = DiodeSync(tmp_path / "src", dst)
    result = d.push()
    assert "b1" in result.pushed

def test_diode_skip_existing(tmp_path: Path):
    src = tmp_path / "src" / "bundles" / "b1"; src.mkdir(parents=True)
    (src / "bundle.json").write_text("{}")
    dst = tmp_path / "dst" / "bundles" / "b1"; dst.mkdir(parents=True)
    (dst / "bundle.json").write_text("{}")
    result = DiodeSync(tmp_path / "src", tmp_path / "dst").push()
    assert "b1" in result.skipped

def test_audit_chain(tmp_path: Path):
    chain = TransferAuditChain()
    chain.add_entry("b1", "ci", "github-actions", action="build", artifact_hash="abc123")
    chain.add_entry("b1", "gateway", "gateway-1", action="transfer", artifact_hash="abc123")
    chain.add_entry("b1", "mirror", "mirror-1", action="publish", artifact_hash="abc123")
    ok, errors = chain.verify_chain()
    assert ok and len(errors) == 0
    assert len(chain.get_chain("b1")) == 3

def test_audit_chain_tamper(tmp_path: Path):
    chain = TransferAuditChain()
    chain.add_entry("b1", "ci", "bot")
    chain.add_entry("b1", "gw", "gw1")
    chain._entries[1].previous_hash = "tampered"
    ok, errors = chain.verify_chain()
    assert not ok

def test_audit_chain_persistence(tmp_path: Path):
    p = tmp_path / "chain.json"
    chain = TransferAuditChain(p)
    chain.add_entry("b1", "ci", "bot")
    chain.save()
    loaded = TransferAuditChain(p)
    assert len(loaded.get_chain()) == 1
