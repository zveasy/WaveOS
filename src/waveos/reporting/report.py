from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from jinja2 import Environment, FileSystemLoader

from waveos.models import ActionRecommendation, Event, HealthScore, RunStats
from waveos.utils import get_logger, span, utc_now, write_csv, write_json, write_jsonl

logger = get_logger("waveos.reporting")

EVIDENCE_ATTESTATION_FILENAME = "evidence_attestation.json"
ATTESTATION_ARTIFACTS = (
    "run_meta.json",
    "health_summary.json",
    "actions.json",
    "events.jsonl",
    "explainability.json",
    "report.html",
    "metrics.csv",
)
ACTION_SIGNING_EVIDENCE_FILENAME = "action_signing_evidence.json"


def write_outputs(
    out_dir: Path,
    health_scores: Iterable[HealthScore],
    events: Iterable[Event],
    actions: Iterable[ActionRecommendation],
    run_id: str | None = None,
    explainability: bool = True,
    run_meta: Optional[dict] = None,
    run_stats: Optional[Iterable[RunStats]] = None,
    evidence_pack_enabled: bool = True,
    encrypt_artifacts: bool = False,
    action_outcomes: Optional[List[dict]] = None,
    action_signing_evidence: Optional[dict] = None,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    if action_signing_evidence is not None:
        write_json(out_dir / ACTION_SIGNING_EVIDENCE_FILENAME, action_signing_evidence)
    health_payload = [score.model_dump() for score in health_scores]
    events_payload = [event.model_dump() for event in events]
    actions_payload = [action.model_dump() for action in actions]
    explainability_payload = _build_explainability(health_payload, actions_payload, run_id=run_id) if explainability else []

    health_path = out_dir / "health_summary.json"
    events_path = out_dir / "events.jsonl"
    actions_path = out_dir / "actions.json"
    explainability_path = out_dir / "explainability.json"
    run_meta_path = out_dir / "run_meta.json"
    metrics_path = out_dir / "metrics.csv"
    write_json(health_path, health_payload)
    write_json(actions_path, actions_payload)
    if explainability:
        write_json(explainability_path, explainability_payload)
    else:
        explainability_path.unlink(missing_ok=True)
    write_jsonl(events_path, events_payload)
    if run_meta:
        if encrypt_artifacts:
            try:
                from waveos.utils.encryption import write_json_encrypted
                write_json_encrypted(run_meta_path, run_meta, fallback_plain=True)
            except (ImportError, OSError, ValueError, TypeError) as exc:
                logger.debug("Encrypted write failed, falling back to plain: %s", type(exc).__name__)
                write_json(run_meta_path, run_meta)
        else:
            write_json(run_meta_path, run_meta)
    if run_stats:
        rows = []
        for stat in run_stats:
            for metric, value in stat.metrics.items():
                rows.append(
                    {
                        "run_id": run_id or "",
                        "entity_type": stat.entity_type,
                        "entity_id": stat.entity_id,
                        "metric": metric,
                        "value": value,
                        "window_start": stat.window_start,
                        "window_end": stat.window_end,
                    }
                )
        if rows:
            write_csv(metrics_path, rows, fieldnames=list(rows[0].keys()))

    report_path = render_report(
        out_dir, health_payload, events_payload, actions_payload,
        run_id=run_id, action_outcomes=action_outcomes,
    )
    if evidence_pack_enabled:
        build_evidence_attestation(out_dir, run_id)
        _export_evidence_pack(out_dir, run_id)
    return report_path


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_evidence_attestation(out_dir: Path, run_id: str | None = None) -> Path:
    """Write evidence_attestation.json with artifact paths and SHA-256 hashes (Persistence Phase 3)."""
    artifacts: List[Dict[str, str]] = []
    for name in ATTESTATION_ARTIFACTS:
        p = out_dir / name
        if p.is_file():
            artifacts.append({"path": name, "sha256": _sha256_file(p)})
    if (out_dir / ACTION_SIGNING_EVIDENCE_FILENAME).is_file():
        artifacts.append({"path": ACTION_SIGNING_EVIDENCE_FILENAME, "sha256": _sha256_file(out_dir / ACTION_SIGNING_EVIDENCE_FILENAME)})
    payload: Dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "timestamp_utc": utc_now().isoformat(),
        "artifacts": artifacts,
    }
    attestation_path = out_dir / EVIDENCE_ATTESTATION_FILENAME
    write_json(attestation_path, payload)
    logger.debug("Wrote evidence attestation to %s", attestation_path)
    return attestation_path


def verify_evidence_attestation(attestation_path: Path) -> Tuple[bool, List[str]]:
    """Verify artifact hashes in attestation manifest; return (ok, list of mismatch messages)."""
    if not attestation_path.is_file():
        return False, [f"Attestation file not found: {attestation_path}"]
    payload = json.loads(attestation_path.read_text(encoding="utf-8"))
    out_dir = attestation_path.parent
    artifacts = payload.get("artifacts", [])
    errors: List[str] = []
    for entry in artifacts:
        path = out_dir / entry.get("path", "")
        expected = entry.get("sha256")
        if not path.is_file():
            errors.append(f"Missing artifact: {path.name}")
            continue
        if expected and _sha256_file(path) != expected:
            errors.append(f"Hash mismatch: {path.name}")
    return len(errors) == 0, errors


def _export_evidence_pack(out_dir: Path, run_id: str | None) -> None:
    name = f"evidence_pack_{run_id or 'run'}.zip"
    pack_path = out_dir / name
    with zipfile.ZipFile(pack_path, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        for path in out_dir.iterdir():
            if path.is_file() and path.name != pack_path.name:
                handle.write(path, arcname=path.name)


def _build_explainability(
    health_payload: List[dict],
    actions_payload: List[dict],
    run_id: str | None = None,
) -> List[dict]:
    health_map = {(h["entity_type"], h["entity_id"]): h for h in health_payload}
    explainability: List[dict] = []
    for action in actions_payload:
        key = (action["entity_type"], action["entity_id"])
        health = health_map.get(key, {})
        explainability.append(
            {
                "schema_version": 1,
                "run_id": run_id,
                "entity_type": action["entity_type"],
                "entity_id": action["entity_id"],
                "action": action["action"],
                "rationale": action.get("rationale"),
                "rule_id": action.get("rule_id"),
                "drivers": health.get("drivers", []),
                "status": health.get("status"),
                "score": health.get("score"),
            }
        )
    return explainability


def render_report(
    out_dir: Path,
    health_payload: List[dict],
    events_payload: List[dict],
    actions_payload: List[dict],
    run_id: str | None = None,
    action_outcomes: Optional[List[dict]] = None,
) -> Path:
    templates_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(templates_dir), autoescape=True)
    template = env.get_template("report.html.j2")
    with span("report_render") as active_span:
        if run_id:
            active_span.set_attribute("waveos.run_id", run_id)
        active_span.set_attribute("waveos.action_count", len(actions_payload))
        active_span.set_attribute("waveos.event_count", len(events_payload))
        html = template.render(
            health_scores=health_payload,
            events=events_payload,
            actions=actions_payload,
            action_outcomes=action_outcomes or [],
        )
    report_path = out_dir / "report.html"
    report_path.write_text(html, encoding="utf-8")
    return report_path
