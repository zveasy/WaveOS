from __future__ import annotations

import json
import urllib.request
from typing import Any, Dict

from waveos.utils.retry import retry


# Timeout for outbound webhook/Slack requests (seconds)
WEBHOOK_REQUEST_TIMEOUT = 10


def send_webhook(url: str, payload: Dict[str, Any], retries: int = 2) -> None:
    def _send() -> None:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=WEBHOOK_REQUEST_TIMEOUT) as response:
            response.read()

    retry(_send, retries=retries, base_delay=0.2, max_delay=1.0)
