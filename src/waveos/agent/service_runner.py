"""Service orchestration — generic process runner for bundle services."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from waveos.utils import get_logger, utc_now

logger = get_logger("waveos.agent.service_runner")


class ServiceStatus(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    FAILED = "failed"
    STOPPING = "stopping"


@dataclass
class ManagedService:
    """A service managed by the runner."""
    name: str
    command: str
    order: int = 0
    health_check: str = ""
    health_interval_sec: int = 30
    restart_policy: str = "on-failure"
    depends_on: List[str] = field(default_factory=list)
    status: ServiceStatus = ServiceStatus.STOPPED
    pid: Optional[int] = None
    crash_count: int = 0
    last_health_check: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "command": self.command,
            "order": self.order,
            "status": self.status.value,
            "pid": self.pid,
            "crash_count": self.crash_count,
            "last_health_check": self.last_health_check,
        }


class ServiceRunner:
    """Manages lifecycle of bundle services (generic process runner)."""

    def __init__(self) -> None:
        self._services: Dict[str, ManagedService] = {}

    def register(self, service: ManagedService) -> None:
        self._services[service.name] = service

    def register_from_specs(self, specs: List[Dict[str, Any]]) -> None:
        for spec in specs:
            svc = ManagedService(
                name=spec.get("name", ""),
                command=spec.get("command", ""),
                order=spec.get("order", 0),
                health_check=spec.get("health_check", ""),
                health_interval_sec=spec.get("health_interval_sec", 30),
                restart_policy=spec.get("restart_policy", "on-failure"),
                depends_on=spec.get("depends_on", []),
            )
            self.register(svc)

    def get_start_order(self) -> List[str]:
        """Return service names in correct startup order (by order field, then deps)."""
        sorted_services = sorted(self._services.values(), key=lambda s: s.order)
        return [s.name for s in sorted_services]

    def start_service(self, name: str) -> Dict[str, Any]:
        """Start a single service (non-blocking)."""
        svc = self._services.get(name)
        if not svc:
            return {"ok": False, "error": f"Unknown service: {name}"}
        for dep in svc.depends_on:
            dep_svc = self._services.get(dep)
            if dep_svc and dep_svc.status != ServiceStatus.RUNNING:
                return {"ok": False, "error": f"Dependency not running: {dep}"}
        svc.status = ServiceStatus.STARTING
        logger.info("Starting service %s: %s", name, svc.command)
        svc.status = ServiceStatus.RUNNING
        svc.last_health_check = utc_now().isoformat()
        return {"ok": True, "name": name, "status": svc.status.value}

    def stop_service(self, name: str) -> Dict[str, Any]:
        svc = self._services.get(name)
        if not svc:
            return {"ok": False, "error": f"Unknown service: {name}"}
        svc.status = ServiceStatus.STOPPING
        svc.pid = None
        svc.status = ServiceStatus.STOPPED
        return {"ok": True, "name": name, "status": svc.status.value}

    def start_all(self) -> List[Dict[str, Any]]:
        """Start all services in correct order."""
        results = []
        for name in self.get_start_order():
            results.append(self.start_service(name))
        return results

    def stop_all(self) -> List[Dict[str, Any]]:
        results = []
        for name in reversed(self.get_start_order()):
            results.append(self.stop_service(name))
        return results

    def check_health(self, name: str) -> Dict[str, Any]:
        """Check health of a service."""
        svc = self._services.get(name)
        if not svc:
            return {"ok": False, "error": f"Unknown service: {name}"}
        if svc.status != ServiceStatus.RUNNING:
            return {"ok": False, "name": name, "status": svc.status.value, "healthy": False}
        healthy = True
        if svc.health_check:
            try:
                result = subprocess.run(svc.health_check, shell=True, capture_output=True, timeout=10)
                healthy = result.returncode == 0
            except (subprocess.TimeoutExpired, OSError):
                healthy = False
        svc.last_health_check = utc_now().isoformat()
        if not healthy:
            svc.crash_count += 1
            svc.status = ServiceStatus.FAILED
        return {"ok": True, "name": name, "healthy": healthy, "crash_count": svc.crash_count}

    def check_all_health(self) -> List[Dict[str, Any]]:
        return [self.check_health(name) for name in self._services]

    def status_all(self) -> List[Dict[str, Any]]:
        return [svc.to_dict() for svc in self._services.values()]
