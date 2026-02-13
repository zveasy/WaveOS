"""V3: Node registry and topology for federated/air-gapped control."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger

logger = get_logger("waveos.orchestration")


class NodeRole(str, Enum):
    EDGE = "edge"
    CLOUD = "cloud"
    AIR_GAPPED = "air_gapped"
    CONTROLLER = "controller"


@dataclass
class NodeRecord:
    node_id: str
    role: NodeRole
    endpoint: Optional[str] = None  # e.g. https://node1.local
    site_id: Optional[str] = None
    meta: Dict[str, Any] = None

    def __post_init__(self) -> None:
        if self.meta is None:
            self.meta = {}


_registry: Dict[str, NodeRecord] = {}


def get_node_registry() -> Dict[str, NodeRecord]:
    return dict(_registry)


def register_node(node_id: str, role: NodeRole, endpoint: Optional[str] = None, site_id: Optional[str] = None, meta: Optional[Dict[str, Any]] = None) -> None:
    _registry[node_id] = NodeRecord(node_id=node_id, role=role, endpoint=endpoint, site_id=site_id, meta=meta or {})


def load_nodes_from_file(path: Path) -> int:
    """Load node registry from JSON; return count loaded."""
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        nodes = data.get("nodes", data) if isinstance(data, dict) else data
        if not isinstance(nodes, list):
            return 0
        for n in nodes:
            if isinstance(n, dict) and n.get("node_id"):
                register_node(
                    n["node_id"],
                    NodeRole(n.get("role", "edge")),
                    n.get("endpoint"),
                    n.get("site_id"),
                    n.get("meta"),
                )
        return len(nodes)
    except Exception as exc:
        logger.warning("Failed to load nodes from %s: %s", path, type(exc).__name__)
        return 0


def save_nodes_to_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nodes = []
    for r in _registry.values():
        d = asdict(r)
        d["role"] = r.role.value
        nodes.append(d)
    path.write_text(json.dumps({"nodes": nodes}, indent=2), encoding="utf-8")
