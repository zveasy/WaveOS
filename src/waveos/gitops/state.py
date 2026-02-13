"""V3: Desired state (JSON/YAML), current state from registry, diff, state history."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.gitops")


@dataclass
class DesiredState:
    """V3: Declarative desired state for infrastructure (GitOps)."""
    schema_version: int = 1
    waveos_version: Optional[str] = None
    policy_version: Optional[str] = None
    bundle_id: Optional[str] = None
    nodes: List[Dict[str, Any]] = field(default_factory=list)
    devices: List[Dict[str, Any]] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)


def load_desired_state(path: Path) -> Optional[DesiredState]:
    """Load desired state from JSON or YAML file."""
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
        if path.suffix in (".yaml", ".yml"):
            try:
                import yaml
                data = yaml.safe_load(text)
            except ImportError:
                data = json.loads(text)
        else:
            data = json.loads(text)
        if not isinstance(data, dict):
            return None
        return DesiredState(
            schema_version=data.get("schema_version", 1),
            waveos_version=data.get("waveos_version"),
            policy_version=data.get("policy_version"),
            bundle_id=data.get("bundle_id"),
            nodes=data.get("nodes", []),
            devices=data.get("devices", []),
            meta=data.get("meta", {}),
        )
    except Exception as exc:
        logger.warning("Failed to load desired state from %s: %s", path, type(exc).__name__)
        return None


def current_state_from_registry(
    state_registry_path: Optional[Path] = None,
    node_registry: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build current state from state registry and node registry (for diff)."""
    current: Dict[str, Any] = {"nodes": [], "devices": [], "waveos_version": None, "bundle_id": None}
    if node_registry:
        for nid, rec in node_registry.items():
            if hasattr(rec, "role"):
                current["nodes"].append({"node_id": nid, "role": rec.role.value, "endpoint": getattr(rec, "endpoint", None), "site_id": getattr(rec, "site_id", None)})
            elif isinstance(rec, dict):
                current["nodes"].append({"node_id": nid, "role": rec.get("role", ""), "endpoint": rec.get("endpoint"), "site_id": rec.get("site_id")})
    return current


def diff_state(desired: DesiredState, current: Dict[str, Any]) -> Dict[str, Any]:
    """Return diff: additions, removals, changes (V3 GitOps)."""
    diff: Dict[str, Any] = {"additions": [], "removals": [], "changes": []}
    desired_node_ids = {n.get("node_id") for n in desired.nodes if isinstance(n, dict) and n.get("node_id")}
    current_node_ids = {n.get("node_id") for n in current.get("nodes", []) if isinstance(n, dict)}
    for nid in desired_node_ids:
        if nid and nid not in current_node_ids:
            diff["additions"].append({"type": "node", "id": nid})
    for nid in current_node_ids:
        if nid and nid not in desired_node_ids:
            diff["removals"].append({"type": "node", "id": nid})
    if desired.waveos_version and desired.waveos_version != current.get("waveos_version"):
        diff["changes"].append({"field": "waveos_version", "desired": desired.waveos_version, "current": current.get("waveos_version")})
    if desired.bundle_id and desired.bundle_id != current.get("bundle_id"):
        diff["changes"].append({"field": "bundle_id", "desired": desired.bundle_id, "current": current.get("bundle_id")})
    return diff


def save_state_history(history_path: Path, state_snapshot: Dict[str, Any], reason: str = "") -> None:
    """Append state snapshot to history (append-only log for replay)."""
    history_path.parent.mkdir(parents=True, exist_ok=True)
    record = {"timestamp": utc_now().isoformat(), "reason": reason, "state": state_snapshot}
    with history_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def apply_desired_state(
    desired: DesiredState,
    state_history_path: Path,
    desired_state_path: Optional[Path] = None,
) -> Path:
    """V3: Apply desired state — write to file (approval gate can call this after diff)."""
    state_snapshot = {
        "schema_version": desired.schema_version,
        "waveos_version": desired.waveos_version,
        "policy_version": desired.policy_version,
        "bundle_id": desired.bundle_id,
        "nodes": desired.nodes,
        "devices": desired.devices,
    }
    save_state_history(state_history_path, state_snapshot, reason="apply_desired_state")
    if desired_state_path:
        desired_state_path.parent.mkdir(parents=True, exist_ok=True)
        desired_state_path.write_text(
            json.dumps(state_snapshot, indent=2) + "\n",
            encoding="utf-8",
        )
        return desired_state_path
    return state_history_path
