"""Tests for WaveOS Agent system."""

from __future__ import annotations

import json
from pathlib import Path

from waveos.agent.evidence import (
    DeploymentEvidence,
    collect_deployment_evidence,
    write_evidence_pack,
)
from waveos.agent.manager import AgentConfig, AgentManager
from waveos.agent.service_runner import ManagedService, ServiceRunner
from waveos.agent.state_machine import AgentState, AgentStateMachine


def test_state_machine_initial() -> None:
    sm = AgentStateMachine()
    assert sm.state == AgentState.IDLE


def test_state_machine_valid_transition() -> None:
    sm = AgentStateMachine()
    assert sm.can_transition(AgentState.CHECK_UPDATE)
    ok = sm.transition(AgentState.CHECK_UPDATE, reason="test")
    assert ok
    assert sm.state == AgentState.CHECK_UPDATE


def test_state_machine_invalid_transition() -> None:
    sm = AgentStateMachine()
    assert not sm.can_transition(AgentState.ACTIVATE)
    ok = sm.transition(AgentState.ACTIVATE)
    assert not ok
    assert sm.state == AgentState.IDLE


def test_state_machine_full_lifecycle() -> None:
    sm = AgentStateMachine()
    sm.transition(AgentState.CHECK_UPDATE)
    sm.transition(AgentState.DOWNLOAD)
    sm.transition(AgentState.VERIFY)
    sm.transition(AgentState.PREFLIGHT)
    sm.transition(AgentState.INSTALL)
    sm.transition(AgentState.ACTIVATE)
    sm.transition(AgentState.MONITOR)
    assert sm.state == AgentState.MONITOR
    assert len(sm.history) == 7


def test_state_machine_force_state() -> None:
    sm = AgentStateMachine()
    sm.force_state(AgentState.QUARANTINE, reason="forced")
    assert sm.state == AgentState.QUARANTINE


def test_state_machine_persistence(tmp_path: Path) -> None:
    sm = AgentStateMachine()
    sm.transition(AgentState.CHECK_UPDATE)
    sm.transition(AgentState.DOWNLOAD)
    path = tmp_path / "state.json"
    sm.save_state(path)
    loaded = AgentStateMachine.load_state(path)
    assert loaded.state == AgentState.DOWNLOAD
    assert len(loaded.history) == 2


def test_agent_manager_bootstrap(tmp_path: Path) -> None:
    config = AgentConfig(base_dir=tmp_path / "agent", apps_dir=tmp_path / "apps")
    manager = AgentManager(config)
    result = manager.install_bootstrap()
    assert result["status"] == "ok"
    assert (tmp_path / "agent" / "bundles").is_dir()
    assert (tmp_path / "apps").is_dir()


def test_agent_manager_status(tmp_path: Path) -> None:
    config = AgentConfig(base_dir=tmp_path / "agent", apps_dir=tmp_path / "apps")
    manager = AgentManager(config)
    status = manager.status()
    assert status["state"] == "IDLE"
    assert status["active_bundle"] is None


def test_agent_manager_activate(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "bundle.json").write_text(json.dumps({"bundle_id": "b1", "version": "1.0"}))
    (bundle_dir / "app.py").write_text("# app\n")
    config = AgentConfig(base_dir=tmp_path / "agent", apps_dir=tmp_path / "apps")
    manager = AgentManager(config)
    result = manager.activate_bundle(bundle_dir, bundle_id="b1", app_name="myapp", version="1.0.0")
    steps = result.get("steps", [])
    assert any(s["step"] == "activate" and s["ok"] for s in steps)
    assert manager.sm.state == AgentState.MONITOR


def test_agent_manager_rollback(tmp_path: Path) -> None:
    config = AgentConfig(base_dir=tmp_path / "agent", apps_dir=tmp_path / "apps")
    manager = AgentManager(config)
    # Install two versions
    for ver in ["1.0", "2.0"]:
        bundle_dir = tmp_path / f"bundle_{ver}"
        bundle_dir.mkdir()
        (bundle_dir / "bundle.json").write_text(json.dumps({"bundle_id": f"b-{ver}", "version": ver}))
        manager.activate_bundle(bundle_dir, bundle_id=f"b-{ver}", version=ver)
    result = manager.rollback()
    assert result["ok"]
    assert "1.0" in result["rolled_back_to"]


def test_agent_manager_logs(tmp_path: Path) -> None:
    config = AgentConfig(base_dir=tmp_path / "agent", apps_dir=tmp_path / "apps")
    manager = AgentManager(config)
    manager.install_bootstrap()
    logs = manager.get_logs()
    assert len(logs) >= 1


def test_service_runner_start_stop() -> None:
    runner = ServiceRunner()
    runner.register(ManagedService(name="svc1", command="echo hello", order=1))
    runner.register(ManagedService(name="svc2", command="echo world", order=2))
    assert runner.get_start_order() == ["svc1", "svc2"]
    results = runner.start_all()
    assert all(r["ok"] for r in results)
    statuses = runner.status_all()
    assert all(s["status"] == "running" for s in statuses)
    stop_results = runner.stop_all()
    assert all(r["ok"] for r in stop_results)


def test_service_runner_health() -> None:
    runner = ServiceRunner()
    runner.register(ManagedService(name="svc", command="echo hi"))
    runner.start_service("svc")
    result = runner.check_health("svc")
    assert result["ok"]
    assert result["healthy"]


def test_evidence_collect_and_write(tmp_path: Path) -> None:
    evidence = collect_deployment_evidence(
        bundle_id="test-ev",
        steps=[{"step": "verify", "ok": True}],
        agent_state="MONITOR",
    )
    assert evidence.bundle_id == "test-ev"
    path = write_evidence_pack(evidence, tmp_path / "evidence")
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["bundle_id"] == "test-ev"


def test_deployment_evidence_roundtrip() -> None:
    ev = DeploymentEvidence(bundle_id="rt", steps=[{"step": "test"}])
    d = ev.to_dict()
    restored = DeploymentEvidence.from_dict(d)
    assert restored.bundle_id == "rt"
    assert len(restored.steps) == 1
