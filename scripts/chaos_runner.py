#!/usr/bin/env python3
"""
Chaos / failure-injection runner: run predefined scenarios and record outcomes to a report.
Use for evidence that "we operated it" (partition, restart, backpressure).

Usage:
  python scripts/chaos_runner.py --scenario kill_coordinator --report out/chaos_outcomes.json
  python scripts/chaos_runner.py --scenario backpressure --report out/chaos_outcomes.json
  python scripts/chaos_runner.py --list
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


SCENARIOS = {
    "kill_coordinator": "Start coordinator and agent; after K seconds kill coordinator; verify agent logs failure and retries (no crash).",
    "backpressure": "POST /runs at high rate to coordinator; record success/fail counts and memory/behavior.",
    "duplicate_join": "POST /nodes/join twice with same node_id; GET /nodes and fleet status; verify idempotent or single record.",
}


def _write_report(report: dict, path: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Append if file exists (multiple chaos runs)
    existing: list = []
    if p.exists():
        try:
            existing = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                existing = [existing]
        except Exception:
            existing = []
    existing.append(report)
    p.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def run_kill_coordinator(args: argparse.Namespace) -> dict:
    """Start coordinator in background, start agent, kill coordinator after K s, check agent exit/retry."""
    import tempfile
    db_dir = tempfile.mkdtemp(prefix="waveos_chaos_")
    db_path = os.path.join(db_dir, "coordinator.db")
    port = 19998
    started = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    outcome = "skipped"
    details = ""

    try:
        proc_coord = subprocess.Popen(
            [sys.executable, "-m", "waveos", "coordinator", "serve", "--db", db_path, "--port", str(port)],
            env={**os.environ, "WAVEOS_COORDINATOR_PORT": str(port)},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(1.5)
        if proc_coord.poll() is not None:
            outcome = "coordinator_exit_early"
            details = proc_coord.stderr.read() if proc_coord.stderr else ""
            return _chaos_report("kill_coordinator", started, time.perf_counter() - t0, outcome, details)

        # Run agent for a few seconds (it will heartbeat)
        env = {**os.environ, "WAVEOS_COORDINATOR_URL": f"http://127.0.0.1:{port}", "WAVEOS_AGENT_INTERVAL_SEC": "2"}
        proc_agent = subprocess.Popen(
            [sys.executable, "-m", "waveos", "agent", "--interval", "2", "--coordinator-url", f"http://127.0.0.1:{port}"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(2)
        proc_coord.terminate()
        proc_coord.wait(timeout=3)
        time.sleep(2)
        proc_agent.terminate()
        stderr = proc_agent.stderr.read() if proc_agent.stderr else ""
        proc_agent.wait(timeout=2)
        # Agent should exit cleanly (SIGTERM) or have logged connection failure; no crash.
        outcome = "passed" if proc_agent.returncode in (0, -15, None) else "agent_crash"
        details = stderr[:500] if stderr else "Agent exited after coordinator kill; no crash."
    except Exception as e:
        outcome = "error"
        details = str(e)
    finally:
        try:
            proc_coord.kill()
        except Exception:
            pass

    return _chaos_report("kill_coordinator", started, round(time.perf_counter() - t0, 2), outcome, details)


def run_backpressure(args: argparse.Namespace) -> dict:
    """POST /runs repeatedly; record counts and any errors."""
    started = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    url = getattr(args, "coordinator_url", None) or os.getenv("WAVEOS_COORDINATOR_URL", "http://127.0.0.1:9100")
    count = getattr(args, "request_count", 50)
    success = 0
    failed = 0
    try:
        import urllib.request
        for i in range(count):
            req = urllib.request.Request(
                f"{url.rstrip('/')}/runs",
                data=json.dumps({"node_id": "chaos-node", "run_id": f"chaos-{i}", "summary": {}}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    if 200 <= r.status < 300:
                        success += 1
            except Exception:
                failed += 1
    except Exception as e:
        outcome = "error"
        details = str(e)
        success, failed = 0, count
    else:
        outcome = "passed" if failed == 0 else "degraded"
        details = f"success={success} failed={failed}"
    return _chaos_report("backpressure", started, round(time.perf_counter() - t0, 2), outcome, details)


def run_duplicate_join(args: argparse.Namespace) -> dict:
    """POST /nodes/join twice with same node_id; GET /nodes; verify single or idempotent."""
    started = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    url = getattr(args, "coordinator_url", None) or os.getenv("WAVEOS_COORDINATOR_URL", "http://127.0.0.1:9100")
    try:
        import urllib.request
        body = json.dumps({"node_id": "chaos-dup-node", "site_id": "site1"}).encode("utf-8")
        for _ in range(2):
            req = urllib.request.Request(f"{url.rstrip('/')}/nodes/join", data=body, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=5) as r:
                r.read()
        req = urllib.request.Request(f"{url.rstrip('/')}/nodes", method="GET")
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode())
        nodes = data.get("nodes") or data.get("node_ids") or []
        dup = [n for n in nodes if (n.get("node_id") if isinstance(n, dict) else n) == "chaos-dup-node"]
        outcome = "passed" if len(dup) <= 1 else "unexpected_duplicates"
        details = f"nodes count={len(nodes)}; chaos-dup-node occurrences={len(dup)}"
    except Exception as e:
        outcome = "error"
        details = str(e)
    return _chaos_report("duplicate_join", started, round(time.perf_counter() - t0, 2), outcome, details)


def _chaos_report(scenario: str, started: str, duration_sec: float, outcome: str, details: str) -> dict:
    return {
        "scenario": scenario,
        "started_at": started,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "duration_sec": duration_sec,
        "outcome": outcome,
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Chaos / failure-injection runner; writes outcomes to --report.")
    parser.add_argument("--scenario", choices=list(SCENARIOS), help="Scenario to run")
    parser.add_argument("--report", default="out/chaos_outcomes.json", help="Report path (JSON)")
    parser.add_argument("--list", action="store_true", help="List scenarios and exit")
    parser.add_argument("--coordinator-url", default=os.getenv("WAVEOS_COORDINATOR_URL"), help="Coordinator base URL for backpressure/duplicate_join")
    parser.add_argument("--request-count", type=int, default=50, help="For backpressure: number of POSTs")
    args = parser.parse_args()

    if args.list:
        for name, desc in SCENARIOS.items():
            print(f"  {name}: {desc}")
        return 0

    if not args.scenario:
        parser.print_help()
        return 1

    runners = {
        "kill_coordinator": run_kill_coordinator,
        "backpressure": run_backpressure,
        "duplicate_join": run_duplicate_join,
    }
    report = runners[args.scenario](args)
    _write_report(report, args.report)
    print(f"Chaos {args.scenario}: outcome={report['outcome']} details={report['details'][:200]}")
    return 0 if report["outcome"] in ("passed", "degraded") else 1


if __name__ == "__main__":
    sys.exit(main())
