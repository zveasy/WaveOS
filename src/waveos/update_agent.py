from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from waveos.bundle import verify_manifest
from waveos.utils import utc_now


@dataclass
class BundleState:
    active_bundle_id: Optional[str] = None
    last_updated_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "active_bundle_id": self.active_bundle_id,
            "last_updated_at": self.last_updated_at,
        }


def _state_path(state_dir: Path) -> Path:
    return state_dir / "state.json"


def load_state(state_dir: Path) -> BundleState:
    path = _state_path(state_dir)
    if not path.exists():
        return BundleState()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return BundleState(**payload)


def save_state(state_dir: Path, state: BundleState) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    _state_path(state_dir).write_text(json.dumps(state.to_dict(), indent=2) + "\n", encoding="utf-8")


def install_bundle(
    bundle_dir: Path,
    active_dir: Path,
    history_dir: Path,
    state_dir: Path,
    hmac_key: Optional[str] = None,
) -> None:
    if hmac_key and not verify_manifest(bundle_dir, hmac_key):
        raise ValueError("Bundle signature verification failed")
    history_dir.mkdir(parents=True, exist_ok=True)
    if active_dir.exists():
        timestamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
        archived = history_dir / f"bundle_{timestamp}"
        if archived.exists():
            shutil.rmtree(archived)
        shutil.move(str(active_dir), str(archived))
    if active_dir.exists():
        shutil.rmtree(active_dir)
    shutil.copytree(bundle_dir, active_dir)
    bundle_id = None
    manifest_path = bundle_dir / "bundle.json"
    if manifest_path.exists():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        bundle_id = payload.get("bundle_id")
    state = BundleState(active_bundle_id=bundle_id, last_updated_at=utc_now().isoformat())
    save_state(state_dir, state)


def rollback_bundle(active_dir: Path, history_dir: Path, state_dir: Path) -> None:
    if not history_dir.exists():
        raise ValueError("No bundle history available")
    candidates = sorted([path for path in history_dir.iterdir() if path.is_dir()])
    if not candidates:
        raise ValueError("No bundle history available")
    latest = candidates[-1]
    if active_dir.exists():
        shutil.rmtree(active_dir)
    shutil.move(str(latest), str(active_dir))
    bundle_id = None
    manifest_path = active_dir / "bundle.json"
    if manifest_path.exists():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        bundle_id = payload.get("bundle_id")
    state = BundleState(active_bundle_id=bundle_id, last_updated_at=utc_now().isoformat())
    save_state(state_dir, state)
