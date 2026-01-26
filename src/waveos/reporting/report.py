from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from jinja2 import Environment, FileSystemLoader

from waveos.models import ActionRecommendation, Event, HealthScore
from waveos.utils import write_json, write_jsonl


def write_outputs(
    out_dir: Path,
    health_scores: Iterable[HealthScore],
    events: Iterable[Event],
    actions: Iterable[ActionRecommendation],
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    health_payload = [score.model_dump() for score in health_scores]
    events_payload = [event.model_dump() for event in events]
    actions_payload = [action.model_dump() for action in actions]

    health_path = out_dir / "health_summary.json"
    events_path = out_dir / "events.jsonl"
    actions_path = out_dir / "actions.json"
    write_json(health_path, health_payload)
    write_json(actions_path, actions_payload)
    write_jsonl(events_path, events_payload)

    return render_report(out_dir, health_payload, events_payload, actions_payload)


def render_report(
    out_dir: Path,
    health_payload: List[dict],
    events_payload: List[dict],
    actions_payload: List[dict],
) -> Path:
    templates_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(templates_dir), autoescape=True)
    template = env.get_template("report.html.j2")
    html = template.render(
        health_scores=health_payload,
        events=events_payload,
        actions=actions_payload,
    )
    report_path = out_dir / "report.html"
    report_path.write_text(html, encoding="utf-8")
    return report_path
