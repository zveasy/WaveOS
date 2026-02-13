"""Tests for V3: compatibility, orchestration, GitOps, shadow, node health, compliance, quotas, security."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from waveos.bundle import build_manifest
from waveos.compatibility import RuntimeTranslator, translate_telemetry
from waveos.compliance import ComplianceReport, generate_report, write_report
from waveos.gitops import (
    DesiredState,
    diff_state,
    load_desired_state,
    current_state_from_registry,
    apply_desired_state,
)
from waveos.orchestration import (
    NodeRole,
    NodeRecord,
    get_node_registry,
    register_node,
    load_nodes_from_file,
    save_nodes_to_file,
)
from waveos.quotas import check_quota, record_run
from waveos.scheduler import EnergyScheduler, GridSignal
from waveos.security import DeviceIdentity, set_anomaly_callback, on_anomaly
from waveos.shadow import run_shadow, ShadowResult
from waveos.policy.templates import load_policy_templates
from waveos.utils.rbac import Clearance, Principal, Permission, Role, authorize


def test_build_manifest_attestation(tmp_path: Path) -> None:
    (tmp_path / "dummy").write_text("x")
    m = build_manifest(
        tmp_path,
        "1.0",
        "p1",
        "b1",
        attestation={"build_id": "abc", "provenance": "ci"},
    )
    assert m.attestation == {"build_id": "abc", "provenance": "ci"}
    assert "attestation" in m.to_dict()


def test_runtime_translator() -> None:
    t = RuntimeTranslator()
    raw = {"vendor": "acme", "soc_pct": 80, "temp_c": 25, "link_id": "L1"}
    out = t.translate(raw)
    assert out is not None
    assert out.link_id == "L1"
    assert out.battery_soc_pct == 80.0
    assert out.temperature_c == 25.0
    direct = translate_telemetry(raw, "generic")
    assert direct.link_id == "L1"


def test_orchestration_nodes(tmp_path: Path) -> None:
    reg = get_node_registry()
    initial = len(reg)
    register_node("n1", NodeRole.EDGE, endpoint="https://n1.local", site_id="site-a")
    reg = get_node_registry()
    assert "n1" in reg
    assert reg["n1"].role == NodeRole.EDGE
    assert reg["n1"].endpoint == "https://n1.local"
    path = tmp_path / "nodes.json"
    save_nodes_to_file(path)
    assert path.is_file()
    data = json.loads(path.read_text())
    assert "nodes" in data
    assert any(n["node_id"] == "n1" and n["role"] == "edge" for n in data["nodes"])


def test_load_nodes_from_file(tmp_path: Path) -> None:
    path = tmp_path / "nodes.json"
    path.write_text(json.dumps({"nodes": [{"node_id": "n2", "role": "cloud", "site_id": "s1"}]}))
    n = load_nodes_from_file(path)
    assert n == 1
    reg = get_node_registry()
    assert "n2" in reg
    assert reg["n2"].role == NodeRole.CLOUD


def test_gitops_desired_state_load_diff(tmp_path: Path) -> None:
    path = tmp_path / "desired.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "waveos_version": "2.0",
        "bundle_id": "b2",
        "nodes": [{"node_id": "a"}],
        "devices": [],
    }))
    desired = load_desired_state(path)
    assert desired is not None
    assert desired.waveos_version == "2.0"
    assert desired.bundle_id == "b2"
    current = current_state_from_registry(node_registry={"a": NodeRecord("a", NodeRole.EDGE)})
    diff = diff_state(desired, current)
    assert "additions" in diff
    assert "removals" in diff
    assert "changes" in diff


def test_gitops_apply_desired_state(tmp_path: Path) -> None:
    desired = DesiredState(schema_version=1, waveos_version="3.0", nodes=[], devices=[])
    history = tmp_path / "state_history.jsonl"
    out = tmp_path / "applied.json"
    apply_desired_state(desired, history, desired_state_path=out)
    assert history.is_file()
    assert out.is_file()
    data = json.loads(out.read_text())
    assert data.get("waveos_version") == "3.0"


def test_shadow_result() -> None:
    r = run_shadow("run-1", scores=[], events=[], actions=[{"a": 1}], live_run_meta={"action_count": 0})
    assert isinstance(r, ShadowResult)
    assert r.shadow is True
    assert r.actions_count == 1
    assert "action_count_delta" in r.diff_vs_live


def test_scheduler_grid_signal() -> None:
    sched = EnergyScheduler(island_mode=False)
    sched.set_grid_signal(GridSignal(frequency_hz=60.0, price_signal=0.12, is_island=True))
    assert sched.island_mode is True
    assert sched._grid_signal is not None


def test_node_health_empty(tmp_path: Path) -> None:
    from waveos.node_health import healthy_nodes, unhealthy_node_ids
    hb = tmp_path / "heartbeats.jsonl"
    hb.write_text("")  # empty
    status = healthy_nodes(hb, max_age_seconds=120)
    assert status == {}
    un = unhealthy_node_ids(hb, max_age_seconds=120)
    assert un == set()


def test_compliance_report(tmp_path: Path) -> None:
    report = generate_report("NERC", run_meta={"run_count": 10, "failure_count": 1}, audit_path=None)
    assert report.framework == "NERC"
    assert report.run_count == 10
    assert report.failure_count == 1
    assert len(report.findings) >= 0
    out = tmp_path / "report.json"
    write_report(report, out)
    assert out.is_file()


def test_quotas() -> None:
    assert check_quota("t1", None) is True
    assert check_quota("t1", 10) is True
    for _ in range(3):
        record_run("t1")
    assert check_quota("t1", 2) is False
    assert check_quota("t1", 5) is True


def test_policy_templates(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"rules": [{"id": "r1", "type": "soc_limit"}]}))
    rules = load_policy_templates(path)
    assert len(rules) == 1
    assert rules[0]["id"] == "r1"


def test_security_anomaly_callback() -> None:
    seen = []
    set_anomaly_callback(lambda rule_id, ctx: seen.append((rule_id, ctx)))
    on_anomaly("rule1", {"value": 99})
    assert len(seen) == 1
    assert seen[0][0] == "rule1"
    assert seen[0][1]["value"] == 99


def test_device_identity() -> None:
    ident = DeviceIdentity("dev-1", credential_hint="x509", site_id="s1")
    assert ident.device_id == "dev-1"
    assert ident.credential_hint == "x509"


def test_clearance_authorize() -> None:
    principal = Principal("u1", role=Role.ADMIN, clearance=Clearance.CONFIDENTIAL)
    ok = authorize(principal, Permission.DEPLOY_BUNDLE)
    assert ok is True
    low_clearance = Principal("u2", role=Role.ADMIN, clearance=Clearance.UNCLASSIFIED)
    ok2 = authorize(low_clearance, Permission.DEPLOY_BUNDLE)  # DEPLOY_BUNDLE requires CONFIDENTIAL
    assert ok2 is False


def test_list_nodes_cli(tmp_path: Path) -> None:
    (tmp_path / "out").mkdir(exist_ok=True)
    nodes_file = tmp_path / "out" / "nodes.json"
    nodes_file.write_text(json.dumps({"nodes": [{"node_id": "cli-node", "role": "edge"}]}))
    result = subprocess.run(
        [sys.executable, "-m", "waveos.cli", "list-nodes", "--file", str(nodes_file)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        env={**os.environ, "WAVEOS_LICENSE_KEY": "WAVEOS-CI-20991231-TEST"},
    )
    assert result.returncode == 0
    assert "cli-node" in result.stdout


def test_compliance_report_cli(tmp_path: Path) -> None:
    out = tmp_path / "compliance.json"
    result = subprocess.run(
        [sys.executable, "-m", "waveos.cli", "compliance-report", "--framework", "SOC2", "--out", str(out)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        env={**os.environ, "WAVEOS_LICENSE_KEY": "WAVEOS-CI-20991231-TEST"},
    )
    assert result.returncode == 0
    assert out.is_file()
    data = json.loads(out.read_text())
    assert data.get("framework") == "SOC2"
