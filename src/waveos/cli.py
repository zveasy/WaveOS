"""Wave OS CLI entrypoint."""

from __future__ import annotations

import argparse
import logging
import sys
import time
import webbrowser
from pathlib import Path
from typing import Dict, Iterable, List
from uuid import uuid4

from rich.console import Console
from rich.table import Table

from waveos.actuators import MockActuator
from waveos.collectors import load_records
from waveos.licensing import LicenseError, require_license
from waveos.models import ActionRecommendation, BaselineStats, Event, EventLevel, HealthScore, HealthStatus, RunStats
from waveos.normalize import normalize_records
from waveos.policy import recommend_actions
from waveos.reporting import render_report, write_outputs
from waveos.scoring import build_stats, score_links
from waveos.sim import build_demo_dataset
from waveos.sim.generator import generate_telemetry, _make_links
from waveos.validation import validate_file
from waveos.versioning import current_version
from waveos.bundle import build_manifest, sign_manifest, write_manifest
from waveos.update_agent import install_bundle, rollback_bundle
from waveos.recovery import RecoveryOrchestrator, watchdog_ping
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
    start_proxy,
    ProxyConfig,
    collect_system_metrics,
    supervise,
    drop_privileges,
    apply_resource_limits,
)
from pydantic import ValidationError

console = Console()
logger = get_logger("waveos.cli")


def _find_telemetry_files(in_dir: Path) -> List[Path]:
    candidates = list(in_dir.glob("telemetry.*"))
    if not candidates:
        candidates = list(in_dir.glob("*.jsonl")) + list(in_dir.glob("*.json"))
    return candidates


def _load_samples(in_dir: Path, run_id: str | None = None, config: WaveOSConfig | None = None):
    samples = []
    files = _find_telemetry_files(in_dir)
    if not files:
        return samples
    threads = config.collector_threads if config else 1
    if threads <= 1:
        for path in files:
            if should_shutdown():
                return samples
            records = load_records(path, max_failures=config.breaker_max_failures if config else None, reset_after=config.breaker_reset_after if config else None)
            samples.extend(normalize_records(records, run_id=run_id))
        return samples
    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {
            executor.submit(
                load_records,
                path,
                max_failures=config.breaker_max_failures if config else None,
                reset_after=config.breaker_reset_after if config else None,
            ): path
            for path in files
        }
        for future in as_completed(futures):
            if should_shutdown():
                return samples
            records = future.result()
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


def _build_action_events(actions: Iterable[ActionRecommendation], run_id: str | None = None) -> List[Event]:
    events: List[Event] = []
    for action in actions:
        events.append(
            Event(
                timestamp=utc_now(),
                level=EventLevel.INFO,
                message=f"action={action.action} entity={action.entity_type}:{action.entity_id}",
                entity_type=action.entity_type,
                entity_id=action.entity_id,
                details={"action": action.action, "run_id": run_id, "rationale": action.rationale},
            )
        )
    return events


def _aggregate_run_metrics(stats: Iterable[RunStats]) -> dict:
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for stat in stats:
        for metric, value in stat.metrics.items():
            totals[metric] = totals.get(metric, 0.0) + float(value)
            counts[metric] = counts.get(metric, 0) + 1
    averages = {metric: totals[metric] / max(counts[metric], 1) for metric in totals}
    return averages


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
    if not _authorize(args, Permission.RUN_PIPELINE, action="baseline"):
        console.print("Access denied: run_pipeline required")
        return 3
    in_dir = Path(args.input)
    config = getattr(args, "config_obj", None)
    samples = _load_samples(in_dir, config=config)
    baseline_stats, _ = build_stats(samples)
    payload = [stat.model_dump() for stat in baseline_stats]
    write_json(in_dir / "baseline.json", payload)
    write_jsonl(in_dir / "normalized.jsonl", [s.model_dump() for s in samples])
    if config:
        write_json(in_dir / "config_fingerprint.json", {"fingerprint": config_fingerprint(config)})
    console.print(f"Wrote baseline stats to {in_dir / 'baseline.json'}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    if not _authorize(args, Permission.RUN_PIPELINE, action="run"):
        console.print("Access denied: run_pipeline required")
        return 3
    in_dir = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"run-{uuid4().hex[:8]}"
    started_at = utc_now()
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
                write_json(out_dir / "config_drift.json", {"baseline": baseline_fp, "run": run_fp})
    if not baseline_path.exists():
        console.print(f"Missing baseline.json in {baseline_dir}")
        return 1
    samples = _load_samples(in_dir, run_id=run_id, config=config)
    _, run_stats = build_stats(samples)
    baseline_records = read_json(baseline_path)
    baseline_map = _baseline_map(baseline_records)
    run_map = {stat.entity_id: stat for stat in run_stats}
    scores = score_links(baseline_map, run_map, run_id=run_id)
    feature_flags = config.feature_flags if config else {}
    policy_rules = config.policy_rules if config else []
    actions = recommend_actions(scores, run_id=run_id, feature_flags=feature_flags, policy_rules=policy_rules)
    events = _build_events(scores, run_id=run_id)
    MockActuator().apply(actions)
    events.extend(_build_action_events(actions, run_id=run_id))
    if config and config.enforce_actions:
        enforced_path = out_dir / "enforced_actions.jsonl"
        write_jsonl(enforced_path, [action.model_dump() for action in actions])
        events.append(
            Event(
                timestamp=utc_now(),
                level=EventLevel.INFO,
                message="policy_enforced",
                details={"run_id": run_id, "action_count": len(actions)},
            )
        )
    _send_alerts_if_configured(args, run_id, events)

    write_json(out_dir / "run_stats.json", [stat.model_dump() for stat in run_stats])
    config = getattr(args, "config_obj", None)
    explainability_enabled = True
    if config:
        explainability_enabled = config.feature_flags.get("explainability", True)
    config = getattr(args, "config_obj", None)
    waveos_version = config.waveos_version if config and config.waveos_version else current_version()
    policy_version = config.policy_version if config and config.policy_version else "policy-1"
    bundle_id = config.bundle_id if config else None
    telemetry_metrics = _aggregate_run_metrics(run_stats)
    run_meta = {
        "run_id": run_id,
        "waveos_version": waveos_version,
        "policy_version": policy_version,
        "bundle_id": bundle_id,
        "input_dir": str(in_dir),
        "baseline_dir": str(baseline_dir),
        "output_dir": str(out_dir),
        "config_fingerprint": config_fingerprint(config) if config else None,
        "sample_count": len(samples),
        "score_count": len(scores),
        "event_count": len(events),
        "action_count": len(actions),
        "started_at": started_at.isoformat(),
        "completed_at": utc_now().isoformat(),
        "enforce_actions": config.enforce_actions if config else False,
        "recovery_enabled": config.recovery_enabled if config else False,
        "evidence_pack_enabled": config.evidence_pack_enabled if config else True,
        "system_metrics": collect_system_metrics(),
        "telemetry_metrics": telemetry_metrics,
        "task_health": {"normalize": "ok", "score": "ok", "policy": "ok", "report": "ok"},
        "queue_depths": {"telemetry_ingest": len(samples)},
        "transformations": [
            {"name": "normalize_records", "schema_version": 1},
            {"name": "score_links", "schema_version": 1},
            {"name": "policy_recommendations", "schema_version": 1},
        ],
        "model_versions": {
            "waveos_version": waveos_version,
            "policy_version": policy_version,
        },
    }
    if config and config.recovery_enabled:
        RecoveryOrchestrator(
            restart_command=config.recovery_restart_command,
            degrade_command=config.recovery_degrade_command,
            reboot_command=config.recovery_reboot_command,
        ).handle_events(events, out_dir)
    if config and config.watchdog_enabled and config.watchdog_path:
        watchdog_ping(Path(config.watchdog_path))
    if config and config.idempotent_outputs:
        if (out_dir / "run_meta.json").exists() or (out_dir / "report.html").exists():
            out_dir = out_dir / run_id
            out_dir.mkdir(parents=True, exist_ok=True)
    report_path = write_outputs(
        out_dir,
        scores,
        events,
        actions,
        run_id=run_id,
        explainability=explainability_enabled,
        run_meta=run_meta,
        run_stats=run_stats,
        evidence_pack_enabled=config.evidence_pack_enabled if config else True,
    )
    _render_console_summary(scores)
    console.print(f"Report written to {report_path}")
    console.print(f"Run ID: {run_id}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    if not _authorize(args, Permission.VIEW_REPORTS, action="report"):
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


def cmd_schedule(args: argparse.Namespace) -> int:
    interval = args.every
    runs = args.count
    base_out = Path(args.output)
    for idx in range(runs):
        if should_shutdown():
            return 1
        run_out = base_out / f"run_{idx + 1}"
        run_args = argparse.Namespace(**vars(args))
        run_args.output = str(run_out)
        cmd_run(run_args)
        if idx < runs - 1:
            logger.info("Sleeping for %s seconds before next run", interval)
            time.sleep(interval)
    return 0


def cmd_supervise(args: argparse.Namespace) -> int:
    if not args.command:
        console.print("Missing command to supervise.")
        return 2
    return supervise(args.command, max_restarts=args.max_restarts, backoff_seconds=args.backoff)


def cmd_load_test(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    links = _make_links(args.links)
    start = utc_now()
    generate_telemetry(out_dir, links, samples_per_link=args.samples, baseline=True)
    records = load_records(out_dir / "telemetry.jsonl")
    normalize_records(records)
    duration = (utc_now() - start).total_seconds()
    payload = {
        "links": args.links,
        "samples_per_link": args.samples,
        "total_samples": args.links * args.samples,
        "duration_seconds": duration,
        "samples_per_second": (args.links * args.samples) / max(duration, 1e-6),
    }
    write_json(out_dir / "load_test.json", payload)
    console.print(f"Load test complete: {payload}")
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    import cProfile
    import pstats

    profile_path = Path(args.profile)
    profiler = cProfile.Profile()
    profiler.enable()
    exit_code = cmd_run(args)
    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.strip_dirs().sort_stats("cumtime").dump_stats(str(profile_path))
    console.print(f"Wrote profile stats to {profile_path}")
    return exit_code


def cmd_cleanup(args: argparse.Namespace) -> int:
    base = Path(args.path)
    if not base.exists():
        console.print("Cleanup path does not exist.")
        return 2
    cutoff = utc_now().timestamp() - (args.days * 86400)
    deleted = 0
    for path in base.rglob("*"):
        if path.is_file():
            if path.stat().st_mtime < cutoff:
                path.unlink()
                deleted += 1
    console.print(f"Deleted {deleted} files older than {args.days} days from {base}")
    return 0


def cmd_proxy_serve(args: argparse.Namespace) -> int:
    logger.info("Proxy serve running; press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Proxy serve stopped.")
    return 0


def cmd_metrics_serve(args: argparse.Namespace) -> int:
    logger.info("Metrics serve running; press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Metrics serve stopped.")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    logger.info("Serve running (metrics + proxy); press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Serve stopped.")
    return 0


def cmd_validate_telemetry(args: argparse.Namespace) -> int:
    result = validate_file(Path(args.input), args.profile, Path(args.output) if args.output else None)
    console.print(result)
    return 0


def cmd_bundle_build(args: argparse.Namespace) -> int:
    bundle_dir = Path(args.dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    config = getattr(args, "config_obj", None)
    waveos_version = config.waveos_version if config and config.waveos_version else current_version()
    policy_version = args.policy_version or (config.policy_version if config else "policy-1")
    bundle_id = args.bundle_id or (config.bundle_id if config else None)
    if not bundle_id:
        bundle_id = f"bundle-{uuid4().hex[:8]}"
    identity = None
    if args.device_id or args.app_id:
        identity = {"device_id": args.device_id, "app_id": args.app_id}
    feature_flags = config.feature_flags if config else {}
    manifest = build_manifest(
        bundle_dir,
        waveos_version,
        policy_version,
        bundle_id,
        identity=identity,
        environment=args.environment,
        feature_flags=feature_flags,
    )
    manifest_path = write_manifest(bundle_dir, manifest)
    if args.sign:
        hmac_key = None
        if config and config.bundle_hmac_key_secret:
            hmac_key = get_secret(config.bundle_hmac_key_secret, provider=config.secrets_provider)
        if not hmac_key:
            console.print("Missing bundle HMAC key; set WAVEOS_BUNDLE_HMAC_KEY_SECRET")
            return 2
        sign_manifest(manifest_path, hmac_key)
    console.print(f"Wrote bundle manifest to {manifest_path}")
    return 0


def cmd_bundle_install(args: argparse.Namespace) -> int:
    config = getattr(args, "config_obj", None)
    if not config:
        console.print("Missing configuration")
        return 2
    hmac_key = None
    if config.bundle_hmac_key_secret:
        hmac_key = get_secret(config.bundle_hmac_key_secret, provider=config.secrets_provider)
    install_bundle(
        Path(args.dir),
        Path(config.bundle_active_dir),
        Path(config.bundle_history_dir),
        Path(config.bundle_state_dir),
        hmac_key=hmac_key,
    )
    console.print("Bundle installed")
    return 0


def cmd_bundle_rollback(args: argparse.Namespace) -> int:
    config = getattr(args, "config_obj", None)
    if not config:
        console.print("Missing configuration")
        return 2
    rollback_bundle(
        Path(config.bundle_active_dir),
        Path(config.bundle_history_dir),
        Path(config.bundle_state_dir),
    )
    console.print("Bundle rolled back")
    return 0


def _send_alerts_if_configured(args: argparse.Namespace, run_id: str, events: List[Event]) -> None:
    config = getattr(args, "config_obj", None)
    if not config:
        return
    alert_events = [e.model_dump() for e in events]
    if not alert_events:
        return
    routes: List[AlertRoute] = []
    if config.alert_webhook_url:
        min_level = config.alert_webhook_min_level or config.alert_min_level
        routes.append(AlertRoute(name="webhook", destination="webhook", url=config.alert_webhook_url, min_level=min_level))
    if config.alert_slack_webhook_url:
        min_level = config.alert_slack_min_level or config.alert_min_level
        routes.append(AlertRoute(name="slack", destination="slack", url=config.alert_slack_webhook_url, min_level=min_level))
    if config.alert_email_to:
        smtp_password = None
        if config.alert_email_smtp_password_secret:
            smtp_password = get_secret(config.alert_email_smtp_password_secret, provider=config.secrets_provider)
        routes.append(
            AlertRoute(
                name="email",
                destination="email",
                url=config.alert_email_to,
                min_level=config.alert_email_min_level or config.alert_min_level,
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


def _authorize(args: argparse.Namespace, permission: Permission, action: str | None = None) -> bool:
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
                "action": action or "access_attempt",
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

    schedule_parser = sub.add_parser("schedule", help="Run pipeline on a schedule")
    schedule_parser.add_argument("--in", required=True, dest="input")
    schedule_parser.add_argument("--baseline", required=True)
    schedule_parser.add_argument("--out", required=True, dest="output")
    schedule_parser.add_argument("--every", type=int, required=True, help="Seconds between runs")
    schedule_parser.add_argument("--count", type=int, default=1, help="Number of runs to execute")
    schedule_parser.set_defaults(func=cmd_schedule)

    supervise_parser = sub.add_parser("supervise", help="Supervise a child process")
    supervise_parser.add_argument("command", nargs=argparse.REMAINDER)
    supervise_parser.add_argument("--max-restarts", type=int, default=3)
    supervise_parser.add_argument("--backoff", type=float, default=1.0)
    supervise_parser.set_defaults(func=cmd_supervise)

    load_parser = sub.add_parser("load-test", help="Run a load test on telemetry normalization")
    load_parser.add_argument("--out", required=True)
    load_parser.add_argument("--links", type=int, default=100)
    load_parser.add_argument("--samples", type=int, default=100)
    load_parser.set_defaults(func=cmd_load_test)

    profile_parser = sub.add_parser("profile", help="Profile a run")
    profile_parser.add_argument("--in", required=True, dest="input")
    profile_parser.add_argument("--baseline", required=True)
    profile_parser.add_argument("--out", required=True, dest="output")
    profile_parser.add_argument("--profile", required=True, help="Path to cProfile output")
    profile_parser.set_defaults(func=cmd_profile)

    cleanup_parser = sub.add_parser("cleanup", help="Purge old outputs and logs")
    cleanup_parser.add_argument("--path", required=True)
    cleanup_parser.add_argument("--days", type=int, required=True)
    cleanup_parser.set_defaults(func=cmd_cleanup)

    proxy_parser = sub.add_parser("proxy-serve", help="Run proxy server only")
    proxy_parser.set_defaults(func=cmd_proxy_serve)

    metrics_parser = sub.add_parser("metrics-serve", help="Run metrics server only")
    metrics_parser.set_defaults(func=cmd_metrics_serve)

    serve_parser = sub.add_parser("serve", help="Run metrics + proxy servers")
    serve_parser.set_defaults(func=cmd_serve)

    validate_parser = sub.add_parser("validate-telemetry", help="Validate telemetry against a profile")
    validate_parser.add_argument("--in", required=True, dest="input")
    validate_parser.add_argument("--profile", required=True, choices=["microgrid", "ev_charger"])
    validate_parser.add_argument("--out", dest="output")
    validate_parser.set_defaults(func=cmd_validate_telemetry)

    report_parser = sub.add_parser("report", help="Render HTML report")
    report_parser.add_argument("--in", required=True, dest="input")
    report_parser.add_argument("--open", action="store_true", default=False)
    report_parser.set_defaults(func=cmd_report)

    bundle_parser = sub.add_parser("bundle", help="Bundle management")
    bundle_sub = bundle_parser.add_subparsers(dest="bundle_command")
    bundle_build = bundle_sub.add_parser("build", help="Build bundle manifest")
    bundle_build.add_argument("--dir", required=True)
    bundle_build.add_argument("--policy-version")
    bundle_build.add_argument("--bundle-id")
    bundle_build.add_argument("--device-id")
    bundle_build.add_argument("--app-id")
    bundle_build.add_argument("--environment")
    bundle_build.add_argument("--sign", action="store_true", default=False)
    bundle_build.set_defaults(func=cmd_bundle_build)
    bundle_install = bundle_sub.add_parser("install", help="Install bundle")
    bundle_install.add_argument("--dir", required=True)
    bundle_install.set_defaults(func=cmd_bundle_install)
    bundle_rollback = bundle_sub.add_parser("rollback", help="Rollback bundle")
    bundle_rollback.set_defaults(func=cmd_bundle_rollback)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        require_license()
    except LicenseError as exc:
        console.print(str(exc))
        raise SystemExit(3)
    try:
        config = load_config(Path(args.config) if args.config else None)
    except (ValidationError, ValueError) as exc:
        console.print(f"Invalid configuration: {exc}")
        raise SystemExit(2)
    args.config_obj = config
    level = getattr(logging, config.log_level.upper(), logging.INFO)
    setup_logging(level=level, log_format=config.log_format, spool_path=Path(config.log_spool_path) if config.log_spool_path else None)
    drop_privileges(config.drop_privileges_user, config.drop_privileges_group)
    apply_resource_limits(config.max_memory_mb, config.max_cpu_seconds)
    start_metrics_server(config.metrics_port)
    init_tracer(endpoint=config.otel_endpoint)
    if config.proxy_enabled and config.proxy_mode:
        start_proxy(
            ProxyConfig(
                mode=config.proxy_mode,
                listen_host=config.proxy_listen_host,
                listen_port=config.proxy_listen_port,
                target_host=config.proxy_target_host,
                target_port=config.proxy_target_port,
            )
        )
    install_signal_handlers(lambda: logger.warning("Graceful shutdown requested"))
    if not getattr(args, "func", None):
        parser.print_help()
        raise SystemExit(1)
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
