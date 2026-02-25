"""Fleet state reconciliation — converge devices to desired state after disconnection."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.fleet.reconciliation")


@dataclass
class NodeDesiredState:
    node_id: str
    desired_bundle_id: str
    desired_version: str = ""
    channel: str = "prod"
    force: bool = False

    def to_dict(self) -> dict:
        return {"node_id": self.node_id, "desired_bundle_id": self.desired_bundle_id,
                "desired_version": self.desired_version, "channel": self.channel, "force": self.force}

    @classmethod
    def from_dict(cls, d: dict) -> NodeDesiredState:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


@dataclass
class DesiredFleetState:
    """Desired state for the entire fleet."""
    default_bundle_id: str = ""
    default_version: str = ""
    default_channel: str = "prod"
    node_overrides: Dict[str, NodeDesiredState] = field(default_factory=dict)
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {"default_bundle_id": self.default_bundle_id, "default_version": self.default_version,
                "default_channel": self.default_channel,
                "node_overrides": {k: v.to_dict() for k, v in self.node_overrides.items()},
                "updated_at": self.updated_at or utc_now().isoformat()}

    @classmethod
    def from_dict(cls, d: dict) -> DesiredFleetState:
        overrides = {k: NodeDesiredState.from_dict(v) for k, v in d.get("node_overrides", {}).items()}
        return cls(default_bundle_id=d.get("default_bundle_id", ""),
                   default_version=d.get("default_version", ""),
                   default_channel=d.get("default_channel", "prod"),
                   node_overrides=overrides, updated_at=d.get("updated_at", ""))

    def get_desired_for_node(self, node_id: str) -> NodeDesiredState:
        if node_id in self.node_overrides:
            return self.node_overrides[node_id]
        return NodeDesiredState(node_id=node_id, desired_bundle_id=self.default_bundle_id,
                                desired_version=self.default_version, channel=self.default_channel)


@dataclass
class ReconciliationAction:
    node_id: str
    action: str  # update | rollback | noop | skip
    current_bundle: str = ""
    desired_bundle: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {"node_id": self.node_id, "action": self.action, "current_bundle": self.current_bundle,
                "desired_bundle": self.desired_bundle, "reason": self.reason}


@dataclass
class ReconciliationResult:
    actions: List[ReconciliationAction] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {"actions": [a.to_dict() for a in self.actions],
                "timestamp": self.timestamp or utc_now().isoformat()}


class FleetReconciler:
    """Reconciles fleet to desired state."""

    def __init__(self, desired: DesiredFleetState) -> None:
        self.desired = desired

    def reconcile(self, current_states: Dict[str, str]) -> ReconciliationResult:
        """Compare current node states to desired and produce actions.
        current_states: {node_id: current_bundle_id}
        """
        result = ReconciliationResult(timestamp=utc_now().isoformat())
        all_nodes = set(current_states.keys()) | set(self.desired.node_overrides.keys())
        for node_id in sorted(all_nodes):
            desired = self.desired.get_desired_for_node(node_id)
            current = current_states.get(node_id, "")
            if not desired.desired_bundle_id:
                result.actions.append(ReconciliationAction(node_id=node_id, action="noop",
                    current_bundle=current, reason="No desired state defined"))
                continue
            if current == desired.desired_bundle_id:
                result.actions.append(ReconciliationAction(node_id=node_id, action="noop",
                    current_bundle=current, desired_bundle=desired.desired_bundle_id,
                    reason="Already at desired version"))
            elif not current:
                result.actions.append(ReconciliationAction(node_id=node_id, action="update",
                    desired_bundle=desired.desired_bundle_id, reason="No bundle installed"))
            else:
                result.actions.append(ReconciliationAction(node_id=node_id, action="update",
                    current_bundle=current, desired_bundle=desired.desired_bundle_id,
                    reason="Version mismatch"))
        return result

    def save_desired(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.desired.to_dict(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load_desired(cls, path: Path) -> FleetReconciler:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(DesiredFleetState.from_dict(data))
