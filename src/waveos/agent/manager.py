"""Agent manager — orchestrates the deployment lifecycle."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.agent.state_machine import AgentState, AgentStateMachine
from waveos.agent.evidence import collect_deployment_evidence
from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.agent.manager")


@dataclass
class AgentConfig:
    """Configuration for the agent."""
    base_dir: Path = Path("out/agent")
    apps_dir: Path = Path("/opt/waveos/apps")
    state_file: str = "agent_state.json"
    log_file: str = "agent_events.jsonl"
    health_check_interval_sec: int = 30
    auto_rollback: bool = True
    health_score_threshold: float = 50.0
    max_crash_count: int = 3
    crash_window_sec: int = 300

    def state_path(self) -> Path:
        return self.base_dir / self.state_file

    def log_path(self) -> Path:
        return self.base_dir / self.log_file

    def app_version_dir(self, app_name: str, version: str) -> Path:
        return self.apps_dir / app_name / version


class AgentManager:
    """Manages the full agent deployment lifecycle."""

    def __init__(self, config: Optional[AgentConfig] = None) -> None:
        self.config = config or AgentConfig()
        self.config.base_dir.mkdir(parents=True, exist_ok=True)
        self.sm = AgentStateMachine.load_state(self.config.state_path())
        self._active_bundle: Optional[str] = None
        self._load_active_bundle()

    def _load_active_bundle(self) -> None:
        active_path = self.config.base_dir / "active_bundle.json"
        if active_path.exists():
            try:
                data = json.loads(active_path.read_text(encoding="utf-8"))
                self._active_bundle = data.get("bundle_id")
            except (json.JSONDecodeError, OSError):
                pass

    def _save_active_bundle(self, bundle_id: str) -> None:
        self._active_bundle = bundle_id
        path = self.config.base_dir / "active_bundle.json"
        path.write_text(json.dumps({"bundle_id": bundle_id, "activated_at": utc_now().isoformat()}, indent=2) + "\n", encoding="utf-8")

    def _append_log(self, event: Dict[str, Any]) -> None:
        log_path = self.config.log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=str) + "\n")

    def _save(self) -> None:
        self.sm.save_state(self.config.state_path())

    def status(self) -> Dict[str, Any]:
        """Return agent status."""
        return {
            "state": self.sm.state.value,
            "active_bundle": self._active_bundle,
            "base_dir": str(self.config.base_dir),
            "apps_dir": str(self.config.apps_dir),
            "auto_rollback": self.config.auto_rollback,
            "history_count": len(self.sm.history),
        }

    def install_bootstrap(self, target_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Bootstrap agent installation: create directory structure."""
        base = target_dir or self.config.base_dir
        base.mkdir(parents=True, exist_ok=True)
        (base / "bundles").mkdir(exist_ok=True)
        (base / "logs").mkdir(exist_ok=True)
        (base / "evidence").mkdir(exist_ok=True)
        self.config.apps_dir.mkdir(parents=True, exist_ok=True)
        self._append_log({"event": "bootstrap", "timestamp": utc_now().isoformat(), "base_dir": str(base)})
        self._save()
        return {"status": "ok", "base_dir": str(base), "apps_dir": str(self.config.apps_dir)}

    def activate_bundle(
        self,
        bundle_dir: Path,
        bundle_id: str = "",
        app_name: str = "default",
        version: str = "latest",
        hmac_key: Optional[str] = None,
        skip_preflight: bool = False,
    ) -> Dict[str, Any]:
        """Full activation lifecycle: verify -> preflight -> install -> activate."""
        results: Dict[str, Any] = {"bundle_dir": str(bundle_dir), "bundle_id": bundle_id, "steps": []}

        # VERIFY
        if not self.sm.transition(AgentState.VERIFY, reason=f"Activating bundle {bundle_id}"):
            if self.sm.state != AgentState.IDLE:
                self.sm.force_state(AgentState.IDLE, reason="Reset for activation")
            self.sm.transition(AgentState.VERIFY, reason=f"Activating bundle {bundle_id}")

        manifest_path = bundle_dir / "bundle.json"
        if not manifest_path.exists():
            results["steps"].append({"step": "verify", "ok": False, "error": "No manifest"})
            self.sm.transition(AgentState.QUARANTINE, reason="No manifest")
            self._save()
            return results

        if hmac_key:
            from waveos.bundle import verify_manifest
            if not verify_manifest(bundle_dir, hmac_key):
                results["steps"].append({"step": "verify", "ok": False, "error": "Signature verification failed"})
                self.sm.transition(AgentState.QUARANTINE, reason="Signature failed")
                self._save()
                return results
        results["steps"].append({"step": "verify", "ok": True})

        # PREFLIGHT
        if not skip_preflight:
            self.sm.transition(AgentState.PREFLIGHT, reason="Running preflight checks")
            try:
                from waveos.compat import run_preflight
                preflight_result = run_preflight(bundle_dir)
                results["steps"].append({"step": "preflight", "ok": preflight_result["outcome"] != "block", "details": preflight_result})
                if preflight_result["outcome"] == "block":
                    self.sm.transition(AgentState.QUARANTINE, reason="Preflight blocked")
                    self._save()
                    return results
            except ImportError:
                results["steps"].append({"step": "preflight", "ok": True, "details": "compat module not available, skipped"})
        else:
            results["steps"].append({"step": "preflight", "ok": True, "details": "skipped"})

        # INSTALL (side-by-side)
        self.sm.transition(AgentState.INSTALL, reason="Installing side-by-side")
        install_dir = self.config.app_version_dir(app_name, version)
        install_dir.mkdir(parents=True, exist_ok=True)
        try:
            if install_dir.exists():
                shutil.rmtree(install_dir)
            shutil.copytree(bundle_dir, install_dir)
            results["steps"].append({"step": "install", "ok": True, "install_dir": str(install_dir)})
        except (OSError, shutil.Error) as exc:
            results["steps"].append({"step": "install", "ok": False, "error": str(exc)})
            self.sm.transition(AgentState.ROLLBACK, reason=f"Install failed: {exc}")
            self._save()
            return results

        # ACTIVATE
        self.sm.transition(AgentState.ACTIVATE, reason=f"Activating {bundle_id}")
        self._save_active_bundle(bundle_id or version)
        results["steps"].append({"step": "activate", "ok": True, "bundle_id": bundle_id or version})

        # -> MONITOR
        self.sm.transition(AgentState.MONITOR, reason="Activation complete, monitoring")
        self._save()

        evidence = collect_deployment_evidence(
            bundle_id=bundle_id or version,
            steps=results["steps"],
            agent_state=self.sm.state.value,
        )
        evidence_dir = self.config.base_dir / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        evidence_path = evidence_dir / f"deploy_{bundle_id or version}.json"
        evidence_path.write_text(json.dumps(evidence.to_dict(), indent=2) + "\n", encoding="utf-8")
        results["evidence_path"] = str(evidence_path)

        self._append_log({"event": "activate", "timestamp": utc_now().isoformat(), "bundle_id": bundle_id, "results": results})
        return results

    def rollback(self, app_name: str = "default") -> Dict[str, Any]:
        """Rollback to previous version."""
        if not self.sm.can_transition(AgentState.ROLLBACK):
            self.sm.force_state(AgentState.ROLLBACK, reason="Forced rollback")
        else:
            self.sm.transition(AgentState.ROLLBACK, reason="Rollback requested")

        app_dir = self.config.apps_dir / app_name
        if not app_dir.exists():
            self.sm.transition(AgentState.IDLE, reason="No versions to rollback to")
            self._save()
            return {"ok": False, "error": "No app versions found"}

        versions = sorted([d for d in app_dir.iterdir() if d.is_dir()])
        if len(versions) < 2:
            self.sm.transition(AgentState.IDLE, reason="Only one version, cannot rollback")
            self._save()
            return {"ok": False, "error": "No previous version available"}

        current = versions[-1]
        previous = versions[-2]
        shutil.rmtree(current)

        manifest_path = previous / "bundle.json"
        bundle_id = ""
        if manifest_path.exists():
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                bundle_id = data.get("bundle_id", previous.name)
            except (json.JSONDecodeError, OSError):
                bundle_id = previous.name
        else:
            bundle_id = previous.name

        self._save_active_bundle(bundle_id)
        self.sm.transition(AgentState.IDLE, reason=f"Rolled back to {bundle_id}")
        self._save()
        self._append_log({"event": "rollback", "timestamp": utc_now().isoformat(), "rolled_back_to": bundle_id})
        return {"ok": True, "rolled_back_to": bundle_id, "removed_version": current.name}

    def get_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent agent event logs."""
        log_path = self.config.log_path()
        if not log_path.exists():
            return []
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        entries = []
        for line in lines[-limit:]:
            if line.strip():
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    entries.append({"raw": line})
        return entries
