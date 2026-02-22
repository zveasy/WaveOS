"""V2: Device heartbeat — emit and optionally aggregate device liveness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.heartbeat")


def emit_heartbeat(
    node_id: str,
    payload: Optional[Dict[str, Any]] = None,
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Emit a heartbeat record (timestamp, node_id, optional payload). Optionally write to output_path (JSONL)."""
    record = {
        "timestamp": utc_now().isoformat(),
        "node_id": node_id,
        "payload": payload or {},
    }
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    return record


def read_latest_heartbeats(heartbeat_path: Path, max_per_node: int = 1) -> Dict[str, Dict[str, Any]]:
    """Read latest heartbeat per node from a JSONL file. Returns {node_id: record}."""
    if not heartbeat_path.is_file():
        return {}
    from collections import defaultdict
    by_node: Dict[str, list] = defaultdict(list)
    with heartbeat_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                nid = rec.get("node_id")
                if nid:
                    by_node[nid].append(rec)
            except json.JSONDecodeError:
                continue
    return {
        nid: (sorted(recs, key=lambda r: r.get("timestamp", ""), reverse=True)[:max_per_node][0])
        for nid, recs in by_node.items()
    }
