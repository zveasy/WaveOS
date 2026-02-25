"""Tests for governance: promotion gates, audit chain, separation of duties (§7-8)."""
from __future__ import annotations
from pathlib import Path
from waveos.governance.promotion import PromotionRequest, evaluate_promotion, PromotionGate
from waveos.governance.audit_chain import GovernanceAuditChain, GovernanceEvent
from waveos.governance.separation import SeparationOfDuties, DutyRole
from waveos.bridge.contracts import InterfaceContract, validate_against_contract, validate_adapter, RoutingEnforcer, CompatTestCase, run_compat_tests

def test_promotion_dev_to_staging():
    req = PromotionRequest(bundle_id="b1", from_channel="dev", to_channel="staging",
                          requester="ci", has_signature=True, is_ci=True)
    result = evaluate_promotion(req)
    assert result.approved

def test_promotion_requires_signature():
    req = PromotionRequest(bundle_id="b1", from_channel="dev", to_channel="staging",
                          requester="human", has_signature=False, is_ci=True)
    result = evaluate_promotion(req)
    assert not result.approved

def test_promotion_separation_of_duties():
    req = PromotionRequest(bundle_id="b1", from_channel="staging", to_channel="prod",
                          requester="alice", builder="alice", approvers=["alice"],
                          has_signature=True, has_attestation=True, has_sbom=True, health_score=90)
    result = evaluate_promotion(req)
    assert not result.approved
    assert any("separation" in v.lower() for v in result.violations)

def test_promotion_backward_blocked():
    req = PromotionRequest(bundle_id="b1", from_channel="prod", to_channel="dev", requester="x")
    result = evaluate_promotion(req)
    assert not result.approved

def test_governance_audit_chain(tmp_path: Path):
    p = tmp_path / "audit.json"
    chain = GovernanceAuditChain(p)
    chain.record("publish", "ci-bot", bundle_id="b1", channel="dev")
    chain.record("promote", "admin", bundle_id="b1", channel="staging")
    ok, errors = chain.verify()
    assert ok

def test_governance_audit_who_deployed():
    chain = GovernanceAuditChain()
    chain.record("publish", "ci", bundle_id="b1")
    chain.record("promote", "admin", bundle_id="b1", channel="prod")
    deps = chain.who_deployed_what()
    assert len(deps) == 2

def test_separation_of_duties():
    sod = SeparationOfDuties()
    sod.assign("alice", [DutyRole.BUILDER])
    sod.assign("bob", [DutyRole.APPROVER])
    ok, _ = sod.check_can_approve("bob", "alice")
    assert ok
    ok2, msg = sod.check_can_approve("alice", "alice")
    assert not ok2

def test_interface_contract():
    contract = InterfaceContract(contract_id="c1", version="1.0",
        input_schema={"required": ["id"], "properties": {"id": {"type": "string"}}},
        output_schema={"required": ["result"], "properties": {"result": {"type": "string"}}})
    ok, errs = validate_against_contract({"id": "123"}, contract, "input")
    assert ok
    ok2, errs2 = validate_against_contract({}, contract, "input")
    assert not ok2

def test_routing_enforcer():
    re = RoutingEnforcer()
    ok, _ = re.set_mode("canary", canary_percent=10)
    assert ok and re.state.canary_percent == 10
    re.lock("maintenance")
    ok2, msg = re.set_mode("cutover")
    assert not ok2

def test_compat_test_harness():
    contract = InterfaceContract(contract_id="c1", version="1.0",
        input_schema={"required": ["x"], "properties": {"x": {"type": "integer"}}},
        output_schema={"required": ["y"], "properties": {"y": {"type": "integer"}}})
    def adapter(data):
        return {"y": data["x"] * 2}
    cases = [CompatTestCase(name="double", input_data={"x": 5}, expected_output={"y": 10})]
    result = run_compat_tests(adapter, contract, cases)
    assert result.passed == 1 and result.failed == 0
