from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from waveos.utils.alerts import send_webhook
from waveos.utils.alert_integrations import send_email, send_slack


_LEVEL_ORDER = {"INFO": 10, "WARN": 20, "ERROR": 30}


@dataclass
class AlertRoute:
    name: str
    destination: str
    url: Optional[str] = None
    min_level: str = "WARN"
    metadata: Dict[str, Any] = field(default_factory=dict)


def _level_value(level: str) -> int:
    return _LEVEL_ORDER.get(level.upper(), 0)


def route_alerts(events: List[Dict[str, Any]], routes: List[AlertRoute], run_id: str) -> None:
    for route in routes:
        min_level = _level_value(route.min_level)
        route_events = [event for event in events if _level_value(str(event.get("level", ""))) >= min_level]
        if not route_events:
            continue
        if route.destination == "webhook" and route.url:
            payload = {"run_id": run_id, "events": route_events, "route": route.name}
            send_webhook(route.url, payload)
        if route.destination == "slack" and route.url:
            send_slack(route.url, {"run_id": run_id})
        if route.destination == "email":
            recipient = route.url or ""
            provider = route.metadata.get("provider", "smtp")
            settings = route.metadata
            send_email(recipient, "Wave OS alert", f"run_id={run_id}", provider=provider, settings=settings)
