"""Health contracts — SLOs, rollback proofs, quarantine workflows, registry ban/hold."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.health_contracts")


class QuarantineStatus(str, Enum):
    ACTIVE = "active"
    QUARANTINED = "quarantined"
    BANNED = "banned"
    HELD = "held"


@dataclass
class ServiceSLO:
    """SLO (Service Level Objective) for a service."""
    service_name: str
    readiness_probe: str = ""
    max_startup_sec: float = 60.0
    max_latency_ms: float = 500.0
    min_success_rate: float = 99.0
    min_health_score: float = 70.0
    invariants: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"service_name": self.service_name, "readiness_probe": self.readiness_probe,
                "max_startup_sec": self.max_startup_sec, "max_latency_ms": self.max_latency_ms,
                "min_success_rate": self.min_success_rate, "min_health_score": self.min_health_score,
                "invariants": self.invariants}

    @classmethod
    def from_dict(cls, d: dict) -> ServiceSLO:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


@dataclass
class SLOCheckResult:
    """Result of checking a service against its SLO."""
    service_name: str
    passed: bool
    checks: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {"service_name": self.service_name, "passed": self.passed, "checks": self.checks,
                "timestamp": self.timestamp or utc_now().isoformat()}


def check_service_slo(slo: ServiceSLO, health_score: float = 100.0,
                      latency_ms: float = 0.0, success_rate: float = 100.0,
                      startup_sec: float = 0.0, invariant_results: Optional[Dict[str, bool]] = None) -> SLOCheckResult:
    """Check a service against its SLO."""
    checks: List[Dict[str, Any]] = []
    all_passed = True

    if health_score < slo.min_health_score:
        checks.append({"check": "health_score", "passed": False, "actual": health_score, "required": slo.min_health_score})
        all_passed = False
    else:
        checks.append({"check": "health_score", "passed": True, "actual": health_score, "required": slo.min_health_score})

    if slo.max_latency_ms > 0 and latency_ms > slo.max_latency_ms:
        checks.append({"check": "latency", "passed": False, "actual_ms": latency_ms, "max_ms": slo.max_latency_ms})
        all_passed = False
    else:
        checks.append({"check": "latency", "passed": True, "actual_ms": latency_ms, "max_ms": slo.max_latency_ms})

    if success_rate < slo.min_success_rate:
        checks.append({"check": "success_rate", "passed": False, "actual": success_rate, "required": slo.min_success_rate})
        all_passed = False
    else:
        checks.append({"check": "success_rate", "passed": True, "actual": success_rate, "required": slo.min_success_rate})

    if slo.max_startup_sec > 0 and startup_sec > slo.max_startup_sec:
        checks.append({"check": "startup_time", "passed": False, "actual_sec": startup_sec, "max_sec": slo.max_startup_sec})
        all_passed = False
    else:
        checks.append({"check": "startup_time", "passed": True, "actual_sec": startup_sec, "max_sec": slo.max_startup_sec})

    if slo.invariants and invariant_results:
        for inv in slo.invariants:
            inv_ok = invariant_results.get(inv, False)
            checks.append({"check": f"invariant:{inv}", "passed": inv_ok})
            if not inv_ok:
                all_passed = False

    return SLOCheckResult(service_name=slo.service_name, passed=all_passed, checks=checks, timestamp=utc_now().isoformat())


@dataclass
class RollbackProof:
    """Deterministic evidence of why a rollback occurred."""
    bundle_id: str
    trigger: str
    reason: str
    health_state_before: Dict[str, Any] = field(default_factory=dict)
    health_state_after: Dict[str, Any] = field(default_factory=dict)
    slo_violations: List[Dict[str, Any]] = field(default_factory=list)
    events_leading: List[Dict[str, Any]] = field(default_factory=list)
    rolled_back_to: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {"bundle_id": self.bundle_id, "trigger": self.trigger, "reason": self.reason,
                "health_state_before": self.health_state_before, "health_state_after": self.health_state_after,
                "slo_violations": self.slo_violations, "events_leading": self.events_leading,
                "rolled_back_to": self.rolled_back_to, "timestamp": self.timestamp or utc_now().isoformat()}

    @classmethod
    def from_dict(cls, d: dict) -> RollbackProof:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


def generate_rollback_proof(bundle_id: str, trigger: str, reason: str,
                            slo_result: Optional[SLOCheckResult] = None,
                            health_before: Optional[Dict[str, Any]] = None,
                            events: Optional[List[Dict[str, Any]]] = None,
                            rolled_back_to: str = "") -> RollbackProof:
    """Generate a rollback proof with all evidence."""
    return RollbackProof(
        bundle_id=bundle_id, trigger=trigger, reason=reason,
        health_state_before=health_before or {},
        slo_violations=[c for c in (slo_result.checks if slo_result else []) if not c.get("passed")],
        events_leading=events or [],
        rolled_back_to=rolled_back_to,
        timestamp=utc_now().isoformat(),
    )


def write_rollback_proof(proof: RollbackProof, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = proof.timestamp.replace(":", "-")[:19] if proof.timestamp else "unknown"
    path = output_dir / f"rollback_proof_{proof.bundle_id}_{ts}.json"
    path.write_text(json.dumps(proof.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


@dataclass
class BundleQuarantineEntry:
    """Registry quarantine/ban entry for a bundle."""
    bundle_id: str
    status: QuarantineStatus
    reason: str = ""
    quarantined_by: str = ""
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"bundle_id": self.bundle_id, "status": self.status.value, "reason": self.reason,
                "quarantined_by": self.quarantined_by, "timestamp": self.timestamp or utc_now().isoformat(),
                "metadata": self.metadata}

    @classmethod
    def from_dict(cls, d: dict) -> BundleQuarantineEntry:
        d2 = dict(d)
        if "status" in d2:
            d2["status"] = QuarantineStatus(d2["status"])
        return cls(**{k: d2[k] for k in d2 if k in cls.__dataclass_fields__})


class QuarantineRegistry:
    """Manages quarantine/ban/hold states for bundles in the registry."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._entries: Dict[str, BundleQuarantineEntry] = {}
        self._path = path
        if path and path.exists():
            self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            for d in data:
                e = BundleQuarantineEntry.from_dict(d)
                self._entries[e.bundle_id] = e
        except (json.JSONDecodeError, OSError):
            pass

    def save(self) -> None:
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps([e.to_dict() for e in self._entries.values()], indent=2) + "\n", encoding="utf-8")

    def quarantine(self, bundle_id: str, reason: str = "", by: str = "") -> BundleQuarantineEntry:
        entry = BundleQuarantineEntry(bundle_id=bundle_id, status=QuarantineStatus.QUARANTINED,
                                       reason=reason, quarantined_by=by, timestamp=utc_now().isoformat())
        self._entries[bundle_id] = entry
        self.save()
        return entry

    def ban(self, bundle_id: str, reason: str = "", by: str = "") -> BundleQuarantineEntry:
        entry = BundleQuarantineEntry(bundle_id=bundle_id, status=QuarantineStatus.BANNED,
                                       reason=reason, quarantined_by=by, timestamp=utc_now().isoformat())
        self._entries[bundle_id] = entry
        self.save()
        return entry

    def hold(self, bundle_id: str, reason: str = "", by: str = "") -> BundleQuarantineEntry:
        entry = BundleQuarantineEntry(bundle_id=bundle_id, status=QuarantineStatus.HELD,
                                       reason=reason, quarantined_by=by, timestamp=utc_now().isoformat())
        self._entries[bundle_id] = entry
        self.save()
        return entry

    def release(self, bundle_id: str) -> bool:
        if bundle_id in self._entries:
            del self._entries[bundle_id]
            self.save()
            return True
        return False

    def is_blocked(self, bundle_id: str) -> Tuple[bool, str]:
        entry = self._entries.get(bundle_id)
        if not entry:
            return False, ""
        if entry.status in (QuarantineStatus.QUARANTINED, QuarantineStatus.BANNED, QuarantineStatus.HELD):
            return True, f"{entry.status.value}: {entry.reason}"
        return False, ""

    def get_status(self, bundle_id: str) -> Optional[BundleQuarantineEntry]:
        return self._entries.get(bundle_id)

    def list_all(self) -> List[BundleQuarantineEntry]:
        return list(self._entries.values())
