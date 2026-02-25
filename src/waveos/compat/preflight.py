"""Preflight compatibility checks before bundle install/activate."""

from __future__ import annotations

import json
import os
import platform
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.compat.preflight")


class PreflightOutcome(str, Enum):
    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"
    ALLOW_WITH_ISOLATION = "allow_with_isolation"


@dataclass
class PreflightCheck:
    name: str
    passed: bool
    message: str = ""
    severity: str = "error"  # error | warning | info

    def to_dict(self) -> dict:
        return {"name": self.name, "passed": self.passed, "message": self.message, "severity": self.severity}


@dataclass
class PreflightResult:
    outcome: PreflightOutcome
    checks: List[PreflightCheck] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome.value,
            "checks": [c.to_dict() for c in self.checks],
            "timestamp": self.timestamp or utc_now().isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> PreflightResult:
        return cls(
            outcome=PreflightOutcome(d.get("outcome", "allow")),
            checks=[PreflightCheck(**c) for c in d.get("checks", [])],
            timestamp=d.get("timestamp", ""),
        )


def _check_os(required_os: str) -> PreflightCheck:
    current = platform.system().lower()
    required = required_os.lower()
    if not required:
        return PreflightCheck(name="os", passed=True, message=f"No OS requirement (current: {current})", severity="info")
    passed = current == required or required in current
    return PreflightCheck(name="os", passed=passed, message=f"Required: {required}, Current: {current}")


def _check_arch(required_arch: str) -> PreflightCheck:
    current = platform.machine().lower()
    required = required_arch.lower()
    if not required:
        return PreflightCheck(name="arch", passed=True, message=f"No arch requirement (current: {current})", severity="info")
    aliases = {"x86_64": ["x86_64", "amd64"], "aarch64": ["aarch64", "arm64"]}
    current_aliases = aliases.get(current, [current])
    required_aliases = aliases.get(required, [required])
    passed = bool(set(current_aliases) & set(required_aliases))
    return PreflightCheck(name="arch", passed=passed, message=f"Required: {required}, Current: {current}")


def _check_disk_space(path: str = "/", min_mb: int = 100) -> PreflightCheck:
    try:
        usage = shutil.disk_usage(path)
        free_mb = usage.free // (1024 * 1024)
        passed = free_mb >= min_mb
        return PreflightCheck(name="disk_space", passed=passed, message=f"Free: {free_mb}MB, Required: {min_mb}MB", severity="error" if not passed else "info")
    except OSError as exc:
        return PreflightCheck(name="disk_space", passed=False, message=f"Cannot check disk space: {exc}")


def _check_python_version(required: str = "") -> PreflightCheck:
    import sys
    current = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if not required:
        return PreflightCheck(name="python_version", passed=True, message=f"Current: {current}", severity="info")
    passed = current >= required
    return PreflightCheck(name="python_version", passed=passed, message=f"Required: >={required}, Current: {current}", severity="warning" if not passed else "info")


def _check_dependencies(required_libs: List[str]) -> PreflightCheck:
    if not required_libs:
        return PreflightCheck(name="dependencies", passed=True, message="No dependency requirements", severity="info")
    missing = []
    for lib in required_libs:
        try:
            __import__(lib.split(">=")[0].split("==")[0].strip().replace("-", "_"))
        except ImportError:
            missing.append(lib)
    passed = len(missing) == 0
    msg = f"Missing: {', '.join(missing)}" if missing else f"All {len(required_libs)} dependencies available"
    return PreflightCheck(name="dependencies", passed=passed, message=msg, severity="warning")


def run_preflight(
    bundle_dir: Path,
    min_disk_mb: int = 100,
    extra_checks: Optional[List[PreflightCheck]] = None,
) -> Dict[str, Any]:
    """Run preflight checks against a bundle manifest.

    Returns dict with 'outcome' (allow|warn|block|allow_with_isolation) and 'checks'.
    """
    checks: List[PreflightCheck] = []

    manifest_path = bundle_dir / "bundle.json"
    targets: List[Dict[str, Any]] = []
    runtimes_deps: List[str] = []
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            targets = data.get("targets", [])
            runtimes = data.get("runtimes", {})
            runtimes_deps = runtimes.get("dependencies", [])
        except (json.JSONDecodeError, OSError):
            checks.append(PreflightCheck(name="manifest", passed=False, message="Cannot parse manifest"))

    if targets:
        for target in targets:
            if target.get("os"):
                checks.append(_check_os(target["os"]))
            if target.get("arch"):
                checks.append(_check_arch(target["arch"]))
    else:
        checks.append(PreflightCheck(name="targets", passed=True, message="No target constraints", severity="info"))

    checks.append(_check_disk_space(min_mb=min_disk_mb))
    checks.append(_check_python_version())

    if runtimes_deps:
        checks.append(_check_dependencies(runtimes_deps))

    if extra_checks:
        checks.extend(extra_checks)

    has_errors = any(not c.passed and c.severity == "error" for c in checks)
    has_warnings = any(not c.passed and c.severity == "warning" for c in checks)

    if has_errors:
        outcome = PreflightOutcome.BLOCK
    elif has_warnings:
        outcome = PreflightOutcome.WARN
    else:
        outcome = PreflightOutcome.ALLOW

    result = PreflightResult(outcome=outcome, checks=checks, timestamp=utc_now().isoformat())
    return result.to_dict()
