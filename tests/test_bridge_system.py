"""Tests for WaveOS Bridge Layer."""

from __future__ import annotations

from waveos.bridge.orchestrator import BridgeConfig, BridgeMode, BridgeOrchestrator, BridgeState
from waveos.bridge.patterns import BRIDGE_PATTERNS, get_pattern_description, list_patterns


def test_bridge_startup_sequence() -> None:
    config = BridgeConfig(
        mode=BridgeMode.MIRROR,
        legacy_service="legacy",
        adapter_service="adapter",
        new_service="new-svc",
    )
    orch = BridgeOrchestrator(config)
    seq = orch.get_startup_sequence()
    assert len(seq) == 5
    assert seq[0]["step"] == "start_legacy"
    assert seq[1]["step"] == "start_adapter"
    assert seq[2]["step"] == "start_new"
    assert seq[3]["step"] == "validate"
    assert seq[4]["step"] == "route"


def test_bridge_execute_startup() -> None:
    config = BridgeConfig(
        mode=BridgeMode.MIRROR,
        legacy_service="legacy",
        adapter_service="adapter",
        new_service="new-svc",
    )
    orch = BridgeOrchestrator(config)
    result = orch.execute_startup()
    assert result["ok"]
    assert result["state"] == "active"
    assert orch.state == BridgeState.ACTIVE


def test_bridge_health_gate_failure() -> None:
    config = BridgeConfig(
        mode=BridgeMode.CANARY,
        legacy_service="old",
        new_service="new",
        health_threshold=80.0,
    )
    orch = BridgeOrchestrator(config)
    result = orch.execute_startup(health_check_fn=lambda: 50.0)
    assert not result["ok"]
    assert orch.state == BridgeState.FAILED


def test_bridge_mode_transition() -> None:
    config = BridgeConfig(mode=BridgeMode.MIRROR, legacy_service="old", new_service="new")
    orch = BridgeOrchestrator(config)
    orch.execute_startup()
    result = orch.transition_mode(BridgeMode.CANARY)
    assert result["ok"]
    assert result["to"] == "canary"


def test_bridge_mode_transition_blocked_by_health() -> None:
    config = BridgeConfig(mode=BridgeMode.MIRROR, health_threshold=90.0)
    orch = BridgeOrchestrator(config)
    result = orch.transition_mode(BridgeMode.CUTOVER, health_check_fn=lambda: 50.0)
    assert not result["ok"]


def test_bridge_patterns() -> None:
    assert len(BRIDGE_PATTERNS) == 3
    names = list_patterns()
    assert "adapter_facade" in names
    assert "mirror_canary_cutover" in names


def test_get_pattern_description() -> None:
    desc = get_pattern_description("adapter_facade")
    assert desc["name"] == "adapter_facade"
    assert "adapter" in desc["description"].lower()
    unknown = get_pattern_description("unknown")
    assert unknown["description"] == "Unknown pattern"
