"""Wave OS CLI entrypoint."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
from uuid import uuid4

from rich.console import Console
from rich.table import Table

from waveos.actuators import MockActuator, SdnThermalActuator
from waveos.actuators.reliability import ActuationReliabilityLayer
from waveos.actuators.safety import SafetyInterlock, safe_actuator
from waveos.actuators.adapter_actuator import AdapterBasedActuator
from waveos.actuators.adapters import SdnRestAdapter
from waveos.actuators.adapters.modbus_inverter import ModbusInverterAdapter
from waveos.collectors import load_records, load_records_from_mqtt, load_records_from_url
from waveos.licensing import LicenseError, require_license
from waveos.models import ActionRecommendation, BaselineStats, Event, EventLevel, HealthScore, HealthStatus, RunStats
from waveos.normalize import normalize_records
from waveos.policy import recommend_actions
from waveos.reporting import render_report, write_outputs
from waveos.persistence import build_incident_from_run, get_store, persist_incident_if_enabled, persist_run_if_enabled
from waveos.action_lifecycle import propose_actions, record_acked, record_dispatched, record_verified
from waveos.action_signing import sign_action_batch, verify_action_batch, verified_by_agent_record
from waveos.scoring import build_stats, score_links
from waveos.sim import build_demo_dataset
from waveos.sim.generator import generate_telemetry, _make_links
from waveos.validation import validate_file
from waveos.versioning import current_version
from waveos.bundle import build_manifest, encrypt_bundle_artifacts, sign_manifest, write_manifest
from waveos.plugins.registry import list_plugins, get_registry, PluginKind
from waveos.device_api import get_device_registry, get_driver_instance, DeviceCapability
from waveos.update_agent import install_bundle, install_bundle_from_cache, promote_canary_bundle, rollback_bundle
from waveos.recovery import RecoveryOrchestrator, watchdog_ping
from waveos.heartbeat import emit_heartbeat
from waveos.coordinator import run_coordinator_server
from waveos.utils import (
    WaveOSConfig,
    get_logger,
    start_health_server,
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
    set_strict_secrets,
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
    if config and config.require_ingestion_token:
        from waveos.collectors.auth import IngestionAuthError, verify_ingestion_token
        try:
            verify_ingestion_token(
                Path(config.ingestion_token_path) if config.ingestion_token_path else None,
            )
        except IngestionAuthError as e:
            logger.error("Ingestion auth failed: %s", e)
            raise
    files = _find_telemetry_files(in_dir)
    if not files:
        return samples
    threads = config.collector_threads if config else 1
    if threads <= 1:
        for path in files:
            if should_shutdown():
                return samples
            records = load_records(path, max_failures=config.breaker_max_failures if config else None, reset_after=config.breaker_reset_after if config else None)
            samples.extend(normalize_records(records, run_id=run_id, max_records=config.max_telemetry_records if config else None))
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
            samples.extend(normalize_records(records, run_id=run_id, max_records=config.max_telemetry_records if config else None))
    return samples


def _get_actuator(
    config,
    actuator_dir: Path,
    run_id: str,
    state_lookup: Optional[Callable[[str], dict]] = None,
):
    """Build actuator chain: base (SdnThermal or AdapterBased or custom) -> optional Safety -> optional Reliability.
    state_lookup: optional (entity_id) -> dict of metrics (e.g. temperature_c, battery_soc_pct, current_a) for safety limits."""
    # 1) Base actuator
    if config and getattr(config, "actuator_class", None):
        spec = config.actuator_class.strip()
        if ":" in spec:
            mod_name, cls_name = spec.rsplit(":", 1)
            import importlib
            mod = importlib.import_module(mod_name)
            cls = getattr(mod, cls_name)
            try:
                base = cls(output_dir=actuator_dir, run_id=run_id)
            except TypeError:
                base = cls()
        else:
            logger.warning("actuator_class must be 'module:ClassName'; using default")
            base = _default_base_actuator(config, actuator_dir, run_id)
    else:
        base = _default_base_actuator(config, actuator_dir, run_id)

    # 2) Optional safety interlock (with state from run/telemetry when provided)
    interlock = _build_safety_interlock(config, state_lookup=state_lookup)
    if interlock is not None:
        base = safe_actuator(interlock, base)

    # 3) Optional reliability layer (when enforce_actions)
    if config and getattr(config, "enforce_actions", False):
        base = _wrap_reliability(config, base, actuator_dir, run_id)

    return base


def _default_base_actuator(config, actuator_dir: Path, run_id: str):
    """Default base: AdapterBasedActuator when actuation_use_adapters else SdnThermalActuator.
    When adapters enabled: SDN REST + Modbus inverter (if host set) for vendor-neutral real device control.
    """
    if config and getattr(config, "actuation_use_adapters", False):
        adapters: List[Any] = [
            SdnRestAdapter(
                mtls_cert_path=getattr(config, "actuator_mtls_cert_path", None),
                mtls_key_path=getattr(config, "actuator_mtls_key_path", None),
                mtls_ca_path=getattr(config, "actuator_mtls_ca_path", None),
            )
        ]
        if os.getenv("WAVEOS_ACTUATOR_MODBUS_HOST", "").strip():
            adapters.append(ModbusInverterAdapter())
        fallback = SdnThermalActuator(output_dir=actuator_dir, run_id=run_id)
        timeout = getattr(config, "actuation_timeout_sec", 10.0) or 10.0
        return AdapterBasedActuator(
            adapters=adapters,
            fallback=fallback,
            output_dir=actuator_dir,
            run_id=run_id,
            timeout_seconds=float(timeout),
        )
    return SdnThermalActuator(output_dir=actuator_dir, run_id=run_id)


def _build_safety_interlock(
    config,
    state_lookup: Optional[Callable[[str], dict]] = None,
) -> Optional[SafetyInterlock]:
    """Build SafetyInterlock from config if any safety setting is set.
    state_lookup: optional (entity_id) -> dict with temperature_c, battery_soc_pct/soc_pct, current_a for hard limits."""
    if not config:
        return None
    max_temp = getattr(config, "actuation_safety_max_temp_c", None)
    min_soc = getattr(config, "actuation_safety_min_soc_pct", None)
    max_current = getattr(config, "actuation_safety_max_current_a", None)
    approval_types = getattr(config, "actuation_approval_required_types", None) or []
    approval_path = getattr(config, "actuation_approval_path", None)
    cooldown = float(getattr(config, "actuation_cooldown_seconds", 0) or 0)
    max_per_min = getattr(config, "actuation_max_actions_per_minute", None)
    if max_temp is None and min_soc is None and max_current is None and not approval_types and cooldown <= 0 and max_per_min is None:
        return None
    approval_path_resolved = Path(approval_path).expanduser() if approval_path else None
    return SafetyInterlock(
        max_temp_c=max_temp,
        min_soc_pct=min_soc,
        max_current_a=max_current,
        approval_required_action_types=set(approval_types),
        approval_path=approval_path_resolved,
        max_actions_per_minute=max_per_min,
        cooldown_seconds=cooldown,
        state_lookup=state_lookup,
    )


def _wrap_reliability(config, inner, actuator_dir: Path, run_id: str):
    """Wrap actuator with ActuationReliabilityLayer using config."""
    timeout = float(getattr(config, "actuation_timeout_sec", 10) or 10)
    retry = int(getattr(config, "actuation_retry_count", 2) or 2)
    ttl = float(getattr(config, "actuation_idempotency_ttl_sec", 300) or 300)
    outcomes_path = getattr(config, "actuation_outcomes_path", None)
    path = Path(outcomes_path).expanduser() if outcomes_path else (actuator_dir / "action_outcomes.jsonl")
    return ActuationReliabilityLayer(
        inner=inner,
        run_id=run_id,
        timeout_seconds=timeout,
        retry_count=retry,
        idempotency_ttl_seconds=ttl,
        outcomes_path=path,
    )


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
    baseline_dir = Path(args.baseline)
    input_is_url = str(args.input).startswith("http://") or str(args.input).startswith("https://")
    if not input_is_url and not in_dir.is_dir():
        console.print(f"Input directory does not exist: {in_dir}")
        return 1
    if not baseline_dir.is_dir():
        console.print(f"Baseline directory does not exist: {baseline_dir}")
        return 1
    baseline_path = baseline_dir / "baseline.json"
    if not baseline_path.exists():
        console.print(f"Missing baseline.json in {baseline_dir}. Run 'waveos baseline --in <dir>' first.")
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"run-{uuid4().hex[:8]}"
    started_at = utc_now()
    config = getattr(args, "config_obj", None)
    if config:
        run_fp = config_fingerprint(config)
        fp_path = baseline_dir / "config_fingerprint.json"
        if fp_path.exists():
            baseline_fp = read_json(fp_path).get("fingerprint")
            if baseline_fp and baseline_fp != run_fp:
                logger.warning("Config drift detected between baseline and run.")
                write_json(out_dir / "config_drift.json", {"baseline": baseline_fp, "run": run_fp})
    if input_is_url:
        records = load_records_from_url(
            args.input,
            timeout=getattr(config, "ingestion_http_timeout", 10.0) if config else 10.0,
        )
        samples = list(normalize_records(records, run_id=run_id, max_records=config.max_telemetry_records if config else None))
    else:
        samples = _load_samples(in_dir, run_id=run_id, config=config)
    _, run_stats = build_stats(samples)
    baseline_records = read_json(baseline_path)
    baseline_map = _baseline_map(baseline_records)
    run_map = {stat.entity_id: stat for stat in run_stats}
    scores = score_links(baseline_map, run_map, run_id=run_id)
    feature_flags = config.feature_flags if config else {}
    policy_rules = config.policy_rules if config else []
    # Optional: use coordinator-signed action batch (verify before use)
    signed_batch_path = os.getenv("WAVEOS_SIGNED_ACTIONS_PATH", "").strip()
    signed_batch_json = os.getenv("WAVEOS_SIGNED_ACTIONS_JSON", "").strip()
    actions_from_signed: Optional[List[ActionRecommendation]] = None
    action_signing_evidence_for_report: Optional[Dict[str, Any]] = None
    if signed_batch_path or signed_batch_json:
        try:
            if signed_batch_path and Path(signed_batch_path).expanduser().exists():
                raw = read_json(Path(signed_batch_path).expanduser())
            else:
                import json as _json
                raw = _json.loads(signed_batch_json) if signed_batch_json else None
            if raw:
                acts, err = verify_action_batch(raw, max_age_sec=300)
                if err:
                    action_signing_evidence_for_report = verified_by_agent_record(
                        raw.get("nonce", "unknown"), os.getenv("WAVEOS_AGENT_NODE_ID", "local"), utc_now().isoformat(), raw.get("nonce", ""), 0, False
                    )
                    action_signing_evidence_for_report["error"] = err
                elif acts:
                    actions_from_signed = [ActionRecommendation.model_validate(a) for a in acts if isinstance(a, dict)]
                    action_signing_evidence_for_report = verified_by_agent_record(
                        raw.get("nonce", "unknown"), os.getenv("WAVEOS_AGENT_NODE_ID", "local"), utc_now().isoformat(), raw.get("nonce", ""), len(actions_from_signed), True
                    )
        except Exception as e:
            logger.warning("Signed action batch load/verify failed: %s", e)
    actions = actions_from_signed if actions_from_signed is not None else recommend_actions(scores, run_id=run_id, feature_flags=feature_flags, policy_rules=policy_rules)
    events = _build_events(scores, run_id=run_id)
    if action_signing_evidence_for_report is not None and not action_signing_evidence_for_report.get("verification_success"):
        events.append(Event(timestamp=utc_now(), level=EventLevel.ERROR, message="action_signing_verify_failed", details={"error": "see action_signing_evidence"}))
    action_outcomes_for_report: List[Dict[str, Any]] = []
    # Escalation lock: if enforcement is locked, do not apply actions (advisory only)
    enforcement_locked = False
    if config:
        locked_path = getattr(config, "enforcement_locked_path", None)
        if locked_path and Path(locked_path).expanduser().exists():
            try:
                enforcement_locked = Path(locked_path).expanduser().read_text(encoding="utf-8").strip().lower() in ("1", "locked", "true", "yes")
            except Exception:
                pass
        if not enforcement_locked and getattr(config, "enforcement_require_approval_path", None):
            approval_path = Path(config.enforcement_require_approval_path).expanduser()
            if approval_path.exists() and approval_path.read_text(encoding="utf-8").strip().lower() not in ("1", "approved", "true", "yes"):
                enforcement_locked = True
    if config and config.enforce_actions and not enforcement_locked:
        actuator_dir = (Path(config.actuator_output_dir).expanduser() if config.actuator_output_dir else out_dir / "actuator")
        state_lookup = (lambda eid: run_map[eid].metrics if eid in run_map else {}) if run_map else None
        real_actuator = _get_actuator(config, actuator_dir, run_id, state_lookup=state_lookup)
        actuator_name = getattr(real_actuator, "name", real_actuator.__class__.__name__)
        # Action transaction model: propose (idempotency + cooldown), dispatch, ack, outcomes
        db_path = Path(config.persistence_db_path).expanduser().resolve() if (getattr(config, "persistence_enabled", False) and getattr(config, "persistence_db_path", None)) else None
        store = get_store(db_path) if db_path else None
        idempotency_ttl = float(getattr(config, "actuation_idempotency_ttl_sec", 300) or 300)
        cooldown_sec = float(getattr(config, "actuation_cooldown_seconds", 0) or 0)
        to_dispatch, skipped = propose_actions(actions, run_id, store=store, idempotency_ttl_sec=idempotency_ttl, cooldown_sec=cooldown_sec)
        if skipped:
            logger.info("Action lifecycle: skipped %s actions (idempotency/cooldown)", len(skipped))
        actions_to_apply = [a for a, _ in to_dispatch]
        for _action, txn in to_dispatch:
            record_dispatched(txn["action_id"], store, run_id=run_id)
        real_actuator.apply_safe(actions_to_apply)
        # Record ACK from adapter results when available (real device adapters); closed-loop outcome
        results = getattr(real_actuator, "get_last_results", lambda: [])()
        outcome_rows = []
        for i, (_action, txn) in enumerate(to_dispatch):
            if i < len(results):
                r = results[i]
                record_acked(txn["action_id"], store, ack_message=getattr(r, "message", None), actual_state=getattr(r, "actual_state", None))
                outcome_str = getattr(r.outcome, "value", str(r.outcome)) if hasattr(r, "outcome") else "unknown"
                # Map adapter outcome to verification outcome (effective / no_effect / harmful / unknown)
                if outcome_str in ("succeeded", "SUCCEEDED"):
                    verification_outcome = "effective"
                elif outcome_str in ("no_effect", "NO_EFFECT", "degraded", "DEGRADED"):
                    verification_outcome = "no_effect"
                else:
                    verification_outcome = "unknown"
                record_verified(txn["action_id"], store, outcome=verification_outcome, verification_summary=outcome_str)
                outcome_rows.append({"action_id": txn["action_id"], "outcome": verification_outcome, "state": "VERIFIED", "run_id": run_id, "what_happened_after": outcome_str})
            else:
                outcome_rows.append({"action_id": txn["action_id"], "outcome": "unknown", "state": "DISPATCHED", "run_id": run_id})
        action_outcomes_for_report = outcome_rows
        actuator_dir.mkdir(parents=True, exist_ok=True)
        write_jsonl(actuator_dir / "action_outcomes.jsonl", outcome_rows)
        enforced_path = out_dir / "enforced_actions.jsonl"
        write_jsonl(enforced_path, [a.model_dump() for a in actions_to_apply])
        events.append(
            Event(
                timestamp=utc_now(),
                level=EventLevel.INFO,
                message="policy_enforced",
                details={"run_id": run_id, "action_count": len(actions_to_apply), "skipped": len(skipped), "actuator": actuator_name, "actuator_dir": str(actuator_dir)},
            )
        )
    elif config and config.enforce_actions and enforcement_locked:
        logger.warning("Enforcement locked (escalation); actions not applied")
        events.append(
            Event(
                timestamp=utc_now(),
                level=EventLevel.WARN,
                message="enforcement_locked",
                details={"run_id": run_id, "reason": "escalation lock or approval required"},
            )
        )
        MockActuator().apply(actions)
    else:
        MockActuator().apply(actions)
    events.extend(_build_action_events(actions, run_id=run_id))
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
    # Post-action verification: attach action outcome counts from reliability layer (closed-loop Phase 1)
    if config and config.enforce_actions:
        _actuator_dir = (Path(config.actuator_output_dir).expanduser() if config.actuator_output_dir else out_dir / "actuator")
        _outcomes_path = _actuator_dir / "action_outcomes.jsonl"
        if _outcomes_path.exists():
            try:
                _outcome_rows = list(read_jsonl(_outcomes_path))
                _counts: Dict[str, int] = {}
                for _r in _outcome_rows:
                    _o = _r.get("outcome", "unknown")
                    _counts[_o] = _counts.get(_o, 0) + 1
                run_meta["action_outcomes"] = _counts
                run_meta["action_outcomes_path"] = str(_outcomes_path)
            except Exception as _e:
                logger.debug("Could not read action outcomes: %s", _e)
    if config and config.recovery_enabled:
        approval_path = Path(config.recovery_approval_path) if config.recovery_approval_path else None
        env_approved = (os.environ.get("WAVEOS_RECOVERY_APPROVED", "").lower() in {"1", "true", "yes", "on"})
        RecoveryOrchestrator(
            restart_command=config.recovery_restart_command,
            degrade_command=config.recovery_degrade_command,
            reboot_command=config.recovery_reboot_command,
            require_approval=config.recovery_require_approval,
            approval_path=approval_path,
            env_approved=env_approved,
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
        encrypt_artifacts=config.encrypt_artifacts if config else False,
        action_outcomes=action_outcomes_for_report,
        action_signing_evidence=action_signing_evidence_for_report,
    )
    if config and getattr(config, "persistence_enabled", False) and getattr(config, "persistence_db_path", None):
        db_path = Path(config.persistence_db_path).expanduser().resolve()
        persist_run_if_enabled(
            db_path,
            run_id=run_id,
            output_dir=str(out_dir),
            run_meta=run_meta,
            scores=[s.model_dump() for s in scores],
            events=[e.model_dump() for e in events],
            actions=[a.model_dump() for a in actions],
        )
        incident = build_incident_from_run(
            run_id=run_id,
            run_meta=run_meta,
            scores=[s.model_dump() for s in scores],
            actions=[a.model_dump() for a in actions],
            action_outcomes=run_meta.get("action_outcomes"),
        )
        if incident:
            persist_incident_if_enabled(db_path, incident)
    _render_console_summary(scores)
    console.print(f"Report written to {report_path}")
    console.print(f"Run ID: {run_id}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    if not _authorize(args, Permission.VIEW_REPORTS, action="report"):
        console.print("Access denied: view_reports required")
        return 3
    out_dir = Path(args.input)
    if not out_dir.is_dir():
        console.print(f"Output directory does not exist: {out_dir}")
        return 1
    health_path = out_dir / "health_summary.json"
    events_path = out_dir / "events.jsonl"
    actions_path = out_dir / "actions.json"
    missing = [p for p in (health_path, events_path, actions_path) if not p.is_file()]
    if missing:
        console.print("Missing required files for report:", ", ".join(str(p) for p in missing))
        console.print("Run 'waveos run' first to generate outputs.")
        return 1
    health_payload = read_json(health_path)
    events_payload = read_jsonl(events_path)
    actions_payload = read_json(actions_path)
    action_outcomes_payload: List[Dict[str, Any]] = []
    outcomes_path = out_dir / "actuator" / "action_outcomes.jsonl"
    if outcomes_path.is_file():
        try:
            action_outcomes_payload = list(read_jsonl(outcomes_path))
        except Exception:
            pass
    report_path = render_report(out_dir, health_payload, events_payload, actions_payload, action_outcomes=action_outcomes_payload)
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


def cmd_ingest_mqtt(args: argparse.Namespace) -> int:
    """Pull telemetry from MQTT topic and write to file (Data plane Phase 1)."""
    if load_records_from_mqtt is None:
        console.print("MQTT connector requires paho-mqtt: pip install paho-mqtt")
        return 1
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        records = load_records_from_mqtt(
            args.broker,
            args.topic,
            max_messages=getattr(args, "max_messages", 1000),
            timeout_sec=getattr(args, "timeout", 30.0),
            port=getattr(args, "port", 1883),
        )
    except Exception as e:
        console.print(f"MQTT ingest failed: {e}")
        return 1
    write_jsonl(out_path, records)
    console.print(f"Wrote {len(records)} records to {out_path}")
    return 0


def cmd_soak_test(args: argparse.Namespace) -> int:
    """Run pipeline repeatedly to validate stability (SRE Phase 3: soak tests)."""
    n_runs = getattr(args, "runs", 5)
    interval = getattr(args, "every", 10)
    base_out = Path(args.output)
    min_success = getattr(args, "min_success", None)  # require at least this many successes
    success = 0
    for idx in range(n_runs):
        if should_shutdown():
            return 1
        run_out = base_out / f"soak_run_{idx + 1}"
        run_args = argparse.Namespace(**vars(args))
        run_args.output = str(run_out)
        rc = cmd_run(run_args)
        if rc == 0:
            success += 1
        if idx < n_runs - 1:
            time.sleep(interval)
    console.print(f"Soak test: {success}/{n_runs} runs succeeded.")
    if min_success is not None and success < min_success:
        console.print(f"[red]Required at least {min_success} successes.[/red]")
        return 1
    return 0 if success == n_runs else 1


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


def _cleanup_allowed_base() -> Path:
    """Base path under which cleanup is allowed (SSRF/path traversal protection)."""
    env_base = os.environ.get("WAVEOS_CLEANUP_ALLOWED_BASE", "").strip()
    if env_base:
        return Path(env_base).resolve()
    return Path.cwd().resolve()


def cmd_cleanup(args: argparse.Namespace) -> int:
    base = Path(args.path).resolve()
    allowed = _cleanup_allowed_base()
    try:
        base.relative_to(allowed)
    except ValueError:
        console.print(f"Cleanup path must be under allowed base {allowed}. Set WAVEOS_CLEANUP_ALLOWED_BASE to override.")
        return 2
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


def cmd_list_plugins(args: argparse.Namespace) -> int:
    """List registered plugins (V2)."""
    from waveos.plugins.registry import discover_entry_points
    discover_entry_points()
    kind_filter = getattr(args, "kind", None)
    kind = PluginKind(kind_filter) if kind_filter else None
    plugins = list_plugins(kind=kind)
    if not plugins:
        console.print("No plugins registered.")
        return 0
    for m in plugins:
        console.print(f"  {m.name}  kind={m.kind.value}  version={m.version}  {m.description or ''}")
    return 0


def cmd_list_devices(args: argparse.Namespace) -> int:
    """List device drivers and optionally devices (V2)."""
    reg = get_device_registry()
    if not reg:
        console.print("No device drivers registered.")
        return 0
    for key in sorted(reg.keys()):
        console.print(f"  {key}")
        if getattr(args, "devices", False):
            try:
                cap, vendor = key.split(":", 1)
                cap_enum = DeviceCapability(cap)
                driver = get_driver_instance(cap_enum, vendor)
                if driver:
                    for dev_id in driver.list_devices():
                        console.print(f"    -> {dev_id}")
            except (ValueError, KeyError) as exc:
                logger.debug("list_devices failed for %s: %s", key, type(exc).__name__)
    return 0


def cmd_list_nodes(args: argparse.Namespace) -> int:
    """List registered orchestration nodes (V3). Optional --sites or --canary-sites filter (Fleet Phase 2)."""
    from waveos.orchestration import get_node_registry, get_nodes_in_sites, load_nodes_from_file
    nodes_path = getattr(args, "file", None)
    if nodes_path:
        load_nodes_from_file(Path(nodes_path))
    else:
        default = Path("out/nodes.json")
        if default.is_file():
            load_nodes_from_file(default)
    reg = get_node_registry()
    if not reg:
        console.print("No nodes registered.")
        return 0
    config = getattr(args, "config_obj", None)
    canary_sites = getattr(args, "canary_sites", None) or (config and getattr(config, "bundle_canary_sites", None))
    sites_filter = getattr(args, "sites", None)
    if canary_sites:
        site_list = [s.strip() for s in (canary_sites.split(",") if isinstance(canary_sites, str) else canary_sites) if s.strip()]
        nodes = get_nodes_in_sites(site_list)
        if not nodes:
            console.print(f"No nodes in canary sites: {site_list}")
            return 0
        for rec in sorted(nodes, key=lambda r: r.node_id):
            role_str = rec.role.value if hasattr(rec.role, "value") else str(rec.role)
            site_str = f"  site={rec.site_id}" if rec.site_id else ""
            console.print(f"  {rec.node_id}  role={role_str}{site_str}")
        return 0
    if sites_filter:
        site_list = [s.strip() for s in (sites_filter.split(",") if isinstance(sites_filter, str) else sites_filter) if s.strip()]
        nodes = get_nodes_in_sites(site_list)
        for rec in sorted(nodes, key=lambda r: r.node_id):
            role_str = rec.role.value if hasattr(rec.role, "value") else str(rec.role)
            site_str = f"  site={rec.site_id}" if rec.site_id else ""
            console.print(f"  {rec.node_id}  role={role_str}{site_str}")
        return 0
    for nid, rec in sorted(reg.items()):
        role = getattr(rec, "role", None)
        role_str = role.value if hasattr(role, "value") else str(rec)
        site_str = f"  site={rec.site_id}" if getattr(rec, "site_id", None) else ""
        console.print(f"  {nid}  role={role_str}{site_str}")
    return 0


def cmd_fleet_status(args: argparse.Namespace) -> int:
    """Fleet status: nodes + optional health from heartbeats (Area 3 Phase 1)."""
    from waveos.node_health import healthy_nodes
    from waveos.orchestration import get_node_registry, load_nodes_from_file
    config = getattr(args, "config_obj", None)
    nodes_path = getattr(args, "file", None) or (Path(config.state_registry_path).parent / "nodes.json" if config and config.state_registry_path else None) or Path("out/nodes.json")
    if isinstance(nodes_path, str):
        nodes_path = Path(nodes_path)
    if nodes_path.is_file():
        load_nodes_from_file(nodes_path)
    reg = get_node_registry()
    heartbeat_path = Path(config.watchdog_path or "out/watchdog.txt").parent / "heartbeats.jsonl" if config else None
    if not heartbeat_path or not heartbeat_path.is_file():
        heartbeat_path = Path("out/heartbeats.jsonl")
    health: Dict[str, bool] = {}
    if heartbeat_path.is_file():
        health = healthy_nodes(heartbeat_path, max_age_seconds=float(getattr(args, "max_age_seconds", 120) or 120))
    console.print("[bold]Fleet status[/bold]")
    if not reg:
        console.print("  No nodes in registry. Use list-nodes --file <nodes.json> to load.")
        return 0
    for nid, rec in sorted(reg.items()):
        role = getattr(rec, "role", None)
        role_str = role.value if hasattr(role, "value") else "?"
        ok = health.get(nid, None)
        status = "ok" if ok is True else ("stale" if ok is False else "—")
        site_str = f"  site={rec.site_id}" if getattr(rec, "site_id", None) else ""
        console.print(f"  {nid}  role={role_str}  health={status}{site_str}")
    return 0


def cmd_runbook_list(args: argparse.Namespace) -> int:
    """List available runbooks (SRE Phase 2)."""
    from waveos.runbooks import list_runbooks
    for rb in list_runbooks():
        console.print(f"  [bold]{rb.id}[/bold]  {rb.title}")
        desc = (rb.description[:60] + "...") if len(rb.description) > 60 else rb.description
        console.print(f"    trigger={rb.trigger}  {desc}")
    return 0


def cmd_runbook_run(args: argparse.Namespace) -> int:
    """Run a runbook by id (steps are informational)."""
    from waveos.runbooks import get_runbook, run_runbook
    runbook_id = getattr(args, "runbook_id", None)
    if not runbook_id:
        console.print("Usage: waveos runbook run <runbook_id>")
        return 1
    rb = get_runbook(runbook_id)
    if not rb:
        console.print(f"Runbook not found: {runbook_id}")
        return 1
    result = run_runbook(runbook_id)
    if not result.get("ok"):
        console.print(result.get("error", "Unknown error"))
        return 1
    console.print(f"[bold]{result['title']}[/bold]")
    for s in result.get("steps", []):
        console.print(f"  {s['step']}. {s['title']}")
        if s.get("description"):
            console.print(f"     {s['description']}")
        if s.get("command"):
            console.print(f"     command: {s['command']}")
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    """One-command install: create out dirs and optional config example (Productization Phase 1)."""
    prefix = Path(getattr(args, "prefix", ".")).resolve()
    write_config_example = getattr(args, "config_example", False)
    (prefix / "out").mkdir(parents=True, exist_ok=True)
    (prefix / "out" / "bundles" / "active").mkdir(parents=True, exist_ok=True)
    (prefix / "out" / "bundles" / "history").mkdir(parents=True, exist_ok=True)
    (prefix / "out" / "bundles" / "state").mkdir(parents=True, exist_ok=True)
    (prefix / "out" / "actuator").mkdir(parents=True, exist_ok=True)
    (prefix / "out" / "nodes").mkdir(parents=True, exist_ok=True)
    for name in ("audit.jsonl", "watchdog.txt"):
        p = prefix / "out" / name
        if not p.exists():
            p.touch()
    if write_config_example:
        config_path = prefix / "out" / "config.toml.example"
        if not config_path.exists():
            config_path.write_text(
                "# WaveOS config example. Copy to config.toml and customize.\n"
                "# See docs and WAVEOS_* env vars for all options.\n\n"
                "schema_version = 1\nlog_level = \"INFO\"\nlog_format = \"json\"\n\n"
                "persistence_enabled = false\npersistence_db_path = \"out/waveos.db\"\n\n"
                "enforce_actions = false\nactuation_use_adapters = false\n",
                encoding="utf-8",
            )
            console.print(f"Wrote {config_path}")
    console.print(f"Install complete (prefix={prefix}). Next: pip install -e . ; waveos baseline --in <dir> --out out")
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    """Ensure persistence DB schema is current (Productization Phase 1)."""
    config = getattr(args, "config_obj", None)
    db_path = getattr(args, "db", None)
    if not db_path and config and getattr(config, "persistence_db_path", None):
        db_path = config.persistence_db_path
    if not db_path:
        console.print("No DB path. Use --db <path> or set persistence_db_path in config.")
        return 1
    path = Path(db_path)
    from waveos.persistence.store import get_store
    store = get_store(path)
    if not store:
        console.print("Failed to create or open store.")
        return 1
    console.print(f"Schema at version 1: {path}")
    return 0


def cmd_last_runs(args: argparse.Namespace) -> int:
    """Show recent runs and incidents from persistence (admin view)."""
    config = getattr(args, "config_obj", None)
    db_path = getattr(args, "db", None) or (config and getattr(config, "persistence_db_path", None)) or os.getenv("WAVEOS_PERSISTENCE_DB_PATH")
    if not db_path:
        console.print("Persistence not configured. Set --db <path> or persistence_db_path in config.")
        return 1
    from waveos.persistence.store import get_store
    store = get_store(Path(db_path))
    if not store:
        console.print(f"Could not open store at {db_path}")
        return 1
    limit_runs = getattr(args, "limit", 10)
    limit_incidents = getattr(args, "incidents", 5)
    runs = store.get_recent_runs(limit=limit_runs)
    incidents = store.get_recent_incidents(limit=limit_incidents)
    rt = Table(title="Recent runs")
    rt.add_column("run_id", style="cyan")
    rt.add_column("started_at")
    rt.add_column("completed_at")
    rt.add_column("samples")
    rt.add_column("scores")
    rt.add_column("actions")
    for r in runs:
        rt.add_row(
            str(r.get("run_id", ""))[:16] + "…" if len(str(r.get("run_id", ""))) > 16 else str(r.get("run_id", "")),
            str(r.get("started_at", "")),
            str(r.get("completed_at", "")),
            str(r.get("sample_count", 0)),
            str(r.get("score_count", 0)),
            str(r.get("action_count", 0)),
        )
    console.print(rt)
    it = Table(title="Recent incidents")
    it.add_column("incident_id", style="cyan")
    it.add_column("run_id")
    it.add_column("created_at")
    it.add_column("severity")
    it.add_column("summary")
    for i in incidents:
        it.add_row(
            str(i.get("incident_id", ""))[:14] + "…" if len(str(i.get("incident_id", ""))) > 14 else str(i.get("incident_id", "")),
            str(i.get("run_id", ""))[:16] + "…" if len(str(i.get("run_id", ""))) > 16 else str(i.get("run_id", "")),
            str(i.get("created_at", "")),
            str(i.get("severity", "")),
            (str(i.get("summary", ""))[:50] + "…") if len(str(i.get("summary", ""))) > 50 else str(i.get("summary", "")),
        )
    console.print(it)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Single-pane status: active bundle, last runs, fleet, policy (Productization Phase 3 admin view)."""
    config = getattr(args, "config_obj", None)
    console.print("[bold]WaveOS status[/bold]")
    # Active bundle
    state_dir = Path(getattr(config, "bundle_state_dir", "out/bundles/state") or "out/bundles/state")
    if state_dir.exists():
        try:
            from waveos.update_agent import load_state
            state = load_state(state_dir)
            console.print(f"  Active bundle: {state.active_bundle_id or '—'}")
            if state.canary_bundle_id:
                console.print(f"  Canary staged: {state.canary_bundle_id}")
        except Exception:
            console.print("  Active bundle: —")
    else:
        console.print("  Active bundle: —")
    # Last runs (from persistence)
    db_path = config and getattr(config, "persistence_db_path", None) or os.getenv("WAVEOS_PERSISTENCE_DB_PATH")
    if db_path:
        try:
            from waveos.persistence.store import get_store
            store = get_store(Path(db_path))
            if store:
                runs = store.get_recent_runs(limit=3)
                if runs:
                    console.print(f"  Last runs: {len(runs)} recent (use 'waveos last-runs' for details)")
                else:
                    console.print("  Last runs: none")
            else:
                console.print("  Last runs: —")
        except Exception:
            console.print("  Last runs: —")
    else:
        console.print("  Last runs: (persistence not configured)")
    # Fleet
    nodes_path = None
    if config and getattr(config, "state_registry_path", None):
        nodes_path = Path(config.state_registry_path).parent / "nodes.json"
    if not nodes_path or not nodes_path.is_file():
        nodes_path = Path("out/nodes.json")
    if nodes_path.is_file():
        try:
            from waveos.orchestration import get_node_registry, load_nodes_from_file
            from waveos.node_health import healthy_nodes
            load_nodes_from_file(nodes_path)
            reg = get_node_registry()
            heartbeat_path = nodes_path.parent / "heartbeats.jsonl"
            if not heartbeat_path.is_file():
                heartbeat_path = Path("out/heartbeats.jsonl")
            health = healthy_nodes(heartbeat_path, max_age_seconds=120) if heartbeat_path.is_file() else {}
            healthy_count = sum(1 for nid in reg if health.get(nid) is True)
            console.print(f"  Fleet: {len(reg)} nodes ({healthy_count} healthy)")
        except Exception:
            console.print("  Fleet: —")
    else:
        console.print("  Fleet: (no nodes registry)")
    # Policy
    policy_path = config and getattr(config, "policy_templates_path", None)
    console.print(f"  Policy: {policy_path or 'default'}")
    return 0


def cmd_validate_schema(args: argparse.Namespace) -> int:
    """Validate telemetry file against schema registry (Data plane Phase 2)."""
    from waveos.schema_registry import validate_telemetry_schema
    from waveos.utils import read_json, read_jsonl
    path = Path(getattr(args, "file", ""))
    version = getattr(args, "schema_version", "1")
    if not path.is_file():
        console.print(f"File not found: {path}")
        return 1
    if path.suffix == ".json":
        data = read_json(path)
        records = data if isinstance(data, list) else data.get("records", [])
    else:
        records = read_jsonl(path)
    ok, errors = validate_telemetry_schema(records, version=version)
    if ok:
        console.print(f"[green]Valid[/green]: {len(records)} records, schema version {version}")
        return 0
    for e in errors[:30]:
        console.print(f"[red]{e}[/red]")
    if len(errors) > 30:
        console.print(f"[red]... and {len(errors) - 30} more[/red]")
    return 1


def cmd_change_log(args: argparse.Namespace) -> int:
    """Show deployment/policy change log (Compliance Phase 3)."""
    from waveos.change_log import get_recent_changes
    config = getattr(args, "config_obj", None)
    path = getattr(args, "path", None)
    if not path:
        state_dir = Path(getattr(config, "bundle_state_dir", "out/bundles/state") or "out/bundles/state")
        path = state_dir / "deployment_changes.jsonl"
    else:
        path = Path(path)
    limit = getattr(args, "limit", 20)
    entries = get_recent_changes(path, limit=limit)
    if not entries:
        console.print("No change log entries (or file not found).")
        return 0
    table = Table(title="Change log (newest first)")
    table.add_column("timestamp_utc", style="dim")
    table.add_column("event", style="cyan")
    table.add_column("bundle_id")
    table.add_column("approver")
    for e in entries:
        table.add_row(
            str(e.get("timestamp_utc", ""))[:19],
            str(e.get("event", "")),
            str(e.get("bundle_id", "—")),
            str(e.get("approver", "—")),
        )
    console.print(table)
    return 0


def cmd_verify_evidence_attestation(args: argparse.Namespace) -> int:
    """Verify evidence_attestation.json artifact hashes (Persistence Phase 3)."""
    from waveos.reporting import verify_evidence_attestation
    path = Path(getattr(args, "path", ""))
    if path.is_dir():
        path = path / "evidence_attestation.json"
    ok, errors = verify_evidence_attestation(path)
    if ok:
        console.print("[green]Attestation verified.[/green]")
        return 0
    for e in errors:
        console.print(f"[red]{e}[/red]")
    return 1


def cmd_policy_lint(args: argparse.Namespace) -> int:
    """Validate policy template file against schema (Policy Phase 2)."""
    from waveos.policy.schema import validate_policy_file
    path = Path(getattr(args, "file", ""))
    ok, errors = validate_policy_file(path)
    if ok:
        console.print(f"[green]Valid[/green]: {path}")
        return 0
    for e in errors:
        console.print(f"[red]{e}[/red]")
    return 1


def cmd_access_review_export(args: argparse.Namespace) -> int:
    """Export RBAC roles, permissions, and token assignment summary for access review (Compliance Phase 2)."""
    from waveos.utils.rbac import ROLE_PERMISSIONS, PERMISSION_CLEARANCE, Role
    from waveos.utils.auth import load_token_roles_from_env, load_token_roles_from_config
    config = getattr(args, "config_obj", None)
    out_path = Path(args.out)
    roles_export = []
    for role in Role:
        perms = ROLE_PERMISSIONS.get(role, [])
        roles_export.append({
            "role": role.value,
            "permissions": [p.value for p in perms],
        })
    clearance_export = {p.value: c.value for p, c in (PERMISSION_CLEARANCE or {}).items()}
    token_roles_from_config = {}
    if config and getattr(config, "auth_tokens", None):
        token_roles_from_config = dict(config.auth_tokens)
    token_roles_from_env = load_token_roles_from_env()
    roles_from_config = set(token_roles_from_config.values())
    roles_from_env = {r.value for r in token_roles_from_env.values()}
    export = {
        "roles": roles_export,
        "permission_clearance": clearance_export,
        "token_assignments": {
            "from_config_count": len(token_roles_from_config),
            "from_env_count": len(token_roles_from_env),
            "roles_granted": list(sorted(roles_from_config | roles_from_env)),
        },
    }
    write_json(out_path, export)
    console.print(f"Access review export written to {out_path}")
    return 0


def cmd_compliance_report(args: argparse.Namespace) -> int:
    """Generate compliance report (V3); optional auditor-ready zip."""
    from waveos.compliance import build_auditor_package, generate_report, write_report
    config = getattr(args, "config_obj", None)
    audit_path = Path(args.audit_path) if getattr(args, "audit_path", None) else None
    if not audit_path and config and config.audit_log_path:
        audit_path = Path(config.audit_log_path)
    report = generate_report(
        framework=args.framework,
        run_meta={},
        audit_path=audit_path,
    )
    out_path = Path(args.out)
    sign_key = getattr(args, "sign_key", None)
    if sign_key is None and config and getattr(config, "compliance_report_sign_key", None):
        sign_key = get_secret(config.compliance_report_sign_key, provider=config.secrets_provider) if config.secrets_provider else None
    if sign_key is None and config and config.bundle_hmac_key_secret:
        sign_key = get_secret(config.bundle_hmac_key_secret, provider=config.secrets_provider)  # fallback: reuse HMAC key
    retention_days = getattr(args, "retention_days", None) or (config.retention_days if config else None)
    write_report(report, out_path, sign_key=sign_key, retention_days=retention_days)
    console.print(f"Wrote {args.framework} report to {args.out}")
    auditor_zip = getattr(args, "auditor_package", None)
    if auditor_zip:
        build_auditor_package(
            report, out_path, Path(auditor_zip),
            include_audit_path=audit_path,
            retention_days=retention_days,
        )
        console.print(f"Auditor package written to {auditor_zip}")
    return 0


def cmd_validate_config(args: argparse.Namespace) -> int:
    """Validate config and print summary. Exit 0 if valid, 2 if invalid (handled in main). Used for automation."""
    config = getattr(args, "config_obj", None)
    if not config:
        console.print("No config loaded (using defaults and env)")
        return 0
    fp = config_fingerprint(config)
    console.print(f"config valid (fingerprint={fp[:16]}...)")
    console.print(f"  log_level={config.log_level} metrics_port={config.metrics_port} audit_enabled={config.audit_enabled}")
    return 0


def cmd_health_check(args: argparse.Namespace) -> int:
    """Exit 0 if license and config are valid. Used for K8s exec readiness/liveness probes."""
    # License already checked in main(); config loaded and attached as args.config_obj
    if getattr(args, "config_obj", None) is not None:
        console.print("ok (license and config valid)")
    else:
        console.print("ok (license valid)")
    return 0


def cmd_agent(args: argparse.Namespace) -> int:
    """Edge agent mode (Implementation Priorities §4): heartbeat to coordinator, optional run loop, offline-safe."""
    node_id = getattr(args, "node_id", None) or os.getenv("WAVEOS_AGENT_NODE_ID", "node-1")
    coordinator_url = (getattr(args, "coordinator_url", None) or os.getenv("WAVEOS_COORDINATOR_URL", "")).strip()
    heartbeat_file = getattr(args, "heartbeat_file", None) or os.getenv("WAVEOS_AGENT_HEARTBEAT_FILE", "")
    interval = int(getattr(args, "interval", 0) or os.getenv("WAVEOS_AGENT_INTERVAL_SEC", "60"))
    run_each_cycle = getattr(args, "run", False) or (os.getenv("WAVEOS_AGENT_RUN_EACH_CYCLE", "").lower() in ("1", "true", "yes"))
    out_dir = Path(getattr(args, "output", "out") or "out")
    payload = {"node_id": node_id, "version": current_version()}
    heartbeat_path = Path(heartbeat_file).expanduser() if heartbeat_file else (out_dir / "agent" / "heartbeat.jsonl")
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    cycle = 0
    while not should_shutdown():
        cycle += 1
        emit_heartbeat(node_id, payload=payload, output_path=heartbeat_path)
        if coordinator_url and coordinator_url.startswith("https://"):
            try:
                import urllib.request
                req = urllib.request.Request(
                    f"{coordinator_url.rstrip('/')}/heartbeat",
                    data=json.dumps({**payload, "timestamp": utc_now().isoformat()}, default=str).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status in (200, 201, 202):
                        logger.debug("Heartbeat sent to coordinator")
            except Exception as exc:
                logger.warning("Coordinator heartbeat failed: %s", type(exc).__name__)
        if run_each_cycle:
            run_args = argparse.Namespace(
                input=str(out_dir / "run_input"),
                baseline=str(out_dir / "baseline"),
                output=str(out_dir / f"run_{cycle}"),
                config=getattr(args, "config", None),
                config_obj=getattr(args, "config_obj", None),
            )
            if (out_dir / "run_input").exists() or (out_dir / "baseline").exists():
                cmd_run(run_args)
        if interval <= 0:
            break
        time.sleep(interval)
    return 0


def cmd_coordinator(args: argparse.Namespace) -> int:
    """Coordinator v1: node registry, heartbeat ingestion, policy distribution, run ingestion, fleet status API."""
    sub = getattr(args, "coordinator_command", None)
    if sub == "serve":
        host = getattr(args, "host", None) or os.getenv("WAVEOS_COORDINATOR_HOST", "0.0.0.0")
        port = getattr(args, "port", None) or int(os.getenv("WAVEOS_COORDINATOR_PORT", "9100"))
        db_path = (Path(getattr(args, "db", "") or os.getenv("WAVEOS_COORDINATOR_DB", "out/coordinator/coordinator.db")).expanduser())
        use_ssl = getattr(args, "tls", False) or (os.getenv("WAVEOS_COORDINATOR_TLS", "").lower() in ("1", "true", "yes"))
        run_coordinator_server(host=host, port=port, db_path=db_path, use_ssl=use_ssl)
        return 0
    console.print("Coordinator v1: node registry, heartbeats, policy, run ingestion, fleet status API.")
    console.print("  waveos coordinator serve   - start coordinator server")
    console.print("  Endpoints: POST /heartbeat, POST /nodes/join, GET /fleet/status, GET /policy/<version>, POST /runs")
    console.print("  Auth: set WAVEOS_COORDINATOR_AGENT_TOKEN for Bearer token; mTLS optional.")
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
    if getattr(args, "encrypt", False):
        enc_key = get_secret("WAVEOS_ENCRYPTION_KEY") or get_secret("waveos_encryption_key")
        if not enc_key:
            console.print("Missing encryption key; set WAVEOS_ENCRYPTION_KEY for --encrypt")
            return 2
        if not encrypt_bundle_artifacts(bundle_dir, enc_key):
            console.print("Failed to encrypt bundle artifacts")
            return 2
        import json
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["encrypted_artifacts"] = True
        manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
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
    active_dir = Path(config.bundle_active_dir)
    history_dir = Path(config.bundle_history_dir)
    state_dir = Path(config.bundle_state_dir)
    canary_percent = getattr(args, "canary_percent", None) or config.bundle_canary_percent
    canary_dir = Path(args.canary_dir) if getattr(args, "canary_dir", None) else None
    cache_path = getattr(args, "from_cache", None) or config.bundle_offline_cache_path
    decryption_key = get_secret("WAVEOS_ENCRYPTION_KEY") or get_secret("waveos_encryption_key")
    if cache_path and getattr(args, "bundle_id", None):
        install_bundle_from_cache(
            Path(cache_path),
            args.bundle_id,
            active_dir,
            history_dir,
            state_dir,
            hmac_key=hmac_key,
            canary_percent=canary_percent,
            canary_dir=canary_dir,
            decryption_key=decryption_key,
        )
    else:
        if not getattr(args, "dir", None):
            console.print("Either --dir <path> or --from-cache <path> and --bundle-id are required")
            return 1
        install_bundle(
            Path(args.dir),
            active_dir,
            history_dir,
            state_dir,
            hmac_key=hmac_key,
            canary_percent=canary_percent,
            canary_dir=canary_dir,
            decryption_key=decryption_key,
        )
    if canary_percent is not None and canary_dir and 0 <= canary_percent < 100:
        console.print("Bundle installed to canary; run 'waveos bundle promote' to activate.")
    else:
        console.print("Bundle installed")
    return 0


def cmd_bundle_promote(args: argparse.Namespace) -> int:
    config = getattr(args, "config_obj", None)
    if not config:
        console.print("Missing configuration")
        return 2
    canary_dir = Path(args.canary_dir) if getattr(args, "canary_dir", None) else Path(config.bundle_active_dir).parent / "canary"
    promote_canary_bundle(
        canary_dir,
        Path(config.bundle_active_dir),
        Path(config.bundle_history_dir),
        Path(config.bundle_state_dir),
    )
    console.print("Canary promoted to active")
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
        logger.warning("Alert routing failed: %s", type(exc).__name__)


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
            hash_chain=getattr(config, "audit_hash_chain", False),
        )
    return allowed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="waveos", description="Wave OS demo CLI")
    parser.add_argument("--config", help="Path to config file (toml/json)")
    parser.add_argument("-V", "--version", action="store_true", help="Show version and exit")
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

    soak_test_parser = sub.add_parser("soak-test", help="Run pipeline repeatedly for stability (SRE Phase 3)")
    soak_test_parser.add_argument("--in", required=True, dest="input")
    soak_test_parser.add_argument("--baseline", required=True)
    soak_test_parser.add_argument("--out", required=True, dest="output")
    soak_test_parser.add_argument("--runs", type=int, default=5, help="Number of runs")
    soak_test_parser.add_argument("--every", type=int, default=10, help="Seconds between runs")
    soak_test_parser.add_argument("--min-success", type=int, help="Require at least N successful runs to pass")
    soak_test_parser.set_defaults(func=cmd_soak_test)

    ingest_mqtt_parser = sub.add_parser("ingest-mqtt", help="Pull telemetry from MQTT topic and write to file (Data plane Phase 1)")
    ingest_mqtt_parser.add_argument("--broker", required=True, help="MQTT broker host (e.g. localhost or hostname)")
    ingest_mqtt_parser.add_argument("--topic", required=True, help="Topic to subscribe to")
    ingest_mqtt_parser.add_argument("--out", required=True, dest="output", help="Output path (e.g. out/telemetry.jsonl)")
    ingest_mqtt_parser.add_argument("--timeout", type=float, default=30.0, help="Seconds to collect (default 30)")
    ingest_mqtt_parser.add_argument("--max-messages", type=int, default=1000, help="Max messages to collect")
    ingest_mqtt_parser.add_argument("--port", type=int, default=1883, help="Broker port")
    ingest_mqtt_parser.set_defaults(func=cmd_ingest_mqtt)

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

    health_parser = sub.add_parser("health-check", help="Readiness/liveness check (license + config)")
    health_parser.set_defaults(func=cmd_health_check)

    validate_config_parser = sub.add_parser("validate-config", help="Validate config file and env, print summary")
    validate_config_parser.set_defaults(func=cmd_validate_config)

    list_plugins_parser = sub.add_parser("list-plugins", help="List registered plugins (V2)")
    list_plugins_parser.add_argument("--kind", choices=[k.value for k in PluginKind])
    list_plugins_parser.set_defaults(func=cmd_list_plugins)

    list_devices_parser = sub.add_parser("list-devices", help="List device drivers and optional devices (V2)")
    list_devices_parser.add_argument("--devices", action="store_true", help="List device IDs per driver")
    list_devices_parser.set_defaults(func=cmd_list_devices)

    list_nodes_parser = sub.add_parser("list-nodes", help="List registered orchestration nodes (V3)")
    list_nodes_parser.add_argument("--file", help="Path to nodes JSON file (default: from env or out/nodes.json)")
    list_nodes_parser.add_argument("--canary-sites", help="Only list nodes in these site IDs (comma-separated; Fleet Phase 2)")
    list_nodes_parser.add_argument("--sites", help="Only list nodes in these site IDs (comma-separated)")
    list_nodes_parser.set_defaults(func=cmd_list_nodes)

    fleet_status_parser = sub.add_parser("fleet-status", help="Fleet status: nodes + health from heartbeats")
    fleet_status_parser.add_argument("--file", help="Path to nodes JSON (default: out/nodes.json)")
    fleet_status_parser.add_argument("--max-age-seconds", type=int, default=120, help="Heartbeat max age for healthy")
    fleet_status_parser.set_defaults(func=cmd_fleet_status)

    agent_parser = sub.add_parser("agent", help="Edge agent: heartbeat to coordinator, optional run loop (Fleet §4)")
    agent_parser.add_argument("--node-id", help="Node/site ID (default: WAVEOS_AGENT_NODE_ID or node-1)")
    agent_parser.add_argument("--coordinator-url", help="Coordinator URL for heartbeat POST (default: WAVEOS_COORDINATOR_URL)")
    agent_parser.add_argument("--heartbeat-file", help="Write heartbeats to this JSONL file (default: out/agent/heartbeat.jsonl)")
    agent_parser.add_argument("--interval", type=int, default=0, help="Seconds between cycles (0=once; default: WAVEOS_AGENT_INTERVAL_SEC or 60)")
    agent_parser.add_argument("--run", action="store_true", help="Run pipeline each cycle (or set WAVEOS_AGENT_RUN_EACH_CYCLE=1)")
    agent_parser.add_argument("--output", default="out", help="Output base dir for run artifacts")
    agent_parser.set_defaults(func=cmd_agent)

    coordinator_parser = sub.add_parser("coordinator", help="Coordinator v1: node registry, policy, fleet status (Fleet §4)")
    coordinator_sub = coordinator_parser.add_subparsers(dest="coordinator_command")
    coordinator_serve = coordinator_sub.add_parser("serve", help="Start coordinator server")
    coordinator_serve.add_argument("--host", default="0.0.0.0", help="Bind host")
    coordinator_serve.add_argument("--port", type=int, help="Port (default: WAVEOS_COORDINATOR_PORT or 9100)")
    coordinator_serve.add_argument("--db", help="SQLite path (default: out/coordinator/coordinator.db)")
    coordinator_serve.add_argument("--tls", action="store_true", help="Enable TLS (WAVEOS_COORDINATOR_TLS_CERT, _TLS_KEY)")
    coordinator_serve.set_defaults(func=cmd_coordinator)
    coordinator_parser.set_defaults(func=cmd_coordinator)

    runbook_parser = sub.add_parser("runbook", help="SRE runbooks: list or run")
    runbook_sub = runbook_parser.add_subparsers(dest="runbook_command")
    runbook_list_parser = runbook_sub.add_parser("list", help="List available runbooks")
    runbook_list_parser.set_defaults(func=cmd_runbook_list)
    runbook_run_parser = runbook_sub.add_parser("run", help="Run a runbook (steps shown)")
    runbook_run_parser.add_argument("runbook_id", help="Runbook id (e.g. telemetry_stale, actuator_down)")
    runbook_run_parser.set_defaults(func=cmd_runbook_run)

    policy_parser = sub.add_parser("policy", help="Policy schema and lint (Policy Phase 2)")
    policy_sub = policy_parser.add_subparsers(dest="policy_command")
    policy_lint_parser = policy_sub.add_parser("lint", help="Validate policy template file against schema")
    policy_lint_parser.add_argument("file", help="Path to policy JSON file")
    policy_lint_parser.set_defaults(func=cmd_policy_lint)

    access_review_parser = sub.add_parser("access-review-export", help="Export RBAC access review (Compliance Phase 2)")
    access_review_parser.add_argument("--out", required=True, help="Output JSON path")
    access_review_parser.set_defaults(func=cmd_access_review_export)

    install_parser = sub.add_parser("install", help="One-command install: create out dirs and optional config example")
    install_parser.add_argument("--prefix", default=".", help="Installation prefix (default: .)")
    install_parser.add_argument("--config", dest="config_example", action="store_true", help="Write out/config.toml.example")
    install_parser.set_defaults(func=cmd_install)

    migrate_parser = sub.add_parser("migrate", help="Ensure persistence DB schema is current")
    migrate_parser.add_argument("--db", help="Path to SQLite DB (default: from config persistence_db_path)")
    migrate_parser.set_defaults(func=cmd_migrate)

    last_runs_parser = sub.add_parser("last-runs", help="Show recent runs and incidents from persistence (admin view)")
    last_runs_parser.add_argument("--db", help="Path to SQLite DB (default: from config)")
    last_runs_parser.add_argument("--limit", type=int, default=10, help="Max runs to show")
    last_runs_parser.add_argument("--incidents", type=int, default=5, help="Max incidents to show")
    last_runs_parser.set_defaults(func=cmd_last_runs)

    status_parser = sub.add_parser("status", help="Single-pane status: bundle, last runs, fleet, policy (admin view)")
    status_parser.set_defaults(func=cmd_status)

    verify_attestation_parser = sub.add_parser("verify-evidence-attestation", help="Verify evidence pack attestation hashes (Persistence Phase 3)")
    verify_attestation_parser.add_argument("path", help="Path to evidence_attestation.json (or run output dir)")
    verify_attestation_parser.set_defaults(func=cmd_verify_evidence_attestation)

    change_log_parser = sub.add_parser("change-log", help="Show deployment/policy change log (Compliance Phase 3)")
    change_log_parser.add_argument("--path", help="Path to deployment_changes.jsonl (default: <bundle_state_dir>/deployment_changes.jsonl)")
    change_log_parser.add_argument("--limit", type=int, default=20, help="Max entries to show")
    change_log_parser.set_defaults(func=cmd_change_log)

    validate_schema_parser = sub.add_parser("validate-schema", help="Validate telemetry file against schema registry (Data plane Phase 2)")
    validate_schema_parser.add_argument("file", help="Path to telemetry JSON/JSONL file")
    validate_schema_parser.add_argument("--schema-version", dest="schema_version", default="1", help="Schema version (default: 1)")
    validate_schema_parser.set_defaults(func=cmd_validate_schema)

    compliance_report_parser = sub.add_parser("compliance-report", help="Generate compliance report (V3)")
    compliance_report_parser.add_argument("--framework", choices=["NERC", "SOC2", "DoD"], default="NERC")
    compliance_report_parser.add_argument("--out", required=True, help="Output JSON path")
    compliance_report_parser.add_argument("--audit-path", help="Path to audit JSONL")
    compliance_report_parser.add_argument("--auditor-package", help="Also write auditor-ready zip (report + manifest + optional audit excerpt)")
    compliance_report_parser.add_argument("--sign-key", help="HMAC key to sign report (or set via secrets)")
    compliance_report_parser.add_argument("--retention-days", type=int, help="Retention period for report (auditor-ready)")
    compliance_report_parser.set_defaults(func=cmd_compliance_report)

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
    bundle_build.add_argument("--encrypt", action="store_true", default=False, help="Encrypt artifact payloads (DoD); requires WAVEOS_ENCRYPTION_KEY")
    bundle_build.set_defaults(func=cmd_bundle_build)
    bundle_install = bundle_sub.add_parser("install", help="Install bundle")
    bundle_install.add_argument("--dir", help="Bundle directory (or use --from-cache + --bundle-id)")
    bundle_install.add_argument("--from-cache", help="Install from offline cache directory (air-gapped)")
    bundle_install.add_argument("--bundle-id", help="Bundle ID when installing from cache")
    bundle_install.add_argument("--canary-percent", type=int, help="Install to canary only (0-99); then run promote")
    bundle_install.add_argument("--canary-dir", help="Directory for canary install (default: <active_dir>/../canary)")
    bundle_install.set_defaults(func=cmd_bundle_install)
    bundle_promote = bundle_sub.add_parser("promote", help="Promote canary bundle to active")
    bundle_promote.add_argument("--canary-dir", help="Canary directory to promote")
    bundle_promote.set_defaults(func=cmd_bundle_promote)
    bundle_rollback = bundle_sub.add_parser("rollback", help="Rollback bundle")
    bundle_rollback.set_defaults(func=cmd_bundle_rollback)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if getattr(args, "version", False):
        console.print(current_version())
        raise SystemExit(0)
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
    set_strict_secrets(config.strict_secrets)
    level = getattr(logging, config.log_level.upper(), logging.INFO)
    setup_logging(level=level, log_format=config.log_format, spool_path=Path(config.log_spool_path) if config.log_spool_path else None)
    drop_privileges(config.drop_privileges_user, config.drop_privileges_group)
    apply_resource_limits(config.max_memory_mb, config.max_cpu_seconds)
    start_metrics_server(config.metrics_port)
    start_health_server(getattr(config, "health_http_port", None), config)
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
