from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from waveos.utils import utc_now


@dataclass
class BundleArtifact:
    path: str
    sha256: str
    size_bytes: int


@dataclass
class BundleMetadata:
    waveos_version: str
    policy_version: str
    bundle_id: str
    created_at: str
    artifacts: List[BundleArtifact]
    identity: dict | None = None
    environment: str | None = None
    feature_flags: dict | None = None

    def to_dict(self) -> dict:
        return {
            "waveos_version": self.waveos_version,
            "policy_version": self.policy_version,
            "bundle_id": self.bundle_id,
            "created_at": self.created_at,
            "artifacts": [artifact.__dict__ for artifact in self.artifacts],
            "identity": self.identity,
            "environment": self.environment,
            "feature_flags": self.feature_flags,
        }


def _iter_files(bundle_dir: Path, exclude: Iterable[str]) -> List[Path]:
    excluded = {bundle_dir / name for name in exclude}
    files: List[Path] = []
    for path in bundle_dir.rglob("*"):
        if path.is_dir():
            continue
        if path in excluded:
            continue
        files.append(path)
    return sorted(files)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    bundle_dir: Path,
    waveos_version: str,
    policy_version: str,
    bundle_id: str,
    identity: dict | None = None,
    environment: str | None = None,
    feature_flags: dict | None = None,
    exclude: Iterable[str] = ("bundle.json", "bundle.sig"),
) -> BundleMetadata:
    artifacts: List[BundleArtifact] = []
    for path in _iter_files(bundle_dir, exclude):
        artifacts.append(
            BundleArtifact(
                path=str(path.relative_to(bundle_dir)),
                sha256=_sha256(path),
                size_bytes=path.stat().st_size,
            )
        )
    return BundleMetadata(
        waveos_version=waveos_version,
        policy_version=policy_version,
        bundle_id=bundle_id,
        created_at=utc_now().isoformat(),
        artifacts=artifacts,
        identity=identity,
        environment=environment,
        feature_flags=feature_flags,
    )


def write_manifest(bundle_dir: Path, manifest: BundleMetadata) -> Path:
    path = bundle_dir / "bundle.json"
    path.write_text(json.dumps(manifest.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def sign_manifest(manifest_path: Path, hmac_key: str) -> str:
    payload = manifest_path.read_bytes()
    signature = hmac.new(hmac_key.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    sig_path = manifest_path.parent / "bundle.sig"
    sig_path.write_text(signature + "\n", encoding="utf-8")
    return signature


def verify_manifest(bundle_dir: Path, hmac_key: str) -> bool:
    manifest_path = bundle_dir / "bundle.json"
    sig_path = bundle_dir / "bundle.sig"
    if not manifest_path.exists() or not sig_path.exists():
        return False
    expected = sig_path.read_text(encoding="utf-8").strip()
    actual = hmac.new(hmac_key.encode("utf-8"), manifest_path.read_bytes(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, actual)
