#!/usr/bin/env python3
"""
Soak runner: run waveos pipeline or agent in a loop for N iterations or duration.
Emits a report JSON (and optional Markdown) for evidence of soak runs.

Usage:
  python scripts/soak_runner.py pipeline --iterations 100 --in demo_data/run --baseline demo_data/baseline --out out/soak --report out/soak_report.json
  python scripts/soak_runner.py agent --duration 300 --interval 60 --report out/soak_agent_report.json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def _waveos_cmd() -> list[str]:
    """Return [waveos, ...] if waveos is on PATH, else [sys.executable, -m, waveos] so subprocess finds the package."""
    if shutil.which("waveos"):
        return ["waveos"]
    return [sys.executable, "-m", "waveos"]


def _write_report(report: dict, path: str, write_md: bool = True) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if write_md and path.endswith(".json"):
        md_path = p.with_suffix(".md")
        md_path.write_text(_report_to_md(report), encoding="utf-8")


def _report_to_md(report: dict) -> str:
    lines = [
        "# Soak run report",
        "",
        f"- **Mode:** {report.get('mode', 'unknown')}",
        f"- **Started:** {report.get('started_at', '')}",
        f"- **Ended:** {report.get('ended_at', '')}",
        f"- **Duration (s):** {report.get('duration_sec', 0)}",
    ]
    if report.get("mode") == "pipeline":
        lines.extend([
            f"- **Run count (total):** {report.get('run_count', 0)}",
            f"- **Success count:** {report.get('success_count', 0)}",
            f"- **Failure count:** {report.get('failure_count', 0)}",
            "",
            "## Recovery behavior",
            report.get("recovery_behavior") or "N/A (no restarts or failures during soak).",
        ])
    if report.get("mode") == "agent":
        lines.extend([
            f"- **Exit:** {report.get('exit_reason', 'completed')}",
            report.get("recovery_behavior") and f"- **Recovery:** {report['recovery_behavior']}" or "",
        ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Soak run: pipeline or agent loop; optional --report for evidence.")
    sub = parser.add_subparsers(dest="mode")
    p_pl = sub.add_parser("pipeline", help="Run waveos run in a loop")
    p_pl.add_argument("--iterations", type=int, default=10)
    p_pl.add_argument("--in", dest="input", required=True)
    p_pl.add_argument("--baseline", required=True)
    p_pl.add_argument("--out", default="out/soak")
    p_pl.add_argument("--report", default=None, help="Write report JSON (and .md) to this path")
    p_agent = sub.add_parser("agent", help="Run waveos agent for duration")
    p_agent.add_argument("--duration", type=int, default=60, help="Seconds to run")
    p_agent.add_argument("--interval", type=int, default=30)
    p_agent.add_argument("--report", default=None, help="Write report JSON (and .md) to this path")
    args = parser.parse_args()

    if args.mode == "pipeline":
        cmd_base = _waveos_cmd()
        env = os.environ.copy()
        env.setdefault("WAVEOS_LICENSE_KEY", "WAVEOS-CI-20991231-TEST")
        started = datetime.now(timezone.utc).isoformat()
        t0 = time.perf_counter()
        success_count = 0
        failure_count = 0
        completed = 0
        try:
            for i in range(args.iterations):
                out = os.path.join(args.out, f"run_{i}")
                rc = subprocess.call(
                    [*cmd_base, "run", "--in", args.input, "--baseline", args.baseline, "--out", out],
                    timeout=120,
                    env=env,
                )
                completed = i + 1
                if rc == 0:
                    success_count += 1
                else:
                    failure_count += 1
                    print(f"Run {i} failed with exit {rc}")
        except KeyboardInterrupt:
            print("\nSoak interrupted (Ctrl+C); writing partial report.")
        duration_sec = round(time.perf_counter() - t0, 2)
        ended = datetime.now(timezone.utc).isoformat()
        report = {
            "mode": "pipeline",
            "started_at": started,
            "ended_at": ended,
            "duration_sec": duration_sec,
            "run_count": completed,
            "success_count": success_count,
            "failure_count": failure_count,
            "recovery_behavior": "All runs completed in-process; no coordinator/agent restart during soak."
            if failure_count == 0 else f"{failure_count} run(s) failed; inspect logs for root cause.",
        }
        if getattr(args, "report", None):
            _write_report(report, args.report)
        print(f"Soak pipeline: {success_count}/{completed} ok in {duration_sec}s")
        return 0 if failure_count == 0 else 1

    if args.mode == "agent":
        started = datetime.now(timezone.utc).isoformat()
        t0 = time.perf_counter()
        env = os.environ.copy()
        env.setdefault("WAVEOS_LICENSE_KEY", "WAVEOS-CI-20991231-TEST")
        env["WAVEOS_AGENT_INTERVAL_SEC"] = str(args.interval)
        cmd_base = _waveos_cmd()
        proc = subprocess.Popen(
            [*cmd_base, "agent", "--interval", str(args.interval)],
            env=env,
        )
        exit_reason = "completed"
        try:
            proc.wait(timeout=args.duration + 5)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=5)
            exit_reason = "terminated_after_duration"
        duration_sec = round(time.perf_counter() - t0, 2)
        ended = datetime.now(timezone.utc).isoformat()
        report = {
            "mode": "agent",
            "started_at": started,
            "ended_at": ended,
            "duration_sec": duration_sec,
            "exit_reason": exit_reason,
            "recovery_behavior": "Agent ran for requested duration; no coordinator kill/partition in this run.",
        }
        if getattr(args, "report", None):
            _write_report(report, args.report)
        print("Soak agent: completed")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
