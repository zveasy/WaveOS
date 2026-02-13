"""V3: Compliance reports — NERC, SOC2, DoD templates from run_meta and audit; auditor-ready signing and retention."""

from __future__ import annotations

import hashlib
import hmac
import json
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.compliance")


@dataclass
class ComplianceReport:
    """Single compliance report (framework, period, findings)."""
    framework: str  # NERC, SOC2, DoD
    period_start: str
    period_end: str
    generated_at: str
    run_count: int = 0
    failure_count: int = 0
    audit_events_count: int = 0
    findings: List[Dict[str, Any]] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)
    retention_days: Optional[int] = None  # auditor-ready: how long to retain
    signed_at: Optional[str] = None
    signature: Optional[str] = None  # HMAC-SHA256 hex of canonical JSON


def _load_audit_count(audit_path: Optional[Path]) -> int:
    if not audit_path or not audit_path.is_file():
        return 0
    count = 0
    try:
        with audit_path.open("r", encoding="utf-8") as f:
            for _ in f:
                count += 1
                if count > 100_000:
                    break
    except Exception:
        pass
    return count


def generate_report(
    framework: str,
    run_meta: Optional[Dict[str, Any]] = None,
    audit_path: Optional[Path] = None,
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
) -> ComplianceReport:
    """Generate a compliance report from run metadata and audit log."""
    now = utc_now().isoformat()
    period_start = period_start or now[:10]
    period_end = period_end or now[:10]
    run_count = (run_meta or {}).get("run_count", 0)
    failure_count = (run_meta or {}).get("failure_count", 0)
    audit_events_count = _load_audit_count(audit_path)
    findings: List[Dict[str, Any]] = []
    if failure_count > 0:
        findings.append({"severity": "medium", "rule": "run_failures", "count": failure_count})
    return ComplianceReport(
        framework=framework,
        period_start=period_start,
        period_end=period_end,
        generated_at=now,
        run_count=run_count,
        failure_count=failure_count,
        audit_events_count=audit_events_count,
        findings=findings,
        meta={"run_meta": run_meta or {}},
    )


def sign_report(payload: Dict[str, Any], key: str) -> str:
    """Return HMAC-SHA256 hex signature of canonical JSON payload (auditor-ready)."""
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hmac.new(key.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def write_report(
    report: ComplianceReport,
    path: Path,
    *,
    sign_key: Optional[str] = None,
    retention_days: Optional[int] = None,
) -> Path:
    """Write report to JSON file; optionally add signature and retention metadata (auditor-ready)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if retention_days is not None:
        report.retention_days = retention_days
    payload = asdict(report)
    if sign_key:
        report.signed_at = utc_now().isoformat()
        report.signature = sign_report(payload, sign_key)
        payload = asdict(report)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def build_auditor_package(
    report: ComplianceReport,
    report_path: Path,
    out_zip: Path,
    *,
    include_audit_path: Optional[Path] = None,
    retention_days: Optional[int] = None,
) -> Path:
    """Build an auditor-ready zip: report JSON + manifest (chain of custody). Optional: include audit log excerpt."""
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "package_type": "waveos_compliance_auditor",
        "framework": report.framework,
        "period_start": report.period_start,
        "period_end": report.period_end,
        "generated_at": report.generated_at,
        "retention_days": retention_days or report.retention_days,
        "signed_at": report.signed_at,
        "contents": ["report.json"],
    }
    if include_audit_path and include_audit_path.is_file():
        manifest["contents"].append("audit_excerpt.jsonl")
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("report.json", report_path.read_text(encoding="utf-8"))
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, default=str) + "\n")
        if include_audit_path and include_audit_path.is_file():
            lines: List[str] = []
            with include_audit_path.open("r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i >= 10_000:
                        break
                    lines.append(line)
            zf.writestr("audit_excerpt.jsonl", "".join(lines))
    logger.info("Wrote auditor package to %s", out_zip)
    return out_zip
