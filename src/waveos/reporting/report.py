from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from jinja2 import Environment, FileSystemLoader

from waveos.models import ActionRecommendation, Event, HealthScore
from waveos.utils import span, write_json, write_jsonl


def write_outputs(
    out_dir: Path,
    health_scores: Iterable[HealthScore],
    events: Iterable[Event],
    actions: Iterable[ActionRecommendation],
    run_id: str | None = None,
    explainability: bool = True,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    health_payload = [score.model_dump() for score in health_scores]
    events_payload = [event.model_dump() for event in events]
    actions_payload = [action.model_dump() for action in actions]
    explainability_payload = _build_explainability(health_payload, actions_payload, run_id=run_id) if explainability else []

    health_path = out_dir / "health_summary.json"
    events_path = out_dir / "events.jsonl"
    actions_path = out_dir / "actions.json"
    explainability_path = out_dir / "explainability.json"
    write_json(health_path, health_payload)
    write_json(actions_path, actions_payload)
    if explainability:
        write_json(explainability_path, explainability_payload)
    else:
        explainability_path.unlink(missing_ok=True)
    write_jsonl(events_path, events_payload)

    return render_report(out_dir, health_payload, events_payload, actions_payload, run_id=run_id)


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
        )
    report_path = out_dir / "report.html"
    report_path.write_text(html, encoding="utf-8")
    return report_path
