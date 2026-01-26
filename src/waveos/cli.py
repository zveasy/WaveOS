"""Wave OS CLI entrypoint."""

from __future__ import annotations

import argparse
import logging
import sys
import webbrowser
from pathlib import Path
from typing import Dict, Iterable, List
from uuid import uuid4

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
from waveos.utils import (
    get_logger,
    install_signal_handlers,
    read_json,
    read_jsonl,
    load_config,
    setup_logging,
    should_shutdown,
    start_metrics_server,
    write_json,
    write_jsonl,
    init_tracer,
    AlertRoute,
    route_alerts,
    Principal,
    Role,
    Permission,
    authorize,
    TokenAuth,
    load_token_roles_from_env,
    load_token_roles_from_config,
    append_audit,
    utc_now,
    get_secret,
    config_fingerprint,
)
from pydantic import ValidationError

console = Console()
logger = get_logger("waveos.cli")


def _find_telemetry_files(in_dir: Path) -> List[Path]:
    candidates = list(in_dir.glob("telemetry.*"))
    if not candidates:
        candidates = list(in_dir.glob("*.jsonl")) + list(in_dir.glob("*.json"))
    return candidates


def _load_samples(in_dir: Path, run_id: str | None = None):
    samples = []
    for path in _find_telemetry_files(in_dir):
        if should_shutdown():
            return samples
        records = load_records(path)
        samples.extend(normalize_records(records, run_id=run_id))
    return samples


def _baseline_map(records: Iterable[dict]) -> Dict[str, BaselineStats]:
    stats = [BaselineStats(**record) for record in records]
    return {entry.entity_id: entry for entry in stats}


def _run_map(records: Iterable[dict]) -> Dict[str, RunStats]:
    stats = [RunStats(**record) for record in records]
    return {entry.entity_id: entry for entry in stats}


def _build_events(scores: Iterable[HealthScore], run_id: str | None = None) -> List[Event]:
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
                details={"drivers": score.drivers, "score": score.score, "run_id": run_id},
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
    if not _authorize(args, Permission.RUN_PIPELINE):
        console.print("Access denied: run_pipeline required")
        return 3
    in_dir = Path(args.input)
    samples = _load_samples(in_dir)
    baseline_stats, _ = build_stats(samples)
    payload = [stat.model_dump() for stat in baseline_stats]
    write_json(in_dir / "baseline.json", payload)
    write_jsonl(in_dir / "normalized.jsonl", [s.model_dump() for s in samples])
    config = getattr(args, "config_obj", None)
    if config:
        write_json(in_dir / "config_fingerprint.json", {"fingerprint": config_fingerprint(config)})
    console.print(f"Wrote baseline stats to {in_dir / 'baseline.json'}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    if not _authorize(args, Permission.RUN_PIPELINE):
        console.print("Access denied: run_pipeline required")
        return 3
    in_dir = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"run-{uuid4().hex[:8]}"
    baseline_dir = Path(args.baseline)
    baseline_path = baseline_dir / "baseline.json"
    config = getattr(args, "config_obj", None)
    if config:
        run_fp = config_fingerprint(config)
        fp_path = baseline_dir / "config_fingerprint.json"
        if fp_path.exists():
            baseline_fp = read_json(fp_path).get("fingerprint")
            if baseline_fp and baseline_fp != run_fp:
                logger.warning("Config drift detected between baseline and run.")
    if not baseline_path.exists():
        console.print(f"Missing baseline.json in {baseline_dir}")
        return 1
    samples = _load_samples(in_dir, run_id=run_id)
    _, run_stats = build_stats(samples)
    baseline_records = read_json(baseline_path)
    baseline_map = _baseline_map(baseline_records)
    run_map = {stat.entity_id: stat for stat in run_stats}
    scores = score_links(baseline_map, run_map, run_id=run_id)
    feature_flags = config.feature_flags if config else {}
    actions = recommend_actions(scores, run_id=run_id, feature_flags=feature_flags)
    events = _build_events(scores, run_id=run_id)
    MockActuator().apply(actions)
    _send_alerts_if_configured(args, run_id, events)

    write_json(out_dir / "run_stats.json", [stat.model_dump() for stat in run_stats])
    config = getattr(args, "config_obj", None)
    explainability_enabled = True
    if config:
        explainability_enabled = config.feature_flags.get("explainability", True)
    report_path = write_outputs(out_dir, scores, events, actions, run_id=run_id, explainability=explainability_enabled)
    _render_console_summary(scores)
    console.print(f"Report written to {report_path}")
    console.print(f"Run ID: {run_id}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    if not _authorize(args, Permission.VIEW_REPORTS):
        console.print("Access denied: view_reports required")
        return 3
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


def _send_alerts_if_configured(args: argparse.Namespace, run_id: str, events: List[Event]) -> None:
    config = getattr(args, "config_obj", None)
    if not config:
        return
    alert_events = [e.model_dump() for e in events if e.level in {EventLevel.WARN, EventLevel.ERROR}]
    if not alert_events:
        return
    routes: List[AlertRoute] = []
    if config.alert_webhook_url:
        routes.append(AlertRoute(name="webhook", destination="webhook", url=config.alert_webhook_url))
    if config.alert_slack_webhook_url:
        routes.append(AlertRoute(name="slack", destination="slack", url=config.alert_slack_webhook_url))
    if config.alert_email_to:
        smtp_password = None
        if config.alert_email_smtp_password_secret:
            smtp_password = get_secret(config.alert_email_smtp_password_secret, provider=config.secrets_provider)
        routes.append(
            AlertRoute(
                name="email",
                destination="email",
                url=config.alert_email_to,
                metadata={
                    "provider": config.alert_email_provider,
                    "smtp_host": config.alert_email_smtp_host,
                    "smtp_port": config.alert_email_smtp_port,
                    "smtp_user": config.alert_email_smtp_user,
                    "smtp_password": smtp_password,
                    "smtp_from": config.alert_email_from,
                    "ses_region": config.alert_email_ses_region,
                    "ses_from": config.alert_email_from,
                },
            )
        )
    if not routes:
        return
    try:
        route_alerts(alert_events, routes, run_id=run_id)
    except Exception as exc:
        logger.warning("Alert routing failed: %s", exc)


def _authorize(args: argparse.Namespace, permission: Permission) -> bool:
    token = args.token or None
    config = getattr(args, "config_obj", None)
    token_roles = {}
    if config:
        token_roles.update(load_token_roles_from_config(config.auth_tokens))
    token_roles.update(load_token_roles_from_env())
    principal: Principal | None = None
    if token_roles:
        principal = TokenAuth(token_roles).authenticate(token)
    if not principal:
        principal_name = "local-user"
        role = Role(args.role)
        principal = Principal(name=principal_name, role=role)
    allowed = authorize(principal, permission)
    logger.info(
        "authz principal=%s role=%s permission=%s allowed=%s",
        principal.name,
        principal.role.value,
        permission.value,
        allowed,
    )
    config = getattr(args, "config_obj", None)
    if config and config.audit_enabled and config.audit_log_path:
        append_audit(
            Path(config.audit_log_path),
            {
                "timestamp": utc_now().isoformat(),
                "principal": principal.name,
                "role": principal.role.value,
                "permission": permission.value,
                "allowed": allowed,
            },
            max_bytes=config.audit_max_bytes,
            max_files=config.audit_max_files,
        )
    return allowed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="waveos", description="Wave OS demo CLI")
    parser.add_argument("--config", help="Path to config file (toml/json)")
    parser.add_argument("--role", choices=[role.value for role in Role], default=Role.OPERATOR.value)
    parser.add_argument("--token", help="Auth token for RBAC")
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
    parser = build_parser()
    args = parser.parse_args()
    try:
        config = load_config(Path(args.config) if args.config else None)
    except (ValidationError, ValueError) as exc:
        console.print(f"Invalid configuration: {exc}")
        raise SystemExit(2)
    args.config_obj = config
    level = getattr(logging, config.log_level.upper(), logging.INFO)
    setup_logging(level=level, log_format=config.log_format)
    start_metrics_server(config.metrics_port)
    init_tracer(endpoint=config.otel_endpoint)
    install_signal_handlers(lambda: logger.warning("Graceful shutdown requested"))
    if not getattr(args, "func", None):
        parser.print_help()
        raise SystemExit(1)
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
