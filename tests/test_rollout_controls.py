"""Tests for WaveOS Rollout Controls."""

from __future__ import annotations

from waveos.rollout_controls import (
    DEFAULT_POLICIES,
    DEFAULT_ROLLBACK_TRIGGERS,
    ChannelPolicy,
    DeploymentChannel,
    HealthGate,
    RollbackTrigger,
    check_channel_requirements,
    evaluate_health_gates,
    evaluate_rollback_triggers,
    get_channel_policy,
)


def test_default_policies() -> None:
    assert len(DEFAULT_POLICIES) == 4
    dev = get_channel_policy("dev")
    assert not dev.require_signature
    prod = get_channel_policy("prod")
    assert prod.require_signature
    assert prod.require_attestation


def test_channel_policy_roundtrip() -> None:
    policy = ChannelPolicy(channel=DeploymentChannel.STAGING, require_signature=True)
    d = policy.to_dict()
    restored = ChannelPolicy.from_dict(d)
    assert restored.channel == DeploymentChannel.STAGING
    assert restored.require_signature


def test_evaluate_health_gates_pass() -> None:
    gates = [HealthGate(name="health", threshold=50.0)]
    ok, results = evaluate_health_gates(gates, health_score=80.0)
    assert ok
    assert results[0]["passed"]


def test_evaluate_health_gates_fail() -> None:
    gates = [HealthGate(name="health", threshold=90.0)]
    ok, results = evaluate_health_gates(gates, health_score=50.0)
    assert not ok


def test_evaluate_rollback_triggers_none() -> None:
    should, triggered = evaluate_rollback_triggers(DEFAULT_ROLLBACK_TRIGGERS, health_score=80.0)
    assert not should
    assert triggered == []


def test_evaluate_rollback_triggers_crash_loop() -> None:
    triggers = [RollbackTrigger(name="crash", trigger_type="crash_loop", threshold=3)]
    should, triggered = evaluate_rollback_triggers(triggers, crash_count=5)
    assert should
    assert len(triggered) == 1


def test_evaluate_rollback_triggers_health() -> None:
    triggers = [RollbackTrigger(name="health", trigger_type="health_below", threshold=30.0)]
    should, triggered = evaluate_rollback_triggers(triggers, health_score=20.0)
    assert should


def test_check_channel_requirements_dev() -> None:
    ok, violations = check_channel_requirements("dev")
    assert ok


def test_check_channel_requirements_prod_missing() -> None:
    ok, violations = check_channel_requirements("prod")
    assert not ok
    assert any("signature" in v for v in violations)


def test_check_channel_requirements_prod_all_met() -> None:
    ok, violations = check_channel_requirements(
        "prod",
        has_signature=True,
        has_attestation=True,
        has_sbom=True,
        health_score=90.0,
        has_approval=True,
    )
    assert ok
