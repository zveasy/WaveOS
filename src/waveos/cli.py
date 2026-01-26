"""Wave OS CLI entrypoint."""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path
from typing import Dict, Iterable, List

from rich.console import Console
from rich.table import Table

from waveos.actuators import MockActuator
from waveos.collectors import load_records
from waveos.models import BaselineStats, Event, EventLevel, HealthScore, HealthStatus, RunStats
from waveos.normalize import normalize_records
from waveos.policy import recommend_actions
from waveos.reporting import render_report, write_outputs
from waveos.scoring import build_stats, score_links
from waveos.sim import build_demo_dataset
from waveos.utils import get_logger, read_json, read_jsonl, setup_logging, write_json, write_jsonl

console = Console()
logger = get_logger("waveos.cli")


def _find_telemetry_files(in_dir: Path) -> List[Path]:
    candidates = list(in_dir.glob("telemetry.*"))
    if not candidates:
        candidates = list(in_dir.glob("*.jsonl")) + list(in_dir.glob("*.json"))
    return candidates


def _load_samples(in_dir: Path):
    samples = []
    for path in _find_telemetry_files(in_dir):
        records = load_records(path)
        samples.extend(normalize_records(records))
    return samples


def _baseline_map(records: Iterable[dict]) -> Dict[str, BaselineStats]:
    stats = [BaselineStats(**record) for record in records]
    return {entry.entity_id: entry for entry in stats}


def _run_map(records: Iterable[dict]) -> Dict[str, RunStats]:
    stats = [RunStats(**record) for record in records]
    return {entry.entity_id: entry for entry in stats}


def _build_events(scores: Iterable[HealthScore]) -> List[Event]:
    events: List[Event] = []
    for score in scores:
        if score.status == HealthStatus.PASS:
            continue
        level = EventLevel.WARN if score.status == HealthStatus.WARN else EventLevel.ERROR
        events.append(
            Event(
                timestamp=score.window_end,
                level=level,
                message=f"{score.entity_type} {score.entity_id} {score.status} drivers={','.join(score.drivers)}",
                entity_type=score.entity_type,
                entity_id=score.entity_id,
                details={"drivers": score.drivers, "score": score.score},
            )
        )
    return events


def _render_console_summary(scores: Iterable[HealthScore]) -> None:
    table = Table(title="Wave OS Health Summary")
    table.add_column("Entity")
    table.add_column("Status")
    table.add_column("Score")
    table.add_column("Drivers")
    for score in scores:
        table.add_row(
            f"{score.entity_type}:{score.entity_id}",
            score.status,
            f"{score.score:.1f}",
            ", ".join(score.drivers),
        )
    console.print(table)


def cmd_sim(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    baseline_dir, run_dir = build_demo_dataset(out_dir)
    console.print(f"Generated baseline data in {baseline_dir}")
    console.print(f"Generated run data in {run_dir}")
    return 0


def cmd_baseline(args: argparse.Namespace) -> int:
    in_dir = Path(args.input)
    samples = _load_samples(in_dir)
    baseline_stats, _ = build_stats(samples)
    payload = [stat.model_dump() for stat in baseline_stats]
    write_json(in_dir / "baseline.json", payload)
    write_jsonl(in_dir / "normalized.jsonl", [s.model_dump() for s in samples])
    console.print(f"Wrote baseline stats to {in_dir / 'baseline.json'}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    in_dir = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    baseline_dir = Path(args.baseline)
    baseline_path = baseline_dir / "baseline.json"
    if not baseline_path.exists():
        console.print(f"Missing baseline.json in {baseline_dir}")
        return 1
    samples = _load_samples(in_dir)
    _, run_stats = build_stats(samples)
    baseline_records = read_json(baseline_path)
    baseline_map = _baseline_map(baseline_records)
    run_map = {stat.entity_id: stat for stat in run_stats}
    scores = score_links(baseline_map, run_map)
    actions = recommend_actions(scores)
    events = _build_events(scores)
    MockActuator().apply(actions)

    write_json(out_dir / "run_stats.json", [stat.model_dump() for stat in run_stats])
    report_path = write_outputs(out_dir, scores, events, actions)
    _render_console_summary(scores)
    console.print(f"Report written to {report_path}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    out_dir = Path(args.input)
    health_path = out_dir / "health_summary.json"
    events_path = out_dir / "events.jsonl"
    actions_path = out_dir / "actions.json"
    health_payload = read_json(health_path)
    events_payload = read_jsonl(events_path)
    actions_payload = read_json(actions_path)
    report_path = render_report(out_dir, health_payload, events_payload, actions_payload)
    console.print(f"Report written to {report_path}")
    if args.open:
        webbrowser.open(report_path.resolve().as_uri())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="waveos", description="Wave OS demo CLI")
    sub = parser.add_subparsers(dest="command")

    sim_parser = sub.add_parser("sim", help="Generate simulated telemetry")
    sim_parser.add_argument("--out", required=True, dest="out")
    sim_parser.set_defaults(func=cmd_sim)

    base_parser = sub.add_parser("baseline", help="Build baseline stats")
    base_parser.add_argument("--in", required=True, dest="input")
    base_parser.set_defaults(func=cmd_baseline)

    run_parser = sub.add_parser("run", help="Run scoring + policy on telemetry")
    run_parser.add_argument("--in", required=True, dest="input")
    run_parser.add_argument("--baseline", required=True)
    run_parser.add_argument("--out", required=True, dest="output")
    run_parser.set_defaults(func=cmd_run)

    report_parser = sub.add_parser("report", help="Render HTML report")
    report_parser.add_argument("--in", required=True, dest="input")
    report_parser.add_argument("--open", action="store_true", default=False)
    report_parser.set_defaults(func=cmd_report)

    return parser


def main() -> None:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "func", None):
        parser.print_help()
        raise SystemExit(1)
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
