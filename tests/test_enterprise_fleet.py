"""Tests for fleet reconciliation, self-update, failure drills, dashboard (§9-10)."""
from __future__ import annotations
import json
from pathlib import Path
from waveos.fleet.reconciliation import FleetReconciler, DesiredFleetState, NodeDesiredState
from waveos.fleet.self_update import AgentSelfUpdater
from waveos.fleet.drills import list_drills, run_drill, FailureDrill, DrillType
from waveos.dashboard.server import DashboardDataProvider

def test_reconcile_update_needed():
    desired = DesiredFleetState(default_bundle_id="b2")
    r = FleetReconciler(desired)
    result = r.reconcile({"node-1": "b1", "node-2": "b2"})
    actions = {a.node_id: a.action for a in result.actions}
    assert actions["node-1"] == "update"
    assert actions["node-2"] == "noop"

def test_reconcile_node_override():
    desired = DesiredFleetState(default_bundle_id="b1",
        node_overrides={"special": NodeDesiredState(node_id="special", desired_bundle_id="b3")})
    result = FleetReconciler(desired).reconcile({"special": "b1"})
    assert result.actions[0].action == "update" and result.actions[0].desired_bundle == "b3"

def test_reconcile_save_load(tmp_path: Path):
    desired = DesiredFleetState(default_bundle_id="b1")
    r = FleetReconciler(desired)
    p = tmp_path / "desired.json"
    r.save_desired(p)
    loaded = FleetReconciler.load_desired(p)
    assert loaded.desired.default_bundle_id == "b1"

def test_self_updater_version():
    updater = AgentSelfUpdater()
    assert updater.get_current_version() != ""

def test_self_updater_check():
    updater = AgentSelfUpdater()
    result = updater.check_update_available()
    assert "current_version" in result

def test_default_drills():
    drills = list_drills()
    assert len(drills) >= 5
    names = [d.name for d in drills]
    assert "registry_down" in names and "network_split" in names

def test_run_drill_dry():
    drill = FailureDrill(name="test", drill_type=DrillType.REGISTRY_OUTAGE,
                         expected_behavior="Agent retries", recovery_steps=["Restore"])
    result = run_drill(drill)
    assert result.passed and "Dry run" in result.observations[0]

def test_run_drill_with_sim():
    drill = FailureDrill(name="test", drill_type=DrillType.AGENT_CRASH)
    result = run_drill(drill, simulate_fn=lambda d: True)
    assert result.passed and result.recovery_verified

def test_dashboard_data_provider(tmp_path: Path):
    provider = DashboardDataProvider(registry_root=tmp_path / "reg")
    fleet = provider.get_fleet_data()
    assert "nodes" in fleet
    reg = provider.get_registry_data()
    assert "bundles" in reg
    drills = provider.get_drills_data()
    assert "drills" in drills
