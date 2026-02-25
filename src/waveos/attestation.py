"""WaveOS Attestation — build provenance and supply-chain attestation."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.attestation")


@dataclass
class BuildProvenance:
    """Build provenance record for supply-chain traceability."""
    build_id: str = ""
    commit_sha: str = ""
    branch: str = ""
    builder_identity: str = ""
    ci_run_id: str = ""
    ci_run_url: str = ""
    ci_provider: str = ""
    build_timestamp: str = ""
    source_repo: str = ""
    inputs_digest: str = ""
    build_command: str = ""
    reproducible: bool = False

    def to_dict(self) -> dict:
        return {
            "build_id": self.build_id,
            "commit_sha": self.commit_sha,
            "branch": self.branch,
            "builder_identity": self.builder_identity,
            "ci_run_id": self.ci_run_id,
            "ci_run_url": self.ci_run_url,
            "ci_provider": self.ci_provider,
            "build_timestamp": self.build_timestamp,
            "source_repo": self.source_repo,
            "inputs_digest": self.inputs_digest,
            "build_command": self.build_command,
            "reproducible": self.reproducible,
        }

    @classmethod
    def from_dict(cls, d: dict) -> BuildProvenance:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


@dataclass
class Attestation:
    """Full attestation envelope (in-toto-like)."""
    attestation_type: str = "https://waveos.io/attestation/v1"
    subject: List[Dict[str, Any]] = field(default_factory=list)
    provenance: Optional[BuildProvenance] = None
    materials: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "attestation_type": self.attestation_type,
            "subject": self.subject,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "materials": self.materials,
            "metadata": self.metadata,
            "timestamp": self.timestamp or utc_now().isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> Attestation:
        prov = BuildProvenance.from_dict(d["provenance"]) if d.get("provenance") else None
        return cls(
            attestation_type=d.get("attestation_type", "https://waveos.io/attestation/v1"),
            subject=d.get("subject", []),
            provenance=prov,
            materials=d.get("materials", []),
            metadata=d.get("metadata", {}),
            timestamp=d.get("timestamp", ""),
        )


def _git_info(cwd: str = ".") -> Dict[str, str]:
    """Gather git info from current directory."""
    info: Dict[str, str] = {}
    for key, cmd in [
        ("commit_sha", ["git", "rev-parse", "HEAD"]),
        ("branch", ["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        ("source_repo", ["git", "config", "--get", "remote.origin.url"]),
    ]:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=5)
            if result.returncode == 0:
                info[key] = result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return info


def _ci_info() -> Dict[str, str]:
    """Detect CI environment and extract run metadata."""
    info: Dict[str, str] = {}
    if os.getenv("GITHUB_ACTIONS"):
        info["ci_provider"] = "github-actions"
        info["ci_run_id"] = os.getenv("GITHUB_RUN_ID", "")
        info["ci_run_url"] = f"{os.getenv('GITHUB_SERVER_URL', 'https://github.com')}/{os.getenv('GITHUB_REPOSITORY', '')}/actions/runs/{os.getenv('GITHUB_RUN_ID', '')}"
        info["builder_identity"] = os.getenv("GITHUB_ACTOR", "")
    elif os.getenv("JENKINS_URL"):
        info["ci_provider"] = "jenkins"
        info["ci_run_id"] = os.getenv("BUILD_ID", "")
        info["ci_run_url"] = os.getenv("BUILD_URL", "")
        info["builder_identity"] = os.getenv("BUILD_USER_ID", "")
    elif os.getenv("GITLAB_CI"):
        info["ci_provider"] = "gitlab-ci"
        info["ci_run_id"] = os.getenv("CI_PIPELINE_ID", "")
        info["ci_run_url"] = os.getenv("CI_PIPELINE_URL", "")
        info["builder_identity"] = os.getenv("GITLAB_USER_LOGIN", "")
    else:
        info["ci_provider"] = "local"
        info["builder_identity"] = os.getenv("USER", os.getenv("USERNAME", "unknown"))
    return info


def generate_attestation(
    bundle_dir: Path,
    bundle_id: str = "",
    build_command: str = "",
    materials: Optional[List[Dict[str, str]]] = None,
) -> Attestation:
    """Generate build provenance attestation for a bundle."""
    from waveos.bundle import _iter_files, _sha256

    git = _git_info(str(bundle_dir))
    ci = _ci_info()
    build_id = f"build-{utc_now().strftime('%Y%m%d%H%M%S')}-{git.get('commit_sha', 'unknown')[:8]}"

    subject: List[Dict[str, Any]] = []
    for path in _iter_files(bundle_dir, ("bundle.json", "bundle.sig", "checksums.txt", "attestation.json")):
        rel = str(path.relative_to(bundle_dir))
        subject.append({"name": rel, "digest": {"sha256": _sha256(path)}})

    inputs_digest = hashlib.sha256(json.dumps(sorted([s["digest"]["sha256"] for s in subject])).encode()).hexdigest()

    provenance = BuildProvenance(
        build_id=build_id,
        commit_sha=git.get("commit_sha", ""),
        branch=git.get("branch", ""),
        builder_identity=ci.get("builder_identity", ""),
        ci_run_id=ci.get("ci_run_id", ""),
        ci_run_url=ci.get("ci_run_url", ""),
        ci_provider=ci.get("ci_provider", "local"),
        build_timestamp=utc_now().isoformat(),
        source_repo=git.get("source_repo", ""),
        inputs_digest=inputs_digest,
        build_command=build_command,
    )

    return Attestation(
        subject=subject,
        provenance=provenance,
        materials=materials or [],
        metadata={"bundle_id": bundle_id},
        timestamp=utc_now().isoformat(),
    )


def write_attestation(bundle_dir: Path, attestation: Attestation) -> Path:
    """Write attestation to bundle directory."""
    path = bundle_dir / "attestation.json"
    path.write_text(json.dumps(attestation.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def read_attestation(bundle_dir: Path) -> Optional[Attestation]:
    """Read attestation from bundle directory."""
    path = bundle_dir / "attestation.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Attestation.from_dict(data)
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Failed to read attestation: %s", exc)
        return None
