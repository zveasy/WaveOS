"""WaveOS Bundle V2 — enhanced manifest with targets, payload, runtimes, services, bridge, rollback, and policy fields."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.bundle import BundleArtifact, _iter_files, _sha256, sign_manifest, verify_manifest
from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.bundle_v2")


@dataclass
class TargetConstraint:
    """OS/arch/CPU constraints for a bundle target."""
    os: str = ""              # e.g. "linux", "windows"
    os_version: str = ""      # e.g. ">=20.04"
    arch: str = ""            # e.g. "x86_64", "aarch64"
    cpu_features: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"os": self.os, "os_version": self.os_version, "arch": self.arch, "cpu_features": self.cpu_features}

    @classmethod
    def from_dict(cls, d: dict) -> TargetConstraint:
        return cls(os=d.get("os", ""), os_version=d.get("os_version", ""), arch=d.get("arch", ""), cpu_features=d.get("cpu_features", []))


@dataclass
class PayloadEntry:
    """A file in the bundle payload with install metadata."""
    source: str          # relative path in bundle
    destination: str     # install location on target
    permissions: str = "0644"
    sha256: str = ""
    size_bytes: int = 0

    def to_dict(self) -> dict:
        return {"source": self.source, "destination": self.destination, "permissions": self.permissions, "sha256": self.sha256, "size_bytes": self.size_bytes}

    @classmethod
    def from_dict(cls, d: dict) -> PayloadEntry:
        return cls(source=d.get("source", ""), destination=d.get("destination", ""), permissions=d.get("permissions", "0644"), sha256=d.get("sha256", ""), size_bytes=d.get("size_bytes", 0))


@dataclass
class RuntimeSpec:
    """Dependency/isolation strategy for bundle runtime."""
    strategy: str = "bundled"  # bundled | side_by_side | container | vm
    runtime_version: str = ""
    dependencies: List[str] = field(default_factory=list)
    isolation: str = "none"   # none | namespace | container | vm

    def to_dict(self) -> dict:
        return {"strategy": self.strategy, "runtime_version": self.runtime_version, "dependencies": self.dependencies, "isolation": self.isolation}

    @classmethod
    def from_dict(cls, d: dict) -> RuntimeSpec:
        return cls(strategy=d.get("strategy", "bundled"), runtime_version=d.get("runtime_version", ""), dependencies=d.get("dependencies", []), isolation=d.get("isolation", "none"))


@dataclass
class ServiceSpec:
    """Service to run from the bundle, with ordering and health checks."""
    name: str
    command: str
    order: int = 0
    health_check: str = ""       # command or URL to check health
    health_interval_sec: int = 30
    restart_policy: str = "on-failure"  # on-failure | always | never
    depends_on: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"name": self.name, "command": self.command, "order": self.order, "health_check": self.health_check, "health_interval_sec": self.health_interval_sec, "restart_policy": self.restart_policy, "depends_on": self.depends_on}

    @classmethod
    def from_dict(cls, d: dict) -> ServiceSpec:
        return cls(name=d.get("name", ""), command=d.get("command", ""), order=d.get("order", 0), health_check=d.get("health_check", ""), health_interval_sec=d.get("health_interval_sec", 30), restart_policy=d.get("restart_policy", "on-failure"), depends_on=d.get("depends_on", []))


@dataclass
class BridgeSpec:
    """Legacy bridge wiring configuration."""
    mode: str = "mirror"  # mirror | canary | cutover
    legacy_service: str = ""
    adapter_service: str = ""
    routing_rules: Dict[str, Any] = field(default_factory=dict)
    validation_checks: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"mode": self.mode, "legacy_service": self.legacy_service, "adapter_service": self.adapter_service, "routing_rules": self.routing_rules, "validation_checks": self.validation_checks}

    @classmethod
    def from_dict(cls, d: dict) -> BridgeSpec:
        return cls(mode=d.get("mode", "mirror"), legacy_service=d.get("legacy_service", ""), adapter_service=d.get("adapter_service", ""), routing_rules=d.get("routing_rules", {}), validation_checks=d.get("validation_checks", []))


@dataclass
class RollbackSpec:
    """Rollback configuration."""
    previous_versions: List[str] = field(default_factory=list)
    conditions: List[str] = field(default_factory=list)  # e.g. ["crash_loop", "health_below_50", "latency_regression"]
    auto_rollback: bool = True

    def to_dict(self) -> dict:
        return {"previous_versions": self.previous_versions, "conditions": self.conditions, "auto_rollback": self.auto_rollback}

    @classmethod
    def from_dict(cls, d: dict) -> RollbackSpec:
        return cls(previous_versions=d.get("previous_versions", []), conditions=d.get("conditions", []), auto_rollback=d.get("auto_rollback", True))


@dataclass
class PolicyGate:
    """Policy gate required to activate a bundle."""
    name: str
    type: str = "health_score"  # health_score | approval | check_passed
    threshold: float = 70.0
    required: bool = True

    def to_dict(self) -> dict:
        return {"name": self.name, "type": self.type, "threshold": self.threshold, "required": self.required}

    @classmethod
    def from_dict(cls, d: dict) -> PolicyGate:
        return cls(name=d.get("name", ""), type=d.get("type", "health_score"), threshold=d.get("threshold", 70.0), required=d.get("required", True))


@dataclass
class BundleManifestV2:
    """V2 bundle manifest with full deployment metadata."""
    bundle_id: str
    version: str
    build_commit: str = ""
    build_time: str = ""
    waveos_version: str = ""
    policy_version: str = ""
    targets: List[TargetConstraint] = field(default_factory=list)
    payload: List[PayloadEntry] = field(default_factory=list)
    runtimes: RuntimeSpec = field(default_factory=RuntimeSpec)
    services: List[ServiceSpec] = field(default_factory=list)
    bridge: Optional[BridgeSpec] = None
    rollback: RollbackSpec = field(default_factory=RollbackSpec)
    policy: List[PolicyGate] = field(default_factory=list)
    artifacts: List[BundleArtifact] = field(default_factory=list)
    checksums: Dict[str, str] = field(default_factory=dict)
    attestation: Optional[Dict[str, Any]] = None
    sbom_ref: str = ""
    channel: str = "dev"   # dev | staging | prod | mission-critical
    identity: Optional[Dict[str, Any]] = None
    environment: str = ""
    feature_flags: Dict[str, Any] = field(default_factory=dict)
    encrypted_artifacts: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "manifest_version": "2.0",
            "bundle_id": self.bundle_id,
            "version": self.version,
            "build_commit": self.build_commit,
            "build_time": self.build_time,
            "waveos_version": self.waveos_version,
            "policy_version": self.policy_version,
            "targets": [t.to_dict() for t in self.targets],
            "payload": [p.to_dict() for p in self.payload],
            "runtimes": self.runtimes.to_dict(),
            "services": [s.to_dict() for s in self.services],
            "bridge": self.bridge.to_dict() if self.bridge else None,
            "rollback": self.rollback.to_dict(),
            "policy": [g.to_dict() for g in self.policy],
            "artifacts": [{"path": a.path, "sha256": a.sha256, "size_bytes": a.size_bytes} for a in self.artifacts],
            "checksums": self.checksums,
            "attestation": self.attestation,
            "sbom_ref": self.sbom_ref,
            "channel": self.channel,
            "identity": self.identity,
            "environment": self.environment,
            "feature_flags": self.feature_flags,
            "encrypted_artifacts": self.encrypted_artifacts,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> BundleManifestV2:
        return cls(
            bundle_id=d.get("bundle_id", ""),
            version=d.get("version", ""),
            build_commit=d.get("build_commit", ""),
            build_time=d.get("build_time", ""),
            waveos_version=d.get("waveos_version", ""),
            policy_version=d.get("policy_version", ""),
            targets=[TargetConstraint.from_dict(t) for t in d.get("targets", [])],
            payload=[PayloadEntry.from_dict(p) for p in d.get("payload", [])],
            runtimes=RuntimeSpec.from_dict(d["runtimes"]) if "runtimes" in d else RuntimeSpec(),
            services=[ServiceSpec.from_dict(s) for s in d.get("services", [])],
            bridge=BridgeSpec.from_dict(d["bridge"]) if d.get("bridge") else None,
            rollback=RollbackSpec.from_dict(d["rollback"]) if "rollback" in d else RollbackSpec(),
            policy=[PolicyGate.from_dict(g) for g in d.get("policy", [])],
            artifacts=[BundleArtifact(path=a["path"], sha256=a["sha256"], size_bytes=a["size_bytes"]) for a in d.get("artifacts", [])],
            checksums=d.get("checksums", {}),
            attestation=d.get("attestation"),
            sbom_ref=d.get("sbom_ref", ""),
            channel=d.get("channel", "dev"),
            identity=d.get("identity"),
            environment=d.get("environment", ""),
            feature_flags=d.get("feature_flags", {}),
            encrypted_artifacts=d.get("encrypted_artifacts", False),
            metadata=d.get("metadata", {}),
        )


def build_manifest_v2(
    bundle_dir: Path,
    bundle_id: str,
    version: str,
    waveos_version: str = "",
    policy_version: str = "",
    targets: Optional[List[TargetConstraint]] = None,
    services: Optional[List[ServiceSpec]] = None,
    bridge: Optional[BridgeSpec] = None,
    rollback: Optional[RollbackSpec] = None,
    policy_gates: Optional[List[PolicyGate]] = None,
    runtimes: Optional[RuntimeSpec] = None,
    channel: str = "dev",
    identity: Optional[Dict[str, Any]] = None,
    environment: str = "",
    feature_flags: Optional[Dict[str, Any]] = None,
    attestation: Optional[Dict[str, Any]] = None,
    exclude: tuple = ("bundle.json", "bundle.sig", "checksums.txt"),
) -> BundleManifestV2:
    """Build V2 manifest from bundle directory contents."""
    artifacts: List[BundleArtifact] = []
    payload_entries: List[PayloadEntry] = []
    checksums: Dict[str, str] = {}

    for path in _iter_files(bundle_dir, exclude):
        rel = str(path.relative_to(bundle_dir))
        sha = _sha256(path)
        size = path.stat().st_size
        artifacts.append(BundleArtifact(path=rel, sha256=sha, size_bytes=size))
        payload_entries.append(PayloadEntry(source=rel, destination=rel, sha256=sha, size_bytes=size))
        checksums[rel] = sha

    build_commit = ""
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=str(bundle_dir), timeout=5)
        if result.returncode == 0:
            build_commit = result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return BundleManifestV2(
        bundle_id=bundle_id,
        version=version,
        build_commit=build_commit,
        build_time=utc_now().isoformat(),
        waveos_version=waveos_version,
        policy_version=policy_version,
        targets=targets or [],
        payload=payload_entries,
        runtimes=runtimes or RuntimeSpec(),
        services=services or [],
        bridge=bridge,
        rollback=rollback or RollbackSpec(),
        policy=policy_gates or [],
        artifacts=artifacts,
        checksums=checksums,
        attestation=attestation,
        channel=channel,
        identity=identity,
        environment=environment,
        feature_flags=feature_flags or {},
    )


def write_manifest_v2(bundle_dir: Path, manifest: BundleManifestV2) -> Path:
    """Write V2 manifest and checksums.txt."""
    path = bundle_dir / "bundle.json"
    path.write_text(json.dumps(manifest.to_dict(), indent=2) + "\n", encoding="utf-8")
    checksums_path = bundle_dir / "checksums.txt"
    lines = [f"{sha}  {name}" for name, sha in sorted(manifest.checksums.items())]
    checksums_path.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")
    return path


def read_manifest_v2(bundle_dir: Path) -> Optional[BundleManifestV2]:
    """Read V2 manifest from bundle directory."""
    path = bundle_dir / "bundle.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return BundleManifestV2.from_dict(data)
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Failed to read V2 manifest: %s", exc)
        return None


def inspect_bundle(bundle_dir: Path) -> Dict[str, Any]:
    """Inspect a bundle and return summary info."""
    manifest = read_manifest_v2(bundle_dir)
    if not manifest:
        return {"error": "No bundle manifest found", "path": str(bundle_dir)}
    artifact_count = len(manifest.artifacts)
    total_size = sum(a.size_bytes for a in manifest.artifacts)
    return {
        "bundle_id": manifest.bundle_id,
        "version": manifest.version,
        "manifest_version": "2.0" if manifest.targets or manifest.services else "1.0",
        "waveos_version": manifest.waveos_version,
        "policy_version": manifest.policy_version,
        "channel": manifest.channel,
        "build_commit": manifest.build_commit,
        "build_time": manifest.build_time,
        "artifact_count": artifact_count,
        "total_size_bytes": total_size,
        "targets": [t.to_dict() for t in manifest.targets],
        "services": [s.name for s in manifest.services],
        "bridge": manifest.bridge.to_dict() if manifest.bridge else None,
        "rollback": manifest.rollback.to_dict(),
        "policy_gates": [g.name for g in manifest.policy],
        "runtime_strategy": manifest.runtimes.strategy,
        "encrypted": manifest.encrypted_artifacts,
        "has_attestation": manifest.attestation is not None,
        "has_sbom": bool(manifest.sbom_ref),
    }


def verify_bundle_checksums(bundle_dir: Path) -> tuple[bool, List[str]]:
    """Verify all artifact checksums in the bundle. Returns (ok, errors)."""
    manifest = read_manifest_v2(bundle_dir)
    if not manifest:
        return False, ["No manifest found"]
    errors: List[str] = []
    for artifact in manifest.artifacts:
        path = bundle_dir / artifact.path
        if not path.exists():
            errors.append(f"Missing artifact: {artifact.path}")
            continue
        actual = _sha256(path)
        if actual != artifact.sha256:
            errors.append(f"Checksum mismatch for {artifact.path}: expected {artifact.sha256[:16]}... got {actual[:16]}...")
    return len(errors) == 0, errors


def verify_bundle_with_trust_store(bundle_dir: Path, trust_store_path: Path) -> tuple[bool, List[str]]:
    """Verify bundle using keys from a trust store directory.
    Trust store contains files named *.key with HMAC keys (one per line).
    """
    errors: List[str] = []
    manifest_path = bundle_dir / "bundle.json"
    sig_path = bundle_dir / "bundle.sig"
    if not manifest_path.exists():
        return False, ["No manifest found"]
    if not sig_path.exists():
        return False, ["No signature found"]
    if not trust_store_path.is_dir():
        return False, [f"Trust store not found: {trust_store_path}"]
    key_files = sorted(trust_store_path.glob("*.key"))
    if not key_files:
        return False, ["No keys in trust store"]
    for key_file in key_files:
        key = key_file.read_text(encoding="utf-8").strip()
        if not key:
            continue
        if verify_manifest(bundle_dir, key):
            checksum_ok, checksum_errors = verify_bundle_checksums(bundle_dir)
            if not checksum_ok:
                errors.extend(checksum_errors)
                return False, errors
            return True, []
    return False, ["Signature verification failed with all keys in trust store"]
