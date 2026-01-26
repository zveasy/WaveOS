from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from waveos.utils.alerts import send_webhook


@dataclass
class AlertRoute:
    name: str
    destination: str
    url: Optional[str] = None
    min_level: str = "WARN"


def route_alerts(events: List[Dict[str, Any]], routes: List[AlertRoute], run_id: str) -> None:
    for route in routes:
        if route.destination == "webhook" and route.url:
            payload = {"run_id": run_id, "events": events, "route": route.name}
            send_webhook(route.url, payload)
        if route.destination == "slack":
            # Placeholder for Slack integration
            continue
        if route.destination == "email":
            # Placeholder for email integration
            continue
