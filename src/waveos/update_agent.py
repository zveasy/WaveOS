from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from waveos.bundle import (
    bundle_has_encrypted_artifacts,
    decrypt_bundle_artifacts,
    verify_manifest,
)
from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.update_agent")


def _change_log_path(state_dir: Path) -> Path:
    return state_dir / "deployment_changes.jsonl"


@dataclass
class BundleState:
    active_bundle_id: Optional[str] = None
    last_updated_at: Optional[str] = None
    canary_bundle_id: Optional[str] = None  # when canary is staged

    def to_dict(self) -> dict:
        return {
            "active_bundle_id": self.active_bundle_id,
            "last_updated_at": self.last_updated_at,
            "canary_bundle_id": self.canary_bundle_id,
        }


def _state_path(state_dir: Path) -> Path:
    return state_dir / "state.json"


def load_state(state_dir: Path) -> BundleState:
    path = _state_path(state_dir)
    if not path.exists():
        return BundleState()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return BundleState(
        active_bundle_id=payload.get("active_bundle_id"),
        last_updated_at=payload.get("last_updated_at"),
        canary_bundle_id=payload.get("canary_bundle_id"),
    )


def save_state(state_dir: Path, state: BundleState) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    _state_path(state_dir).write_text(json.dumps(state.to_dict(), indent=2) + "\n", encoding="utf-8")


def _install_to_dir(
    bundle_dir: Path,
    target_dir: Path,
    hmac_key: Optional[str] = None,
    decryption_key: Optional[str] = None,
    allowed_install_root: Optional[Path] = None,
) -> Optional[str]:
    """Copy bundle to target_dir; verify manifest if hmac_key set; decrypt artifacts if encrypted and key given. Returns bundle_id.
    If allowed_install_root is set, target_dir must resolve to a path under it (path traversal protection).
    """
    if hmac_key and not verify_manifest(bundle_dir, hmac_key):
        raise ValueError("Bundle manifest signature verification failed (wrong or missing HMAC key)")
    target_resolved = target_dir.resolve()
    if allowed_install_root is not None:
        root_resolved = allowed_install_root.resolve()
        try:
            target_resolved.relative_to(root_resolved)
        except ValueError:
            raise ValueError(
                f"Bundle install target {target_resolved} is not under allowed root {root_resolved}. "
                "Refusing to install to avoid overwriting system paths."
            )
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(bundle_dir, target_dir)
    if bundle_has_encrypted_artifacts(target_dir) and decryption_key:
        if not decrypt_bundle_artifacts(target_dir, decryption_key):
            raise ValueError("Bundle has encrypted artifacts but decryption failed (check WAVEOS_ENCRYPTION_KEY)")
    manifest_path = bundle_dir / "bundle.json"
    if manifest_path.exists():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        return payload.get("bundle_id")
    return None


def install_bundle(
    bundle_dir: Path,
    active_dir: Path,
    history_dir: Path,
    state_dir: Path,
    hmac_key: Optional[str] = None,
    canary_percent: Optional[int] = None,
    canary_dir: Optional[Path] = None,
    decryption_key: Optional[str] = None,
) -> None:
    """Install bundle to active (or to canary if canary_percent < 100 and canary_dir set). Decrypt artifacts if encrypted and decryption_key set."""
    if not bundle_dir.is_dir():
        raise ValueError(f"Bundle directory does not exist: {bundle_dir}")
    history_dir.mkdir(parents=True, exist_ok=True)
    use_canary = (
        canary_percent is not None
        and canary_dir is not None
        and 0 <= canary_percent < 100
    )
    if use_canary:
        canary_dir.mkdir(parents=True, exist_ok=True)
        root = active_dir.resolve().parent
        bundle_id = _install_to_dir(bundle_dir, canary_dir, hmac_key, decryption_key, allowed_install_root=root)
        state = load_state(state_dir)
        state.canary_bundle_id = bundle_id
        save_state(state_dir, state)
        try:
            from waveos.change_log import append_change_log
            append_change_log(_change_log_path(state_dir), "install_canary", bundle_id=bundle_id)
        except Exception:
            pass
        logger.info("Bundle %s installed to canary; run promote to activate", bundle_id)
        return
    if active_dir.exists():
        timestamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
        archived = history_dir / f"bundle_{timestamp}"
        if archived.exists():
            shutil.rmtree(archived)
        shutil.move(str(active_dir), str(archived))
    root = active_dir.resolve().parent
    bundle_id = _install_to_dir(bundle_dir, active_dir, hmac_key, decryption_key, allowed_install_root=root)
    state = BundleState(active_bundle_id=bundle_id, last_updated_at=utc_now().isoformat())
    save_state(state_dir, state)
    try:
        from waveos.change_log import append_change_log
        append_change_log(_change_log_path(state_dir), "install", bundle_id=bundle_id)
    except Exception:
        pass
    logger.info("Bundle %s installed to active", bundle_id)


def install_bundle_from_cache(
    cache_dir: Path,
    bundle_id: str,
    active_dir: Path,
    history_dir: Path,
    state_dir: Path,
    hmac_key: Optional[str] = None,
    canary_percent: Optional[int] = None,
    canary_dir: Optional[Path] = None,
    decryption_key: Optional[str] = None,
) -> None:
    """Install bundle from offline cache (air-gapped). Resolves bundle_dir = cache_dir / bundle_id."""
    bundle_dir = cache_dir / bundle_id
    if not bundle_dir.is_dir():
        for sub in cache_dir.iterdir():
            if sub.is_dir():
                m = sub / "bundle.json"
                if m.is_file():
                    try:
                        payload = json.loads(m.read_text(encoding="utf-8"))
                        if payload.get("bundle_id") == bundle_id:
                            bundle_dir = sub
                            break
                    except (OSError, json.JSONDecodeError) as exc:
                        logger.debug("Skip cache entry %s: %s", sub, type(exc).__name__)
                        continue
    if not bundle_dir.is_dir():
        raise ValueError(f"Bundle {bundle_id} not found in cache {cache_dir}")
    install_bundle(
        bundle_dir, active_dir, history_dir, state_dir,
        hmac_key=hmac_key,
        canary_percent=canary_percent,
        canary_dir=canary_dir,
        decryption_key=decryption_key,
    )


def promote_canary_bundle(
    canary_dir: Path,
    active_dir: Path,
    history_dir: Path,
    state_dir: Path,
) -> None:
    """Promote canary bundle to active (after validation)."""
    if not canary_dir.is_dir():
        raise ValueError("No canary bundle to promote")
    history_dir.mkdir(parents=True, exist_ok=True)
    if active_dir.exists():
        timestamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
        archived = history_dir / f"bundle_{timestamp}"
        if archived.exists():
            shutil.rmtree(archived)
        shutil.move(str(active_dir), str(archived))
    shutil.move(str(canary_dir), str(active_dir))
    bundle_id = None
    manifest_path = active_dir / "bundle.json"
    if manifest_path.exists():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        bundle_id = payload.get("bundle_id")
    state = load_state(state_dir)
    state.active_bundle_id = bundle_id
    state.last_updated_at = utc_now().isoformat()
    state.canary_bundle_id = None
    save_state(state_dir, state)
    try:
        from waveos.change_log import append_change_log
        append_change_log(_change_log_path(state_dir), "promote", bundle_id=bundle_id)
    except Exception:
        pass
    logger.info("Canary promoted to active: %s", bundle_id)


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
    try:
        from waveos.change_log import append_change_log
        append_change_log(_change_log_path(state_dir), "rollback", bundle_id=bundle_id)
    except Exception:
        pass
    logger.info("Rolled back to bundle %s", bundle_id)
